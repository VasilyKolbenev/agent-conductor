"""Optional networkless Kimi ACP session probes with synthetic credentials, before any prompt."""
from contextlib import contextmanager, ExitStack
import hashlib
import json
import os
from pathlib import Path

import pytest

from conductor import ownership
from conductor.command.adapters.kimi_code import KIMI_AUTH_INPUT, KIMI_PROFILE
from conductor.command.adapters.process import CommandSpec, ProcessRunner
from conductor.command.long_path import extended
from conductor.ownership_native import NativeHold, identity
from scripts.kimi_windows_kit import stage, verified_bundle
from tests.os_boundary_box import base_environment
from tests.test_kimi_home_loan_native import ARCHIVE_SHA, configure, fixture_home, folders
from tests.test_relay_home_native import RelaySite

pytestmark = pytest.mark.skipif(os.name != "nt", reason="requires Windows AppContainer")
SHELL_FILES = {
    "sh.exe": "e769a06bace817d96a4448f985ea2b48526c6cab042417229665f6b446e038dd",
    "msys-2.0.dll": "a4f38fafec60affc988a0ccc9a51255b86469326ead9730ec7b1af87ce95579e",
}
EXE_SHA = "b7e658d06176284384d1e9eb627d11e5a26627b3964bf8787f197915d1484b1e"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@pytest.fixture(scope="module")
def native_files():
    archive = os.environ.get("CONDUCT_TEST_KIMI_ARCHIVE")
    shell = os.environ.get("CONDUCT_TEST_KIMI_SHELL")
    if not archive or not shell:
        pytest.skip("supply the 0.38.0 Windows archive and measured Git for Windows sh.exe")
    archive, shell = Path(archive), Path(shell)
    assert archive.is_absolute() and shell.is_absolute() and shell.name == "sh.exe"
    assert sha(archive) == ARCHIVE_SHA
    for name, digest in SHELL_FILES.items():
        assert sha(shell.parent / name) == digest, name
    return archive, shell.parent


def install(site, archive, shell_dir):
    root = site.install / "kimi-kit"
    receipt = stage(archive, shell_dir, root)
    assert receipt["files"]["kimi.exe"]["sha256"] == EXE_SHA
    assert {p: receipt["files"]["shell/" + p]["sha256"] for p in SHELL_FILES} == SHELL_FILES
    return root


def grant_file(path, sid, rights):
    from conductor.command.adapters import _winlaunch as native

    handle = NativeHold(path, grants=True)
    try:
        _, _, owner = native.acl_snapshot(handle)
        mask = "0x120089" if rights == "read" else "0x13019f"
        acl = f"O:{owner}D:P(A;;FA;;;SY)(A;;FA;;;{owner})(A;;{mask};;;{sid})"
        native.acl_set(handle, acl, protected=True)
        actual, protected, _ = native.acl_snapshot(handle)
        assert protected and native.acl_equal(actual, acl)
    finally:
        handle.close()


@contextmanager
def state_home(home, source, sid):
    """Seed only synthetic fixture files in the actual runner's journaled state."""
    with ExitStack() as held:
        for rel in ("config.toml", "credentials/kimi-code.json"):
            target = home / rel
            target.touch(exist_ok=False)
            grant_file(target, sid, "read")
            target.write_bytes((source / rel).read_bytes())
            held.callback(NativeHold(target).close)
        for filename, data in (("workspaces.json", b"{}\n"),
                               ("device_id", b"12345678-1234-4123-8123-123456789abc")):
            target = home / filename
            target.write_bytes(data)
            grant_file(target, sid, "modify")
        yield home


READ_ROLE_POLICY = '\n[tools]\nenabled = ["Read"]\n'


@pytest.mark.parametrize("case", [
    "read-only", "shell-unconfigured", "session", "read-role", "read-role-no-shell"])
def test_native_session_before_a_prompt(tmp_path, native_files, case, monkeypatch):
    from conductor.command.adapters import _winlaunch as native
    from tests import test_kimi_home_loan_native as fixture

    if case.startswith("read-role"):
        monkeypatch.setattr(fixture, "CONFIG", fixture.CONFIG + READ_ROLE_POLICY)

    site = RelaySite(tmp_path, relay=False)
    kit = install(site, *native_files)
    runner = ProcessRunner(site.root)
    with fixture_home(site) as (source, anchor, token), ownership.acquire_owner(site.root):
        configure(site, kit / "kimi.exe")
        with runner.container_profile(mode="review", internet_client=False,
                                      folders=folders(site, anchor),
                                      kimi_state=case != "read-only") as (boundary, paths):
            assert not boundary.internet_client and identity(paths["home"]) == anchor.identity
            sid, parent = boundary.sid, paths["parent"]
            with ExitStack() as held:
                receipt = held.enter_context(verified_bundle(kit))
                exe, shell = Path(receipt["executable"]), Path(receipt["shell"])
                home = (source if case == "read-only" else held.enter_context(
                    state_home(paths["kimi_state"], source, sid)))
                env = {**base_environment(paths["runtime"]), **dict(KIMI_PROFILE.forced_env),
                       "KIMI_CODE_HOME": str(home)}
                if case not in {"shell-unconfigured", "read-role-no-shell"}:
                    env["KIMI_SHELL_PATH"] = str(shell)
                else:
                    # This opt-in control measures a host without another Git installation
                    # at Kimi 0.38.0's built-in fallback locations. A host that supplies one
                    # can still run the two other controls.
                    defaults = [Path(base, "Git", part, "bash.exe")
                                for base in ("C:/Program Files", "C:/Program Files (x86)")
                                for part in ("bin", "usr/bin")]
                    defaults.append(Path(env["LOCALAPPDATA"], "Programs/Git/bin/bash.exe"))
                    defaults.extend(Path(p, "git.exe") for p in env["PATH"].split(os.pathsep))
                    if any(p.is_file() for p in defaults):
                        pytest.skip("the missing-shell control needs no host fallback Git Bash")
                request = {"jsonrpc": "2.0", "id": 3, "method": "session/new",
                           "params": {"cwd": str(site.root / "work/t1"), "mcpServers": []}}
                frames = KIMI_AUTH_INPUT + json.dumps(request).encode() + b"\n"
                assert [json.loads(line)["method"] for line in frames.splitlines()] == [
                    "initialize", "authenticate", "session/new"]
                inputs = {n: sha(source / n) for n in ("config.toml", "credentials/kimi-code.json")}
                result = runner.run(CommandSpec(
                    (str(exe), "acp"), "work/t1", env=env, boundary=boundary, timeout_seconds=30,
                    output_limit=32768, stdin_bytes=frames, separate_stderr=True,
                    stdin_completion_id=3, sensitive_extra=(b"synthetic-stage-access",)))
                assert not result.output_truncated and not result.output_contains_env_value
                assert result.status == "completed" and result.exit_code == 0
                replies = [json.loads(line) for line in result.output.splitlines()]
                by_id = {row["id"]: row for row in replies if "id" in row}
                assert all(isinstance(by_id[n].get("result"), dict) for n in (1, 2))
                if case in {"session", "read-role"}:
                    error = json.dumps(by_id[3].get("error", {})).lower()
                    assert "result" in by_id[3], [
                        word for word in ("git bash was not found", "permission denied", "runtime",
                                          "not found", "access denied") if word in error]
                    issued = by_id[3]["result"]["sessionId"]
                    assert isinstance(issued, str) and issued
                    sessions = Path(extended(home / "sessions"))
                    assert any(p.is_dir() and p.name in {issued, "session_" + issued}
                               for p in sessions.glob("*/*"))
                else:
                    error = by_id[3]["error"]
                    assert error["code"] == -32603
                    phrase = ("permission denied" if case == "read-only" else
                              "git bash was not found on this windows host")
                    assert phrase in json.dumps(error).lower()
                assert all(sha(home / n) == sha(source / n) == digest
                           for n, digest in inputs.items())
                assert (source / "credentials/kimi-code.json").read_bytes() == token
        assert native.inspect_profile(sid) is None and not parent.exists()
    assert not runner.active_tokens()


@pytest.mark.skipif(os.environ.get("CONDUCT_TEST_KIMI_SHELL_EXEC") != "1",
                    reason="opt-in acceptance of shell execution inside AppContainer")
def test_native_shell_can_report_its_version(tmp_path, native_files):
    """Exercise the shell itself; a positive ACP session does not execute a shell command."""
    from conductor.command.adapters import _winlaunch as native
    from conductor.command.adapters.process_boundary import AttemptFolders

    site = RelaySite(tmp_path, relay=False)
    kit = install(site, *native_files)
    with ownership.acquire_owner(site.root):
        runner = ProcessRunner(site.root)
        configure(site, kit / "kimi.exe")
        folders = AttemptFolders("work/t1", None, str(site.install))
        profile = runner.container_profile(mode="review", internet_client=False, folders=folders)
        with profile as pair:
            boundary, paths = pair
            assert not boundary.internet_client
            env = base_environment(paths["runtime"])
            env["HOME"] = str(paths["runtime"])
            with verified_bundle(kit) as receipt:
                result = runner.run(CommandSpec(
                    (receipt["shell"], "--noprofile", "--norc", "--version"), "work/t1",
                    env=env, boundary=boundary, timeout_seconds=12, output_limit=8192))
            sid, parent = boundary.sid, paths["parent"]
        assert native.inspect_profile(sid) is None and not parent.exists()
        assert not runner.active_tokens()
    assert result.status == "completed" and not result.output_truncated
    output = result.output.lower()
    known_msys_denial = (b"ntcreatedirectoryobject(" in output and b"0xc0000022" in output)
    assert result.exit_code == 0 and b"gnu bash, version" in output, (
        f"exit={result.exit_code}, MSYS named-object access denied={known_msys_denial}")
