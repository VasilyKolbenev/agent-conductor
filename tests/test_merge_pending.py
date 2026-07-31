from datetime import datetime, timezone
from conductor import merge
from tests.test_merge_review import MAP, lane, finding
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)

def test_pending_verdicts_lists_unverdicted_finding_ids_per_role():
    ls = [lane("claude", "impl", [finding("D-1"), finding("D-2")]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": ""}}),
          lane("scan", "sec")]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    pending = merge.pending_verdicts(state)
    assert pending["rev"] == ["D-2"]
    assert pending["sec"] == ["D-1", "D-2"]
