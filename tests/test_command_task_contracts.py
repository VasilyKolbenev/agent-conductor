"""What a task IS: the record, the binding a run freezes, and the scoped work item.

Project -> Task -> Run. Every claim here is about the contract layer alone --
no directory, no store, no route: a task record is closed at every key and
held exactly at schema version 1; its two ids are bounded to 64 characters so
that ``t<len(scope)>.<work_scope>.<work_item_id>`` stays inside the
128-character id grammar;
the ``task`` key a run freezes into its configuration is read back by a reader
as strict as ``frozen_config_workflow``, where absent is a real answer and
malformed is a refusal, never legacy; and the one refusal that names an absent
task is a reviewed fact carrying the task id and nothing else.

The seam is ``conductor.command.task_contracts`` (and ``ApiRefusal.missing_task``
beside it). Each refusal witness names the mutation that would turn it red.
"""
from __future__ import annotations

from types import MappingProxyType

import pytest

from conductor.command.api_contracts import ApiRefusal
from conductor.command.contracts import ContractError
from conductor.command.task_contracts import (
    MAX_TASK_ID,
    MAX_TASK_TITLE,
    TASK_SCHEMA_VERSION,
    TaskBinding,
    TaskRecord,
    frozen_config_task,
)

NOW = "2026-09-15T12:00:00Z"
#: One past the bound, spelled as a literal so a widened bound cannot pass.
ONE_TOO_LONG = "t" * 65


def a_record(**changes) -> TaskRecord:
    values = {
        "task_id": "task-001",
        "title": "Ship the task store",
        "work_scope": "task-001",
        "created_at": NOW,
    }
    values.update(changes)
    return TaskRecord(**values)


def a_document(**changes) -> dict:
    document = a_record().as_dict()
    document.update(changes)
    return document


# -- the record -----------------------------------------------------------------


def test_the_bounds_are_the_ones_the_contract_names():
    assert TASK_SCHEMA_VERSION == 1
    assert MAX_TASK_ID == 64
    assert MAX_TASK_TITLE == 200


def test_a_record_round_trips_through_its_own_document_with_keys_in_a_fixed_order():
    """`as_dict` is the stored shape, so its key order is part of the contract."""
    record = a_record()
    document = record.as_dict()

    assert list(document) == [
        "schema_version", "task_id", "title", "work_scope", "created_at"]
    assert document["schema_version"] == 1
    assert document["work_scope"] == "task-001"
    assert TaskRecord.from_dict(document) == record
    assert record.schema_version == 1


@pytest.mark.parametrize("field", ["task_id", "work_scope"])
def test_an_identity_of_sixty_four_characters_is_admitted_and_sixty_five_is_refused(field):
    """The bound, at both identity fields. Mutation: drop the length check -> red."""
    assert getattr(a_record(**{field: "t" * 64}), field) == "t" * 64
    with pytest.raises(ContractError, match="64"):
        a_record(**{field: ONE_TOO_LONG})


@pytest.mark.parametrize("value", ["", "has space", "../escape", ".dot", None, 7])
@pytest.mark.parametrize("field", ["task_id", "work_scope"])
def test_a_name_the_id_grammar_refuses_is_refused_for_both_identity_fields(field, value):
    """Mutation: `_bounded_id` bounds `str(value)` without `_id` -> red."""
    with pytest.raises(ContractError, match=field):
        a_record(**{field: value})


def test_a_title_is_stored_exactly_as_given_within_its_bounds():
    """No normalisation: the spaces a person typed are the title they typed."""
    assert a_record(title=" Ship it  ").title == " Ship it  "
    assert a_record(title="x" * 200).title == "x" * 200
    assert a_record(title="Задача — v2 ✓").title == "Задача — v2 ✓"


@pytest.mark.parametrize("title", [
    "", "   ", "\t\n",                        # nothing to display
    "x" * 201,                                # one past the bound
    "a\x00b", "a\x01b", "a\x1fb", "a\x7fb",   # the control range, both ends
    "line\nbreak", "tab\there",               # a title is one line
    None, 7, ["x"], {"title": "x"},           # not text at all
])
def test_a_title_outside_its_bounds_is_refused(title):
    """Mutation: accept whitespace, drop the 200 bound, or skip the control scan -> red."""
    with pytest.raises(ContractError, match="title"):
        a_record(title=title)


@pytest.mark.parametrize("created_at", [
    "2026-09-15 12:00:00", "2026-09-15T12:00:00+03:00", "2026-09-15T12:00:00", None, 0])
def test_created_at_must_be_one_utc_instant(created_at):
    """Mutation: store `created_at` as given instead of through `_timestamp` -> red."""
    with pytest.raises(ContractError, match="created_at"):
        a_record(created_at=created_at)


@pytest.mark.parametrize("document", [
    {**a_document(), "runs": []},             # an extra key: no mutable run list, ever
    {**a_document(), "note": "x"},
    {key: value for key, value in a_document().items() if key != "title"},
    {key: value for key, value in a_document().items() if key != "work_scope"},
    a_document(schema_version=2),
    a_document(schema_version=0),
    a_document(schema_version="1"),
    a_document(schema_version=True),
    a_document(schema_version=1.0),
    [a_document()], None, "task-001", 1,
], ids=lambda value: repr(value)[:60])
def test_from_dict_admits_exactly_the_five_keys_and_schema_version_one(document):
    """Closed at every key and exact at the version. Mutation: `>= 1` -> red on 2."""
    with pytest.raises(ContractError):
        TaskRecord.from_dict(document)


def test_from_dict_reads_a_frozen_mapping_the_way_replay_hands_one_back():
    frozen = MappingProxyType(a_document())
    assert TaskRecord.from_dict(frozen) == a_record()


# -- the binding a run freezes ---------------------------------------------------


def test_a_binding_holds_both_ids_to_the_task_bound():
    assert TaskBinding("task-001", "task-001") == TaskBinding(
        task_id="task-001", work_scope="task-001")
    with pytest.raises(ContractError, match="64"):
        TaskBinding(ONE_TOO_LONG, "task-001")
    with pytest.raises(ContractError, match="work_scope"):
        TaskBinding("task-001", "bad id")
    with pytest.raises(ContractError, match="task_id"):
        TaskBinding(None, "task-001")


def test_a_configuration_naming_no_task_reads_as_none_and_never_as_its_cycle():
    """Absent is a real answer. Mutation: derive a task from `cycle_id` -> red.

    The cycle id here is a perfectly good task id on purpose: a reader that
    guessed would find one to guess.
    """
    assert frozen_config_task({"cycle": {"id": "task-001"}, "instances": []}) is None
    assert frozen_config_task({}) is None


def test_the_binding_this_product_writes_is_the_one_the_reader_reads():
    """The snapshot spelling `{"task": {"id", "work_scope"}}`, read back whole."""
    config = {"cycle": {"id": "c"}, "task": {"id": "task-001", "work_scope": "task-001"}}

    assert frozen_config_task(config) == TaskBinding("task-001", "task-001")
    # As replay hands it back: frozen at every level.
    frozen = MappingProxyType({**config, "task": MappingProxyType(config["task"])})
    assert frozen_config_task(frozen) == TaskBinding("task-001", "task-001")


@pytest.mark.parametrize("reference", [
    {"id": "task-001"},                                   # half of one: no scope
    {"work_scope": "task-001"},                           # half of one: no id
    {"id": "task-001", "work_scope": "task-001", "title": "x"},   # a key it does not carry
    {"id": "task-001", "work_scope": ONE_TOO_LONG},       # over the task bound
    {"id": ONE_TOO_LONG, "work_scope": "task-001"},
    {"id": 1, "work_scope": "task-001"},                  # not an id
    {"id": None, "work_scope": "task-001"},               # null is not absent
    {"id": "task-001", "work_scope": "has space"},
    {}, "task-001", None, [], 1, True,                    # not a binding at all
], ids=lambda value: repr(value)[:60])
def test_a_malformed_task_binding_is_refused_and_never_read_as_absent(reference):
    """CORRUPT, never legacy. Mutation: treat a malformed key as absent -> red."""
    with pytest.raises(ContractError):
        frozen_config_task({"cycle": {"id": "c"}, "task": reference})


def test_the_refusals_say_what_was_found_and_what_must_be_there():
    """The exact sentences, pinned where they are chosen."""
    with pytest.raises(ContractError) as half:
        frozen_config_task({"task": {"id": "task-001"}})
    assert str(half.value) == (
        "frozen config task carries ['id'] and must carry exactly ['id', 'work_scope']")
    with pytest.raises(ContractError) as shape:
        frozen_config_task({"task": "task-001"})
    assert str(shape.value) == "frozen config task must be a JSON object"
    with pytest.raises(ContractError) as config:
        frozen_config_task("not a config")
    assert str(config.value) == "frozen config must be a JSON object"
    with pytest.raises(ContractError) as bound:
        frozen_config_task({"task": {"id": ONE_TOO_LONG, "work_scope": "task-001"}})
    assert "frozen config task id" in str(bound.value) and "64" in str(bound.value)


# -- the refusal that names an absent task ----------------------------------------


def test_missing_task_is_a_service_refusal_naming_only_the_task_id():
    """A reviewed fact: the id the caller sent, no run, no path, no new code."""
    refusal = ApiRefusal.missing_task("task-001")

    assert refusal.code == "service_refused"
    assert refusal.status == 409
    assert refusal.message == "no stored task 'task-001'"
    assert dict(refusal.detail) == {"task_id": "task-001"}
    assert refusal.as_dict() == {"error": {
        "code": "service_refused", "message": "no stored task 'task-001'",
        "detail": {"task_id": "task-001"}}}


def test_missing_task_refuses_to_render_a_name_that_is_not_an_id():
    """What may appear in a browser is reviewed one fact at a time.

    Mutation: `_safe_detail` answers True for any string -> ``<script>``
    renders -> red.
    """
    with pytest.raises(ValueError):
        ApiRefusal.missing_task("has space")
    with pytest.raises(ValueError):
        ApiRefusal.missing_task("<script>")
