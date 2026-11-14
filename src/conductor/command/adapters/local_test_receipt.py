"""A closed, bounded local-test transcript; execution facts never become a model verdict."""
from __future__ import annotations

import base64
from collections.abc import Mapping
import hashlib
import re

from .local_test_plan import canonical, digest, read_plan

OUTPUT_LIMIT = 64 * 1024
_KEYS = {"version", "binding", "policy", "argv", "cwd", "status", "process_status",
         "exit_code", "output", "output_b64", "output_sha256", "output_stream", "counts",
         "truncated", "reason"}
_BINDING = {"run", "action", "attempt", "instance", "grant", "grant_digest", "policy",
            "toolpin", "workspace_tree", "work_modes"}
_DIGESTS = {"grant_digest", "policy", "toolpin", "workspace_tree", "work_modes"}
_HEX = re.compile(r"sha256:[0-9a-f]{64}\Z")
STATUSES = {"passed", "failed", "zero_tests", "timed_out", "truncated",
            "infrastructure_error"}
_REASONS = {None, "test_failures", "no_tests", "all_tests_skipped", "timeout",
            "output_truncated", "result_protocol_invalid", "test_spawn_refused",
            "tree_changed", "runtime_changed", "protected_output", "boundary_refused",
            "test_already_started", "deadline_expired", "process_stopped"}


def _bad():
    return ValueError("local test report invalid")


def _plain(value):
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise _bad()
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if value is None or type(value) in (str, int, bool):
        return value
    raise _bad()


def counts_for(value):
    if (type(value) is not dict or set(value) != {"total", "failures", "errors", "skipped"}
            or any(type(v) is not int or not 0 <= v <= 1_000_000 for v in value.values())
            or value["skipped"] > value["total"]):
        raise _bad()
    return dict(value)


def settled_report(value):
    """Validate frozen or ordinary mappings and return detached canonical JSON data."""
    report = _plain(value)
    if (type(report) is not dict or set(report) != _KEYS
            or type(report["version"]) is not int or report["version"] != 1):
        raise _bad()
    binding = report["binding"]
    if type(binding) is not dict or set(binding) != _BINDING:
        raise _bad()
    for key, item in binding.items():
        if (type(item) is not str or not item or len(item) > 320 or "\0" in item
                or key in _DIGESTS and _HEX.fullmatch(item) is None):
            raise _bad()
    plan = read_plan(report["policy"])
    if binding["policy"] != plan.digest or binding["toolpin"] != plan.toolchain_digest:
        raise _bad()
    argv = report["argv"]
    if (type(argv) is not list or not 1 <= len(argv) <= 16
            or any(type(arg) is not str or not arg or "\0" in arg
                   or len(arg) > 4096 for arg in argv)
            or type(report["cwd"]) is not str or not report["cwd"]
            or len(report["cwd"]) > 1024 or "\0" in report["cwd"]
            or type(report["status"]) is not str or report["status"] not in STATUSES
            or type(report["process_status"]) is not str
            or report["process_status"] not in {"completed", "timed_out", "stopped", "not_started"}
            or report["exit_code"] is not None and type(report["exit_code"]) is not int
            or type(report["truncated"]) is not bool
            or report["reason"] is not None and type(report["reason"]) is not str
            or report["reason"] not in _REASONS
            or report["output_stream"] != "merged" or type(report["output"]) is not str
            or type(report["output_b64"]) is not str
            or len(report["output_b64"]) > 4 * ((OUTPUT_LIMIT + 2) // 3)):
        raise _bad()
    try:
        raw = base64.b64decode(report["output_b64"], validate=True)
    except (ValueError, TypeError):
        raise _bad() from None
    if (len(raw) > OUTPUT_LIMIT or raw.decode("utf-8", "replace") != report["output"]
            or report["output_sha256"] != "sha256:" + hashlib.sha256(raw).hexdigest()):
        raise _bad()
    counts = report["counts"]
    if counts is not None:
        counts_for(counts)
    state = report["status"]
    if state in {"passed", "failed", "zero_tests"}:
        if (report["process_status"] != "completed" or report["truncated"] or counts is None
                or report["exit_code"] not in (0, 1)):
            raise _bad()
        failures = counts["failures"] + counts["errors"]
        if state == "passed" and (report["exit_code"] != 0 or failures
                                  or counts["total"] <= counts["skipped"]):
            raise _bad()
        if state == "failed" and (report["exit_code"] != 1 or not failures):
            raise _bad()
        if state == "zero_tests" and (failures or counts["total"] != counts["skipped"]):
            raise _bad()
    if state == "timed_out" and (report["process_status"] != "timed_out"
                                 or report["exit_code"] is not None):
        raise _bad()
    if state == "truncated" and not report["truncated"]:
        raise _bad()
    if len(canonical(report)) > 512 * 1024:
        raise _bad()
    return report


def report_digest(value):
    return digest(settled_report(value))


def valid_report(request, report, policy=None, tree=None, modes=None):
    """Check the report against independently held request, policy and tree facts."""
    value = settled_report(report)
    binding = value["binding"]
    expected = {"run": request.run_id, "action": request.action_id,
                "attempt": request.attempt_id, "instance": request.instance_id,
                "grant": request.run_authorization_id,
                "grant_digest": request.run_authorization_digest}
    if any(binding[key] != item for key, item in expected.items()):
        raise _bad()
    if policy is not None and binding["policy"] != policy.digest:
        raise _bad()
    if tree is not None and binding["workspace_tree"] != digest(dict(tree)):
        raise _bad()
    if modes is not None and binding["work_modes"] != digest(dict(modes)):
        raise _bad()
    return value
