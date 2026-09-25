"""What the Decisions screen OFFERS, and what it says where it offers nothing.

One circuit, split out of ``test_studio_runs.py`` when that module crossed the
project's line cap, and along a seam of its own: everything here is about the
question *may this gate be answered right now*, which the screen must answer
the same way the write door does.

The rule the server holds is that a decision is admitted for a gate its
schedule says the run has arrived at, or as a supersede of the receipt already
standing on it. So this screen offers its form on exactly that word, and where
it offers nothing it says WHICH of the two situations a person is in -- a gate
still waiting for the steps in front of it, or a gate no run will ever reach.
A form offered anywhere else is a control whose only possible outcome is a
refusal, which is the thing this screen exists not to do.

Named ``test_studio_*`` for the reason its parent module is: ``test_panel_
smoke.py`` machine-checks that ``index.html``'s file-size waiver names, as a
pattern, exactly the set of ``test_panel_*.py`` modules in the tree, so a new
module under that prefix would red a file this slice does not own.

Source guards, like the module they came from: what is asserted is that the
window ASKS the right layer. The rendered halves are in
``browser_tests/test_studio_decision_doors.py``.
"""
from __future__ import annotations

import re
import json

from tests.test_studio_runs import PANEL, PEOPLE_FILE, WORDS_FILE, source

RUNREAD_FILE = PANEL / "studio-runread.js"


def _copy(key):
    text = (PANEL / "studio-agents-copy.js").read_text(encoding="utf-8")
    catalog = json.loads(text.split("Object.freeze(", 1)[1].rsplit(");", 1)[0])
    return catalog["agents." + key][0]



def _decision_rows() -> str:
    """The body of the loop that builds one row per gate of the plan."""
    return re.search(
        r"for \(const node of rows\(definition\.nodes\)(.*?)\n  \}",
        RUNREAD_FILE.read_text(encoding="utf-8"), re.DOTALL).group(1)


#: The offer rule, EXACTLY. Pinned as a whole expression rather than as
#: substrings: a widened rule -- offering a form on a blocked gate whose
#: `closed_by` happens to be empty -- keeps every substring a looser guard
#: would look for while admitting the answers the door refuses. So what is
#: asserted is the body, whitespace-normalized and nothing else.
#:
#: The word the screen gates on is the SERVER's: `answerable` on the gate's
#: schedule row is the decision door's own verdict, served on the read. The
#: screen used to spell the door's arms for itself -- "a receipt stands, so it
#: may be replaced" -- and offered a supersede on a gate whose lap-one answer
#: stood while the loop had already begun a second lap the plan had not carried
#: to that gate; the door refused every one of those (R02 of the review of
#: `8dec0e4`). A rule that lives in one place cannot drift from itself.
OFFER_RULE = (
    'return row.ended !== true && row.decision !== "unknown" '
    '&& (row.answerable === "first" || row.answerable === "supersede");')
#: The server's own reading of ARRIVED, still carried for the sentences that
#: explain a halted run, and beside it the door's verdict, carried verbatim.
REACHABLE_RULE = (
    'reachable: state !== null && state !== "settled" '
    "&& blocked.length === 0 && closed.length === 0,")
ANSWERABLE_RULE = (
    'answerable: planned !== null && typeof planned.answerable === "string" '
    "? planned.answerable : null,")


def _body(text: str, signature: str) -> str:
    found = re.search(rf"function {re.escape(signature)} \{{(.*?)\n\}}",
                      text, re.DOTALL)
    assert found is not None, f"no function {signature}"
    return " ".join(found.group(1).split())


def _sentences(text: str, signature: str) -> str:
    """The same body with adjacent string literals joined back together.

    A sentence written across a line break is one sentence to a reader and two
    literals to a regex, so the concatenation is undone before it is read --
    otherwise a guard would be asserting where the author happened to wrap.
    """
    return _body(text, signature).replace('" + "', "")


def test_the_decisions_screen_offers_an_answer_only_where_the_plan_admits_one():
    """The offer rule is the write door's rule, spelled the same way.

    Three facts and no fourth. A gate whose recorded answers contradict is
    offered nothing; a gate a receipt STANDS on may be answered by replacing
    it, reached or not; a gate nothing stands on may be answered once the plan
    has reached it. That is the server's predicate, arm for arm.

    Both halves are held because they fail apart: the row must CARRY the plan's
    reading out of the run read, and the screen must GATE the form on it.
    """
    carried = _decision_rows()
    assert "...planWords(planned, answered)," in carried, carried
    read = RUNREAD_FILE.read_text(encoding="utf-8")
    words = " ".join(_body(read, "planWords(planned, answered)").split())
    assert REACHABLE_RULE in words, read
    assert ANSWERABLE_RULE in words, read

    people = source(PEOPLE_FILE)
    assert _body(people, "offersAnAnswer(row)") == OFFER_RULE, _body(
        people, "offersAnAnswer(row)")
    # And it is what the detail actually branches on.
    assert "if (offersAnAnswer(row)) {" in people, people


def test_the_offer_rule_never_reads_the_word_the_halt_takes_away():
    """`runnable` is not this question's word, and may not creep back in.

    A halt rewrites every runnable row to `blocked` so that nothing further is
    offered as WORK. A decision is not work -- so a screen reading `runnable`
    explained a gate whose roads were all open by saying its roads had not
    opened, and went on saying "cannot be answered yet" about a run that had
    already stopped.
    """
    people = source(PEOPLE_FILE)

    assert "runnable" not in _body(people, "offersAnAnswer(row)")
    assert "runnable" not in " ".join(
        _body(RUNREAD_FILE.read_text(encoding="utf-8"),
              "planWords(planned, answered)").split())


def test_a_gate_that_cannot_be_answered_yet_says_which_of_the_two_it_is():
    """Blocked and unreachable are nothing alike, so they are two sentences.

    One ends when the steps in front of it finish and the other never ends at
    all; a person told the wrong one either waits for something that will never
    happen or goes looking for a step that does not exist. The AND-join clause
    is the Runs screen's own constant rather than a second copy, because one
    rule said twice in two files is one rule that can be said two ways.
    """
    # The keys reached, as written: this guard is about WHICH catalogue rows a reason names.
    people = PEOPLE_FILE.read_text(encoding="utf-8")
    sentence = re.search(r'ALL_ROADS = "(.+?)";', source(WORDS_FILE), re.DOTALL)
    assert sentence is not None, "the AND-join sentence has no one owner"
    assert "ALL incoming roads must open" in sentence.group(1).replace(
        '"\n  + "', "")

    why = _sentences(people, "whyNotYet(row, state)")
    expected = {
        "waiting": "Waiting on: {waiting}", "closed": "road into it was closed",
        "unreachable": "unreachable too", "ended": "no decision can be recorded",
        "contradiction": "recorded answers contradict each other",
        "halted": "Nothing further is offered in this run: it was halted.",
        "schedule_missing": "cannot say whether the plan has reached this gate",
    }
    for key, phrase in expected.items():
        assert f'"agents.{key}"' in why
        assert phrase in _copy(key)
    # The translated clause preserves the existing AND-join owner's exact EN.
    assert sentence.group(1).replace('"\n  + "', "") in _copy("waiting")
    assert 'if (row.ended === true)' in why
    assert why.index('"agents.ended"') < why.index('"agents.waiting"')
    assert '{plan}' in _copy("ended") and 'plan: show(row.plan_word, state)' in why
    assert 'waiting}' in why and 'closed}' in why



def test_a_reopened_gate_says_the_answer_will_supersede_what_stands():
    """The lap-2 answer replaces the lap-1 one, and the form says so first.

    A person pressing the same control a second time is doing something
    different from the first time, and a screen that did not say so would let
    them write a second standing answer without knowing. The receipt id is
    named, because "an earlier answer" is not something a person can go and
    check.
    """
    carried = _decision_rows()
    read = RUNREAD_FILE.read_text(encoding="utf-8")
    assert "standing: standingOf(answered)," in _body(
        read, "planWords(planned, answered)")

    standing = _body(read, "standingOf(mine)")
    # The projection's own reading: unsuperseded, and exactly one of them.
    assert "superseded.has(receipt.receipt_id)" in standing, standing
    assert "current.length === 1" in standing, standing

    said = _sentences(PEOPLE_FILE.read_text(encoding="utf-8"), "reopenedNote(row, state)")
    assert 'typeof row.standing !== "string"' in said, said
    assert '"agents.reopened", {receipt: row.standing}' in said, said
    assert "supersedes {receipt}" in _copy("reopened")
    assert "a decision is never edited" in _copy("reopened")


def test_a_second_answer_on_one_gate_carries_an_identity_of_its_own():
    """A receipt id spelled from the gate and the person can be spelled ONCE.

    That was invisible while a gate could only be answered once: the second
    answer on a reopened lap re-sent the first answer's identity with different
    facts, which the route refuses as a conflict -- so the loop could not be
    answered from the screen at all, whatever `supersedes` said.

    The count is what makes it derivable rather than minted. A lost reply
    re-sent before the write lands counts the same durable answers and produces
    the same id, which is the idempotency the bare form was chosen for.

    It is ALWAYS present and stands BEFORE the actor. As an optional suffix it
    collided across people: `bob-1` answering a gate first minted the same id
    as `bob` answering it second, and one of the two writes would then be
    refused as a retry of the other's answer.
    """
    assert "answers: answered.length," in _body(
        RUNREAD_FILE.read_text(encoding="utf-8"), "planWords(planned, answered)")

    # The decision road left the boot module at its line cap for the module
    # that holds what a press MEANS (`studio-runwrite.js`); the rule is read
    # there.
    writer = (PANEL / "studio-runwrite.js").read_text(encoding="utf-8")
    assert ('const answered = Number.isInteger(row.answers) ? row.answers : 0;'
            in writer), writer
    assert ("receipt_id: `receipt-${row.gate_id}-${answered}-${draft.actor}`"
            in writer), writer
