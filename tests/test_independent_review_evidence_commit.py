"""A checker signs only the review document it actually judged.

The native adapter is real, but both participant outcomes are scripted: these
witnesses exercise publication, checker framing and journal recovery without
starting a child. A schema-valid but wrong Published document must not buy a
signature for the different document standing in the store, even transiently.
"""
from dataclasses import replace

import pytest

from conductor.command.adapters.base import Published, VerifierBinding
from conductor.command.adapters.process import ProcessOutcome
from conductor.command.run_store import RecordConflict
from conductor.command.runtime import AttemptState
from tests.test_command_runtime_execute import ScriptedAdapter
from tests.test_independent_checker_transport import CHECKER, RUN, setup


def _interrupted_review(tmp_path, monkeypatch):
    runtime, authorization, store, doer, checker, log, _, _ = setup(tmp_path, review=True)
    reports = []

    def execute(prepared):
        result = ScriptedAdapter(capabilities=("observe", "review")).execute(prepared)
        reports.append(result)
        return result

    def interrupted(*args, **kwargs):
        raise RuntimeError("interrupted after observation")

    with monkeypatch.context() as patch:
        patch.setattr(doer, "execute", execute)
        patch.setattr(runtime, "_resolve", interrupted)
        with pytest.raises(RuntimeError, match="interrupted after observation"):
            runtime.execute(authorization)
    document = doer._handoff.record_review_artifact(
        authorization.request, "review-result", input_artifact_ids=("input-001",),
        content="The actual published review result.")
    assert document is not None and not log.exists()
    return runtime, authorization, store, checker, log, reports[0], document


def _check(checker, request, report, store, document, monkeypatch):
    inputs = tuple(row.value.as_dict() for row in store.read(RUN).records
                   if row.kind == "artifact" and row.value.artifact_id == "input-001")
    material = Published(None, (), {}, ("input-001",), (), None, inputs, document.as_dict())
    frames = []

    def accepted(*args, **kwargs):
        frames.append(kwargs["stdin_bytes"])
        return ProcessOutcome("completed", 0, b"VERDICT: accept", False, 4096, 1,
                              "scripted-owned-token", stdin_state="delivered")

    monkeypatch.setattr(checker, "_preflight", lambda request: None)
    monkeypatch.setattr(checker, "_attempt", accepted)
    answer = checker.verify_for(request, report,
        VerifierBinding(CHECKER, "claude-code", "checker-model"), material)
    assert len(frames) == 1 and document.content.encode() in frames[0]
    return answer


def test_wrong_but_valid_result_material_leaves_no_signature_or_resume_success(tmp_path, monkeypatch):
    runtime, auth, store, checker, log, report, document = _interrupted_review(tmp_path, monkeypatch)
    different = replace(document, content="A different, allegedly safe result.")
    journal = store.run_path(RUN) / "records.jsonl"
    before = journal.read_bytes()
    answer = _check(checker, auth.request, report, store, different, monkeypatch)
    assert answer.state == "error" and answer.detail == "material_unavailable"
    assert journal.read_bytes() == before, "a rejected checked digest wrote durable evidence"
    assert not [row for row in store.read(RUN).records if row.kind == "evidence"]
    resumed = runtime.execute(auth)
    assert resumed.state is AttemptState.VERIFICATION_FAILED
    assert resumed.receipt.evidence_refs == () and not log.exists()


def test_matching_result_is_signed_and_resumes_without_a_second_participant(tmp_path, monkeypatch):
    runtime, auth, store, checker, log, report, document = _interrupted_review(tmp_path, monkeypatch)
    answer = _check(checker, auth.request, report, store, document, monkeypatch)
    assert answer.state == "verified"
    evidence = [row.value for row in store.read(RUN).records if row.kind == "evidence"]
    assert len(evidence) == 1 and evidence[0].digest == document.digest()
    assert evidence[0].verifier_instance_id == CHECKER
    resumed = runtime.execute(auth)
    assert resumed.state is AttemptState.SUCCEEDED
    assert resumed.receipt.evidence_refs == answer.evidence_refs and not log.exists()


@pytest.mark.parametrize("expected", [True, False])
def test_review_writer_checks_expected_digest_before_any_append(tmp_path, monkeypatch, expected):
    _, auth, store, checker, _, _, document = _interrupted_review(tmp_path, monkeypatch)
    journal = store.run_path(RUN) / "records.jsonl"
    before = journal.read_bytes()
    digest = document.digest() if expected else replace(document, content="Different.").digest()
    kwargs = dict(input_artifact_ids=None, content=None, adapter_id="claude-code",
                  verifier_instance_id=CHECKER, expected_digest=digest)
    if expected:
        evidence = checker._handoff.record_review(auth.request, "review-result", **kwargs)
        assert evidence.digest == digest
        assert checker._handoff.record_review(auth.request, "review-result", **kwargs) == evidence
    else:
        with pytest.raises(RecordConflict, match="checked digest"):
            checker._handoff.record_review(auth.request, "review-result", **kwargs)
        assert journal.read_bytes() == before


def test_omitted_expected_digest_preserves_the_existing_writer_road(tmp_path, monkeypatch):
    _, auth, store, checker, _, _, document = _interrupted_review(tmp_path, monkeypatch)
    evidence = checker._handoff.record_review(auth.request, "review-result",
        input_artifact_ids=None, content=None, adapter_id="claude-code", verifier_instance_id=CHECKER)
    assert evidence.digest == document.digest()
    assert len([row for row in store.read(RUN).records if row.kind == "evidence"]) == 1
