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
    with pytest.raises(CheckFrameError, match="frame_over_limit"):
        build_frame(a_request(), material(instruction="x" * 65536), {}, {})


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
