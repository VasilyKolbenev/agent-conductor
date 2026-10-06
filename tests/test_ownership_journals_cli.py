"""`conduct ownership recover-clones` and `recover-containers`: the explicit road for two journals.

The hub's clone attempts and a project's container attempt loans hold one boot text per record. A
record from before the boot counter needs an explicit preparation; these two operations are where a
person asks for it, with the same flag the project and the login already have (`--prepare-restart`).
A plain run is the recovery itself and never prepares. Nothing here runs a real clean-up of a real
project: the clone road works on a made-up hub folder, and the container road is driven through a
stand-in for the runner, because those journals' native side is a Windows AppContainer.
"""
from __future__ import annotations

import json
import sys
import types

import pytest

from conductor import __main__ as cli, ownership, ownership_records as records
from conductor.command import adapters
from conductor.command.adapters.process_profile import ProfileJournal, ProfileRefused
from conductor.hub import instance
from tests._boot_world import assert_plain_restart_advice, counter, later_boot, measure
from tests._prepared_world import LEGACY_OTHER, read, tree
from tests.test_hub_clone import bound  # noqa: F401
from tests.test_hub_clone_restart import (NOW, cleaned, counter_of_a, legacy_in_a, prep_path,
                                          untouched)
from tests.test_project_ownership import activated
from tests.test_project_recovery_prepare import abandoned_legacy


_NATIVE = "conductor.command.adapters._winlaunch"


def run(capsys, *argv):
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def on_hub_home(monkeypatch, home):
    monkeypatch.setenv("CONDUCT_HOME", str(home))


def snap(home):
    """Every byte of the hub folder but `hub.lock`, which the command makes to keep a hub out."""
    return {name: data for name, data in tree(home, skip=("hub.lock",)).items()
            if name != "hub.lock"}


# -- the flag -----------------------------------------------------------------------------------

@pytest.mark.parametrize("operation", ["recover-clones", "recover-containers"])
def test_the_flag_is_accepted_on_the_two_new_recoveries(operation):
    args = cli._build_parser().parse_args(["ownership", operation, "--prepare-restart"])
    assert args.operation == operation and args.prepare_restart is True


@pytest.mark.parametrize("operation", ["status", "activate", "rollback"])
def test_the_flag_is_still_refused_on_every_other_operation(tmp_path, capsys, operation):
    code, out, err = run(capsys, "ownership", operation, "--prepare-restart", "--dir",
                         str(tmp_path))
    assert code == 1 and out == "" and "only for recover" in err
    for name in ("recover-login", "recover-clones", "recover-containers"):
        assert name in err


# -- recover-clones -----------------------------------------------------------------------------

def test_a_plain_recover_clones_of_an_old_record_writes_nothing_and_names_the_next_command(
        bound, monkeypatch, capsys):  # noqa: F811
    world = legacy_in_a(bound[0], monkeypatch)
    on_hub_home(monkeypatch, world.home)
    measure(monkeypatch, counter(43))
    before = snap(world.home)
    code, out, err = run(capsys, "ownership", "recover-clones")
    result = json.loads(out)
    assert code == 1 and result["state"] == "unfinished"
    (entry,) = result["unfinished"]
    assert entry["operation_id"] == world.ident and "--prepare-restart" in entry["action"]
    assert "--prepare-restart" in err and world.ident in err
    assert untouched(world) and snap(world.home) == before


def test_the_explicit_preparation_prints_the_record_and_says_nothing_was_cleaned_up(
        bound, monkeypatch, capsys):  # noqa: F811
    world = legacy_in_a(bound[0], monkeypatch)
    on_hub_home(monkeypatch, world.home)
    measure(monkeypatch, counter(43))
    code, out, err = run(capsys, "ownership", "recover-clones", "--prepare-restart")
    result = json.loads(out)
    assert code == 0 and result["state"] == "recovery_prepared" and result["released"] is False
    (entry,) = result["records"]
    assert entry == {"operation_id": world.ident, "state": "recovery_prepared", "created": True,
                     "prepared_boot": counter(43)}
    assert prep_path(world).is_file() and untouched(world)
    assert "NOT cleaned up" in err and "Restart" in err and "recover-clones" in err


def test_a_repeated_preparation_says_it_was_already_prepared_and_writes_nothing(
        bound, monkeypatch, capsys):  # noqa: F811
    world = legacy_in_a(bound[0], monkeypatch)
    on_hub_home(monkeypatch, world.home)
    measure(monkeypatch, counter(43))
    run(capsys, "ownership", "recover-clones", "--prepare-restart")
    before = snap(world.home)
    measure(monkeypatch, counter(90))
    code, out, err = run(capsys, "ownership", "recover-clones", "--prepare-restart")
    assert code == 0 and json.loads(out)["records"][0]["created"] is False
    assert "already prepared" in err and snap(world.home) == before


def test_the_whole_road_is_prepare_restart_then_the_plain_command_through_the_cli(
        bound, monkeypatch, capsys):  # noqa: F811
    world = legacy_in_a(bound[0], monkeypatch)
    on_hub_home(monkeypatch, world.home)
    measure(monkeypatch, counter(43))
    run(capsys, "ownership", "recover-clones", "--prepare-restart")
    code, out, err = run(capsys, "ownership", "recover-clones")
    assert code == 1 and json.loads(out)["state"] == "unfinished"
    assert_plain_restart_advice(json.loads(out)["unfinished"][0]["action"])
    assert untouched(world)
    measure(monkeypatch, counter(44))
    code, out, err = run(capsys, "ownership", "recover-clones")
    assert code == 0 and json.loads(out) == {"state": "recovered", "unfinished": []}
    assert cleaned(world)


def test_a_record_that_cannot_be_prepared_is_named_and_the_exit_code_is_one(
        bound, monkeypatch, capsys):  # noqa: F811
    world = counter_of_a(bound[0], monkeypatch)
    on_hub_home(monkeypatch, world.home)
    measure(monkeypatch, NOW)
    before = snap(world.home)
    code, out, err = run(capsys, "ownership", "recover-clones", "--prepare-restart")
    result = json.loads(out)
    assert code == 1 and result["records"][0]["state"] == "not_prepared"
    assert "no preparation is needed" in result["records"][0]["action"]
    assert snap(world.home) == before and "no preparation is needed" in err


def test_a_running_hub_makes_the_command_refuse_and_write_nothing(
        bound, monkeypatch, capsys):  # noqa: F811
    world = legacy_in_a(bound[0], monkeypatch)
    on_hub_home(monkeypatch, world.home)
    measure(monkeypatch, counter(43))
    live = instance.HubInstance.acquire(world.home)
    try:
        before = snap(world.home)
        for argv in (("recover-clones",), ("recover-clones", "--prepare-restart")):
            code, out, err = run(capsys, "ownership", *argv)
            assert code == 1 and out == "" and "hub is running" in err
        assert snap(world.home) == before
    finally:
        live.close()


@pytest.mark.parametrize("argv", [("recover-clones",), ("recover-clones", "--prepare-restart")])
def test_a_journal_record_that_cannot_be_read_is_refused_in_one_line_and_nothing_changes(
        bound, monkeypatch, capsys, argv):  # noqa: F811
    world = legacy_in_a(bound[0], monkeypatch)
    on_hub_home(monkeypatch, world.home)
    # `operation-000...0` sorts before every other record, so the unreadable one is met first
    (world.home / "clone-attempts" / ("operation-" + "0" * 32 + ".json")).write_bytes(b"not json")
    measure(monkeypatch, counter(43))
    before = snap(world.home)
    code, out, err = run(capsys, "ownership", *argv)
    assert code == 1 and out == "" and err.startswith("recovery_refused: ")
    assert snap(world.home) == before and untouched(world)


def test_without_a_hub_folder_there_is_nothing_to_recover_and_nothing_is_made(
        tmp_path, monkeypatch, capsys):
    nowhere = tmp_path / "no-hub-here"
    on_hub_home(monkeypatch, nowhere)
    code, out, err = run(capsys, "ownership", "recover-clones")
    assert code == 0 and json.loads(out) == {"state": "recovered", "unfinished": []}
    assert not nowhere.exists()


def test_a_legacy_text_that_no_reader_gives_is_still_only_prepared_never_cleaned_up(
        bound, monkeypatch, capsys):  # noqa: F811
    world = legacy_in_a(bound[0], monkeypatch, LEGACY_OTHER)
    on_hub_home(monkeypatch, world.home)
    measure(monkeypatch, later_boot(NOW))
    code, out, err = run(capsys, "ownership", "recover-clones")
    assert code == 1 and untouched(world) and read(world.record)["phase"] == "running"


# -- recover-containers -------------------------------------------------------------------------

class Runner:
    """The journal the CLI opens under the owner; it records that an owner was open when asked.

    The native side (`_winlaunch`, a Windows module) is replaced by an empty module, so the same
    tests run on every OS; what the journal does with real records is witnessed in
    `test_process_acl_restart`.
    """

    def __init__(self, root, monkeypatch):
        self.root, self.calls, self.outcome = root, [], None
        monkeypatch.setitem(sys.modules, _NATIVE, types.ModuleType("fake_winlaunch"))
        monkeypatch.setattr(ProfileJournal, "for_project",
                            classmethod(lambda _cls, _root, _native: self))

    def _ask(self, name):
        ownership.require_owner(self.root)      # raises unless an owner is open
        self.calls.append(name)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome

    def recover(self):
        return self._ask("recover")

    def prepare_restarts(self):
        return self._ask("prepare")


@pytest.fixture
def project(tmp_path, monkeypatch):
    measure(monkeypatch, NOW)
    root = tmp_path / "project"
    root.mkdir()
    activated(root)
    return root


def test_a_plain_recover_containers_runs_the_runners_recovery_under_an_owner_and_closes_it(
        project, monkeypatch, capsys):
    runner = Runner(project, monkeypatch)
    code, out, err = run(capsys, "ownership", "recover-containers", "--dir", str(project))
    assert code == 0 and runner.calls == ["recover"]
    assert json.loads(out) == {"state": "recovered", "project_root": str(project.resolve())}
    assert records.chain(project)["phase"] == "closed"


def test_a_refusal_of_the_journal_is_printed_as_it_is_and_the_owner_is_closed_again(
        project, monkeypatch, capsys):
    runner = Runner(project, monkeypatch)
    runner.outcome = ProfileRefused("profile_acl_unproven", "run `ownership recover-containers "
                                    "--prepare-restart`, restart the OS, then run it again")
    code, out, err = run(capsys, "ownership", "recover-containers", "--dir", str(project))
    assert code == 1 and out == "" and "profile_acl_unproven" in err
    assert "--prepare-restart" in err and records.chain(project)["phase"] == "closed"


def test_the_explicit_preparation_lists_each_attempt_and_says_nothing_was_cleaned_up(
        project, monkeypatch, capsys):
    runner = Runner(project, monkeypatch)
    runner.outcome = [{"attempt": "a" * 32, "state": "recovery_prepared", "created": True,
                       "prepared_boot": counter(43)}]
    code, out, err = run(capsys, "ownership", "recover-containers", "--prepare-restart",
                         "--dir", str(project))
    result = json.loads(out)
    assert code == 0 and runner.calls == ["prepare"] and result["released"] is False
    assert result["state"] == "recovery_prepared" and result["records"] == runner.outcome
    assert "NOT cleaned up" in err and "Restart" in err and "recover-containers" in err
    assert str(project.resolve()) in err and records.chain(project)["phase"] == "closed"


def test_an_attempt_that_cannot_be_prepared_is_named_and_the_exit_code_is_one(
        project, monkeypatch, capsys):
    runner = Runner(project, monkeypatch)
    runner.outcome = [{"attempt": "a" * 32, "state": "not_prepared", "action": "no preparation "
                       "is needed: a restart is already proven"}]
    code, out, err = run(capsys, "ownership", "recover-containers", "--prepare-restart",
                         "--dir", str(project))
    assert code == 1 and json.loads(out)["records"][0]["state"] == "not_prepared"
    assert "no preparation is needed" in err


def test_a_project_that_is_not_activated_has_no_container_journal_and_nothing_is_asked(
        tmp_path, monkeypatch, capsys):
    root = tmp_path / "plain"
    root.mkdir()
    runner = Runner(root, monkeypatch)
    code, out, err = run(capsys, "ownership", "recover-containers", "--dir", str(root))
    assert code == 1 and out == "" and "activation_required" in err and runner.calls == []


def test_an_abandoned_project_is_recovered_first_and_the_journal_is_not_asked(
        tmp_path, monkeypatch, capsys):
    root = tmp_path / "abandoned"
    root.mkdir()
    abandoned_legacy(root)
    runner = Runner(root, monkeypatch)
    code, out, err = run(capsys, "ownership", "recover-containers", "--dir", str(root))
    assert code == 1 and out == "" and "recovery_required" in err and runner.calls == []


def test_a_platform_without_the_native_side_is_refused_in_one_clear_line_before_any_owner(
        project, monkeypatch, capsys):
    runner = Runner(project, monkeypatch)
    monkeypatch.setitem(sys.modules, _NATIVE, None)     # the import of `_winlaunch` fails
    monkeypatch.delattr(adapters, "_winlaunch", raising=False)   # nor is it found as an attribute
    code, out, err = run(capsys, "ownership", "recover-containers", "--dir", str(project))
    assert code == 1 and out == "" and "only on Windows" in err and runner.calls == []
    assert records.chain(project)["phase"] == "active"
