"""Runtime substitution around an independent checker never produces verified evidence."""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor.command.adapters.independent_check import CheckFrame
from conductor.command.adapters.independent_transport import IndependentCheckTransport
from conductor.command.adapters.local_test_plan import digest
from tests.test_local_test_plan import policy
from tests.test_patch_do_policy import reply


@dataclass
class Answer:
    detail: str
    result_manifest: object = None


class Checker(IndependentCheckTransport):
    def __init__(self, tmp_path, mutate):
        self.events = []
        self.mutate = mutate
        self.data = policy(tmp_path)
        install = Path(self.data["toolchain"]["install"])
        install.mkdir(parents=True)
        self.executable = install / "python.exe"
        self.executable.write_bytes(b"runtime")
        self.data["toolchain"]["runtime_digest"] = digest([
            {"path": "python.exe", "length": 7, "sha256": sha256(b"runtime").hexdigest()}])
        self._workspace = SimpleNamespace(
            sweep_homes=lambda: False, is_verification_claimed=lambda *a: False,
            digest_work_tree=lambda: {"task.py": "bytes"})
        self._handoff = SimpleNamespace(finish_attempt=lambda *a: self.events.append("finish"))
        self._retained = self._login_residue = False
        self._verdict_argv = ("never-started-model",)

    def _begin_road(self):
        pass

    def _relay_start(self, mode):
        return None

    def _dispatch_args(self, args):
        return SimpleNamespace(work_item_id="item", task_scope="one", output_limit_profile="normal")

    def _check_frame(self, *args):
        return CheckFrame(b"bounded-frame", "sha256:" + "0" * 64,
                          test_report_status="passed", attempt_seal={"digest": "sealed"})

    def _sealed_frame(self, request, verifier, material, frame):
        return frame

    def _sensitive_values(self):
        return ()

    def _checker_answer(self, request, reason):
        return Answer(reason)

    def _preflight(self, request):
        if self.mutate == "preflight":
            self.executable.write_bytes(b"substitution")
        return None

    def _evidence(self):
        return {"task.py": "bytes"}

    def _claim_of(self, *args, **options):
        return lambda: None

    def _attempt(self, *args, **options):
        self.events.append("checker")
        if self.mutate == "checker":
            self.executable.write_bytes(b"substitution")
        return reply(b"VERDICT: accept\n")

    def _record_check(self, *args):
        self.events.append("verified")
        return Answer("verified")


@pytest.mark.parametrize("mutate,events,detail", [
    (None, ["checker", "verified", "finish"], "verified"),
    ("preflight", ["finish"], "test_runtime_changed"),
    ("checker", ["checker", "finish"], "test_runtime_changed"),
])
def test_runtime_bytes_are_held_before_and_after_the_checker(tmp_path, mutate, events, detail):
    checker = Checker(tmp_path, mutate)
    text = "Do.\n\nconduct.test-plan.v1\n" + json.dumps(checker.data)
    material = SimpleNamespace(test_report={"present": True}, sensitive=(),
        after={"task.py": "bytes"}, instruction=text,
        instruction_document={"content": text, "source_action_id": None}, result_manifest=None)
    request = SimpleNamespace(capability="dispatch", arguments={}, timeout_seconds=30,
                              run_id="run", action_id="action")
    verifier = SimpleNamespace(model="fake-checker")
    answer = checker._check_owned(request, verifier, material)
    assert answer.detail == detail and checker.events == events
