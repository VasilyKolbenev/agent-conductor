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
    ("the Grok diagnostic reported an opened session before the error",
     "the Grok diagnostic reported an opened session before the error"),
    ("the Grok diagnostic reported no session ID before the error",
     "the Grok diagnostic reported no session ID before the error"),
    ("the Grok diagnostic stream did not establish a result",
     "the Grok diagnostic stream did not establish a result"),
    ("wrote past the capture bound", "its output was longer than the capture bound"),
    ("exceeded its timeout", "it exceeded its timeout"),
    ("subscription login check timed out", "the subscription login check timed out before dispatch"),
    ("was never handed its whole instruction", "its instruction was not delivered whole"),
    ("left state this build does not declare in the login",
     "it left undeclared state in the pinned login directory"),
    ("was observed to exit non-zero", "the process exited non-zero"),
    ("the harness reported that sign-in is required", "the harness reported that sign-in is required"),
    ("the harness reported a session startup failure", "the harness reported a session startup failure"),
    ("the harness reported an embedded agent startup failure",
     "the harness reported an embedded agent startup failure"),
    ("the harness reported an agent initialization failure",
     "the harness reported an agent initialization failure"),
    ("the harness reported a task session opening failure", "the harness reported a task session opening failure"),
    ("the harness reported a subscription usage limit", "the harness reported a subscription usage limit"),
    ("the harness reported that a subscription is required for this task",
     "the harness reported that a subscription is required for this task"),
    ("the harness reported that the requested model is unavailable",
     "the harness reported that the requested model is unavailable"),
    ("the harness reported an access refusal", "the harness reported an access refusal"),
    ("the harness reported a connection failure", "the harness reported a connection failure"),
    ("the harness reported that its local prompt channel closed",
     "the harness reported that its local prompt channel closed"),
    ("the harness reported that the turn limit was reached",
     "the harness reported that the turn limit was reached"),
    ("service error with recorded token usage",
     "the harness reported an unclassified service error with recorded token usage"),
    ("service error with incomplete usage data",
     "the harness reported an unclassified service error with incomplete usage data"),
    ("the harness reported an unclassified service error", "the harness reported an unclassified service error"),
    ("the review contained sensitive output", "the review contained sensitive output"),
    ("the review returned an invalid terminal response",
     "the review returned an invalid terminal response"),
    # A relay attempt refused before its claim, one row per closed code (`adapters/relay_attempt`,
    # `adapters/login_relay.REFUSALS`): the fragment is the phrase the sentence says it in. They
    # stand after the two rows of what a child did, so a sentence about a run is read first.
    ("the login holds no credential file this build can copy",
     "the pinned login has no credential file to copy"),
    ("the credential file is not an ordinary file with a single name",
     "the pinned login's credential file is not an ordinary file"),
    ("the credential file is larger than a credential file is",
     "the pinned login's credential file is too large"),
    ("the credential file is not one JSON object in UTF-8",
     "the pinned login's credential file is damaged"),
    ("the credential file holds credentials this build does not copy",
     "the pinned login holds credentials this build does not copy"),
    ("the credential file is not in a shape this build was reviewed against",
     "the pinned login's credential file is in a shape this build does not know"),
    ("the credential file holds no access token", "the pinned login holds no access token"),
    ("the login holds an API key, which is not a subscription",
     "the pinned login holds an API key, which is not a subscription"),
    ("the login does not say which plan it is on",
     "the pinned login does not say which plan it is on"),
    ("the login is on the API-billing plan, which is not a subscription",
     "the pinned login is on the API-billing plan"),
    ("the account of the login could not be established",
     "the account of the pinned login could not be established"),
    ("the vendor would keep the refreshed login in the Windows credential manager",
     "the pinned login would be kept in the Windows credential manager"),
    ("whether the vendor uses the Windows credential manager is not known",
     "it is not known whether the pinned login is kept in the Windows credential manager"),
    ("when the access token expires could not be established",
     "when the pinned login expires is not known; sign in again"),
    ("the access token expires before the attempt would end",
     "the pinned login expires before the attempt would end; sign in again"),
    ("the credential file changed after it was checked",
     "the pinned login changed while the attempt was prepared"),
    ("the copy would carry a refresh token",
     "the copy of the pinned login would carry a refresh token"),
    ("the attempt home is not a folder this build can copy into",
     "the attempt's relay home could not be used"),
    ("the attempt home is not empty", "the attempt's relay home was not empty"),
    ("the credential could not be written into the attempt home",
     "the login could not be copied into the attempt's relay home"),
    ("the relay folder of the login is not usable",
     "the relay folder of the pinned login is not usable"),
    ("a folder of the login or of its relay is open to an isolated child",
     "a folder of the pinned login or of its relay is open to an isolated child"),
    ("the environment of the attempt carries a name that replaces the login or "
     "reroutes its traffic",
     "the environment of the attempt replaces the pinned login or reroutes its traffic"),
    ("the login was not proved ready for this attempt",
     "the pinned login was not proved ready for the attempt"),
    ("the login lease of the attempt does not name this login",
     "the login lease of the attempt does not name the pinned login"),
    ("the relay home of the attempt could not be made",
     "the attempt's relay home could not be made"),
    ("the command of the attempt could not be built for its relay home",
     "the attempt's command could not be built"),
    ("the execution boundary refused the relay home of the attempt",
     "the execution boundary refused the attempt's relay home"),
    ("the action could not be claimed for the attempt",
     "the action could not be claimed for the attempt"),
    ("the claim of the action could not be completed but its marker stands, and a repeat of the "
     "action is unknown", "the claim of the action could not be completed and its marker stands"),
    ("was stopped by the runner", "it was stopped"),
    ("reports no subscription", "the pinned login is not an admitted subscription"),
    ("which is not supported inside the execution boundary for this harness yet",
     "a subscription login for this harness is not supported inside the execution boundary yet"),
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


def lease_words(sentence: object, refused: str = _LEASE_REFUSED) -> str | None:
    """The words for a lease refusal a transport wrote, from the closed lists only.

    Args:
        sentence: What a transport wrote (`adapters/login_refusal.sentence`), or anything else.
        refused: The runtime's own opening words, which say whose lease it was.

    Returns:
        ``refused``, then the words of the closed code and of the closed reader code under it.
        Never text taken from ``sentence``: an id outside the two lists is dropped. None when the
        text is not the sentence of a refused lease.
    """
    found = _LEASE_SENTENCE.search(sentence) if type(sentence) is str else None
    if found is None:
        return None
    code, reader = found["code"], found["reader"]
    if code not in LEASE_WORDS:
        return refused
    named = code if reader not in READER_WORDS else f"{code}, {reader}: {READER_WORDS[reader]}"
    return f"{refused}: {LEASE_WORDS[code]} ({named})"


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
    return found if found is not None else lease_words(sentence)
