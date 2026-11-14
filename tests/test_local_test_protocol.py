"""One real public patch road; only process and durable-test-store boundaries are doubled."""
from hashlib import sha256
from dataclasses import replace
import json
from pathlib import Path

import pytest

from tests.relay_roads import CODEX, Site
from tests.test_patch_do_policy import ACTUAL, PATCH, one_grant, reply, work_and_calls


TRANSCRIPT = (b"test_first ... ok\ntest_second ... ok\nRan 2 tests\nOK\n"
              b'\nconduct.test-result.v1 {"total":2,"failures":0,"errors":0,"skipped":0}\n')


@pytest.mark.parametrize("test_reply,expected,checked", [
    (reply(TRANSCRIPT), "succeeded", True),
    (reply(b'\nconduct.test-result.v1 {"total":1,"failures":1,"errors":0,"skipped":0}\n',
           code=1), "verification_failed", True),
    (reply(b'\nconduct.test-result.v1 {"total":0,"failures":0,"errors":0,"skipped":0}\n'),
     "verification_failed", False),
    (replace(reply(TRANSCRIPT), output_truncated=True), "verification_failed", False),
    (replace(reply(b"unfinished"), status="timed_out", exit_code=None),
     "verification_failed", False),
])
def test_public_do_runs_tests_after_apply_before_checker(tmp_path, test_reply, expected, checked):
    site = Site(tmp_path, CODEX)
    install = tmp_path / "harnesses" / "python-unittest" / "3.12.14"
    install.mkdir(parents=True)
    (install / "python.exe").write_bytes(b"fake-python-never-executed")
    rows = [{"path": "python.exe", "length": 26,
             "sha256": sha256(b"fake-python-never-executed").hexdigest()}]
    runtime = "sha256:" + sha256(json.dumps(
        rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    plan = {"runner": "python-unittest-v1", "start": "tests", "pattern": "test_*.py",
            "timeout_seconds": 60, "toolchain": {"install": str(install),
            "entry": "python.exe", "runtime_digest": runtime}}
    instruction = "Count successes.\n\nconduct.test-plan.v1\n" + json.dumps(plan)
    recorded = []
    claims = []
    with site.owned():
        work, calls = work_and_calls(site, PATCH)
        (work / "tests").mkdir()
        site.adapter._test_reports = {}
        site.adapter._handoff.claim_test_run = lambda request, binding: not claims.append(binding)
        site.adapter._handoff.record_test_run = lambda request, report: recorded.append(report)
        original = site.runner.run

        def observed(spec):
            if Path(spec.argv[0]).name == "python.exe":
                calls.append("tests")
                assert (work / "count.py").read_bytes() == ACTUAL
                assert spec.boundary and not spec.boundary.internet_client
                assert spec.env_allow == () and not spec.separate_stderr
                assert spec.argv[1:4] == ("-I", "-S", "-B")
                assert 0 < spec.timeout_seconds <= 30 and spec.output_limit == 65536
                assert "CODEX_HOME" not in spec.env
                return test_reply
            if "checker-model" in spec.argv:
                assert len(recorded) == 1, "test protocol was not saved before checker"
                assert recorded[0]["output"] == test_reply.output.decode()
            return original(spec)

        site.runner.run = observed
        get, _request = one_grant(site, instruction=instruction)
        result, = get("action_result")
        assert calls == ["prepare", "apply", "tests"] + (["check"] if checked else [])
        assert result.outcome == expected
        assert len(claims) == 1 and len(recorded) == 1
        if checked and expected != "succeeded":
            assert result.detail == "post-patch tests failed; the checker cannot confirm success"
        if not checked:
            assert result.detail == "post-patch tests did not produce a complete usable result"
