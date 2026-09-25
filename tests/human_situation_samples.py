"""Explicit supplied read instant and exact empty wire expectation for S2 tests."""
READ_AT = "2026-09-21T15:00:00.123Z"


def empty_situation(at=READ_AT):
    """A literal expectation, independent of the production projection."""
    return {"state": "not_required", "computed_at": at, "gates": [],
        "checked": [{"reason": reason, "count": 0, "sources": []} for reason in (
            "gate_decision", "confirmation", "input_document", "reconcile",
            "attempt_bound", "run_ended")], "unknown_because": [],
        "unknown_sources": [{"reason": reason, "count": 0, "sources": []} for reason in (
            "contradictory_gate_receipts", "replay_warnings", "unobserved_request")]}
