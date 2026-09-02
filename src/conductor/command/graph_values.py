"""The values a graph document is built out of, and their rules.

Split out of ``graph_definition`` and ``graph_template`` when both crossed the
800-line cap, along the seam ``contract_values`` already found one layer down:
a value's grammar is a self-contained circuit and is not the document that holds
it. Both contracts import these back under their old names, so no caller
anywhere learns that the split happened.

What lives here is exactly what BOTH node contracts have to agree about. A
ceiling the template would store and the definition would refuse is a plan that
cannot run, discovered at run time; a purpose one door bounded and the other did
not is prose reaching a vendor binary through the looser of two judges. One
rule, one home, is what makes those impossible rather than unlikely.

``NodePosition`` is here for a different reason and the docstring below says it:
it is the one value on a template that is NOT execution semantics, and keeping
it beside the plan's own grammars is what stops it drifting into them.

Like the modules it was taken from, this has no filesystem, subprocess, server
or adapter imports.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .contracts import ContractError


MIN_LOOP_BOUND, MAX_LOOP_BOUND = 1, 99
#: The widest timeout an ACTION contract accepts, so a plan-side ceiling is
#: always one a real request could sit under. Held equal to the action
#: contract's own bound by tests/test_command_graph_bounds.py rather than
#: imported: `contracts` imports this module, and the reverse would be a cycle.
MAX_ACTION_SECONDS = 86400


def _positive(name: str, value: object, *, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{name} must be an integer, got {value!r}")
    if not low <= value <= high:
        raise ContractError(f"{name} must be between {low} and {high}, got {value}")
    return value


def _json_object(name: str, value: object) -> dict[str, Any]:
    """A JSON object is exactly ``dict``, settled BEFORE anything reads it.

    Everything else was being laundered rather than refused. A falsy value --
    ``None``, ``[]``, ``""``, ``0``, ``False`` -- became an empty payload, so a
    caller who sent the wrong shape was told nothing and the node claimed
    arguments it never received. A list of pairs became a DIFFERENT object,
    inventing a mapping nobody wrote. And a string or a number reached
    ``dict()`` and left an untyped ``TypeError``/``ValueError`` carrying
    whatever it carried.

    A ``dict`` subclass is refused too: it answers ``items`` however it likes,
    and this value is copied and digested.
    """
    if type(value) is not dict:
        raise ContractError(
            f"{name} must be a JSON object") from None
    return value


#: How far a step may sit from the canvas origin, on either axis. A bound
#: rather than a free integer, because a document is durable and a coordinate
#: nobody could ever scroll to is a step a person cannot find again. Whole
#: pixels: a canvas is a grid of them, and a fraction would put a rendering
#: detail into a digested document.
POSITION_LIMIT = 100_000


@dataclass(frozen=True)
class NodePosition:
    """Where a person PUT a step on the canvas. Editor state, made durable.

    It is on the template node and deliberately nowhere else. A position is not
    execution semantics: `materialize` drops it, so a run's frozen plan carries
    no coordinate, no replay depends on one, and moving a box on a screen can
    never change what a run does. That separation is the whole reason this is a
    value of its own rather than two more fields on the step -- a reader asking
    "what does this step DO" never has to walk past where it sits.

    Absent means the canvas may place the step itself, which is what every
    template written before this existed says. `dalio-v1` and `dalio-v2` name
    no position, so their revision digests do not move.
    """

    x: int
    y: int

    _FIELDS = frozenset({"x", "y"})

    def __post_init__(self) -> None:
        for name in self._FIELDS:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ContractError(
                    f"a node position names whole pixels; {name} is {value!r}")
            if not -POSITION_LIMIT <= value <= POSITION_LIMIT:
                raise ContractError(
                    f"a node position stays within {POSITION_LIMIT} of the "
                    f"origin; {name} is {value}")

    def as_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, value: object) -> "NodePosition":
        data = dict(_json_object("node position", value))
        unknown = sorted(set(data) - cls._FIELDS)
        if unknown:
            raise ContractError(
                f"a node position carries unsupported field(s) {unknown!r}")
        missing = sorted(cls._FIELDS - set(data))
        if missing:
            raise ContractError(
                f"a node position needs both axes; missing {missing!r}")
        return cls(x=data["x"], y=data["y"])


def _position(value: object) -> "NodePosition | None":
    """A position, or None when the document names none.

    Absent and explicit-null are ONE fact here, unlike `arguments` next door:
    there is no third thing a coordinate could mean, and a document that says
    `"position": null` is saying the canvas may place this step -- which is
    what saying nothing says.
    """
    if value is None:
        return None
    if type(value) is NodePosition:
        return value
    return NodePosition.from_dict(value)


#: The longest a step's purpose may be. A bound rather than free text: a purpose
#: is durable, it is frozen into every run's plan, and for a task it is carried
#: into the code-owned frame handed to a vendor binary -- three places where "as
#: long as somebody pasted" is not an answer. Long enough for a sentence that
#: says why a step exists, short enough that it cannot become the instruction.
MAX_PURPOSE = 500


def settled_purpose(purpose: object) -> str | None:
    """One grammar for a step's purpose, judged the same in template and plan.

    Prose a PERSON wrote about why a step exists. It is project-authored
    context, and it is bounded, single-line and NUL-free for the reason the
    bound exists: on a task node this rides into the frame a vendor binary is
    handed, where an unbounded multi-line value would stop being context and
    start being an instruction.

    Absent stays absent, and so does whitespace -- an empty string is the same
    answer as saying nothing -- so no document written before this field existed
    changes a byte or moves a digest.
    """
    if purpose is None:
        return None
    if type(purpose) is not str:
        raise ContractError("a step's purpose is text, or nothing at all")
    settled = purpose.strip()
    if not settled:
        return None
    if any(character in settled for character in ("\x00", "\n", "\r")):
        raise ContractError(
            "a step's purpose is one line of text: it carries no NUL and no "
            "line break")
    if len(settled) > MAX_PURPOSE:
        raise ContractError(
            f"a step's purpose is at most {MAX_PURPOSE} characters; this one "
            f"is {len(settled)}")
    return settled


#: What a plan may require of a step's verification, BEYOND the fact that one
#: happened. A closed set, and the one word in it names the one degree of
#: freedom the evidence contract still has: `EvidenceRef.digest` is optional, so
#: a verification may stand without naming WHAT it checked, and the replay
#: relation has therefore never asked for one.
#:
#: The set is closed in one direction only, and that asymmetry is the field.
#: A plan may TIGHTEN what a run must prove and it may never loosen it, so there
#: is no word here for "less": a document saying `"none"`, `"optional"` or
#: `"any"` would be asking the runtime to drop a demand it makes of every step,
#: and it is refused rather than quietly ignored.
REQUIRED_EVIDENCE = frozenset({"digest"})


def settled_required_evidence(value: object) -> str | None:
    """One grammar for a step's evidence demand, judged the same in both.

    Here for `settled_purpose`'s reason one field over: a template that stored a
    word the definition would refuse is a plan that cannot materialize, found
    out at run time rather than where it was drawn.

    Absent stays absent, and so does whitespace -- an empty string is the same
    answer as saying nothing -- so no document written before this field existed
    changes a byte or moves a digest. Anything else is one of `REQUIRED_EVIDENCE`
    and nothing else: this vocabulary may only ever grow words that ask for
    MORE, so a word it does not carry is refused rather than read as "no
    requirement".

    Args:
        value: What the document says this step's verification must name.

    Returns:
        The settled word, or None when the plan requires nothing extra.

    Raises:
        ContractError: The value is not text, or is a word this build has no
            tightening for.
    """
    if value is None:
        return None
    if type(value) is not str:
        raise ContractError(
            "a step's evidence requirement is text, or nothing at all")
    settled = value.strip()
    if not settled:
        return None
    if settled not in REQUIRED_EVIDENCE:
        raise ContractError(
            f"a step may require {sorted(REQUIRED_EVIDENCE)} of its "
            f"verification, and {settled!r} is not one of them; a plan may ask "
            "for more proof than the runtime already demands and never for less")
    return settled


#: What a plan may do to the REST of a run when one step fails. One word, and
#: the asymmetry is the same as `REQUIRED_EVIDENCE`'s next door: this vocabulary
#: may only ever grow words that TIGHTEN. There is no word here for "carry on",
#: because carrying on is what a plan that says nothing already gets.
#:
#: `halt_run` is not routing and the two must never be folded together. An
#: `on_failed` edge says where the plan goes NEXT; this says nothing further may
#: be authorized in this run at all -- including branches no edge from the
#: failing step can reach. Neither can express the other, which is why the field
#: exists beside the conditions rather than instead of them.
FAILURE_POLICIES = frozenset({"halt_run"})


def settled_failure_policy(value: object) -> str | None:
    """One grammar for a step's failure policy, judged the same in both.

    Here for `settled_required_evidence`'s reason one field over: a template
    that stored a word the definition would refuse is a plan that cannot
    materialize, found out at run time rather than where it was drawn.

    Absent stays absent, and so does whitespace -- an empty string is the same
    answer as saying nothing, which is what a Studio select spells when a person
    clears it -- so no document written before this field existed changes a byte
    or moves a digest.

    Args:
        value: What the document says should happen to the run when this step
            fails.

    Returns:
        The settled word, or None when the plan asks for no halt.

    Raises:
        ContractError: The value is not text, or is a word this build has no
            behaviour for.
    """
    if value is None:
        return None
    if type(value) is not str:
        raise ContractError(
            "a step's failure policy is text, or nothing at all")
    settled = value.strip()
    if not settled:
        return None
    if settled not in FAILURE_POLICIES:
        raise ContractError(
            f"a step's failure policy is one of {sorted(FAILURE_POLICIES)}, "
            f"and {settled!r} is not one of them; this vocabulary may only "
            "grow words that stop a run, never words that let one continue")
    return settled


#: What a step may ask this build to do when a document it requires does not
#: exist when the step is reached. Both words are FAIL-CLOSED and there is no
#: third: nothing here skips the step, substitutes another document, or lets the
#: run go on as though the input had arrived.
#:
#: `fail` is what this build has always done, now sayable out loud: the step is
#: reached, the input is resolved, the resolution refuses, and a durable
#: `failed` receipt is written with no task spawned and no model call spent.
#: `block` is the new one: the step is never offered at all while the document
#: is absent, so nothing is attempted and nothing fails -- the plan waits, and
#: the screen says which document it waits for.
#:
#: Saying nothing means `fail`. That is not a default chosen here for
#: convenience: it is the behaviour every plan already written has, and the
#: enum's `fail` exists so a person can say it on purpose rather than to name a
#: second behaviour. A witness holds the two identical.
MISSING_ARTIFACT_POLICIES = frozenset({"fail", "block"})

#: What a GATE may demand of the answer that settles it. One word, and it only
#: ever TIGHTENS: `human_approval` says this gate may not be set aside, so the
#: one answer that closes a gate without judging the work -- `waive` -- is
#: refused on it, at the door and again on replay.
#:
#: Absent is the whole of backward compatibility: every gate written before this
#: existed may still be waived, exactly as it always could, and no shipped
#: document moves a byte. A word added here must make an answer HARDER to give;
#: a word that made one easier would let a revision quietly loosen a gate a
#: person already approved under stricter terms.
GATE_SUCCESS_DEMANDS = frozenset({"human_approval"})


def settled_success_requires(value: object) -> str | None:
    """One grammar for what a gate demands of its answer, judged in both.

    Here for `settled_missing_artifact_policy`'s reason one field over: a
    template that stored a word the definition would refuse is a plan that
    cannot materialize, found out at run time rather than where it was drawn.

    Absent stays absent, and so does whitespace -- an empty string is the same
    answer as saying nothing, which is what a Studio select spells when a person
    clears it -- so no document written before this field existed changes a byte
    or moves a digest.

    Args:
        value: What the document demands of the answer that settles this gate.

    Returns:
        The settled word, or None when the gate demands nothing extra and may
        be answered every way this build has always allowed.

    Raises:
        ContractError: The value is not text, or is a word this build has no
            behaviour for.
    """
    if value is None:
        return None
    if type(value) is not str:
        raise ContractError(
            "a gate's success requirement is text, or nothing at all")
    settled = value.strip()
    if not settled:
        return None
    if settled not in GATE_SUCCESS_DEMANDS:
        raise ContractError(
            f"a gate's success requirement is one of "
            f"{sorted(GATE_SUCCESS_DEMANDS)}, and {settled!r} is not one of "
            "them; every word this vocabulary may grow must make the answer "
            "harder to give, never easier, because a revision that loosened a "
            "gate would change what an earlier approval meant")
    return settled


def settled_missing_artifact_policy(value: object) -> str | None:
    """One grammar for a step's missing-artifact policy, judged the same in both.

    Here for `settled_failure_policy`'s reason one field over: a template that
    stored a word the definition would refuse is a plan that cannot materialize,
    found out at run time rather than where it was drawn.

    Absent stays absent, and so does whitespace -- an empty string is the same
    answer as saying nothing, which is what a Studio select spells when a person
    clears it -- so no document written before this field existed changes a byte
    or moves a digest.

    Args:
        value: What the document says should happen when a required input
            artifact does not exist.

    Returns:
        The settled word, or None when the plan names no policy -- which reads
        as `fail`, the behaviour every plan already had.

    Raises:
        ContractError: The value is not text, or is a word this build has no
            behaviour for.
    """
    if value is None:
        return None
    if type(value) is not str:
        raise ContractError(
            "a step's missing-artifact policy is text, or nothing at all")
    settled = value.strip()
    if not settled:
        return None
    if settled not in MISSING_ARTIFACT_POLICIES:
        raise ContractError(
            f"a step's missing-artifact policy is one of "
            f"{sorted(MISSING_ARTIFACT_POLICIES)}, and {settled!r} is not one "
            "of them; every word this vocabulary may grow must be fail-closed, "
            "because a missing input is never evidence that the work is done")
    return settled


def settled_bounds(timeout_seconds: object,
                   attempt_bound: object) -> dict[str, int | None]:
    """The two plan-side ceilings, judged once for both node contracts.

    ONE rule with one home, called by `GraphNode` and by `TemplateNode`. A
    second copy would be a second answer to "what may a plan ask for", and the
    template would be able to store a ceiling the definition it materializes
    into would then refuse -- which is a plan that cannot run, discovered at
    run time.

    The timeout range is the ACTION contract's own, so a plan-side ceiling is
    always one a real request could sit under: a plan naming 90000 seconds
    would refuse every legal request, which is a plan nobody can run rather
    than a strict one. The attempt range is the loop bound's, because
    `MIN_LOOP_BOUND..MAX_LOOP_BOUND` is already what this product means by "how
    many times may this be reopened", and a second, wider vocabulary for one
    idea is two answers to one question.

    `None` passes through untouched and means the plan constrains nothing.
    `bool` is refused by `_positive`, because `True` is an `int` in Python and
    it is not one attempt.

    Args:
        timeout_seconds: The longest this step's work may run, or None.
        attempt_bound: The most attempts the plan allows it, or None.

    Returns:
        The settled values, keyed by field name.

    Raises:
        ContractError: Either value is present and not an integer in range.
    """
    settled: dict[str, int | None] = {}
    for name, value, high in (
            ("timeout_seconds", timeout_seconds, MAX_ACTION_SECONDS),
            ("attempt_bound", attempt_bound, MAX_LOOP_BOUND)):
        settled[name] = None if value is None else _positive(
            f"node {name}", value, low=1, high=high)
    return settled


# -- the closed document's own grammars ------------------------------------
#
# Moved here from `graph_definition` when it crossed the cap a second time,
# along the seam this module was already the far side of: `_json_object` has
# lived here since the first split while `_json_list` beside it did not, and
# a walk that both contracts are held to is exactly what this module is for.
# `graph_definition` imports them back under their old names, so no caller
# anywhere learns that they moved.


#: Every word that belongs to a RUN rather than to a plan. Refused as a field
#: name anywhere in this document, at every level, so no amount of nesting can
#: smuggle execution state into something called immutable. ``arguments`` is
#: exempt by design: it is the capability's own payload, judged by the
#: capability's own schema at the provider door.
#:
#: ``required_evidence`` is NOT one of these and must never become one, which is
#: worth saying because the two look alike from a distance: ``evidence`` and
#: ``evidence_refs`` are what a RUN produced, and the whole of this refusal is
#: that a plan may not carry them. ``required_evidence`` is a DEMAND the plan
#: makes of a run that has not happened -- it names no evidence, resolves to no
#: row, and is written by whoever drew the workflow. ``_reserved`` matches keys
#: exactly, so the difference is a fact of the code and not of this comment; a
#: node carrying a nested ``{"evidence": ...}`` is refused exactly as it was.
RUNTIME_ONLY_FIELDS = frozenset({
    "attempt_id", "attempt_ids", "attempts", "availability", "bound_reached",
    "decided_at", "decision", "decisions", "evidence", "evidence_refs",
    "health", "observed_at", "outcome", "outcomes", "pass", "passes", "phase",
    "started_at", "state", "status", "timeline",
})


#: The one FIELD whose value is a capability's own payload. Its exemption is
#: applied by the code that handles that field -- ``GraphNode.from_dict`` lifts
#: the value out before the walk runs -- and never by the walk itself: a name
#: is not a field, and a key merely SPELLED ``arguments`` in some tolerant
#: metadata is nobody's payload and got scanned by nothing.
EXEMPT_FIELD = "arguments"


def _reserved(name: str, document: Mapping[str, Any]) -> None:
    """Refuse a runtime word used as a field name at ANY depth, with no exception.

    Checking one level was a promise this could not keep, and exempting a NAME
    was the same mistake one layer down: a tolerant ``extra`` holds arbitrary
    JSON, so ``{"arguments": {"status": ...}}`` was skipped by a walk that had
    no idea whose payload it was looking at. This walk skips nothing. The one
    real payload is lifted out by its own field before the walk ever sees it.
    """
    stack: list[Any] = [document]
    found: set[str] = set()
    while stack:
        value = stack.pop()
        if isinstance(value, Mapping):
            found |= set(value) & RUNTIME_ONLY_FIELDS
            stack.extend(value.values())
        elif isinstance(value, (list, tuple)):
            stack.extend(value)
    if found:
        raise ContractError(
            f"{name} carries runtime-only field(s) {sorted(found)!r}; a graph "
            "definition records intent, and what a run did belongs to its projection")


def _exact(name: str, value: object, expected: type) -> Any:
    """Accept the base type itself, never a subclass that can act on its own.

    A subclass satisfies ``isinstance`` and then answers ``as_dict`` with
    whatever it likes -- which is how a runtime word reached a definition and
    its digest. Identity of type is the only check that closes that, and it is
    followed by a rebuild, because a value can also be edited after it was
    validated.
    """
    if type(value) is not expected:
        raise ContractError(
            f"{name} must be exactly {expected.__name__}; a subclass may answer "
            "for itself and is not accepted at this boundary")
    return value


def _json_list(name: str, value: object) -> list[Any]:
    """A JSON array is exactly ``list``, refused BEFORE anything iterates it.

    A tuple reaching here came from Python, not from JSON. A ``list`` subclass
    reaching here is worse: it satisfies ``isinstance`` and then answers
    ``__iter__`` with an exception of its own, whose message this contract would
    have carried outward. Identity of type settles both, and it is checked
    before the value is touched.
    """
    if type(value) is not list:
        raise ContractError(f"{name} must be a JSON array") from None
    return value


#: Tells "the field was not there" apart from "the field was there and was
#: null". Absent means the capability was given nothing; present-and-null is a
#: caller saying something, and what it says is not a JSON object.
_ABSENT = object()


def _sequence(name: str, value: object) -> tuple[Any, ...]:
    """Materialize a caller's sequence, or refuse in this contract's own words.

    The Python-side constructors take any sequence, which means they take one
    whose iteration raises. Whatever it raises is the caller's, not ours, so it
    is replaced here rather than allowed to travel with whatever it carries.
    """
    if isinstance(value, (str, bytes, Mapping)):
        raise ContractError(f"{name} must be a sequence of records") from None
    try:
        return tuple(value)
    except Exception:  # noqa: BLE001 -- a hostile iterable carries its own words
        raise ContractError(f"{name} could not be read as a sequence") from None
