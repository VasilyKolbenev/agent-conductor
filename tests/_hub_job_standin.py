"""A stand-in for a hub inside a Windows job (helper of `test_hub_job.py`, not a test).

``python _hub_job_standin.py <go-file> <result-file> <home> <real|breakaway|none>``

The test puts this process into a job of its own and then creates the go file. The stand-in
reads the job it is in, tries to start one child with the real spawner (whose "head" is the
sleeper, so the child does nothing), and writes what happened to the result file: its own pid
and the job it read (so the test can tell that the process it put into the job is this one, and
not a launcher in front of it), the policy, whether a child was started, or the code a refusal
carried. `none` starts the child as if no policy were known, which is how the instrument proves
itself: a child that does not break away dies with its job. `breakaway` asks for the breakaway
whatever the job says, which is how the refusal of the OS itself is provoked.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from conductor.hub import job, spawn

SLEEPER = Path(__file__).resolve().with_name("_hub_job_sleeper.py")

go, result, home, which = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
while not go.exists():
    time.sleep(0.02)
in_job, flags = job.read_own_job()
record = {"pid": os.getpid(), "in_job": in_job, "flags": flags, "policy": job.own_policy()}
POLICIES = {"real": job.own_policy, "breakaway": lambda: "breakaway", "none": lambda: "none"}
spawner = spawn.Spawner(
    home, hub_origin="http://127.0.0.1:7700", head=(sys.executable, str(SLEEPER)),
    job_policy=POLICIES[which])
try:
    spawner.start(project_id="a" * 32, root=home / "project", port=0, mode="view")
    record["started"] = True
except spawn.SpawnRefused as refused:
    record.update(started=False, code=refused.code)
result.write_text(json.dumps(record), encoding="utf-8")
time.sleep(120)
