"""Lane/event validation per spec §4.3–§4.4."""
from conductor import schema


def valid_lane() -> dict:
    return {
        "schema_version": 1,
        "author": "claude",
        "role": "implementer",
        "updated": "2026-07-29T21:20:00+03:00",
        "now": {"task": "fixing gate D", "since": "2026-07-29T20:00:00+03:00",
                "phase": "review"},
        "map_status": {"backend": "pass"},
        "findings": [{"id": "D-2", "title": "STT missing", "severity": "blocker",
                      "claim": "defect", "detail": "d", "evidence": "e",
                      "refs": ["backend"]}],
        "verdicts": {"D-1": {"disposition": "confirmed", "note": "reproduced"}},
        "waits_on_human": [{"id": "w-1", "kind": "decision", "title": "t",
                            "why": "w", "blocks": ["D-2"]}],
        "invariants": [{"id": "main-untouched", "ok": True}],
    }


def test_valid_lane_passes():
    errors, warnings = schema.validate_lane(valid_lane(), filename_stem="claude")
    assert errors == [] and warnings == []

def test_author_must_match_filename():
    errors, _ = schema.validate_lane(valid_lane(), filename_stem="codex")
    assert any("author" in e and "filename" in e for e in errors)

def test_bad_updated_is_error():
    lane = valid_lane(); lane["updated"] = "yesterday"
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("updated" in e for e in errors)

def test_bad_severity_is_error():
    lane = valid_lane(); lane["findings"][0]["severity"] = "huge"
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("severity" in e for e in errors)

def test_bad_disposition_is_error():
    lane = valid_lane(); lane["verdicts"]["D-1"]["disposition"] = "meh"
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("disposition" in e for e in errors)

def test_bad_map_status_value_is_error():
    lane = valid_lane(); lane["map_status"]["backend"] = "greenish"
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("map_status" in e for e in errors)

def test_bad_wait_kind_is_error():
    lane = valid_lane(); lane["waits_on_human"][0]["kind"] = "vibe"
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("kind" in e for e in errors)

def test_duplicate_finding_id_within_lane_is_error():
    lane = valid_lane()
    lane["findings"].append(dict(lane["findings"][0]))
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("duplicate finding id" in e for e in errors)

def test_role_is_optional():
    lane = valid_lane(); del lane["role"]
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert errors == []

def test_non_numeric_staleness_threshold_is_error():
    lane = valid_lane(); lane["staleness_after_minutes"] = "soon"
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("staleness_after_minutes" in e for e in errors)

def test_event_line_valid_and_invalid():
    ok = {"ts": "2026-07-29T21:05:00+03:00", "author": "claude",
          "kind": "fail", "text": "smoke failed"}
    assert schema.validate_event(ok) == []
    assert schema.validate_event({"kind": "sparkle"}) != []


def test_findings_scalar_is_single_error():
    lane = valid_lane(); lane["findings"] = "D-2"
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert len([e for e in errors if "findings" in e]) == 1
    assert any("must be a list" in e for e in errors)

def test_verdicts_non_dict_is_single_error():
    lane = valid_lane(); lane["verdicts"] = ["D-1"]
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("verdicts" in e and "must be" in e for e in errors)

def test_map_status_scalar_is_single_error():
    lane = valid_lane(); lane["map_status"] = "backend"
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("map_status" in e and "must be" in e for e in errors)

def test_waits_scalar_is_single_error():
    lane = valid_lane(); lane["waits_on_human"] = "w-1"
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("waits_on_human" in e and "must be a list" in e for e in errors)

def test_invariants_scalar_is_single_error():
    lane = valid_lane(); lane["invariants"] = "main-untouched"
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("invariants" in e and "must be a list" in e for e in errors)

def test_now_scalar_is_single_error():
    lane = valid_lane(); lane["now"] = "busy"
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("now" in e and "must be" in e for e in errors)
