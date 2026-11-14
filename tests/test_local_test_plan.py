"""Owner policy framing is strict and legacy instructions remain legacy."""
from dataclasses import replace
from hashlib import sha256
import json

import pytest

from conductor.command.adapters.codex_patch import PatchRefused
from conductor.command.adapters.local_test_plan import plan_for, read_plan
from tests.test_patch_do_sources import doc


def policy(tmp_path):
    return {"runner": "python-unittest-v1", "start": "tests", "pattern": "test_*.py",
            "timeout_seconds": 60, "toolchain": {
                "install": str(tmp_path / "harnesses" / "python-unittest" / "3.12.14"),
                "entry": "python.exe", "runtime_digest": "sha256:" + sha256(b"pin").hexdigest()}}


def test_initial_plan_precedes_the_unchanged_source_suffix(tmp_path):
    value = policy(tmp_path)
    text = ("Do.\n\nconduct.test-plan.v1\n" + json.dumps(value)
            + '\n\nconduct.patch-sources.v1\n["count.py"]')
    plan = plan_for(doc("brief", text), text)
    assert plan.as_dict() == value and plan.runner == "python-unittest-v1"
    assert plan_for(doc("brief", text).as_dict(), text) == plan
    assert plan_for(doc("brief", "Legacy instruction")) is None
    assert plan_for(None, "Legacy instruction") is None
    with pytest.raises(PatchRefused):
        plan_for(replace(doc("brief", text), source_action_id="model"), text)
    with pytest.raises(PatchRefused):
        plan_for(None, text)


@pytest.mark.parametrize("suffix", [
    "trailing", '\n{}', '\n\nconduct.test-plan.v1\n{}',
    '\n\nconduct.patch-sources.v1\n[]\n\nconduct.test-plan.v1\n{}',
])
def test_duplicate_or_trailing_plan_data_is_refused(tmp_path, suffix):
    text = "Do.\n\nconduct.test-plan.v1\n" + json.dumps(policy(tmp_path)) + suffix
    with pytest.raises(PatchRefused):
        plan_for(doc("brief", text))


@pytest.mark.parametrize("key,value", [
    ("start", "../private"), ("start", ".config"), ("start", "C:/outside"),
    ("pattern", "../test_*.py"), ("pattern", "tests\\test_*.py"),
    ("runner", "shell"), ("timeout_seconds", True), ("timeout_seconds", 0),
    ("timeout_seconds", 86401), ("new_field", "ignored"),
])
def test_plan_fields_are_closed_and_paths_do_not_select_a_command(tmp_path, key, value):
    data = policy(tmp_path)
    data[key] = value
    with pytest.raises(PatchRefused):
        read_plan(data)


def test_duplicate_json_keys_and_reversed_markers_are_refused(tmp_path):
    encoded = json.dumps(policy(tmp_path)).replace('"runner":', '"runner":"shell","runner":')
    for text in ("Do.\n\nconduct.test-plan.v1\n" + encoded,
                 "Do.\n\nconduct.patch-sources.v1\n[]\n\nconduct.test-plan.v1\n"
                 + json.dumps(policy(tmp_path))):
        with pytest.raises(PatchRefused):
            plan_for(doc("brief", text))
