"""Owned GitHub clone attempts; no caller-supplied absolute path crosses HTTP.

The caller supplies a previously admitted project-target ticket. An intent is
durable before its exclusive mkdir. Ambiguous crash windows preserve the folder.

A record names the boot it was written in. After a crash the folder is removed only for a restart
the boot counter proves (`boot_witness.prove_restart`). A record from before the counter, or one
that met another boot environment, needs an explicit preparation first (`prepare_restart`);
starting the hub or `recover()` never writes one, and an attempt that cannot be proven stays
unfinished with the action named in `unfinished`.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import stat
import subprocess
import threading
import time
from collections import deque
from contextlib import ExitStack
from pathlib import Path

from conductor import (boot_prepared, boot_witness, ownership_boot, ownership_native, tool_env,
                       tool_pins)
from conductor.boot_witness import BootRefused
from conductor.command.adapters import _procgroup
from conductor.hub import clone_cleanup, project_targets, registry
from conductor.hub.refusals import HubRefusal

REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}\Z")
OPERATION = re.compile(r"operation-[0-9a-f]{32}\Z")
RECORD = re.compile(r"operation-[0-9a-f]{32}\.json\Z")
TIMEOUT = 900
OUTPUT_LIMIT = 1024 * 1024
_FINAL = frozenset({"cloned", "cleaned"})
_COMMAND = "ownership recover-clones"


class CloneFailed(Exception):
    def __init__(self, code: str, *, stderr: tuple[str, ...] = ()):
        self.code, self.stderr = code, stderr
        super().__init__(code)


def _boot_now(consequence: str, code: str) -> str:
    """The boot measured now; a boot that cannot be measured proves and prepares nothing."""
    try:
        return ownership_boot.current_boot()
    except (BootRefused, OSError, ValueError) as error:
        raise CloneFailed(code, stderr=(f"the OS boot cannot be measured, so {consequence}: "
                                        f"{error}",)) from error


def _new_boot() -> str:
    """The boot text a NEW record holds: one that can prove a restart, never the old string."""
    text = _boot_now("no clone is started", "clone_failed")
    if boot_witness.parse(text).kind == "legacy":
        raise CloneFailed("clone_failed",
                          stderr=("a boot text that cannot prove a restart is never recorded",))
    return text


def _identity(path: Path) -> tuple[int, int]:
    return tuple(ownership_native.identity(path))


def _expected_held(row: dict) -> dict:
    """The identities a record names, by the keys a preparation holds them under."""
    return {"target": row["target_identity"], "parent": row["parent_identity"]}


def _facts(row: dict) -> dict:
    return boot_prepared.facts("clone-attempt", row["operation_id"], row)


def _plain(path: Path, *, directory: bool) -> None:
    found = os.lstat(path)
    if (stat.S_ISLNK(found.st_mode) or getattr(found, "st_reparse_tag", 0)
            or (not stat.S_ISDIR(found.st_mode) if directory else
                not stat.S_ISREG(found.st_mode) or found.st_nlink != 1)):
        raise CloneFailed("clone_cleanup_incomplete")


def _encoded(row: dict) -> bytes:
    return (json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n").encode("utf-8")


class _Journal:
    def __init__(self, home: Path):
        self.folder = home / "clone-attempts"

    def _directory(self):
        try:
            self.folder.mkdir(mode=0o700)
        except FileExistsError:
            pass
        _plain(self.folder, directory=True)

    def path(self, ident: str) -> Path:
        if OPERATION.fullmatch(ident) is None:
            raise CloneFailed("clone_cleanup_incomplete")
        return self.folder / f"{ident}.json"

    def write_new(self, row: dict) -> Path:
        self._directory()
        path = self.path(row["operation_id"])
        with path.open("xb") as stream:
            stream.write(_encoded(row))
            stream.flush()
            os.fsync(stream.fileno())
        return path

    def replace(self, row: dict) -> None:
        path = self.path(row["operation_id"])
        temporary = self.folder / f".{path.name}.{secrets.token_hex(8)}.tmp"
        try:
            with temporary.open("xb") as stream:
                stream.write(_encoded(row))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.lexists(temporary):
                temporary.unlink()

    def records(self) -> list[Path]:
        """The record files: exactly `operation-<id>.json`, never a restart preparation."""
        return sorted(path for path in self.folder.iterdir() if RECORD.fullmatch(path.name))

    def read(self, path: Path) -> dict:
        if path.parent != self.folder or OPERATION.fullmatch(path.stem) is None:
            raise CloneFailed("clone_cleanup_incomplete")
        _plain(path, directory=False)
        with path.open("rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise CloneFailed("clone_cleanup_incomplete")
        try:
            row = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError) as error:
            raise CloneFailed("clone_cleanup_incomplete") from error
        if (type(row) is not dict or raw != _encoded(row)
                or set(row) != {"schema", "operation_id", "repo", "path", "ancestors",
                                    "parent_identity", "target_identity", "boot", "phase"}
                or type(row["schema"]) is not int or row["schema"] not in (1, 2)
                or row["operation_id"] != path.stem
                or type(row["repo"]) is not str or REPO.fullmatch(row["repo"]) is None
                or type(row["path"]) is not str or not Path(row["path"]).is_absolute()
                or type(row["ancestors"]) is not list or not row["ancestors"]
                or any(type(item) is not list or len(item) != 2
                       or type(item[0]) is not str or not Path(item[0]).is_absolute()
                       or type(item[1]) is not list or len(item[1]) != 2
                       or any(type(part) is not int or part < 0 for part in item[1])
                       for item in row["ancestors"])
                or row["parent_identity"] is not None and (
                    type(row["parent_identity"]) is not list
                    or len(row["parent_identity"]) != 2
                    or any(type(part) is not int or part < 0 for part in row["parent_identity"]))
                or row["target_identity"] is not None and (
                    type(row["target_identity"]) is not list
                    or len(row["target_identity"]) != 2
                    or any(type(part) is not int or part < 0 for part in row["target_identity"]))
                or not boot_prepared.schema_fits(row["schema"], row["boot"])
                or type(row["phase"]) is not str
                or row["phase"] not in {"planned", "created", "running", "cloned",
                                     "cleaned", "cleanup_incomplete"}):
            raise CloneFailed("clone_cleanup_incomplete")
        return row


class _BoundedOutput:
    def __init__(self):
        self.total = 0
        self.exceeded = False
        self.failed = False
        self.stderr = deque(maxlen=20)
        self._lock = threading.Lock()

    def drain(self, stream, *, errors: bool):
        tail = b""
        try:
            while chunk := stream.read(8192):
                with self._lock:
                    self.total += len(chunk)
                    if self.total > OUTPUT_LIMIT:
                        self.exceeded = True
                    if errors and not self.exceeded:
                        lines = (tail + chunk).split(b"\n")
                        tail = lines.pop()
                        for line in lines:
                            self.stderr.append(line.decode("utf-8", errors="replace")[:1000])
            if errors and tail:
                with self._lock:
                    self.stderr.append(tail.decode("utf-8", errors="replace")[:1000])
        except (OSError, ValueError):
            with self._lock:
                self.failed = True
        finally:
            stream.close()


class Clones:
    def __init__(self, home: Path, *, source=None, popen=subprocess.Popen,
                 make_group=_procgroup.make_group, clock=time.monotonic):
        self.home = Path(home)
        self.source = dict(os.environ if source is None else source)
        self._popen, self._make_group, self._clock = popen, make_group, clock
        self._journal = _Journal(self.home)
        self._lock = threading.RLock()
        self._live: dict[str, dict] = {}
        self._pending_cancel: set[str] = set()
        self._finished: set[str] = set()
        self._finished_order = deque()
        #: The attempts the last `recover()` left, by operation id, each with the sentence that
        #: names the next action.
        self.unfinished: dict[str, str] = {}

    def cancel(self, ident: str) -> None:
        with self._lock:
            attempt = self._live.get(ident)
            if ident in self._finished:
                raise CloneFailed("operation_not_cancellable")
            if attempt is None:
                self._pending_cancel.add(ident)
                return
            if not attempt["accepting"]:
                raise CloneFailed("operation_not_cancellable")
            attempt["cancelled"] = True

    def clone(self, ident: str, repo: str, ticket: project_targets.TargetTicket):
        if OPERATION.fullmatch(ident) is None or type(repo) is not str or REPO.fullmatch(repo) is None:
            raise CloneFailed("clone_failed")
        boot = _new_boot()  # before anything is written: no boot measurement, no attempt
        row = {"schema": 2 if boot_witness.is_counter(boot) else 1, "operation_id": ident,
               "repo": repo, "path": str(ticket.path),
               "ancestors": [[str(path), list(identity)] for path, identity in ticket.ancestors],
               "parent_identity": None,
               "target_identity": None, "boot": boot,
               "phase": "planned"}
        self._journal.write_new(row)  # durable intent before exclusive mkdir
        with self._lock:
            self._live[ident] = {"group": None, "cancelled": ident in self._pending_cancel,
                                 "accepting": True,
                                 "stopped_proven": True}
            self._pending_cancel.discard(ident)
        try:
            target, made_home = project_targets.create(self.home, ticket.path.name, expected=ticket)
            row["parent_identity"] = list(_identity(target.parent))
            row["target_identity"] = list(_identity(target))
            row["phase"] = "created"
            self._journal.replace(row)
            if self._cancelled(ident):
                raise CloneFailed("cancelled")
            self._run(ident, repo, target, row)
            with self._lock:
                self._live[ident]["accepting"] = False
                cancelled = self._live[ident]["cancelled"]
            if cancelled:
                raise CloneFailed("cancelled")
            row["phase"] = "cloned"  # a successful clone is now owner data, even if add fails
            self._journal.replace(row)
            return target, made_home
        except BaseException as error:
            if row["phase"] in {"planned", "created", "running"}:
                with self._lock:
                    proven = self._live[ident]["stopped_proven"]
                if not proven:
                    row["phase"] = "cleanup_incomplete"
                    self._journal.replace(row)
                    raise CloneFailed("clone_cleanup_incomplete") from error
                self._cleanup(row)
            raise
        finally:
            with self._lock:
                self._live.pop(ident, None)
                self._finished.add(ident)
                self._finished_order.append(ident)
                if len(self._finished_order) > 100:
                    self._finished.discard(self._finished_order.popleft())

    def _cancelled(self, ident: str):
        with self._lock:
            return self._live[ident]["cancelled"]

    def _run(self, ident: str, repo: str, target: Path, row: dict):
        try:
            pins = tool_pins.load_pins(self.home)
        except tool_pins.ToolPinError as error:
            raise CloneFailed("gh_changed") from error
        if pins.gh is None:
            raise CloneFailed("gh_not_pinned")
        if pins.git is None:
            raise CloneFailed("clone_failed")
        try:
            gh = tool_pins.verify_pin("gh", folder=self.home, source=self.source)
            tool_pins.verify_pin("git", folder=self.home, source=self.source)
        except tool_pins.ToolPinError as error:
            raise CloneFailed(error.code if error.code in {"gh_not_pinned", "gh_changed"}
                              else "clone_failed") from error
        argv = [gh.path, "repo", "clone", repo, str(target), "--", "--no-recurse-submodules"]
        env = tool_env.tool_env(self.source, pins, self.home)
        row["phase"] = "running"
        self._journal.replace(row)
        with self._lock:
            self._live[ident]["stopped_proven"] = False
        try:
            proc = self._popen(argv, cwd=self.home, env=env, shell=False,
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, **_procgroup.popen_kwargs())
        except BaseException:
            with self._lock:
                self._live[ident]["stopped_proven"] = True
            raise
        group = None
        try:
            group = self._make_group(proc)
            with self._lock:
                self._live[ident]["group"] = group
                cancelled = self._live[ident]["cancelled"]
            output = _BoundedOutput()
            pumps = [threading.Thread(target=output.drain, args=(stream,),
                                      kwargs={"errors": errors}, daemon=True)
                     for stream, errors in ((proc.stdout, False), (proc.stderr, True))]
            for pump in pumps:
                pump.start()
            deadline = self._clock() + TIMEOUT
            reason = "cancelled" if cancelled else None
            while proc.poll() is None and reason is None:
                if output.exceeded or output.failed:
                    reason = "clone_failed"
                elif self._cancelled(ident):
                    reason = "cancelled"
                elif self._clock() >= deadline:
                    reason = "clone_timeout"
                else:
                    time.sleep(0.05)
            group.terminate()  # retire descendants even if gh's leader exited
            proc.wait(timeout=5)
            proven = group.retired(timeout=5)
            for pump in pumps:
                pump.join(timeout=5)
            if not proven or any(pump.is_alive() for pump in pumps):
                raise CloneFailed("clone_cleanup_incomplete")
            with self._lock:
                self._live[ident]["stopped_proven"] = True
            if output.exceeded or output.failed:
                reason = "clone_failed"
            if reason is None and proc.returncode != 0:
                reason = "gh_not_logged_in" if proc.returncode == 4 else "clone_failed"
            if reason is not None:
                raise CloneFailed(reason, stderr=tuple(output.stderr))
        finally:
            with self._lock:
                if self._live.get(ident, {}).get("group") is group:
                    self._live[ident]["group"] = None
            if group is not None:
                group.close()
            else:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)
                # A reaped leader is not proof about descendants. The intent
                # remains for a later, independently proven recovery.

    def _held(self, row: dict, holds: ExitStack, chain=()):
        """Admit the folder of `row` and hold what its removal holds; the parent's descriptor.

        The descriptor is None where there is none (Windows) or no folder was ever made.

        Raises:
            CloneFailed: The folder, its parent or its ancestors are not what the record names, or
                an object appeared that the newest preparation did not hold.
        """
        target = Path(row["path"])
        self._admitted_target(target)
        if row["target_identity"] is None:
            if os.path.lexists(target):
                raise CloneFailed("clone_cleanup_incomplete")
            return None
        _plain(target, directory=True)
        if (row["parent_identity"] is None
                or list(_identity(target)) != row["target_identity"]
                or list(_identity(target.parent)) != row["parent_identity"]):
            raise CloneFailed("clone_cleanup_incomplete")
        ancestors = tuple((Path(path), tuple(identity)) for path, identity in row["ancestors"])
        anchor = ancestors[-1][0]
        if (anchor not in {target.parent, target.parent.parent}
                or tuple(path for path, _identity_value in ancestors)
                != project_targets._ancestors(anchor)):
            raise CloneFailed("clone_cleanup_incomplete")
        expected = project_targets.TargetTicket(target, self.home.resolve(),
            registry.load(self.home).projects_home, ancestors)
        parent_fd, _made_home = project_targets._held_parent(expected, holds)
        if list(_identity(target.parent)) != row["parent_identity"]:
            raise CloneFailed("clone_cleanup_incomplete")
        if boot_prepared.appeared(chain, _expected_held(row), ("target", "parent")):
            raise CloneFailed("clone_cleanup_incomplete", stderr=(
                "an owned object appeared after the restart was prepared",))
        return parent_fd

    def _cleanup(self, row: dict, chain=()) -> None:
        try:
            with ExitStack() as holds:
                parent_fd = self._held(row, holds, chain)
                if row["target_identity"] is not None:
                    target, expected = Path(row["path"]), tuple(row["target_identity"])
                    if os.name == "nt":
                        clone_cleanup.remove_windows(target, expected)
                    else:
                        clone_cleanup.remove_posix(parent_fd, target, expected)
            row["phase"] = "cleaned"
            self._journal.replace(row)
        except (OSError, ownership_native.NativeOwnershipError, registry.RegistryError,
                HubRefusal, clone_cleanup.CleanupRefused, CloneFailed) as error:
            row["phase"] = "cleanup_incomplete"
            self._journal.replace(row)
            raise CloneFailed("clone_cleanup_incomplete", stderr=getattr(error, "stderr", ())
                              ) from error

    def _admitted_target(self, target: Path) -> None:
        if project_targets.FOLDER.fullmatch(target.name) is None:
            raise CloneFailed("clone_cleanup_incomplete")
        configured = registry.load(self.home).projects_home
        parent = Path(configured) if configured is not None else Path.home() / project_targets.DEFAULT_NAME
        if target.parent != project_targets.admit_home(parent, self.home,
                                                        missing_default=configured is None):
            raise CloneFailed("clone_cleanup_incomplete")

    def recover(self) -> tuple[str, ...]:
        """Remove the folders of attempts a restart is proven for; prepare nothing.

        An attempt whose restart is not proven, or that needs a preparation (a record from before
        the boot counter, or one that met another boot environment), is left as it is and listed;
        `unfinished` holds, for each, the sentence that names the next action.

        Returns:
            The operation ids still unfinished.
        """
        self.unfinished = {}
        if not self._journal.folder.exists():
            return ()
        _plain(self._journal.folder, directory=True)
        unmeasured = None
        try:
            current = _boot_now("no restart can be proven", "clone_cleanup_incomplete")
        except CloneFailed as error:
            current, unmeasured = "", " ".join(error.stderr)
        for path in self._journal.records():
            row = self._journal.read(path)
            if row["phase"] in _FINAL:
                continue
            reason = unmeasured or self._recover_one(row, current)
            if reason is not None:
                self.unfinished[row["operation_id"]] = reason
        return tuple(self.unfinished)

    def _recover_one(self, row: dict, current: str) -> str | None:
        """Clean one attempt up if a restart is proven for it; else the sentence for the action."""
        with ExitStack() as files:
            found = boot_prepared.standing(files, self._journal.folder, row["operation_id"],
                                           _facts(row), _expected_held(row), current, _COMMAND)
            if found.reason is not None:
                return found.reason
            try:
                self._cleanup(row, found.chain)
            except CloneFailed as error:
                return " ".join(error.stderr) or "the folder could not be removed completely"
        return None

    def prepare_restart(self, ident: str) -> tuple[dict, bool]:
        """Write the next restart preparation of one attempt; clean up and release nothing.

        Only an explicit call writes it, never `recover()` or the start of the hub. The folder and
        its parents are held and checked against the record first, exactly as a clean-up would;
        the chain already on disk is read whole. A record from before the boot counter gets its
        first preparation; one that met another boot environment gets a new one that binds the one
        before. In the environment that already stands a repeat returns the newest and writes
        nothing; a lower counter, an unreadable boot or a record that needs none is never a way to
        write one.

        Returns:
            `(preparation, created)`.

        Raises:
            CloneFailed: `clone_cleanup_incomplete`; `stderr` holds the sentence that says why.
        """
        row = self._journal.read(self._journal.path(ident))
        if row["phase"] in _FINAL:
            raise CloneFailed("clone_cleanup_incomplete",
                              stderr=("this attempt is finished: nothing to prepare",))
        try:
            with ExitStack() as stack:
                self._held(row, stack)
                return self._prepared(row, stack)
        except CloneFailed as error:
            if error.stderr:
                raise
            raise CloneFailed(error.code, stderr=(
                "the folder and its parents are not the ones the record names",)) from error
        except (OSError, ownership_native.NativeOwnershipError, registry.RegistryError,
                HubRefusal) as error:
            raise CloneFailed("clone_cleanup_incomplete", stderr=(
                f"the folder and its parents could not be held as the record names them: {error}",
            )) from error

    def _prepared(self, row: dict, stack: ExitStack) -> tuple[dict, bool]:
        folder, ident = self._journal.folder, row["operation_id"]
        held = {"target": None, "parent": None}
        if row["target_identity"] is not None:
            target = Path(row["path"])
            hold = ownership_native.NativeHold(target, directory=True)
            stack.callback(hold.close)
            held = {"target": list(hold.identity), "parent": list(_identity(target.parent))}
            if held != _expected_held(row):
                raise CloneFailed("clone_cleanup_incomplete", stderr=(
                    "the folder is not the one the record names",))
        try:
            chain = boot_prepared.read_chain(stack, folder, ident, _facts(row), _expected_held(row))
        except boot_prepared.PreparationInvalid as error:
            raise CloneFailed("clone_cleanup_incomplete", stderr=(
                f"the restart preparations of this record do not stand: {error}",)) from error
        current = _boot_now("no restart can be prepared", "clone_cleanup_incomplete")
        try:
            needed = boot_prepared.decide(row["boot"], chain, current)
        except BootRefused as error:
            raise CloneFailed("clone_cleanup_incomplete", stderr=(
                boot_witness.preparation_refusal(error, _COMMAND),)) from error
        if not needed:
            return chain[-1], False
        try:
            written = boot_prepared.write_next(stack, folder, ident, _facts(row), held, chain,
                                               current)
        except boot_prepared.PreparationInvalid as error:
            raise CloneFailed("clone_cleanup_incomplete", stderr=(str(error),)) from error
        return written, True

    def prepare_restarts(self) -> list[dict]:
        """`prepare_restart` for every attempt that is not finished; one refusal hides no other.

        Returns:
            One row per attempt: `recovery_prepared` with `created` and `prepared_boot`, or
            `not_prepared` with the sentence that says why.
        """
        rows: list[dict] = []
        if not self._journal.folder.exists():
            return rows
        _plain(self._journal.folder, directory=True)
        for path in self._journal.records():
            row = self._journal.read(path)
            if row["phase"] in _FINAL:
                continue
            ident = row["operation_id"]
            try:
                preparation, created = self.prepare_restart(ident)
            except CloneFailed as error:
                rows.append({"operation_id": ident, "state": "not_prepared",
                             "action": " ".join(error.stderr) or error.code})
            else:
                rows.append({"operation_id": ident, "state": "recovery_prepared",
                             "created": created, "prepared_boot": preparation["prepared_boot"]})
        return rows
