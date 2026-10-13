"""The desk's name field keeps to the range its doors share, and its source says only that.

The name of the person at the page is one value the desk sends as the actor of a gate decision
(a `DecisionReceipt`, which takes an id) and of writes that check an actor with `human_identity`
(any non-blank UTF-8 text). The desk keeps to the id grammar so that one value passes both
(ADR-4d, canon row L42). That is the desk's compatibility range. The comment over the pattern
says so and cites the one door whose grammar it can: the gate decision's receipt takes only an
id. It names no route as taking more, because the gate decision route does not: the panel
refuses a name that is not an id before it sends the decision, and the server builds a receipt.
"""
from __future__ import annotations

import re

import pytest

from conductor.command.authorization_terms import human_identity
from conductor.command.contract_values import ContractError
from conductor.command.contracts import DecisionReceipt
from tests.desk_node import PANEL

BOOT = (PANEL / "desk.js").read_text(encoding="utf-8")
DECLARATION = re.compile(r"^const ACTOR = /(?P<pattern>.+)/;$", re.MULTILINE)


def _desk_pattern() -> re.Pattern[str]:
    return re.compile(DECLARATION.search(BOOT).group("pattern"))


def _comment_over_the_pattern() -> str:
    lines = BOOT[:DECLARATION.search(BOOT).start()].splitlines()
    comment = []
    while lines and lines[-1].startswith("//:"):
        comment.insert(0, lines.pop()[3:].strip())
    return " ".join(comment)


def _receipt(actor: str) -> DecisionReceipt:
    return DecisionReceipt(
        receipt_id="decision-001", run_id="run-001", gate_id="release", action="approve",
        actor=actor, decided_at="2026-08-11T07:30:00Z", reason="", scope_refs=("release",),
        config_digest="sha256:" + "a" * 64)


def test_the_comment_over_the_actor_pattern_names_the_shared_compatibility_range():
    comment = _comment_over_the_pattern()
    assert "shared compatibility range" in comment, comment
    assert "ADR-4d" in comment and "L42" in comment, comment


def test_the_comment_over_the_actor_pattern_says_the_decision_receipt_takes_only_an_id():
    comment = _comment_over_the_pattern()
    assert "receipt takes only an id" in comment, comment
    assert "command/contracts.py" in comment, comment


def test_the_comment_over_the_actor_pattern_names_no_route_as_taking_more():
    comment = _comment_over_the_pattern()
    assert re.search(r"\broutes?\b", comment, re.IGNORECASE) is None, comment


def test_a_name_in_the_desk_range_builds_a_decision_receipt_and_passes_human_identity():
    pattern = _desk_pattern()
    for name in ("a", "vasya", "Vasily.K-2_x", "x" * 128):
        assert pattern.fullmatch(name), name
        assert _receipt(name).actor == name
        assert human_identity("actor", name) == name


def test_a_name_outside_the_desk_range_passes_human_identity_and_no_decision_receipt_is_built():
    pattern = _desk_pattern()
    for name in ("Вася Пупкин", "a b", "-x", "x" * 129):
        assert pattern.fullmatch(name) is None, name
        assert human_identity("actor", name) == name
        with pytest.raises(ContractError):
            _receipt(name)
