"""Guards for D/THREAT-0's early Day-1/Day-2 threat matrix.

The matrix is intentionally not a security-pass counter. This module holds the
opposite relation: every seam that does not exist is spelled PENDING, names its
future slice and resolves to a real hostile fixture, but has no green test stub
using the reserved permanent-regression name.
"""
from __future__ import annotations

import ast
from pathlib import Path
import re

from tests import sabotage_fixtures as sf


ROOT = Path(__file__).parents[1]
MATRIX = ROOT / "docs" / "audits" / "2026-08-13-v2-threat-matrix.md"
EXPECTED_IDS = frozenset({
    "CONF-STALE", "CONF-DIGEST", "PATH-SCOPE", "PATH-CWD", "SHELL-INJECT",
    "TIMEOUT", "OUTPUT-BOMB", "DUPLICATE-IDEMPOTENCY", "FOREIGN-PID",
    "PORTAL-PREVIEW", "HARDLINK-PREVIEW", "PORTAL-CONFIRM", "HARDLINK-CONFIRM",
    "RECEIPT-TAMPER", "RESTART", "DISCONNECT", "VERIFY-FAIL", "CSRF-ORIGIN",
})
HELD_IDS = frozenset({
    "PATH-SCOPE", "PORTAL-PREVIEW", "HARDLINK-PREVIEW", "RECEIPT-TAMPER"})
PENDING_IDS = EXPECTED_IDS - HELD_IDS
FIELDS = frozenset({"Status", "Slice", "Fixture", "Expected invariant", "Regression"})


def _records():
    """Parse only the delimited matrix records, not explanatory prose."""
    text = MATRIX.read_text(encoding="utf-8")
    body = text.split("<!-- THREAT-MATRIX:START -->", 1)[1]
    body = body.split("<!-- THREAT-MATRIX:END -->", 1)[0]
    records = {}
    for chunk in body.split("\n### "):
        chunk = chunk.strip()
        if not chunk:
            continue
        heading, *lines = chunk.splitlines()
        threat_id = heading.split(" — ", 1)[0]
        fields = {}
        continuation = None
        for line in lines:
            if line.startswith("- ") and ": " in line:
                name, value = line[2:].split(": ", 1)
                fields[name] = value
                continuation = None
            elif line.startswith("- ") and line.endswith(":"):
                continuation = line[2:-1]
                fields[continuation] = ""
            elif continuation is not None and line.startswith("  "):
                fields[continuation] = (fields[continuation] + " " + line.strip()).strip()
                continuation = None
        records[threat_id] = fields
    return records


def _literal(value):
    """Read a field that is exactly one Markdown code span."""
    match = re.fullmatch(r"`([^`]+)`", value)
    assert match is not None, value
    return match.group(1)


def test_matrix_names_every_required_threat_and_does_not_promote_pending_seams():
    records = _records()
    assert set(records) == EXPECTED_IDS
    assert all(set(row) == FIELDS for row in records.values())
    statuses = {threat_id: _literal(row["Status"])
                for threat_id, row in records.items()}
    assert {name for name, status in statuses.items() if status == "HELD"} == HELD_IDS
    assert {name for name, status in statuses.items() if status == "PENDING"} == PENDING_IDS
    assert set(statuses.values()) == {"HELD", "PENDING"}
    for threat_id in PENDING_IDS:
        slices = re.findall(r"`([^`]+)`", records[threat_id]["Slice"])
        assert slices and all("/" in slice_id for slice_id in slices), threat_id
        regression = _literal(records[threat_id]["Regression"])
        assert regression.startswith("PENDING: test_"), threat_id


def test_every_matrix_fixture_resolves_to_executable_test_support():
    used = set()
    for row in _records().values():
        names = re.findall(r"`([^`]+)`", row["Fixture"])
        assert names
        for name in names:
            fixture = getattr(sf, name, None)
            assert callable(fixture), name
            used.add(name)
    public = {name for name, value in vars(sf).items()
              if callable(value) and not name.startswith("_")}
    assert used <= public


def test_held_regressions_exist_and_pending_regressions_do_not_pretend_to_pass():
    records = _records()
    tests_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "tests").glob("test_*.py"))
    for threat_id in HELD_IDS:
        target = _literal(records[threat_id]["Regression"])
        relative, function = target.split("::", 1)
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        defined = {node.name for node in ast.walk(tree)
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        assert function in defined, threat_id
    for threat_id in PENDING_IDS:
        reserved = _literal(records[threat_id]["Regression"]).split(": ", 1)[1]
        assert f"def {reserved}(" not in tests_text, threat_id
