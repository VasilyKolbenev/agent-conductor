"""Value-only helpers shared by the provider-neutral headless transport."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .harness_profile import HeadlessCliError


def flagless(
        token: str, what: str, launcher_noun: str,
        error: type[HeadlessCliError]) -> str:
    """Prove one argv token cannot be read by a launcher as its own flag.

    A launcher parses the flags it owns and treats an unrecognized token as the
    start of what it passes through. A token that begins with ``-`` is therefore
    the whole injection surface: a flag in a task position would be consumed by
    the launcher rather than passed through as text. Contract identifiers cannot
    begin with ``-`` by their own grammar; this proves it at the argv boundary
    anyway, because that is where the consequence lives.
    """
    if type(token) is not str or not token.strip():
        raise error(f"{what} must be a non-empty task token")
    if "\x00" in token:
        raise error(f"{what} must not contain NUL")
    if token.startswith("-"):
        raise error(
            f"{what} would be read by the {launcher_noun} as one of its own flags")
    return token


def changed_paths(
        before: Mapping[str, str], after: Mapping[str, str]) -> tuple[str, ...]:
    """Every path whose content appeared, vanished, or moved between snapshots."""
    return tuple(sorted(
        name for name in set(before) | set(after)
        if before.get(name) != after.get(name)))


def version_token(output: bytes) -> str:
    """The first non-empty line of a version print, as an exact token.

    The bytes are the child's raw output, so nothing derived from them is ever
    returned to a caller: this token is only ever COMPARED against the reviewed
    constant, and the comparison's answer is a boolean.
    """
    text = output.decode("utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


@dataclass(frozen=True)
class _Attempt:
    """The evidence PAIR one execute read, so verify judges values, not the tree.

    Both snapshots are taken inside the workspace turn, around the spawn. That is
    the whole reason ``after`` is carried here instead of being re-read later: the
    turn is the only window in which the shared work tree is this dispatch's
    alone, and a verification that re-read the tree afterwards would be judging a
    tree a neighbouring provider may have changed in the meantime. What is judged
    must be what was read.

    ``after`` is None when the tree could not be read on a contained route at
    all. That is told apart from an empty reading, because "nothing changed" and
    "the route refused" are different answers.
    """

    work_dir: Path
    before: Mapping[str, str]
    after: Mapping[str, str] | None


#: What ``_attempt`` is handed to build the child's OWN tokens with. A provider
#: on the ``argv`` channel knows every token before anything is minted and hands
#: a ready tuple, exactly as it always did; one on the ``stdin`` channel may not,
#: because a vendor asked to write into the profile home this build mints needs
#: that path on its command line and the home does not exist yet. So that channel
#: hands a BUILDER, called once, with the minted home and nothing else.
ArgvSource = tuple[str, ...] | Callable[[Path], tuple[str, ...]]


# Publicly descriptive aliases; the private names remain byte-compatible for
# existing providers and tests importing them through ``headless_cli``.
AttemptEvidence = _Attempt
_changed = changed_paths
_version_token = version_token
