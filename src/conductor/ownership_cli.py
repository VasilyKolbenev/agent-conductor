"""Explicit ownership maintenance and short-lived CLI writer contexts."""
from __future__ import annotations

import json
import sys


def dispatch(args):
    writes = args.command in {"preview", "integration-smoke", "providers"}
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


def ownership_command(args):
    from .ownership_records import OwnerRefused, state
    from .ownership_transition import activate, recover, rollback
    try:
        if args.operation != "recover-login" and args.auth_home is not None:
            raise OwnerRefused("login_context_required", "--auth-home is only for recover-login")
        if args.operation == "recover-login":
            from .ownership_login import recover_login
            if args.auth_home is None:
                raise OwnerRefused("login_context_required", "recover-login requires --auth-home")
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
