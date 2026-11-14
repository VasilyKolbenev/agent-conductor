"""AppContainer independently checks the staged identity and exact rights. No network or model."""
from contextlib import contextmanager, ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from zipfile import ZipFile

import pytest

from conductor import ownership
from conductor.command.adapters.kimi_code import KIMI_AUTH_INPUT, KIMI_PROFILE, KIMI_PROTOCOL
from conductor.command.adapters.process import CommandSpec, ProcessRunner
from conductor.command.adapters.process_boundary import AttemptFolders
from conductor.command.adapters.process_profile import ProfileRefused
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.operator_config import provider_config_path, save_provider_configs
from conductor.ownership_native import NativeHold, identity
from scripts._kimi_stage_native import HeldObject
from tests._ps1 import strict_text, write_ps1
from tests.os_boundary_box import base_environment, WITHOUT_CMDLETS
from tests.test_kimi_quota import CONFIG
from tests.test_process_login_native import _q
from tests.test_relay_home_native import RelaySite, _probe

pytestmark = pytest.mark.skipif(os.name != "nt", reason="a real Windows AppContainer")
ARCHIVE_SHA = "80e4de3f2bd7c33ba10cfe3c2282492b0758fae9887537f4ff79ec2022957004"


@contextmanager
def fixture_home(site):
    parent = site.root / ".kimi-home"
    parent.mkdir()
    path = parent / "attempt"
    with ExitStack() as held:
        original = NativeHold(parent, directory=True)
        held.callback(original.close)
        anchor = HeldObject(original, "attempt", create=True, loan_anchor=True)
        held.callback(anchor.close)
        # The producer allows the loan handle to coexist; do not lock the leaf through the
        # runtime ACL witness, or a sharing violation could impersonate a denied container.
        token = json.dumps({"access_token": "synthetic-stage-access", "refresh_token": "",
                            "expires_in": 7200, "expires_at": int(time.time()) + 7100,
                            "scope": "", "token_type": "Bearer"}).encode()
        with ExitStack() as material:
            subdir = HeldObject(anchor, "credentials", create=True)
            material.callback(subdir.close)
            for holder, name, content in [(subdir, "kimi-code.json", token),
                                           (anchor, "config.toml", CONFIG.encode())]:
                leaf = HeldObject(holder, name, create=True)
                material.callback(leaf.close)
                leaf.append(content)
        yield path, anchor, token


def folders(site, anchor):
    return AttemptFolders("work/t1", ".kimi-home/attempt", str(site.install),
                          readonly_home_identity=anchor.identity)


def configure(site, binary):
    pin = ProviderConfig("kimi-code", str(binary), KIMI_PROTOCOL,
                         auth="subscription", auth_home=str(site.login))
    config_path = provider_config_path(ownership.data_root(site.root))
    save_provider_configs(config_path, [pin], project_root=site.root)


def test_actual_container_reads_credential_cannot_write_or_rename_and_writes_scratch(tmp_path):
    from tests import os_boundary_windows as ac
    site = RelaySite(tmp_path, relay=False)
    runner = ProcessRunner(site.root)
    with fixture_home(site) as (home, anchor, token), ownership.acquire_owner(site.root):
        leaf = home / "credentials" / "kimi-code.json"
        configure(site, site.install / "entry.ps1")
        with runner.container_profile(mode="review", internet_client=False,
                                      folders=folders(site, anchor)) as (boundary, paths):
            scratch = paths["runtime"] / "allowed.txt"
            assert identity(paths["home"]) == anchor.identity and not boundary.internet_client
            script = WITHOUT_CMDLETS + "$o=''; " + "".join([
                _probe("read", f"[void][IO.File]::ReadAllBytes({_q(leaf)})"),
                _probe("write", f"[IO.File]::WriteAllText({_q(leaf)},'forbidden')"),
                _probe("rename", f"[IO.File]::Move({_q(leaf)},{_q(leaf.with_name('moved'))})"),
                _probe("home", f"[IO.File]::WriteAllText({_q(home/'unreviewed')},'forbidden')"),
                _probe("scratch", f"[IO.File]::WriteAllText({_q(scratch)},'allowed')"),
            ]) + "[Console]::Out.Write($o)"
            entry = write_ps1(site.install / "entry.ps1", script)
            result = runner.run(CommandSpec(
                (str(ac.POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(entry)), "work/t1", env=base_environment(paths["runtime"]),
                boundary=boundary, timeout_seconds=60))
            denied = "UnauthorizedAccessException/80070005"
            assert result.status == "completed" and result.exit_code == 0
            expected = f"read=ok;write={denied};rename={denied};home={denied};scratch=ok;"
            assert strict_text(result.output) == expected
            assert scratch.read_text() == "allowed" and leaf.read_bytes() == token
            assert not (home / "unreviewed").exists()
            scratch.unlink()  # Test-created witness in the runner's owned runtime folder.
        assert identity(home) == anchor.identity


def test_original_pinned_kimi_acp_uses_the_readonly_loan_without_network(tmp_path):
    source = os.environ.get("CONDUCT_TEST_KIMI_ARCHIVE")
    if not source:
        pytest.skip("supply the official 0.38.0 Windows x64 archive for this opt-in test")
    path = Path(source)
    with path.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == ARCHIVE_SHA
    site = RelaySite(tmp_path, relay=False)
    binary = site.install / "kimi.exe"
    with ZipFile(path) as archive:
        assert archive.namelist() == ["kimi.exe"]
        assert archive.getinfo("kimi.exe").file_size == 150901248
        with archive.open("kimi.exe") as src, binary.open("xb") as dst:
            shutil.copyfileobj(src, dst)
    runner = ProcessRunner(site.root)
    with fixture_home(site) as (home, anchor, token), ownership.acquire_owner(site.root):
        configure(site, binary)
        with runner.container_profile(mode="review", internet_client=False,
                                      folders=folders(site, anchor)) as (boundary, paths):
            env = dict(base_environment(paths["runtime"]), **dict(KIMI_PROFILE.forced_env))
            env[KIMI_PROFILE.home_env] = str(home)
            assert identity(paths["home"]) == anchor.identity and not boundary.internet_client
            result = runner.run(CommandSpec((str(binary), "acp"), "work/t1", env=env,
                                boundary=boundary, timeout_seconds=45, stdin_bytes=KIMI_AUTH_INPUT,
                                stdin_completion_id=2, separate_stderr=True))
            replies = [json.loads(line) for line in result.output.splitlines()
                       if line.startswith(b"{")]
            assert result.status == "completed" and result.exit_code == 0
            assert any(r.get("id") == 1 and isinstance(r.get("result"), dict) for r in replies)
            assert any(r.get("id") == 2 and isinstance(r.get("result"), dict) for r in replies), (
                "the pinned offline CLI did not accept this synthetic profile on a read-only loan")
            assert (home / "credentials/kimi-code.json").read_bytes() == token
