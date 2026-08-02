"""Map validation per spec §4.2: errors block, warnings inform."""
import datetime
import tomllib

from conductor import schema


def valid_map() -> dict:
    return {
        "schema_version": 1,
        "project": "web-app",
        "nodes": [
            {"id": "models", "label": "models", "kind": "artifact"},
            {"id": "backend", "label": "backend", "kind": "artifact",
             "depends_on": ["models"]},
        ],
        "cycle": {
            "phases": ["plan", "implement", "review"],
            "roles": [
                {"id": "implementer", "harness": "claude-code", "reviews": []},
                {"id": "reviewer", "harness": "codex", "reviews": ["implementer"]},
            ],
        },
        "invariants": [{"id": "main-untouched", "text": "main is protected"}],
    }


def test_valid_map_passes():
    errors, warnings = schema.validate_map(valid_map())
    assert errors == [] and warnings == []

def test_missing_schema_version_is_error():
    m = valid_map(); del m["schema_version"]
    errors, _ = schema.validate_map(m)
    assert any("schema_version" in e for e in errors)

def test_unknown_schema_version_is_warning_not_error():
    m = valid_map(); m["schema_version"] = 2
    errors, warnings = schema.validate_map(m)
    assert errors == [] and any("schema_version" in w for w in warnings)

def test_empty_nodes_is_error():
    m = valid_map(); m["nodes"] = []
    errors, _ = schema.validate_map(m)
    assert any("at least one node" in e for e in errors)

def test_duplicate_node_id_is_error():
    m = valid_map(); m["nodes"].append({"id": "models", "label": "x", "kind": "artifact"})
    errors, _ = schema.validate_map(m)
    assert any("duplicate node id" in e for e in errors)

def test_depends_on_unknown_id_is_error():
    m = valid_map(); m["nodes"][1]["depends_on"] = ["ghost"]
    errors, _ = schema.validate_map(m)
    assert any("ghost" in e for e in errors)

def test_reviews_unknown_role_is_error():
    m = valid_map(); m["cycle"]["roles"][1]["reviews"] = ["ghost"]
    errors, _ = schema.validate_map(m)
    assert any("ghost" in e for e in errors)

def test_map_with_only_nodes_is_valid():
    errors, warnings = schema.validate_map(
        {"schema_version": 1, "nodes": [{"id": "a", "label": "a", "kind": "artifact"}]})
    assert errors == [] and warnings == []

def test_cycle_scalar_is_error():
    m = valid_map(); m["cycle"] = "oops"
    errors, _ = schema.validate_map(m)
    assert any("cycle must be a table" in e for e in errors)

def test_phases_scalar_is_error():
    m = valid_map(); m["cycle"]["phases"] = "plan"
    errors, _ = schema.validate_map(m)
    assert any("cycle.phases must be a list of strings" in e for e in errors)

def test_phases_with_non_string_element_is_error():
    m = valid_map(); m["cycle"]["phases"] = ["plan", 5]
    errors, _ = schema.validate_map(m)
    assert any("cycle.phases must be a list of strings" in e for e in errors)

def test_roles_scalar_is_error():
    m = valid_map(); m["cycle"]["roles"] = "oops"
    errors, _ = schema.validate_map(m)
    assert any("cycle.roles must be a list of tables" in e for e in errors)

def test_depends_on_scalar_is_single_error():
    m = valid_map(); m["nodes"][1]["depends_on"] = "models"
    errors, _ = schema.validate_map(m)
    matches = [e for e in errors if "depends_on" in e]
    assert len(matches) == 1
    assert "must be a list" in matches[0]

def test_reviews_scalar_is_single_error():
    m = valid_map(); m["cycle"]["roles"][1]["reviews"] = "implementer"
    errors, _ = schema.validate_map(m)
    matches = [e for e in errors if "reviews" in e]
    assert len(matches) == 1
    assert "must be a list" in matches[0]

def test_invariants_scalar_is_error():
    m = valid_map(); m["invariants"] = "oops"
    errors, _ = schema.validate_map(m)
    assert any("invariants must be a list of tables" in e for e in errors)

def test_reviews_nested_list_element_is_clear_error_not_crash():
    m = valid_map(); m["cycle"]["roles"][1]["reviews"] = [["nested"]]
    errors, _ = schema.validate_map(m)
    assert any("reviews element must be a string" in e for e in errors)

def test_depends_on_nested_list_element_is_clear_error_not_crash():
    m = valid_map(); m["nodes"][1]["depends_on"] = [["nested"]]
    errors, _ = schema.validate_map(m)
    assert any("depends_on element must be a string" in e for e in errors)


# --- string-typed fields: TOML yields dates/ints for unquoted values (15.5) ---

def test_project_non_string_is_error():
    m = valid_map(); m["project"] = datetime.date(2026, 7, 30)
    errors, _ = schema.validate_map(m)
    assert any("project must be a string" in e for e in errors)

def test_node_label_toml_date_is_error():
    # tomllib parses `label = 2026-07-30` as datetime.date — not serializable.
    m = valid_map(); m["nodes"][0]["label"] = datetime.date(2026, 7, 30)
    errors, _ = schema.validate_map(m)
    assert any("label must be a string" in e for e in errors)

def test_node_kind_non_string_is_error():
    m = valid_map(); m["nodes"][0]["kind"] = 7
    errors, _ = schema.validate_map(m)
    assert any("kind must be a string" in e for e in errors)

def test_role_harness_non_string_is_error():
    m = valid_map(); m["cycle"]["roles"][0]["harness"] = datetime.datetime(2026, 7, 30)
    errors, _ = schema.validate_map(m)
    assert any("harness must be a string" in e for e in errors)

def test_invariant_text_non_string_is_error():
    m = valid_map(); m["invariants"][0]["text"] = 42
    errors, _ = schema.validate_map(m)
    assert any("text must be a string" in e for e in errors)

def test_node_row_is_warning_not_error():
    # ADR 0001: `row` is accepted-and-ignored with a warning — legacy maps
    # keep validating, layout hints never become semantics.
    m = valid_map(); m["nodes"][0]["row"] = 0
    errors, warnings = schema.validate_map(m)
    assert errors == []
    assert any("row is deprecated and ignored" in w for w in warnings)

def test_toml_dates_in_already_enforced_fields_are_errors():
    # Audit pin: these string fields were ALREADY guarded by isinstance
    # checks — prove TOML-native dates hit them (no new code needed).
    m = tomllib.loads(
        'schema_version = 1\n'
        '[[nodes]]\nid = 2026-07-30\nlabel = "a"\nkind = "artifact"\n'
        '[[nodes]]\nid = "b"\nlabel = "b"\nkind = "artifact"\n'
        'depends_on = [2026-07-30]\n'
        '[cycle]\nphases = [2026-07-30]\n'
        '[[cycle.roles]]\nid = 2026-07-30\nharness = "h"\n'
        '[[cycle.roles]]\nid = "r"\nharness = "h"\nreviews = [2026-07-30]\n'
        '[[invariants]]\nid = 2026-07-30\ntext = "t"\n')
    errors, _ = schema.validate_map(m)
    assert any("every node needs a non-empty string id" in e for e in errors)
    assert any("depends_on element must be a string" in e for e in errors)
    assert any("cycle.phases must be a list of strings" in e for e in errors)
    assert any("every role needs a non-empty string id" in e for e in errors)
    assert any("reviews element must be a string" in e for e in errors)
    assert any("every invariant needs a non-empty string id" in e for e in errors)
