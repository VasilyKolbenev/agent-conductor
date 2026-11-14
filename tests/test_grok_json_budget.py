"""The Grok JSON transport bounds the envelope and the published text independently."""
import json
from pathlib import Path

import pytest

from conductor.command.run_store import RunStore
from conductor.command.runtime import AttemptState
from tests import _fakegrok
from tests.test_grok_activation import EXPECTED_ARGV, _confirmed_review, _site


def exercise(tmp_path, case):
    adapter, root, log, login, original, runner = _site(tmp_path, "subscription", "budget-" + case)
    attempt = _confirmed_review(adapter, root)
    (process,) = _fakegrok.prompt_spawns(log)
    assert process["argv"][:-1] == EXPECTED_ARGV
    assert [entry.mode for entry in runner.entries] == ["review"]
    assert not Path(process["grok_home"]).exists()
    assert (login / "auth.json").read_bytes() == original
    store = RunStore(root)
    records = store.read("run-grok").records
    (receipt,) = [r.value for r in records if r.kind == "action_result"]
    outputs = [r.value for r in records if r.kind == "artifact" and r.value.source_action_id]
    ledger = (store.run_path("run-grok") / "records.jsonl").read_bytes()
    for marker in (b"private-thought-marker", b"request-marker", b"session-marker",
                   b"fake-access-activation-1234", b"stderr-private-", b"late-fake-error"):
        assert marker not in ledger
    sizes = json.loads(Path(log).with_suffix(".sizes").read_bytes())
    assert sizes["stderr"] == (720000 if case == "stderr" else 0)
    return attempt, receipt, outputs, sizes["stdout"]


@pytest.mark.parametrize("size", [49152, 49153, 557056])
def test_wire_keeps_small_answer(tmp_path, size):
    attempt, receipt, outputs, emitted = exercise(tmp_path, "wire-" + str(size))
    assert emitted == size
    assert attempt.state is AttemptState.SUCCEEDED, receipt.detail
    (document,) = outputs
    assert document.content == "  Да 🚀\n"
    assert document.source_action_id == receipt.action_id
    assert document.input_artifact_ids == ("seed-1",) and document.artifact_ref == "diagnosis"


def test_wire_over_cap(tmp_path):
    attempt, receipt, outputs, emitted = exercise(tmp_path, "wire-557057")
    assert emitted == 557057 and outputs == []
    assert attempt.state is AttemptState.FAILED
    assert receipt.outcome == "failed" and "longer than the capture bound" in receipt.detail


@pytest.mark.parametrize("over", [False, True])
def test_decoded_utf8_cap(tmp_path, over):
    expected = " " + "🚀" * 12287 + "\n\t " + ("x" if over else "")
    assert len(expected.encode("utf-8")) == (49153 if over else 49152)
    attempt, receipt, outputs, emitted = exercise(tmp_path, "text-over" if over else "text-at")
    assert 12 * 12287 < emitted < 557056, "the complete escaped envelope fits the wire budget"
    if over:
        assert attempt.state is AttemptState.FAILED and outputs == []
        assert receipt.detail == (
            "adapter reported failed: the review result exceeded the artifact byte limit")
    else:
        assert attempt.state is AttemptState.SUCCEEDED
        (document,) = outputs
        assert document.content.encode("utf-8") == expected.encode("utf-8")
        assert document.input_artifact_ids == ("seed-1",)


@pytest.mark.parametrize("case,reason", [
    ("malformed", "the review returned an invalid terminal response"),
    ("duplicate", "the review returned an invalid terminal response"),
    ("tail", "the review returned an invalid terminal response"),
    ("stop", "the review returned an invalid terminal response"),
    ("error", "the harness reported an embedded agent startup failure"),
    ("secret-thought", "the review contained sensitive output"),
    ("secret-text", "the review contained sensitive output"),
])
def test_large_invalid_or_sensitive_result(tmp_path, case, reason):
    attempt, receipt, outputs, emitted = exercise(tmp_path, case)
    assert 49152 < emitted < 557056 and outputs == []
    assert attempt.state is AttemptState.FAILED
    assert receipt.outcome == "failed" and receipt.detail == "adapter reported failed: " + reason
    if case == "error":
        assert receipt.exit_code == 1


def test_stderr_does_not_use_stdout_budget(tmp_path):
    attempt, receipt, outputs, emitted = exercise(tmp_path, "stderr")
    assert emitted < 49152 and attempt.state is AttemptState.SUCCEEDED, receipt.detail
    (document,) = outputs
    assert document.content == "  Да 🚀\n"


def test_wire_limit_belongs_only_to_ordinary_json(tmp_path, monkeypatch):
    adapter, root, log, *_rest, runner = _site(tmp_path, "subscription", "stream-full")
    calls = []
    run = runner.run

    def observe(spec):
        calls.append((spec.argv, spec.output_limit))
        return run(spec)

    monkeypatch.setattr(runner, "run", observe)
    for name, diagnostic in [("ordinary", False), ("diagnostic", True), ("ordinary-2", False)]:
        attempt = _confirmed_review(adapter, root, run_id=name, diagnostic=diagnostic)
        assert attempt.state is AttemptState.SUCCEEDED
    tasks = [(argv[argv.index("--output-format") + 1], cap)
             for argv, cap in calls if "--prompt-file" in argv]
    assert tasks == [("json", 557056), ("streaming-messages-json", 49152), ("json", 557056)]
    assert len(_fakegrok.prompt_spawns(log)) == 3
    assert [cap for argv, cap in calls if "--version" in argv] == [49152, 49152, 49152]
