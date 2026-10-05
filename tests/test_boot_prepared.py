"""The shared preparation of the journals that name a boot in every record (`boot_prepared`).

One module reads, checks and writes the chain of immutable preparations and says, from the chain
and from the measurement now, whether a restart is proven; the two journals (the attempt ACL loans
and the clone attempts) only say what their record binds. Pure but for the files of one directory.
"""
from __future__ import annotations

from contextlib import ExitStack
import os

import pytest

from conductor import boot_prepared as prepared, boot_witness
from conductor import ownership_records as records
from conductor.boot_witness import BootRefused
from tests._boot_world import GUID, OTHER_GUID, assert_plain_restart_advice, counter, later_boot
from tests._prepared_world import (FORGERIES, LEGACY_OTHER, LEGACY_SAME_MACHINE,
                                   STANDING_ENVIRONMENT, THIRD_GUID, read, rewrite)

SUBJECT = "a" * 32
STEM = f"acl-{SUBJECT}"
HELD = {"parent": [1, 2], "work": [3, 4]}
NOW = counter(42)


def record(boot=LEGACY_SAME_MACHINE, **extra):
    return {"schema": 1, "attempt": SUBJECT, "boot": boot, "phase": "applied", **extra}


def facts_of(row):
    return prepared.facts("acl-attempt", SUBJECT, row)


def write(directory, row, chain, current, held=None):
    with ExitStack() as files:
        return prepared.write_next(files, directory, STEM, facts_of(row),
                                   dict(HELD if held is None else held), chain, current)


def chain_of(directory, row, held=None):
    with ExitStack() as files:
        return prepared.read_chain(files, directory, STEM, facts_of(row),
                                   dict(HELD if held is None else held))


def path_of(directory, index=0):
    return directory / f"{STEM}.prepared-{index}.json"


# -- the digest of the record --------------------------------------------------------------------

def test_the_digest_of_a_record_ignores_its_phase_and_nothing_else():
    base = record()
    assert prepared.record_digest(base) == prepared.record_digest({**base, "phase": "retired"})
    for change in ({"boot": NOW}, {"schema": 2}, {"attempt": "b" * 32}, {"extra": 1}):
        assert prepared.record_digest({**base, **change}) != prepared.record_digest(base)
    shuffled = dict(reversed(list(base.items())))
    assert prepared.record_digest(shuffled) == prepared.record_digest(base)


def test_the_facts_a_preparation_binds_are_the_kind_the_subject_the_digest_and_the_boot():
    row = record()
    assert prepared.facts("acl-attempt", SUBJECT, row) == {
        "kind": "acl-attempt", "subject": SUBJECT, "record_digest": prepared.record_digest(row),
        "record_boot": LEGACY_SAME_MACHINE}


@pytest.mark.parametrize(("schema", "boot", "fits"), [
    (1, LEGACY_SAME_MACHINE, True), (1, "linux:00000000-1111-4222-8333-444444444444", True),
    (1, NOW, False), (2, NOW, True), (2, LEGACY_SAME_MACHINE, False),
    (2, "darwin:00000000-1111-4222-8333-444444444444", False), (3, NOW, False),
    (0, NOW, False), (True, NOW, False), ("2", NOW, False), (2, None, False), (1, 7, False),
    (1, "windows:not-a-uuid", False)])
def test_a_schema_and_a_boot_text_agree_only_in_the_two_closed_pairs(schema, boot, fits):
    assert prepared.schema_fits(schema, boot) is fits


# -- the names ------------------------------------------------------------------------------------

def test_no_preparation_is_an_empty_chain(tmp_path):
    assert prepared.names(tmp_path, STEM) == []
    assert chain_of(tmp_path, record()) == ()


def test_the_names_of_a_record_are_a_whole_sequence_and_another_record_is_not_mistaken_for_it(
        tmp_path):
    other = "acl-" + "b" * 32
    for name in (f"{STEM}.json", f"{other}.prepared-0.json", f".{STEM}.json.0123456789abcdef.tmp",
                 f"{STEM}x.prepared-0.json"):
        (tmp_path / name).write_bytes(b"{}")
    assert prepared.names(tmp_path, STEM) == []
    for index in (0, 1, 2):
        path_of(tmp_path, index).write_bytes(b"{}")
    assert [path.name for path in prepared.names(tmp_path, STEM)] == [
        f"{STEM}.prepared-{i}.json" for i in (0, 1, 2)]


@pytest.mark.parametrize("stray", ["x", "01", "-1", "0.json", "1a", ""])
def test_a_stray_name_that_starts_like_a_preparation_refuses(tmp_path, stray):
    path_of(tmp_path, 0).write_bytes(b"{}")
    (tmp_path / f"{STEM}.prepared-{stray}.json").write_bytes(b"{}")
    with pytest.raises(prepared.PreparationInvalid, match="no restart preparation"):
        prepared.names(tmp_path, STEM)


def test_a_gap_in_the_numbering_refuses(tmp_path):
    path_of(tmp_path, 1).write_bytes(b"{}")
    with pytest.raises(prepared.PreparationInvalid, match="whole sequence"):
        prepared.names(tmp_path, STEM)
    path_of(tmp_path, 0).write_bytes(b"{}")
    path_of(tmp_path, 3).write_bytes(b"{}")
    with pytest.raises(prepared.PreparationInvalid, match="whole sequence"):
        prepared.names(tmp_path, STEM)


# -- writing and reading the chain ----------------------------------------------------------------

def test_the_first_preparation_is_written_exclusively_and_read_back_whole(tmp_path):
    row = record()
    first = write(tmp_path, row, (), counter(43))
    assert first == read(path_of(tmp_path)) and first["sequence"] == 0
    assert first["previous_digest"] is None and first["held"] == HELD
    assert first["protocol"] == prepared.PROTOCOL and first["prepared_boot"] == counter(43)
    assert chain_of(tmp_path, row) == (first,)
    with pytest.raises(FileExistsError):
        write(tmp_path, row, (), counter(44))
    assert read(path_of(tmp_path)) == first


def test_a_follow_up_binds_the_digest_of_the_one_before_and_a_chain_reads_whole(tmp_path):
    row = record()
    first = write(tmp_path, row, (), counter(43))
    second = write(tmp_path, row, (first,), counter(7, OTHER_GUID))
    third = write(tmp_path, row, (first, second), counter(3, THIRD_GUID))
    assert second["previous_digest"] == records.digest(records.canonical(first))
    assert third["previous_digest"] == records.digest(records.canonical(second))
    assert [item["sequence"] for item in chain_of(tmp_path, row)] == [0, 1, 2]


def test_a_follow_up_in_the_environment_that_already_stands_does_not_stand(tmp_path):
    row = record()
    first = write(tmp_path, row, (), counter(43))
    write(tmp_path, row, (first,), counter(90))
    with pytest.raises(prepared.PreparationInvalid, match="environment that already stands"):
        chain_of(tmp_path, row)


def test_a_counter_record_cannot_be_prepared_in_its_own_environment(tmp_path):
    row = record(NOW)
    write(tmp_path, row, (), counter(43))
    with pytest.raises(prepared.PreparationInvalid, match="environment that already stands"):
        chain_of(tmp_path, row)
    path_of(tmp_path).unlink()
    write(tmp_path, row, (), counter(7, OTHER_GUID))
    assert chain_of(tmp_path, row)[0]["prepared_boot"] == counter(7, OTHER_GUID)


@pytest.mark.parametrize("name", sorted(set(FORGERIES) - {STANDING_ENVIRONMENT}))
def test_every_forged_field_of_a_preparation_refuses(tmp_path, name):
    row = record()
    write(tmp_path, row, (), counter(43))
    rewrite(path_of(tmp_path), FORGERIES[name])
    with pytest.raises(prepared.PreparationInvalid):
        chain_of(tmp_path, row)


def test_a_preparation_of_another_record_or_of_a_changed_record_refuses(tmp_path):
    row = record()
    write(tmp_path, row, (), counter(43))
    with pytest.raises(prepared.PreparationInvalid, match="record_digest"):
        chain_of(tmp_path, {**row, "extra": 1})
    with pytest.raises(prepared.PreparationInvalid, match="subject"):
        with ExitStack() as files:
            prepared.read_chain(files, tmp_path, STEM, prepared.facts("acl-attempt", "b" * 32, row),
                                dict(HELD))
    assert chain_of(tmp_path, {**row, "phase": "retired"})


def test_the_held_objects_must_be_the_records_or_absent_and_the_keys_must_match(tmp_path):
    row = record()
    write(tmp_path, row, (), counter(43), held={"parent": [1, 2], "work": None})
    assert chain_of(tmp_path, row)[0]["held"] == {"parent": [1, 2], "work": None}
    path_of(tmp_path).unlink()
    write(tmp_path, row, (), counter(43))                        # holds [3, 4] for `work`
    with pytest.raises(prepared.PreparationInvalid, match="held"):
        chain_of(tmp_path, row, held={"parent": [1, 2], "work": [5, 6]})
    with pytest.raises(prepared.PreparationInvalid, match="held"):
        chain_of(tmp_path, row, held={"parent": [1, 2]})
    with pytest.raises(prepared.PreparationInvalid, match="held"):
        chain_of(tmp_path, row, held={"parent": [1, 2], "work": [3, 4], "login": [7, 8]})


@pytest.mark.skipif(os.name != "nt", reason="a native file hold is a Windows share mode")
def test_the_files_of_the_chain_are_held_while_it_is_in_use(tmp_path):
    row = record()
    write(tmp_path, row, (), counter(43))
    with ExitStack() as files:
        prepared.read_chain(files, tmp_path, STEM, facts_of(row), dict(HELD))
        with pytest.raises(OSError):
            path_of(tmp_path).unlink()
    path_of(tmp_path).unlink()


def test_a_per_boot_id_record_is_never_asked_for_preparations(tmp_path):
    row = record("linux:00000000-1111-4222-8333-444444444444")
    path_of(tmp_path).write_bytes(b"not even json")
    (tmp_path / f"{STEM}.prepared-x.json").write_bytes(b"{}")
    assert chain_of(tmp_path, row) == ()


def test_a_second_name_of_a_preparation_file_refuses(tmp_path):
    row = record()
    write(tmp_path, row, (), counter(43))
    os.link(path_of(tmp_path), tmp_path / "alias.json")
    with pytest.raises(prepared.PreparationInvalid):
        chain_of(tmp_path, row)


# -- what the chain says about a restart -----------------------------------------------------------

def standing_of(directory, row, current):
    with ExitStack() as files:
        return prepared.standing(files, directory, STEM, facts_of(row), dict(HELD), current,
                                 "ownership recover-containers")


def test_a_legacy_record_without_a_preparation_names_the_explicit_action(tmp_path):
    found = standing_of(tmp_path, record(), counter(43))
    assert found.chain == () and "--prepare-restart" in found.reason
    assert "ownership recover-containers" in found.reason and "predates" in found.reason


def test_a_legacy_record_with_a_preparation_stands_on_it_alone(tmp_path):
    row = record()
    write(tmp_path, row, (), counter(43))
    assert "full Restart" in standing_of(tmp_path, row, counter(43)).reason
    assert standing_of(tmp_path, row, counter(44)).reason is None
    assert standing_of(tmp_path, row, counter(42)).reason is not None


def test_a_counter_record_stands_on_its_own_boot_and_says_when_it_does_not(tmp_path):
    row = record(NOW)
    assert_plain_restart_advice(standing_of(tmp_path, row, NOW).reason)
    assert standing_of(tmp_path, row, later_boot(NOW)).reason is None
    other = standing_of(tmp_path, row, counter(7, OTHER_GUID)).reason
    assert "--prepare-restart" in other and "environment" in other
    assert "lower" in standing_of(tmp_path, row, counter(41)).reason


def test_a_per_boot_id_record_stands_on_a_different_id(tmp_path):
    first = "linux:00000000-1111-4222-8333-444444444444"
    row = record(first)
    assert_plain_restart_advice(standing_of(tmp_path, row, first).reason)
    assert standing_of(tmp_path, row, "linux:99999999-1111-4222-8333-444444444444").reason is None


def test_a_chain_that_does_not_stand_proves_nothing_and_says_so(tmp_path):
    row = record()
    write(tmp_path, row, (), counter(43))
    rewrite(path_of(tmp_path), FORGERIES["an extra field"])
    found = standing_of(tmp_path, row, counter(44))
    assert found.chain == () and "do not stand" in found.reason


def test_the_newest_preparation_is_the_baseline(tmp_path):
    row = record()
    first = write(tmp_path, row, (), counter(43))
    write(tmp_path, row, (first,), counter(3, OTHER_GUID))
    assert standing_of(tmp_path, row, counter(8, GUID)).reason is not None
    assert standing_of(tmp_path, row, counter(4, OTHER_GUID)).reason is None
    assert prepared.baseline(LEGACY_SAME_MACHINE, chain_of(tmp_path, row)) == counter(3, OTHER_GUID)
    assert prepared.baseline(LEGACY_SAME_MACHINE, ()) == LEGACY_SAME_MACHINE


# -- when a preparation may be written ---------------------------------------------------------

def test_the_decision_to_prepare_is_the_one_the_project_and_the_login_use(tmp_path):
    assert prepared.decide(LEGACY_OTHER, (), counter(43)) is True
    assert prepared.decide(NOW, (), counter(7, OTHER_GUID)) is True
    row = record()
    first = write(tmp_path, row, (), counter(43))
    assert prepared.decide(LEGACY_SAME_MACHINE, (first,), counter(90)) is False
    assert prepared.decide(LEGACY_SAME_MACHINE, (first,), counter(7, OTHER_GUID)) is True
    for refused_boot, code in ((NOW, "same_boot"), (counter(41), "counter_decreased")):
        with pytest.raises(BootRefused) as caught:
            prepared.decide(NOW, (), refused_boot)
        assert caught.value.code == code
    with pytest.raises(BootRefused) as caught:
        prepared.decide(NOW, (), later_boot(NOW))
    assert caught.value.code == "preparation_unneeded"
    with pytest.raises(BootRefused) as caught:
        prepared.decide("linux:00000000-1111-4222-8333-444444444444", (), counter(43))
    assert caught.value.code == "preparation_unneeded"


# -- the objects the newest preparation held ---------------------------------------------------

def test_an_object_that_exists_now_but_was_not_held_is_named(tmp_path):
    row = record()
    first = write(tmp_path, row, (), counter(43), held={"parent": [1, 2], "work": None})
    assert prepared.appeared((first,), HELD, ("parent", "work")) == ("work",)
    assert prepared.appeared((first,), HELD, ("parent",)) == ()
    assert prepared.appeared((), HELD, ("parent", "work")) == ()


def test_the_closed_codes_the_module_leans_on_exist():
    assert {"legacy_value", "other_scope", "preparation_unneeded"} <= boot_witness.CODES
