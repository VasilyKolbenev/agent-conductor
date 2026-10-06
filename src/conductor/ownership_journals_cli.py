"""`conduct ownership recover-clones` and `recover-containers`: the road for two journals.

The hub's clone attempts and a project's container attempt loans hold one boot text per record. A
record from before the boot counter, or one that met another boot environment, needs an explicit
preparation before a restart can clean it up. Here a person asks for it, with the flag the project
and the login already have (`--prepare-restart`); a plain run is the recovery itself and writes no
preparation. Neither runs while its owner lives: a running hub holds the clone attempts, and the
container journal is opened only under the project's owner.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

_CLONES = "conduct ownership recover-clones"
_CONTAINERS = "conduct ownership recover-containers"


def _print(result: dict, code: int) -> int:
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return code


def _refused(code: str, detail: str) -> int:
    print(f"{code}: {detail}", file=sys.stderr)
    return 1


def _prepared(rows: list[dict], identifier: str, command: str) -> int:
    """Print what a preparation did, one row per record, and say that nothing was cleaned up."""
    done = [row for row in rows if row["state"] == "recovery_prepared"]
    failed = [row for row in rows if row["state"] == "not_prepared"]
    if not rows:
        return _print({"state": "nothing_to_prepare", "released": False, "records": []}, 0)
    for row in failed:
        print(f"{row[identifier]}: {row['action']}", file=sys.stderr)
    if done:
        fresh = any(row["created"] for row in done)
        again = "restart prepared; " if fresh else "already prepared; "
        print(f"NOT cleaned up: {again}nothing was recovered. Restart the OS now (a full Restart, "
              f"not a shutdown), then run: {command}", file=sys.stderr)
    state = "recovery_prepared" if done else "not_prepared"
    return _print({"state": state, "released": False, "records": rows}, 1 if failed else 0)


def recover_clones(prepare: bool) -> int:
    """The clone attempts of the hub's folder: clean up what a restart is proven for, or prepare.

    Returns:
        0 when nothing is left unfinished (or every record was prepared), else 1.
    """
    from .hub import clone, home, instance
    try:
        folder = home.conduct_home_path()
    except home.ConductHomeInvalid as error:
        return _refused("recovery_refused", str(error))
    if not (folder / "clone-attempts").exists():
        return _print({"state": "recovered", "unfinished": []}, 0)
    try:
        live = instance.HubInstance.acquire(folder)
    except instance.HubAlreadyRunning:
        return _refused("recovery_refused", "a hub is running and owns its clone attempts; "
                                            "stop it, then run this again")
    try:
        cloner = clone.Clones(folder)
        if prepare:
            return _prepared(cloner.prepare_restarts(), "operation_id", _CLONES)
        unresolved = cloner.recover()
    except clone.CloneFailed as error:
        return _refused("recovery_refused", " ".join(error.stderr) or (
            "a record of the clone journal cannot be read; nothing was changed"))
    finally:
        live.close()
    entries = [{"operation_id": ident, "action": cloner.unfinished[ident]} for ident in unresolved]
    for entry in entries:
        print(f"{entry['operation_id']}: {entry['action']}", file=sys.stderr)
    return _print({"state": "unfinished" if entries else "recovered", "unfinished": entries},
                  1 if entries else 0)


def recover_containers(directory: str, prepare: bool) -> int:
    """The container attempt loans of one activated project, under its owner.

    Returns:
        0 when the recovery ran or every record was prepared, else 1.
    """
    from .command.adapters.process_profile import ProfileJournal, ProfileRefused
    from .ownership import acquire_owner
    from .ownership_records import OwnerRefused
    try:
        from .command.adapters import _winlaunch
    except ImportError:
        return _refused("recovery_refused", "container attempt journals exist only on Windows")
    root = Path(directory).resolve()
    try:
        with acquire_owner(root):
            journal = ProfileJournal.for_project(root, _winlaunch)
            rows = journal.prepare_restarts() if prepare else journal.recover()
    except (OwnerRefused, ProfileRefused) as error:
        print(str(error), file=sys.stderr)
        return 1
    if prepare:
        return _prepared(rows, "attempt", f"{_CONTAINERS} --dir {root}")
    return _print({"state": "recovered", "project_root": str(root)}, 0)
