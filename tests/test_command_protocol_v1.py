"""Protocol v1 output is byte-for-byte what it was before December Command v2.

CMD-4 is an additive sidecar: it adds contracts, a store extension, and an
observe/propose service, and it touches neither the merge engine nor the report
renderer. This guard imports the whole v2 command surface first, then merges and
renders a fixed v1 document and pins the exact bytes by digest. The pinned digest
is an independently recorded fact; the rendered bytes come from production. If a
v2 change ever reaches into the v1 merger or renderer, this reddens.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

# Importing the v2 surface must not perturb a single v1 byte; load it up front.
from conductor.command import contracts as _contracts  # noqa: F401
from conductor.command import run_store as _run_store  # noqa: F401
from conductor.command import service as _service  # noqa: F401
from conductor.command.adapters import base as _adapter_base  # noqa: F401

from conductor import merge, report


NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)

# The one fixture, spelled out here so the guard does not drift with a shared
# test helper: a map with two roles and a lane whose finding a reviewer confirms.
MAP_DATA = {
    "schema_version": 1,
    "project": "orbit",
    "nodes": [{"id": "n", "label": "n", "kind": "artifact"}],
    "cycle": {
        "phases": ["implement"],
        "roles": [
            {"id": "impl", "harness": "cc", "reviews": []},
            {"id": "rev", "harness": "cc", "reviews": ["impl"], "stage": "implement"},
        ],
    },
}
LANES = [
    {"author": "claude", "data": {
        "schema_version": 1, "author": "claude", "role": "impl",
        "updated": "2026-07-30T11:00:00+00:00",
        "findings": [{"id": "D-1", "title": "t", "severity": "blocker",
                      "claim": "defect", "detail": "d", "evidence": "e",
                      "refs": ["n"]}],
        "verdicts": {}, "waits_on_human": []}, "error": None},
    {"author": "codex", "data": {
        "schema_version": 1, "author": "codex", "role": "rev",
        "updated": "2026-07-30T11:00:00+00:00", "findings": [],
        "verdicts": {"D-1": {"disposition": "confirmed", "note": "n"}},
        "waits_on_human": []}, "error": None},
]

# The bytes v1 produced before CMD-4 existed, recorded once from the base tree.
V1_RENDER_SHA256 = "c751020d2ea9491b86f3c5a9141f865748584ba04644032663b367afc03ceb67"


def test_the_v1_merger_and_renderer_still_produce_the_recorded_bytes():
    state = merge.merge(MAP_DATA, None, LANES, [], 0, NOW)
    rendered = report.render(state).encode("utf-8")
    assert hashlib.sha256(rendered).hexdigest() == V1_RENDER_SHA256
