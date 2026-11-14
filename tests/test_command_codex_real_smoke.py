"""OPT-IN smoke against a REAL Codex CLI install. Skips honestly; never fakes a pass.

No vendor process runs unless an operator points this file at a real install; nothing
installs, downloads or searches for one. The synthetic witness guard runs offline.
A missing install is an honest skip, never a success:

    CONDUCT_CODEX_EXECUTABLE    absolute path to the codex binary

The npm package ships a Node shim that spawns a vendored native binary; what this
build pins is the BINARY, which on Windows stands at
``node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe``
under the reviewed 0.164.0 install root, with its package resources intact.

The prompt smoke needs one more opt-in and a real key, because it spends a real
model call:

    CONDUCT_CODEX_REAL_PROMPT=1
    CONDUCT_CODEX_KEY_NAME      the env NAME holding the key, itself set
                                (``OPENAI_API_KEY`` unless a deployment renames
                                it)

The version smoke compares the install's printed version with the production parser.
The paid pipe smoke requires a marker present only in stdin, read through the production
retention seam before the attempt home is discarded. File existence alone proves nothing.
The no-auth project-layer pair compares clean/untrusted execution with a trusted control:
an invalid TOML layer must be ignored when untrusted and rejected when trusted.

Everything the module reaches the child through goes via the production retention
path; ``tests/test_real_smoke_retention.py`` guards that with tests that cannot
skip.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace

import pytest

from conductor.command.adapters.codex_cli import (
    CODEX_PROTOCOL,
    CODEX_PROVIDER_ID,
    HOME_DIR,
    LAST_MESSAGE_NAME,
    MARKER_DIR,
    REVIEWED_CODEX_VERSION,
)
from conductor.command.adapters.headless_cli import _version_token
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.providers import resolve_providers
from conductor.command.adapters.process import CommandSpec

from tests.test_command_codex_transport import NOW, _Ids, a_request

EXECUTABLE_ENV = "CONDUCT_CODEX_EXECUTABLE"
PROMPT_ENV = "CONDUCT_CODEX_REAL_PROMPT"
KEY_NAME_ENV = "CONDUCT_CODEX_KEY_NAME"
P8_DIAGNOSTIC_ENV = "CONDUCT_CODEX_P8_DIAGNOSTIC"

#: The observed form, SPELLED here rather than imported from the adapter: a check
#: that read the shipped pattern would move with it, and the whole point of this
#: file is to be the one place that does not.
_OBSERVED_FORM = re.compile(r"\Acodex-cli (?P<semver>\d+\.\d+\.\d+)\Z")


def _pin() -> str:
    """The one pin, or an honest skip naming exactly what is missing."""
    value = os.environ.get(EXECUTABLE_ENV, "")
    if not value:
        pytest.skip(f"no real Codex CLI install: {EXECUTABLE_ENV} is not set")
    if not Path(value).is_absolute():
        pytest.skip(
            f"no real Codex CLI install: {EXECUTABLE_ENV} is not an absolute path")
    if not Path(value).is_file():
        pytest.skip(
            f"no real Codex CLI install: {EXECUTABLE_ENV} names no file on disk")
    return value


def _real_harness(tmp_path: Path, names: tuple[str, ...] = ()):
    executable = _pin()
    root = tmp_path / "root"
    root.mkdir()
    # Windows DNS returned WSANO_RECOVERY (11003) with env={}, resolved with only this name.
    # Python normalizes the Windows environment to uppercase before the runner snapshots it.
    runtime_names = ("SYSTEMROOT",) if os.name == "nt" else ()
    resolution = resolve_providers(
        [ProviderConfig(
            provider_id=CODEX_PROVIDER_ID, executable=executable,
            protocol=CODEX_PROTOCOL, env_allow=tuple(dict.fromkeys((*names, *runtime_names))))],
        root=root, clock=lambda: NOW, ids=_Ids(),
        confine_platform=None)  # a real install, driven plain: opt-in, not the production door
    contract = next(
        row for row in resolution.contracts if row.provider_id == CODEX_PROVIDER_ID)
    assert contract.available is True, "the pin is on disk, so this must be available"
    return resolution.registry.resolve(CODEX_PROVIDER_ID), root


def test_real_harness_admits_only_the_explicit_windows_dns_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("SystemRoot", "C:\\synthetic-windows")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key-not-forwarded")
    monkeypatch.setenv("UNRELATED_PARENT_SETTING", "not-forwarded")
    # The file is never spawned: resolve the actual runner, not just a captured config row.
    monkeypatch.setattr(sys.modules[__name__], "_pin", lambda: sys.executable)
    adapter, _root = _real_harness(tmp_path)
    captured = adapter._runner.capture_environment(adapter._env_allow())
    expected = {"SYSTEMROOT": "C:\\synthetic-windows"} if os.name == "nt" else {}
    assert dict(captured.values) == expected


@pytest.mark.parametrize("failure", ["exact", "other_failure", "wrong_path", "zero", "timeout"])
def test_trusted_project_control_adds_only_windows_systemroot(tmp_path, monkeypatch, failure):
    root = tmp_path / "root"
    root.mkdir()
    adapter = SimpleNamespace(_pin=SimpleNamespace(executable="synthetic-codex"),
                              _stdin_argv=lambda _home, _model: ("exec", "-"))
    monkeypatch.setenv("SystemRoot", "C:\\synthetic-windows")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key-not-forwarded")
    monkeypatch.setattr(sys.modules[__name__], "_real_harness", lambda _path: (adapter, root))
    monkeypatch.delenv(PROMPT_ENV, raising=False)
    diagnostic = tmp_path / "trusted-failure.json"
    monkeypatch.setenv(P8_DIAGNOSTIC_ENV, str(diagnostic))
    captured = []
    planted = root / "work" / "work-001" / ".codex" / "config.toml"

    def run(argv, **options):
        captured.append(options["env"])
        assert options["timeout"] == 60
        if failure == "timeout":
            raise subprocess.TimeoutExpired(argv, 60, output=b"waiting for network")
        path = planted if failure != "wrong_path" else planted.with_name("config.toml.other")
        output = f"Error parsing project config file {path}: invalid TOML".encode()
        if failure == "other_failure":
            output = b"ERROR: unrelated failure mentioning PROBE_INVALID_PROJECT_LAYER"
        return SimpleNamespace(returncode=0 if failure == "zero" else 1, stdout=output)

    monkeypatch.setattr(subprocess, "run", run)
    if failure == "exact":
        test_the_poisoned_layer_really_fires_when_the_directory_is_trusted(tmp_path)
        assert not diagnostic.exists()
    else:
        with pytest.raises(AssertionError):
            test_the_poisoned_layer_really_fires_when_the_directory_is_trusted(tmp_path)
        row, = json.loads(diagnostic.read_text(encoding="utf-8"))["attempts"]
        assert row["status"] == ("timed_out" if failure == "timeout" else "completed")
        assert row["timeout_seconds"] == 60 and row["output_tail"]
    assert planted.read_text(encoding="utf-8") == "[PROBE_INVALID_PROJECT_LAYER\n"
    home = tmp_path / "trusted-home-outside-the-project"
    expected = {"CODEX_HOME": str(home), "TEMP": str(home / "tmp"), "TMP": str(home / "tmp")}
    if os.name == "nt":
        expected["SystemRoot"] = "C:\\synthetic-windows"
    assert captured == [expected]


def _seed_instruction(root: Path, text: str) -> None:
    instructions = root / "instructions"
    instructions.mkdir(exist_ok=True)
    (instructions / "instr-001.md").write_text(
        text, encoding="utf-8", newline="\n")


def _assert_the_production_parser_read_it(
        adapter, output: bytes, observed: str) -> None:
    """The production parser read the SAME semver this file read independently.

    This is the question a boolean cannot answer. `_version_matches` returning
    False means either "a different build" or "this parser read nothing at all",
    and a smoke that checked the form itself and then accepted any False could
    not tell them apart -- a production parser replaced with one that matches
    NOTHING passes that shape, against a valid form at a non-reviewed version.

    So the two parses are compared to each other. The expected semver comes from
    this file's own literal pattern, which is the whole reason that pattern is
    spelled here instead of imported from the adapter it exists to check.
    """
    described = _OBSERVED_FORM.match(observed)
    assert described is not None
    expected = described.group("semver")
    produced = adapter._parsed_version(output)
    assert produced == expected, (
        f"the production parser did not read the form this install printed: it "
        f"made {produced!r} of {observed!r}, where an independent reading of the "
        f"same form gives {expected!r}. A parser that reads nothing is "
        f"indistinguishable from a correct refusal unless this is checked")


def _assert_form_is_readable(observed: str) -> None:
    """The FORM question, asked separately from the version question.

    They fail differently and mean different things: a different version is an
    operator running another build, which the adapter is right to refuse; an
    unreadable form is this parser being wrong about the vendor, which no
    refusal can fix.

    For this provider the likeliest wrong form is a NAMED one: the source
    declares `bin_name = "codex"`, so an install printing `codex 0.164.0` would
    mean the crate was renamed and this pattern must follow it. That is a
    finding about the PARSER, and it is widened in review.
    """
    assert _OBSERVED_FORM.match(observed) is not None, (
        f"the install prints a form this parser cannot read at all: "
        f"{observed!r} -- expected `codex-cli <semver>`. This is a finding "
        f"about the PARSER, not about the build, and it is widened in review")


def test_a_real_install_prints_a_form_this_adapter_can_parse(tmp_path):
    """The parser meets a real binary, which is the only place it can be settled.

    It carries more weight here than for any other provider: the reviewed number
    was READ from a binary rather than from a file, so this print is the only
    statement of it that exists. If a real install prints a shape this parser
    refuses, this fails with both strings in the message.
    """
    adapter, root = _real_harness(tmp_path)
    _seed_instruction(root, "Report the current directory and change nothing.")
    adapter._workspace.work_root()
    outcome = adapter._attempt(("--version",), "work", timeout=60)

    assert outcome.status == "completed", (
        "the pinned Codex CLI did not exit within the preflight budget")
    assert outcome.exit_code == 0, "the pinned build failed to report a version"

    observed = _version_token(outcome.output)
    assert observed, "the pinned Codex CLI printed no version token at all"

    _assert_form_is_readable(observed)
    _assert_the_production_parser_read_it(adapter, outcome.output, observed)
    parsed = adapter._version_matches(outcome.output)

    request = a_request()
    receipt = adapter.execute(adapter.prepare(request))
    if parsed:
        # The reviewed build: the task was allowed to run, and whatever it did
        # the receipt is an OBSERVATION -- this smoke claims nothing about it.
        assert receipt.outcome in {"succeeded", "failed", "unknown", "cancelled"}
    else:
        assert receipt.outcome == "failed", (
            f"an unreviewed build must be refused, not run (installed "
            f"{observed!r}, reviewed {REVIEWED_CODEX_VERSION!r})")
        assert REVIEWED_CODEX_VERSION in receipt.detail
        assert observed not in receipt.detail, (
            "the observed version is raw child output and must never be echoed")
        # The form already matched above, so reaching here means one thing only:
        # a build that is not the reviewed one, refused correctly.
        assert REVIEWED_CODEX_VERSION not in observed, (
            f"the form matched and the version did too, yet the parser refused: "
            f"{observed!r} -- this is a parser defect, not an unreviewed build")


def test_no_codex_state_is_left_anywhere_a_real_install_would_have_put_it(tmp_path):
    """`CODEX_HOME` relocates the config directory, and this vendor REQUIRES it
    to exist -- so a real preflight runs inside a directory this build made, and
    after the spawn returns none of it may still stand under this build's home
    root. The operator's own ``~/.codex`` is untouched."""
    adapter, root = _real_harness(tmp_path)
    adapter._workspace.work_root()

    outcome = adapter._attempt(("--version",), "work", timeout=60)

    assert outcome.status == "completed"
    homes = root / HOME_DIR
    standing = sorted(path.name for path in homes.iterdir()) if homes.is_dir() else []
    assert standing == [], f"REAL_INSTALL_LEFT_STATE_STANDING={standing}"


def _collecting_final_messages(adapter, patches) -> list[str]:
    """Read each spawn's final message from inside the transport's own seam.

    The file stands inside the attempt home, which is discarded the instant
    `_attempt` returns, so this is the one moment it exists. The production
    reading still runs: what is added is a copy taken for this process only,
    and it never leaves the test.
    """
    answers: list[str] = []
    read_home = adapter._read_attempt_home

    def watched(home):
        target = home / LAST_MESSAGE_NAME
        if target.is_file():
            answers.append(target.read_text(encoding="utf-8", errors="replace"))
        return read_home(home)

    patches.setattr(adapter, "_read_attempt_home", watched)
    return answers


def _collecting_dispatch_outcomes(adapter, patches, diagnostics) -> list:
    """Keep bounded child outcomes without bypassing attempt retention or leaking a wrapper."""
    seen = []
    attempt = adapter._attempt

    def watched(*args, **kwargs):
        if kwargs.get("mode") != "dispatch":
            return attempt(*args, **kwargs)
        row = {}
        launch = adapter._runner._launch

        def observed(spec, cwd, env, payload, loan):
            row.update(argv=list(spec.argv), cwd=str(cwd), env_names=sorted(env),
                       timeout_seconds=spec.timeout_seconds,
                       original_separate_stderr=spec.separate_stderr,
                       capture_separate_stderr=False)
            # This NO-AUTH witness needs the vendor diagnostic the product discards.
            # Only pipe routing changes: the existing bounded pump/lifecycle still owns it.
            return launch(replace(spec, separate_stderr=False), cwd, env, payload, loan)

        started = time.monotonic()
        with pytest.MonkeyPatch.context() as launch_patch:
            launch_patch.setattr(adapter._runner, "_launch", observed)
            outcome = attempt(*args, **kwargs)
        row.update(elapsed_seconds=round(time.monotonic() - started, 3),
                   status=outcome.status, exit_code=outcome.exit_code,
                   output_truncated=outcome.output_truncated,
                   output_contains_env_value=outcome.output_contains_env_value,
                   stdin_state=getattr(outcome, "stdin_state", "not_reported"))
        try:
            row["canonical_error_sha256"] = _failed_auth_fingerprint(outcome)
        except AssertionError:
            row["canonical_error_sha256"] = None
        diagnostics.append((row, outcome.output))
        seen.append(outcome)
        return outcome

    patches.setattr(adapter, "_attempt", watched)
    return seen


def _p8_diagnostic_path():
    value = os.environ.get(P8_DIAGNOSTIC_ENV)
    if not value:
        return None
    assert not os.environ.get(PROMPT_ENV), "P8 diagnostics are forbidden for the paid smoke"
    path = Path(value)
    assert path.is_absolute() and path.parent.is_dir(), "use an existing absolute report parent"
    assert not path.exists(), "P8 diagnostics never overwrite an existing artifact"
    return path


def _write_p8_failure(path, diagnostics):
    if path is None:
        return
    attempts = []
    for metadata, output in diagnostics:
        row = dict(metadata)
        withheld = row["output_contains_env_value"]
        tail = "" if withheld else output[-8192:].decode("utf-8", errors="replace")
        # No credentials are admitted by this test; suppress recognizable secret lines too.
        tail = "\n".join(
            "[sensitive diagnostic line withheld]" if re.search(
                r"authorization|bearer\s|(?:api[_ -]?key|(?:access|refresh)[_ -]?token)\s*[=:]"
                r"|\beyJ[A-Za-z0-9_-]{15,}\.|\bsk-[A-Za-z0-9_-]{15,}", line, re.I)
            else re.sub(r"(https?://[^\s?#]+)[?#][^\s]*", r"\1[query withheld]", line)
            for line in tail.splitlines())
        # Replacement characters and redaction text can grow; enforce the artifact bound too.
        tail = tail.encode("utf-8")[-8192:].decode("utf-8", errors="ignore")
        row.update(output_tail=tail, output_withheld=withheld,
                   captured_output_bytes=len(output), diagnostic_tail_truncated=len(output) > 8192)
        attempts.append(row)
    payload = json.dumps({"witness": "P8 no-auth project layer", "attempts": attempts},
                         ensure_ascii=True, indent=2).encode("utf-8")
    with path.open("xb") as artifact:
        artifact.write(payload)


@pytest.mark.parametrize("invalid", ["relative", "missing_parent", "existing", "paid"])
def test_p8_diagnostic_refuses_unsafe_or_non_noauth_destination(tmp_path, monkeypatch, invalid):
    monkeypatch.delenv(P8_DIAGNOSTIC_ENV, raising=False)
    assert _p8_diagnostic_path() is None
    path = tmp_path / "diagnostic.json"
    if invalid == "relative":
        value = "diagnostic.json"
    elif invalid == "missing_parent":
        value = str(tmp_path / "missing" / "diagnostic.json")
    else:
        value = str(path)
    if invalid == "existing":
        path.write_bytes(b"keep this artifact")
    if invalid == "paid":
        monkeypatch.setenv(PROMPT_ENV, "yes")
    monkeypatch.setenv(P8_DIAGNOSTIC_ENV, value)
    with pytest.raises(AssertionError):
        _p8_diagnostic_path()
    assert not (tmp_path / "missing").exists()
    if invalid == "existing":
        assert path.read_bytes() == b"keep this artifact"


def test_p8_diagnostic_exclusive_creation_and_redaction(tmp_path):
    path = tmp_path / "diagnostic.json"
    metadata = {"output_contains_env_value": False}
    output = (b"Reconnecting...\nAuthorization: Bearer synthetic-secret\n"
              b"ERROR: https://example.invalid/request?token=synthetic-secret\n")
    _write_p8_failure(path, [(metadata, output)])
    first = path.read_bytes()
    assert b"synthetic-secret" not in first
    assert b"Reconnecting..." in first
    with pytest.raises(FileExistsError):
        _write_p8_failure(path, [])
    assert path.read_bytes() == first


def _failed_auth_fingerprint(outcome) -> str:
    """Preserve the last error except S164's two per-request metadata IDs; retain its digest."""
    assert outcome.status == "completed" and outcome.exit_code not in (None, 0)
    assert not outcome.output_truncated, "truncated output cannot prove the poison was absent"
    assert not outcome.output_contains_env_value, "the witness must not expose environment data"
    said = outcome.output.decode("utf-8", errors="replace")
    poison_seen = any(marker in said for marker in (
        "PROBE_INVALID_PROJECT_LAYER", "Error parsing project config file"))
    assert not poison_seen, "an untrusted project layer reached the child"
    errors = [line.strip() for line in said.splitlines()
              if line.strip().casefold().startswith("error:")]
    assert errors, "the child must report a concrete failure, not merely leave -o absent"
    last = errors[-1]
    authentication_error = bool(re.search(
        r"auth|credentials|api key|not logged|log in|\b401\b", last, re.I))
    assert authentication_error, (
        "a non-auth failure cannot establish the uncredentialed project-layer witness")
    body, separator, metadata = last.rpartition(", url: ")
    if separator:
        parsed = re.fullmatch(
            r"(?P<url>(?:https?|wss?)://[^\s,]+)(?:, cf-ray: [A-Za-z0-9_-]{1,128})?"
            r"(?:, request id: [A-Za-z0-9_-]{1,128})?"
            r"(?P<auth>(?:, auth error: [^,\r\n]+)?(?:, auth error code: [^,\r\n]+)?)", metadata)
        if parsed is not None:  # Unknown suffixes keep every byte; never normalize the body.
            last = body + separator + parsed["url"] + parsed["auth"]
    return hashlib.sha256(last.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("old,new,equal", [
    ("cf-ray: ray-a", "cf-ray: ray-b", True),
    ("request id: req-a", "request id: req-b", True),
    (", cf-ray: ray-a", "", True), (", request id: req-a", "", True),
    ("401", "403", False), ("Missing bearer", "Expired bearer", False),
    ("api.openai.com", "elsewhere.invalid", False),
    ("request id: body-a", "request id: body-b", False),
    ("auth error: denied", "auth error: changed", False),
    ("auth error code: no-login", "auth error code: expired", False),
    ("request id: req-a", "request id: req-b, unknown: field", False)])
def test_auth_fingerprint_removes_only_known_metadata_ids(old, new, equal):
    message = ("ERROR: unexpected status 401 Unauthorized: Missing bearer; request id: body-a"
               ", url: https://api.openai.com/v1/responses, cf-ray: ray-a, request id: req-a"
               ", auth error: denied, auth error code: no-login")

    def fingerprint(text):
        return _failed_auth_fingerprint(SimpleNamespace(
            status="completed", exit_code=1, output=text.encode(), output_truncated=False,
            output_contains_env_value=False))

    assert (fingerprint(message) == fingerprint(message.replace(old, new))) is equal


# --- the project layer a previous action could leave in the work tree ---------

#: S164 strips model_provider even for trusted projects; invalid TOML distinguishes trust.
POISON = "[PROBE_INVALID_PROJECT_LAYER\n"
#: What the trust store looks like. Spelled here rather than derived, because
#: this is the vendor's shape and this file is where a change to it must show.
TRUST = '[projects."{key}"]\ntrust_level = "trusted"\n'


def _plant_project_layer(work: Path) -> Path:
    """Leave a `.codex/config.toml` where a previous action's model could."""
    layer = work / ".codex"
    layer.mkdir(parents=True, exist_ok=True)
    (layer / "config.toml").write_text(POISON, encoding="utf-8", newline="\n")
    return layer


@pytest.mark.parametrize("changed", [
    "same", "poison", "different", "empty", "timeout", "truncated", "noop", "env", "argument",
    "diagnostic", "diagnostic_env", "diagnostic_long", "same_diagnostic", "canonical"])
def test_project_layer_witness_distinguishes_child_outcomes_when_final_file_is_absent(
        tmp_path, monkeypatch, changed):
    """A failed receipt and absent -o file alone used to pass even when poison fired."""
    root = tmp_path / "synthetic-root"
    root.mkdir()
    normal = b"ERROR: Missing authentication credentials\n"
    second = {"poison": b"ERROR: Error parsing project config file PROBE_INVALID_PROJECT_LAYER\n",
              "different": b"ERROR: Different authentication failure\n",
              "empty": b"", "argument": b"ERROR: unknown argument --fake\n"}.get(changed, normal)
    if changed == "canonical":
        normal = b"ERROR: Missing bearer credentials"
        second = b"ERROR: Different bearer credentials"

    class Adapter:
        _answer = "absent"
        calls = 0

        def __init__(self):
            self.launched = []
            self._runner = SimpleNamespace(_launch=self.launch)

        def launch(self, spec, cwd, env, payload, loan):
            self.launched.append(spec)

        def prepare(self, request):
            return request

        def _attempt(self, *args, **kwargs):
            self.calls += 1
            spec = CommandSpec(argv=("synthetic-codex", "exec", "-"), cwd="work",
                               timeout_seconds=60, separate_stderr=True)
            self._runner._launch(spec, root, {"SYNTHETIC_NAME": "DO_NOT_SAVE"}, b"task", None)
            output = normal if self.calls == 1 else second
            if self.launched[-1].separate_stderr:
                output = b""  # Real exec diagnostics are on stderr, discarded on the product road.
            return SimpleNamespace(
                status="timed_out" if changed == "timeout" else "completed", exit_code=1,
                output=output,
                output_truncated=changed == "truncated", output_contains_env_value=changed == "env")

        def execute(self, prepared):
            if changed != "noop":
                self._attempt(("exec", "-"), "work", mode="dispatch")
            return SimpleNamespace(outcome="failed", detail="synthetic failure")

    adapter = Adapter()
    original = adapter._attempt
    original_launch = adapter._runner._launch
    monkeypatch.setattr(sys.modules[__name__], "_real_harness", lambda _path: (adapter, root))
    monkeypatch.delenv(P8_DIAGNOSTIC_ENV, raising=False)
    monkeypatch.delenv(PROMPT_ENV, raising=False)
    diagnostic = tmp_path / "failure.json"
    if changed.startswith("diagnostic") or changed in ("same_diagnostic", "canonical"):
        monkeypatch.setenv(P8_DIAGNOSTIC_ENV, str(diagnostic))
    if changed.startswith("diagnostic"):
        original_attempt = adapter._attempt

        def timeout_attempt(*args, **kwargs):
            result = original_attempt(*args, **kwargs)
            result.status = "timed_out"
            result.output = b"Reconnecting... waiting for network\n"
            if changed == "diagnostic_env":
                result.output = b"SYNTHETIC_SECRET_VALUE"
                result.output_contains_env_value = True
            if changed == "diagnostic_long":
                result.output = b"x" * 20000 + b"\nReconnecting...\n"
            return result

        adapter._attempt = timeout_attempt
        original = timeout_attempt

    if changed in ("same", "same_diagnostic"):
        test_a_project_layer_in_the_work_tree_changes_nothing_on_the_production_road(tmp_path)
    else:
        with pytest.raises(AssertionError):
            test_a_project_layer_in_the_work_tree_changes_nothing_on_the_production_road(tmp_path)

    assert adapter._attempt == original, "the capture wrapper must be scoped even on failure"
    assert adapter._runner._launch == original_launch, "stderr observation must never escape P8"
    expected = CommandSpec(argv=("synthetic-codex", "exec", "-"), cwd="work",
                           timeout_seconds=60, separate_stderr=False)
    assert all(spec == expected for spec in adapter.launched), "only stderr routing may change"
    if changed == "same_diagnostic":
        assert not diagnostic.exists(), "the opt-in artifact is for failures only"
    if changed == "canonical":
        rows = json.loads(diagnostic.read_text(encoding="utf-8"))["attempts"]
        assert [row["canonical_error_sha256"] for row in rows] == [
            hashlib.sha256(message).hexdigest() for message in (normal, second)]
        assert all(row["output_tail"] == "[sensitive diagnostic line withheld]" for row in rows)
    if changed == "timeout" or changed.startswith("diagnostic"):
        assert adapter.calls == 1, "a failed clean witness must stop before the poisoned launch"
    if changed.startswith("diagnostic"):
        saved = json.loads(diagnostic.read_text(encoding="utf-8"))
        assert len(saved["attempts"]) == 1
        row = saved["attempts"][0]
        assert row["status"] == "timed_out"
        assert row["elapsed_seconds"] >= 0
        assert row["argv"] == ["synthetic-codex", "exec", "-"]
        assert row["env_names"] == ["SYNTHETIC_NAME"]
        assert row["original_separate_stderr"] is True
        assert row["timeout_seconds"] == 60
        assert "DO_NOT_SAVE" not in diagnostic.read_text(encoding="utf-8")
        assert len(row["output_tail"].encode("utf-8")) <= 8192
        if changed == "diagnostic_env":
            assert "SYNTHETIC_SECRET_VALUE" not in diagnostic.read_text(encoding="utf-8")
            assert row["output_withheld"] is True
        else:
            assert "Reconnecting..." in row["output_tail"]
        assert row["diagnostic_tail_truncated"] == (changed == "diagnostic_long")


def test_a_project_layer_in_the_work_tree_changes_nothing_on_the_production_road(
        tmp_path):
    """The containment claim, asked of the REVIEWED binary rather than of source.

    This build spawns the child inside the run's own work subtree, and a
    `.codex/` left there by an earlier action is not swept: it stands outside
    the home root, so nothing this build discards reaches it. Whether it can
    reach the CHILD is therefore a vendor question, and the pinned source is not
    allowed to answer it -- that tree declares three flags this binary rejects,
    which is exactly how much its statements are worth here.

    Ask twice through the production road and capture bounded child output at `_attempt`.
    Both failures must reach authentication, omit the poison token and report the same final
    error. Codex 0.164.0 writes no `-o` file on Failed/Interrupted, so matching `_answer` alone
    would also pass if the poison fired. That secondary observation remains below.
    The trusted control must independently prove the poison can fire.

    No credential is forwarded. S164 can retry networking before reaching the auth error;
    stop after a failed clean witness, keeping the existing 60-second bound.
    """
    diagnostic_path = _p8_diagnostic_path()
    adapter, root = _real_harness(tmp_path)
    _seed_instruction(root, "Report the current directory and change nothing.")
    request = a_request()

    diagnostics = []
    try:
        with pytest.MonkeyPatch.context() as patches:
            seen = _collecting_dispatch_outcomes(adapter, patches, diagnostics)
            clean = adapter.execute(adapter.prepare(request))
            baseline = adapter._answer
            assert len(seen) == 1, "the clean attempt must actually reach the child"
            assert clean.outcome == "failed"
            clean_fingerprint = _failed_auth_fingerprint(seen[0])

            _plant_project_layer(root / "work" / request.arguments["work_item_id"])
            poisoned = adapter.execute(adapter.prepare(
                a_request(action_id="act-project-layer")))

        assert len(seen) == 2, "both task attempts must actually reach the child"
        assert poisoned.outcome == "failed"
        assert clean_fingerprint == _failed_auth_fingerprint(seen[1]), (
            "the untrusted project layer changed the child's final authentication error")
        assert baseline is not None, clean.detail
        assert adapter._answer == baseline, (
            "the untrusted project layer changed the final-message observation")
    except AssertionError:
        _write_p8_failure(diagnostic_path, diagnostics)
        raise


def test_the_poisoned_layer_really_fires_when_the_directory_is_trusted(tmp_path):
    """The control for the control: planted and TRUSTED, the layer takes effect.

    Without it the claim above is empty -- a `.codex/config.toml` that could
    never change anything would satisfy it on any install, including one that
    reads every project layer it finds.

    This one cannot go through the production road, and that is the point rather
    than a shortcut: the road mints a fresh `CODEX_HOME` per spawn and discards
    it, so a trust store is precisely the thing it can never produce. What is
    asked here is a question about the VENDOR -- given a trusted directory, does
    the layer take effect -- so it is asked of the same binary, with the same
    argv this transport builds, in a home that stands OUTSIDE the project root.
    The project's own home root is asserted untouched afterwards.
    """
    diagnostic_path = _p8_diagnostic_path()
    adapter, root = _real_harness(tmp_path)
    work = root / "work" / "work-001"
    work.mkdir(parents=True, exist_ok=True)
    planted = _plant_project_layer(work) / "config.toml"
    home = tmp_path / "trusted-home-outside-the-project"
    home.mkdir()
    scratch = home / "tmp"
    scratch.mkdir()
    (home / "config.toml").write_text(
        TRUST.format(key=str(work).replace("\\", "\\\\")),
        encoding="utf-8", newline="\n")
    child_env = {"CODEX_HOME": str(home), "TEMP": str(scratch), "TMP": str(scratch)}
    if os.name == "nt":
        child_env["SystemRoot"] = os.environ["SystemRoot"]

    argv = [adapter._pin.executable, *adapter._stdin_argv(home, None)]
    row = dict(argv=argv, cwd=str(work), env_names=sorted(child_env), timeout_seconds=60,
               output_contains_env_value=False, output_truncated=False)
    output = b""
    started = time.monotonic()
    try:
        try:
            done = subprocess.run(
                argv, cwd=str(work), env=child_env,
                input=b"Reply with the word ok and nothing else.",
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        except subprocess.TimeoutExpired as error:
            output = error.output or b""
            row.update(status="timed_out", exit_code=None)
            raise AssertionError("trusted project-layer control exceeded 60 seconds") from None
        output = done.stdout
        row.update(status="completed", exit_code=done.returncode)
        said = output.decode("utf-8", errors="replace")
        assert done.returncode != 0, "a trusted poisoned layer must not be shrugged off"
        poison_seen = f"Error parsing project config file {planted}:" in said
        assert poison_seen, "the control must reject the exact planted project config file"
        homes = root / HOME_DIR
        standing = sorted(path.name for path in homes.iterdir()) if homes.is_dir() else []
        assert standing == [], f"THE_CONTROL_LEFT_STATE_STANDING={standing}"
    except AssertionError:
        row["elapsed_seconds"] = round(time.monotonic() - started, 3)
        _write_p8_failure(diagnostic_path, [(row, output)])
        raise


def _prompt_gate() -> str:
    """The three opt-ins the one paid test needs, or an honest skip naming which.

    Each skip says exactly what is missing, because "skipped" with no reason is
    how an opt-in suite becomes green by never running.
    """
    if os.environ.get(PROMPT_ENV) != "1":
        pytest.skip(f"the real prompt smoke is opt-in: set {PROMPT_ENV}=1 to run it")
    key_name = os.environ.get(KEY_NAME_ENV, "")
    if not key_name:
        pytest.skip(f"no credential reference: {KEY_NAME_ENV} is not set")
    if not os.environ.get(key_name):
        # The NAME is configured but the live environment holds no value. That is
        # an honest unavailable, and running anyway would prove nothing.
        pytest.skip(f"no value present: the environment holds none for {key_name}")
    return key_name


def test_a_real_prompt_answers_with_something_only_the_piped_task_carried(tmp_path):
    """The one test that spends a model call, and the only far-side witness.

    The marker is minted fresh per run and placed ONLY in the instruction, which
    reaches the child by stdin alone -- the argv is a fixed list of code-owned
    flags plus one minted path, the environment carries the pin's allowlist, and
    the working directory is a temporary path. So an answer containing it cannot
    have come from anywhere else, and it is the one piece of evidence this build
    can obtain that the child really read what it was piped rather than merely
    being handed it.

    It is collected from the file `-o` names, because that is where this
    provider's answer goes and because the file dies with the home: the read
    happens inside the transport's own seam, which is the one moment it exists.
    What is asserted is the TOKEN, never the file -- the vendor writes that file
    on every completed run, EMPTY when the model said nothing, so its presence
    would prove only that the CLI reached the end.
    """
    key_name = _prompt_gate()

    marker = f"STDIN-ONLY-{uuid.uuid4().hex}"
    adapter, root = _real_harness(tmp_path, names=(key_name,))
    _seed_instruction(
        root,
        f"Reply with exactly this token and nothing else: {marker}\n"
        "Do not run any command, and do not create or modify any file.")
    request = a_request()
    with pytest.MonkeyPatch.context() as patches:
        answers = _collecting_final_messages(adapter, patches)
        receipt = adapter.execute(adapter.prepare(request))

    assert receipt.action_id == request.action_id
    assert receipt.outcome != "rejected", (
        f"the pinned build refused the dispatch outright: {receipt.detail}")
    assert (root / MARKER_DIR).is_dir(), "the task must have claimed its marker"

    verification = adapter.verify(request, receipt)
    assert verification.state in {"verified", "mismatch", "error"}
    assert verification.state != "unavailable", (
        "an adapter that HAS a verifier must never borrow the absent-verifier token")

    # THE far-side witness, and it is an ASSERTION rather than advice.
    assert any(marker in answer for answer in answers), (
        "no final message carried the piped token. Either the child never read "
        "its stdin -- which is what this assertion exists to catch, and which no "
        "parent-side check can see below the pipe buffer -- or it answered "
        f"something else. Final messages seen: {[len(a) for a in answers]} bytes")
