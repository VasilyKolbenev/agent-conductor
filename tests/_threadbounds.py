"""What a wait in the concurrency suite may cost, and how its threads are run.

Its own module for the reason `tests/_stdinseam.py` is: one closed question with
several exits, shared by a suite that would otherwise cross the line cap holding
it. Nothing here knows about runs, stores or adapters. It knows how long
something may block, who is allowed to outlive a test, and how a reader checks
both -- including in this file, which is judged by the same guards it supplies.

The names are the ones the suite already used, so a call site reads the same and
the syntax guards still recognise a bound by its id.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
import threading
from pathlib import Path

#: A rendezvous that must SUCCEED, and a DEADLOCK bound rather than a speed
#: budget. It has to outlive the slowest thing the OTHER thread can legitimately
#: be doing while this one waits, and for the effect-overlap circuit that thing
#: is a durable write: the effect lease is the one fsync standing between the
#: prepare rendezvous and the execute rendezvous. This used to be one second,
#: which is about one fsync, so a loaded disk answered "the seams did not
#: overlap" to a question nobody had asked about the disk. Nothing should ever
#: reach this bound; reaching it means a seam really is mutually excluded, and
#: the assertion that names the relation is what reports it.
#:
#: Fifteen seconds is twelve times the slowest write the suite deliberately
#: injects and orders of magnitude past any single fsync. It is not tuned and
#: nothing is expected to spend it.
_RENDEZVOUS_BOUND = 15.0

#: A probe window that must EXPIRE, which is the opposite instrument. A durable
#: write pauses here to see whether ANOTHER writer arrives, and nobody arriving
#: is the passing answer. Enlarging it would pause every serialized write for
#: that long; shrinking it only weakens the probe and can never red it, so a
#: slow machine costs coverage here and never a false failure.
_PROBE_WINDOW = 0.1

#: How many rendezvous ONE thread can reach in a single circuit: the
#: effect-overlap adapter waits once inside prepare and once inside execute.
#: This is what the group bound is derived from rather than guessed against,
#: because a mutually excluded runtime reaches every one of them in turn before
#: any assertion in a test body runs. It is DECLARED here and proved against the
#: adapter's own body by a guard, so a seam added there cannot pass unread.
_RENDEZVOUS_PER_THREAD = 2

#: The group must outlive ALL of them. A caller that gave up first would hand a
#: reader a bare TimeoutError instead of the named relation that actually
#: failed -- the watchdog would have become the thing under test, which is the
#: same mistake as the budget it replaced, one layer out. The spare multiple is
#: for the work BETWEEN the rendezvous, which is durable writes.
_RESULT_BOUND = _RENDEZVOUS_BOUND * (_RENDEZVOUS_PER_THREAD + 1)

#: A durable write far slower than the rendezvous the suite used to allow. The
#: old bound was one second and the lease is the one durable write between the
#: two rendezvous, so this is exactly the shape of machine that used to turn a
#: concurrency claim into a disk benchmark.
_A_SLOW_DURABLE_WRITE = 1.2

#: The names above, and the calls they are allowed to bound. `bound` is the ONE
#: forwarder: `_run_together` takes it so a test can prove the lifecycle gives
#: up without spending the real bound. It is admitted by NAME here and pinned by
#: SYMBOL in the guard -- its default must BE `_RESULT_BOUND` -- so a second
#: forwarder cannot slip in by being spelled `bound` and defaulting to a number.
_NAMED_BOUNDS = {"_RENDEZVOUS_BOUND", "_PROBE_WINDOW", "_RESULT_BOUND", "bound"}
#: Every way the suite blocks on another thread. `map` is here because
#: `Executor.map` takes a timeout too, and a lazy iterator nobody bounded is an
#: unbounded wait wearing a comprehension.
_TIMED_CALLS = {"wait", "result", "join", "map"}


# The lifecycle every circuit runs on, and why it is not an executor.
#
# `ThreadPoolExecutor.__exit__` calls `shutdown(wait=True)` with NO bound, and
# `concurrent.futures.thread` registers an interpreter-exit hook that joins
# every worker again. So the timeout a caller passes to `result()` bounds the
# CALLER and never the process, which is the opposite of what a watchdog is for.
# Measured rather than reasoned about: a worker sleeping 1.2 seconds under
# `result(timeout=0.05)` handed back its TimeoutError in 0.06s and the `with`
# block returned in 1.20s. On a real deadlock a remote job would still hang,
# with the bound in the source saying otherwise.
#
# Daemon threads make it a claim about the process. What is NOT claimed: that
# the stuck work stops. Python cannot kill a thread, so the work is ABANDONED
# and a named report is what a reader gets instead of a silent job timeout.


def _run_together(*work, bound=_RESULT_BOUND):
    """Run each callable on its own daemon thread; outcomes in the order given.

    An outcome is ``("value", result)`` or ``("error", exception)``, so a
    circuit expecting one of two to refuse can say WHICH refused rather than
    catching whichever arrived first.
    """
    outcomes: list[tuple[str, object] | None] = [None] * len(work)
    done = threading.Event()
    left = [len(work)]
    guard = threading.Lock()

    def run(index, call):
        try:
            outcomes[index] = ("value", call())
        except BaseException as error:  # noqa: BLE001 -- reported, never swallowed
            outcomes[index] = ("error", error)
        finally:
            with guard:
                left[0] -= 1
                if not left[0]:
                    done.set()

    for index, call in enumerate(work):
        threading.Thread(target=run, args=(index, call), daemon=True).start()
    if not done.wait(timeout=bound):
        unfinished = [index for index, row in enumerate(outcomes) if row is None]
        raise TimeoutError(
            f"WORK_NEVER_FINISHED={unfinished} within {bound}s; the relation "
            "they were to establish never happened")
    return outcomes


def _values(outcomes):
    """Every outcome as a value, refusing to hide a raised exception as one."""
    for kind, value in outcomes:
        if kind == "error":
            raise value
    return [value for _kind, value in outcomes]


def _timeout_of(node):
    """The `timeout=` argument of one call, or None when it carries none."""
    return next((kw.value for kw in node.keywords if kw.arg == "timeout"), None)


def _unnamed_waits(*paths: Path) -> tuple[list[str], set[str]]:
    """Every blocking call in `paths` that spells its bound, or carries none.

    Both are the same failure with different faces. A spelled bound cannot say
    what it is for; an ABSENT one waits forever, so a deadlocked circuit hangs a
    remote job until the runner kills it instead of naming what did not happen.

    Also reports which named bounds are actually IN USE, so a caller can refuse
    to guard an empty set. A bound reaches a wait through a keyword DEFAULT too,
    which is a `timeout=` site one hop away, and those are counted -- otherwise
    the forwarded one would have to be carved out by name.
    """
    offenders: list[str] = []
    used: set[str] = set()
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef):
                for default in node.args.kw_defaults + node.args.defaults:
                    if isinstance(default, ast.Name) and default.id in _NAMED_BOUNDS:
                        used.add(default.id)
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr not in _TIMED_CALLS:
                continue
            where = f"{path.name}:{node.lineno}"
            bound = _timeout_of(node)
            if bound is None:
                offenders.append(f"{node.func.attr} waits unbounded at {where}")
            elif isinstance(bound, ast.Name) and bound.id in _NAMED_BOUNDS:
                used.add(bound.id)
            else:
                offenders.append(f"{node.func.attr} spells its bound at {where}")
    return offenders, used


def _named(node: ast.AST) -> str:
    """The bare name an expression refers to, whether it is `f` or `x.y.f`.

    A review reached past the first version of this guard with two ordinary
    spellings -- `futures.ThreadPoolExecutor(...)` and a bare `Thread(...)` from
    `from threading import Thread` -- because it read only ONE node kind each,
    an attribute for the first and an attribute for the second. A name is a
    name however many dots stand in front of it, and neither kind is optional.
    """
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _import_offence(node: ast.AST) -> str | None:
    """An import that would put an unbounded lifecycle within reach.

    Closed by CONSTRUCTION rather than by listing spellings, which is what the
    first version got wrong. `concurrent.futures` is refused whole: hold the
    module under any alias and every executor in it is one attribute away.
    `Thread` is refused as a NAME, so the only way to build one is
    `threading.Thread(...)`, which the call rule below can always see.
    """
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name == "concurrent.futures" or alias.name.startswith(
                    "concurrent.futures."):
                return "the executor module is imported"
    if isinstance(node, ast.ImportFrom):
        if (node.module or "").startswith("concurrent.futures"):
            return "the executor module is imported from"
        if node.module == "concurrent" and any(
                alias.name == "futures" for alias in node.names):
            return "the executor module is imported from"
        if node.module == "threading" and any(
                alias.name == "Thread" for alias in node.names):
            return "a thread class is imported under a bare name"
    return None


def _unbounded_lifecycles(*paths: Path) -> list[str]:
    """Every thread started in `paths` that could outlive the test that did it.

    `ThreadPoolExecutor` may not be reachable at all: its exit waits without a
    bound, so a bound handed to `result()` is a claim about the caller and not
    about the process. A thread that is not a daemon is the same hazard with no
    wrapper around it, and a subclass of one is that hazard wearing a new name.
    """
    offenders: list[str] = []
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            where = f"{path.name}:{getattr(node, 'lineno', 0)}"
            offence = _import_offence(node)
            if offence is not None:
                offenders.append(f"{offence} at {where}")
            if isinstance(node, ast.ClassDef) and any(
                    _named(base) == "Thread" for base in node.bases):
                offenders.append(f"a thread subclass is declared at {where}")
            if not isinstance(node, ast.Call):
                continue
            if _named(node.func) == "ThreadPoolExecutor":
                offenders.append(f"an executor is built at {where}")
            if _named(node.func) != "Thread":
                continue
            daemon = next(
                (kw.value for kw in node.keywords if kw.arg == "daemon"), None)
            if not (isinstance(daemon, ast.Constant) and daemon.value is True):
                offenders.append(f"a non-daemon thread starts at {where}")
    return offenders


def _rendezvous_call_sites(cls) -> int:
    """How many times an adapter's own body calls `self._wait`, from its source.

    Counted from the CLASS rather than from a roster of method names somebody
    wrote out. A roster can only find the names already in it: the first version
    filtered `vars()` down to `{"prepare", "execute"}` and so could never return
    more than two, whatever the adapter grew. A review proved that by adding a
    third seam and watching the guard stay green.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(cls)))
    return sum(
        1 for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_wait"
        # SELF, which the docstring said and the first version did not check:
        # `other._wait(...)` is a wait this adapter's threads never reach, and
        # counting it would inflate a bound derived from this number.
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self")
