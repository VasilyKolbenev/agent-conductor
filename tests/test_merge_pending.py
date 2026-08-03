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

def test_self_verdict_does_not_satisfy_own_obligation():
    # role that reviews itself is schema-legal; a self-verdict must not
    # discharge the author's own review debt (PROTOCOL §6, self-verdicts).
    m = {**MAP, "cycle": {"phases": [], "roles": [
        {"id": "impl", "harness": "cc", "reviews": ["impl"]}]}}
    ls = [lane("claude", "impl", [finding("D-1")],
               verdicts={"D-1": {"disposition": "confirmed", "note": "self-ok"}})]
    state = merge.merge(m, None, ls, [], 0, NOW)
    assert merge.pending_verdicts(state) == {"impl": ["D-1"]}   # RED today: {}

def test_suspended_findings_never_appear_in_pending():
    ls = [lane("claude", "impl", [finding("D-1")]),
          lane("scan", "sec", [finding("D-1")])]        # id collision -> suspended
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert merge.pending_verdicts(state) == {}          # pin-test: passes today
