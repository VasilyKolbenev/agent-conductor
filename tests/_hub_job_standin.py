"""A stand-in for a hub inside a Windows job (helper of `test_hub_job.py`, not a test).

``python _hub_job_standin.py <go-file> <result-file> <home> <real|none>``

The test puts this process into a job of its own and then creates the go file. The stand-in
reads the policy of the job it is in, tries to start one child with the real spawner (whose
"head" is the sleeper, so the child does nothing), and writes what happened to the result file:
the policy it read, whether a child was started, or the code a refusal carried. `none` starts
the child as if no policy were known, which is how the instrument proves itself: a child that
does not break away dies with its job.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from conductor.hub import job, spawn

SLEEPER = Path(__file__).resolve().with_name("_hub_job_sleeper.py")

go, result, home, which = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
while not go.exists():
    time.sleep(0.02)
record = {"policy": job.own_policy()}
spawner = spawn.Spawner(
    home, hub_origin="http://127.0.0.1:7700", head=(sys.executable, str(SLEEPER)),
    job_policy=job.own_policy if which == "real" else (lambda: "none"))
try:
    spawner.start(project_id="a" * 32, root=home / "project", port=0, mode="view")
    record["started"] = True
except spawn.SpawnRefused as refused:
    record.update(started=False, code=refused.code)
result.write_text(json.dumps(record), encoding="utf-8")
time.sleep(120)
