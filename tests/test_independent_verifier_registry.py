"""Optional independent seams carry copied facts, never another Protocol."""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from conductor.command.adapters.base import (
    Adapter, AdapterContractError, AdapterRegistry, AdapterVerification,
    IndependentVerifierUnavailable, Published, VerifierBinding,
)
from conductor.command.contracts import ActionResultReceipt
from tests.test_command_adapters import FakeAdapter, NOW, an_action


def _result():
    return ActionResultReceipt(
        receipt_id="result-001", action_id="action-001", run_id="run-001",
        attempt_id="attempt-001", instance_id="claude-dev", outcome="succeeded",
        observed_at=NOW)


def _material(**changes):
    values = dict(
        refusal=None, changed=("item/output.txt",),
        after={"item/output.txt": "a" * 64}, input_artifact_ids=("input-1",),
        sensitive=(b"private-env-value",), instruction="private-instruction",
        input_documents=({"content": "private-input", "nested": ["first"]},),
        result_document={"content": "private-result"})
    values.update(changes)
    return Published(**values)


class _Independent(FakeAdapter):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls = []
        self.material = _material()

    def publish(self, request, result):
        self.calls.append(("publish", request, result))
        return self.material

    def release(self, request):
        self.calls.append(("release", request))

    def verify_for(self, request, result, verifier, material):
        self.calls.append(("verify_for", request, result, verifier, material))
        return AdapterVerification(
            adapter_id=self.manifest.adapter_id, action_id=request.action_id,
            state="verified", observed_at=NOW, detail="not durable here",
            evidence_refs=("check-evidence",))


def test_independent_seams_are_optional_and_the_plain_protocol_stays_four():
    assert {name for name, value in vars(Adapter).items()
            if not name.startswith("_") and callable(value)} == {
                "observe", "prepare", "execute", "verify"}
    registry = AdapterRegistry([FakeAdapter()])
    assert not registry.verifies_independently("claude-code", "dispatch")
    assert registry.publish("claude-code", an_action(), _result()) is None
    assert registry.release("claude-code", an_action()) is None
    assert registry.verify("claude-code", an_action(), _result()).state == "unavailable"
    with pytest.raises(IndependentVerifierUnavailable):
        registry.verify("claude-code", an_action(), _result(),
                        verifier=VerifierBinding("checker", "claude-code"),
                        material=_material())


@pytest.mark.parametrize("missing", ("publish", "release", "verify_for"))
def test_independent_availability_requires_all_three_registered_seams(missing):
    adapter = _Independent()
    setattr(adapter, missing, None)
    registry = AdapterRegistry([adapter])
    assert not registry.verifies_independently("claude-code", "dispatch")


def test_availability_is_registration_owned_and_capability_specific():
    adapter = _Independent()
    registry = AdapterRegistry([adapter])
    assert registry.verifies_independently("claude-code", "dispatch")
    assert not registry.verifies_independently("claude-code", "review")
    adapter.verify_for = None
    assert registry.verifies_independently("claude-code", "dispatch")
    answer = registry.verify(
        "claude-code", an_action(), _result(),
        verifier=VerifierBinding("checker", "claude-code", "checker-model"),
        material=_material())
    assert answer.state == "verified"
    assert adapter.calls[-1][0] == "verify_for"
    plain = FakeAdapter(adapter_id="late")
    registry.register(plain)
    plain.verify_for = adapter.calls.append
    plain.publish = adapter.calls.append
    plain.release = adapter.calls.append
    assert not registry.verifies_independently("late", "dispatch")


def test_the_registry_passes_copies_to_each_optional_untrusted_seam():
    adapter = _Independent()
    registry = AdapterRegistry([adapter])
    request, result = an_action(), _result()
    material = registry.publish("claude-code", request, result)
    assert material == adapter.material and material is not adapter.material
    _, passed_request, passed_result = adapter.calls[-1]
    assert passed_request == request and passed_request is not request
    assert passed_result == result and passed_result is not result
    binding = VerifierBinding("checker", "claude-code", "checker-model")
    registry.verify("claude-code", request, result, verifier=binding, material=material)
    _, passed_request, passed_result, passed_binding, passed_material = adapter.calls[-1]
    assert passed_binding == binding and passed_binding is not binding
    assert passed_material == material and passed_material is not material
    assert passed_request is not request and passed_result is not result
    registry.release("claude-code", request)
    assert adapter.calls[-1][1] == request and adapter.calls[-1][1] is not request


@pytest.mark.parametrize("binding", (
    VerifierBinding("claude-dev", "claude-code"), VerifierBinding("checker", "other"),
))
def test_a_binding_cannot_name_the_doer_or_another_adapter(binding):
    adapter = _Independent()
    registry = AdapterRegistry([adapter])
    with pytest.raises(AdapterContractError, match="another participant"):
        registry.verify("claude-code", an_action(), _result(),
                        verifier=binding, material=_material())
    assert adapter.calls == []


@pytest.mark.parametrize("field,value", (
    ("instance_id", ""), ("adapter_id", "../other"), ("model", ""),
))
def test_binding_identity_and_model_are_validated(field, value):
    values = dict(instance_id="checker", adapter_id="claude-code", model=None)
    values[field] = value
    with pytest.raises(AdapterContractError):
        VerifierBinding(**values)


def test_published_material_has_no_mutable_alias_and_no_sensitive_repr():
    after = {"item/output.txt": "a" * 64}
    nested = {"content": "private-input", "items": ["before"]}
    result = {"content": "private-result"}
    material = _material(after=after, input_documents=(nested,), result_document=result)
    after.clear()
    nested["items"].append("later")
    result["content"] = "replaced"
    assert material.after == {"item/output.txt": "a" * 64}
    assert material.input_documents[0]["items"] == ("before",)
    assert material.result_document["content"] == "private-result"
    with pytest.raises(TypeError):
        material.after["item/output.txt"] = "b" * 64
    with pytest.raises(FrozenInstanceError):
        material.instruction = "replaced"
    assert "private-" not in repr(material)


@pytest.mark.parametrize("changes", (
    {"refusal": "a child chose this sentence"}, {"changed": ["item/a"]},
    {"changed": ("../outside",)}, {"changed": ("item/a", "item/a")},
    {"after": {"/outside": "a" * 64}}, {"input_artifact_ids": "input-1"},
    {"input_artifact_ids": ("../input",)}, {"sensitive": [b"value"]},
    {"sensitive": (bytearray(b"mutable"),)}, {"input_documents": [{"content": "x"}]},
    {"input_documents": ("not an object",)}, {"result_document": []},
))
def test_published_refuses_malformed_material_before_a_checker_sees_it(changes):
    with pytest.raises(AdapterContractError):
        _material(**changes)


def test_mutated_published_results_are_revalidated_at_the_registry_boundary():
    adapter = _Independent()
    registry = AdapterRegistry([adapter])
    object.__setattr__(adapter.material, "changed", ("../outside",))
    with pytest.raises(AdapterContractError, match="relative"):
        registry.publish("claude-code", an_action(), _result())


def test_a_mutated_binding_is_revalidated_without_calling_the_checker():
    adapter = _Independent()
    registry = AdapterRegistry([adapter])
    binding = VerifierBinding("checker", "claude-code")
    object.__setattr__(binding, "model", "")
    with pytest.raises(AdapterContractError, match="model"):
        registry.verify("claude-code", an_action(), _result(),
                        verifier=binding, material=_material())
    assert adapter.calls == []


def test_absence_of_marker_knowledge_is_not_an_unstarted_verification():
    adapter = _Independent()
    registry = AdapterRegistry([adapter])
    assert registry.verification_started("claude-code", an_action()) is None
    adapter.verification_started = lambda request: False
    assert registry.verification_started("claude-code", an_action()) is None
    assert registry.verifies_independently("claude-code", "dispatch")
    assert adapter.calls == []


@pytest.mark.parametrize("started", (True, False))
def test_checker_marker_knowledge_is_exact_and_reads_a_copied_request(started):
    adapter = _Independent()
    calls = []

    def read_claim(request):
        calls.append(request)
        return started

    adapter.verification_started = read_claim
    registry = AdapterRegistry([adapter])
    request = an_action()
    assert registry.verification_started("claude-code", request) is started
    assert calls == [request] and calls[0] is not request
    assert registry.verifies_independently("claude-code", "dispatch")
    assert adapter.calls == []


@pytest.mark.parametrize("invalid", (None, 0, 1, "true", (), []))
def test_marker_knowledge_never_substitutes_truthiness_for_a_bool(invalid):
    adapter = _Independent()
    adapter.verification_started = lambda request: invalid
    registry = AdapterRegistry([adapter])
    with pytest.raises(AdapterContractError, match="must return a bool"):
        registry.verification_started("claude-code", an_action())
    assert adapter.calls == []
