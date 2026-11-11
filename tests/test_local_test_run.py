"""Local runner outcomes and changed facts are distinguished without a native child."""
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic
from types import SimpleNamespace

import pytest

from conductor.command.adapters.codex_patch import PatchRefused
from conductor.command.adapters.local_test_plan import digest, read_plan
from conductor.command.adapters.local_test_receipt import settled_report
from conductor.command.adapters.local_test_run import run_local_tests
from conductor.command.adapters.process_boundary import WindowsContainer
from tests.test_local_test_plan import policy
from tests.test_local_test_protocol import TRANSCRIPT
from tests.test_patch_do_policy import reply


def setup(tmp_path, outcome):
    root = tmp_path / "root"
    work = root / "work" / "_tasks" / "one" / "item"
    (work / "tests").mkdir(parents=True)
    source = work / "count.py"
    source.write_bytes(b"post-patch")
    expected = {"_tasks/one/item/count.py": sha256(b"post-patch").hexdigest()}
    data = policy(tmp_path)
    install = Path(data["toolchain"]["install"])
    install.mkdir(parents=True)
    (install / "python.exe").write_bytes(b"fake-runtime")
    data["toolchain"]["runtime_digest"] = digest([
        {"path": "python.exe", "length": 12, "sha256": sha256(b"fake-runtime").hexdigest()}])
    plan = read_plan(data)
    events, records, claimed = [], [], []
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    @contextmanager
    def boundary(**options):
        assert options["mode"] == "review" and not options["internet_client"]
        assert options["folders"].home is None
        events.append("enter")
        yield WindowsContainer("S-1-15-2-1-2-3-4-5-6-7"), {"runtime": scratch}
        events.append("exit")

    def child(spec):
        events.append("tests")
        assert spec.env_allow == () and spec.boundary and not spec.separate_stderr
        bootstrap = Path(spec.argv[4]).read_text(encoding="utf-8")
        assert bootstrap.index("import json, pathlib, sys, unittest") < bootstrap.index(
            "sys.path.insert")
        return outcome() if callable(outcome) else outcome

    def claim(request, binding):
        events.append("claim")
        if claimed:
            return False
        claimed.append(binding)
        return True

    def record(request, report):
        events.append("record")
        records.append(report)

    ws = SimpleNamespace(root=root, work_modes=lambda *a, **kw: {"count.py": False},
                         digest_work_tree=lambda: {
                             "_tasks/one/item/count.py": sha256(source.read_bytes()).hexdigest()})
    transport = SimpleNamespace(
        _workspace=ws, _confine=True, boundary_provided=lambda mode: True,
        _runner=SimpleNamespace(container_profile=boundary, run=child),
        _handoff=SimpleNamespace(claim_test_run=claim, record_test_run=record),
        _sensitive_values=lambda *a: (), _login_seen=())
    request = SimpleNamespace(run_id="run", action_id="action", attempt_id="attempt",
        instance_id="doer", run_authorization_id="grant",
        run_authorization_digest="sha256:" + "0" * 64)
    args = SimpleNamespace(work_item_id="item", task_scope="one")
    call = lambda: run_local_tests(transport, request, args, work, expected, plan,
                                  monotonic() + 30)
    return call, events, records, source, install, transport


@pytest.mark.parametrize("outcome,status", [
    (reply(TRANSCRIPT), "passed"),
    (reply(b'bad\n\nconduct.test-result.v1 {"total":2,"failures":1,"errors":0,"skipped":0}\n',
           code=1), "failed"),
    (reply(b'\nconduct.test-result.v1 {"total":0,"failures":0,"errors":0,"skipped":0}\n'),
     "zero_tests"),
    (reply(b'\nconduct.test-result.v1 {"total":2,"failures":0,"errors":0,"skipped":2}\n'),
     "zero_tests"),
    (replace(reply(b"unfinished"), status="timed_out", exit_code=None), "timed_out"),
    (replace(reply(TRANSCRIPT), output_truncated=True), "truncated"),
    (reply(b"exit zero is not a test result"), "infrastructure_error"),
])
def test_real_process_facts_never_collapse_to_exit_zero(tmp_path, outcome, status):
    call, events, records, *_rest = setup(tmp_path, outcome)
    report = call()
    assert report["status"] == status
    assert events == ["claim", "enter", "tests", "exit", "record"]
    assert records == [report]
    with pytest.raises(PatchRefused, match="already started"):
        call()
    assert events.count("tests") == 1


@pytest.mark.parametrize("target,reason", [("tree", "tree_changed"), ("pin", "runtime_changed")])
def test_a_changed_fact_cannot_keep_a_passed_report(tmp_path, target, reason):
    call, _events, _records, source, install, transport = setup(tmp_path, reply(TRANSCRIPT))
    def changed(spec):
        (source if target == "tree" else install / "python.exe").write_bytes(b"tampered")
        return reply(TRANSCRIPT)
    transport._runner.run = changed
    report = call()
    assert report["status"] == "infrastructure_error" and report["reason"] == reason


def test_no_boundary_or_wrong_pin_spawns_nothing(tmp_path):
    call, events, _records, _source, install, transport = setup(tmp_path, reply(TRANSCRIPT))
    transport.boundary_provided = lambda mode: False
    with pytest.raises(PatchRefused, match="boundary"):
        call()
    transport.boundary_provided = lambda mode: True
    (install / "python.exe").write_bytes(b"wrong-runtime")
    with pytest.raises(PatchRefused, match="pin mismatch"):
        call()
    assert events == []


def test_protected_bytes_are_never_saved_in_a_transcript(tmp_path):
    call, _events, records, _source, _install, transport = setup(
        tmp_path, reply(b"synthetic-secret\xff" + TRANSCRIPT))
    transport._sensitive_values = lambda *a: (b"synthetic-secret\xff",)
    report = call()
    assert report["status"] == "infrastructure_error"
    assert report["reason"] == "protected_output" and report["output_b64"] == ""
    assert "synthetic-secret" not in json.dumps(records)


@pytest.mark.parametrize("field,value", [("status", "verified"), ("counts", None),
                                        ("output", "substituted"), ("extra", True)])
def test_receipt_cannot_be_relabelled_or_have_its_bytes_substituted(tmp_path, field, value):
    call, *_rest = setup(tmp_path, reply(TRANSCRIPT))
    report = call()
    report[field] = value
    with pytest.raises(ValueError):
        settled_report(report)
