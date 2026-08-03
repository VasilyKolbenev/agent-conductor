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
        "findings": [{"id": "D-2", "title": "config missing", "severity": "blocker",
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

def test_non_string_detail_and_evidence_are_errors():
    # detail/evidence are optional, but when present they must be strings —
    # they now travel into state.json verbatim (spec §6.1).
    lane = valid_lane()
    lane["findings"][0]["detail"] = 42
    lane["findings"][0]["evidence"] = ["x"]
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("detail" in e and "must be a string" in e for e in errors)
    assert any("evidence" in e and "must be a string" in e for e in errors)

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
    assert len([e for e in errors if "verdicts" in e]) == 1

def test_map_status_scalar_is_single_error():
    lane = valid_lane(); lane["map_status"] = "backend"
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("map_status" in e and "must be" in e for e in errors)
    assert len([e for e in errors if "map_status" in e]) == 1

def test_waits_scalar_is_single_error():
    lane = valid_lane(); lane["waits_on_human"] = "w-1"
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("waits_on_human" in e and "must be a list" in e for e in errors)
    assert len([e for e in errors if "waits_on_human" in e]) == 1

def test_invariants_scalar_is_single_error():
    lane = valid_lane(); lane["invariants"] = "main-untouched"
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("invariants" in e and "must be a list" in e for e in errors)
    assert len([e for e in errors if "invariants" in e]) == 1

def test_now_scalar_is_single_error():
    lane = valid_lane(); lane["now"] = "busy"
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("now" in e and "must be" in e for e in errors)
    assert len([e for e in errors if "now" in e]) == 1


def test_unhashable_map_status_value_does_not_crash():
    lane = valid_lane(); lane["map_status"]["backend"] = ["pass"]
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("map_status" in e for e in errors)

def test_unhashable_finding_severity_does_not_crash():
    lane = valid_lane(); lane["findings"][0]["severity"] = ["blocker"]
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("severity" in e for e in errors)

def test_unhashable_verdict_disposition_does_not_crash():
    lane = valid_lane(); lane["verdicts"]["D-1"]["disposition"] = {"x": 1}
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("disposition" in e for e in errors)

def test_unhashable_wait_kind_does_not_crash():
    lane = valid_lane(); lane["waits_on_human"][0]["kind"] = {}
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("kind" in e for e in errors)

def test_unhashable_event_kind_does_not_crash():
    event = {"ts": "2026-07-29T21:05:00+03:00", "author": "claude",
              "kind": ["ok"], "text": "t"}
    errors = schema.validate_event(event)
    assert any("kind" in e for e in errors)

def test_staleness_after_minutes_bool_is_error():
    lane = valid_lane(); lane["staleness_after_minutes"] = True
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("staleness_after_minutes" in e for e in errors)

def test_staleness_nan_is_error():
    # NaN passes isinstance(float) but crashes timedelta in merge — reject here.
    lane = valid_lane(); lane["staleness_after_minutes"] = float("nan")
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("staleness_after_minutes" in e for e in errors)

def test_staleness_infinity_is_error():
    lane = valid_lane(); lane["staleness_after_minutes"] = float("inf")
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("staleness_after_minutes" in e for e in errors)

def test_staleness_negative_infinity_is_error():
    lane = valid_lane(); lane["staleness_after_minutes"] = float("-inf")
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("staleness_after_minutes" in e for e in errors)

def test_staleness_zero_is_error():
    lane = valid_lane(); lane["staleness_after_minutes"] = 0
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("staleness_after_minutes" in e for e in errors)

def test_staleness_negative_is_error():
    lane = valid_lane(); lane["staleness_after_minutes"] = -5
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("staleness_after_minutes" in e for e in errors)

def test_staleness_positive_float_is_valid():
    lane = valid_lane(); lane["staleness_after_minutes"] = 0.5
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert errors == []


def test_refs_scalar_is_single_error():
    lane = valid_lane(); lane["findings"][0]["refs"] = "backend"
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert len([e for e in errors if "refs" in e]) == 1
    assert any("must be a list" in e for e in errors)

def test_refs_null_is_error_not_crash_downstream():
    lane = valid_lane(); lane["findings"][0]["refs"] = None
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("refs" in e for e in errors)

def test_refs_non_string_element_is_clear_error():
    lane = valid_lane(); lane["findings"][0]["refs"] = ["backend", ["nested"]]
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("refs" in e and "element" in e for e in errors)

def test_refs_absent_is_fine():
    lane = valid_lane(); del lane["findings"][0]["refs"]
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert errors == []


def test_wait_blocks_scalar_is_single_error():
    lane = valid_lane(); lane["waits_on_human"][0]["blocks"] = "D-2"
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert len([e for e in errors if "blocks" in e]) == 1
    assert any("must be a list" in e for e in errors)

def test_wait_blocks_null_is_error():
    lane = valid_lane(); lane["waits_on_human"][0]["blocks"] = None
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("blocks" in e for e in errors)

def test_wait_blocks_non_string_element_is_clear_error():
    lane = valid_lane(); lane["waits_on_human"][0]["blocks"] = ["D-2", 7]
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("blocks" in e and "element" in e for e in errors)

def test_wait_blocks_absent_is_fine():
    lane = valid_lane(); del lane["waits_on_human"][0]["blocks"]
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert errors == []


# --- container-element guards: `isinstance(x, dict)` inside a loop (audit §2) ---
# The four crash defects fixed in M1 all had this shape. A wrong-shape element
# must produce a clear error, never an AttributeError from a bare `.get`.

def test_findings_element_non_object_is_rejected_not_crash():
    lane = valid_lane(); lane["findings"] = ["D-2", 42]
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert [e for e in errors if "every finding needs a non-empty string id" in e]

def test_waits_on_human_element_non_object_is_rejected_not_crash():
    lane = valid_lane(); lane["waits_on_human"] = ["w-1", 42]
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert [e for e in errors if "every waits_on_human item needs an id" in e]

def test_invariants_element_non_object_is_rejected_not_crash():
    lane = valid_lane(); lane["invariants"] = ["main-untouched", 42]
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert [e for e in errors if "invariants need string id + boolean ok" in e]

def test_verdict_value_scalar_is_rejected_not_crash():
    # The dict guard is fused with the vocabulary check, so a scalar verdict
    # value lands on the same disposition error rather than crashing `.get`.
    lane = valid_lane(); lane["verdicts"]["D-1"] = "confirmed"
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert any("disposition" in e for e in errors)

def test_now_null_is_tolerated_not_rejected():
    # Deliberate tolerance: §4 accepts a null `now`. merge maps it to {} so the
    # §6.1 shape holds — pinned by
    # test_merge_lanes.py::test_null_now_is_emitted_as_an_empty_object.
    lane = valid_lane(); lane["now"] = None
    errors, _ = schema.validate_lane(lane, filename_stem="claude")
    assert errors == []

def test_event_non_object_line_is_rejected_not_crash():
    # A JSON line that parses to a list, a scalar or null reaches validate_event;
    # the top-level guard must answer with one error, not an AttributeError.
    for obj in ("string", [1], None, 7):
        assert schema.validate_event(obj) == ["event line must be an object"]
