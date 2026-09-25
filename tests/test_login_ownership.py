"""Shared external login lifetime across real projects and native processes."""
from __future__ import annotations

import json
from dataclasses import replace
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from conductor import ownership, ownership_login
from conductor.command.adapters.harness_workspace import WORK_DIR
from conductor.command.adapters.process import CommandSpec, OwnershipError, ProcessRunner
from tests.test_command_task_store import durable_bytes
from tests.test_harness_subscription_login import a_harness
from tests.test_project_ownership import activated


def child(base, home, code):
    source = Path(ownership.__file__).resolve().parents[1]
    environment = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ}
    environment.update(PYTHONPATH=str(source) + os.pathsep + str(source.parent),
                       PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    return subprocess.run([sys.executable, "-c", code, str(base), str(home)],
        cwd=base, env=environment, capture_output=True, timeout=20, check=False)


ATTEMPT = """
import sys
from pathlib import Path
from conductor.ownership import acquire_owner
from conductor.command.adapters.harness_workspace import WORK_DIR
from conductor.command.adapters.process import ProcessRunnerError
from tests.test_harness_subscription_login import a_harness
adapter, root, log = a_harness(Path(sys.argv[1]), auth='subscription', auth_home=sys.argv[2])
with acquire_owner(root):
    adapter._workspace.work_root()
    try:
        result = adapter._attempt(adapter.profile.version_argv, WORK_DIR, timeout=5)
        assert result.exit_code == 0
        print('completed')
    except ProcessRunnerError as error:
        print(str(error))
"""


def test_two_real_projects_share_one_resource_through_post_spawn_cleanup(tmp_path, monkeypatch):
    home = tmp_path / "login"
    home.mkdir()
    first, root, _ = a_harness(tmp_path / "one", auth="subscription", auth_home=str(home))
    _, second_root, second_log = a_harness(tmp_path / "two", auth="subscription", auth_home=str(home))
    activated(root)
    activated(second_root)
    entered, release = threading.Event(), threading.Event()
    original = first._take_back_login
    results, errors = [], []

    def held_cleanup(auth_home, before):
        entered.set()
        assert release.wait(15), "test did not release post-spawn cleanup"
        return original(auth_home, before)

    def attempt():
        try:
            results.append(first._attempt(first.profile.version_argv, WORK_DIR, timeout=5))
        except BaseException as error:
            errors.append(error)

    monkeypatch.setattr(first, "_take_back_login", held_cleanup)
    with ownership.acquire_owner(root):
        first._workspace.work_root()
        worker = threading.Thread(target=attempt)
        worker.start()
        try:
            assert entered.wait(8), errors
            refused = child(tmp_path / "two", home, ATTEMPT)
            assert refused.returncode == 0, refused.stderr
            assert b"login_owner_busy" in refused.stdout
            assert not second_log.exists(), "loser spawned before owning the shared login"
        finally:
            release.set()
            worker.join(10)
        assert not worker.is_alive() and not errors
        assert results[0].exit_code == 0
    accepted = child(tmp_path / "two", home, ATTEMPT)
    assert accepted.returncode == 0, accepted.stderr
    assert accepted.stdout.strip() == b"completed"
    assert second_log.is_file()


def test_normal_shared_lease_keeps_credentials_out_of_ownership_records(tmp_path):
    home = tmp_path / "login"
    home.mkdir()
    secret = b"synthetic-login-secret-123456789"
    (home / "credential.json").write_bytes(secret)
    project = tmp_path / "project"
    project.mkdir()
    activated(project)
    with ownership.acquire_owner(project):
        with ProcessRunner.login_write_guard(project, str(home)):
            pass
    assert (home / "credential.json").read_bytes() == secret
    _, box = ownership_login._route(str(home))
    assert not (box / "active.json").exists()
    assert len(list(box.glob("closed-*.json"))) == 1
    assert all(secret not in payload for payload in durable_bytes(box).values())


def test_native_child_inherits_both_project_and_shared_login_holds(tmp_path, monkeypatch):
    home = tmp_path / "login"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    activated(project)
    (project / "work").mkdir()
    launch = ProcessRunner._launch
    code = """
import os, sys
for word in sys.argv[1:]:
    handle = int(word)
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetFileType.argtypes = [wintypes.HANDLE]
        assert kernel.GetFileType(handle) == 1, ctypes.get_last_error()
    else:
        import stat
        assert stat.S_ISREG(os.fstat(handle).st_mode)
print('both-native-holds')
"""

    def observe(spec, cwd, environment, payload, loan):
        assert len(set(loan.handles)) == 2
        argv = [sys.executable, "-c", code, *map(str, loan.handles)]
        return launch(replace(spec, argv=argv), cwd, environment, payload, loan)

    monkeypatch.setattr(ProcessRunner, "_launch", staticmethod(observe))
    with ownership.acquire_owner(project), ProcessRunner.login_write_guard(project, str(home)):
        result = ProcessRunner(project).run(CommandSpec(
            argv=[sys.executable, "-c", "pass"], cwd="work", timeout_seconds=5))
        assert result.exit_code == 0 and result.output.strip() == b"both-native-holds"


CRASH = """
import os, sys
from conductor.ownership import acquire_owner
from conductor.command.adapters.process import ProcessRunner
owner = acquire_owner(sys.argv[1])
with ProcessRunner.login_write_guard(sys.argv[1], sys.argv[2]):
    os._exit(0)
"""


def abandoned(tmp_path):
    home = tmp_path / "login"
    home.mkdir()
    project = tmp_path / "project-a"
    project.mkdir()
    activated(project)
    done = child(project, home, CRASH)
    assert done.returncode == 0, done.stderr
    _, box = ownership_login._route(str(home))
    assert (box / "active.json").is_file()
    return home, box


def test_crashed_lease_refuses_another_project_and_same_boot_recovery(tmp_path):
    home, box = abandoned(tmp_path)
    project = tmp_path / "project-b"
    project.mkdir()
    activated(project)
    before = durable_bytes(box)
    with ownership.acquire_owner(project):
        with pytest.raises(OwnershipError, match="login_recovery_required"):
            with ProcessRunner.login_write_guard(project, str(home)):
                pytest.fail("unknown shared writer was admitted")
    with pytest.raises(ownership.OwnerRefused, match="restart the OS"):
        ownership_login.recover_login(str(home))
    assert durable_bytes(box) == before


def test_explicit_controlled_new_boot_recovery_does_not_run_or_read_credentials(tmp_path, monkeypatch):
    """A protocol test with a supplied boot fact, not an actual OS reboot."""
    home, box = abandoned(tmp_path)
    record = json.loads((box / "active.json").read_bytes())
    other = record["boot"].split(":")[0] + ":00000000-1111-4222-8333-444444444444"
    assert other != record["boot"]
    monkeypatch.setattr(ownership_login, "boot_identity", lambda: other)
    assert ownership_login.recover_login(str(home))["state"] == "recovered"
    assert not (box / "active.json").exists()
    assert len(list(box.glob("recovered-*.json"))) == 1
    project = tmp_path / "project-b"
    project.mkdir()
    activated(project)
    with ownership.acquire_owner(project):
        with ProcessRunner.login_write_guard(project, str(home)):
            pass
    assert len(list(box.glob("closed-*.json"))) == 1


def test_recovery_never_adopts_a_copied_active_record(tmp_path, monkeypatch):
    home, box = abandoned(tmp_path)
    standing = (box / "active.json").read_bytes()
    (box / "active.json").rename(box / "foreign-original.json")
    (box / "active.json").write_bytes(standing)
    before = durable_bytes(box)
    monkeypatch.setattr(ownership_login, "boot_identity", lambda: "windows:00000000-1111-4222-8333-444444444444")
    with pytest.raises(ownership.OwnerRefused, match="login_ownership_invalid"):
        ownership_login.recover_login(str(home))
    assert durable_bytes(box) == before


def test_exception_preserves_uncertain_lease_instead_of_claiming_a_clean_close(tmp_path):
    home = tmp_path / "login"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    activated(project)
    with ownership.acquire_owner(project):
        with pytest.raises(OwnershipError, match="uncertain"):
            with ProcessRunner.login_write_guard(project, str(home)):
                raise RuntimeError("interrupted existing attempt lifetime")
    _, box = ownership_login._route(str(home))
    assert (box / "active.json").is_file()
    assert not list(box.glob("closed-*.json"))


def test_unproven_native_retirement_remains_a_shared_refusal(tmp_path):
    home = tmp_path / "login"
    home.mkdir()
    project = tmp_path / "project-a"
    project.mkdir()
    activated(project)
    result = child(project, home, """
import os, sys
from conductor.ownership import acquire_owner
from conductor.command.adapters.process import OwnershipError, ProcessRunner
owner = acquire_owner(sys.argv[1])
try:
    with ProcessRunner.login_write_guard(sys.argv[1], sys.argv[2]):
        loan = owner._claim_process()
        loan.retire(False)
except OwnershipError:
    print('uncertain-refused', flush=True)
    os._exit(0)
os._exit(3)
""")
    assert result.returncode == 0 and result.stdout.strip() == b"uncertain-refused", result.stderr
    _, box = ownership_login._route(str(home))
    assert (box / "active.json").is_file()
    assert not list(box.glob("closed-*.json"))
    with pytest.raises(ownership.OwnerRefused, match="restart the OS"):
        ownership_login.recover_login(str(home))


def test_api_key_road_does_not_create_shared_login_metadata(tmp_path):
    activated(tmp_path)
    before = set(tmp_path.parent.iterdir()), durable_bytes(tmp_path)
    with ProcessRunner.login_write_guard(tmp_path, ""):
        pass
    assert (set(tmp_path.parent.iterdir()), durable_bytes(tmp_path)) == before
