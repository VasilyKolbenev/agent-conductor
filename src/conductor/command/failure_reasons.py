"""The runtime's OWN words for why a step failed, recognized in a built-in adapter's sentence.

The runtime never forwards adapter prose. A receipt's detail is a second line of defence
against a leak (``tests/test_command_*_leak_surfaces.py``): a hostile or broken build can put
anything where a sentence belongs -- a version it printed, a value it echoed. The first live
runs (23.09.2026) showed the price of saying nothing at all: a failed step read "adapter
reported failed", and nobody could tell a truncated review from a login residue.

So the runtime RECOGNIZES the fixed fragments this build's own transports write and answers
with a phrase from the table below. Nothing an adapter wrote is copied; a sentence carrying
none of the fragments earns no phrase; a sentence that carries one only earns the runtime's
own words for it. ``tests/test_failure_reasons.py`` holds every fragment to the transport
source that writes it, so a reworded sentence cannot quietly fall out of the table.
"""
from __future__ import annotations

import re

#: (fragment a built-in transport writes, the runtime's own words for it). First match wins.
REASONS = (
    ("wrote past the capture bound", "its output was longer than the capture bound"),
    ("exceeded its timeout", "it exceeded its timeout"),
    ("was never handed its whole instruction", "its instruction was not delivered whole"),
    ("left state this build does not declare in the login",
     "it left undeclared state in the pinned login directory"),
    ("was observed to exit non-zero", "the process exited non-zero"),
    ("was stopped by the runner", "it was stopped"),
    ("reports no subscription", "the pinned login is not an admitted subscription"),
    ("version preflight, so no task was spawned", "the version preflight failed"),
    ("is not the reviewed", "the installed build is not the reviewed version"),
    ("exceeds the bounded task channel", "its task was larger than the bounded task channel"),
)

#: The runtime's words for the code of a refused shared-login lease (`adapters/login_refusal.py`).
#: A transport hands over a CODE, never the owner's sentence, which names state of the operator's
#: machine; `tests/test_login_lease_refusal_words.py` holds each code to the owner source that
#: raises it.
LEASE_WORDS = {
    "ownership_unavailable": "the OS boot counter or the ownership state cannot be read",
    "login_recovery_required": "the shared login has a lease that was not closed",
    "login_owner_busy": "the shared login is already held by another lease of this process",
    "login_ownership_invalid": "the record of the shared login lease is not valid",
    "login_context_required": "the shared login directory is not an absolute configured path",
    "recovery_required": "the project's owner session needs recovery",
    "owner_required": "the project has no live owner",
    "ownership_lost": "the project's ownership changed under the run",
    "transition_conflict": "the ownership state is not in a form this build accepts",
}
#: The runtime's words for the reason the boot reader gave under `ownership_unavailable`.
READER_WORDS = {
    "native_unavailable": "the OS call that reads it failed",
    "layout_unknown": "the OS page is not the documented layout",
    "partial_read": "the OS page was read only in part",
    "value_empty": "the OS counter is empty",
    "counter_overflow": "the OS counter is saturated",
    "unsupported_platform": "this platform has no reader for it",
}
#: What a transport writes when its login guard refused at the entry: two ids and nothing else.
_LEASE_SENTENCE = re.compile(
    r"the shared login lease was refused \((?P<code>[a-z_]+)(?:: (?P<reader>[a-z_]+))?\), "
    r"so no task was spawned")
_LEASE_REFUSED = "the shared login lease was refused"


def _lease_words(sentence: str) -> str | None:
    """The words for a lease refusal a transport wrote, from the closed lists only."""
    found = _LEASE_SENTENCE.search(sentence)
    if found is None:
        return None
    code, reader = found["code"], found["reader"]
    if code not in LEASE_WORDS:
        return _LEASE_REFUSED
    named = code if reader not in READER_WORDS else f"{code}, {reader}: {READER_WORDS[reader]}"
    return f"{_LEASE_REFUSED}: {LEASE_WORDS[code]} ({named})"


def reason_words(sentence: object) -> str | None:
    """The runtime's own words for a recognized built-in sentence, or None.

    Args:
        sentence: A built-in adapter's receipt detail, or anything else.

    Returns:
        A phrase from ``REASONS``, or the words of a refused login lease built from the two
        closed lists above -- never text taken from ``sentence`` -- or None.
    """
    if type(sentence) is not str:
        return None
    found = next((words for fragment, words in REASONS if fragment in sentence), None)
    return found if found is not None else _lease_words(sentence)
