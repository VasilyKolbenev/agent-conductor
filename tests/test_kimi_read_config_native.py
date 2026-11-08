"""Observe the code-owned config and its denial of writes from a real offline AppContainer."""
import hashlib
import json
import os

import pytest

from conductor import ownership
from conductor.command.adapters.kimi_read_config import read_role_config
from conductor.command.adapters.process import CommandSpec, ProcessRunner
from conductor.command.adapters.process_profile import ProfileRefused
from conductor.ownership_native import identity
from tests._ps1 import strict_text, write_ps1
from tests.os_boundary_box import base_environment, WITHOUT_CMDLETS
from tests.test_kimi_home_loan_native import configure, fixture_home, folders, _probe, _q
from tests.test_kimi_session_state_native import state_home
from tests.test_relay_home_native import RelaySite


pytestmark = pytest.mark.skipif(os.name != "nt", reason="requires Windows AppContainer")


def test_bound_config_and_credentials_are_readable_and_writes_are_denied(tmp_path):
    from tests import os_boundary_windows as ac

    site = RelaySite(tmp_path, relay=False)
    runner = ProcessRunner(site.root)
    with fixture_home(site) as (source, anchor, _), ownership.acquire_owner(site.root):
        configure(site, site.install / "entry.ps1")
        original = (source / "config.toml").read_bytes()
        role = read_role_config(original)
        records = ownership.data_root(site.root) / "process-profiles"
        with runner.container_profile(mode="review", folders=folders(site, anchor),
                                      kimi_state=True, kimi_read_config=role) as (boundary, paths):
            assert not boundary.internet_client
            config = paths["kimi_state"] / "config.toml"
            staged_cred = paths["kimi_credentials"] / "kimi-code.json"
            journal = records / ("acl-" + paths["parent"].name + ".json")
            row = json.loads(journal.read_bytes())
            assert row["profile_sid"] == boundary.sid and row["phase"] == "applied"
            assert row["kimi_read_config"] == {
                "source_sha256": hashlib.sha256(original).hexdigest(),
                "config_sha256": role.config_sha256, "identity": list(identity(config))}
            with state_home(paths["kimi_state"], source, boundary.sid, bound_config=True):
                new_cred = staged_cred.parent / "x"
                hash_read = (f"$h=[Security.Cryptography.SHA256]::Create();"
                             f"$bytes=$h.ComputeHash([IO.File]::ReadAllBytes({_q(config)}));"
                             "$sha=[BitConverter]::ToString($bytes).Replace('-','').ToLower();"
                             f"if($sha -ne '{role.config_sha256}'){{throw 'digest'}}")
                script = WITHOUT_CMDLETS + "$o=''; " + "".join([
                    _probe("config-read", hash_read),
                    _probe("config-write", f"[IO.File]::WriteAllText({_q(config)},'bad')"),
                    _probe("cred-write", f"[IO.File]::WriteAllText({_q(staged_cred)},'bad')"),
                    _probe("new-cred", f"[IO.File]::WriteAllText({_q(new_cred)},'x')"),
                ]) + "[Console]::Out.Write($o)"
                entry = write_ps1(site.install / "entry.ps1", script)
                result = runner.run(CommandSpec(
                    (str(ac.POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                     "Bypass", "-File", str(entry)), "work/t1",
                    env=base_environment(paths["runtime"]), boundary=boundary, timeout_seconds=30))
                denied = "UnauthorizedAccessException/80070005"
                assert result.exit_code == 0 and strict_text(result.output) == (
                    f"config-read=ok;config-write={denied};cred-write={denied};new-cred={denied};")
                assert config.read_bytes() == role.content
                original_cred = source / "credentials/kimi-code.json"
                assert staged_cred.read_bytes() == original_cred.read_bytes()
        assert not paths["parent"].exists()
        assert json.loads(journal.read_bytes())["phase"] == "retired"


def test_changed_source_after_preview_cannot_yield_an_attempt(tmp_path):
    site = RelaySite(tmp_path, relay=False)
    runner = ProcessRunner(site.root)
    with fixture_home(site) as (source, anchor, _), ownership.acquire_owner(site.root):
        configure(site, site.install / "entry.ps1")
        config = source / "config.toml"
        before = config.read_bytes()
        preview = read_role_config(before)
        config.write_bytes(before + b"\n")
        with pytest.raises(ProfileRefused, match="preview digest changed"):
            with runner.container_profile(mode="review", folders=folders(site, anchor),
                                          kimi_state=True, kimi_read_config=preview):
                pytest.fail("yielded a changed profile to the caller")
        assert config.read_bytes() == before + b"\n"
        records = ownership.data_root(site.root) / "process-profiles"
        rows = [json.loads(p.read_bytes()) for p in records.glob("acl-*.json")]
        assert len(rows) == 1 and rows[0]["phase"] == "retired"
