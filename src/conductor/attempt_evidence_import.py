"""Import a sealed action's Git before-images and optional external test counters.

Run with the installed product's Python. The target is a separate project/archive already
containing the run, seed, manifest and changed blobs. Stop its active server before import.
The Git source is read-only. No provider, login, test program or model is started.
"""
import argparse
from contextlib import nullcontext
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from conductor import ownership, server_git
from conductor.command import attempt_detail
from conductor.command.accept_snapshot import _folder, _put, _read
from conductor.command.api_refusals import ApiRefusal
from conductor.command.attempt_base import MAX_TREE, _object_id, import_attempt_base
from conductor.command.attempt_test_evidence import _LIMIT, _path, _unique, import_test_evidence
from conductor.command.checked_changes import MAX_SHOWN
from conductor.command.contracts import ActionRequest
from conductor.command.git_setup_facts import REAL_OBJECTS
from conductor.command.project_git import GitReadFailed
from conductor.command.project_git_state import _checked
from conductor.command.run_store import RunStore
from conductor.command.seed_record import read_seed
from conductor.command.store_errors import StoreError
from conductor.command.task_contracts import frozen_config_task


def options(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("source", "target"):
        parser.add_argument("--" + arg, required=True, type=Path)
    for arg in ("run", "node", "action"):
        parser.add_argument("--" + arg, required=True)
    parser.add_argument("--pin-home", type=Path, help="Conduct home with the owner's Git pin")
    parser.add_argument("--report", type=Path, help="external JSON test report for this action")
    return parser.parse_args(argv)


def _selection(target, opts):
    recovered = RunStore(target).read(opts.run)
    try:
        shown = attempt_detail.read_attempt(target, recovered, opts.node, opts.action)
    except ApiRefusal:
        raise ValueError("the run contains no such action on that node") from None
    if (shown["outcome"] != "succeeded" or not shown["verdict"]
            or shown["verdict"]["status"] != "verified" or shown["files_total"] is None):
        raise ValueError("the selected action has no matching verified patch snapshot")
    request, = [r.value for r in recovered.records if isinstance(r.value, ActionRequest)
                and (r.value.node_id, r.value.action_id) == (opts.node, opts.action)]
    seed = read_seed(target, frozen_config_task(recovered.config).task_id)
    digest = shown["manifest_digest"]
    return recovered, request, seed, attempt_detail._snapshot(target, request, seed, digest)


def _git(scratch, pin_home):
    # Each child gets a new empty home without proxy or credential environment from the operator.
    source_env = {k: v for k, v in os.environ.items()
                  if k.upper() in {"SYSTEMROOT", "WINDIR", "TMP", "TEMP", "TMPDIR", "LANG"}}
    source_env.update(dict.fromkeys(("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA"),
                                    str(scratch)))
    pinned = server_git.project_git_reader(scratch, source=source_env, folder=pin_home)

    def read(args, *a, **kw):
        answer = pinned(["--no-lazy-fetch", "-c", "protocol.allow=never", *args], *a, **kw)
        if args[-2] == "blob" and answer.exit_code == 0:
            if not attempt_detail.displayable_source("blob", answer.output):
                raise ValueError("the frozen before-image cannot be safely displayed")
        return answer

    return read


def _base(source, scratch, request, seed, snap, pin_home):
    if seed.source == "empty":
        return
    if not (source / ".git").exists():
        raise ValueError("the source must be a local Git working repository")
    git = _git(scratch, pin_home)
    args = ["--no-optional-locks", "-C", str(source), "--git-dir=.git", *REAL_OBJECTS,
            "cat-file", "commit", seed.base_commit]
    answer = git(args, True, output_limit=MAX_TREE + 1)
    raw = _checked(answer)
    if (answer.truncated or len(raw) > MAX_TREE
            or _object_id("commit", raw, seed.object_format) != seed.base_commit
            or raw.split(b"\n", 1)[0] != ("tree " + seed.base_tree).encode("ascii")):
        raise ValueError("Git commit does not prove the recorded seed tree")
    rows = [row for row in snap.rows[:MAX_SHOWN] if not attempt_detail._private_path(row.path)
            and row.length <= attempt_detail._FILE_BYTES]
    import_attempt_base(scratch, request.run_id, seed, rows, git, source_root=source)


def _report(path, scratch, request, seed, snap):
    path = path.absolute()
    # Include every parent in the no-portal read. Only explicitly named JSON is admitted.
    if path.suffix.lower() != ".json":
        raise ValueError("the external report must be a local JSON file")
    raw = _read(Path(path.anchor), path, _LIMIT)
    report = json.loads(raw, object_pairs_hook=_unique)
    import_test_evidence(scratch, request, snap.digest, seed, snap, report)
    return _path(scratch, request)


def run(opts):
    source = opts.source.resolve(strict=True)
    target = opts.target.resolve(strict=True)
    if (source == target or source in target.parents or target in source.parents
            or not source.is_dir() or not target.is_dir()):
        raise ValueError("separate existing source and target project directories are required")
    guard = ownership.acquire_owner(target) if ownership.is_activated(target) else nullcontext()
    with guard, ownership.write_guard(target):
        recovered, request, seed, snap = _selection(target, opts)
        with TemporaryDirectory(prefix=".evidence-", dir=target) as folder:
            scratch = Path(folder)
            receipt = _report(opts.report, scratch, request, seed, snap) if opts.report else None
            _base(source, scratch, request, seed, snap, opts.pin_home)
            source_base = _folder(scratch, opts.run) / "base"
            dest = _folder(target, opts.run)
            records = []
            if source_base.exists():
                records.extend((dest / "base" / p.name, _read(scratch, p, MAX_TREE))
                               for p in sorted(source_base.iterdir()))
            if receipt:
                records.append((_path(target, request), _read(scratch, receipt, _LIMIT)))
            # Existing evidence must agree before any new file appears; a retry only appends
            # missing immutable objects. The checker and execution journal are never modified.
            for path, payload in records:
                if os.path.lexists(path) and _read(target, path, len(payload)) != payload:
                    raise ValueError("existing evidence conflicts with the requested import")
            for path, payload in records:
                _put(target, path, payload)
        return attempt_detail.read_attempt(target, recovered, opts.node, opts.action)


def main(argv=None):
    try:
        result = run(options(argv))
    except (ValueError, OSError, StoreError, ownership.OwnerRefused, GitReadFailed) as error:
        print("Evidence import refused:", str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
