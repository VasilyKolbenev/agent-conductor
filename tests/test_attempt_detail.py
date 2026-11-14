"""The operator reads a single action through the public, read-only command route."""
from conductor.command.adapters import AdapterRegistry
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.seed_record import write_seed
from conductor.command.seed_stage import move_staged, stage_empty
from tests.relay_roads import CODEX, Site
from tests.test_command_http_api import PORT, TOKEN, get_headers, ids
from tests.test_patch_do_policy import PATCH, run_state, work_and_calls
from tests.test_policy_driver import attach_driver, wait_terminal
from tests.test_policy_runtime import NOW


def test_selected_attempt_reads_its_seal_without_touching_live_files(tmp_path):
    site = Site(tmp_path, CODEX)
    with site.owned():
        item = "work-001"
        seed = stage_empty(site.root, task_id="one", work_scope="one", work_item_id=item,
                           staged_at=NOW)
        write_seed(site.root, seed)
        move_staged(site.root, seed)
        work, calls = work_and_calls(site, PATCH, item=item)
        f = run_state(site.root, site.adapter, item=item)
        driver, execution = attach_driver(f)
        try:
            bounds = {"node_limits": [{"node_id": "do", "timeout_seconds": 30, "max_attempts": 1}],
                      "max_actions": 1, "max_action_seconds": 60, "max_total_task_seconds": 60,
                      "duration_seconds": 1800}
            preview = f.policy.preview("run", bounds)
            f.policy.authorize("run", {"authorization_id": "grant", "authorized_by": "owner",
                                       "terms": preview["terms"], "supersedes": None,
                                       "preview_digest": preview["preview_digest"]})
            finished = wait_terminal(f)
        finally:
            driver.stop()
            execution.shutdown()
        request, = (row.value for row in finished.records if row.kind == "action_request")
        assert calls == ["prepare", "apply", "check"]
        (work / "count.py").write_bytes(b"secret from the subsequent workspace\n")
        saved = (f.store.run_path("run") / "records.jsonl").read_bytes()
        api = CommandApi(f.store, AdapterRegistry([]), session=CommandSession(PORT, TOKEN),
                         budget=PRODUCT_COMMAND_BUDGET, clock=lambda: NOW, ids=ids(),
                         publish_run=lambda _run: None)
        url = f"/command/runs/run/steps/do/actions/{request.action_id}"
        answer = api.handle("GET", url, get_headers())
        assert answer.status == 200, answer.payload
        body = answer.payload
        assert (body["run_id"], body["node_id"], body["action_id"], body["attempt_id"]) == (
            "run", "do", request.action_id, request.attempt_id)
        assert (body["outcome"], body["files_total"]) == ("succeeded", 2)
        assert body["verdict"] == {"status": "verified", "instance_id": "checker",
                                   "adapter_id": "codex"}
        assert body["tests"]["status"] == "not_recorded"
        file, test = body["files"]
        assert file["path"] == "count.py" and file["diff_status"] == "available"
        assert "+    return sum(row == 'ok' for row in rows)" in file["lines"]
        assert test["path"] == "test_count.py" and test["state"] == "added"
        assert "subsequent workspace" not in str(body)
        assert api.handle("GET", url.replace("/do/", "/next/"), get_headers()).status == 404
        assert api.handle("GET", url + "-missing", get_headers()).status == 404
        assert api.handle("POST", url, get_headers()).status == 405
        assert api.handle("GET", url, get_headers(host="elsewhere.invalid")).status == 403
        assert (f.store.run_path("run") / "records.jsonl").read_bytes() == saved
