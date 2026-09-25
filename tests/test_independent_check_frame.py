"""The checker receives bounded material, never an escaped allowed credential."""
from dataclasses import replace

import pytest

from conductor.command.adapters.base import Published
from conductor.command.adapters.independent_check import (
    CheckFrameError, build_frame, scan_material, verdict,
)
from conductor.command.adapters.process import ProcessOutcome, ProcessRunner
from tests.test_command_claude_transport import a_request


def material(**changes):
    values = dict(refusal=None, changed=("work-001/result.txt",),
                  after={"work-001/result.txt": "a"}, input_artifact_ids=(),
                  sensitive=(), instruction="The exact task.")
    values.update(changes)
    return Published(**values)


@pytest.mark.parametrize("secret", [b'quote"slash\\newline\nsecret', b'\xff\x80secret'])
def test_semantic_secrets_are_refused_before_json_or_hex_can_hide_them(secret):
    with pytest.raises(CheckFrameError, match="frame_env_echo"):
        build_frame(a_request(), material(), {},
                    {"work-001/result.txt": b"prefix" + secret}, sensitive=(secret,))


def test_json_escaped_document_secret_is_still_refused():
    secret = 'quote"slash\\newline\nsecret'
    with pytest.raises(CheckFrameError, match="frame_env_echo"):
        build_frame(a_request(), material(input_documents=({"content": secret},)), {}, {},
                    sensitive=(secret.encode(),))


def test_ordinary_material_and_nonmatching_credentials_are_preserved():
    frame = build_frame(a_request(), material(), {"work-001/result.txt": "digest"},
                        {"work-001/result.txt": b"ordinary result"}, sensitive=(b"private-key",))
    assert b"ordinary result" in frame.payload
    assert b"The exact task." in frame.payload
    assert frame.digest.startswith("sha256:")
    assert "ordinary result" not in repr(frame)


def test_material_that_does_not_fit_is_refused_not_truncated():
    """The ceiling is the whole serialized frame: exactly FRAME_LIMIT passes, one byte more refuses."""
    from conductor.command.adapters.independent_check import FRAME_LIMIT
    # Measured with a one-byte instruction: an empty one is replaced by a stand-in sentence.
    overhead = len(build_frame(a_request(), material(instruction="x"), {}, {}).payload) - 1
    exact = build_frame(a_request(), material(instruction="x" * (FRAME_LIMIT - overhead)), {}, {})
    assert len(exact.payload) == FRAME_LIMIT
    with pytest.raises(CheckFrameError, match="frame_over_limit"):
        build_frame(a_request(), material(instruction="x" * (FRAME_LIMIT - overhead + 1)), {}, {})


@pytest.mark.parametrize("answer,expected", [
    (b"VERDICT: accept\nwhy", "verified"), (b"\n  VERDICT: reject\nwhy", "rejected"),
    (b"VERDICT: accept \n", "no_verdict"), (b"VERDICT: accepted", "no_verdict"),
    (b"Reason first\nVERDICT: accept", "no_verdict"), (b"\xff", "no_verdict"),
])
def test_only_the_exact_first_answer_is_a_verdict(answer, expected):
    outcome = ProcessOutcome("completed", 0, answer, False, 1024, 1, "token",
                             stdin_state="delivered")
    assert verdict(outcome) == expected
    for changes in ({"exit_code": 1}, {"output_truncated": True},
                    {"output_contains_env_value": True}, {"stdin_state": "incomplete"}):
        assert verdict(replace(outcome, **changes)) == "no_verdict"


def test_environment_values_are_the_actual_allowlist_after_overrides(tmp_path):
    runner = ProcessRunner(tmp_path, environ={"KEY": "old", "EMPTY": "", "Case": "exact"})
    names = ("KEY", "EMPTY", "MISSING", "Case", "CASE")
    assert runner.allowed_environment_values(names) == (b"old", b"exact")
    assert runner.allowed_environment_values(names, overrides={
        "KEY": "new", "EMPTY": "", "MISSING": "added", "OTHER": "not-allowed",
    }) == (b"new", b"added", b"exact")
    # The same assembler is the source of both the child environment and this scan.
    class Spec:
        env_allow = names
        env = {"KEY": "new", "MISSING": "added", "OTHER": "not-allowed"}
    env = runner._child_env(Spec())
    assert runner.allowed_environment_values(names, overrides=Spec.env) == tuple(
        env[name].encode() for name in names if name in env and env[name])


def test_instruction_document_is_frozen_and_not_a_repr_surface():
    document = {"content": "private-instruction", "nested": {"id": "before"}}
    published = material(instruction_document=document)
    document["nested"]["id"] = "after"
    assert published.instruction_document["nested"]["id"] == "before"
    assert "private-instruction" not in repr(published)
    with pytest.raises(TypeError):
        published.instruction_document["nested"]["id"] = "changed"


@pytest.mark.parametrize("profile", ["small", "normal"])
def test_a_dispatch_checker_is_told_the_reply_bound_its_transport_enforces(profile):
    from conductor.command.adapters.deep_commands import OUTPUT_LIMIT_BYTES
    request = a_request(arguments={"work_item_id": "work-001", "instruction_ref": "instr-001",
        "profile": "implement", "artifact_refs": [], "output_limit_profile": profile})
    frame = build_frame(request, material(), {}, {})
    said = f"Your whole reply must fit in {OUTPUT_LIMIT_BYTES[profile]} UTF-8 bytes".encode()
    assert frame.payload.count(said) == 1



def test_a_dispatch_checker_is_told_the_file_budget_and_the_frame_ceiling_before_the_material():
    from conductor.command.adapters.harness_workspace import FILE_BUDGET
    from conductor.command.adapters.independent_check import FRAME_LIMIT
    payload = build_frame(a_request(), material(), {"work-001/result.txt": "digest"},
                          {"work-001/result.txt": b"ordinary result"}).payload.decode("utf-8")
    said = (f"Each changed file of at most {FILE_BUDGET} bytes is included whole below; "
            f"a larger one appears in WORK TREE by digest only. This whole frame is bounded at {FRAME_LIMIT} bytes.")
    assert payload.count(said) == 1 and payload.index(said) < payload.index("\nWORK TREE\n")



def test_a_confirmation_checker_is_asked_for_reasons_and_not_for_the_typed_shape():
    """The typed-reply shape belongs to a bounded run; its own witness is the native road
    (tests/test_check_road_limits.py), since a bounded frame needs a real result manifest."""
    payload = build_frame(a_request(), material(), {}, {}).payload.decode("utf-8")
    assert "Then explain your reasons." in payload and "no prose, no code fence" not in payload



def _bounded(request):
    return replace(request, mode="policy", run_authorization_id="grant-1",
                   run_authorization_digest="sha256:" + "0" * 64)


@pytest.mark.parametrize("profile,room", [
    ("small", 4 * 1024 - len("VERDICT: reject") - 4), ("normal", 8192)])
def test_a_bounded_dispatch_checker_is_told_one_reply_shape_and_findings_that_fit_its_reply(
        profile, room):
    """MEASURED live (live-nc-1): a frame asking for reasons and for JSON-only lost a real REJECT."""
    request = _bounded(a_request(arguments={"work_item_id": "work-001",
        "instruction_ref": "instr-001", "profile": "implement", "artifact_refs": [],
        "output_limit_profile": profile}))
    published = material(result_manifest={"action_id": request.action_id,
        "attempt_id": request.attempt_id, "input_artifact_ids": [], "files": []})
    payload = build_frame(request, published, {}, {},
                          result_manifest=published.result_manifest).payload.decode("utf-8")
    assert payload.count("after 'VERDICT: reject' write nothing but the one JSON object") == 1
    assert "Then explain your reasons." not in payload
    assert payload.count(f"Use 1 to 16 findings and at most {room} UTF-8 bytes.") == 1


def test_a_bounded_review_checker_is_not_asked_for_findings_its_transport_never_reads():
    """Typed findings are parsed for a marked dispatch only; a review is judged by its verdict."""
    request = _bounded(a_request(capability="review", arguments={"work_item_id": "work-001",
        "target_artifact_refs": ["artifact-a"], "result_artifact_ref": "artifact-r",
        "review_profile": "quality"}))
    payload = build_frame(request, material(result_document={"content": "reviewed"}), {}, {},
                          result_digest="sha256:" + "1" * 64).payload.decode("utf-8")
    assert "Then explain your reasons." in payload
    assert "conduct.feedback.v1" not in payload and "no prose" not in payload
