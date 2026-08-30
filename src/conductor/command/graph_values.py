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
