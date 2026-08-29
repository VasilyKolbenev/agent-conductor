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
    "no argv, no working directory and no URL.")
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
                  optional: bool) -> str:
    """Read one absolute path, re-asking until it is one.

    Judged by the same predicate the durable contract uses, imported rather than
    reimplemented: a wizard with its own idea of "absolute" would accept a path
    the config then refuses, after the person had been told it was saved.
    """
    from conductor.command.adapters.provider import _is_absolute

    while True:
        answer = ask(question).strip().strip('"')
        if not answer:
            if optional:
                return ""
            _say("  a provider needs an executable; there is no default.")
            continue
        if "\x00" in answer:
            _say("  that is not a path this build can pin.")
            continue
        if not _is_absolute(answer):
            _say("  it must be an ABSOLUTE path — the whole route from the "
                 "root of your disk, not a relative one.")
            continue
        return answer


def _ask_env_names(ask: Callable[[str], str]) -> list[str]:
    """Read environment variable NAMES, refusing a value and an injector alike.

    Both refusals name the offending token and say WHY, because "invalid" sends
    a person hunting for a typo in a line that has no typo in it.
    """
    from conductor.command.adapters.process import injecting_env_reason
    from conductor.command.adapters.deep_contracts import _ENV_NAME

    _say("\n" + _ENV_QUESTION)
    while True:
        answer = ask("> ").strip()
        if not answer:
            return []
        names = answer.replace(",", " ").split()
        refused = False
        for name in names:
            if "=" in name:
                _say(f"  {name.split('=')[0]!r} looks like NAME=value. Give the "
                     "name alone; the value is read from your environment.")
                refused = True
                break
            if _ENV_NAME.fullmatch(name) is None:
                _say(f"  {name!r} is not an environment variable name. A name "
                     "is letters, digits and underscores, and does not start "
                     "with a digit.")
                refused = True
                break
            reason = injecting_env_reason(name)
            if reason is not None:
                _say(f"  {name!r} may not be allowed: {reason}")
                refused = True
                break
        if refused:
            continue
        if len(set(names)) != len(names):
            _say("  each name once, please.")
            continue
        return names


def _summarise(config, path: Path, existing: Iterable[str]) -> None:
    """Show exactly what will be written, before anything is."""
    _say(f"\nWriting {path}:")
    _say(f"  provider    {config.provider_id}")
    _say(f"  protocol    {config.protocol}   (chosen by this build, not by you)")
    _say(f"  executable  {config.executable}")
    _say(f"  entrypoint  {config.entrypoint or '(none)'}")
    _say(f"  env_allow   {' '.join(config.env_allow) or '(none)'}")
    kept = [name for name in existing if name != config.provider_id]
    if kept:
        _say(f"  keeping     {', '.join(kept)}")


def _collect(ask: Callable[[str], str]):
    """Ask the four questions and build the config they describe."""
    from conductor.command.adapters.provider import (
        ProviderConfig, ProviderConfigError)

    provider_id, protocol, display = _choose_provider(ask)
    _say(f"\n{display}")
    executable = _ask_absolute(
        ask, f"Absolute path to the {provider_id} executable: ", optional=False)
    entrypoint = _ask_absolute(
        ask, "Optional entrypoint (absolute path), or Enter for none: ",
        optional=True)
    env_allow = _ask_env_names(ask)
    try:
        return ProviderConfig(
            provider_id=provider_id, executable=executable, protocol=protocol,
            entrypoint=entrypoint, env_allow=env_allow)
    except ProviderConfigError as error:
        raise SetupError(f"this build refuses that provider: {error}") from None


def _warn_if_absent(config) -> None:
    """Say what will happen if the pinned executable is not there.

    Not a refusal: the durable contract requires an absolute path, not a present
    one, and refusing here would stop somebody configuring a harness they are
    about to install. What it must not do is stay quiet and let them discover it
    from a screen that says `executable_absent` with no idea why.
    """
    if not Path(config.executable).exists():
        _say(f"\nnote: {config.executable} is not on this machine yet. The file "
             "will be written; the Agents screen will show this provider as "
             "unavailable until the path exists.")


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
    try:
        config = _collect(ask)
    except (SetupError, EOFError) as error:
        _say(f"\n{error or 'nothing was written'}")
        return 1
    _warn_if_absent(config)
    _summarise(config, path, [row.provider_id for row in standing])
    if ask("\nWrite it? [y/N]: ").strip().lower() not in {"y", "yes"}:
        _say("nothing was written.")
        return 1
    return _write(path, standing, config)


def _write(path, standing, config) -> int:
    """Put the new row beside the ones already there, and say what happens next.

    Replace by identity rather than append: configuring a provider twice is
    CORRECTING it, and a second row under one id is a document the reader
    refuses -- which would leave a person unable to start a project they were
    just told was configured.
    """
    from conductor.command import operator_config

    kept = [row for row in standing if row.provider_id != config.provider_id]
    try:
        operator_config.save_provider_configs(path, [*kept, config])
    except operator_config.OperatorConfigError as error:
        _say(str(error))
        return 1
    _say(f"\nwrote {path}")
    _say("providers are read once at startup, so restart `conduct up` for this "
         "to take effect.")
    return 0
