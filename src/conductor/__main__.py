"""The `conduct` command-line interface.

Subcommands: `validate` (schema errors → exit 1, merge warnings → stdout),
`init` (scaffold conductor/ and print the bootstrap prompt), `prompt --role R
[--author A]` (vend a role's working prompt; the positional role form is
deprecated), `up` (serve the panel on 127.0.0.1 with SSE
live updates; Ctrl-C → exit 0), `demo` (materialize the bundled fixture
into a temp directory and serve it — takes `--port` but no `--dir`). Every
other command takes `--dir` (the project root, default `.`). Exit codes
flow through `main`'s return value (0 ok, 1 failure); argparse exits 2 on
usage errors.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import tomllib
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from conductor import demo, merge, prompts, server, store, templates


def _merged_state(loaded: store.Loaded) -> dict:
    """Merge a `Loaded` snapshot into a state dict at the current time."""
    return merge.merge(loaded.map_data, loaded.map_error, loaded.lanes,
                       loaded.events, loaded.skipped_events,
                       datetime.now(timezone.utc),
                       extra_warnings=loaded.warnings)


def _cmd_validate(args: argparse.Namespace) -> int:
    """Print schema errors (exit 1) or merge warnings (exit 0)."""
    loaded = store.load(args.dir)
    errors = [entry["error"] for entry in loaded.lanes if entry["error"] is not None]
    if loaded.map_error is not None:
        errors.insert(0, loaded.map_error)
    if errors:
        for error in errors:          # already self-prefixed (lane <stem>: / map...)
            print(error)
        return 1
    state = _merged_state(loaded)
    for warning in state["warnings"]:
        print(warning)
    return 0


# The harnesses the wizard offers by name. Ids only, and deliberately short:
# the branded registry (display names, detection metadata) is DO-4, and this
# slice offers a recommended pair plus "type your own" rather than a wall of
# products. NOTHING here inspects the machine — no PATH lookup, no subprocess,
# no environment scan. Probing a user's box for installed harnesses is a new
# capability class and needs its own ADR before any of it exists.
_HARNESSES = ("claude-code", "codex")

#: The reviewer answer that means "no independent reviewer" — the one answer
#: that changes which template is written.
_NO_REVIEWER = "none"


def _interactive() -> bool:
    """True only for a real terminal on stdin — the sole gate on the wizard.

    Everything else — a pipe, a CI runner, a captured test stream, a closed or
    absent stdin — takes the deterministic path, which never reads stdin at
    all. A suite that can block on input blocks the whole of CI, so this
    errs toward "not a terminal" on every doubt.
    """
    stream = getattr(sys, "stdin", None)
    try:
        return bool(stream is not None and stream.isatty())
    except (AttributeError, ValueError, OSError):   # closed or substituted stream
        return False


def _say(message: str = "") -> None:
    """Write one line of interactive dialogue to stderr.

    The wizard is a conversation, not output. Keeping every question, menu and
    rejection off stdout means stdout carries the same scaffold report on all
    three init paths — so a caller capturing it never reads back a question,
    least of all one the non-interactive fallback asked into the void.
    """
    print(message, file=sys.stderr)


def _console_ask(prompt: str) -> str:
    """Read one line from a real terminal, with the prompt on stderr.

    `input(prompt)` writes its prompt to stdout, which is the one stream that
    must stay clean — and it writes it *before* discovering there is nothing
    to read, so on the EOF fallback path the question would outlive the
    session that never asked it.
    """
    print(prompt, end="", file=sys.stderr, flush=True)
    return input()


def _ask_name(ask: Callable[[str], str], question: str, default: str,
              kind: str) -> str:
    """Read one name, re-asking until it is legal; Enter takes `default`."""
    while True:
        answer = ask(f"{question} [{default}]: ").strip() or default
        try:
            return templates.check_name(kind, answer)
        except templates.InvalidName as e:
            _say(f"  {e}")


def _ask_harness(ask: Callable[[str], str], question: str,
                 options: list[tuple[str, str]]) -> str:
    """Offer a short numbered menu; any other legal name is taken as typed.

    Args:
        ask: The prompting function (`_console_ask` in a terminal).
        question: The headline shown above the menu.
        options: `(value, gloss)` pairs, most recommended first — option 1 is
            the default, so pressing Enter always works.

    Returns:
        The chosen value: a menu entry, or a harness id the user typed. A
        digit is an index only while it indexes this menu — out of range it is
        just what the user typed, so a harness genuinely called `7` stays
        reachable instead of being answered with an error.
    """
    _say(question)
    for index, (value, gloss) in enumerate(options, 1):
        _say(f"  {index}) {value}{gloss}")
    _say("  or type any other harness id")
    default = options[0][0]
    while True:
        answer = ask(f"  choice [{default}]: ").strip()
        if not answer:
            return default
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1][0]
        try:
            return templates.check_name("harness id", answer)
        except templates.InvalidName as e:
            _say(f"  {e}")


def _wizard(ask: Callable[[str], str], default_project: str) -> tuple[str, str]:
    """Ask the three questions `conduct init` cannot answer for you.

    Args:
        ask: The prompting function; injectable so tests drive a script.
        default_project: What Enter accepts as the project name.

    Returns:
        `(template name, map.toml text)`. Everything is collected, validated
        and echoed before this returns — the caller writes nothing until it
        does, so an abandoned or rejected answer leaves no directory behind.

    Raises:
        EOFError: Propagated from `ask` when stdin closes mid-question.
        KeyboardInterrupt: Propagated from `ask` on Ctrl-C.
    """
    _say("conduct init — three questions, and Enter takes the default.\n")
    project = _ask_name(ask, "Project name", default_project, "project name")
    primary = _ask_harness(ask, "\nWhich harness runs the implementing roles?",
                           [(h, "") for h in _HARNESSES])
    others = [(h, "") for h in _HARNESSES if h != primary]
    reviewer = _ask_harness(
        ask, "\nWhich harness reviews their work?",
        others + [(_NO_REVIEWER, " — no independent reviewer")])
    name = "single-harness" if reviewer == _NO_REVIEWER else templates.DEFAULT
    _say(f"\nWriting the {name} template:")
    _say(f"  project    {project}")
    _say(f"  implements {primary}")
    _say(f"  reviews    {reviewer}")
    if reviewer == primary:
        _say("  note: both roles run the same harness product, so this review "
             "is not independent.")
    _say()
    return name, templates.get(name, project=project, primary=primary,
                               reviewer=None if reviewer == _NO_REVIEWER else reviewer)


def _default_project(dirname: str) -> str:
    """The project root's own directory name, when that is a legal name."""
    name = Path(dirname).resolve().name
    return name if templates.NAME_RE.fullmatch(name) else "your-project"


class _Prompter:
    """An `ask` that remembers whether it ever came back with an answer.

    The difference decides what an EOF means: after an answer it is a person
    abandoning the wizard, before one it is a session that was never
    interactive at all, however loudly stdin claimed otherwise.
    """

    def __init__(self, ask: Callable[[str], str]) -> None:
        self._ask = ask
        self.answered = False

    def __call__(self, prompt: str) -> str:
        answer = self._ask(prompt)
        self.answered = True          # set even when the answer is rejected
        return answer


def _init_map_text(args: argparse.Namespace,
                   ask: Callable[[str], str] | None) -> tuple[str, str]:
    """Choose the starting map: explicit `--template`, the wizard, or the default.

    Args:
        args: The parsed `init` namespace.
        ask: An injected prompting function, which by itself means "this is an
            interactive session"; None means detect a terminal and use `input`.

    Returns:
        `(template name, map.toml text)`. Writes nothing.

    Raises:
        EOFError: Only when stdin closes AFTER at least one answer — a wizard
            a person started and abandoned.
        KeyboardInterrupt: Propagated from the wizard on Ctrl-C.
    """
    if args.template is not None:
        return args.template, templates.get(args.template)
    default = (templates.DEFAULT, templates.get(templates.DEFAULT))
    if ask is None and not _interactive():
        return default
    prompter = _Prompter(_console_ask if ask is None else ask)
    try:
        return _wizard(prompter, _default_project(args.dir))
    except EOFError:
        if prompter.answered:
            raise
        # isatty() said terminal and the first read hit EOF. On Windows that
        # is `conduct init < NUL` — stdin redirected from the null DEVICE,
        # which isatty()s as a console — and that is precisely the shape a
        # script uses to mean "no input". Answer it the way the non-TTY path
        # would rather than failing an automated caller.
        _say("\nno input available — writing the default template instead.\n")
        return default


def _dir_suffix(dirname: str) -> str:
    """The ` --dir …` a printed command needs, or `""` for the default root."""
    if dirname == ".":
        return ""
    return f' --dir "{dirname}"' if " " in dirname else f" --dir {dirname}"


def _print_next_steps(args: argparse.Namespace, text: str) -> None:
    """Print the first action, the next command, and how to open the panel."""
    where = _dir_suffix(args.dir)
    roles = tomllib.loads(text).get("cycle", {}).get("roles", [])
    print("Your first action")
    print("  Open conductor/map.toml and replace every PLACEHOLDER node with a "
          "real\n  component of your project. Until you do, nothing it reports "
          "is about\n  your project.\n")
    print("Next command")
    print(f"  conduct validate{where}")
    print("      silence means the map and every lane are valid\n")
    print("Then")
    if roles:
        print(f"  conduct prompt --role {roles[0]['id']}{where}")
        print("      the working prompt for that role — paste it into your harness")
    print(f"  conduct up{where}")
    print("      the panel, at http://127.0.0.1:7777/")


def _scaffold(args: argparse.Namespace, cdir: Path, name: str, text: str) -> int:
    """Write conductor/, run the same check `conduct validate` runs, then advise."""
    (cdir / "lanes").mkdir(parents=True)
    (cdir / "events.jsonl").write_text("", encoding="utf-8", newline="\n")
    # No `+ "\n"`: templates.get() already ends in exactly one newline, and a
    # second would leave a blank line at the end of every user's committed map.
    (cdir / "map.toml").write_text(text, encoding="utf-8", newline="\n")
    print(f"scaffolded {cdir}: map.toml (edit me), lanes/, events.jsonl")
    print(f"template: {name}\n")
    # The map on disk is a valid placeholder, not a description of this
    # project. The bootstrap prompt is how you hand that gap to an agent, so
    # it needs a line saying so — unheaded, it reads as "nothing was written".
    print("To have an agent fill it in for you, paste everything between the "
          "rules:\n" + "-" * 74)
    print(prompts.bootstrap_prompt() + "-" * 74 + "\n")
    if _cmd_validate(args) != 0:
        print("the generated map did not validate — that is a bug, please report it",
              file=sys.stderr)
        return 1
    print("conduct validate: clean — the map is valid as written.\n")
    _print_next_steps(args, text)
    return 0


def _cmd_init(args: argparse.Namespace,
              ask: Callable[[str], str] | None = None) -> int:
    """Scaffold conductor/: `--template` is explicit, a terminal gets the wizard.

    Args:
        args: The parsed `init` namespace.
        ask: An injected prompting function for the wizard; None (the CLI's
            own call) means detect a terminal and use `input`.

    Returns:
        0 on success; 1 for an existing conductor/, an unknown template, or a
        wizard abandoned at EOF or Ctrl-C. Nothing is written on any of them.
    """
    cdir = Path(args.dir) / "conductor"
    if cdir.exists():                 # checked before any question is asked
        print(f"{cdir} already exists — refusing to touch it", file=sys.stderr)
        return 1
    try:
        name, text = _init_map_text(args, ask)
    except templates.UnknownTemplate as e:
        print(str(e), file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\ninit cancelled — nothing was written", file=sys.stderr)
        return 1
    return _scaffold(args, cdir, name, text)


def _cmd_prompt(args: argparse.Namespace) -> int:
    """Render the role prompt; bad author, broken map, or unknown role → stderr, exit 1."""
    if args.role_positional is not None and args.role is not None:
        args.prompt_parser.error("give the role via --role or positionally, not both")
    if args.role_positional is None and args.role is None:
        args.prompt_parser.error("a role is required: conduct prompt --role <role>")
    if args.role_positional is not None:
        print("warning: positional role is deprecated; use --role/--author",
              file=sys.stderr)
    role = args.role if args.role is not None else args.role_positional
    if args.author is not None and not store.AUTHOR_RE.fullmatch(args.author):
        print(f"invalid author {args.author!r}: must match the lane filename "
              "rule (letters, digits, _ and - only)", file=sys.stderr)
        return 1
    loaded = store.load(args.dir)
    if loaded.map_error is not None:  # a substitute empty map would mislead the agent
        print(f"cannot vend a prompt: {loaded.map_error}", file=sys.stderr)
        return 1
    try:
        text = prompts.role_prompt(_merged_state(loaded), role, args.author)
    except prompts.UnknownRole as e:
        print(str(e), file=sys.stderr)
        return 1
    print(text)
    return 0


def _serve(root: Path | str, port: int) -> int:
    """Serve the panel for `root` on 127.0.0.1; Ctrl-C shuts down cleanly."""
    try:
        srv = server.build(root, port=port)
    except OSError as e:                  # port busy / unbindable → exit 1
        print(f"cannot serve on 127.0.0.1:{port}: {e}", file=sys.stderr)
        return 1
    host, bound = srv.server_address[:2]
    print(f"serving http://{host}:{bound}/ — Ctrl+C to stop")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


def _cmd_up(args: argparse.Namespace) -> int:
    """Serve the panel on 127.0.0.1; Ctrl-C shuts down cleanly (exit 0)."""
    return _serve(args.dir, args.port)


def _cmd_demo(args: argparse.Namespace) -> int:
    """Materialize the bundled demo fixture into a temp dir and serve it."""
    try:
        root = demo.materialize(Path(tempfile.mkdtemp(prefix="conduct-demo-")))
    except OSError as e:                  # unwritable temp dir / broken package data
        print(f"cannot materialize the demo fixture: {e}", file=sys.stderr)
        return 1
    print(f"demo fixture materialized in {root} (throwaway copy)")
    return _serve(root, args.port)


def _add_dir_and_func(p: argparse.ArgumentParser,
                      func: Callable[[argparse.Namespace], int]) -> None:
    """Attach the shared `--dir` option and the dispatch target to a subparser."""
    p.add_argument("--dir", default=".",
                   help="project root, the directory holding conductor/ (default: .)")
    p.set_defaults(func=func)


def _build_parser() -> argparse.ArgumentParser:
    """Build the `conduct` argument parser: one explicit block per subcommand."""
    parser = argparse.ArgumentParser(
        prog="conduct",
        description="A local, decision-centric control plane for AI coding agents.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate",
                       help="check map.toml and lane files; report errors and warnings")
    _add_dir_and_func(p, _cmd_validate)

    p = sub.add_parser("init", help="scaffold conductor/ and print the bootstrap prompt")
    # Deliberately NOT argparse `choices`: that raises a usage error (exit 2)
    # and hardcodes a second copy of the list. The explicit check in
    # _cmd_init exits 1 with templates.get()'s own message, so the available
    # names can never drift from the module that vends them.
    p.add_argument("--template", metavar="NAME",
                   help="starting map: " + ", ".join(n for n, _ in templates.names())
                        + f" (default: {templates.DEFAULT}; omit it in a terminal "
                          "to be asked instead)")
    _add_dir_and_func(p, _cmd_init)

    p = sub.add_parser("prompt", help="print the working prompt for one cycle role")
    # ADR 0001: the positional is the DEPRECATED spelling of --role and its
    # meaning must NEVER be silently redefined (e.g. to an instance id in v2) —
    # any new addressing scheme gets its own flag.
    p.add_argument("role_positional", nargs="?", metavar="role", default=None,
                   help="deprecated positional form of --role")
    p.add_argument("--role", help="a cycle.roles id from map.toml")
    p.add_argument("--author",
                   help="your lane author id — fills conductor/lanes/<author>.json "
                        "into the prompt")
    p.set_defaults(prompt_parser=p)   # lets _cmd_prompt raise argparse usage errors
    _add_dir_and_func(p, _cmd_prompt)

    p = sub.add_parser("up", help="serve the panel on loopback HTTP with live updates")
    p.add_argument("--port", type=int, default=7777,
                   help="TCP port on 127.0.0.1 (default: 7777)")
    _add_dir_and_func(p, _cmd_up)

    # No --dir: demo materializes its own throwaway root.
    p = sub.add_parser("demo", help="serve the bundled demo fixture")
    p.add_argument("--port", type=int, default=7777,
                   help="TCP port on 127.0.0.1 (default: 7777)")
    p.set_defaults(func=_cmd_demo)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the `conduct` CLI.

    Args:
        argv: Command-line arguments without the program name; None means
            `sys.argv[1:]` (argparse's default).

    Returns:
        Process exit code: 0 on success, 1 on any reported failure
        (schema errors, missing conductor/, unknown role, broken map).
    """
    # Windows consoles/pipes default to the ANSI code page; the messages and
    # prompts we emit contain non-ASCII punctuation. capsys-style substitute
    # streams may lack reconfigure — hence the hasattr guard.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args(argv)
    try:
        return args.func(args)
    except store.StoreError as e:
        print(str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
