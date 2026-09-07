"""The Runs screen's closed vocabularies, each derived from its Python owner.

Split out of ``tests/test_studio_runs.py`` when that module reached the line
cap, along the seam its own section header drew: every closed word list the
screen spells is a copy of exactly one Python owner, and each test below
DERIVES the owner's answer rather than restating it -- the record kinds from
the store's own table, the ladder from the enum's declaration order, the
timeline's fields from each contract's exact field set. A word added on either
side and not the other reds one of these.

The readers (``frozen_list`` and its siblings) and the file constants stay in
``tests/test_studio_runs.py``, which every other Studio test module already
imports them from; this module imports them the same way.

Named ``test_studio_*`` on purpose, for the reason its parent gives.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from conductor.command.attempts import ATTEMPT_PHASES
from conductor.command.contract_values import (
    _RESULT_OUTCOMES,
    _RUN_STATES,
    _VERIFICATION_STATES,
    ControlMode,
)
from conductor.command.graph_projection import GATE_STATES, NODE_PHASES
from conductor.command.run_store import _RECORDS

from tests.test_studio_runs import (
    MOUNTED,
    WORDS_FILE,
    WORDS_OF,
    frozen_arrays,
    frozen_keys,
    frozen_list,
    frozen_pairs,
)


def test_the_runs_screen_spells_the_projections_node_phases() -> None:
    assert frozen_list(WORDS_FILE, "NODE_PHASES") == list(NODE_PHASES)


@pytest.mark.parametrize("path", MOUNTED, ids=lambda path: path.name)
def test_both_screens_spell_the_projections_gate_states(path: Path) -> None:
    assert sorted(frozen_list(WORDS_OF[path], "GATE_STATES")) == sorted(
        GATE_STATES)


def test_the_runs_screen_spells_the_contracts_result_outcomes() -> None:
    assert frozen_list(WORDS_FILE, "RESULT_OUTCOMES") == sorted(_RESULT_OUTCOMES)


def test_the_runs_screen_spells_the_contracts_verification_states() -> None:
    assert frozen_list(WORDS_FILE, "VERIFICATION_STATES") == sorted(
        _VERIFICATION_STATES)


def test_the_runs_screen_spells_the_contracts_run_states() -> None:
    assert frozen_list(WORDS_FILE, "RUN_STATES") == sorted(_RUN_STATES)


def test_the_runs_screen_spells_both_durable_attempt_phases() -> None:
    assert frozen_list(WORDS_FILE, "ATTEMPT_PHASES") == sorted(ATTEMPT_PHASES)


def test_the_runs_screen_names_every_record_kind_the_store_can_hold() -> None:
    """The timeline renders the journal, so it must know every kind of it."""
    assert frozen_keys(WORDS_FILE, "RECORD_KINDS") == sorted(_RECORDS)


@pytest.mark.parametrize("name", ["INSTANT_FIELDS", "ROW_FACTS"])
def test_every_timeline_table_is_keyed_by_real_record_kinds(name: str) -> None:
    assert frozen_keys(WORDS_FILE, name) == sorted(_RECORDS)


def test_every_field_a_timeline_row_shows_is_one_the_record_really_has() -> None:
    """A misspelled field renders nothing and looks like an empty record. The
    names are held against each contract's own exact field set."""
    facts = frozen_arrays(WORDS_FILE, "ROW_FACTS")
    assert set(facts) == set(_RECORDS)
    for kind, names in sorted(facts.items()):
        contract, _ = _RECORDS[kind]
        unknown = sorted(set(names) - set(contract._FIELDS))
        assert not unknown, f"{kind} has no field {unknown}"
        assert names, f"{kind} shows no field at all"


def test_every_instant_a_timeline_row_stamps_is_the_records_own() -> None:
    stamps = frozen_pairs(WORDS_FILE, "INSTANT_FIELDS")
    assert set(stamps) == set(_RECORDS)
    for kind, stamp in sorted(stamps.items()):
        contract, _ = _RECORDS[kind]
        assert stamp in contract._FIELDS, f"{kind} has no field {stamp!r}"


def test_the_runs_screen_spells_the_whole_authority_ladder_in_order() -> None:
    """A mode a run can hold and this screen cannot describe is a silent gap,
    and the ladder's own order is the enum's declaration order."""
    assert frozen_keys(WORDS_FILE, "CONTROL_MODES") == [
        mode.value for mode in ControlMode]


def test_the_five_progression_steps_are_records_and_attempt_phases() -> None:
    """The progression is not a story this screen tells: three of its five
    names are record kinds and two are the attempt event's own phases."""
    steps = frozen_list(WORDS_FILE, "TIMELINE_STEPS")
    assert steps == ["action_proposal", "action_request", "effect_lease",
                     "execution_observed", "action_result"]
    assert {steps[0], steps[1], steps[4]} <= set(_RECORDS)
    assert {steps[2], steps[3]} == set(ATTEMPT_PHASES)
