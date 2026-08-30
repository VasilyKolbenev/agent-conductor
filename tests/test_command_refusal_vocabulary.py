"""Every refusal the server can send is one a window can read out loud.

The two halves of a refusal live in two languages: `api_contracts.ERROR_STATUS`
says which codes exist, and `command-projection.js`'s `ERROR_LABELS` says what a
person is shown for each. Nothing held them together, and the failure mode is
quiet in the worst way -- `said()` falls back to `ERROR_LABELS.store_error`, so
a code with no label is not blank or broken. It renders as "The run store is
unavailable.", which is a sentence about a different thing that is not true.

That is a class, not an instance. Adding `draft_changed` is what made it worth
closing, but the guard is written about the vocabulary rather than about that
one word, so the next code added on either side has to be added on both.

The direction is deliberately asymmetric. Every server code MUST have a label,
because the server can send any of them. A label with no server code is allowed
to exist for one release -- a client is entitled to know a word before the build
it talks to sends it -- so that side is reported rather than refused.
"""
from __future__ import annotations

import re
from pathlib import Path

from conductor.command.api_contracts import ERROR_STATUS, _FIXED_MESSAGES

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
PROJECTION = PANEL / "command-projection.js"


def labelled() -> set[str]:
    """Every code `ERROR_LABELS` gives a person a sentence for.

    Read out of the source rather than imported, because there is no importing
    it: the table is JavaScript. The regex is anchored on the two-space indent
    of an object literal member so a code named in a comment or in prose cannot
    be counted as a label.
    """
    source = PROJECTION.read_text(encoding="utf-8")
    body = re.search(r"export const ERROR_LABELS = Object\.freeze\(\{(.*?)\n\}\);",
                     source, re.DOTALL)
    assert body, "command-projection.js no longer declares ERROR_LABELS"
    return set(re.findall(r"^  ([a-z_]+):", body.group(1), re.MULTILINE))


def test_every_refusal_code_the_server_can_send_has_a_sentence_for_a_person():
    """The fallback is a lie when it fires, so it must never fire."""
    missing = sorted(set(ERROR_STATUS) - labelled())

    assert not missing, (
        "these refusal codes render as 'The run store is unavailable.' because "
        f"command-projection.js has no label for them: {missing}")


def test_the_window_names_no_refusal_this_build_cannot_send():
    """The other direction, reported rather than refused.

    A label for a code no build sends is dead copy, not a defect: it misleads
    nobody because it can never appear. It is still worth seeing, because the
    usual cause is a code that was renamed on one side only.
    """
    unknown = sorted(labelled() - set(ERROR_STATUS))

    assert not unknown, (
        "command-projection.js labels refusal codes this build never sends; "
        f"a rename on one side only looks exactly like this: {unknown}")


def test_every_code_carries_a_fixed_message_and_a_status():
    """The server's own two tables, held to each other.

    `ApiRefusal.fixed` reads `_FIXED_MESSAGES` and the constructor reads
    `ERROR_STATUS`; a code in one and not the other is a refusal that raises
    `ValueError` from inside the error path, which is the worst place to find
    out.
    """
    assert set(_FIXED_MESSAGES) == set(ERROR_STATUS)
    for code, status in ERROR_STATUS.items():
        assert 400 <= status <= 599, (code, status)
        assert _FIXED_MESSAGES[code].strip(), code


def test_draft_changed_is_a_conflict_and_says_what_to_do_about_it():
    """The code this guard was written for, pinned where it is decided.

    A 4xx that is not 409 would tell a client the request was malformed; the
    request was correct and the world moved. The sentence has to carry an
    action, because "conflict" alone leaves a person pressing Confirm again.
    """
    assert ERROR_STATUS["draft_changed"] == 409
    assert "read it again" in _FIXED_MESSAGES["draft_changed"]


def test_draft_conflict_is_its_own_conflict_and_never_blames_the_request():
    """The sibling code, pinned where it is decided.

    Both arms it answers used to be something else, and both were wrong in the
    same way. A save that found another window's draft standing overwrote it
    silently -- no refusal at all. A publish whose reviewed draft had been
    consumed answered `contract_invalid`, telling a window its REQUEST SHAPE was
    invalid for a confirm that was perfectly well formed. It is 409 because the
    request was right and the world moved, and it is not `draft_changed`
    because that names a draft that is still stored and says something else.
    """
    assert ERROR_STATUS["draft_conflict"] == 409
    assert ERROR_STATUS["draft_conflict"] != ERROR_STATUS["contract_invalid"]
    assert "not the one this request" in _FIXED_MESSAGES["draft_conflict"]
    assert _FIXED_MESSAGES["draft_conflict"] != _FIXED_MESSAGES["draft_changed"]


def test_both_draft_conflict_roads_are_reviewed_facts_naming_no_digest():
    """The two reviewed rows, built through the factories that own them.

    A reviewed fact is rendered into a browser, so what may appear in one is
    argued for a field at a time. These two carry ids the caller already
    supplied and nothing else -- in particular never the standing draft's
    digest, which is a fact about somebody else's document.
    """
    from conductor.command.api_contracts import ApiRefusal

    save = ApiRefusal.conflicting_draft("release-check")
    publish = ApiRefusal.unpublishable_draft("release-check", 2)

    assert save.code == publish.code == "draft_conflict"
    assert save.status == publish.status == 409
    assert dict(save.detail) == {"workflow_id": "release-check"}
    assert dict(publish.detail) == {"workflow_id": "release-check", "revision": 2}
    for refusal in (save, publish):
        assert "sha256" not in refusal.message
        assert set(refusal.as_dict()["error"]) == {"code", "message", "detail"}
    # The two are told apart by their field sets, so neither may answer with
    # the other's sentence -- which is what a single row would have allowed.
    assert save.message != publish.message
