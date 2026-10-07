"""A real `conduct up --mode view` child: the process a hub starts for a project on show.

The in-process witnesses of `test_view_mode.py` build a server and look at it. This one starts
the real command in its own process with the flags a hub gives (4.1.4), so what only an
interpreter can show is shown: the child reaches `serving` and says `view` in its status file,
answers the quota read from the hub's snapshot, never polls a quota source while an ACTIVE
child of the same project (the control, same fake source) does, and closes on end of file
with the ownership head `closed`.
"""
from __future__ import annotations

import json

from tests._drain_harness import WAIT, DrainProject, stays_true, wait_until

STORED_AT = "2026-08-11T11:59:01Z"
ANSWER = {"as_of": "2026-08-11T11:59:00Z", "max_age_seconds": 300.0,
          "providers": [{"provider_id": "codex", "availability": "available"}],
          "snapshots": [{"binding_id": "codex", "state": "observed"}]}


def _forget_the_polls(project: DrainProject) -> None:
    """The marker of poll `n` has the same name in every process: clear them between children."""
    for marker in project.control.glob("quota-poll-*"):
        marker.unlink()


def test_a_view_child_serves_from_the_hub_snapshot_never_polls_quota_and_closes_on_eof(
        tmp_path):
    project = DrainProject.build(tmp_path)
    try:
        active = project.start(hub=True, quota="poll")
        active.wait_serving()
        wait_until(lambda: project.quota_polls() >= 1, WAIT, "the active child to poll", active)
        active.close_stdin()
        assert active.wait_exit(WAIT) == 0
        _forget_the_polls(project)
        (project.home / "limits.json").write_text(json.dumps({
            "schema_version": 1, "project_id": project.project_id, "taken_at": STORED_AT,
            "quotas": ANSWER}), encoding="utf-8")

        view = project.start(hub=True, quota="poll", mode="view")
        view.wait_serving()
        assert view.status()["mode"] == "view"
        status, answer = view.http("GET", "/command/quotas")
        assert status == 200
        assert answer == {**ANSWER, "hub_snapshot": {
            "project_id": project.project_id, "taken_at": STORED_AT}}
        stays_true(lambda: project.quota_polls() == 0, 3.0, "the view child to poll no quota")

        view.close_stdin()
        assert view.wait_exit(WAIT) == 0
        view.wait_state("stopped")
        assert project.head_phase() == "closed"
    finally:
        project.close()
