"""Explicit ownership maintenance and short-lived CLI writer contexts."""
from __future__ import annotations

import json
from pathlib import Path
import sys


def dispatch(args):
    writes = args.command in {"preview", "integration-smoke", "providers"}
    if args.command == "providers" and getattr(args, "profile", False):
        writes = False
    writes = writes or (args.command == "reconcile" and args.run is not None and args.action is not None)
    if not writes:
        return args.func(args)
    from .ownership import acquire_owner, OwnerRefused
    from .ownership_records import state
    try:
        root, head = state(args.dir)
        if head is None or head["phase"] == "rolled_back":
            return args.func(args)
        with acquire_owner(root):
            return args.func(args)
    except OwnerRefused as error:
        print(str(error), file=sys.stderr)
        return 1


def _prepared_message(repeat, command):
    again = "already prepared; " if repeat else "restart prepared; "
    return (f"ownership is NOT released: {again}nothing was recovered. Restart the OS now (a full "
            f"Restart, not a shutdown), then run: {command}")


def _prepare(args):
    """`--prepare-restart`: the result to print and the message to say, on stderr."""
    if args.operation == "recover-login":
        from .ownership_login import prepare_login_recovery
        result = prepare_login_recovery(args.auth_home)
        command = f"conduct ownership recover-login --auth-home {args.auth_home}"
    else:
        from .ownership_transition import prepare_recovery
        record, created = prepare_recovery(args.dir)
        result = {"state": "recovery_prepared", "released": False, "created": created,
                  "generation": record["generation"], "prepared_boot": record["prepared_boot"],
                  "project_root": str(Path(args.dir).resolve())}
        command = f"conduct ownership recover --dir {args.dir}"
    print(_prepared_message(not result["created"], command), file=sys.stderr)
    return result


_RECOVERIES = frozenset({"recover", "recover-login", "recover-clones", "recover-containers"})


def _journals(args):
    """The two journal recoveries; each prints its own result and returns its exit code."""
    from . import ownership_journals_cli as journals
    if args.operation == "recover-clones":
        return journals.recover_clones(args.prepare_restart)
    return journals.recover_containers(args.dir, args.prepare_restart)


def ownership_command(args):
    from .ownership_records import OwnerRefused, state
    from .ownership_transition import activate, recover, rollback
    try:
        if args.operation != "recover-login" and args.auth_home is not None:
            raise OwnerRefused("login_context_required", "--auth-home is only for recover-login")
        if args.prepare_restart and args.operation not in _RECOVERIES:
            raise OwnerRefused("recovery_refused", "--prepare-restart is only for recover, "
                               "recover-login, recover-clones and recover-containers")
        if args.operation == "recover-login" and args.auth_home is None:
            raise OwnerRefused("login_context_required", "recover-login requires --auth-home")
        if args.operation in {"recover-clones", "recover-containers"}:
            return _journals(args)
        if args.prepare_restart:
            result = _prepare(args)
        elif args.operation == "recover-login":
            from .ownership_login import recover_login
            result = recover_login(args.auth_home)
        elif args.operation == "status":
            root, head = state(args.dir)
            result = {"state": "legacy" if head is None else head["phase"],
                      "project_root": str(root)}
        elif args.operation == "activate":
            result = activate(args.dir, legacy_writers_stopped=args.legacy_writers_stopped)
        elif args.operation == "rollback":
            result = rollback(args.dir, legacy_writers_stopped=args.legacy_writers_stopped)
        else:
            result = recover(args.dir)
    except OwnerRefused as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0
