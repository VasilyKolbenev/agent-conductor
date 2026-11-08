"""A real offline state grant and a separate owner-process death; no provider login."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from conductor import ownership
from conductor.command.adapters.process import CommandSpec, ProcessRunner
from tests._boot_world import later_boot, measure
from tests._ps1 import strict_text, write_ps1
from tests.os_boundary_box import base_environment, WITHOUT_CMDLETS
from tests.test_kimi_home_loan_native import configure, fixture_home, folders
from tests.test_process_login_native import _q
from tests.test_relay_home_native import RelaySite, _probe

pytestmark = pytest.mark.skipif(os.name != "nt", reason="native Windows profile and ACL")


def exercise(base, *, interrupt=False):
    from conductor.command.adapters import _winlaunch as native
    from tests import os_boundary_windows as ac

    site = RelaySite(base, relay=False)
    original = site.login / ".credentials.json"
    before = original.read_bytes()
    runner = ProcessRunner(site.root)
    with fixture_home(site) as (stage, anchor, token), ownership.acquire_owner(site.root):
        configure(site, site.install / "entry.ps1")
        with runner.container_profile(mode="review", internet_client=False,
                                      folders=folders(site, anchor), kimi_state=True) as entry:
            boundary, paths = entry
            assert not boundary.internet_client
            state, sessions = paths["kimi_state"], paths["kimi_sessions"]
            read_stage = stage / "credentials/kimi-code.json"
            newdir, sealed = state / "other", paths["kimi_credentials"] / "x"
            checks = [("registry", f"[IO.File]::WriteAllText({_q(state/'workspaces.json')},'ok')"),
                      ("session", f"[IO.File]::WriteAllText({_q(sessions/'record')},'changed')"),
                      ("newdir", f"[IO.Directory]::CreateDirectory({_q(newdir)}) | Out-Null"),
                      ("sealed", f"[IO.File]::WriteAllText({_q(sealed)},'x')"),
                      ("stage", f"[IO.File]::WriteAllText({_q(read_stage)},'x')"),
                      ("login", f"[IO.File]::WriteAllText({_q(original)},'x')")]
            script = WITHOUT_CMDLETS + "$o=''; " + "".join(_probe(*item) for item in checks)
            entrypoint = write_ps1(site.install / "entry.ps1", script + "[Console]::Out.Write($o)")
            result = runner.run(CommandSpec(
                (str(ac.POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(entrypoint)), "work/t1", env=base_environment(paths["runtime"]),
                boundary=boundary, timeout_seconds=30))
            denied = "UnauthorizedAccessException/80070005"
            assert result.exit_code == 0 and strict_text(result.output) == (
                f"registry=ok;session=ok;newdir={denied};sealed={denied};stage={denied};"
                f"login={denied};")
            assert original.read_bytes() == before and read_stage.read_bytes() == token
            assert (sessions / "record").read_bytes() == b"changed"
            proof = {"sid": boundary.sid, "state": str(state),
                     "source_hash": hashlib.sha256(before).hexdigest()}
            if interrupt:
                (base / "witness.json").write_text(json.dumps(proof), encoding="utf-8")
                os._exit(37)  # Kill the owner before any context manager retires its resources.
        assert native.inspect_profile(proof["sid"]) is None and not state.exists()
    assert not runner.active_tokens()


def test_child_writes_only_the_two_permitted_state_classes(tmp_path):
    exercise(tmp_path)


def test_reopen_after_owner_death_keeps_state_until_a_proven_restart(tmp_path, monkeypatch):
    from conductor.command.adapters import _winlaunch as native
    from conductor import ownership_boot, ownership_transition
    from conductor.ownership_records import OwnerRefused

    command = [sys.executable, "-B", "-m", "tests.test_kimi_state_journal_native", str(tmp_path)]
    child = subprocess.run(command, capture_output=True, timeout=60)
    assert child.returncode == 37, child.stderr
    proof = json.loads((tmp_path / "witness.json").read_bytes())
    state = Path(proof["state"])
    assert state.is_relative_to(tmp_path / "project" / "conductor.v3" / "container-attempts")
    root = tmp_path / "project"
    with pytest.raises(OwnerRefused, match="restart"):
        ownership_transition.recover(root)
    assert (state / "sessions" / "record").read_bytes() == b"changed"
    assert native.inspect_profile(proof["sid"]) is not None
    # Only the clock witness below is simulated. The crash, journal and Windows cleanup
    # are real. This does not restart the host.
    measure(monkeypatch, later_boot(ownership_boot.current_boot()))
    ownership_transition.recover(root)
    with ownership.acquire_owner(root):
        runner = ProcessRunner(root)
        runner.recover_container_profiles()
        runner.recover_container_profiles()
        assert not state.parent.exists() and native.inspect_profile(proof["sid"]) is None
        original = tmp_path / "DecemberCommand/logins/x/.credentials.json"
        assert hashlib.sha256(original.read_bytes()).hexdigest() == proof["source_hash"]
        assert any(json.loads(p.read_bytes())["phase"] == "retired" for p in
                   (ownership.data_root(root) / "process-profiles").glob("acl-*.json"))


if __name__ == "__main__":
    exercise(Path(sys.argv[1]), interrupt=True)
