"""The `conduct init` command: scaffold a project's `conductor/` directory.

Three ways in, one result. `--template NAME` is the explicit, deterministic
path and the automation interface. A terminal without it gets a guided wizard
asking only what cannot be derived — project name, the harness that implements,
the harness that reviews. Anything that is not a terminal takes the same
default without reading stdin at all, because a command that can block on
input can block the whole of CI.

Nothing in this module, or anything it imports, may inspect the machine: no
PATH lookup, no subprocess, no environment scan. Detecting installed harnesses
is a capability class of its own and needs its own ADR before any of it exists.
Keeping the init path in one module is what makes that ban statable as a
property of an import graph rather than a hand-kept list of file names.

Validation is injected rather than imported (`run(..., validate=...)`): the
scaffold is checked with exactly the computation `conduct validate` performs,
without this module depending on the CLI that renders it.
"""
from __future__ import annotations

import argparse
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

from conductor import prompts, templates

#: What `run` needs of `conduct validate`: the errors and warnings it would
#: report for a project root, as data, leaving the rendering to the caller.
Validation = Callable[[argparse.Namespace], "tuple[list[str], list[str]]"]


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

# `harness` is presentation metadata: no merge rule computes on it. Asked at a
# prompt, though, it reads like configuring a tool integration, and a newcomer
# will reasonably expect Conduct to go and start something. Say what the answer
# does before they answer it.
_PRIMARY_QUESTION = (
    "\nWhich harness runs the implementing roles?\n"
    "  Conduct never launches, installs or detects a harness. The answer only\n"
    "  labels who does what, in the map and in the panel.")

# The reviewer question carries a structural decision inside a cosmetic one:
# every other answer names a product, while `none` removes the reviewing role
# altogether. Name that consequence at the point of choosing it, not in a
# comment the user reads afterwards.
_REVIEWER_QUESTION = "\nWhich harness reviews their work?"
_NO_REVIEWER_GLOSS = (" — no reviewing role at all: findings then come out "
                      "agreed with nobody having looked")


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
    primary = _ask_harness(ask, _PRIMARY_QUESTION, [(h, "") for h in _HARNESSES])
    others = [(h, "") for h in _HARNESSES if h != primary]
    reviewer = _ask_harness(
        ask, _REVIEWER_QUESTION, others + [(_NO_REVIEWER, _NO_REVIEWER_GLOSS)])
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


# The one sentence naming what the user must do next. Said once, to both
# audiences: here to the person, and inside `bootstrap_prompt` to the agent
# they may hand it to. Two differently-worded first actions read as two tasks.
_FIRST_ACTION = ("Replace the placeholder nodes in conductor/map.toml with the "
                 "real components of your project — until you do, nothing it "
                 "reports is about your project.")


def _print_next_steps(args: argparse.Namespace, text: str) -> None:
    """Say, on stderr, the first action and the commands that follow it."""
    where = _dir_suffix(args.dir)
    roles = tomllib.loads(text).get("cycle", {}).get("roles", [])
    _say("Your first action")
    _say(f"  {_FIRST_ACTION}\n")
    _say("Next command")
    _say(f"  conduct validate{where}")
    _say("      silence means the map and every lane are valid\n")
    _say("Then")
    if roles:
        _say(f"  conduct prompt --role {roles[0]['id']}{where}")
        _say("      the working prompt for that role — paste it into your harness")
    _say(f"  conduct up{where}")
    _say("      the panel, at http://127.0.0.1:7777/")


def _scaffold(args: argparse.Namespace, cdir: Path, name: str, text: str,
              validate: Validation) -> int:
    """Write conductor/, check it, and emit the bootstrap prompt as the result.

    Everything a person reads — what was written, which template, the
    validation verdict, what to do next — is dialogue and goes to stderr. The
    prompt that fills the map in is the command's one deliverable, so it is
    all that stdout carries, byte for byte and identical whether the answers
    came from a wizard, from `--template`, or from neither.
    """
    (cdir / "lanes").mkdir(parents=True)
    (cdir / "events.jsonl").write_text("", encoding="utf-8", newline="\n")
    # No `+ "\n"`: templates.get() already ends in exactly one newline, and a
    # second would leave a blank line at the end of every user's committed map.
    (cdir / "map.toml").write_text(text, encoding="utf-8", newline="\n")
    _say(f"scaffolded {cdir}: map.toml (edit me), lanes/, events.jsonl")
    _say(f"template: {name}\n")
    errors, warnings = validate(args)
    if errors:
        for error in errors:
            _say(error)
        _say("the generated map did not validate — that is a bug, please report it")
        return 1
    for warning in warnings:          # exit 0 either way, so say which one it is
        _say(warning)
    verdict = "valid, with the warnings above" if warnings else "clean — no warnings"
    _say(f"conduct validate: {verdict}.\n")
    # The map is valid but generic, and the prompt is how that gap gets handed
    # to an agent. Unannounced it reads as "nothing was written" — but the
    # announcement is dialogue, so it goes to stderr and the prompt does not.
    # It does NOT restate _FIRST_ACTION: the same sentence twice in one screen
    # of output reads as two tasks just as surely as two different ones did.
    _say("The map is valid but generic. The prompt that fills it in follows on "
         "stdout —\npaste it into an agent, or re-run with `> setup.txt` to keep "
         "it as a file.\n")
    sys.stdout.write(prompts.bootstrap_prompt(str(cdir / "map.toml")))
    _say()
    _print_next_steps(args, text)
    return 0


def execute(args: argparse.Namespace, ask: Callable[[str], str] | None = None,
            *, validate: Validation) -> int:
    """Scaffold conductor/: `--template` is explicit, a terminal gets the wizard.

    Args:
        args: The parsed `init` namespace.
        ask: An injected prompting function for the wizard; None (the CLI's
            own call) means detect a terminal and use `input`.
        validate: The check `conduct validate` performs, returning
            `(errors, warnings)` for `args.dir`.

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
    return _scaffold(args, cdir, name, text, validate)
