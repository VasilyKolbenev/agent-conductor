"""Map validation per spec §4.2: errors block, warnings inform."""
from conductor import schema


def valid_map() -> dict:
    return {
        "schema_version": 1,
        "project": "voice-app",
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
