"""External test outcomes associated with one sealed action."""

import ast
import json
from pathlib import Path, PurePosixPath

from ..ownership import write_guard
from .accept_manifest import SnapshotRefused
from .accept_snapshot import _folder, _hold, _put, _read
from .contract_values import _id
from .path_admission import admit_name
from .run_store import _root_gate

_LIMIT = 64 * 1024
_COUNT_KEYS = ("total", "errors", "failures", "skipped")


def _bad():
    return SnapshotRefused("test_report_invalid")


def _summary(values):
    if (type(values) is not list or len(values) != 4
            or any(type(v) is not int or not 0 <= v <= 1_000_000 for v in values)
            or values[3] > values[0]):
        raise _bad()
    # unittest can count multiple subtest failures per method.
    return dict(zip(_COUNT_KEYS, values))


def _path(root, request):
    action = _id("action_id", request.action_id)
    admit_name(action, "action_id")
    return _folder(root, request.run_id) / "tests" / (action + ".json")


def _binding(request, digest, seed, snapshot):
    if snapshot.digest != digest:
        raise _bad()
    return {"run": request.run_id, "action": request.action_id, "attempt": request.attempt_id,
            "manifest": digest, "base": seed.base_commit}


def _cases(snapshot):
    """Read source locations, never import test modules or claim they executed."""
    from .attempt_detail import displayable_source

    found = []
    total = 0
    for row in snapshot.rows[:32]:
        path = PurePosixPath(row.path)
        if (row.state == "deleted" or row.length > _LIMIT or total + row.length > 4 * _LIMIT
                or not (path.name.startswith("test_") or path.stem.endswith("_test"))
                or path.suffix != ".py"):
            continue
        total += row.length
        raw = snapshot.blobs[row.sha256]
        if not displayable_source(row.path, raw):
            continue
        try:
            text = raw.decode("utf-8")
            tree = ast.parse(text)
        except (UnicodeError, SyntaxError, ValueError, RecursionError):
            continue
        lines = text.splitlines()
        definitions = list(tree.body)
        for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            definitions.extend(cls.body)
        for method in definitions:
            if (not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
                    or not method.name.startswith("test_") or len(method.name) > 160):
                continue
            checks = [n for n in ast.walk(method) if isinstance(n, ast.Assert)
                      or isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                      and n.func.attr.startswith("assert")]
            line = min((n.lineno for n in checks), default=method.lineno)
            found.append({"path": row.path, "name": method.name, "line": line,
                          "assertion": lines[line - 1].strip()[:320] if checks else None})
            if len(found) == 40:
                return found
    return found


def read_test_evidence(root, request, manifest_digest, seed, snapshot, *, protocol=None):
    root = Path(root).resolve()
    result = {"status": "not_recorded", "summary": None, "cases": [], "source": None}
    try:
        binding = _binding(request, manifest_digest, seed, snapshot)
        result["cases"] = _cases(snapshot)
        if protocol is not None:
            from .adapters.local_test_receipt import valid_report
            report = valid_report(request, protocol)
            return {**result, "status": "recorded", "source": "native",
                    "summary": report["counts"], "protocol": report}
        path = _path(root, request)
        _hold(root, path)
        value = json.loads(_read(root, path, _LIMIT), object_pairs_hook=_unique)
        if (type(value) is not dict or set(value) != {"binding", "tests", "version"}
                or type(value["version"]) is not int or value["version"] != 1
                or value["binding"] != binding):
            raise _bad()
        return {**result, "status": "recorded", "summary": _summary(value["tests"]),
                "source": "external"}
    except FileNotFoundError:
        return result
    except (OSError, ValueError, RecursionError):
        return {**result, "status": "unavailable"}


def _unique(pairs):
    value = dict(pairs)
    if len(value) != len(pairs):
        raise _bad()
    return value


def import_test_evidence(root, request, manifest_digest, seed, snapshot, report):
    """Copy only counters from an operator-supplied report; compare its artifact hashes."""
    root = Path(root).resolve()
    binding = _binding(request, manifest_digest, seed, snapshot)
    if (type(report) is not dict or report.get("run") != request.run_id
            or report.get("action") != "verification/" + request.action_id
            or report.get("manifest") != manifest_digest
            or report.get("source_commit") != seed.base_commit
            or type(report.get("files")) is not dict):
        raise _bad()
    if any(k in report and report[k] != request.attempt_id for k in ("attempt", "attempt_id")):
        raise _bad()
    _summary(report.get("tests"))
    for row in snapshot.rows:
        value = report["files"].get(row.path)
        if row.state == "deleted":
            if row.path in report["files"]:
                raise _bad()
        elif value != row.sha256.removeprefix("sha256:"):
            raise _bad()
    value = {"version": 1, "binding": binding, "tests": report["tests"]}
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")
    with write_guard(root), _root_gate(root).lock:
        _put(root, _path(root, request), payload)
