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


def reason_words(sentence: object) -> str | None:
    """The runtime's own words for a recognized built-in sentence, or None.

    Args:
        sentence: A built-in adapter's receipt detail, or anything else.

    Returns:
        A phrase from ``REASONS`` -- never text taken from ``sentence`` -- or None.
    """
    if type(sentence) is not str:
        return None
    return next((words for fragment, words in REASONS if fragment in sentence), None)
