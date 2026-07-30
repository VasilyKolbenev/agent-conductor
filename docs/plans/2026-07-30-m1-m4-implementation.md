# agent-conductor M1–M4 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the working core of Conduct: protocol + validation + merge engine (M1), the five-command CLI (M2), the live SSE server and panel (M3), and the bundled demo with CI (M4).

**Architecture:** A pure functional core (`schema.py`, `merge.py`, `prompts.py` — no I/O, fully golden-tested) wrapped by two thin I/O surfaces: a tolerant filesystem loader (`store.py`) and a loopback HTTP/SSE server (`server.py`). The panel is a single static HTML file consuming `/state.json` + `/events`. Everything the merger computes is defined normatively in the spec §5/§5.1 — tests mirror those tables rule by rule.

**Tech Stack:** Python ≥ 3.11, stdlib only at runtime (`tomllib`, `http.server`, `json`, `argparse`, `importlib.resources`). Dev: pytest. No build step for the panel (vanilla JS, no CDN).

**Spec:** `docs/specs/2026-07-29-agent-conductor-design.md` — section references (§) below point there. Where this plan refines the spec, the refinement is marked **[plan decision]** with rationale.

**Branch:** all work on `feature/m1-m4`, created from `main`. Commit after every green step; never commit red.

**Three [plan decisions] up front** (refinements, not contradictions):

1. `store.py` is added to the §11 module list: tolerant loading is needed by `validate`, `prompt`, *and* the server — putting it in `server.py` would force CLI→server imports. Pure core stays pure.
2. Demo fixtures live at `src/conductor/_demo/conductor/…` (packaged automatically via the package itself) instead of a repo-root `demo/`; a root `demo/README.md` points there. Rationale: `importlib.resources` serves files that live inside the package; a repo-root directory would need custom wheel forced-includes — more packaging machinery for zero user benefit.
3. The panel lives at `src/conductor/panel/index.html` (spec §11 sketches repo-root `panel/`) — same `importlib.resources` rationale as decision 2: the server must serve it from the installed package.

---

## Chunk 1: Scaffold + PROTOCOL.md + schema.py (M1a)

### Task 1: Repository scaffold

**Files:**
- Create: `pyproject.toml`, `LICENSE`, `.gitignore`, `src/conductor/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Create the branch**

```bash
git checkout -b feature/m1-m4
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "agent-conductor"
version = "0.1.0.dev0"
description = "A local, decision-centric control plane for heterogeneous AI coding agents. Your agents write lanes; you conduct."
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
authors = [{ name = "Vasily Kolbenev" }]
keywords = ["agents", "ai", "orchestration", "observability", "local-first"]
classifiers = [
  "Development Status :: 3 - Alpha",
  "Environment :: Console",
  "License :: OSI Approved :: MIT License",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
conduct = "conductor.__main__:main"

[project.urls]
Repository = "https://github.com/VasilyKolbenev/agent-conductor"

[tool.hatch.build.targets.wheel]
packages = ["src/conductor"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Write `LICENSE`** — standard MIT text, year `2026`, holder `Vasily Kolbenev`.

- [ ] **Step 3b: Write a stub `README.md`** (the full README is M6; this exists because `pyproject.toml` declares `readme = "README.md"` and hatchling fails the editable install without the file):

```markdown
# Conduct

A local, decision-centric control plane for heterogeneous AI coding agents.
Your agents write lanes. You conduct.

Work in progress — see `docs/specs/` and `spec/PROTOCOL.md`.
```

- [ ] **Step 4: Write `.gitignore`**

```
__pycache__/
*.py[cod]
.venv/
dist/
build/
*.egg-info/
.pytest_cache/
```

- [ ] **Step 5: Write `src/conductor/__init__.py`**

```python
"""Conduct — a local, decision-centric control plane for AI coding agents."""

__version__ = "0.1.0.dev0"
# The protocol version constant lives in conductor.schema.SCHEMA_VERSION —
# single source of truth; nothing else redefines it.
```

- [ ] **Step 6: Create empty `tests/__init__.py`, install, sanity-run**

```bash
python -m venv .venv && .venv\Scripts\python -m pip install -e .[dev]
.venv\Scripts\python -m pytest -q
```
Expected: `no tests ran` (exit 5 is fine at this step only).

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "chore: scaffold zero-dependency package with conduct entry point"
```

### Task 2: `spec/PROTOCOL.md` (normative extraction)

**Files:**
- Create: `spec/PROTOCOL.md`

- [ ] **Step 1: Write PROTOCOL.md** — extract from the design spec **verbatim where normative**: §4 (directory layout, `map.toml` schema + validation rules, lane schema + closed vocabularies + finding lifecycle, `events.jsonl`, versioning) and §5 + §5.1 (merge semantics table, `state.json` shape). Add a short preamble: protocol v1, silence ≠ consent, tolerant-reader/strict-writer. Add one clarifying sentence the spec implies but does not state: *on an id collision, foreign verdicts remain visible on both collided rows while `review_state` stays `suspended`* (visibility policy, consistent with self-verdicts). Do **not** paraphrase rules — copy them, then adjust cross-references to be self-contained.

- [ ] **Step 2: Self-check** — grep PROTOCOL.md for every closed vocabulary term: dispositions (`confirmed`, `refuted`, `partial`), review states (`suspended`, `uncovered`, `unreviewed`, `agreed`, `disagreement`), severities (`blocker`, `major`, `minor`, `note`), node statuses (`pass`, `fail`, `blocked`, `running`, `idle`, `contested`), wait kinds (`decision`, `action`, `review`), event kinds (`ok`, `fail`, `warn`, `stop`, `info`) — and confirm each appears with its rule. Confirm the five-state precedence line is present.

- [ ] **Step 3: Commit**

```bash
git add spec/PROTOCOL.md && git commit -m "docs: extract normative protocol v1 from the design spec"
```

### Task 3: `schema.py` — vocabularies and map validation

**Files:**
- Create: `src/conductor/schema.py`
- Test: `tests/test_schema_map.py`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run — verify they fail**

```bash
.venv\Scripts\python -m pytest tests/test_schema_map.py -q
```
Expected: FAIL / errors (`schema` has no `validate_map`).

- [ ] **Step 3: Implement `schema.py` (map part + shared vocabularies)**

```python
"""Protocol v1 validation. Pure: dicts in, (errors, warnings) out. Spec §4."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = 1
SEVERITIES = frozenset({"blocker", "major", "minor", "note"})
DISPOSITIONS = frozenset({"confirmed", "refuted", "partial"})
NODE_STATUSES = frozenset({"pass", "fail", "blocked", "running", "idle"})
WAIT_KINDS = frozenset({"decision", "action", "review"})
EVENT_KINDS = frozenset({"ok", "fail", "warn", "stop", "info"})
DEFAULT_STALENESS_MINUTES = 360

Result = tuple[list[str], list[str]]  # (errors, warnings)


def _version_check(data: dict, where: str, errors: list, warnings: list) -> None:
    if "schema_version" not in data:
        errors.append(f"{where}: schema_version is required")
    elif data["schema_version"] != SCHEMA_VERSION:
        warnings.append(
            f"{where}: schema_version {data['schema_version']!r} is not {SCHEMA_VERSION}; "
            "proceeding without guessing")


def parse_iso(value: Any) -> datetime | None:
    """Tolerant ISO-8601 parse; None on failure (caller decides error vs warning).

    Naive timestamps are coerced to UTC: a tz-naive `updated` is sloppy but legal
    input, and comparing naive vs aware datetimes would crash the whole merge —
    a tolerant-reader violation (spec §3.5)."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)   # timezone imported at header
    return parsed


def validate_map(data: Any) -> Result:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return (["map: top level must be a table"], warnings)
    _version_check(data, "map", errors, warnings)

    nodes = data.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        errors.append("map: at least one node is required")
        nodes = []
    ids: set[str] = set()
    for n in nodes:
        nid = n.get("id") if isinstance(n, dict) else None
        if not isinstance(nid, str) or not nid:
            errors.append("map: every node needs a non-empty string id")
            continue
        if nid in ids:
            errors.append(f"map: duplicate node id {nid!r}")
        ids.add(nid)
    for n in nodes:
        if not isinstance(n, dict):
            continue
        for dep in n.get("depends_on", []):
            if dep not in ids:
                errors.append(f"map: node {n.get('id')!r} depends_on unknown id {dep!r}")

    cycle = data.get("cycle", {})
    roles = cycle.get("roles", []) if isinstance(cycle, dict) else []
    role_ids: set[str] = set()
    for r in roles:
        rid = r.get("id") if isinstance(r, dict) else None
        if not isinstance(rid, str) or not rid:
            errors.append("map: every role needs a non-empty string id")
            continue
        if rid in role_ids:
            errors.append(f"map: duplicate role id {rid!r}")
        role_ids.add(rid)
    for r in roles:
        if not isinstance(r, dict):
            continue
        for reviewed in r.get("reviews", []):
            if reviewed not in role_ids:
                errors.append(f"map: role {r.get('id')!r} reviews unknown role {reviewed!r}")

    phases = cycle.get("phases", []) if isinstance(cycle, dict) else []
    if not all(isinstance(p, str) for p in phases):
        errors.append("map: cycle.phases must be strings")

    inv_ids: set[str] = set()
    for inv in data.get("invariants", []):
        iid = inv.get("id") if isinstance(inv, dict) else None
        if not isinstance(iid, str) or not iid:
            errors.append("map: every invariant needs a non-empty string id")
            continue
        if iid in inv_ids:
            errors.append(f"map: duplicate invariant id {iid!r}")
        inv_ids.add(iid)
    return errors, warnings
```

- [ ] **Step 4: Run — verify pass**

```bash
.venv\Scripts\python -m pytest tests/test_schema_map.py -q
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/conductor/schema.py tests/test_schema_map.py
git commit -m "feat(schema): map.toml validation with closed vocabularies"
```

### Task 4: `schema.py` — lane and event validation

**Files:**
- Modify: `src/conductor/schema.py`
- Test: `tests/test_schema_lane.py`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run — verify fail** — `pytest tests/test_schema_lane.py -q` → FAIL.

- [ ] **Step 3: Implement `validate_lane` + `validate_event`** (append to `schema.py`)

```python
def validate_lane(data: Any, *, filename_stem: str) -> Result:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return ([f"lane {filename_stem}: top level must be an object"], warnings)
    where = f"lane {filename_stem}"
    _version_check(data, where, errors, warnings)

    if data.get("author") != filename_stem:
        errors.append(f"{where}: author {data.get('author')!r} must equal filename stem")
    if parse_iso(data.get("updated")) is None:
        errors.append(f"{where}: updated must be ISO-8601")
    role = data.get("role")
    if role is not None and (not isinstance(role, str) or not role):
        errors.append(f"{where}: role must be a non-empty string when present")

    threshold = data.get("staleness_after_minutes")
    if threshold is not None and not isinstance(threshold, (int, float)):
        errors.append(f"{where}: staleness_after_minutes must be a number")

    for node_id, status in (data.get("map_status") or {}).items():
        if status not in NODE_STATUSES:
            errors.append(f"{where}: map_status[{node_id!r}]={status!r} not in "
                          f"{sorted(NODE_STATUSES)}")

    seen: set[str] = set()
    for f in data.get("findings", []):
        fid = f.get("id") if isinstance(f, dict) else None
        if not isinstance(fid, str) or not fid:
            errors.append(f"{where}: every finding needs a non-empty string id")
            continue
        if fid in seen:
            errors.append(f"{where}: duplicate finding id {fid!r}")
        seen.add(fid)
        if f.get("severity") not in SEVERITIES:
            errors.append(f"{where}: finding {fid!r} severity {f.get('severity')!r} "
                          f"not in {sorted(SEVERITIES)}")
        for key in ("title", "claim"):
            if not isinstance(f.get(key), str) or not f.get(key):
                errors.append(f"{where}: finding {fid!r} needs a non-empty {key}")

    for fid, v in (data.get("verdicts") or {}).items():
        if not isinstance(v, dict) or v.get("disposition") not in DISPOSITIONS:
            errors.append(f"{where}: verdict {fid!r} disposition must be one of "
                          f"{sorted(DISPOSITIONS)}")

    wait_seen: set[str] = set()
    for w in data.get("waits_on_human", []):
        wid = w.get("id") if isinstance(w, dict) else None
        if not isinstance(wid, str) or not wid:
            errors.append(f"{where}: every waits_on_human item needs an id")
            continue
        if wid in wait_seen:
            errors.append(f"{where}: duplicate waits_on_human id {wid!r}")
        wait_seen.add(wid)
        if w.get("kind") not in WAIT_KINDS:
            errors.append(f"{where}: wait {wid!r} kind {w.get('kind')!r} "
                          f"not in {sorted(WAIT_KINDS)}")

    for inv in data.get("invariants", []):
        if not isinstance(inv, dict) or not isinstance(inv.get("id"), str) \
                or not isinstance(inv.get("ok"), bool):
            errors.append(f"{where}: invariants need string id + boolean ok")
    return errors, warnings


def validate_event(obj: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["event line must be an object"]
    if parse_iso(obj.get("ts")) is None:
        errors.append("event: ts must be ISO-8601")
    if not isinstance(obj.get("author"), str) or not obj.get("author"):
        errors.append("event: author is required")
    if obj.get("kind") not in EVENT_KINDS:
        errors.append(f"event: kind {obj.get('kind')!r} not in {sorted(EVENT_KINDS)}")
    if not isinstance(obj.get("text"), str) or not obj.get("text"):
        errors.append("event: text is required")
    return errors
```

- [ ] **Step 4: Run all — verify pass** — `pytest -q` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(schema): lane and event validation"
```

---

## Chunk 2: merge.py — the normative engine (M1b)

The heart. Every row of spec §5 gets a golden test **before** its implementation. All functions are pure; `now` is injected. Reference @superpowers:test-driven-development — RED first, always.

Input contract (fixed here, used by store/server later):

```python
merge(map_data: dict | None,        # parsed+schema-validated map, or None if broken
      map_error: str | None,        # why the map is broken (None when map_data given)
      lanes: list[dict],            # {"author": str, "data": dict|None, "error": str|None}
      events: list[dict],           # newest last, already line-validated
      skipped_events: int,
      now: datetime) -> dict        # state.json per spec §5.1
```

### Task 5: merge skeleton + lane classification (broken / stale / future)

**Files:**
- Create: `src/conductor/merge.py`
- Test: `tests/test_merge_lanes.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Lane classification: broken, stale, future-dated. Spec §5 rows Staleness/Broken."""
from datetime import datetime, timezone
from conductor import merge

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)

def _map():
    return {"schema_version": 1, "project": "p",
            "nodes": [{"id": "a", "label": "a", "kind": "artifact"}]}

def lane(author="claude", updated="2026-07-30T11:00:00+00:00", **over):
    data = {"schema_version": 1, "author": author, "updated": updated}
    data.update(over)
    return {"author": author, "data": data, "error": None}


def test_broken_lane_is_listed_and_nothing_inferred():
    state = merge.merge(_map(), None,
                        [{"author": "bad", "data": None, "error": "invalid JSON"}],
                        [], 0, NOW)
    assert state["lanes"][0]["broken"] is True
    assert state["lanes"][0]["error"] == "invalid JSON"
    assert state["kpi"]["broken_lanes"] == 1

def test_stale_lane_flagged_by_default_threshold():
    old = lane(updated="2026-07-30T05:00:00+00:00")   # 7h ago > 360min
    state = merge.merge(_map(), None, [old], [], 0, NOW)
    assert state["lanes"][0]["stale"] is True
    assert state["kpi"]["stale_lanes"] == 1

def test_custom_staleness_threshold_respected():
    old = lane(updated="2026-07-30T05:00:00+00:00",
               staleness_after_minutes=600)            # 7h < 10h
    state = merge.merge(_map(), None, [old], [], 0, NOW)
    assert state["lanes"][0]["stale"] is False

def test_future_dated_lane_warns():
    fut = lane(updated="2026-07-30T13:00:00+00:00")
    state = merge.merge(_map(), None, [fut], [], 0, NOW)
    assert any("future" in w for w in state["warnings"])

def test_naive_timestamp_is_coerced_to_utc_not_crash():
    naive = lane(updated="2026-07-30T11:00:00")        # no offset — sloppy but legal
    state = merge.merge(_map(), None, [naive], [], 0, NOW)
    assert state["lanes"][0]["stale"] is False          # 1h ago in UTC

def test_state_shape_minimum():
    state = merge.merge(_map(), None, [], [], 0, NOW)
    for key in ("schema_version", "generated_at", "project", "map", "cycle",
                "lanes", "findings", "disagreements", "human_queue",
                "invariants", "events_tail", "kpi", "warnings"):
        assert key in state

def test_broken_map_is_surfaced():
    state = merge.merge(None, "map: at least one node is required", [], [], 0, NOW)
    assert any("map" in w for w in state["warnings"])
    assert state["map"]["nodes"] == []
```

- [ ] **Step 2: Run — verify fail.**

- [ ] **Step 3: Implement the skeleton**

```python
"""The merge engine — pure functions implementing spec §5 exactly.

Every computed value is derived; no author can write a disagreement, a stale
flag, or a queue de-dup. Silence is never consent.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from conductor import schema
from conductor.schema import DEFAULT_STALENESS_MINUTES

EVENTS_TAIL = 500


def _lane_view(entry: dict, now: datetime, warnings: list[str]) -> dict:
    author = entry["author"]
    data = entry.get("data")
    if data is None:
        return {"author": author, "role": None, "updated": None, "stale": False,
                "broken": True, "error": entry.get("error") or "unreadable",
                "now": {}, "_data": None, "_dt": None, "_future": False}
    dt = schema.parse_iso(data.get("updated"))
    threshold = data.get("staleness_after_minutes", DEFAULT_STALENESS_MINUTES)
    future = dt is not None and dt > now
    if future:
        warnings.append(f"lane {author}: updated is in the future (clock skew?)")
    stale = dt is not None and not future and (now - dt) > timedelta(minutes=threshold)
    return {"author": author, "role": data.get("role"), "updated": data.get("updated"),
            "stale": stale, "broken": False, "error": None,
            "now": data.get("now", {}), "_data": data, "_dt": dt, "_future": future}


def merge(map_data: dict | None, map_error: str | None, lanes: list[dict],
          events: list[dict], skipped_events: int, now: datetime,
          *, extra_warnings: tuple[str, ...] | list[str] = ()) -> dict:
    # extra_warnings: schema-version and other loader-level warnings (§4.5) —
    # store.load collects them, callers pass them through so they surface in state.
    warnings: list[str] = list(extra_warnings)
    if map_data is None:
        warnings.append(f"map is unreadable: {map_error}")
        map_data = {"nodes": [], "cycle": {}, "invariants": []}
    if skipped_events:
        warnings.append(f"events.jsonl: skipped {skipped_events} malformed line(s)")

    views = [_lane_view(entry, now, warnings) for entry in lanes]
    live = [v for v in views if not v["broken"]]

    nodes = _nodes(map_data, live, warnings)
    findings = _findings(map_data, views, warnings)
    queue = _human_queue(live)
    invariants = _invariants(map_data, live, warnings)
    cycle = _cycle(map_data, live, warnings)

    lanes_out = [{k: v for k, v in view.items() if not k.startswith("_")}
                 for view in views]
    disagreements = [f for f in findings if f["review_state"] == "disagreement"]
    kpi = {
        "nodes_pass": sum(1 for n in nodes if n["status"] == "pass"),
        "nodes_total": len(nodes),
        "blockers": sum(1 for f in findings if f["severity"] == "blocker"),
        "queue": len(queue),
        "disagreements": len(disagreements),
        "broken_lanes": sum(1 for v in views if v["broken"]),
        "stale_lanes": sum(1 for v in views if v["stale"]),
    }
    return {
        "schema_version": schema.SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "project": map_data.get("project", ""),
        "map": {"nodes": nodes},
        "cycle": cycle,
        "lanes": lanes_out,
        "findings": findings,
        "disagreements": disagreements,
        "human_queue": queue,
        "invariants": invariants,
        "events_tail": list(reversed(events[-EVENTS_TAIL:])),
        "kpi": kpi,
        "warnings": warnings,
    }
```

Add **stub** implementations so this chunk's tests run (fleshed out task by task):

```python
def _nodes(map_data, live, warnings):
    return [{"id": n["id"], "label": n.get("label", n["id"]),
             "kind": n.get("kind", ""), "depends_on": n.get("depends_on", []),
             "status": "idle", "contested_by": []}
            for n in map_data.get("nodes", [])]

def _findings(map_data, views, warnings): return []
def _human_queue(live): return []
def _invariants(map_data, live, warnings): return []
def _cycle(map_data, live, warnings):
    cyc = map_data.get("cycle", {}) or {}
    return {"phases": cyc.get("phases", []),
            "roles": [{"id": r["id"], "harness": r.get("harness", ""),
                       "reviews": r.get("reviews", [])}
                      for r in cyc.get("roles", [])]}
```

- [ ] **Step 4: Run — verify pass** — `pytest tests/test_merge_lanes.py -q` → PASS.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(merge): skeleton, lane classification, state shape"`

### Task 6: node status, contested nodes

**Files:**
- Modify: `src/conductor/merge.py` (`_nodes`)
- Test: `tests/test_merge_nodes.py`

- [ ] **Step 1: Write the failing tests** — spec §5 rows *Node status* / *Contested* / *Unknown referenced ids*:

```python
from datetime import datetime, timezone
from conductor import merge
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)

def _map():
    return {"schema_version": 1, "project": "p",
            "nodes": [{"id": "a", "label": "a", "kind": "artifact"},
                      {"id": "b", "label": "b", "kind": "artifact"}]}

def lane(author, updated, status_map, **over):
    data = {"schema_version": 1, "author": author, "updated": updated,
            "map_status": status_map}
    data.update(over)
    return {"author": author, "data": data, "error": None}


def _node(state, nid):
    return next(n for n in state["map"]["nodes"] if n["id"] == nid)

# NOTE (spec insight): the §5 "most recently updated lane wins" clause can only
# ever run when all voters AGREE — any disagreement is contested first. So
# recency is unobservable in output and deliberately has no dedicated test.

def test_single_lane_sets_node_status():
    l1 = lane("only", "2026-07-30T11:00:00+00:00", {"a": "pass"})
    state = merge.merge(_map(), None, [l1], [], 0, NOW)
    assert _node(state, "a")["status"] == "pass"

def test_agreeing_lanes_are_not_contested():
    l1 = lane("x", "2026-07-30T10:00:00+00:00", {"a": "pass"})
    l2 = lane("y", "2026-07-30T11:00:00+00:00", {"a": "pass"})
    state = merge.merge(_map(), None, [l1, l2], [], 0, NOW)
    assert _node(state, "a")["status"] == "pass"
    assert _node(state, "a")["contested_by"] == []

def test_disagreeing_lanes_contest_the_node_with_all_authors():
    ls = [lane("x", "2026-07-30T10:00:00+00:00", {"a": "pass"}),
          lane("y", "2026-07-30T11:00:00+00:00", {"a": "fail"}),
          lane("z", "2026-07-30T09:00:00+00:00", {"a": "blocked"})]
    state = merge.merge(_map(), None, ls, [], 0, NOW)
    node = _node(state, "a")
    assert node["status"] == "contested"
    assert sorted(node["contested_by"]) == ["x", "y", "z"]

def test_unmentioned_node_is_idle():
    state = merge.merge(_map(), None, [], [], 0, NOW)
    assert _node(state, "b")["status"] == "idle"

def test_future_dated_lane_excluded_from_race_but_counts_for_contested():
    l1 = lane("past", "2026-07-30T11:00:00+00:00", {"a": "pass"})
    l2 = lane("fut", "2026-07-30T13:00:00+00:00", {"a": "pass"})
    state = merge.merge(_map(), None, [l1, l2], [], 0, NOW)
    assert _node(state, "a")["status"] == "pass"   # agreement → future lane harmless
    l3 = lane("fut2", "2026-07-30T13:00:00+00:00", {"a": "fail"})
    state2 = merge.merge(_map(), None, [l1, l3], [], 0, NOW)
    assert _node(state2, "a")["status"] == "contested"

def test_stale_lane_still_counts_for_node_status():
    old = lane("old", "2026-07-30T01:00:00+00:00", {"a": "fail"})
    state = merge.merge(_map(), None, [old], [], 0, NOW)
    assert _node(state, "a")["status"] == "fail"

def test_unknown_map_status_key_ignored_with_warning():
    l1 = lane("x", "2026-07-30T11:00:00+00:00", {"ghost": "pass"})
    state = merge.merge(_map(), None, [l1], [], 0, NOW)
    assert all(n["status"] == "idle" for n in state["map"]["nodes"])
    assert any("ghost" in w for w in state["warnings"])
```

- [ ] **Step 2: Run — verify fail.**
- [ ] **Step 3: Implement `_nodes`**

```python
def _nodes(map_data, live, warnings):
    known = {n["id"] for n in map_data.get("nodes", [])}
    votes: dict[str, list[tuple]] = {}          # node_id -> [(dt, future, author, status)]
    for v in live:
        for nid, status in (v["_data"].get("map_status") or {}).items():
            if nid not in known:
                warnings.append(
                    f"lane {v['author']}: map_status key {nid!r} is not a map node — ignored")
                continue
            votes.setdefault(nid, []).append((v["_dt"], v["_future"], v["author"], status))
    out = []
    for n in map_data.get("nodes", []):
        cast = votes.get(n["id"], [])
        statuses = {s for (_, _, _, s) in cast}
        if len(statuses) > 1:
            status, contested = "contested", sorted(a for (_, _, a, _) in cast)
        elif cast:
            eligible = [c for c in cast if not c[1]] or cast   # prefer non-future voters
            eligible.sort(key=lambda c: (c[0] is not None, c[0]))
            status, contested = eligible[-1][3], []
        else:
            status, contested = "idle", []
        out.append({"id": n["id"], "label": n.get("label", n["id"]),
                    "kind": n.get("kind", ""), "depends_on": n.get("depends_on", []),
                    "status": status, "contested_by": contested})
    return out
```

- [ ] **Step 4: Run — verify pass** (`pytest -q`, full suite stays green).
- [ ] **Step 5: Commit** — `git commit -am "feat(merge): node status with contested detection"`

### Task 7: findings, verdicts, review_state (the five-state precedence)

**Files:**
- Modify: `src/conductor/merge.py` (`_findings`)
- Test: `tests/test_merge_review.py`

- [ ] **Step 1: Write the failing tests** — every branch of §5 *Disagreement / Unreviewed / Uncovered / Review state / Id collision*, plus the two clarified corners (self-verdicts ignored; vacuous agreed):

```python
from datetime import datetime, timezone
from conductor import merge
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)

MAP = {"schema_version": 1, "project": "p",
       "nodes": [{"id": "n", "label": "n", "kind": "artifact"}],
       "cycle": {"phases": [],
                 "roles": [{"id": "impl", "harness": "cc", "reviews": []},
                           {"id": "rev", "harness": "cx", "reviews": ["impl"]},
                           {"id": "sec", "harness": "cx", "reviews": ["impl"]}]}}

def lane(author, role=None, findings=(), verdicts=None, updated="2026-07-30T11:00:00+00:00"):
    data = {"schema_version": 1, "author": author, "updated": updated,
            "findings": list(findings), "verdicts": verdicts or {}}
    if role:
        data["role"] = role
    return {"author": author, "data": data, "error": None}

def finding(fid="D-1", severity="blocker"):
    return {"id": fid, "title": "t", "severity": severity, "claim": "defect",
            "detail": "d", "evidence": "e", "refs": ["n"]}

def _f(state, fid):
    return next(f for f in state["findings"] if f["id"] == fid)


def test_confirmed_by_all_reviewing_roles_is_agreed():
    ls = [lane("claude", "impl", [finding()]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": ""}}),
          lane("scan", "sec", verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert _f(state, "D-1")["review_state"] == "agreed"

def test_refuted_by_any_lane_is_disagreement():
    ls = [lane("claude", "impl", [finding()]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "refuted", "note": "no"}}),
          lane("scan", "sec", verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert _f(state, "D-1")["review_state"] == "disagreement"
    assert state["kpi"]["disagreements"] == 1

def test_observer_can_dispute_without_role():
    ls = [lane("claude", "impl", [finding()]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": ""}}),
          lane("scan", "sec", verdicts={"D-1": {"disposition": "confirmed", "note": ""}}),
          lane("watcher", None, verdicts={"D-1": {"disposition": "partial", "note": "hm"}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert _f(state, "D-1")["review_state"] == "disagreement"

def test_silent_reviewing_role_is_unreviewed_never_agreed():
    ls = [lane("claude", "impl", [finding()]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": ""}}),
          lane("scan", "sec")]                       # sec present but silent
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert _f(state, "D-1")["review_state"] == "unreviewed"

def test_absent_reviewing_role_is_uncovered():
    ls = [lane("claude", "impl", [finding()]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)   # nobody holds "sec"
    assert _f(state, "D-1")["review_state"] == "uncovered"

def test_two_lanes_same_role_any_one_satisfies():
    m = {**MAP, "cycle": {"phases": [], "roles": [
        {"id": "impl", "harness": "cc", "reviews": []},
        {"id": "rev", "harness": "cx", "reviews": ["impl"]}]}}
    ls = [lane("claude", "impl", [finding()]),
          lane("codex1", "rev"),
          lane("codex2", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    state = merge.merge(m, None, ls, [], 0, NOW)
    assert _f(state, "D-1")["review_state"] == "agreed"

def test_self_verdict_visible_but_ignored_in_computation():
    # Spec §5: self-verdicts are ignored in ALL review-state computation, yet
    # "per-author detail always remains visible in the finding's verdicts".
    ls = [lane("claude", "impl", [finding()],
               verdicts={"D-1": {"disposition": "refuted", "note": "self-doubt"}}),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": ""}}),
          lane("scan", "sec", verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    f = _f(state, "D-1")
    assert f["review_state"] == "agreed"                      # self-refute ignored
    assert f["verdicts"]["claude"]["disposition"] == "refuted"  # but still visible

def test_unknown_role_becomes_observer_with_warning():
    ls = [lane("claude", "impl", [finding()]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": ""}}),
          lane("scan", "sec", verdicts={"D-1": {"disposition": "confirmed", "note": ""}}),
          lane("mystery", "ghost-role",
               verdicts={"D-1": {"disposition": "refuted", "note": "x"}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert any("ghost-role" in w for w in state["warnings"])
    # observer verdicts still count for disputes:
    assert _f(state, "D-1")["review_state"] == "disagreement"
    assert _f(state, "D-1")["verdicts"]["mystery"]["role"] is None

def test_unknown_finding_refs_dropped_with_warning():
    bad = finding(); bad["refs"] = ["n", "ghost-node"]
    ls = [lane("claude", "impl", [bad])]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert _f(state, "D-1")["refs"] == ["n"]
    assert any("ghost-node" in w for w in state["warnings"])

def test_finding_with_no_reviewing_roles_is_vacuously_agreed():
    ls = [lane("watcher", None, [finding("O-1")])]   # observer's finding
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert _f(state, "O-1")["review_state"] == "agreed"

def test_id_collision_suspends_and_warns():
    ls = [lane("claude", "impl", [finding()]),
          lane("scan", "sec", [finding()]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "refuted", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    collided = [f for f in state["findings"] if f["id"] == "D-1"]
    assert len(collided) == 2
    assert all(f["review_state"] == "suspended" for f in collided)
    assert any("id-collision" in w for w in state["warnings"])
    assert state["kpi"]["disagreements"] == 0

def test_stale_verdict_warns_and_is_excluded():
    ls = [lane("codex", "rev", verdicts={"GONE": {"disposition": "refuted", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert any("stale verdict" in w for w in state["warnings"])
    assert state["findings"] == []

def test_verdicts_keyed_by_author_with_role_inside():
    ls = [lane("claude", "impl", [finding()]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": "ok"}}),
          lane("scan", "sec", verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    v = _f(state, "D-1")["verdicts"]["codex"]
    assert v == {"disposition": "confirmed", "note": "ok", "role": "rev"}
```

- [ ] **Step 2: Run — verify fail.**
- [ ] **Step 3: Implement `_findings`**

```python
def _findings(map_data, views, warnings):
    live = [v for v in views if not v["broken"]]
    roles = {r["id"]: r for r in (map_data.get("cycle", {}) or {}).get("roles", [])}
    role_holders: dict[str, list] = {}
    for v in live:
        role = v["role"]
        if role is not None and role not in roles:
            warnings.append(f"lane {v['author']}: role {role!r} is not in cycle.roles — "
                            "treated as observer")
            v = {**v, "role": None}
        if v["role"]:
            role_holders.setdefault(v["role"], []).append(v)

    owners: dict[str, list] = {}                      # finding id -> [(view, finding)]
    for v in live:
        for f in v["_data"].get("findings", []):
            owners.setdefault(f["id"], []).append((v, f))
    known_ids = set(owners)

    verdicts_on: dict[str, dict[str, dict]] = {}      # fid -> author -> verdict
    for v in live:
        for fid, verdict in (v["_data"].get("verdicts") or {}).items():
            if fid not in known_ids:
                warnings.append(f"lane {v['author']}: stale verdict on {fid!r} "
                                "(finding no longer exists) — excluded")
                continue
            verdicts_on.setdefault(fid, {})[v["author"]] = {
                "disposition": verdict.get("disposition"),
                "note": verdict.get("note", ""),
                "role": v["role"] if v["role"] in roles else None,
            }

    out = []
    for fid, owner_list in owners.items():
        collided = len(owner_list) > 1
        if collided:
            warnings.append(f"id-collision: finding {fid!r} authored by "
                            f"{sorted(v['author'] for v, _ in owner_list)}")
        for view, f in owner_list:
            author_role = view["role"] if view["role"] in roles else None
            all_verdicts = dict(verdicts_on.get(fid, {}))
            # Self-verdicts stay VISIBLE in output but are ignored in computation (§5).
            others = {a: v for a, v in all_verdicts.items() if a != view["author"]}
            reviewing = [r for r in roles.values() if author_role in r.get("reviews", [])]
            if collided:
                review_state = "suspended"
            elif any(v["disposition"] in ("refuted", "partial")
                     for v in others.values()):
                review_state = "disagreement"
            else:
                unreviewed = uncovered = False
                for r in reviewing:
                    holders = role_holders.get(r["id"], [])
                    if not holders:
                        uncovered = True
                    elif not any(a in others and others[a]["role"] == r["id"]
                                 for a in (h["author"] for h in holders)):
                        unreviewed = True
                review_state = ("unreviewed" if unreviewed
                                else "uncovered" if uncovered else "agreed")
            out.append({"id": fid, "title": f.get("title", ""),
                        "severity": f.get("severity", "note"),
                        "claim": f.get("claim", ""), "author": view["author"],
                        "refs": [r for r in f.get("refs", [])],
                        "verdicts": all_verdicts, "review_state": review_state})
    _warn_unknown_refs(map_data, out, warnings)
    return out


def _warn_unknown_refs(map_data, findings, warnings):
    known = {n["id"] for n in map_data.get("nodes", [])}
    for f in findings:
        unknown = [r for r in f["refs"] if r not in known]
        if unknown:
            warnings.append(f"finding {f['id']!r}: refs {unknown} are not map nodes — ignored")
        f["refs"] = [r for r in f["refs"] if r in known]
```

- [ ] **Step 4: Run full suite — verify pass.**
- [ ] **Step 5: Commit** — `git commit -am "feat(merge): findings, author-keyed verdicts, five-state review precedence"`

### Task 8: human queue, invariants, current phase

**Files:**
- Modify: `src/conductor/merge.py`
- Test: `tests/test_merge_queue_phase.py`

- [ ] **Step 1: Write the failing tests** — §5 rows *Human queue / Invariant state / Current phase*:

```python
from datetime import datetime, timezone
from conductor import merge
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)

MAP = {"schema_version": 1, "project": "p",
       "nodes": [{"id": "n", "label": "n", "kind": "artifact"}],
       "cycle": {"phases": ["plan", "implement", "review"], "roles": []},
       "invariants": [{"id": "inv-1", "text": "main untouched"}]}

def lane(author, updated="2026-07-30T11:00:00+00:00", **over):
    data = {"schema_version": 1, "author": author, "updated": updated}
    data.update(over)
    return {"author": author, "data": data, "error": None}

WAIT = {"id": "w-1", "kind": "decision", "title": "Bundle model?",
        "why": "size", "blocks": ["D-2"]}


def test_queue_dedupes_by_id_and_lists_all_sources():
    ls = [lane("a", waits_on_human=[WAIT]), lane("b", waits_on_human=[dict(WAIT)])]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert len(state["human_queue"]) == 1
    assert sorted(state["human_queue"][0]["sources"]) == ["a", "b"]
    assert state["kpi"]["queue"] == 1

def test_invariant_broken_by_one_lane_is_broken_globally():
    ls = [lane("a", invariants=[{"id": "inv-1", "ok": True}]),
          lane("b", invariants=[{"id": "inv-1", "ok": False}])]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    inv = state["invariants"][0]
    assert inv["ok"] is False and inv["broken_by"] == ["b"]

def test_unknown_invariant_id_ignored_with_warning():
    ls = [lane("a", invariants=[{"id": "ghost", "ok": False}])]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert all(i["id"] != "ghost" for i in state["invariants"])
    assert any("ghost" in w for w in state["warnings"])

def test_current_phase_from_most_recent_declaring_lane():
    ls = [lane("a", updated="2026-07-30T10:00:00+00:00",
               now={"task": "x", "phase": "plan"}),
          lane("b", updated="2026-07-30T11:00:00+00:00",
               now={"task": "y", "phase": "review"})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert state["cycle"]["current_phase"] == "review"

def test_stale_lane_does_not_set_current_phase():
    ls = [lane("a", updated="2026-07-30T01:00:00+00:00",   # stale
               now={"task": "x", "phase": "review"})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert "current_phase" not in state["cycle"]

def test_unknown_phase_is_undeclared_plus_warning():
    ls = [lane("a", now={"task": "x", "phase": "shipping"})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert "current_phase" not in state["cycle"]
    assert any("shipping" in w for w in state["warnings"])

def test_future_dated_lane_does_not_set_current_phase():
    ls = [lane("a", updated="2026-07-30T10:00:00+00:00",
               now={"task": "x", "phase": "plan"}),
          lane("b", updated="2026-07-30T13:00:00+00:00",   # future vs NOW
               now={"task": "y", "phase": "review"})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert state["cycle"]["current_phase"] == "plan"       # future lane excluded
```

- [ ] **Step 2: Run — verify fail.**
- [ ] **Step 3: Implement** (replace the three stubs)

```python
def _human_queue(live):
    queue: dict[str, dict] = {}
    for v in live:
        for w in v["_data"].get("waits_on_human", []):
            item = queue.setdefault(w["id"], {
                "id": w["id"], "kind": w.get("kind"), "title": w.get("title", ""),
                "why": w.get("why", ""), "blocks": list(w.get("blocks", [])),
                "sources": []})
            item["sources"].append(v["author"])
    return list(queue.values())


def _invariants(map_data, live, warnings):
    declared = {i["id"]: i for i in map_data.get("invariants", [])}
    state = {iid: {"id": iid, "ok": True, "broken_by": []} for iid in declared}
    for v in live:
        for inv in v["_data"].get("invariants", []):
            iid = inv.get("id")
            if iid not in declared:
                warnings.append(f"lane {v['author']}: invariant {iid!r} is not declared "
                                "in the map — ignored")
                continue
            if inv.get("ok") is False:
                state[iid]["ok"] = False
                state[iid]["broken_by"].append(v["author"])
    return list(state.values())


def _cycle(map_data, live, warnings):
    cyc = map_data.get("cycle", {}) or {}
    phases = cyc.get("phases", [])
    out = {"phases": phases,
           "roles": [{"id": r["id"], "harness": r.get("harness", ""),
                      "reviews": r.get("reviews", [])}
                     for r in cyc.get("roles", [])]}
    declaring = []
    for v in live:
        phase = (v["now"] or {}).get("phase")
        if phase is None or v["stale"] or v["_future"] or v["_dt"] is None:
            continue
        if phase not in phases:
            warnings.append(f"lane {v['author']}: now.phase {phase!r} is not a "
                            "cycle phase — treated as undeclared")
            continue
        declaring.append((v["_dt"], phase))
    if declaring:
        declaring.sort()
        out["current_phase"] = declaring[-1][1]
    return out
```

- [ ] **Step 4: Run full suite — verify pass.**
- [ ] **Step 5: Commit** — `git commit -am "feat(merge): human queue, invariants, current phase"`

### Task 9: `pending_verdicts` helper + mutation harness

**Files:**
- Modify: `src/conductor/merge.py`
- Create: `scripts/mutate_merge.py`
- Test: `tests/test_merge_pending.py`

- [ ] **Step 1: Failing test for the prompt-vending helper**

```python
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
```

- [ ] **Step 2: Run — fail. Step 3: Implement** (derives from state, stays pure):

```python
def pending_verdicts(state: dict) -> dict[str, list[str]]:
    """finding ids each reviewing role still owes a verdict on (for conduct prompt)."""
    roles = {r["id"]: r for r in state["cycle"]["roles"]}
    author_role = {ln["author"]: ln["role"] for ln in state["lanes"]}
    pending: dict[str, list[str]] = {rid: [] for rid in roles}
    for f in state["findings"]:
        if f["review_state"] == "suspended":
            continue
        for rid, role in roles.items():
            if author_role.get(f["author"]) not in role.get("reviews", []):
                continue
            if not any(v.get("role") == rid for v in f["verdicts"].values()):
                pending[rid].append(f["id"])
    return {rid: sorted(ids) for rid, ids in pending.items() if ids}
```

- [ ] **Step 4: Run — pass. Step 5: Write the mutation harness** `scripts/mutate_merge.py` (dev-only, mirrors the KALI discipline). Mechanism: read `src/conductor/merge.py`, apply ONE source-text substitution **in place**, run the targeted test file via `subprocess` (`pytest <file> -q`), assert nonzero exit (**RED**), then restore the original bytes in a `finally`. (Tests import `conductor.merge` — a temp-dir copy would never be imported; overwrite-and-restore is the working design.) The five mutations:
  1. disagreement requires `refuted` only (drop `partial`) → `tests/test_merge_review.py` red;
  2. drop the self-verdict exclusion (`others = all_verdicts`) → red;
  3. drop collision suspension (`collided = False`) → red;
  4. skip stale lanes in `_nodes` voting → `tests/test_merge_nodes.py` red;
  5. drop the future-exclusion in `_cycle` (remove `or v["_future"]`) → `tests/test_merge_queue_phase.py` red.
  Keep anchors on unique code lines; assert the anchor exists before substituting.

- [ ] **Step 6: Run the harness** — `python scripts/mutate_merge.py` → expected `5/5 mutations killed`.
- [ ] **Step 7: Commit** — `git add -A && git commit -m "feat(merge): pending_verdicts + mutation harness for merge rules"`

---

## Chunk 3: store.py + prompts.py + CLI (M2)

### Task 10: `store.py` — tolerant filesystem loading

**Files:**
- Create: `src/conductor/store.py`
- Test: `tests/test_store.py` (uses `tmp_path`)

- [ ] **Step 1: Failing tests**

```python
import json
from conductor import store

def write_project(tmp_path, map_toml=None, lanes=None, events=None):
    c = tmp_path / "conductor"; (c / "lanes").mkdir(parents=True)
    (c / "map.toml").write_text(map_toml if map_toml is not None else
        'schema_version = 1\nproject = "p"\n[[nodes]]\nid = "a"\nlabel = "a"\nkind = "artifact"\n',
        encoding="utf-8")
    for name, body in (lanes or {}).items():
        (c / "lanes" / f"{name}.json").write_text(body, encoding="utf-8")
    if events is not None:
        (c / "events.jsonl").write_text(events, encoding="utf-8")
    return tmp_path

def good_lane(author="claude"):
    return json.dumps({"schema_version": 1, "author": author,
                       "updated": "2026-07-30T11:00:00+00:00"})


def test_loads_valid_project(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()},
                         events='{"ts":"2026-07-30T10:00:00+00:00","author":"claude","kind":"ok","text":"hi"}\n')
    loaded = store.load(root)
    assert loaded.map_data is not None and loaded.map_error is None
    assert loaded.lanes[0]["author"] == "claude" and loaded.lanes[0]["error"] is None
    assert len(loaded.events) == 1 and loaded.skipped_events == 0

def test_malformed_lane_becomes_broken_entry_not_crash(tmp_path):
    root = write_project(tmp_path, lanes={"bad": "{not json"})
    loaded = store.load(root)
    assert loaded.lanes[0]["data"] is None and "bad" == loaded.lanes[0]["author"]
    assert loaded.lanes[0]["error"]

def test_author_filename_mismatch_is_broken(tmp_path):
    root = write_project(tmp_path, lanes={"impostor": good_lane(author="claude")})
    loaded = store.load(root)
    assert loaded.lanes[0]["data"] is None and "author" in loaded.lanes[0]["error"]

def test_malformed_event_lines_are_skipped_and_counted(tmp_path):
    root = write_project(tmp_path, events="not json\n" +
        '{"ts":"2026-07-30T10:00:00+00:00","author":"a","kind":"ok","text":"x"}\n')
    loaded = store.load(root)
    assert len(loaded.events) == 1 and loaded.skipped_events == 1

def test_broken_map_reported_not_raised(tmp_path):
    root = write_project(tmp_path, map_toml="= not toml")
    loaded = store.load(root)
    assert loaded.map_data is None and loaded.map_error

def test_schema_version_2_lane_surfaces_a_warning(tmp_path):
    body = good_lane().replace('"schema_version": 1', '"schema_version": 2')
    root = write_project(tmp_path, lanes={"claude": body})
    loaded = store.load(root)
    assert loaded.lanes[0]["error"] is None            # accepted, not rejected
    assert any("schema_version" in w for w in loaded.warnings)

def test_missing_conductor_dir_raises_clean_error(tmp_path):
    try:
        store.load(tmp_path)
        assert False, "expected StoreError"
    except store.StoreError as e:
        assert "conductor" in str(e)
```

- [ ] **Step 2: Run — fail. Step 3: Implement `store.py`**

```python
"""Tolerant reading of a project's conductor/ directory. The ONLY file-reading
surface shared by validate, prompt and the server. Strict writers, tolerant
readers (spec §3.5)."""
from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from conductor import schema

AUTHOR_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class StoreError(Exception):
    """The project root has no conductor/ directory (fail-closed startup)."""


@dataclass
class Loaded:
    map_data: dict | None
    map_error: str | None
    warnings: list[str] = field(default_factory=list)   # schema-version etc. (§4.5)
    lanes: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    skipped_events: int = 0


def conductor_dir(root: Path) -> Path:
    path = Path(root) / "conductor"
    if not path.is_dir():
        raise StoreError(f"no conductor/ directory under {root} — run `conduct init`")
    return path


def load(root: Path) -> Loaded:
    cdir = conductor_dir(root)
    out = Loaded(map_data=None, map_error=None)

    map_path = cdir / "map.toml"
    if not map_path.is_file():
        out.map_error = "map.toml is missing"
    else:
        try:
            data = tomllib.loads(map_path.read_text(encoding="utf-8"))
            errors, warnings = schema.validate_map(data)
            out.warnings.extend(warnings)
            if errors:
                out.map_error = "; ".join(errors)
            else:
                out.map_data = data
        except (OSError, tomllib.TOMLDecodeError) as e:
            out.map_error = f"map.toml unreadable: {e}"

    lanes_dir = cdir / "lanes"
    if lanes_dir.is_dir():
        for path in sorted(lanes_dir.glob("*.json")):
            stem = path.stem
            if not AUTHOR_RE.match(stem):
                out.lanes.append({"author": stem, "data": None,
                                  "error": f"invalid author filename {stem!r}"})
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                out.lanes.append({"author": stem, "data": None, "error": str(e)})
                continue
            errors, warnings = schema.validate_lane(data, filename_stem=stem)
            out.warnings.extend(warnings)     # §4.5: schema-version warnings surface
            if errors:
                out.lanes.append({"author": stem, "data": None,
                                  "error": "; ".join(errors)})
            else:
                out.lanes.append({"author": stem, "data": data, "error": None})

    events_path = cdir / "events.jsonl"
    if events_path.is_file():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                out.skipped_events += 1
                continue
            if schema.validate_event(obj):
                out.skipped_events += 1
            else:
                out.events.append(obj)
    return out
```

- [ ] **Step 4: Run — pass. Step 5: Commit** — `git commit -am "feat(store): tolerant conductor/ loader"`

### Task 11: `prompts.py` — bootstrap + state-aware role prompts

**Files:**
- Create: `src/conductor/prompts.py`
- Test: `tests/test_prompts.py`

- [ ] **Step 1: Failing tests**

```python
from datetime import datetime, timezone
from conductor import merge, prompts
from tests.test_merge_review import MAP, lane, finding
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


def test_bootstrap_prompt_names_the_contract_files():
    text = prompts.bootstrap_prompt()
    for token in ("map.toml", "conductor/", "schema_version", "nodes", "roles"):
        assert token in text

def test_role_prompt_is_state_aware():
    ls = [lane("claude", "impl", [finding("D-1"), finding("D-2")]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    text = prompts.role_prompt(state, "rev")
    assert "conductor/lanes/" in text and '"verdicts"' in text
    pending_section = text.split("awaiting your verdict")[1]
    assert "D-2" in pending_section        # still owed
    assert "D-1" not in pending_section    # already verdicted — must NOT be re-asked

def test_role_prompt_unknown_role_raises():
    state = merge.merge(MAP, None, [], [], 0, NOW)
    try:
        prompts.role_prompt(state, "ghost")
        assert False
    except prompts.UnknownRole:
        pass
```

- [ ] **Step 2: Run — fail. Step 3: Implement `prompts.py`** — deterministic template rendering, no LLM (§3.2). `bootstrap_prompt()` returns the fixed English instruction block: read the project's roadmap/plan/architecture docs, produce `conductor/map.toml` (embed the full commented TOML example from spec §4.2), list validation rules, tell the agent to run `conduct validate`. `role_prompt(state, role_id)` renders: mission line with the role id and reviewed roles; the exact lane path `conductor/lanes/<author>.json`; the full lane JSON template from spec §4.3 with the role pre-filled; the closed vocabularies; the current map node ids (from `state["map"]["nodes"]`); and a section `The following finding ids are awaiting your verdict:` fed by `merge.pending_verdicts(state).get(role_id, [])`. Raise `UnknownRole` when `role_id` is not in `state["cycle"]["roles"]`. Both functions pure string builders.

- [ ] **Step 4: Run — pass. Step 5: Commit** — `git commit -am "feat(prompts): bootstrap + state-aware role prompt vending"`

### Task 12: CLI — `validate`, `init`, `prompt`

**Files:**
- Create: `src/conductor/__main__.py`
- Test: `tests/test_cli.py` (subprocess-free: call `main(argv)` directly, capture with `capsys`)

- [ ] **Step 1: Failing tests**

```python
import json
from conductor.__main__ import main
from tests.test_store import write_project, good_lane


def test_validate_ok_project_exits_0(tmp_path, capsys):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    assert main(["validate", "--dir", str(root)]) == 0

def test_validate_schema_error_exits_1(tmp_path, capsys):
    root = write_project(tmp_path, lanes={"bad": "{not json"})
    assert main(["validate", "--dir", str(root)]) == 1
    assert "bad" in capsys.readouterr().out

def test_validate_referential_drift_warns_but_exits_0(tmp_path, capsys):
    lane_body = json.dumps({"schema_version": 1, "author": "claude",
                            "updated": "2026-07-30T11:00:00+00:00",
                            "map_status": {"ghost": "pass"}})
    root = write_project(tmp_path, lanes={"claude": lane_body})
    assert main(["validate", "--dir", str(root)]) == 0
    assert "ghost" in capsys.readouterr().out

def test_init_scaffolds_and_prints_bootstrap(tmp_path, capsys):
    assert main(["init", "--dir", str(tmp_path)]) == 0
    assert (tmp_path / "conductor" / "map.toml").is_file()
    assert (tmp_path / "conductor" / "lanes").is_dir()
    assert "map.toml" in capsys.readouterr().out

def test_init_refuses_existing(tmp_path, capsys):
    (tmp_path / "conductor").mkdir()
    assert main(["init", "--dir", str(tmp_path)]) == 1

def test_prompt_renders_role_and_fails_on_unknown(tmp_path, capsys):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    # map from write_project has no roles → unknown role must exit 1
    assert main(["prompt", "ghost", "--dir", str(root)]) == 1
```

- [ ] **Step 2: Run — fail. Step 3: Implement `__main__.py`** — `argparse` with subcommands; every command takes `--dir` (default `"."`, the **project root**, spec §6). `validate`: `store.load`; print every schema **error** prefixed with its source (broken lanes as `lane <author>: <error>` — the tests grep for the author name), exit 1 if any; otherwise run `merge.merge(..., extra_warnings=loaded.warnings)` and print `state["warnings"]` (referential drift + schema-version warnings, §4.5/§6), exit 0. `init`: refuse existing `conductor/`; write `lanes/`, empty `events.jsonl`, and a commented `map.toml` stub (the §4.2 example); print `prompts.bootstrap_prompt()`. `prompt <role>`: load + merge, `prompts.role_prompt`, print; `UnknownRole`/`StoreError`/broken map → message to stderr, exit 1. `up`/`demo`: added in later tasks — `parser.add_parser` now, body `raise SystemExit("not yet implemented")`. `main(argv=None) -> int`; the console script wraps it.

- [ ] **Step 4: Run — pass (full suite). Step 5: Commit** — `git commit -am "feat(cli): validate, init, prompt commands"`

---

## Chunk 4: server + panel (M3)

### Task 13: `server.py` — merge broker, HTTP routes, SSE, tick

**Files:**
- Create: `src/conductor/server.py`
- Create: `src/conductor/panel/index.html` (placeholder; replaced in Task 14)
- Modify: `src/conductor/__main__.py` (wire `up`)
- Test: `tests/test_server.py`

- [ ] **Step 1: Failing tests** (real HTTP against an ephemeral port; stdlib `urllib`):

```python
import json, threading, urllib.request
from conductor import server
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
```

- [ ] **Step 2: Run — fail. Step 3: Implement `server.py`** — components:
  - `Broker`: holds the latest merged state under a lock; `refresh()` runs `store.load` + `merge.merge(now=datetime.now(timezone.utc), extra_warnings=loaded.warnings)` and returns `True` when state changed (comparison on a deep copy **with `generated_at` removed**, spec §7); keeps raw lane bytes for `/lane/` passthrough.
  - `Watcher` thread: every 0.5 s stats every file under `conductor/` (name, mtime_ns, size); on fingerprint change → `refresh()`; independently, every 60 s → `refresh()` regardless (the staleness tick). On change, sets an event that all SSE clients wait on.
  - `Handler(BaseHTTPRequestHandler)`: `/` → packaged `panel/index.html` via `importlib.resources`; `/state.json` → broker state; `/lane/<author>.json` → 404 unless `store.AUTHOR_RE` matches and the file exists; `/events` → `text/event-stream`, sends one `data: {"kind":"state"}\n\n` frame **immediately on connect** (de-flakes the race between client registration and the first change) and then one per broker change signal (client re-fetches `/state.json` — keeps frames tiny); everything else 404. All responses `Cache-Control: no-store`.
  - `build(root, port) -> ThreadingHTTPServer` bound to `127.0.0.1` only; startup calls `store.conductor_dir` (raises `StoreError` → CLI exit 1) and refuses a broken map at startup (spec §6) while *runtime* map breakage keeps last-good + warning.
  - Wire `conduct up`: parse `--port` (default 7777), `server.build`, print the URL, `serve_forever()` with `KeyboardInterrupt` → clean 0.
  - **Placeholder panel** (so this task's `/` route test can go green before Task 14): create `src/conductor/panel/index.html` containing only `<title>Conduct</title><p>Panel arrives in the next task.</p>`. Task 14 replaces it wholesale.

- [ ] **Step 4: Run — pass. Step 5: Commit** — `git commit -am "feat(server): loopback HTTP + SSE with staleness tick"`

### Task 14: panel — port the proven seed to the protocol

**Files:**
- Create: `src/conductor/panel/index.html`
- Test: `tests/test_panel_smoke.py`

The layout/interaction model is ported from the battle-tested seed at
`C:\Users\User\Desktop\Jarvis\scratchpad\live_ui.html` (same author, same
session). **If the seed is unavailable** (any machine but this one), build
from spec §8 plus the delta list below alone — together they fully determine
the artifact. This task specifies the port as an explicit delta list — the
executor reads the seed once, then applies:

- [ ] **Step 1: Failing smoke test**

```python
import urllib.request
from tests.test_server import start
from tests.test_store import write_project, good_lane

def test_panel_serves_and_references_state(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    srv, base = start(root)
    try:
        with urllib.request.urlopen(base + "/", timeout=5) as r:
            html = r.read().decode()
        for token in ("state.json", "EventSource", "id=\"map\"", "id=\"queue\"",
                      "id=\"findings\"", "id=\"warnings\"", "prefers-color-scheme"):
            assert token in html
    finally:
        srv.shutdown()
```

- [ ] **Step 2: Run — fail. Step 3: Port with these deltas** (single file, vanilla JS, no CDN, ~same size as the seed):
  1. All UI strings **English**; `<title>` = `Conduct — <n> waiting on you` driven by `kpi.queue`.
  2. Data source: initial `fetch("/state.json")`; live via `new EventSource("/events")` → on message re-fetch `/state.json` (drop the seed's 10 s polling).
  3. Views per spec §8, mapped from `state.json` §5.1: **map graph** (SVG; nodes from `state.map.nodes`, edges from `depends_on`; layout: topological layering by longest-path depth, `contested` gets a distinct dashed+two-tone treatment and lists `contested_by` in the detail card), **cycle ring** (`cycle.phases` + `roles`; pulse only when `current_phase` present), **KPI rail** (exactly the `kpi` fields), **human queue** cards (`sources`, `blocks`), **findings table** (columns id/severity/claim/author/review_state; `review_state` chips include `suspended`; findings whose author has no reviewing roles render the "no reviewer assigned" hint per §5), **feed** (`events_tail`), and the **warnings banner** (count + click-through list) when `warnings` non-empty.
  4. Keep the seed's a11y properties: status never color-alone (glyph + text), `prefers-reduced-motion` kills the pulse, visible focus, dark/light via `prefers-color-scheme`.
  5. Element ids used by the smoke test: `map`, `cycle`, `kpis`, `queue`, `findings`, `feed`, `warnings`.

- [ ] **Step 4: Run — pass. Step 5: Manual visual check** — `conduct up` against a scratch project (`conduct init` in a temp dir, hand-write one lane), open `http://127.0.0.1:7777`, confirm: nodes light up, a lane edit re-renders within ~1 s without reload, warnings banner appears when you write a junk lane. Record what you saw in the commit message body.
- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat(panel): protocol-driven panel ported from the proven seed"`

---

## Chunk 5: demo + CI (M4)

### Task 15: demo fixtures + `conduct demo`

**Files:**
- Create: `src/conductor/_demo/conductor/map.toml`, `.../lanes/claude.json`, `.../lanes/codex.json`, `.../events.jsonl`, `demo/README.md`
- Create: `src/conductor/demo.py`
- Modify: `src/conductor/__main__.py` (wire `demo`)
- Test: `tests/test_demo.py`

The fixture replays the real release-gate case (sanitized, spec §10): a
desktop voice app whose offline-smoke gate failed; reviewer confirms two
findings and **partially disputes** one → one computed disagreement; one
genuine product decision in the human queue.

- [ ] **Step 1: Write the fixtures.** `map.toml`: project `voice-app`; nodes `models → backend`, `desktop`, `stage (backend, desktop)`, `installer (stage)`, `smoke (stage)`, `installed (installer)`; roles `implementer` (claude-code, reviews []) and `reviewer` (codex, reviews [implementer]); phases `plan/implement/review/human-gate`; invariants `main-protected`, `stage-sealed`. `lanes/claude.json`: role implementer; `map_status` all pass except `smoke: fail`, `installed: blocked`; findings `D-1` (blocker, "/live answers in 11.5 s against a 1.0 s budget"), `D-2` (blocker, "STT model missing from the bundle — masked by the dev machine's global cache"), `D-3` (blocker, "VAD fetched from the network at runtime, shipped model unused"); wait `w-stt` (decision, "Bundle the STT model (+461 MB) or download on first run?", blocks D-2); `now.phase: review`. `lanes/codex.json`: role reviewer; verdicts D-1 confirmed, D-2 confirmed, D-3 **partial** ("network fetch confirmed, but the shipped file may be a dead artifact — verify before bundling"). `events.jsonl`: ~10 lines telling the story in order (ok/ok/fail/stop/info). All timestamps recent-relative is impossible in static fixtures — use a fixed date and set both lanes `staleness_after_minutes: 52560000` (100 years) so the demo never renders stale. Verify vocabularies against `schema.py` as you write.

- [ ] **Step 2: Failing test**

```python
from conductor import demo
from conductor.__main__ import main

def test_demo_fixture_is_schema_valid(tmp_path):
    root = demo.materialize(tmp_path)
    assert main(["validate", "--dir", str(root)]) == 0

def test_demo_state_tells_the_story(tmp_path):
    root = demo.materialize(tmp_path)
    from conductor import store, merge
    from datetime import datetime, timezone
    loaded = store.load(root)
    state = merge.merge(loaded.map_data, loaded.map_error, loaded.lanes,
                        loaded.events, loaded.skipped_events,
                        datetime.now(timezone.utc))
    assert state["kpi"]["disagreements"] == 1          # D-3 partial
    assert state["kpi"]["queue"] == 1                  # w-stt
    assert state["kpi"]["blockers"] == 3
    smoke = next(n for n in state["map"]["nodes"] if n["id"] == "smoke")
    assert smoke["status"] == "fail"
```

- [ ] **Step 3: Run — fail. Step 4: Implement `demo.py`** — `materialize(target_dir)`: copy the packaged `_demo/conductor` tree (via `importlib.resources.files("conductor") / "_demo"`) into `target_dir`, return `target_dir`. Wire `conduct demo [--port]`: materialize into `tempfile.mkdtemp(prefix="conduct-demo-")`, then start the same server read-only. `demo/README.md` at repo root: one paragraph + pointer to the packaged path.
- [ ] **Step 5: Run — pass. Step 6: Commit** — `git commit -am "feat(demo): bundled real-case fixture and conduct demo"`

### Task 16: CI matrix

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the workflow** — trigger on push+PR; matrix `os: [ubuntu-latest, windows-latest]` × `python: ["3.11", "3.12"]`; steps: checkout, setup-python, `pip install -e .[dev]`, `pytest -q`, `python scripts/mutate_merge.py`, and the demo-drift gate from spec §12: materialize demo to a temp dir and `conduct validate --dir` it (exit 0 required).
- [ ] **Step 2: Commit & push the branch; verify CI is green on both OSes before proceeding.**

```bash
git add .github/workflows/ci.yml && git commit -m "ci: test matrix + mutation harness + demo drift gate"
git push -u origin feature/m1-m4
```

### Task 17: M1–M4 closeout

- [ ] **Step 1: Full local gate** — `pytest -q` (expect ~45+ tests green), `python scripts/mutate_merge.py` (all killed), `conduct demo` manual look.
- [ ] **Step 2: Re-read spec §5/§5.1 against `merge.py`** one final time — every table row must have a test naming it; list any intentional deviations in the PR body (there should be none beyond the three [plan decisions] at the top).
- [ ] **Step 3: Open the PR** `feature/m1-m4 → main` titled `M1–M4: protocol core, CLI, live panel, demo` with the gate results in the body. Merge is the owner's call.

---

## Execution notes

- Fresh subagent per task (@superpowers:subagent-driven-development); every task is self-contained given this file + the spec.
- Never commit red; never skip the RED step — a test that passes on first run is a broken test (@superpowers:test-driven-development).
- If any spec ambiguity surfaces that this plan doesn't resolve, STOP and surface it — don't improvise protocol semantics (they're normative).
