"""The `conduct init` command: scaffold a project's `conductor/` directory.

Three ways in, one result. `--template NAME` is the explicit, deterministic
path and the automation interface. A terminal without it gets a guided wizard
asking only what cannot be derived — project name, the harness that implements,
the harness that reviews. Anything that is not a terminal takes the same
default without reading stdin at all, because a command that can block on
input can block the whole of CI.

Nothing on the init path may inspect the machine: no PATH lookup, no
subprocess, no environment scan. Detecting installed harnesses is a capability
class of its own and needs its own ADR before any of it exists. What enforces
that is `test_init_never_probes_the_machine_for_installed_harnesses`. It runs
`conduct init` in a child interpreter, takes the `conductor.*` modules that
the run actually imported — this module, the harness registry, `__main__`, and
everything the three of them reach — and rejects a probing import or a
qualified probing call in any of them.

The walk stops at `conductor.*`, and it has to: `pathlib` imports both `os`
and `shutil`, and `argparse` imports both as well, so a rule phrased over
"everything init imports" would fail on the standard library before it ever
reached our code. Inside that boundary the two halves catch different
spellings. The import half is the blunt one — a banned module may not be
named at all. The qualified half makes a probe say where it came from: it
matches `os.environ`, never a bare `.environ`, which is what lets `__main__`
go on calling this module's entry point `init.run` instead of losing the name
to a rule that cannot tell it from `subprocess.run`.

Read it for what it is: a REPOSITORY GUARD, not a security sandbox. It stops a
probe from arriving by accident or without discussion. It does not stop a
determined one — `getattr` and a string defeat it in a line, and so does
reaching through a module nobody banned, since `pathlib.os.environ` is a
different string from `os.environ` and neither half matches it — and claiming
otherwise would be exactly the kind of overstatement the last two slices went
through the shipped prose to remove.

stdout carries one thing, the prompt that fills the generated map in. The
scaffold report, the validation verdict, the wizard and the advice that
follows are all dialogue and go to stderr, so redirecting `conduct init`
yields a promptable file and nothing else.
"""
from __future__ import annotations

import argparse
import sys
import textwrap
import tomllib
from collections.abc import Callable
from pathlib import Path

from conductor import harnesses, prompts, templates, validate


# --- what the wizard offers, and the copy it says it with -------------------

# The menu comes from `conductor.harnesses`: `RECOMMENDED` by number, then a
# `custom` row that names the rest without numbering them, then free text.
# There is no "Detected" section and there will not be one — NOTHING here
# inspects the machine, no PATH lookup, no subprocess, no environment scan.
#
# The registry's id is what lands in map.toml; its display name is shown
# beside the id and never written. A user who types their own answer gets
# exactly what they typed, registry or no registry.

#: The reviewer answer that means "no independent reviewer" — the one answer
#: that changes which template is written. Spelled so that it CANNOT be typed:
#: `templates.NAME_RE` requires a letter or digit first, so `(none)` is only
#: ever reachable by choosing its row. The bare word `none` used to be the
#: sentinel, which made it a harness id at the first prompt and a command at
#: the second; now `none` means the same thing at both — a harness called
#: `none` — and the sentinel belongs to the menu alone.
_NO_REVIEWER = "(none)"

# `harness` is presentation metadata: no merge rule computes on it. Asked at a
# prompt, though, it reads like configuring a tool integration, and a newcomer
# will reasonably expect Conduct to go and start something. Say what the answer
# does before they answer it.
_PRIMARY_QUESTION = "Which harness runs the implementing roles?"
_PRIMARY_NOTE = ("Conduct never launches, installs or detects a harness. The "
                 "answer only labels who does what, in the map and in the panel.")

# The reviewer question carries a structural decision inside a cosmetic one:
# every other answer names a product, while `none` removes the reviewing role
# altogether. Name that consequence at the point of choosing it, not in a
# comment the user reads afterwards.
_REVIEWER_QUESTION = "Which harness reviews their work?"
_NO_REVIEWER_GLOSS = (" — no reviewing role at all: findings then come out "
                      "agreed with nobody having looked")

# The one sentence naming what the user must do next. Said once, to the person;
# `prompts.bootstrap_prompt` states the same instruction to the agent in its
# own register, deliberately without sharing this text.
_FIRST_ACTION = ("Replace the placeholder nodes in conductor/map.toml with the "
                 "real components of your project — until you do, nothing it "
                 "reports is about your project.")


# --- talking to the person --------------------------------------------------


def _wrap(text: str, indent: str = "", hang: str | None = None) -> str:
    """Fold one paragraph to `prompts.WIDTH`, indenting every line.

    Args:
        text: A single paragraph, unwrapped.
        indent: Prefix for the first line.
        hang: Prefix for continuation lines; None reuses `indent`.

    Returns:
        The folded paragraph. Wrapping at render time rather than by hand is
        what keeps the width right after someone edits the sentence — every
        hand-wrapped line here has been re-broken by an edit at least once.
    """
    return textwrap.fill(text, width=prompts.WIDTH, initial_indent=indent,
                         subsequent_indent=indent if hang is None else hang)


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

    Everything a person reads during `init` goes through here: the wizard, the
    scaffold report, the validation verdict, the advice at the end. None of it
    is the command's result, so none of it may reach stdout — which carries
    the bootstrap prompt alone, identical on all three init paths. A caller
    capturing it therefore never reads back a question, least of all one the
    non-interactive fallback asked into the void.
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
            _say(_wrap(str(e), "  "))       # NAME_RULE alone runs past 100


def _ask_harness(ask: Callable[[str], str], question: str,
                 options: list[tuple[str, str]], note: str = "") -> str:
    """Offer a short numbered menu; any other legal name is taken as typed.

    Args:
        ask: The prompting function (`_console_ask` in a terminal).
        question: The headline shown above the menu.
        options: `(value, gloss)` pairs, most recommended first — option 1 is
            the default, so pressing Enter always works. A gloss hangs under
            its own value rather than running off the end of the row.
        note: An optional line saying what the answer does, shown before it
            is given rather than explained afterwards.

    Returns:
        The chosen value: a menu entry, or a harness id the user typed. A
        digit is an index only while it indexes this menu — out of range it is
        just what the user typed, so a harness genuinely called `7` stays
        reachable instead of being answered with an error.
    """
    _say(_wrap(question))
    if note:
        _say(_wrap(note, "  "))
    for index, (value, gloss) in enumerate(options, 1):
        _say(_wrap(f"{index}) {value}{gloss}", "  ", hang="     "))
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
            _say(_wrap(str(e), "  "))


def _menu(ids: list[str] | tuple[str, ...]) -> list[tuple[str, str]]:
    """`(value, gloss)` rows for `_ask_harness`: each id, glossed with its name.

    Args:
        ids: Harness ids, in the order they should be offered.

    Returns:
        Rows whose *value* is the id — the string that lands in `map.toml` —
        so choosing a row and typing the same id are the same answer. The
        product name rides in the gloss, where it informs the choice without
        ever becoming the choice.
    """
    return [(h, f" — {harnesses.resolve(h).display_name}") for h in ids]


def _custom_row() -> tuple[str, str]:
    """The `custom` row, which is also how the unnumbered harnesses are named.

    Returns:
        One `(value, gloss)` pair. Progressive disclosure with no second
        round-trip: the numbered list stays short, and this row's gloss — hung
        under its own line — says which other ids the registry knows, so the
        rest are reachable by typing rather than by a menu nobody reads.

        The gloss names both answers available here, because they do not
        produce the same file. Choosing the row writes the literal id
        `custom`; typing an id writes that id, listed or not, exactly as it
        was typed — except for the numbers the menu itself uses, which
        `_ask_harness` reads as a choice, so a legal id like `2` answers with
        the row it numbers. The gloss carries that exception rather than
        promising more than the prompt delivers. A row that taught only the
        typed answer would leave a user to discover the other from their own
        map.toml.
    """
    rest = ", ".join(h.id for h in harnesses.vendors()
                     if h.id not in harnesses.RECOMMENDED)
    return (harnesses.CUSTOM,
            f" — anything else: this row writes the id {harnesses.CUSTOM}. "
            f"Conduct also knows {rest} — type any id that is not a number "
            "above, listed or not, and it is written exactly as typed.")


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
    _say()
    primary = _ask_harness(ask, _PRIMARY_QUESTION,
                           _menu(harnesses.RECOMMENDED) + [_custom_row()],
                           note=_PRIMARY_NOTE)
    others = [h for h in harnesses.RECOMMENDED if h != primary]
    _say()
    reviewer = _ask_harness(ask, _REVIEWER_QUESTION,
                            _menu(others) + [_custom_row(),
                                             (_NO_REVIEWER, _NO_REVIEWER_GLOSS)])
    name = "single-harness" if reviewer == _NO_REVIEWER else templates.DEFAULT
    _say(f"\nWriting the {name} template:")
    _say(f"  project    {project}")
    _say(f"  implements {primary}")
    _say(f"  reviews    {reviewer}")
    if reviewer == primary:
        _say(_wrap("note: both roles run the same harness product, so this "
                   "review is not independent.", "  "))
    _say()
    return name, templates.get(name, project=project, primary=primary,
                               reviewer=None if reviewer == _NO_REVIEWER else reviewer)


# --- choosing what to write -------------------------------------------------


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


# --- writing it, and saying what happens next -------------------------------


def _dir_suffix(dirname: str) -> str:
    """The ` --dir …` a printed command needs, or `""` for the default root."""
    if dirname == ".":
        return ""
    return f' --dir "{dirname}"' if " " in dirname else f" --dir {dirname}"


def _print_next_steps(args: argparse.Namespace, text: str) -> None:
    """Say, on stderr, the first action and the commands that follow it."""
    where = _dir_suffix(args.dir)
    roles = tomllib.loads(text).get("cycle", {}).get("roles", [])
    _say("Your first action")
    _say(_wrap(_FIRST_ACTION, "  ") + "\n")
    _say("Next command")
    _say(f"  conduct validate{where}")
    _say("      silence means the map and every lane are valid\n")
    _say("Then")
    if roles:
        _say(f"  conduct prompt --role {roles[0]['id']}{where}")
        _say("      the working prompt for that role — paste it into your harness")
    _say(f"  conduct up{where}")
    # Derived, never retyped: init advising a port the panel does not bind
    # would be worse than saying nothing.
    _say(f"      the panel, at http://127.0.0.1:{args.default_port}/")


def _check_failed(cdir: Path, errors: list[str], warnings: list[str]) -> bool:
    """Say what the scaffold's own validation found; True if it is unusable.

    Args:
        cdir: The directory just written, named in the recovery line.
        errors: Schema failures. Any at all mean the scaffold is unusable.
        warnings: Informational remarks; they do not fail the command.

    Returns:
        True if the generated map failed validation, False if it is valid —
        with or without warnings. The failing branch is the one exit in `init`
        that leaves a directory behind, and a re-run refuses an existing one,
        so it says how to get unstuck rather than leaving the user to guess.
    """
    for line in errors or warnings:
        _say(line)
    if errors:
        _say(_wrap("the generated map did not validate — that is a bug, please "
                   f"report it. {cdir} was created and is left in place; remove "
                   "it before running conduct init again."))
        return True
    verdict = "valid, with the warnings above" if warnings else "clean — no warnings"
    _say(f"conduct validate: {verdict}.\n")
    return False


def _scaffold(args: argparse.Namespace, cdir: Path, name: str,
              text: str) -> int:
    """Write conductor/, check it, and emit the bootstrap prompt as the result.

    Everything a person reads — what was written, which template, the
    validation verdict, what to do next — is dialogue and goes to stderr. The
    prompt that fills the map in is the command's one deliverable, so it is
    all that stdout carries, byte for byte and identical whether the answers
    came from a wizard, from `--template`, or from neither.

    Returns:
        0 when the scaffold is written and valid; 1 if the root cannot be
        written to, or if the generated map fails its own validation.
    """
    try:
        (cdir / "lanes").mkdir(parents=True)
        (cdir / "events.jsonl").write_text("", encoding="utf-8", newline="\n")
        # No `+ "\n"`: templates.get() already ends in exactly one newline, and
        # a second would leave a blank line at the end of every user's map.
        (cdir / "map.toml").write_text(text, encoding="utf-8", newline="\n")
    except OSError as e:              # unwritable root, read-only mount, quota
        _say(f"cannot write {cdir}: {e}")
        return 1
    _say(f"scaffolded {cdir}: map.toml (edit me), lanes/, events.jsonl")
    _say(f"template: {name}\n")
    errors, warnings = validate.check(args.dir)
    if _check_failed(cdir, errors, warnings):
        return 1
    # The map is valid but generic, and the prompt is how that gap gets handed
    # to an agent. Unannounced it reads as "nothing was written" — but the
    # announcement is dialogue, so it goes to stderr and the prompt does not.
    # It does NOT restate _FIRST_ACTION: the same sentence twice in one screen
    # of output reads as two tasks just as surely as two different ones did.
    _say(_wrap("The map is valid but generic. The prompt that fills it in "
               "follows on stdout: paste it into an agent, or re-run with "
               "`> setup.txt` to keep it as a file.") + "\n")
    sys.stdout.write(prompts.bootstrap_prompt(str(cdir / "map.toml")))
    _say()
    _print_next_steps(args, text)
    return 0


def run(args: argparse.Namespace,
        ask: Callable[[str], str] | None = None) -> int:
    """Scaffold conductor/: `--template` is explicit, a terminal gets the wizard.

    This is `argparse`'s dispatch target, called as `args.func(args)` — there
    is no `_cmd_init` wrapper in the CLI, because a pass-through with this
    signature only gives the contract a second place to be restated.

    Args:
        args: The parsed `init` namespace.
        ask: An injected prompting function for the wizard; None (the CLI's
            own call) means detect a terminal and use `input`. `argparse`
            never passes it: the tests do.

    Returns:
        0 on success, 1 on every refusal. Three of those refuse before
        anything is written — an existing conductor/, an unknown template, a
        wizard abandoned at EOF or Ctrl-C. The fourth comes from `_scaffold`
        and is the exception: an unwritable root, or a generated map that
        fails its own validation, which leaves the directory in place.
    """
    cdir = Path(args.dir) / "conductor"
    if cdir.exists():                 # checked before any question is asked
        _say(f"{cdir} already exists — refusing to touch it")
        return 1
    try:
        name, text = _init_map_text(args, ask)
    except templates.UnknownTemplate as e:
        _say(str(e))
        return 1
    except (EOFError, KeyboardInterrupt):
        _say("\ninit cancelled — nothing was written")
        return 1
    return _scaffold(args, cdir, name, text)
