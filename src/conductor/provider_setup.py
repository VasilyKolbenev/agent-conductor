"""The `conduct providers` command: configure a provider without an editor.

Until this existed, the only way to make this build able to run anything was to
hand-write `conductor/providers.json`. Three surfaces said so in three places,
and `docs/owner-acceptance.md` called it "the one place the script sends you
back to a file". That was the honest description of a gap, not a design: an
owner acceptance script that requires a text editor has not been completed by
anybody who does not already know the schema.

WHY A WIZARD AND NOT FLAGS. `__main__` states, and means, that `--providers` is
"deliberately a PATH and nothing else, so no provider setting is ever spelled on
a command line". A `conduct providers add --executable ...` shape would put a
machine path -- and eventually, from somebody in a hurry, a secret -- into shell
history, process listings and CI logs. An interactive prompt puts it in none of
those. So this asks.

WHY NOT A FORM IN THE STUDIO. A provider pins an ABSOLUTE path on this machine.
The reviewed position has been that no browser should be able to write one, and
nothing here overturns it: the mandate asked for a Studio or a CLI flow, and the
CLI one keeps that position rather than trading it away.

WHAT IT WILL NOT TAKE. A credential value, and not because it screens for one.
It asks for the NAMES of environment variables, and a name is
`[A-Za-z_][A-Za-z0-9_]*` -- so `ANTHROPIC_API_KEY=sk-...` is refused for the
`=`, and `sk-abc123` for the `-`. There is nowhere in this dialogue that a
secret fits, which is a stronger property than a filter that has to recognise
one.

WHAT IT DERIVES RATHER THAN ASKS. The protocol: it is a fact about the provider,
carried by the catalogue, and asking a person to retype it only creates a way to
get it wrong. And the injecting-environment refusal is applied HERE, while
somebody is choosing the name, rather than only at the spawn door -- ADR 0007
records that gap in its own words: a refused name in the file surfaces late as
"the harness could not start the pinned build", naming neither the variable nor
the file.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

from conductor import store

#: What a person is told before a single question is asked. It is the whole
#: security contract of this dialogue, said once, in advance, in plain words.
_PREAMBLE = (
    "conduct providers — tell this build about a harness on this machine.\n"
    "\n"
    "Nothing you type here is a secret. A credential is NAMED, never written: "
    "you give the name of an environment variable, and its value is read from "
    "your environment when a step runs. The file this writes holds no value, "
    "no argv, no working directory and no URL.\n"
    "\n"
    "Your TERMINAL echoes what you type, and this command cannot stop it: a "
    "credential pasted here would be on your screen and in your scrollback "
    "whatever this command did. What it does promise is that it will never "
    "repeat one back — a refusal names the question, not the token.")
_ENV_QUESTION = (
    "Environment variable NAMES this provider may read, separated by spaces.\n"
    "  Names only — never a value, and never NAME=value. Enter for none.")


class SetupError(RuntimeError):
    """The setup flow cannot continue, and the message says why."""


def _say(message: str = "") -> None:
    """One line of dialogue on stderr; stdout carries the command's result."""
    print(message, file=sys.stderr)


def _console_ask(prompt: str) -> str:
    """Read one line from a real terminal, with the prompt on stderr.

    `input(prompt)` writes its prompt to stdout, which must stay clean, and
    writes it before discovering there is nothing to read.
    """
    print(prompt, end="", file=sys.stderr, flush=True)
    return input()


def _interactive() -> bool:
    """True only for a real terminal on stdin, exactly as `conduct init` asks."""
    stream = getattr(sys, "stdin", None)
    try:
        return bool(stream is not None and stream.isatty())
    except (AttributeError, ValueError, OSError):
        return False


def _catalogued() -> list[tuple[str, str, str]]:
    """Every provider this build knows how to construct: (id, protocol, name).

    Read from the catalogue rather than listed here. This module names no
    provider, so a roster that grows or shrinks moves the menu with it and
    nothing has to remember to follow.
    """
    from conductor.command.providers import PROVIDER_CATALOG

    return [(entry.provider_id, entry.protocol, entry.display_name)
            for entry in (PROVIDER_CATALOG[key] for key in sorted(PROVIDER_CATALOG))]


def _choose_provider(ask: Callable[[str], str]) -> tuple[str, str, str]:
    """Offer the catalogue as a numbered menu; re-ask until a row is chosen.

    Only a printed row selects: there is no free-text arm, because a provider
    this build cannot construct is one the file would be refused for naming.
    """
    rows = _catalogued()
    _say("\nWhich provider is installed on this machine?")
    for number, (provider_id, _protocol, display) in enumerate(rows, 1):
        _say(f"  {number}) {provider_id} — {display}")
    while True:
        answer = ask("  choice [1]: ").strip() or "1"
        if answer.isdigit() and 1 <= int(answer) <= len(rows):
            return rows[int(answer) - 1]
        _say(f"  choose one of 1–{len(rows)}.")


def _ask_absolute(ask: Callable[[str], str], question: str, *,
                  optional: bool, noun: str = "executable") -> str:
    """Read one absolute path, re-asking until it is one.

    Judged by the same predicate the durable contract uses, imported rather than
    reimplemented: a wizard with its own idea of "absolute" would accept a path
    the config then refuses, after the person had been told it was saved.

    `noun` is what the empty answer is refused FOR. It exists because this reads
    two different required paths now, and one refusal saying "a provider needs
    an executable" under the entrypoint question sends a person back to check a
    path that was never the problem.
    """
    from conductor.command.adapters.provider import _is_absolute

    while True:
        answer = ask(question).strip().strip('"')
        if not answer:
            if optional:
                return ""
            _say(f"  this provider needs an {noun}; there is no default.")
            continue
        if "\x00" in answer:
            _say("  that is not a path this build can pin.")
            continue
        if not _is_absolute(answer):
            _say("  it must be an ABSOLUTE path — the whole route from the "
                 "root of your disk, not a relative one.")
            continue
        return answer


def _quotable(token: str) -> bool:
    """Whether this token may be repeated back to the person who typed it.

    Only a well-formed environment variable NAME may. Everything else is
    something the dialogue did not ask for, and the one thing somebody in a
    hurry pastes into this question is a credential: a key-shaped token fails
    the name grammar and used to be echoed WHOLE inside its own refusal, which
    put it on the screen, in the scrollback and in any log that captured
    stderr. A refusal has to identify which token it means -- it does that by
    POSITION now, which locates a typo just as well and carries nothing.
    """
    from conductor.command.adapters.deep_contracts import _ENV_NAME

    return _ENV_NAME.fullmatch(token) is not None


def _place(index: int, total: int) -> str:
    """Which token a refusal is about, without saying what it was."""
    return "what you typed" if total == 1 else f"entry {index} of {total}"


def _refuse_name(token: str, index: int, total: int,
                 subscription: bool = False) -> str | None:
    """Why this token is not a name this build will allow, or None if it is.

    Every branch is careful about what it repeats: the head of a `NAME=value`
    is quoted only when the head is itself a name, because `sk-live-x=y` has a
    left half too and it is not one.

    The API-billing refusal is applied HERE, while somebody is choosing the
    name, and not only at the config door: a dialogue that took every answer and
    then refused the finished row would cost a person the whole conversation to
    learn one word, which is the same defect ADR 0007 records about a refused
    name surfacing at the spawn door.
    """
    from conductor.command.adapters.process import injecting_env_reason
    from conductor.command.adapters.provider import API_BILLING_ENV

    where = _place(index, total)
    if "=" in token:
        head = token.split("=", 1)[0]
        shown = repr(head) if _quotable(head) else where
        return (f"{shown} looks like NAME=value. Give the name alone; the "
                "value is read from your environment when a step runs.")
    if not _quotable(token):
        return (f"{where} is not an environment variable name. A name is "
                "letters, digits and underscores, and does not start with a "
                "digit. It is not repeated back here: if that was a credential "
                "VALUE, this question wants the NAME of the variable holding it.")
    reason = injecting_env_reason(token)
    if reason is not None:
        return f"{token!r} may not be allowed: {reason}"
    if subscription and token in API_BILLING_ENV:
        return (f"{token!r} pays for model access through an API account, and "
                "you pinned the subscription login. Passing both would bill the "
                "API account without saying so, so this build refuses the pair.")
    return None


def _ask_env_names(ask: Callable[[str], str],
                   subscription: bool = False) -> list[str]:
    """Read environment variable NAMES, refusing a value and an injector alike.

    A refusal says WHY, because "invalid" sends a person hunting for a typo in
    a line that has no typo in it. What it does not do is quote a token that is
    not a name -- see `_quotable`.
    """
    _say("\n" + _ENV_QUESTION)
    while True:
        answer = ask("> ").strip()
        if not answer:
            return []
        names = answer.replace(",", " ").split()
        refusals = [_refuse_name(name, place, len(names), subscription)
                    for place, name in enumerate(names, 1)]
        stated = next((why for why in refusals if why is not None), None)
        if stated is not None:
            _say(f"  {stated}")
            continue
        if len(set(names)) != len(names):
            _say("  each name once, please.")
            continue
        return names


def _summarise(config, path: Path, existing: Iterable[str]) -> None:
    """Show exactly what will be written, and what the server will make of it."""
    _say(f"\nWriting {path}:")
    _say(f"  provider    {config.provider_id}")
    _say(f"  protocol    {config.protocol}   (chosen by this build, not by you)")
    _say(f"  executable  {config.executable}")
    _say(f"  entrypoint  {config.entrypoint or '(none)'}")
    _say(f"  login       {config.auth}")
    _say(f"  login dir   {config.auth_home or '(none)'}")
    _say(f"  env_allow   {' '.join(config.env_allow) or '(none)'}")
    kept = [name for name in existing if name != config.provider_id]
    if kept:
        _say(f"  keeping     {', '.join(kept)}")
    _say(f"  availability {_availability(config)}")


def _ask_entrypoint(ask: Callable[[str], str], provider_id: str,
                    rule: str) -> str:
    """Ask for the second half of the pin, or do not ask at all.

    The SHAPE comes from `providers.entrypoint_rule`, which is the same rule
    availability is resolved against one layer down. It used to be asked the
    same way of every provider -- "Optional entrypoint … or Enter for none" --
    and both halves of that were wrong for four of the five catalogued rows and
    for the fifth in the other direction:

    - an interpreter-backed provider whose operator pressed Enter was written
      with no entrypoint, reported as written, and resolved `executable_absent`;
    - a single-executable provider whose operator supplied one was written with
      it, reported as written, and resolved `version_mismatch`.

    Neither answer named the question that produced it, and the end-to-end test
    drove only the catalogue's first row -- the one shape where pressing Enter
    happens to be right.
    """
    from conductor.command.providers import (
        ENTRYPOINT_FORBIDDEN, ENTRYPOINT_REQUIRED)

    if rule == ENTRYPOINT_FORBIDDEN:
        # Not asked, because there is no answer this build could honour: this
        # provider IS its executable. A question with one acceptable answer is
        # a way to get it wrong, not a choice.
        _say("\nThis provider is a single executable, so there is no "
             "entrypoint to pin and none is asked for.")
        return ""
    if rule == ENTRYPOINT_REQUIRED:
        _say(f"\n{provider_id} runs through an interpreter: the executable "
             "above is the interpreter, and it needs the absolute path of the "
             "script it runs. Both files must be present for this provider to "
             "be available.")
        return _ask_absolute(
            ask, "Absolute path to the entrypoint it runs: ", optional=False,
            noun="entrypoint")
    return _ask_absolute(
        ask, "Optional entrypoint (absolute path), or Enter for none: ",
        optional=True)


def _quoted(value: str, windows: bool) -> str:
    """One single-quoted literal for the shell this command is running in.

    Printed for a person to paste, so it has to survive the two things a real
    machine path does: a space, which an unquoted argument splits on, and an
    apostrophe, which ends the quoting a naive printer opened. PowerShell
    doubles an apostrophe inside single quotes; a POSIX shell closes, escapes
    and reopens.
    """
    if windows:
        return "'" + value.replace("'", "''") + "'"
    return "'" + value.replace("'", "'\\''") + "'"


def _login_lines(home: str, executable: str, hint,
                 windows: bool | None = None) -> list[str]:
    """The exact two lines a person runs, in the shell they are running in.

    It used to print `NAME=value` and a literal `<executable>`, which is neither
    a PowerShell assignment nor a command: the operator had already told this
    dialogue where the binary is, and was handed a placeholder back.

    Which shell is not a preference. This command runs on the operator's own
    machine, so the platform it is running on IS the answer, and printing the
    other one would repeat the same defect in the other direction.
    """
    windows = os.name == "nt" if windows is None else windows
    if windows:
        return [f"$env:{hint[0]} = {_quoted(home, True)}",
                f"& {_quoted(executable, True)} " + " ".join(hint[1])]
    return [f"export {hint[0]}={_quoted(home, False)}",
            f"{_quoted(executable, False)} " + " ".join(hint[1])]


def _ask_login(ask: Callable[[str], str], provider_id: str, protocol: str,
               executable: str) -> tuple[str, str]:
    """Ask which login this provider uses, or state the only one there is.

    Asked exactly where there is a choice, on the same rule as the entrypoint
    question: `login_hint` names the protocols whose transport really drives a
    vendor login, and it is the same set the config door admits `subscription`
    for. A provider with no such transport is TOLD which login it will use
    rather than offered a menu of one.

    The subscription road asks for a DIRECTORY, never a credential: the vendor's
    own command writes the login there, this build only points the harness at
    it, and the command is printed so a person can run it in their own shell.
    """
    from conductor.command.adapters.provider import (
        DEFAULT_AUTH_MODE, SUBSCRIPTION_AUTH)
    from conductor.command.providers import login_hint

    hint = login_hint(protocol)
    if hint is None:
        _say(f"\nThis build drives no vendor login for {provider_id}, so it "
             "reads its credential from the environment by one of the names "
             "you allow below.")
        return DEFAULT_AUTH_MODE, ""
    _say(f"\nHow does {provider_id} sign in?")
    _say("  1  its own subscription login, kept in a directory you name")
    _say("  2  a credential this build reads from the environment")
    while True:
        answer = ask("> ").strip()
        if answer == "2":
            return DEFAULT_AUTH_MODE, ""
        if answer == "1":
            break
        _say("  type 1 or 2.")
    home = _ask_absolute(
        ask, "Absolute path of the directory to keep that login in: ",
        optional=False, noun="login directory")
    _say("\n  Sign in yourself, once, in your own shell -- this build never "
         "runs a login. Paste these two lines:")
    for line in _login_lines(home, executable, hint):
        _say(f"    {line}")
    return SUBSCRIPTION_AUTH, home


def _collect(ask: Callable[[str], str]):
    """Ask the questions this provider's pin shape needs, and build the config."""
    from conductor.command.adapters.provider import (
        SUBSCRIPTION_AUTH, ProviderConfig, ProviderConfigError)
    from conductor.command.providers import entrypoint_rule

    provider_id, protocol, display = _choose_provider(ask)
    _say(f"\n{display}")
    executable = _ask_absolute(
        ask, f"Absolute path to the {provider_id} executable: ", optional=False)
    entrypoint = _ask_entrypoint(ask, provider_id, entrypoint_rule(protocol))
    auth, auth_home = _ask_login(ask, provider_id, protocol, executable)
    env_allow = _ask_env_names(ask, auth == SUBSCRIPTION_AUTH)
    try:
        return ProviderConfig(
            provider_id=provider_id, executable=executable, protocol=protocol,
            entrypoint=entrypoint, env_allow=env_allow, auth=auth,
            auth_home=auth_home)
    except ProviderConfigError as error:
        raise SetupError(f"this build refuses that provider: {error}") from None


def _availability(config) -> str:
    """What the SERVER will call this pin, asked of the server's own resolver.

    Not re-derived here. A second opinion about availability is a second way to
    be wrong, and the whole defect this closes was two surfaces holding
    different ideas of the same rule.
    """
    from conductor.command.providers import availability_of

    return availability_of(config)


def _warn_if_absent(config) -> None:
    """Say which pinned file is not there, when that is what stands between
    this config and an available provider.

    Not a refusal: the durable contract requires an absolute path, not a present
    one, and refusing here would stop somebody configuring a harness they are
    about to install. What it must not do is stay quiet and let them discover it
    from a screen that says `executable_absent` with no idea why.

    The SHAPE of the pin is settled before this by `_ask_entrypoint`, so a
    missing file is the only thing left that can hold a finished dialogue back.
    """
    if _availability(config) == "available":
        return
    absent = [pin for pin in (config.executable, config.entrypoint)
              if pin and not Path(pin).exists()]
    for pin in absent:
        _say(f"\nnote: {pin} is not on this machine yet. The file will be "
             "written; the Agents screen will show this provider as "
             "unavailable until that path exists.")


def _open_the_file(directory: str):
    """The path this writes, and what already stands in it -- or None to refuse.

    A file this build cannot read is REFUSED rather than started from empty.
    Those rows are somebody's configuration; a flow that quietly began with an
    empty list would delete every provider in it, and they would find out when
    a run refused rather than now, while they can still fix the file.
    """
    try:
        conductor_dir = store.conductor_dir(directory)
    except store.StoreError as error:
        _say(str(error))
        return None
    from conductor.command import operator_config

    path = operator_config.provider_config_path(conductor_dir)
    try:
        return path, operator_config.load_provider_configs(path)
    except operator_config.OperatorConfigError as error:
        _say(str(error))
        _say("fix or remove that file before configuring another provider; "
             "this command will not overwrite what it cannot read.")
        return None


#: What an input that STOPS is told, in the product's own words.
#:
#: Python's phrase for it is "EOF when reading a line", and that sentence used
#: to reach the screen of somebody who had done nothing wrong: a pipe closed, a
#: Ctrl+Z, a command run where there is nothing to type into.
#: `docs/owner-acceptance.md` asks that every failure be understandable without
#: opening a terminal log, and the name of an exception is the opposite of that.
_ENDED = "the input ended before"


def _collected(ask: Callable[[str], str]):
    """The four answers, or None with the reason already said."""
    try:
        return _collect(ask)
    except EOFError:
        _say(f"\n{_ENDED} the questions did, so nothing was written. Run this "
             "again in a terminal you can type into.")
    except SetupError as error:
        _say(f"\n{error or 'nothing was written'}")
    return None


def _confirmed(ask: Callable[[str], str]) -> bool:
    """The last question is a real question, and it may also go unanswered."""
    try:
        answer = ask("\nWrite it? [y/N]: ")
    except EOFError:
        _say(f"\n{_ENDED} the last question, so nothing was written.")
        return False
    if answer.strip().lower() in {"y", "yes"}:
        return True
    _say("nothing was written.")
    return False


def run(args: argparse.Namespace, ask: Callable[[str], str] | None = None) -> int:
    """Configure one provider interactively and write the operator's file.

    Args:
        args: The parsed `providers` namespace; `--dir` names the project.
        ask: The prompting function. Tests inject a scripted one; a terminal
            gets `_console_ask`. A non-terminal with no injected prompter is
            refused rather than defaulted, because every answer here is a fact
            about one machine and there is no honest default for any of them.

    Returns:
        0 when the file was written, 1 for every refusal.
    """
    if ask is None:
        if not _interactive():
            _say("conduct providers needs a terminal: every answer is a fact "
                 "about this machine and none of them has a default.")
            return 1
        ask = _console_ask
    opened = _open_the_file(args.dir)
    if opened is None:
        return 1
    path, standing = opened
    _say(_PREAMBLE)
    _say(f"\nConfigured now: "
         f"{', '.join(row.provider_id for row in standing) or '(none)'}")
    config = _collected(ask)
    if config is None:
        return 1
    _warn_if_absent(config)
    _summarise(config, path, [row.provider_id for row in standing])
    if not _confirmed(ask):
        return 1
    return _write(path, standing, config, project_root=args.dir)


def _write(path, standing, config, *, project_root=None) -> int:
    """Put the new row beside the ones already there, and say what happens next.

    Replace by identity rather than append: configuring a provider twice is
    CORRECTING it, and a second row under one id is a document the reader
    refuses -- which would leave a person unable to start a project they were
    just told was configured.
    """
    from conductor.command import operator_config

    kept = [row for row in standing if row.provider_id != config.provider_id]
    try:
        operator_config.save_provider_configs(path, [*kept, config], project_root=project_root)
    except operator_config.OperatorConfigError as error:
        _say(str(error))
        return 1
    _say(f"\nwrote {path}")
    _say("providers are read once at startup, so restart `conduct up` for this "
         "to take effect.")
    return 0
