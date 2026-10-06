"""The attempt ACL journal grants cleanup only for a restart it has proof of (review ruling H-R1).

Before this slice `retire(after_restart=True)` granted the clean-up by the INEQUALITY of two old
class-90 strings, and `recover()` called it for every record on its own. A record that holds the old
string, met by a reader that now answers a counter witness, would then be unequal on the very same
boot: a false permission. Now a record from before the counter needs an explicit preparation, bound
to the record and to the four objects the loan names, and then a restart that the counter proves.
Starting a recovery never writes that preparation.

Every restart is a model (`ownership_boot.current_boot` is the seam); nothing here touches an ACL.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from conductor import ownership_records as records
from conductor.boot_witness import BootRefused
from conductor.command.adapters.process_acl import AttemptAclJournal
from conductor.command.adapters.process_profile import ProfileRefused
from tests._boot_world import (OTHER_GUID, assert_plain_restart_advice, counter, later_boot,
                               measure)
from tests._prepared_world import (DAMAGE, FORGERIES, LEGACY_OTHER, LEGACY_SAME_MACHINE,
                                   LEGACY_TEXTS, STANDING_ENVIRONMENT, THIRD_GUID, damage, read,
                                   rewrite, tree)
from tests.test_process_acl import fixture

NOW = counter(42)
KEYS = ("parent", "work", "runtime", "login")


def written_in(tmp_path, monkeypatch, boot, *, legacy=None):
    """An applied attempt, then 'the owner died': a fresh journal over the same files.

    `boot` is what the machine measured while the attempt ran; `legacy` rewrites the record the way
    the build before the boot counter wrote it (schema 1, the old string).
    """
    measure(monkeypatch, boot)
    store, acl, profile_path, sid, state = fixture(tmp_path)
    record, paths = acl.prepare(profile_path, sid, "dispatch")
    if legacy is not None:
        rewrite(record, lambda row: row.update(schema=1, boot=legacy))
    journal = AttemptAclJournal(store, store.native, hold_factory=acl.hold_factory)
    return SimpleNamespace(store=store, journal=journal, record=record, paths=paths,
                           state=state, factory=acl.hold_factory)


def refused(call, *args, **options):
    with pytest.raises(ProfileRefused) as caught:
        call(*args, **options)
    return caught.value


def prep_path(world, index=0):
    return world.record.with_name(f"{world.record.stem}.prepared-{index}.json")


def cleaned(world):
    return not world.paths["parent"].exists() and read(world.record)["phase"] == "retired"


def untouched(world):
    return all(path.exists() for path in world.paths.values())


def legacy_in_a(tmp_path, monkeypatch, legacy=LEGACY_SAME_MACHINE):
    return written_in(tmp_path, monkeypatch, NOW, legacy=legacy)


def counter_of_a(tmp_path, monkeypatch):
    return written_in(tmp_path, monkeypatch, NOW)


# -- what a new record holds ------------------------------------------------------------------

@pytest.mark.parametrize(("boot", "schema"), [
    (NOW, 2), ("linux:00000000-1111-4222-8333-444444444444", 1)], ids=["counter", "per-boot-id"])
def test_a_new_record_holds_the_measurement_of_its_boot_and_the_schema_that_fits_it(
        tmp_path, monkeypatch, boot, schema):
    world = written_in(tmp_path, monkeypatch, boot)
    row = read(world.record)
    assert row["boot"] == boot and row["schema"] == schema


def test_an_attempt_is_not_recorded_when_the_boot_cannot_be_measured(tmp_path, monkeypatch):
    def unreadable():
        raise BootRefused("layout_unknown", "the page is not the documented layout")

    measure(monkeypatch, NOW)
    store, acl, profile_path, sid, state = fixture(tmp_path)
    before = tree(tmp_path)
    measure(monkeypatch, unreadable)
    error = refused(acl.prepare, profile_path, sid, "dispatch")
    assert "cannot be measured" in str(error) and "documented layout" in str(error)
    assert tree(tmp_path) == before and state == {}


def test_a_boot_text_that_proves_no_restart_is_never_written_into_a_new_record(
        tmp_path, monkeypatch):
    measure(monkeypatch, LEGACY_OTHER)
    store, acl, profile_path, sid, state = fixture(tmp_path)
    before = tree(tmp_path)
    error = refused(acl.prepare, profile_path, sid, "dispatch")
    assert "cannot prove a restart" in str(error)
    assert tree(tmp_path) == before


# -- a record from before the counter: no permission without an explicit preparation ----------

@pytest.mark.parametrize("legacy", LEGACY_TEXTS, ids=["same-machine", "another-string"])
def test_a_legacy_record_met_in_a_counter_boot_is_not_cleaned_up_whatever_the_strings_say(
        tmp_path, monkeypatch, legacy):
    world = legacy_in_a(tmp_path, monkeypatch, legacy)
    measure(monkeypatch, NOW)
    before = tree(tmp_path)
    error = refused(world.journal.recover)
    assert error.code == "profile_acl_unproven"
    assert "--prepare-restart" in str(error) and "recover-containers" in str(error)
    assert untouched(world) and read(world.record)["phase"] == "applied"
    assert tree(tmp_path) == before


@pytest.mark.parametrize("legacy", LEGACY_TEXTS, ids=["same-machine", "another-string"])
def test_a_legacy_record_is_not_cleaned_up_after_a_restart_either_until_it_is_prepared(
        tmp_path, monkeypatch, legacy):
    world = legacy_in_a(tmp_path, monkeypatch, legacy)
    measure(monkeypatch, later_boot(NOW))
    error = refused(world.journal.recover)
    assert "--prepare-restart" in str(error)
    assert untouched(world)


def test_starting_a_recovery_never_writes_a_preparation(tmp_path, monkeypatch):
    world = legacy_in_a(tmp_path, monkeypatch)
    before = tree(tmp_path)
    for boot in (NOW, later_boot(NOW), counter(7, OTHER_GUID)):
        measure(monkeypatch, boot)
        refused(world.journal.recover)
        refused(world.journal.retire, world.record, after_restart=True)
    assert tree(tmp_path) == before and not prep_path(world).exists()


def test_the_proof_that_the_own_process_group_ended_still_retires_an_old_record(
        tmp_path, monkeypatch):
    world = legacy_in_a(tmp_path, monkeypatch)
    measure(monkeypatch, NOW)
    world.journal.retire(world.record, proven=True)
    assert cleaned(world) and not prep_path(world).exists()


def test_without_the_proof_and_without_the_restart_flag_the_loan_stays(tmp_path, monkeypatch):
    world = counter_of_a(tmp_path, monkeypatch)
    error = refused(world.journal.retire, world.record)
    assert error.code == "profile_acl_unproven" and untouched(world)


# -- the explicit preparation ------------------------------------------------------------------

def test_the_explicit_preparation_is_one_new_file_bound_to_the_record_and_its_objects(
        tmp_path, monkeypatch):
    from conductor import boot_prepared
    world = legacy_in_a(tmp_path, monkeypatch)
    old = tree(tmp_path)
    measure(monkeypatch, counter(43))
    row, created = world.journal.prepare_restart(world.record)
    assert created is True and row == read(prep_path(world))
    new = tree(tmp_path)
    assert {name: new[name] for name in old} == old and len(new) == len(old) + 1
    record = read(world.record)
    assert row["protocol"] == boot_prepared.PROTOCOL and row["kind"] == "acl-attempt"
    assert row["subject"] == record["attempt"] and row["sequence"] == 0
    assert row["previous_digest"] is None and row["prepared_boot"] == counter(43)
    assert row["record_digest"] == boot_prepared.record_digest(record)
    assert row["record_boot"] == LEGACY_SAME_MACHINE
    assert row["held"] == {key: record["paths"][key]["identity"] for key in KEYS}


def test_a_prepared_record_is_not_cleaned_up_before_a_restart_and_is_after_one(
        tmp_path, monkeypatch):
    world = legacy_in_a(tmp_path, monkeypatch)
    measure(monkeypatch, counter(43))
    world.journal.prepare_restart(world.record)
    error = refused(world.journal.recover)
    assert_plain_restart_advice(str(error))
    assert untouched(world)
    measure(monkeypatch, counter(44))
    world.journal.recover()
    assert cleaned(world) and read(prep_path(world))["prepared_boot"] == counter(43)


def test_a_repeated_preparation_in_the_same_environment_returns_the_first_and_moves_nothing(
        tmp_path, monkeypatch):
    world = legacy_in_a(tmp_path, monkeypatch)
    measure(monkeypatch, counter(43))
    first, _ = world.journal.prepare_restart(world.record)
    before = tree(tmp_path)
    measure(monkeypatch, counter(90))
    again, created = world.journal.prepare_restart(world.record)
    assert created is False and again == first and tree(tmp_path) == before


def test_a_counter_record_in_its_own_boot_needs_no_preparation_and_none_is_written(
        tmp_path, monkeypatch):
    world = counter_of_a(tmp_path, monkeypatch)
    before = tree(tmp_path)
    measure(monkeypatch, NOW)
    error = refused(world.journal.prepare_restart, world.record)
    assert "no preparation is needed" in str(error) and "full Restart" in str(error)
    measure(monkeypatch, later_boot(NOW))
    error = refused(world.journal.prepare_restart, world.record)
    assert "no preparation is needed" in str(error) and "recover-containers" in str(error)
    assert tree(tmp_path) == before


def test_a_per_boot_id_record_needs_no_preparation_and_none_is_written(tmp_path, monkeypatch):
    world = written_in(tmp_path, monkeypatch, "linux:00000000-1111-4222-8333-444444444444")
    before = tree(tmp_path)
    measure(monkeypatch, counter(43))
    error = refused(world.journal.prepare_restart, world.record)
    assert "no preparation is needed" in str(error)
    assert tree(tmp_path) == before


def test_an_unreadable_boot_prepares_nothing_and_cleans_nothing(tmp_path, monkeypatch):
    world = legacy_in_a(tmp_path, monkeypatch)
    before = tree(tmp_path)

    def unreadable():
        raise BootRefused("native_unavailable", "the page cannot be read")

    measure(monkeypatch, unreadable)
    assert "cannot be measured" in str(refused(world.journal.prepare_restart, world.record))
    assert "cannot be measured" in str(refused(world.journal.recover))
    assert tree(tmp_path) == before and untouched(world)


def test_the_preparation_holds_the_four_objects_before_it_writes(tmp_path, monkeypatch):
    world = legacy_in_a(tmp_path, monkeypatch)
    asked = []

    def spying(path, **options):
        asked.append((path, options))
        return world.factory(path, **options)

    watched = AttemptAclJournal(world.store, world.store.native, hold_factory=spying)
    measure(monkeypatch, counter(43))
    watched.prepare_restart(world.record)
    assert sorted(str(path) for path, _ in asked) == sorted(
        str(path) for path in world.paths.values())
    assert all(options == {"directory": True, "security": True} for _, options in asked)


def test_a_retired_attempt_has_nothing_to_prepare(tmp_path, monkeypatch):
    world = legacy_in_a(tmp_path, monkeypatch)
    world.journal.retire(world.record, proven=True)
    measure(monkeypatch, counter(43))
    before = tree(tmp_path)
    assert "nothing to prepare" in str(refused(world.journal.prepare_restart, world.record))
    assert tree(tmp_path) == before


# -- another boot environment (the exit of review ruling H-R2, for this journal) ----------------

def test_a_counter_record_met_in_another_environment_names_the_explicit_action(
        tmp_path, monkeypatch):
    world = counter_of_a(tmp_path, monkeypatch)
    measure(monkeypatch, counter(7, OTHER_GUID))
    before = tree(tmp_path)
    error = refused(world.journal.recover)
    assert "--prepare-restart" in str(error) and "environment" in str(error)
    assert "no preparation is needed" not in str(error)
    assert untouched(world) and tree(tmp_path) == before


def test_the_exit_from_another_environment_is_a_new_preparation_then_a_restart_inside_it(
        tmp_path, monkeypatch):
    world = counter_of_a(tmp_path, monkeypatch)
    measure(monkeypatch, counter(7, OTHER_GUID))
    row, created = world.journal.prepare_restart(world.record)
    assert created and row["record_boot"] == NOW and row["prepared_boot"] == counter(7, OTHER_GUID)
    assert_plain_restart_advice(str(refused(world.journal.recover)))
    assert untouched(world)
    measure(monkeypatch, counter(8, OTHER_GUID))
    world.journal.recover()
    assert cleaned(world)


def test_a_second_change_of_environment_adds_a_preparation_that_binds_the_first(
        tmp_path, monkeypatch):
    world = legacy_in_a(tmp_path, monkeypatch)
    measure(monkeypatch, counter(7, OTHER_GUID))
    first, _ = world.journal.prepare_restart(world.record)
    measure(monkeypatch, counter(3, THIRD_GUID))
    error = refused(world.journal.recover)
    assert "--prepare-restart" in str(error) and "environment" in str(error)
    second, created = world.journal.prepare_restart(world.record)
    assert created and second["sequence"] == 1
    assert second["previous_digest"] == records.digest(records.canonical(first))
    assert read(prep_path(world, 0)) == first
    measure(monkeypatch, counter(4, THIRD_GUID))
    world.journal.recover()
    assert cleaned(world)


def test_recovery_stands_on_the_newest_preparation_not_on_the_first(tmp_path, monkeypatch):
    world = legacy_in_a(tmp_path, monkeypatch)
    measure(monkeypatch, counter(7, OTHER_GUID))
    world.journal.prepare_restart(world.record)
    measure(monkeypatch, counter(3, THIRD_GUID))
    world.journal.prepare_restart(world.record)
    measure(monkeypatch, counter(8, OTHER_GUID))   # greater than the first, another environment
    assert "environment" in str(refused(world.journal.recover)) and untouched(world)


# -- forged, damaged and foreign preparations grant nothing -------------------------------------

def prepared_legacy(tmp_path, monkeypatch):
    world = legacy_in_a(tmp_path, monkeypatch)
    measure(monkeypatch, counter(43))
    world.journal.prepare_restart(world.record)
    measure(monkeypatch, counter(44))
    return world


@pytest.mark.parametrize("name", sorted(FORGERIES))
def test_a_preparation_with_one_forged_field_grants_nothing_and_is_not_overwritten(
        tmp_path, monkeypatch, name):
    if name == STANDING_ENVIRONMENT:
        world = counter_of_a(tmp_path, monkeypatch)
        measure(monkeypatch, counter(7, OTHER_GUID))
        world.journal.prepare_restart(world.record)
        measure(monkeypatch, counter(8, OTHER_GUID))
    else:
        world = prepared_legacy(tmp_path, monkeypatch)
    rewrite(prep_path(world), FORGERIES[name])
    before = tree(tmp_path)
    error = refused(world.journal.recover)
    assert error.code == "profile_acl_unproven" and "do not stand" in str(error)
    assert refused(world.journal.prepare_restart, world.record).code == "profile_acl_unproven"
    assert untouched(world) and tree(tmp_path) == before


@pytest.mark.parametrize("how", DAMAGE)
def test_a_damaged_preparation_grants_nothing_and_is_kept(tmp_path, monkeypatch, how):
    world = prepared_legacy(tmp_path, monkeypatch)
    damage(prep_path(world), how)
    before = tree(tmp_path)
    error = refused(world.journal.recover)
    assert "do not stand" in str(error) and untouched(world)
    assert tree(tmp_path) == before


def test_a_stray_name_of_the_record_and_a_gap_in_the_numbering_grant_nothing(
        tmp_path, monkeypatch):
    world = prepared_legacy(tmp_path, monkeypatch)
    stray = world.record.with_name(f"{world.record.stem}.prepared-x.json")
    stray.write_bytes(b"{}")
    assert "do not stand" in str(refused(world.journal.recover))
    stray.unlink()
    prep_path(world).rename(prep_path(world, 2))
    assert "whole sequence" in str(refused(world.journal.recover)) and untouched(world)


def test_a_preparation_copied_from_another_attempt_grants_nothing(tmp_path, monkeypatch):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    other = prepared_legacy(tmp_path / "one", monkeypatch)
    world = legacy_in_a(tmp_path / "two", monkeypatch)
    measure(monkeypatch, counter(44))
    prep_path(world).write_bytes(prep_path(other).read_bytes())
    assert "do not stand" in str(refused(world.journal.recover)) and untouched(world)


def test_a_record_changed_after_its_preparation_grants_nothing(tmp_path, monkeypatch):
    world = prepared_legacy(tmp_path, monkeypatch)
    rewrite(world.record, lambda row: row.update(mode="review"))
    error = refused(world.journal.recover)
    assert "do not stand" in str(error) and untouched(world)


def test_the_phase_alone_is_not_a_change_of_the_record_the_preparation_is_bound_to(
        tmp_path, monkeypatch):
    world = prepared_legacy(tmp_path, monkeypatch)
    rewrite(world.record, lambda row: row.update(phase="planned"))
    world.journal.recover()
    assert cleaned(world)


def test_an_object_that_was_absent_when_the_preparation_was_made_blocks_the_cleanup(
        tmp_path, monkeypatch):
    world = prepared_legacy(tmp_path, monkeypatch)
    rewrite(prep_path(world), lambda row: row["held"].update(work=None))
    error = refused(world.journal.recover)
    assert error.code == "profile_acl_invalid" and "appeared" in str(error)
    assert untouched(world) and read(world.record)["phase"] == "applied"


# -- changed objects ----------------------------------------------------------------------------

def replace_directory(path):
    path.rename(path.with_name(path.name + "-moved"))
    path.mkdir()
    (path / "foreign").write_bytes(b"keep")


def test_a_directory_replaced_before_the_preparation_is_not_prepared(tmp_path, monkeypatch):
    world = legacy_in_a(tmp_path, monkeypatch)
    replace_directory(world.paths["work"])
    measure(monkeypatch, counter(43))
    before = tree(tmp_path)
    error = refused(world.journal.prepare_restart, world.record)
    assert error.code == "profile_acl_invalid" and tree(tmp_path) == before


def test_a_directory_replaced_after_the_preparation_is_not_cleaned_up(tmp_path, monkeypatch):
    world = prepared_legacy(tmp_path, monkeypatch)
    replace_directory(world.paths["work"])
    error = refused(world.journal.recover)
    assert error.code == "profile_acl_invalid"
    assert (world.paths["work"] / "foreign").read_bytes() == b"keep"
    assert read(world.record)["phase"] == "applied"


def test_the_old_record_names_of_the_journal_directory_are_the_only_ones_read_as_records(
        tmp_path, monkeypatch):
    world = prepared_legacy(tmp_path, monkeypatch)
    world.journal.recover()
    assert cleaned(world)
    assert prep_path(world).is_file()
    world.journal.recover()   # a retired record and its preparation: a repeat is a no-op


def test_the_profile_journal_does_not_mistake_a_preparation_for_an_unknown_entry(
        tmp_path, monkeypatch):
    world = prepared_legacy(tmp_path, monkeypatch)
    world.journal.recover()
    world.store.recover()   # the preparation is the journal's own file; the profile retires
    assert prep_path(world).is_file()


def test_the_profile_journal_still_refuses_an_entry_it_does_not_know(tmp_path, monkeypatch):
    world = legacy_in_a(tmp_path, monkeypatch)
    world.journal.retire(world.record, proven=True)
    (world.store.directory / "acl-unknown.txt").write_bytes(b"x")
    with pytest.raises(ProfileRefused, match="profile_record_invalid"):
        world.store.recover()


def test_a_per_boot_id_record_is_cleaned_up_once_the_id_differs_and_never_needs_a_preparation(
        tmp_path, monkeypatch):
    first = "linux:00000000-1111-4222-8333-444444444444"
    world = written_in(tmp_path, monkeypatch, first)
    measure(monkeypatch, first)
    assert_plain_restart_advice(str(refused(world.journal.recover)))
    measure(monkeypatch, "linux:99999999-1111-4222-8333-444444444444")
    world.journal.recover()
    assert cleaned(world) and not prep_path(world).exists()
