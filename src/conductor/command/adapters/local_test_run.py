"""Run one owner-declared test policy through the existing offline owned-process runner."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from time import monotonic

from ..containment import first_directory_violation
from .codex_patch import PatchRefused, remaining
from .harness_attempt import AttemptFolders, LAUNCH_REFUSALS, RUNTIME_ENV
from .headless_values import attempt_relation
from .independent_check import CheckFrameError, scan_material
from .local_test_plan import digest, vet_runtime
from .local_test_receipt import OUTPUT_LIMIT, counts_for, settled_report
from .process import CommandSpec

RESULT_MARKER = b"\nconduct.test-result.v1 "
BOOTSTRAP = '''import json, pathlib, sys, unittest
sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
install, work = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
if not pathlib.Path(unittest.__file__).resolve().is_relative_to(install.resolve()):
    raise RuntimeError("unittest is outside the pinned runtime")
sys.path.insert(0, str(work))
suite = unittest.defaultTestLoader.discover(str(work / sys.argv[3]), pattern=sys.argv[4])
result = unittest.TextTestRunner(verbosity=2).run(suite)
counts = dict(total=result.testsRun, failures=len(result.failures),
              errors=len(result.errors), skipped=len(result.skipped))
sys.stdout.flush()
print("\\nconduct.test-result.v1 " + json.dumps(counts, sort_keys=True), flush=True)
sys.exit(0 if result.wasSuccessful() else 1)
'''


def _binding(transport, request, args, expected, plan):
    modes = transport._workspace.work_modes(args.work_item_id, work_scope=args.task_scope)
    return {"run": request.run_id, "action": request.action_id,
            "attempt": request.attempt_id, "instance": request.instance_id,
            "grant": request.run_authorization_id,
            "grant_digest": request.run_authorization_digest, "policy": plan.digest,
            "toolpin": plan.toolchain_digest, "workspace_tree": digest(dict(expected)),
            "work_modes": digest(dict(modes))}, modes


def _base(binding, plan, cwd):
    empty = b""
    return {"version": 1, "binding": binding, "policy": plan.as_dict(),
            "argv": [str(Path(plan.install) / plan.entry), "-I", "-S", "-B"],
            "cwd": cwd, "status": "infrastructure_error", "process_status": "not_started",
            "exit_code": None, "output": "", "output_b64": "",
            "output_sha256": "sha256:" + hashlib.sha256(empty).hexdigest(),
            "output_stream": "merged", "counts": None, "truncated": False,
            "reason": "test_spawn_refused"}


def _classify(report, outcome):
    raw = outcome.output
    report.update(process_status=outcome.status, exit_code=outcome.exit_code,
                  truncated=outcome.output_truncated)
    if (type(raw) is not bytes or len(raw) > OUTPUT_LIMIT
            or outcome.output_contains_env_value):
        report["reason"] = "protected_output"
        return
    report.update(output=raw.decode("utf-8", "replace"),
                  output_b64=base64.b64encode(raw).decode("ascii"),
                  output_sha256="sha256:" + hashlib.sha256(raw).hexdigest())
    if outcome.output_truncated:
        report.update(status="truncated", reason="output_truncated")
        return
    if outcome.status == "timed_out":
        report.update(status="timed_out", reason="timeout")
        return
    if outcome.status != "completed":
        report["reason"] = "process_stopped"
        return
    try:
        _body, marker, encoded = raw.rpartition(RESULT_MARKER)
        if not marker or raw.count(RESULT_MARKER) != 1:
            raise ValueError
        def unique(pairs):
            value = dict(pairs)
            if len(value) != len(pairs):
                raise ValueError
            return value
        counts = counts_for(json.loads(encoded, object_pairs_hook=unique))
    except (ValueError, TypeError, RecursionError):
        report["reason"] = "result_protocol_invalid"
        return
    report["counts"] = counts
    failures = counts["errors"] + counts["failures"]
    if outcome.exit_code != (1 if failures else 0):
        report["reason"] = "result_protocol_invalid"
    elif failures:
        report.update(status="failed", reason="test_failures")
    elif counts["total"] == counts["skipped"]:
        report.update(status="zero_tests", reason=("no_tests" if not counts["total"]
                                                  else "all_tests_skipped"))
    else:
        report.update(status="passed", reason=None)


def run_local_tests(transport, request, args, work, expected, plan, deadline):
    """A durable started claim precedes the container; a completion precedes the checker."""
    cwd = work.relative_to(transport._workspace.root).as_posix()
    binding, modes = _binding(transport, request, args, expected, plan)
    report = _base(binding, plan, cwd)
    if not transport._confine or not transport.boundary_provided("review"):
        raise PatchRefused("local tests require the execution boundary")
    if transport._workspace.digest_work_tree() != dict(expected):
        raise PatchRefused("task tree changed before tests")
    vet_runtime(plan, deadline=deadline)
    install = Path(plan.install)
    root = transport._workspace.root
    parts = plan.start.split("/")
    directories = [work, *[work.joinpath(*parts[:n]) for n in range(1, len(parts) + 1)]]
    if (install == root or install in root.parents or root in install.parents
            or first_directory_violation(directories)
            or not (work / plan.start).is_dir()):
        raise PatchRefused("local test folders are not admissible")
    remaining(deadline)
    if not transport._handoff.claim_test_run(request, binding):
        raise PatchRefused("local tests were already started; do not replay")
    folders = AttemptFolders(work=cwd, home=None, install=plan.install)
    try:
        with transport._runner.container_profile(
                mode="review", folders=folders, internet_client=False) as (boundary, paths):
            scratch = Path(paths["runtime"])
            script = scratch / "conduct-unittest-v1.py"
            script.write_text(BOOTSTRAP, encoding="utf-8", newline="\n")
            argv = (str(install / plan.entry), "-I", "-S", "-B", str(script),
                    plan.install, str(work), plan.start, plan.pattern)
            report["argv"] = list(argv)
            vet_runtime(plan, deadline=deadline)
            if (transport._workspace.digest_work_tree() != dict(expected)
                    or transport._workspace.work_modes(args.work_item_id,
                                                       work_scope=args.task_scope) != modes):
                raise PatchRefused("task tree changed before tests")
            outcome = transport._runner.run(CommandSpec(
                argv=argv, cwd=cwd, boundary=boundary, env_allow=(),
                env=dict.fromkeys(RUNTIME_ENV, str(scratch)), separate_stderr=False,
                output_limit=OUTPUT_LIMIT,
                timeout_seconds=min(plan.timeout_seconds, remaining(deadline)),
                sensitive_extra=tuple(transport._sensitive_values(attempt_relation(request)))))
            sensitive = (*transport._sensitive_values(attempt_relation(request)),
                         *transport._login_seen)
            try:
                scan_material(outcome.output, sensitive)
            except CheckFrameError:
                report.update(process_status=outcome.status, exit_code=outcome.exit_code,
                              truncated=outcome.output_truncated, reason="protected_output")
            else:
                _classify(report, outcome)
        if (transport._workspace.digest_work_tree() != dict(expected)
                or transport._workspace.work_modes(args.work_item_id,
                                                   work_scope=args.task_scope) != modes):
            report.update(status="infrastructure_error", reason="tree_changed")
        try:
            vet_runtime(plan, deadline=deadline)
        except (ValueError, OSError):
            report.update(status="infrastructure_error", reason="runtime_changed")
        if monotonic() >= deadline:
            report.update(status="infrastructure_error", reason="deadline_expired")
        try:
            scan_material(report, sensitive)
        except CheckFrameError:
            report.update(status="infrastructure_error", reason="protected_output", output="",
                          output_b64="",
                          output_sha256="sha256:" + hashlib.sha256(b"").hexdigest())
    except LAUNCH_REFUSALS + (ValueError, CheckFrameError):
        # Keep a fixed reason, never an exception string or raw command/credential detail.
        report.update(status="infrastructure_error", reason="boundary_refused")
        if report["output"]:
            report.update(output="", output_b64="",
                          output_sha256="sha256:" + hashlib.sha256(b"").hexdigest())
    report = settled_report(report)
    transport._handoff.record_test_run(request, report)
    return report
