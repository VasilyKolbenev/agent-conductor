"""Map validation per spec §4.2: errors block, warnings inform."""
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
