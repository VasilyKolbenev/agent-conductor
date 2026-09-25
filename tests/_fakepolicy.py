"""Native fake whose correction depends on the actual typed stdin handoff."""
import hashlib
import json
import os
from pathlib import Path
import sys

from tests import _fakecodex

INSTRUCTION = "Keep this exact task: answer() must return 1."
PAYLOAD = {"protocol": "conduct.feedback.v1", "findings": [{"kind": "defect",
    "summary": "answer() must return 1 instead of 2", "path": "answer.py", "line": 2}]}
GOOD = b"def answer():\n    return 1\n"
BAD = b"def answer():\n    return 2\n"
#: Bytes of comment padding the doer appends to its answer (0 by default).
PAD = "FAKEPOLICY_PAD"
#: sha256 of the plan document both children must receive whole (unset: no plan).
PLAN_SHA = "FAKEPOLICY_PLAN_SHA256"
#: Extra files of exactly FILE_BUDGET bytes the first doer pass writes (0 by default).
EXTRA = "FAKEPOLICY_EXTRA_FILES"
EXTRA_BYTES = "FAKEPOLICY_EXTRA_BYTES"
#: When set, a REJECT carries a sentence of reasons before its JSON (what a real checker did).
PROSE = "FAKEPOLICY_REJECT_PROSE"
TASK = ""


def _log(row):
    path = Path(os.environ[_fakecodex.SPAWN_LOG]).with_suffix(".semantic.jsonl")
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")


def _read():
    global TASK
    result, TASK = _ORIGINAL_READ()
    return result, TASK


def _doer():
    rows = []
    if "\nCORRECTION DATA" in TASK:
        rows = json.loads(TASK.split("\nCORRECTION DATA", 1)[1].split("\n", 1)[1])
        assert len(rows) == 1 and rows[0]["payload"] == PAYLOAD
        assert Path("answer.py").read_bytes() == BAD + b"#" * int(os.environ.get(PAD, "0"))
    assert INSTRUCTION in TASK
    plan = None
    if os.environ.get(PLAN_SHA):
        plan = TASK.split("--- durable artifact artifact-plan ", 1)[1].split("\n", 1)[1]
        plan = plan.split("\n--- end artifact ---", 1)[0]
        assert hashlib.sha256(plan.encode("utf-8")).hexdigest() == os.environ[PLAN_SHA]
    Path("answer.py").write_bytes((GOOD if rows else BAD) + b"#" * int(os.environ.get(PAD, "0")))
    if not rows:
        # Knob values reach the child through the allowlist, whose values the product scans as
        # secrets; a bare number would be found in any frame, so each carries a prefix.
        for index in range(int(os.environ.get(EXTRA, "files-0").removeprefix("files-"))):
            Path(f"extra-{index}.txt").write_bytes(
                b"x" * int(os.environ[EXTRA_BYTES].removeprefix("bytes-")))
    row = {"role": "doer", "correction_received": bool(rows),
           "instruction_preserved": True, "written": 1 if rows else 2}
    if plan is not None:
        row.update(plan_whole=True, limits_told="\nRESULT LIMITS\n" in TASK)
    _log(row)
    return 0


def _checker():
    content = Path("answer.py").read_bytes()
    manifest = json.loads(TASK.split("\nRESULT MANIFEST\n", 1)[1])
    assert manifest["files"] == [{"path": "item/answer.py", "state": "present",
        "length": len(content), "sha256": "sha256:" + hashlib.sha256(content).hexdigest()}]
    frame_content = TASK.split("\nCHANGED FILE CONTENTS\n", 1)[1].split("\nRESULT MANIFEST\n", 1)[0].strip()
    assert json.loads(frame_content) == {"path": "item/answer.py", "encoding": "utf-8",
                                       "content": content.decode("utf-8")}
    assert INSTRUCTION in TASK
    plan = None
    if os.environ.get(PLAN_SHA):
        documents = json.loads(TASK.split("\nINPUT DOCUMENTS\n", 1)[1].split("\nBOUND INPUT IDS\n", 1)[0])
        plan = next(row["content"] for row in documents if row["artifact_ref"] == "artifact-plan")
        assert hashlib.sha256(plan.encode("utf-8")).hexdigest() == os.environ[PLAN_SHA]
    accepted = content == GOOD + b"#" * int(os.environ.get(PAD, "0"))
    row = {"role": "checker", "manifest_matches": True, "accepted": accepted}
    if plan is not None:
        row.update(plan_whole=True, frame_bytes=len(TASK.encode("utf-8")), file_bytes=len(content))
    if os.environ.get(PROSE):
        row.update(shape_told="no prose, no code fence" in TASK and "Then explain your reasons." not in TASK)
    _log(row)
    prose = "answer() returns 2, which the instruction forbids.\n" if os.environ.get(PROSE) else ""
    sys.stdout.write("VERDICT: accept\n" if accepted else "VERDICT: reject\n" + prose + json.dumps(PAYLOAD) + "\n")
    return 0


def _run(checker=False):
    return _checker() if checker else _doer()


_ORIGINAL_READ = _fakecodex._read_task


def main():
    _fakecodex._read_task = _read
    _fakecodex._run_task = _run
    return _fakecodex.main()
