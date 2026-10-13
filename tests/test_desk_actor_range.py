"""The desk's name field takes the range both doors share, and its source says only that.

The name of the person at the page is one value the desk sends as the actor of a gate decision
(the old `DecisionReceipt`, which takes an id) and of the newer routes (which take any non-empty
UTF-8 text). The desk keeps to the id grammar so that one value passes both (ADR-4d, canon row
L42). It is the desk's compatibility range, not a grammar every route requires, and the comment
over the pattern must not say the second thing.
"""
from __future__ import annotations

import re

import pytest

from conductor.command.authorization_terms import human_identity
from conductor.command.contract_values import ContractError, _id
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


def test_the_comment_over_the_actor_pattern_names_the_shared_compatibility_range():
    comment = _comment_over_the_pattern()
    assert "shared compatibility range" in comment, comment
    assert "ADR-4d" in comment and "L42" in comment, comment
    assert "The routes take more" in comment, comment


def test_the_comment_over_the_actor_pattern_does_not_say_every_route_requires_the_id_grammar():
    comment = _comment_over_the_pattern()
    assert "every id of the routes" not in comment, comment
    assert "would refuse there" not in comment, comment
    assert "what the routes will take" not in comment, comment


def test_a_name_in_the_desk_range_passes_the_decision_receipt_and_the_routes():
    pattern = _desk_pattern()
    for name in ("a", "vasya", "Vasily.K-2_x", "x" * 128):
        assert pattern.fullmatch(name), name
        assert _id("actor", name) == name
        assert human_identity("actor", name) == name


def test_the_routes_take_a_name_outside_the_desk_range_that_the_decision_receipt_refuses():
    pattern = _desk_pattern()
    for name in ("Вася Пупкин", "a b", "-x", "x" * 129):
        assert pattern.fullmatch(name) is None, name
        assert human_identity("actor", name) == name
        with pytest.raises(ContractError):
            _id("actor", name)
