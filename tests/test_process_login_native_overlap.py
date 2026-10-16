"""Two attempts of different harnesses overlap in time inside real AppContainers.

Each attempt runs in its own thread, because the shared login lease is bound to the thread that
took it, holds the lease on its own login home, and is loaned that home, its own install folder and
its own work item. While both stand, each child rewrites its own login file and is refused the
other's. When one attempt leaves, its profile is named nowhere; the one still running keeps every
entry and a second child of it still rewrites its own login file. The homes are throwaway ones under
the pytest base directory, in the shape the product keeps its logins in.
"""
from __future__ import annotations

import os
import threading

import pytest

from conductor import ownership, ownership_transition
from conductor.command.adapters.process import CommandSpec, ProcessRunner
from conductor.command.adapters.process_boundary import AttemptFolders
from tests.login_gate import login_loan_open_module  # noqa: F401 -- a fixture
from tests.test_process_loans_native import entries_naming, same_acl, snapshot
from tests.test_process_login_native import CREDENTIAL, _q, _tries

pytestmark = [pytest.mark.skipif(os.name != "nt", reason="native AppContainer ACL loans"),
              pytest.mark.usefixtures("login_loan_open_module")]

NAMES = ("claude-code", "codex")
WAIT = 90
KEYS = ("work", "install", "login")


def other(name):
    return NAMES[1] if name == NAMES[0] else NAMES[0]


class Duo:
    """One project and two harnesses, each with a login home, an install folder and a work item."""

    def __init__(self, base):
        self.root = (base / "project").resolve()
        (self.root / "conductor").mkdir(parents=True)
        self.login, self.install, self.item = {}, {}, {}
        for number, name in enumerate(NAMES, 1):
            self.item[name] = f"t{number}"
            (self.root / "work" / f"t{number}").mkdir(parents=True)
            self.install[name] = (base / "harnesses" / name / "1.0").resolve()
            self.install[name].mkdir(parents=True)
            self.login[name] = (base / "DecemberCommand" / "logins" / name).resolve()
            self.login[name].mkdir(parents=True)
            (self.login[name] / "auth.json").write_text(CREDENTIAL, encoding="utf-8")
        self.logins = self.login[NAMES[0]].parent
        ownership_transition.activate(self.root, legacy_writers_stopped=True)
        for name in NAMES:
            for tag in ("first", "again"):
                (self.install[name] / f"{tag}.ps1").write_text(self.script(name, tag), "utf-8")

    def script(self, name, tag):
        from tests.os_boundary_box import WITHOUT_CMDLETS
        own, foreign = self.login[name] / "auth.json", self.login[other(name)] / "auth.json"
        return (WITHOUT_CMDLETS + "$o = ''; "
                + _tries("own", f"[IO.File]::WriteAllText({_q(own)},'token={name}-{tag}')")
                + _tries("other", f"[IO.File]::WriteAllText({_q(foreign)},'bad')")
                + "[Console]::Out.Write($o)")

    def folders_of(self, name):
        return {"work": self.root / "work" / self.item[name], "install": self.install[name],
                "login": self.login[name]}

    def everywhere(self):
        return {(name, key): path for name in NAMES for key, path in self.folders_of(name).items()}


class Gate:
    """The events the main thread and the two attempts hand over to each other."""

    def __init__(self):
        self.ran = {name: threading.Event() for name in NAMES}
        self.leave = {name: threading.Event() for name in NAMES}
        self.left = {name: threading.Event() for name in NAMES}
        self.again = threading.Event()

    def open_all(self):
        for group in (self.ran, self.leave, self.left):
            for event in group.values():
                event.set()
        self.again.set()


def child(duo, runner, name, boundary, paths, tag):
    from tests import os_boundary_windows as ac
    from tests.os_boundary_box import base_environment
    entry = duo.install[name] / f"{tag}.ps1"
    spec = CommandSpec(
        (str(ac.POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(entry)), f"work/{duo.item[name]}",
        env=base_environment(paths["runtime"]), boundary=boundary, timeout_seconds=60)
    outcome = runner.run(spec)
    assert outcome.status == "completed" and outcome.exit_code == 0, outcome
    return dict(part.split("=") for part in outcome.output.decode().split(";") if part)


def attempt(duo, name, stays, gate, results):
    """One attempt in its own thread. `stays`: it runs a second child after the other has left."""
    runner = ProcessRunner(duo.root)
    folders = AttemptFolders(work=f"work/{duo.item[name]}", home=None,
                             install=str(duo.install[name]), login=str(duo.login[name]))
    try:
        with ProcessRunner.login_write_guard(duo.root, str(duo.login[name])):
            with runner.container_profile(mode="dispatch", folders=folders) as (boundary, paths):
                results[name] = {"sid": boundary.sid,
                                 "first": child(duo, runner, name, boundary, paths, "first")}
                gate.ran[name].set()
                if stays:
                    assert gate.left[other(name)].wait(WAIT)
                    results[name]["again"] = child(duo, runner, name, boundary, paths, "again")
                    gate.again.set()
                assert gate.leave[name].wait(WAIT)
    except BaseException as error:  # the main thread judges it; nothing may hang
        results[name] = {**results.get(name, {}), "error": error}
        gate.open_all()
    finally:
        gate.left[name].set()


def awaited(event, results):
    """Wait for a step of the other threads; an error of an attempt ends the wait and is named."""
    reached = event.wait(WAIT)
    errors = {name: row["error"] for name, row in results.items() if "error" in row}
    assert reached and not errors, errors


def snapshots(duo):
    return {key: snapshot(path) for key, path in duo.everywhere().items()}


def play(duo, leaving):
    """Both attempts stand; `leaving` returns its loans first; the other runs on and then leaves."""
    staying, gate, results, seen = other(leaving), Gate(), {}, {}
    with ownership.acquire_owner(duo.root):
        seen["before"] = snapshots(duo)
        threads = [threading.Thread(target=attempt, args=(duo, n, n == staying, gate, results))
                   for n in NAMES]
        for thread in threads:
            thread.start()
        try:
            for name in NAMES:
                awaited(gate.ran[name], results)
            seen["together"] = snapshots(duo)
            gate.leave[leaving].set()
            awaited(gate.left[leaving], results)
            awaited(gate.again, results)
            seen["middle"] = snapshots(duo)
        finally:
            gate.open_all()
            for thread in threads:
                thread.join(WAIT)
        seen["after"] = snapshots(duo)
    return results, seen


@pytest.fixture(scope="module", params=NAMES, ids=["first-leaves-first", "second-leaves-first"])
def overlap(request, tmp_path_factory, login_loan_open_module):
    duo = Duo(tmp_path_factory.mktemp("login-duo"))
    results, seen = play(duo, request.param)
    errors = {name: row["error"] for name, row in results.items() if "error" in row}
    assert not errors, errors
    return duo, request.param, results, seen


def named(seen, when, sid, name):
    return {key: sid in seen[when][(name, key)][0] for key in KEYS}


def test_while_both_stand_each_child_rewrites_its_own_login_file_and_is_refused_the_others(
        overlap):
    duo, _, results, _ = overlap
    for name in NAMES:
        assert results[name]["first"] == {"own": "ok", "other": "denied"}, name
        assert (duo.login[other(name)] / "auth.json").read_text("utf-8") != "bad"


def test_while_both_stand_each_profile_is_named_on_its_own_folders_and_on_no_others(overlap):
    _, _, results, seen = overlap
    for name in NAMES:
        mine, theirs = results[name]["sid"], results[other(name)]["sid"]
        assert named(seen, "together", mine, name) == dict.fromkeys(KEYS, True)
        assert named(seen, "together", theirs, name) == dict.fromkeys(KEYS, False)


def test_when_one_attempt_leaves_its_profile_is_named_nowhere_and_the_other_keeps_every_entry(
        overlap):
    duo, leaving, results, seen = overlap
    staying = other(leaving)
    gone, kept = results[leaving]["sid"], results[staying]["sid"]
    assert named(seen, "middle", gone, leaving) == dict.fromkeys(KEYS, False)
    assert named(seen, "middle", kept, staying) == dict.fromkeys(KEYS, True)
    for key in KEYS:
        assert same_acl(seen["middle"][(leaving, key)], seen["before"][(leaving, key)]), key
        assert seen["middle"][(staying, key)] == seen["together"][(staying, key)], key


def test_the_attempt_that_stays_still_rewrites_its_own_login_file_after_the_other_has_left(
        overlap):
    duo, leaving, results, _ = overlap
    staying = other(leaving)
    assert results[staying]["again"] == {"own": "ok", "other": "denied"}
    assert (duo.login[staying] / "auth.json").read_text("utf-8") == f"token={staying}-again"
    assert (duo.login[leaving] / "auth.json").read_text("utf-8") == f"token={leaving}-first"


def test_after_both_have_left_every_folder_has_its_acl_back_and_icacls_names_neither_profile(
        overlap):
    duo, _, results, seen = overlap
    for key in duo.everywhere():
        assert same_acl(seen["after"][key], seen["before"][key]), key
    works = [duo.root / "work" / item for item in duo.item.values()]
    places = [duo.logins, *duo.install.values(), *works]
    for name in NAMES:
        for path in places:
            assert entries_naming(path, results[name]["sid"]) == [], (name, str(path))
