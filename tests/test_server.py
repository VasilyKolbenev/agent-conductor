"""Tests for conductor.server — merge broker, HTTP routes, SSE, staleness tick.

`start` is imported by Task 14's smoke test — keep it module-level and stable.
"""
import json
import threading
import urllib.error
import urllib.request

from conductor import server, store
from tests.test_store import write_project, good_lane


def start(root):
    srv = server.build(root, port=0)          # port 0 → OS-assigned
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, r.read(), dict(r.headers)


def test_routes(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    srv, base = start(root)
    try:
        status, body, headers = get(base + "/state.json")
        assert status == 200 and headers["Cache-Control"] == "no-store"
        state = json.loads(body)
        assert state["lanes"][0]["author"] == "claude"
        status, body, _ = get(base + "/")
        assert status == 200 and b"<title>" in body
        status, _, _ = get(base + "/lane/claude.json")
        assert status == 200
        for bad in ("/lane/..%2fmap.json", "/nope", "/lane/we!rd.json"):
            try:
                status, _, _ = get(base + bad)
            except urllib.error.HTTPError as e:
                status = e.code
            assert status == 404
    finally:
        srv.shutdown()


def test_sse_emits_on_file_change(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    srv, base = start(root)
    try:
        req = urllib.request.urlopen(base + "/events", timeout=10)
        line = req.readline()          # greeting frame, sent on connect
        assert line.startswith(b"data:")
        (root / "conductor" / "lanes" / "claude.json").write_text(
            good_lane().replace("11:00:00", "11:30:00"), encoding="utf-8")
        while True:                    # next non-blank line must be the change frame
            line = req.readline()
            assert line, "SSE stream closed before the change frame arrived"
            if line.strip():
                break
        assert line.startswith(b"data:")
    finally:
        srv.shutdown()


# --- additional coverage beyond the mandated set ---

def test_build_refuses_missing_conductor_dir(tmp_path):
    try:
        server.build(tmp_path, port=0)
        assert False, "expected StoreError"
    except store.StoreError as e:
        assert "conductor" in str(e)


def test_build_refuses_broken_map_at_startup(tmp_path):
    root = write_project(tmp_path, map_toml="= not toml")
    try:
        server.build(root, port=0)
        assert False, "expected StoreError"
    except store.StoreError as e:
        assert "map.toml" in str(e)


def test_runtime_map_breakage_keeps_last_good_state(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    srv, base = start(root)
    try:
        (root / "conductor" / "map.toml").write_text("= not toml", encoding="utf-8")
        srv.broker.refresh()           # deterministic: don't wait for the watcher
        status, body, _ = get(base + "/state.json")
        assert status == 200
        state = json.loads(body)
        assert state["lanes"][0]["author"] == "claude"      # last-good kept
        assert any("map" in w for w in state["warnings"])   # breakage surfaced
    finally:
        srv.shutdown()


def test_lane_route_serves_raw_stored_bytes(tmp_path):
    body_text = good_lane()
    root = write_project(tmp_path, lanes={"claude": body_text})
    srv, base = start(root)
    try:
        status, body, headers = get(base + "/lane/claude.json")
        assert status == 200 and body == body_text.encode("utf-8")
        assert headers["Cache-Control"] == "no-store"
    finally:
        srv.shutdown()


def test_lane_route_404_for_unknown_author(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    srv, base = start(root)
    try:
        try:
            status, _, _ = get(base + "/lane/ghost.json")
        except urllib.error.HTTPError as e:
            status = e.code
        assert status == 404
    finally:
        srv.shutdown()


def test_binds_loopback_only(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    srv, base = start(root)
    try:
        assert srv.server_address[0] == "127.0.0.1"
    finally:
        srv.shutdown()


def test_busy_port_raises_instead_of_double_binding(tmp_path):
    # Windows SO_REUSEADDR would silently hijack a live port; the design
    # wants a startup failure (exit 1 via OSError) instead.
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    srv, _ = start(root)
    try:
        try:
            server.build(root, port=srv.server_address[1])
            assert False, "expected OSError for a busy port"
        except OSError:
            pass
    finally:
        srv.shutdown()


def test_refresh_reports_no_change_when_files_unchanged(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    srv, _ = start(root)
    try:
        assert srv.broker.refresh() is False   # same files → generated_at ignored
    finally:
        srv.shutdown()
