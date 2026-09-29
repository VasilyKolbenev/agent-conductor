"""`conduct up`: settle the flags, start the server, refuse a failed start on one line.

This is what `__main__._serve` used to hold, split out because the start now has
more to say than a bind failure (spec 4.1.4, 4.1.5). The sequence is: flags
(`up_flags`, before any IO), the status record `starting`, the identity check
(the folder's activation nonce must be the one the hub was told, read without
writing), the provider file, `server.build`, then `serving`. Anything that goes
wrong on the way is an `UpRefusal`, printed as `conduct up: refused <code>:
<detail>` with exit 1 and recorded as `refused` in the status file when there is
one. The deferred imports keep `conduct init` off the server's import path.
"""
from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from conductor import store, up_flags, up_status
from conductor.ownership_errors import OwnerRefused


def up(args, serve: Callable[..., int]) -> int:
    """Settle the flags of `conduct up`, then hand the plan to `serve`.

    Args:
        args: The parsed namespace of the `up` subcommand.
        serve: `__main__._serve`, kept a parameter so `up` and `demo` still reach
            one serving function.

    Returns:
        The exit code: 1 for a refused flag, else whatever `serve` returns.
    """
    try:
        plan = up_flags.settle(args)
    except up_flags.UpRefusal as refusal:
        return refuse(refusal, _status_of_refused_flags(args))
    return serve(args.dir, args.port, args.providers, plan=plan)


def serve(root: Path | str, port: int, providers: str | None = None,
          plan: up_flags.UpPlan | None = None) -> int:
    """Start the server for `root`, or refuse; then serve until it is stopped.

    Args:
        root: The project root.
        port: The port asked for on 127.0.0.1.
        providers: The operator provider file, or None for the project's own.
        plan: The settled flags; None is a plain standalone `up` or `demo`.

    Returns:
        0 after a normal stop, 1 for a refused start.
    """
    from conductor import server_drain            # deferred: see `__main__`'s import block
    plan = plan or up_flags.STANDALONE
    status = up_status.NullStatus() if plan.status_file is None else up_status.StatusFile(
        plan.status_file, plan.project_id, plan.mode, port)
    if not plan.hub:
        server_drain.enable_ctrl_c()              # a hub child has no console to clear
    stopper = server_drain.Stopper()
    try:
        srv = _start(root, port, providers, plan, status, stopper)
    except up_flags.UpRefusal as refusal:
        return refuse(refusal, status)
    host, bound = srv.server_address[:2]
    # The URL is the result; how to stop the server is lifecycle chatter. Split
    # so `conduct up | xargs open` gets a URL and not a sentence about it.
    #
    # flush=True is load-bearing, not tidiness. A redirected stdout is
    # block-buffered, and the next statement blocks until the server stops --
    # so without the flush the URL reaches the pipe only once it is useless,
    # and a killed server never emits it at all. stderr needs no flush: it is
    # line-buffered whether or not it is a terminal.
    print(f"http://{host}:{bound}/", flush=True)
    print(f"serving {root} — Ctrl+C to stop", file=sys.stderr)
    return server_drain.serve_until_stopped(srv, status, stopper)


def refuse(refusal: up_flags.UpRefusal, status) -> int:
    """Record the refusal and print it as the one line of a refused start.

    A status file that cannot take the record is named inside the same line, so
    a refused start never grows a second line of stderr.
    """
    detail = refusal.detail
    try:
        status.write("refused", code=refusal.code)
    except OSError as error:
        detail = f"{detail} (the status file could not be written: {error})"
    print(up_flags.refusal_line(refusal.code, detail), file=sys.stderr)
    return 1


def _status_of_refused_flags(args):
    path = up_flags.usable_status_path(args)
    if path is None:
        return up_status.NullStatus()
    given = args.mode
    mode = "active" if given is None else (
        given[0] if len(given) == 1 and given[0] in up_flags.MODES else None)
    return up_status.StatusFile(path, args.project_id, mode, args.port)


def _start(root, port, providers, plan: up_flags.UpPlan, status, stopper):
    """Everything between the settled flags and a bound, owned server."""
    from conductor import server                  # deferred: see `__main__`'s import block
    if plan.mode == "view":                       # day 8 builds it; see the slice plan
        raise up_flags.UpRefusal("start_failed",
                                 "--mode view is not built yet (spec 4.3.1)")
    try:
        status.write("starting")
    except OSError as error:
        raise up_flags.UpRefusal("start_failed",
                                 f"the status file could not be written: {error}") from error
    if plan.stop_on_stdin_eof:                    # EOF while still starting drains the same way
        stopper.watch_stdin(_stdin_descriptor())
    try:
        if plan.project_id is not None:
            _check_identity(root, plan.project_id)
        pinned = _providers(root, providers)
    except (OwnerRefused, store.StoreError) as error:
        raise _refusal_for(error) from error
    try:
        srv = server.build(root, port=port, providers=pinned)
    except server.ServerBindError as error:
        raise _bind_refusal(error, port) from error
    except (OwnerRefused, store.StoreError, OSError) as error:
        raise _refusal_for(error) from error
    try:
        status.write("serving", port=srv.server_address[1])
    except OSError as error:
        srv.server_close()
        raise up_flags.UpRefusal("start_failed",
                                 f"the status file could not be written: {error}") from error
    return srv


def _stdin_descriptor() -> int:
    """The descriptor of stdin, or -1 when there is none: a hub that is gone is end of file."""
    try:
        return sys.stdin.fileno()
    except (OSError, ValueError, AttributeError):
        return -1


def _check_identity(root, project_id: str) -> None:
    """The folder must hold the project the hub was told about (read only, before bind)."""
    from conductor import ownership_records       # deferred: see `__main__`'s import block
    _, head = ownership_records.state(root)
    if head is None or head["phase"] == "rolled_back" or head["nonce"] != project_id:
        raise up_flags.UpRefusal("project_identity_changed",
                                 "the project folder does not hold the project that was "
                                 "asked for; it is not activated or was activated again")


def _providers(root, providers: str | None):
    from conductor.command import operator_config  # deferred: see `__main__`'s import block
    path = (Path(providers) if providers is not None
            else operator_config.provider_config_path(store.conductor_dir(root)))
    try:
        return operator_config.load_provider_configs(path)
    except operator_config.OperatorConfigError as error:
        raise up_flags.UpRefusal("providers_invalid", str(error)) from error


def _refusal_for(error: BaseException) -> up_flags.UpRefusal:
    """Map what a start can meet, other than a failed bind, onto the closed table of 4.1.5."""
    if isinstance(error, OwnerRefused):
        if error.code in up_flags.OWNER_CODES:
            return up_flags.UpRefusal(error.code, error.detail)
        return up_flags.UpRefusal("start_failed", f"{error.code}: {error.detail}")
    if isinstance(error, store.StoreError):
        return up_flags.UpRefusal("store_error", str(error))
    return up_flags.UpRefusal("start_failed", str(error))    # an OSError that is not the bind


def _bind_refusal(error: BaseException, port: int) -> up_flags.UpRefusal:
    """A failed bind. The only port this may name is the one asked for, and no other
    port is known to be free, so the hint keeps the PORT placeholder literal instead
    of volunteering a number."""
    return up_flags.UpRefusal(
        "bind_failed", f"cannot serve on 127.0.0.1:{port}: {error}. "
                       "To try a different port, rerun with --port PORT.")
