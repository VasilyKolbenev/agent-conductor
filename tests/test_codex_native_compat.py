"""P9: three bounded, credential-free Codex commands through the native attempt door.

Opt in with CONDUCT_CODEX_NATIVE_EXE pointing at the protected 0.164.0 install. The
version command uses dispatch, login status uses review and a synthetic access-only
login, and doctor uses dispatch with an empty home. Doctor also requires a fresh,
absolute CONDUCT_CODEX_NATIVE_LOG file path for its complete JSON output. No exec,
prompt, real login or model call is made. One native file per process; a failed
observation stops the next case. Run the protected-install preflight before this file.

These witnesses establish native startup and cleanup, not subscription inference or
an independently checked task. They reuse the lifecycle of test_relay_claude_native.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from conductor import ownership, ownership_login, ownership_transition
from conductor.command.adapters import process_boundary, process_loans
from conductor.command.adapters.codex_cli import CODEX_PROTOCOL, CODEX_PROVIDER_ID
from conductor.command.adapters.codex_relay import AUTH_STORE_ARGV
from conductor.command.adapters.harness_attempt import install_folder
from conductor.command.adapters.process import ProcessRunner, STDIN_NOT_PROVIDED
from conductor.command.adapters.process_boundary import WindowsContainer
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.providers import resolve_providers
from conductor.command.work_layout import work_route
from tests.relay_credentials import codex_leaf, epoch_seconds, jwt, put
from tests.relay_roads import digests
from tests.test_command_codex_transport import a_request
from tests.test_process_login_native import snapshot_of
from tests.test_process_loans_native import entries_naming, same_acl

EXE_VARIABLE = "CONDUCT_CODEX_NATIVE_EXE"
LOG_VARIABLE = "CONDUCT_CODEX_NATIVE_LOG"
EXE = os.environ.get(EXE_VARIABLE, "")
PINNED = ("DecemberCommand", "harnesses", "codex", "0.164.0", "node_modules", "@openai",
          "codex-win32-x64", "vendor", "x86_64-pc-windows-msvc", "bin", "codex.exe")
SHA256 = "6f267830b029ee25d9339864aa867cd45de9f8fd4c5ea007d2e63c13a0c66d36"
TIMEOUT = 60
WORK_ITEM = "work-001"
CASES = ("version-dispatch", "status-review", "doctor-dispatch")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture(scope="module")
def verified_exe(request):
    # Only the native cases opt in; JSON/log guard tests below remain offline and always run.
    if os.name != "nt":
        pytest.skip("native Codex AppContainer compatibility")
    if not EXE:
        pytest.skip(f"P9 needs {EXE_VARIABLE}: the protected Codex binary")
    exe = Path(EXE)
    expected = Path(os.environ["USERPROFILE"], *PINNED)
    assert exe.is_absolute() and os.path.normcase(exe) == os.path.normcase(expected), (
        "P9 STOP: the opt-in path is not the protected 0.164.0 binary")
    assert exe.is_file(), "P9 STOP: the protected binary is absent"
    with exe.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == SHA256, (
            "P9 STOP: the pinned binary hash differs from the P0 inventory")
    assert len({item.nodeid.split("::")[0] for item in request.session.items}) == 1, (
        "P9 STOP: run this native file in its own process")
    return exe


def _site(base, exe, signed_in):
    root = (base / "project").resolve()
    (root / "conductor").mkdir(parents=True)
    ownership_transition.activate(root, legacy_writers_stopped=True)
    login = (base / "DecemberCommand" / "logins" / "codex").resolve()
    if signed_in:
        expiry = datetime.now(timezone.utc) + timedelta(hours=4)
        put(login, "auth.json", codex_leaf(access_token=jwt({
            "sub": "fake-subject", "exp": epoch_seconds(expiry)})))
    system = os.environ["SystemRoot"]
    config = ProviderConfig(
        provider_id=CODEX_PROVIDER_ID, executable=str(exe), protocol=CODEX_PROTOCOL,
        env_allow=("SystemRoot", "windir"),
        auth="subscription" if signed_in else "api_key",
        auth_home=str(login) if signed_in else "")
    counter = iter(range(1, 1000))
    resolved = resolve_providers(
        [config], root=root, clock=_now, ids=lambda kind: f"{kind}-{next(counter)}",
        environ={"SystemRoot": system, "windir": system,
                 "USERPROFILE": os.environ["USERPROFILE"]}, confine_platform="win32")
    return root, login, resolved.registry.resolve(CODEX_PROVIDER_ID)


def _new_doctor_log(value):
    path = Path(value)
    assert value and path.is_absolute(), "P9 STOP: doctor needs an absolute new log path"
    assert path.parent.is_dir(), "P9 STOP: doctor log parent does not exist"
    assert not os.path.lexists(path), "P9 STOP: doctor log already exists"
    return path


def _save_doctor_log(path, output):
    # Exclusive creation also refuses a file planted after the pre-spawn check.
    with path.open("xb") as stream:
        stream.write(output)


def _checked_doctor(output, exit_code, expected_rg):
    # P9 measured exit 1 in an empty home. S164 doctor.rs:1294-1301 reports missing auth as
    # Fail; :346-347 maps any Fail to exit 1. The 401 WebSocket result is only Warning.
    # An unconditional exit-0 criterion was wrong; an arbitrary exit-1 exemption is wrong too.
    # S164 is 6aaac694803004a63c6f393d153c96d22521a6b9, cli/src/doctor{,/runtime}.rs.
    assert exit_code == 1, f"P9 STOP: unexpected empty-home doctor exit {exit_code}"
    report = json.loads(output)
    assert isinstance(report, dict), "P9 STOP: doctor report is not an object"
    assert report.get("schemaVersion") == 1 and report.get("codexVersion") == "0.164.0"
    assert report.get("overallStatus") == "fail"
    checks = report.get("checks")
    assert isinstance(checks, dict) and checks, "P9 STOP: missing doctor checks"
    assert all(isinstance(row, dict) and row.get("id") == name
               and row.get("status") in {"ok", "warning", "fail"}
               for name, row in checks.items()), "P9 STOP: malformed doctor check"
    assert {name for name, row in checks.items() if row["status"] == "fail"} == {
        "auth.credentials"}, "P9 STOP: doctor failure is not exclusively missing auth"
    assert checks["auth.credentials"].get("summary") == "no Codex credentials were found"
    search = checks.get("runtime.search", {})
    assert search.get("status") == "ok", "P9 STOP: packaged search helper is not ready"
    details = search.get("details", {})
    assert details.get("search provider") == "bundled"
    assert details.get("search command readiness") == "file exists"
    command = details.get("search command")
    assert (isinstance(command, str)
            and os.path.normcase(command) == os.path.normcase(expected_rg)), (
                "P9 STOP: doctor did not name the exact protected packaged search helper")
    return report


@pytest.mark.parametrize("case", CASES)
def test_codex_native_startup_and_cleanup(case, tmp_path, verified_exe, request):
    assert not request.session.testsfailed, "P9 STOP: an earlier native observation failed"
    command, mode = case.split("-")
    signed_in = command != "doctor"
    argv = {"version": ("--version",),
            "status": (*AUTH_STORE_ARGV, "login", "status"),
            "doctor": (*AUTH_STORE_ARGV, "doctor", "--json")}[command]
    log_path = _new_doctor_log(os.environ.get(LOG_VARIABLE, "")) if not signed_in else None
    root, login, adapter = _site(tmp_path, verified_exe, signed_in)
    action = a_request(timeout=TIMEOUT)
    runner = adapter._runner
    original_profile, original_run = runner.container_profile, runner.run
    seen = {}

    @contextlib.contextmanager
    def profile(**entry):
        with original_profile(**entry) as (boundary, paths):
            seen.update(sid=boundary.sid, paths=dict(paths), mode=entry["mode"])
            yield boundary, paths

    def run(spec):
        assert tuple(spec.argv) == (str(verified_exe), *argv), (
            "P9 STOP: the spec is not the one permitted non-inference command")
        assert not spec.stdin_bytes and spec.timeout_seconds == TIMEOUT
        assert spec.separate_stderr is False  # status and doctor report diagnostics on stderr
        assert isinstance(spec.boundary, WindowsContainer)
        home = Path(spec.env["CODEX_HOME"])
        seen.update(spec=spec, home=home)
        if not signed_in:
            assert list(home.iterdir()) == [], "P9 doctor needs an initially empty home"
        outcome = original_run(spec)
        if not signed_in:
            # Empty home and closed env only. Preserve ALL returned bytes before any assertion;
            # a truncated report still remains diagnostic evidence, but cannot pass P9.
            _save_doctor_log(log_path, outcome.output)
        seen["home_names"] = tuple(sorted(str(path.relative_to(home)) for path in home.rglob("*")))
        return outcome

    outcome = None
    failure = None
    before = {}
    login_before = digests(login) if signed_in else {}
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(process_loans, "configured_login_homes",
                          lambda _root: (login,) if signed_in else ())
            patch.setattr(runner, "container_profile", profile)
            patch.setattr(runner, "run", run)
            with ownership.acquire_owner(root):
                work = adapter._workspace.work_dir(WORK_ITEM)
                if signed_in:
                    assert adapter._relay_start(mode) is None
                    with ProcessRunner.login_write_guard(root, str(login)):
                        assert adapter._relay_preflight(action) is None
                watched = {"install": Path(install_folder(str(verified_exe))), "work": work}
                if signed_in:
                    watched.update(login=login, logins=login.parent)
                before = {name: snapshot_of(path) for name, path in watched.items()}
                outcome = adapter._attempt(
                    argv, work_route(WORK_ITEM), mode=mode, claim=adapter._claim_of(action),
                    timeout=TIMEOUT, separate_stderr=False)
    except Exception as error:
        failure = type(error).__name__

    # Inspect cleanup even if a launch was lost; never clear an uncertain lease here.
    assert runner.active_tokens() == (), "P9 STOP: the runner retains a child"
    assert (adapter._retained, adapter._login_residue) == (0, 0), "P9 STOP: retained home"
    if "home" in seen:
        assert not seen["home"].exists(), "P9 STOP: the attempt home remains"
    if signed_in:
        assert digests(login) == login_before, "P9 STOP: the synthetic source changed"
    for name in before:
        assert same_acl(snapshot_of(watched[name]), before[name]), f"P9 STOP: changed {name} ACL"
        if "sid" in seen:
            assert entries_naming(watched[name], seen["sid"]) == [], f"P9 STOP: {name} grant"
    if "sid" in seen:
        from conductor.command.adapters import _winlaunch

        assert _winlaunch.inspect_profile(seen["sid"]) is None, "P9 STOP: profile remains"
    assert process_boundary.LOGIN_LOAN_OPEN is False
    assert failure is None, f"P9 STOP: {failure}; launch was not repeated"
    assert outcome is not None and outcome.status == "completed", "P9 STOP: incomplete child"
    if command != "doctor":
        assert outcome.exit_code == 0, f"P9 STOP: child exit {outcome.exit_code}"
    assert outcome.stdin_state == STDIN_NOT_PROVIDED
    assert not outcome.output_truncated
    if command != "doctor":
        assert not outcome.output_contains_env_value
    assert seen["mode"] == mode and seen["spec"].boundary.sid == seen["sid"]
    runtime = str(seen["paths"]["runtime"])
    assert {seen["spec"].env[name] for name in ("TEMP", "TMP", "LOCALAPPDATA")} == {runtime}
    assert Path(runtime).is_absolute() and seen["home"] != login
    combined = outcome.output
    if command == "version":
        assert outcome.output.strip() == b"codex-cli 0.164.0"
    elif command == "status":
        assert b"Logged in using ChatGPT" in combined
    else:
        expected_rg = verified_exe.parent.parent / "codex-path" / "rg.exe"
        _checked_doctor(combined, outcome.exit_code, expected_rg)
    journal = root / "conductor.v3" / "process-profiles"
    phases = {path.name.split("-")[0]: json.loads(path.read_text(encoding="utf-8"))["phase"]
              for path in journal.iterdir()}
    assert phases == {"profile": "retired", "acl": "retired", "loan": "retired"}
    with ownership.acquire_owner(root):
        if signed_in:
            with ProcessRunner.login_write_guard(root, str(login)):
                pass
    if signed_in:
        assert not (ownership_login.box_key(str(login))[1] / "active.json").exists()
    print(json.dumps({"case": case, "exit_code": outcome.exit_code,
                      "home_names": seen["home_names"]}, ensure_ascii=True))


def _doctor_fixture(rg):
    return {"schemaVersion": 1, "codexVersion": "0.164.0", "overallStatus": "fail", "checks": {
        "auth.credentials": {"id": "auth.credentials", "status": "fail",
                             "summary": "no Codex credentials were found"},
        "runtime.search": {"id": "runtime.search", "status": "ok", "details": {
            "search command": str(rg), "search provider": "bundled",
            "search command readiness": "file exists"}},
        "network.websocket_reachability": {"id": "network.websocket_reachability",
                                            "status": "warning", "notes": ["HTTP 401"]}}}


def test_doctor_guard_accepts_only_the_expected_missing_auth_result(tmp_path):
    rg = tmp_path / "protected" / "codex-path" / "rg.exe"
    report = _doctor_fixture(rg)
    assert _checked_doctor(json.dumps(report).encode(), 1, rg) == report


@pytest.mark.parametrize("path,value", [
    (("checks", "network.websocket_reachability", "status"), "fail"),
    (("checks", "network.websocket_reachability", "status"), "unknown"),
    (("checks", "auth.credentials", "status"), "ok"),
    (("checks", "auth.credentials", "summary"), "stored credentials could not be read"),
    (("checks", "runtime.search", "status"), "warning"),
    (("checks", "runtime.search", "details", "search provider"), "system"),
    (("checks", "runtime.search", "details", "search command readiness"), "missing"),
    (("checks", "runtime.search", "details", "search command"), "rg.exe"),
    (("overallStatus",), "ok"),
])
def test_doctor_guard_refuses_an_unexplained_failure_or_wrong_helper(tmp_path, path, value):
    rg = tmp_path / "protected" / "codex-path" / "rg.exe"
    report = _doctor_fixture(rg)
    target = report
    for name in path[:-1]:
        target = target[name]
    target[path[-1]] = value
    with pytest.raises(AssertionError):
        _checked_doctor(json.dumps(report).encode(), 1, rg)


@pytest.mark.parametrize("output", [b"{", b"{}", b"[]"])
def test_doctor_guard_refuses_incomplete_evidence(output, tmp_path):
    with pytest.raises((AssertionError, json.JSONDecodeError)):
        _checked_doctor(output, 1, tmp_path / "rg.exe")


@pytest.mark.parametrize("exit_code", [0, 2])
def test_doctor_guard_refuses_an_unexpected_exit(tmp_path, exit_code):
    rg = tmp_path / "protected" / "codex-path" / "rg.exe"
    with pytest.raises(AssertionError, match="unexpected"):
        _checked_doctor(json.dumps(_doctor_fixture(rg)).encode(), exit_code, rg)


def test_doctor_log_keeps_the_full_report_and_never_overwrites(tmp_path):
    path = _new_doctor_log(str(tmp_path / "doctor.json"))
    output = json.dumps({"diagnostic": "evidence" * 1000}).encode()
    _save_doctor_log(path, output)
    assert path.read_bytes() == output
    with pytest.raises(AssertionError, match="already exists"):
        _new_doctor_log(str(path))
    with pytest.raises(FileExistsError):
        _save_doctor_log(path, b"replacement")
    assert path.read_bytes() == output


def test_doctor_log_refuses_an_implicit_relative_destination():
    with pytest.raises(AssertionError, match="absolute"):
        _new_doctor_log("doctor.json")
