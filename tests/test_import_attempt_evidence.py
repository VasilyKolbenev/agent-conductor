"""An explicitly selected archived attempt can be imported without executing a harness."""
import json

import pytest

from conductor import ownership
from conductor.command.seed_record import write_seed
from conductor.command.seed_stage import move_staged, stage_empty
from tests.relay_roads import CODEX, Site
from tests.test_patch_do_policy import PATCH, run_state, work_and_calls
from tests.test_policy_driver import attach_driver, wait_terminal
from tests.test_policy_runtime import NOW


@pytest.fixture
def closed_run(tmp_path):
    site = Site(tmp_path, CODEX)
    with site.owned():
        item = "work-001"
        seed = stage_empty(site.root, task_id="one", work_scope="one", work_item_id=item,
                           staged_at=NOW)
        write_seed(site.root, seed)
        move_staged(site.root, seed)
        _, calls = work_and_calls(site, PATCH, item=item)
        f = run_state(site.root, site.adapter, item=item)
        driver, execution = attach_driver(f)
        try:
            bounds = {"node_limits": [{"node_id": "do", "timeout_seconds": 30, "max_attempts": 1}],
                      "max_actions": 1, "max_action_seconds": 60, "max_total_task_seconds": 60,
                      "duration_seconds": 1800}
            preview = f.policy.preview("run", bounds)
            f.policy.authorize("run", {"authorization_id": "grant", "authorized_by": "owner",
                                       "terms": preview["terms"],
                                       "preview_digest": preview["preview_digest"],
                                       "supersedes": None})
            run = wait_terminal(f)
        finally:
            driver.stop()
            execution.shutdown()
    assert calls == ["prepare", "apply", "check"]
    request, = (row.value for row in run.records if row.kind == "action_request")
    assert ownership.state(site.root)[1]["phase"] == "closed"
    return site.root, request


def test_cli_imports_only_selected_checked_snapshot_and_repeat_is_safe(closed_run, tmp_path):
    from conductor import attempt_evidence_import as entry

    target, request = closed_run
    source = tmp_path / "separate"
    source.mkdir()
    args = ["--source", str(source), "--target", str(target), "--run", request.run_id,
            "--node", request.node_id, "--action", request.action_id]
    out = entry.run(entry.options(args))
    assert out["attempt_id"] == request.attempt_id and out["verdict"]["status"] == "verified"
    assert out["tests"]["status"] == "not_recorded"
    assert not list(source.iterdir())
    root = ownership.data_root(target)
    snap_file, = (root / "accept" / request.run_id / "snapshots").glob("*.json")
    files = {row["path"]: row["sha256"].removeprefix("sha256:")
             for row in json.loads(snap_file.read_bytes())}
    report = {"run": request.run_id, "action": "verification/" + request.action_id,
              "tests": [1, 0, 0, 0], "manifest": out["manifest_digest"],
              "source_commit": None, "files": files}
    filename = tmp_path / "report.json"
    filename.write_text(json.dumps(report), encoding="utf-8")
    options = entry.options(args + ["--report", str(filename)])
    after = entry.run(options)
    assert after["tests"]["summary"] == {"total": 1, "errors": 0, "failures": 0, "skipped": 0}
    assert after == entry.run(options)
    assert ownership.state(target)[1]["phase"] == "closed"
    filename.write_text(json.dumps({**report, "attempt": "other"}), encoding="utf-8")
    with pytest.raises(ValueError):
        entry.run(options)
    assert entry.run(entry.options(args)) == after


def test_import_rejects_overlapping_paths_and_wrong_node(closed_run, tmp_path):
    from conductor import attempt_evidence_import as entry

    target, request = closed_run
    args = ["--target", str(target), "--run", request.run_id,
            "--node", "other-step", "--action", request.action_id]
    with pytest.raises(ValueError):
        entry.run(entry.options(["--source", str(target), *args]))
    source = tmp_path / "separate"
    source.mkdir()
    with pytest.raises(ValueError):
        entry.run(entry.options(["--source", str(source), *args]))
    assert not list(source.iterdir())
    assert ownership.state(target)[1]["phase"] == "closed"


def test_frozen_git_source_remains_untouched_even_if_current_branch_disagrees(tmp_path):
    from types import SimpleNamespace
    from conductor import attempt_evidence_import as entry, tool_pins
    from conductor.command.accept_manifest import FileImage, build_snapshot
    from conductor.command.attempt_base import read_attempt_base
    from conductor.command.seed_record import SeedRecord
    from tests.git_repo_helpers import GIT, commit, git, repository, snapshot

    if GIT is None:
        pytest.skip("git unavailable")
    source = repository(tmp_path)
    base = commit(source, {"count.py": b"old\n"})
    tree = git("rev-parse", "HEAD^{tree}", cwd=source).stdout.decode().strip()
    seed = SeedRecord("one", "one", "work-001", "git", base, tree, "sha1", None,
                      1, 4, False, "staging", (), (), (), NOW)
    commit(source, {"count.py": b"new HEAD\n"})
    (source / "count.py").write_bytes(b"working tree is private")
    pin = tmp_path / "pins"
    pin.mkdir()
    tool_pins.pin_tool("git", GIT, folder=pin)
    safe = tmp_path / "archive"
    safe.mkdir()
    manifest = build_snapshot({"count.py": FileImage(b"old\n")},
                              {"count.py": FileImage(b"after\n")}, object_format="sha1")
    before = snapshot(source)
    entry._base(source, safe, SimpleNamespace(run_id="run"), seed, manifest, pin)
    assert snapshot(source) == before
    assert read_attempt_base(safe, "run", seed, manifest.rows) == {"count.py": b"old\n"}


def test_private_report_is_rejected_before_reading_the_named_file(tmp_path, monkeypatch):
    from conductor import attempt_evidence_import as entry

    def never_read(*_args):
        pytest.fail("opened a private profile file")

    monkeypatch.setattr(entry, "_read", never_read)
    with pytest.raises(ValueError, match="local JSON file"):
        entry._report(tmp_path / ".codex" / "auth.json", tmp_path, None, None, None)


def test_old_git_is_refused_before_it_reads_the_original_repository(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from conductor import attempt_evidence_import as entry

    calls = []

    def pinned(args, *_, **_kwargs):
        calls.append(args)
        return SimpleNamespace(exit_code=129, output=b"unknown option: --no-lazy-fetch")

    monkeypatch.setattr(entry.server_git, "project_git_reader", lambda *a, **kw: pinned)
    with pytest.raises(ValueError, match="no-lazy-fetch"):
        entry._git(tmp_path, None)
    assert calls == [["--no-lazy-fetch", "--version"]]
