"""The `conduct` command-line interface.

Subcommands: `validate` (schema errors → exit 1, merge warnings → exit 0);
`init` (scaffold conductor/ from a template and print the prompt that fills
it in — `--template NAME` is the explicit path, a terminal without it gets a
guided wizard, and anything that is not a terminal takes the same default
without reading stdin); `doctor` (report whether this project is set up to
work and name the command that fixes each problem — exit 1 while anything is
wrong or could not be checked); `prompt --role R [--author A]` (vend a role's
working prompt; the positional role form is deprecated); `report` (render the
merged state as a Markdown report); `preview` (create/open a run with a frozen
config, propose one dispatch through the command service, and print its canonical
preview for inspection — it prepares and executes nothing); `confirm` (run the
fixed Day-1 loop through the owned-process adapter, verify honestly, and print
the immutable result receipt);
`up` (serve the panel
on 127.0.0.1 with SSE
live updates; Ctrl-C → exit 0); `demo` (materialize the bundled fixture into a
temp directory and serve it — takes `--port` but no `--dir`). Every other
command takes `--dir` (the project root, default `.`).

THE STREAM CONTRACT, which every command here obeys and every command added
here must obey. stdout carries the command's primary result and nothing else,
so that redirecting it yields something usable on its own: the rendered prompt
for `prompt`, the bootstrap prompt for `init`, the validation report for
`validate`, the Markdown report for `report`, the bare URL for `up` and
`demo`. stderr carries everything a
person reads around that — dialogue, progress, explanations, deprecation
warnings, and errors that mean the command could not run.

Two deliberate exceptions. What `validate` found IS its result, so findings
stay on stdout even when the exit code is 1; and a clean `validate` prints
nothing at all, on either stream. Whether a terminal is attached changes the
conversation on stderr, never a byte of stdout.

Nothing structural enforces this. It is held by review and by one contract
test per command, in `tests/test_cli.py` and — for `init` — `tests/test_init.py`;
a new command that prints its progress to stdout would pass every other check
in the suite.

Exit codes flow through `main`'s return value (0 ok, 1 failure); argparse
exits 2 on usage errors.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from conductor import doctor, init, prompts, report, store, templates, validate

# `conductor.demo`, `conductor.server`, `conductor.command.preview`, and
# `conductor.command.control_loop` are imported inside the commands that need
# them, not here. demo copies a tree with `shutil`, server reads `os.environ`, and
# the command modules' run store uses `os`/`tempfile` for durable writes — all
# legitimate, none a probe, but importing them at module scope would put them on
# the import path of EVERY command, `conduct init` included. The machine-probing
# guard in tests/test_init_probing_ban.py measures what a real `conduct init`
# imports, so hoisting any of them back to the top makes that test fail. That is
# the point: the boundary is enforced, not asserted.


def _cmd_validate(args: argparse.Namespace) -> int:
    """Print schema errors (exit 1) or merge warnings (exit 0)."""
    errors, warnings = validate.check(args.dir)
    for line in errors or warnings:
        print(line)
    return 1 if errors else 0


# No `_cmd_init`: `init.run(args)` already has the `args.func(args)` shape, so
# a wrapper here would be pure indirection restating a contract that lives in
# `conductor.init`. Its `ask=` parameter, which argparse never passes, belongs
# to the tests that inject a scripted wizard — and they test `conductor.init`.


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
        state = validate.merged_state(loaded)
        text = prompts.role_prompt(state, role, args.author)
    except prompts.UnknownRole as e:
        print(str(e), file=sys.stderr)
        return 1
    # write, not print: role_prompt() already ends in a newline, and print's
    # own would put a blank line at the end of every redirected prompt.
    sys.stdout.write(text)
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    """Write the Markdown report of the merged state to stdout.

    The state comes from `store.load` + `validate.merged_state` — the same two
    calls `prompt` makes, and no second merge is written here.
    `tests/test_report.py` measures the rest of that claim by running this
    command: on one project, what it writes to stdout is the report of the very
    document the panel's server serves, `generated_at` apart. A missing
    `conductor/` raises `store.StoreError`, which `main` reports on stderr with
    exit 1; stdout stays empty, so a redirected report file is never a
    half-written one. A map that will not parse is not that failure: the merger
    represents it as `project_status.state == "unknown"`, which is a state worth
    reporting.
    """
    state = validate.merged_state(store.load(args.dir))
    # write, not print: render() already ends in exactly one newline.
    sys.stdout.write(report.render(state))
    return 0


def _serve(root: Path | str, port: int) -> int:
    """Serve the panel for `root` on 127.0.0.1; Ctrl-C shuts down cleanly."""
    from conductor import server              # deferred: see the import block
    try:
        srv = server.build(root, port=port)
    except OSError as e:                  # port busy / unbindable → exit 1
        # `port` is the one the user asked for, and the ONLY port this message
        # may name: an OSError is not proof the port is busy, and no other
        # port is known to be free, so the hint keeps the PORT placeholder
        # literal instead of volunteering a number.
        print(f"cannot serve on 127.0.0.1:{port}: {e}. "
              "To try a different port, rerun with --port PORT.", file=sys.stderr)
        return 1
    host, bound = srv.server_address[:2]
    # The URL is the result; how to stop the server is lifecycle chatter. Split
    # so `conduct up | xargs open` gets a URL and not a sentence about it.
    #
    # flush=True is load-bearing, not tidiness. A redirected stdout is
    # block-buffered, and the next statement blocks until the server stops —
    # so without the flush the URL reaches the pipe only once it is useless,
    # and a killed server never emits it at all. stderr needs no flush: it is
    # line-buffered whether or not it is a terminal.
    print(f"http://{host}:{bound}/", flush=True)
    print(f"serving {root} — Ctrl+C to stop", file=sys.stderr)
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
    import tempfile               # local to its one use; no boundary rides on it
    from conductor import demo                # deferred: see the import block
    try:
        root = demo.materialize(Path(tempfile.mkdtemp(prefix="conduct-demo-")))
    except OSError as e:                  # unwritable temp dir / broken package data
        print(f"cannot materialize the demo fixture: {e}", file=sys.stderr)
        return 1
    print(f"demo fixture materialized in {root} (throwaway copy)", file=sys.stderr)
    return _serve(root, args.port)


def _cmd_preview(args: argparse.Namespace) -> int:
    """Print the canonical dispatch preview for one configured instance.

    The Day-1 control-loop gate: it opens (or creates) a run with a frozen config,
    asks the fixed CommandService for one dispatch proposal bound to the instance,
    and writes that proposal's canonical JSON — preview_digest included — to stdout
    for inspection. It prepares, executes and spawns nothing. An unknown instance,
    an adapter that does not match the frozen config's binding, and a run already
    standing at the preview's identity that is not the preview's own run are each
    a refusal on stderr with exit 1; stdout stays empty, so a redirected preview
    is never a half-written one.
    """
    from conductor.command import preview          # deferred: see the import block
    try:
        rendered = preview.render_dispatch_preview(
            args.dir, instance_id=args.instance, adapter_id=args.adapter)
    except preview.PreviewError as e:
        print(str(e), file=sys.stderr)
        return 1
    # write, not print: the canonical preview is one line and gets exactly one
    # trailing newline, so a redirected preview is a clean single-line document.
    sys.stdout.write(rendered + "\n")
    return 0


def _cmd_confirm(args: argparse.Namespace) -> int:
    """Run the Day-1 control loop and print the immutable result receipt.

    The companion to `preview`: it opens the fixed scenario's run, confirms one
    fixed dispatch, executes it through the owned-process adapter, verifies, and
    writes the canonical result receipt to stdout. A run at the
    scenario's fixed identity that disagrees with it is a refusal on stderr with
    exit 1; stdout stays empty, so a redirected receipt is never a half-written one.
    """
    from conductor.command import control_loop      # deferred: see the import block
    try:
        rendered = control_loop.render_control_loop(args.dir)
    except control_loop.GateError as e:
        print(str(e), file=sys.stderr)
        return 1
    # write, not print: the canonical receipt is one line and gets exactly one
    # trailing newline, so a redirected receipt is a clean single-line document.
    sys.stdout.write(rendered + "\n")
    return 0


#: The port `up` and `demo` bind, and the one `init` tells the user to open.
#: One constant, because init advising a port the panel is not on is worse
#: than init saying nothing about the panel at all.
DEFAULT_PORT = 7777


def _add_port(p: argparse.ArgumentParser) -> None:
    """Attach the shared `--port` option to a serving subparser."""
    p.add_argument("--port", type=int, default=DEFAULT_PORT,
                   help=f"TCP port on 127.0.0.1 (default: {DEFAULT_PORT})")


def _add_dir_and_func(p: argparse.ArgumentParser,
                      func: Callable[[argparse.Namespace], int]) -> None:
    """Attach the shared `--dir` option and the dispatch target to a subparser."""
    p.add_argument("--dir", default=".",
                   help="project root, the directory holding conductor/ (default: .)")
    p.set_defaults(func=func)


def _add_template(p: argparse.ArgumentParser) -> None:
    """Attach `init`'s `--template`, whose help lists the maps `templates` vends."""
    # Deliberately NOT argparse `choices`: that raises a usage error (exit 2)
    # and hardcodes a second copy of the list. The explicit check in
    # `init.run` exits 1 with templates.get()'s own message, so the available
    # names can never drift from the module that vends them.
    p.add_argument("--template", metavar="NAME",
                   help="starting map: " + ", ".join(n for n, _ in templates.names())
                        + f" (default: {templates.DEFAULT}; omit it in a terminal "
                          "to be asked instead)")


def _add_role_and_author(p: argparse.ArgumentParser) -> None:
    """Attach `prompt`'s role addressing, keeping the positional spelling deprecated."""
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


def _add_instance_and_adapter(p: argparse.ArgumentParser) -> None:
    """Attach `preview`'s addressing; the frozen config, not this flag, binds the adapter."""
    p.add_argument("--instance", default="claude-dev",
                   help="the configured instance to propose against (default: claude-dev)")
    p.add_argument("--adapter", default=None,
                   help="cross-check the adapter the frozen config binds to the instance")


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
    p.set_defaults(default_port=DEFAULT_PORT)   # init advises it, never binds it
    _add_template(p)
    _add_dir_and_func(p, init.run)

    p = sub.add_parser("doctor",
                       help="check whether this project is set up to work, and how to fix it")
    _add_dir_and_func(p, doctor.run)

    p = sub.add_parser("prompt", help="print the working prompt for one cycle role")
    _add_role_and_author(p)
    _add_dir_and_func(p, _cmd_prompt)

    p = sub.add_parser("report", help="print a Markdown report of the merged state")
    _add_dir_and_func(p, _cmd_report)

    p = sub.add_parser(
        "preview",
        help="propose one dispatch and print its canonical preview (no execution)")
    _add_instance_and_adapter(p)
    _add_dir_and_func(p, _cmd_preview)

    p = sub.add_parser(
        "confirm",
        help="run the Day-1 owned-process control loop and print the receipt")
    _add_dir_and_func(p, _cmd_confirm)

    p = sub.add_parser("up", help="serve the panel on loopback HTTP with live updates")
    _add_port(p)
    _add_dir_and_func(p, _cmd_up)

    # No --dir: demo materializes its own throwaway root.
    p = sub.add_parser("demo", help="serve the bundled demo fixture")
    _add_port(p)
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
