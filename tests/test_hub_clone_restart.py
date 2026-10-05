"""The hub's clone attempts are cleaned up only for a restart the journal has proof of (H-R1).

`Clones.recover()` used to remove an unfinished clone folder when the old class-90 string of its
record was merely unequal to the string measured now. That is no proof: a record that holds the
old string, read by a reader that now answers a counter witness, is unequal on the very same boot.
Now a record from before the counter needs an explicit preparation, bound to the record and to the
folder and its parent, and then a restart the counter proves. Starting the hub, or `recover()`,
never writes it.

Every restart is a model (`ownership_boot.current_boot` is the seam). No `gh`, no network.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
from types import SimpleNamespace

import pytest

from conductor import ownership_native, ownership_records as records
from conductor.boot_witness import BootRefused
from conductor.hub import clone, project_targets
from tests._boot_world import (OTHER_GUID, assert_plain_restart_advice, counter, later_boot,
                               measure)
from tests._prepared_world import (DAMAGE, FORGERIES, LEGACY_OTHER, LEGACY_SAME_MACHINE,
                                   LEGACY_TEXTS, STANDING_ENVIRONMENT, THIRD_GUID, damage, read,
                                   rewrite, tree)
from tests.test_hub_clone import Finished, Group, bound  # noqa: F401
from tests.test_hub_http_surface import stack  # noqa: F401

NOW = counter(42)
PER_BOOT = "linux:00000000-1111-4222-8333-444444444444"


def crashed(home, monkeypatch, boot, *, legacy=None, folder="app", phase="running"):
    """A clone attempt whose hub died: the record on disk, the folder made, no process left.

    `boot` is what the machine measured while the attempt ran; `legacy` writes the record the way
    the build before the boot counter did (schema 1, the old string).
    """
    measure(monkeypatch, boot)
    ticket = project_targets.ticket(home, folder)
    target, _ = project_targets.create(home, folder, expected=ticket)
    (target / "partial").write_bytes(b"half a clone")
    ident = "operation-" + secrets.token_hex(16)
    text = boot if legacy is None else legacy
    row = {"schema": 1 if legacy or not boot.startswith("windows-bootid") else 2,
           "operation_id": ident, "repo": "owner/app", "path": str(ticket.path),
           "ancestors": [[str(path), list(found)] for path, found in ticket.ancestors],
           "parent_identity": list(ownership_native.identity(target.parent)),
           "target_identity": list(ownership_native.identity(target)),
           "boot": text, "phase": phase}
    clone.Clones(home)._journal.write_new(row)
    record = home / "clone-attempts" / f"{ident}.json"
    return SimpleNamespace(home=home, ident=ident, target=target, record=record,
                           cloner=clone.Clones(home))


def refused(call, *args):
    with pytest.raises(clone.CloneFailed) as caught:
        call(*args)
    return caught.value


def said(error):
    return " ".join(error.stderr)


def prep_path(world, index=0):
    return world.record.with_name(f"{world.record.stem}.prepared-{index}.json")


def cleaned(world):
    return not world.target.exists() and read(world.record)["phase"] == "cleaned"


def untouched(world):
    return (world.target / "partial").read_bytes() == b"half a clone"


def legacy_in_a(home, monkeypatch, legacy=LEGACY_SAME_MACHINE):
    return crashed(home, monkeypatch, NOW, legacy=legacy)


def counter_of_a(home, monkeypatch):
    return crashed(home, monkeypatch, NOW)


# -- what a new record holds ------------------------------------------------------------------

def a_finished_clone(home, ticket):
    def launch(argv, **options):
        (ticket.path / ".git").mkdir()
        return Finished()
    return clone.Clones(home, popen=launch, make_group=Group)


@pytest.mark.parametrize(("boot", "schema"), [(NOW, 2), (PER_BOOT, 1)],
                         ids=["counter", "per-boot-id"])
def test_a_new_record_holds_the_measurement_of_its_boot_and_the_schema_that_fits_it(
        bound, monkeypatch, boot, schema):  # noqa: F811
    home, ticket = bound
    measure(monkeypatch, boot)
    ident = "operation-" + "a" * 32
    a_finished_clone(home, ticket).clone(ident, "owner/app", ticket)
    row = read(home / "clone-attempts" / f"{ident}.json")
    assert row["boot"] == boot and row["schema"] == schema and row["phase"] == "cloned"


def test_a_clone_does_not_start_when_the_boot_cannot_be_measured(bound, monkeypatch):  # noqa: F811
    home, ticket = bound

    def unreadable():
        raise BootRefused("layout_unknown", "the page is not the documented layout")

    measure(monkeypatch, unreadable)
    cloner = clone.Clones(home, popen=lambda *_a, **_k: pytest.fail("gh spawned"))
    error = refused(cloner.clone, "operation-" + "b" * 32, "owner/app", ticket)
    assert error.code == "clone_failed" and "documented layout" in said(error)
    assert not (home / "clone-attempts").exists() and not ticket.path.exists()


def test_a_boot_text_that_proves_no_restart_is_never_written_into_a_new_record(
        bound, monkeypatch):  # noqa: F811
    home, ticket = bound
    measure(monkeypatch, LEGACY_OTHER)
    cloner = clone.Clones(home, popen=lambda *_a, **_k: pytest.fail("gh spawned"))
    error = refused(cloner.clone, "operation-" + "c" * 32, "owner/app", ticket)
    assert "cannot prove a restart" in said(error)
    assert not (home / "clone-attempts").exists() and not ticket.path.exists()


# -- a record from before the counter: no permission without an explicit preparation ----------

@pytest.mark.parametrize("legacy", LEGACY_TEXTS, ids=["same-machine", "another-string"])
def test_a_legacy_record_met_in_a_counter_boot_is_not_cleaned_up_whatever_the_strings_say(
        bound, monkeypatch, legacy):  # noqa: F811
    world = legacy_in_a(bound[0], monkeypatch, legacy)
    measure(monkeypatch, NOW)
    before = tree(world.home)
    assert world.cloner.recover() == (world.ident,)
    action = world.cloner.unfinished[world.ident]
    assert "--prepare-restart" in action and "recover-clones" in action
    assert untouched(world) and read(world.record)["phase"] == "running"
    assert tree(world.home) == before


@pytest.mark.parametrize("legacy", LEGACY_TEXTS, ids=["same-machine", "another-string"])
def test_a_legacy_record_is_not_cleaned_up_after_a_restart_either_until_it_is_prepared(
        bound, monkeypatch, legacy):  # noqa: F811
    world = legacy_in_a(bound[0], monkeypatch, legacy)
    measure(monkeypatch, later_boot(NOW))
    assert world.cloner.recover() == (world.ident,)
    assert "--prepare-restart" in world.cloner.unfinished[world.ident] and untouched(world)


def test_starting_a_recovery_never_writes_a_preparation(bound, monkeypatch):  # noqa: F811
    world = legacy_in_a(bound[0], monkeypatch)
    before = tree(world.home)
    for boot in (NOW, later_boot(NOW), counter(7, OTHER_GUID)):
        measure(monkeypatch, boot)
        assert world.cloner.recover() == (world.ident,)
    assert tree(world.home) == before and not prep_path(world).exists()


def test_the_hub_start_leaves_an_unproven_clone_unfinished_and_writes_nothing(
        stack, monkeypatch, tmp_path_factory):  # noqa: F811
    personal = tmp_path_factory.mktemp("hstart")          # short: Windows limits the projects home
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: personal))
    home = stack.service._home
    world = crashed(home, monkeypatch, NOW, legacy=LEGACY_OTHER)
    before = tree(home / "clone-attempts")
    stack.service.start()
    assert stack.service._clone_recovery == (world.ident,)
    assert untouched(world) and tree(home / "clone-attempts") == before


def started_over_an_unproven_clone(stack, monkeypatch, tmp_path_factory):  # noqa: F811
    personal = tmp_path_factory.mktemp("hlog")            # short: Windows limits the projects home
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: personal))
    world = crashed(stack.service._home, monkeypatch, NOW, legacy=LEGACY_OTHER)
    stack.service.start()
    return world


def test_the_hub_start_names_each_unfinished_clone_and_the_command_that_finishes_it_in_its_log(
        stack, monkeypatch, tmp_path_factory, capsys):  # noqa: F811
    world = started_over_an_unproven_clone(stack, monkeypatch, tmp_path_factory)
    lines = capsys.readouterr().err.splitlines()
    [named] = [line for line in lines if world.ident in line]
    assert named.startswith("conduct hub: ") and "unfinished" in named
    assert " ".join(stack.service._clones.unfinished[world.ident].split()) in named
    assert any("stop the hub" in line and "conduct ownership recover-clones" in line
               and "--prepare-restart" in line for line in lines), lines


def test_the_hub_start_says_so_in_its_log_when_the_clone_journal_cannot_be_read(
        stack, monkeypatch, capsys):  # noqa: F811
    def unreadable():
        raise clone.CloneFailed("clone_cleanup_incomplete",
                                stderr=("a record of the clone journal cannot be read",))

    monkeypatch.setattr(stack.service._clones, "recover", unreadable)
    stack.service.start()
    assert stack.service._clone_recovery == (None,)
    lines = capsys.readouterr().err.splitlines()
    assert any("a record of the clone journal cannot be read" in line for line in lines), lines
    assert any("conduct ownership recover-clones" in line for line in lines), lines


def test_the_hub_start_says_nothing_about_clones_when_none_is_unfinished(
        stack, capsys):  # noqa: F811
    stack.service.start()
    assert stack.service._clone_recovery == () and capsys.readouterr().err == ""


def test_the_proof_that_the_own_group_ended_still_cleans_up_at_once(
        bound, monkeypatch):  # noqa: F811
    home, ticket = bound
    measure(monkeypatch, NOW)
    cloner = clone.Clones(home)

    def failed(_ident, _repo, path, _row):
        (path / "half").write_bytes(b"x")
        raise clone.CloneFailed("clone_failed")

    cloner._run = failed
    ident = "operation-" + "e" * 32
    with pytest.raises(clone.CloneFailed, match="clone_failed"):
        cloner.clone(ident, "owner/app", ticket)
    assert not ticket.path.exists()
    assert read(home / "clone-attempts" / f"{ident}.json")["phase"] == "cleaned"


class StuckGroup(Group):
    def retired(self, *, timeout):
        return False


def test_a_group_that_is_not_proven_gone_keeps_the_folder_until_a_restart_is_proven(
        bound, monkeypatch):  # noqa: F811
    home, ticket = bound
    measure(monkeypatch, NOW)
    cloner = clone.Clones(home, popen=lambda *_a, **_k: Finished(), make_group=StuckGroup)
    ident = "operation-" + "f" * 32
    error = refused(cloner.clone, ident, "owner/app", ticket)
    assert error.code == "clone_cleanup_incomplete" and ticket.path.exists()
    record = home / "clone-attempts" / f"{ident}.json"
    assert read(record)["phase"] == "cleanup_incomplete" and read(record)["boot"] == NOW
    assert clone.Clones(home).recover() == (ident,)
    assert ticket.path.exists()
    measure(monkeypatch, later_boot(NOW))
    assert clone.Clones(home).recover() == () and not ticket.path.exists()


# -- the explicit preparation ------------------------------------------------------------------

def test_the_explicit_preparation_is_one_new_file_bound_to_the_record_and_its_objects(
        bound, monkeypatch):  # noqa: F811
    from conductor import boot_prepared
    world = legacy_in_a(bound[0], monkeypatch)
    old = tree(world.home)
    measure(monkeypatch, counter(43))
    row, created = world.cloner.prepare_restart(world.ident)
    assert created is True and row == read(prep_path(world))
    new = tree(world.home)
    assert {name: new[name] for name in old} == old and len(new) == len(old) + 1
    record = read(world.record)
    assert row["protocol"] == boot_prepared.PROTOCOL and row["kind"] == "clone-attempt"
    assert row["subject"] == world.ident and row["sequence"] == 0
    assert row["previous_digest"] is None and row["prepared_boot"] == counter(43)
    assert row["record_digest"] == boot_prepared.record_digest(record)
    assert row["record_boot"] == LEGACY_SAME_MACHINE
    assert row["held"] == {"target": record["target_identity"],
                           "parent": record["parent_identity"]}


def test_a_prepared_record_is_not_cleaned_up_before_a_restart_and_is_after_one(
        bound, monkeypatch):  # noqa: F811
    world = legacy_in_a(bound[0], monkeypatch)
    measure(monkeypatch, counter(43))
    world.cloner.prepare_restart(world.ident)
    assert world.cloner.recover() == (world.ident,)
    assert_plain_restart_advice(world.cloner.unfinished[world.ident])
    assert untouched(world)
    measure(monkeypatch, counter(44))
    assert world.cloner.recover() == () and cleaned(world)
    assert read(prep_path(world))["prepared_boot"] == counter(43)


def test_a_repeated_preparation_in_the_same_environment_returns_the_first_and_moves_nothing(
        bound, monkeypatch):  # noqa: F811
    world = legacy_in_a(bound[0], monkeypatch)
    measure(monkeypatch, counter(43))
    first, _ = world.cloner.prepare_restart(world.ident)
    before = tree(world.home)
    measure(monkeypatch, counter(90))
    again, created = world.cloner.prepare_restart(world.ident)
    assert created is False and again == first and tree(world.home) == before


def test_a_counter_record_in_its_own_boot_needs_no_preparation_and_none_is_written(
        bound, monkeypatch):  # noqa: F811
    world = counter_of_a(bound[0], monkeypatch)
    before = tree(world.home)
    measure(monkeypatch, NOW)
    error = refused(world.cloner.prepare_restart, world.ident)
    assert "no preparation is needed" in said(error) and "full Restart" in said(error)
    measure(monkeypatch, later_boot(NOW))
    error = refused(world.cloner.prepare_restart, world.ident)
    assert "no preparation is needed" in said(error) and "recover-clones" in said(error)
    assert tree(world.home) == before


def test_a_counter_record_in_its_own_boot_stays_unfinished_and_after_a_restart_is_cleaned_up(
        bound, monkeypatch):  # noqa: F811
    world = counter_of_a(bound[0], monkeypatch)
    measure(monkeypatch, NOW)
    assert world.cloner.recover() == (world.ident,)
    assert_plain_restart_advice(world.cloner.unfinished[world.ident])
    measure(monkeypatch, later_boot(NOW))
    assert world.cloner.recover() == () and cleaned(world)
    assert not prep_path(world).exists()


def test_a_per_boot_id_record_needs_no_preparation_and_is_cleaned_up_once_the_id_differs(
        bound, monkeypatch):  # noqa: F811
    world = crashed(bound[0], monkeypatch, PER_BOOT)
    measure(monkeypatch, counter(43))
    assert "no preparation is needed" in said(refused(world.cloner.prepare_restart, world.ident))
    measure(monkeypatch, PER_BOOT)
    assert world.cloner.recover() == (world.ident,)
    measure(monkeypatch, "linux:99999999-1111-4222-8333-444444444444")
    assert world.cloner.recover() == () and cleaned(world)
    assert not prep_path(world).exists()


def test_an_unreadable_boot_prepares_nothing_and_cleans_nothing(bound, monkeypatch):  # noqa: F811
    world = legacy_in_a(bound[0], monkeypatch)
    before = tree(world.home)

    def unreadable():
        raise BootRefused("native_unavailable", "the page cannot be read")

    measure(monkeypatch, unreadable)
    assert "cannot be measured" in said(refused(world.cloner.prepare_restart, world.ident))
    assert world.cloner.recover() == (world.ident,)
    assert "cannot be measured" in world.cloner.unfinished[world.ident]
    assert tree(world.home) == before and untouched(world)


def test_a_finished_attempt_has_nothing_to_prepare(bound, monkeypatch):  # noqa: F811
    world = legacy_in_a(bound[0], monkeypatch)
    measure(monkeypatch, counter(43))
    rewrite(world.record, lambda row: row.update(phase="cloned"))
    before = tree(world.home)
    assert "nothing to prepare" in said(refused(world.cloner.prepare_restart, world.ident))
    assert tree(world.home) == before


# -- another boot environment (the exit of review ruling H-R2, for this journal) ----------------

def test_a_counter_record_met_in_another_environment_names_the_explicit_action(
        bound, monkeypatch):  # noqa: F811
    world = counter_of_a(bound[0], monkeypatch)
    measure(monkeypatch, counter(7, OTHER_GUID))
    before = tree(world.home)
    assert world.cloner.recover() == (world.ident,)
    action = world.cloner.unfinished[world.ident]
    assert "--prepare-restart" in action and "environment" in action
    assert "no preparation is needed" not in action
    assert untouched(world) and tree(world.home) == before


def test_the_exit_from_another_environment_is_a_new_preparation_then_a_restart_inside_it(
        bound, monkeypatch):  # noqa: F811
    world = counter_of_a(bound[0], monkeypatch)
    measure(monkeypatch, counter(7, OTHER_GUID))
    row, created = world.cloner.prepare_restart(world.ident)
    assert created and row["record_boot"] == NOW and row["prepared_boot"] == counter(7, OTHER_GUID)
    assert world.cloner.recover() == (world.ident,)
    assert_plain_restart_advice(world.cloner.unfinished[world.ident])
    measure(monkeypatch, counter(8, OTHER_GUID))
    assert world.cloner.recover() == () and cleaned(world)


def test_a_second_change_of_environment_adds_a_preparation_that_binds_the_first(
        bound, monkeypatch):  # noqa: F811
    world = legacy_in_a(bound[0], monkeypatch)
    measure(monkeypatch, counter(7, OTHER_GUID))
    first, _ = world.cloner.prepare_restart(world.ident)
    measure(monkeypatch, counter(3, THIRD_GUID))
    assert world.cloner.recover() == (world.ident,)
    assert "--prepare-restart" in world.cloner.unfinished[world.ident]
    second, created = world.cloner.prepare_restart(world.ident)
    assert created and second["sequence"] == 1
    assert second["previous_digest"] == records.digest(records.canonical(first))
    assert read(prep_path(world, 0)) == first
    measure(monkeypatch, counter(4, THIRD_GUID))
    assert world.cloner.recover() == () and cleaned(world)


def test_recovery_stands_on_the_newest_preparation_not_on_the_first(
        bound, monkeypatch):  # noqa: F811
    world = legacy_in_a(bound[0], monkeypatch)
    measure(monkeypatch, counter(7, OTHER_GUID))
    world.cloner.prepare_restart(world.ident)
    measure(monkeypatch, counter(3, THIRD_GUID))
    world.cloner.prepare_restart(world.ident)
    measure(monkeypatch, counter(8, OTHER_GUID))   # greater than the first, another environment
    assert world.cloner.recover() == (world.ident,)
    assert "environment" in world.cloner.unfinished[world.ident] and untouched(world)


# -- forged, damaged and foreign preparations grant nothing -------------------------------------

def prepared_legacy(home, monkeypatch, folder="app"):
    world = crashed(home, monkeypatch, NOW, legacy=LEGACY_SAME_MACHINE, folder=folder)
    measure(monkeypatch, counter(43))
    world.cloner.prepare_restart(world.ident)
    measure(monkeypatch, counter(44))
    return world


@pytest.mark.parametrize("name", sorted(FORGERIES))
def test_a_preparation_with_one_forged_field_grants_nothing_and_is_not_overwritten(
        bound, monkeypatch, name):  # noqa: F811
    home = bound[0]
    if name == STANDING_ENVIRONMENT:
        world = counter_of_a(home, monkeypatch)
        measure(monkeypatch, counter(7, OTHER_GUID))
        world.cloner.prepare_restart(world.ident)
        measure(monkeypatch, counter(8, OTHER_GUID))
    else:
        world = prepared_legacy(home, monkeypatch)
    rewrite(prep_path(world), FORGERIES[name])
    before = tree(world.home)
    assert world.cloner.recover() == (world.ident,)
    assert "do not stand" in world.cloner.unfinished[world.ident]
    error = refused(world.cloner.prepare_restart, world.ident)
    assert error.code == "clone_cleanup_incomplete" and "do not stand" in said(error)
    assert untouched(world) and tree(world.home) == before


@pytest.mark.parametrize("how", DAMAGE)
def test_a_damaged_preparation_grants_nothing_and_is_kept(bound, monkeypatch, how):  # noqa: F811
    world = prepared_legacy(bound[0], monkeypatch)
    damage(prep_path(world), how)
    before = tree(world.home)
    assert world.cloner.recover() == (world.ident,)
    assert "do not stand" in world.cloner.unfinished[world.ident] and untouched(world)
    assert tree(world.home) == before


def test_a_stray_name_of_the_record_and_a_gap_in_the_numbering_grant_nothing(
        bound, monkeypatch):  # noqa: F811
    world = prepared_legacy(bound[0], monkeypatch)
    stray = world.record.with_name(f"{world.record.stem}.prepared-x.json")
    stray.write_bytes(b"{}")
    assert world.cloner.recover() == (world.ident,)
    assert "do not stand" in world.cloner.unfinished[world.ident]
    stray.unlink()
    prep_path(world).rename(prep_path(world, 2))
    assert world.cloner.recover() == (world.ident,)
    assert "whole sequence" in world.cloner.unfinished[world.ident] and untouched(world)


def test_a_preparation_copied_from_another_attempt_grants_nothing(bound, monkeypatch):  # noqa: F811
    home = bound[0]
    other = prepared_legacy(home, monkeypatch, folder="app2")
    world = legacy_in_a(home, monkeypatch)
    measure(monkeypatch, counter(44))
    prep_path(world).write_bytes(prep_path(other).read_bytes())
    assert world.cloner.recover() == (world.ident,)   # the other attempt stands and is cleaned
    assert "do not stand" in world.cloner.unfinished[world.ident] and untouched(world)


def test_a_record_changed_after_its_preparation_grants_nothing(bound, monkeypatch):  # noqa: F811
    world = prepared_legacy(bound[0], monkeypatch)
    rewrite(world.record, lambda row: row.update(repo="owner/other"))
    assert world.cloner.recover() == (world.ident,)
    assert "do not stand" in world.cloner.unfinished[world.ident] and untouched(world)


def test_the_phase_alone_is_not_a_change_of_the_record_the_preparation_is_bound_to(
        bound, monkeypatch):  # noqa: F811
    world = prepared_legacy(bound[0], monkeypatch)
    rewrite(world.record, lambda row: row.update(phase="cleanup_incomplete"))
    assert world.cloner.recover() == () and cleaned(world)


def test_an_object_that_was_absent_when_the_preparation_was_made_blocks_the_cleanup(
        bound, monkeypatch):  # noqa: F811
    world = prepared_legacy(bound[0], monkeypatch)
    rewrite(prep_path(world), lambda row: row["held"].update(target=None))
    assert world.cloner.recover() == (world.ident,)
    assert "appeared" in world.cloner.unfinished[world.ident] and untouched(world)


def test_a_failed_removal_after_a_proven_restart_keeps_the_preparation_valid(
        bound, monkeypatch, tmp_path):  # noqa: F811
    world = prepared_legacy(bound[0], monkeypatch)
    foreign = tmp_path / "foreign-file"
    foreign.write_bytes(b"keep")
    os.link(foreign, world.target / "alias")
    assert world.cloner.recover() == (world.ident,)
    assert read(world.record)["phase"] == "cleanup_incomplete" and foreign.read_bytes() == b"keep"
    (world.target / "alias").unlink()
    assert world.cloner.recover() == () and cleaned(world)


# -- changed objects ----------------------------------------------------------------------------

def replace_target(world):
    world.target.rename(world.target.with_name("moved-owned"))
    world.target.mkdir()
    (world.target / "foreign").write_bytes(b"keep")


def test_a_folder_replaced_before_the_preparation_is_not_prepared(bound, monkeypatch):  # noqa: F811
    world = legacy_in_a(bound[0], monkeypatch)
    replace_target(world)
    measure(monkeypatch, counter(43))
    before = tree(world.home)
    error = refused(world.cloner.prepare_restart, world.ident)
    assert error.code == "clone_cleanup_incomplete" and tree(world.home) == before


def test_a_folder_replaced_after_the_preparation_is_not_cleaned_up(
        bound, monkeypatch):  # noqa: F811
    world = prepared_legacy(bound[0], monkeypatch)
    replace_target(world)
    assert world.cloner.recover() == (world.ident,)
    assert (world.target / "foreign").read_bytes() == b"keep"
    assert read(world.record)["phase"] == "cleanup_incomplete"


def test_a_folder_replaced_between_the_check_and_the_hold_is_not_prepared(
        bound, monkeypatch):  # noqa: F811
    world = legacy_in_a(bound[0], monkeypatch)
    measure(monkeypatch, counter(43))
    real = ownership_native.NativeHold
    raced = []

    def swapping(path, **options):
        if Path(path) == world.target and not raced:     # the race, forced at the one moment
            raced.append(path)
            replace_target(world)
        return real(path, **options)

    monkeypatch.setattr(ownership_native, "NativeHold", swapping)
    before = tree(world.home)
    error = refused(world.cloner.prepare_restart, world.ident)
    assert raced and error.code == "clone_cleanup_incomplete"
    assert "not the one the record names" in said(error)
    assert tree(world.home) == before and not prep_path(world).exists()


def test_a_folder_outside_the_admitted_projects_home_is_not_prepared_and_not_cleaned_up(
        bound, monkeypatch, tmp_path):  # noqa: F811
    home = bound[0]
    world = legacy_in_a(home, monkeypatch)
    outside = tmp_path / "elsewhere" / "app"
    outside.mkdir(parents=True)
    (outside / "partial").write_bytes(b"half a clone")
    rewrite(world.record, lambda row: row.update(
        path=str(outside), target_identity=list(ownership_native.identity(outside)),
        parent_identity=list(ownership_native.identity(outside.parent))))
    measure(monkeypatch, counter(43))
    before = tree(world.home)
    error = refused(world.cloner.prepare_restart, world.ident)
    assert error.code == "clone_cleanup_incomplete" and tree(world.home) == before
    assert (outside / "partial").read_bytes() == b"half a clone"


def test_recovery_reads_only_the_names_of_records_and_leaves_finished_ones_alone(
        bound, monkeypatch):  # noqa: F811
    world = prepared_legacy(bound[0], monkeypatch)
    assert world.cloner.recover() == () and cleaned(world)
    assert prep_path(world).is_file()
    assert world.cloner.recover() == () and world.cloner.unfinished == {}
