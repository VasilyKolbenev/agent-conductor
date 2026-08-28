"""The owned-process runner and a thin process-backed adapter over it.

This is the one door December Command uses to start a real child process. Every
safety property the plan's law 1-2 name is enforced here as a *relation*, not a
name check, and each is provable by executing the child:

- **Structured argv only.** A command is a list of strings; a shell string is
  refused at the boundary and ``shell=False`` is never negotiable, so arbitrary
  shell text in any argument reaches the child as one inert token and no shell
  ever interprets it.
- **Contained cwd.** The child's working directory must be strictly beneath the
  resolved project root, proven by reading every component of the route from the
  root down with ``os.lstat`` alone, following nothing: a symlink, an NTFS
  junction, any other reparse point, a ``..`` segment, or a path that simply is
  not under the root refuses *before* the child is spawned. This is the CMD-4
  boundary lesson -- the check covers the whole route, not just the leaf.
- **Sanitized environment.** The child never inherits the parent environment
  wholesale. It receives exactly the parent variables an explicit allowlist
  names (the reference set for secrets, per law 8) plus explicit literal extras;
  a parent variable outside the allowlist never reaches the child. The
  allowlist is itself bounded: a credential or a tool-discovery variable, never
  one a runtime reads to load code ahead of the pinned entrypoint's own.
- **Bounded output.** Captured output is truncated at a stated byte bound and
  the outcome says so; a runaway child cannot exhaust the parent, because the
  pump keeps draining the pipe while discarding everything past the bound.
- **Timeout is its own fact.** A child that overruns its timeout is terminated
  and reported ``timed_out`` -- never ``completed``, never a silent success.
- **Ownership.** The runner mints an unguessable token for each child it starts
  and can stop only a token it minted; there is no method that kills a PID, so a
  foreign or recycled PID cannot be named, let alone signalled.

Two limits are stated rather than hidden. The containment check reads and then
spawns, so a local writer that swaps a route component between the ``lstat`` and
``CreateProcess``/``execve`` is not stopped -- within one project the tree is
single-writer by contract, and against a concurrent adversary this boundary is
best-effort. And an NTFS alternate data stream is not a component of any route
this walk reads, so it is neither detected nor traversed.
"""
from __future__ import annotations

import os
import re
import secrets
import subprocess
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from ..contracts import (
    ActionRequest,
    ActionResultReceipt,
)
from ..containment import (
    assess_cwd_route,
    detected_portal as _detected_portal,
    render_cwd_violation,
)
from ..dispatch import DispatchArgumentError, validate_dispatch_arguments
from . import _procgroup
from .base import (
    AdapterContractError,
    AdapterManifest,
    AdapterObservation,
    AdapterVerification,
    PreparedAction,
    UnsupportedCapability,
)

#: Default ceiling on captured output; a child cannot push the parent past it.
DEFAULT_OUTPUT_LIMIT = 64 * 1024
#: Ceiling on what a caller may hand a child through stdin. The same 64 KiB the
#: workspace door already imposes on an instruction body -- deliberately, and
#: pinned equal by a test, because the only thing this build ever writes to a
#: child's stdin IS an instruction body. A second, larger ceiling here would be
#: a way to deliver an instruction the first one refused.
STDIN_LIMIT = 64 * 1024
#: What became of the input a caller offered the child. A CLOSED vocabulary,
#: because the question it answers is not "did an error occur" but "was the
#: child ever asked the question at all", and there is no third honest answer.
#:
#: `delivered` costs the most to say and is therefore said last: the whole
#: payload written, flushed, and the stream CLOSED, so the child saw end of
#: input. Anything else is `incomplete` -- a broken pipe, a short write, a
#: failure to close -- and `incomplete` is not a degraded success. A child that
#: never read its instruction did not do the task badly; it was never told what
#: the task was, and its exit code answers a different question.
#:
#: **What `delivered` does NOT claim, said out loud.** It is a fact about THIS
#: side of the pipe. A payload small enough to fit the operating system's pipe
#: buffer is written, flushed and closed successfully even if the child then
#: exits without reading a byte of it, and no parent can tell the difference --
#: the read happens on the far side and leaves no trace here. So `delivered`
#: means "handed over in full and ended", never "consumed". The only witness for
#: consumption is the child's own output, which is why a provider taking its
#: task this way owes a smoke that returns a marker present ONLY in what was
#: piped. `incomplete` remains exact in the other direction: it is never wrong
#: about a failure, only silent about a success it cannot see.
STDIN_NOT_PROVIDED = "not_provided"
STDIN_DELIVERED = "delivered"
STDIN_INCOMPLETE = "incomplete"
STDIN_STATES = (STDIN_NOT_PROVIDED, STDIN_DELIVERED, STDIN_INCOMPLETE)
#: One read from the child's merged pipe; the pump loops over these.
_READ_CHUNK = 64 * 1024
#: A POSIX environment variable name; the same shape run_store screens against.
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
#: The one capability this adapter executes; every other control stays absent.
DISPATCH_CAPABILITY = "dispatch"

#: Environment names an operator may NOT put in `env_allow`, grouped by the
#: runtime that reads them, each group carrying the reason it is refused.
#:
#: The line is a relation, not a feeling about a name. `PATH` and its kin choose
#: a SEPARATE program the child may decide to start, and the reviewed entrypoint
#: still runs first and still decides. Every name below instead chooses code
#: loaded INTO the reviewed process before its own first instruction, which
#: hands back the authority an absolute pin was taken to hold. The roster is
#: closed against the runtimes a vendor CLI here can BE, not against today's
#: five providers, so adding a runtime obliges adding its row. The ruling, its
#: evidence and its stated limits: `docs/adr/0007-env-allow-trust-boundary.md`.
_INJECTING_ENV_GROUPS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("LD_PRELOAD", "LD_AUDIT", "LD_LIBRARY_PATH"),
     "the ELF dynamic loader maps and runs what it names inside the process "
     "before the program's own first instruction"),
    (("DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
      "DYLD_FALLBACK_LIBRARY_PATH", "DYLD_FALLBACK_FRAMEWORK_PATH"),
     "macOS dyld inserts and redirects libraries into the process before "
     "main() runs"),
    (("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONEXECUTABLE"),
     "CPython reads it before the pinned entrypoint script, so the first "
     "import that script performs can be an attacker's module"),
    (("NODE_OPTIONS", "NODE_PATH", "NODE_REPL_EXTERNAL_MODULE"),
     "node executes --require and --import modules, and resolves requires "
     "through NODE_PATH, ahead of the pinned entrypoint"),
    (("JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "CLASSPATH"),
     "the JVM reads it before main: the option variables carry -javaagent, "
     "whose premain runs first, and CLASSPATH decides which class a name is"),
    (("DOTNET_STARTUP_HOOKS", "CORECLR_ENABLE_PROFILING", "CORECLR_PROFILER",
      "CORECLR_PROFILER_PATH", "COR_ENABLE_PROFILING", "COR_PROFILER",
      "COR_PROFILER_PATH"),
     "the .NET host runs a startup hook, and loads a profiler library, before "
     "the entrypoint's Main"),
    (("RUBYOPT", "RUBYLIB", "PERL5OPT", "PERL5LIB", "PERLLIB"),
     "ruby and perl read them for -r and -I, requiring a library before the "
     "script they were pointed at"),
)
INJECTING_ENV: Mapping[str, str] = MappingProxyType({
    name: reason for names, reason in _INJECTING_ENV_GROUPS for name in names})


def injecting_env_reason(name: str, *, windows: bool | None = None) -> str | None:
    """Say why an operator may not reference ``name``, or ``None`` if they may.

    Args:
        name: An environment variable name, in the spelling the operator wrote.
        windows: Whether to match without regard to case. ``None`` asks the
            running platform, which is the only honest default: Windows
            environment names are case-insensitive, so ``Ld_Preload`` there IS
            ``LD_PRELOAD`` and a case-sensitive rule would be bypassed by
            shift-key alone. On POSIX the two spellings are different variables
            and folding them would refuse a name that can inject nothing.

    Returns:
        The reason this name is refused, or ``None`` when it may be referenced.
    """
    if windows is None:
        windows = os.name == "nt"
    return INJECTING_ENV.get(name.upper() if windows else name)


class ProcessRunnerError(RuntimeError):
    """The runner cannot safely honour the request as stated."""


class CommandSpecError(ProcessRunnerError):
    """A command is not structured argv, or its environment names are malformed."""


class ContainmentError(ProcessRunnerError):
    """The requested cwd is not strictly, locally beneath the project root."""


class OwnershipError(ProcessRunnerError):
    """A stop names no child this runner started and still holds."""


def _argv(value: object) -> tuple[str, ...]:
    """A non-empty list of NUL-free strings; a shell string is not a command."""
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise CommandSpecError("argv must be a list of strings, never a shell string")
    rows = tuple(value)
    if not rows:
        raise CommandSpecError("argv must name at least the executable to run")
    for item in rows:
        if not isinstance(item, str):
            raise CommandSpecError(f"argv element must be a string, got {item!r}")
        if "\x00" in item:
            raise CommandSpecError("argv element must not contain NUL")
    return rows


def _env_names(value: object) -> tuple[str, ...]:
    """The allowlist: distinct, valid, non-injecting names to reference.

    The refusal sits HERE because every road that starts a child ends in a spec
    -- provider file, public dispatch body, deep adapters, all five headless
    harnesses -- so a refusal on any one door would leave the others open.
    """
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise CommandSpecError("env_allow must be a list of environment variable names")
    names = tuple(value)
    for name in names:
        if not isinstance(name, str) or _ENV_NAME.fullmatch(name) is None:
            raise CommandSpecError(f"env_allow names an invalid variable: {name!r}")
        reason = injecting_env_reason(name)
        if reason is not None:
            # Name AND reason: an operator told only "invalid" hunts a typo.
            raise CommandSpecError(f"env_allow may not name {name!r}: {reason}")
    if len(set(names)) != len(names):
        raise CommandSpecError("env_allow must not repeat a variable name")
    return names


def _env_map(value: object) -> Mapping[str, str]:
    """Explicit literal variables: valid names to NUL-free string values."""
    if not isinstance(value, Mapping):
        raise CommandSpecError("env must map variable names to string values")
    out: dict[str, str] = {}
    for name, item in value.items():
        if not isinstance(name, str) or _ENV_NAME.fullmatch(name) is None:
            raise CommandSpecError(f"env names an invalid variable: {name!r}")
        if not isinstance(item, str) or "\x00" in item:
            raise CommandSpecError(f"env[{name!r}] must be a string without NUL")
        out[name] = item
    return MappingProxyType(out)


def _stdin(value: object) -> bytes | None:
    """Nothing, or a bounded NUL-free byte payload the child will read whole.

    Refused BEFORE the spawn, every time, because the alternative is a child
    that already exists when the input turns out to be inadmissible -- and a
    child that exists has already been handed the workspace.

    NUL is refused for the same reason argv refuses it: this payload is an
    instruction body, a text artefact, and an embedded NUL is either a truncation
    a downstream reader will act on or something that was never text.
    """
    if value is None:
        return None
    if type(value) is not bytes:
        raise CommandSpecError("stdin_bytes must be bytes or None, never text")
    if len(value) > STDIN_LIMIT:
        # The LENGTH is named and the content is not; this message is a road out.
        raise CommandSpecError(
            f"stdin_bytes is {len(value)} bytes, past the {STDIN_LIMIT} ceiling")
    if b"\x00" in value:
        raise CommandSpecError("stdin_bytes must not contain NUL")
    return value


@dataclass(frozen=True)
class CommandSpec:
    """One structured command; validated at construction, never a shell string."""

    argv: tuple[str, ...]
    cwd: str
    env_allow: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    output_limit: int = DEFAULT_OUTPUT_LIMIT
    timeout_seconds: float | None = None
    #: Keep stderr out of ``output`` when one caller must admit stdout bytes as
    #: a typed value. False preserves the historical merged stream exactly.
    #:
    #: Separated does not mean kept: the stream goes to the operating system's
    #: null device, so the child's diagnostics are neither captured nor retained
    #: anywhere here. The one caller that asks for separation does so because
    #: its stdout becomes a durable artifact, and a vendor's stderr -- the
    #: likeliest place for a CLI to echo a key -- has no reader in this build,
    #: so holding it would be secret surface kept alive for nobody. A null SINK
    #: rather than an undrained pipe is also the only shape that cannot
    #: deadlock the first child that writes more than a pipe holds.
    separate_stderr: bool = False
    #: What the child reads on stdin, or ``None`` for no input at all.
    #:
    #: ``repr=False`` is not cosmetic. This field is the ONE place in a spec that
    #: carries the operator's own prose rather than code-owned tokens, and a spec
    #: reaches an exception message, a debugger frame and a log line by simply
    #: being repr'd. Every other road out -- receipts, the journal, the API, SSE
    #: -- is closed by tests that name this field, because nothing about a
    #: dataclass stops a future caller from reading it and passing it on.
    #:
    #: ``None`` is not the same as empty. ``None`` means the child is spawned on
    #: ``DEVNULL`` exactly as every provider was before this field existed;
    #: ``b""`` means it is handed an open pipe that is immediately at EOF.
    stdin_bytes: bytes | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "argv", _argv(self.argv))
        if not isinstance(self.cwd, str) or not self.cwd:
            raise CommandSpecError("cwd must be a non-empty path string")
        object.__setattr__(self, "env_allow", _env_names(self.env_allow))
        object.__setattr__(self, "env", _env_map(self.env))
        if (isinstance(self.output_limit, bool)
                or not isinstance(self.output_limit, int) or self.output_limit <= 0):
            raise CommandSpecError("output_limit must be a positive integer byte count")
        timeout = self.timeout_seconds
        if timeout is not None and (
                isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                or timeout <= 0):
            raise CommandSpecError("timeout_seconds must be a positive number or None")
        if type(self.separate_stderr) is not bool:
            raise CommandSpecError("separate_stderr must be a boolean")
        object.__setattr__(self, "stdin_bytes", _stdin(self.stdin_bytes))


@dataclass(frozen=True)
class OwnedProcess:
    """The identity a started child answers to: an unguessable token plus its pid."""

    token: str
    pid: int


@dataclass(frozen=True)
class ProcessOutcome:
    """The runner's account of a finished child; the status is its own fact.

    ``status`` is one of ``completed`` (the child exited on its own within the
    timeout), ``timed_out`` (it overran and was terminated), or ``stopped`` (a
    ``stop`` terminated it). ``exit_code`` is the child's real code only when it
    completed; a terminated child carries ``None``, because the code a kill
    leaves behind is not the child's own answer.
    """

    status: str
    exit_code: int | None
    output: bytes = field(repr=False)
    output_truncated: bool
    output_limit: int
    pid: int
    token: str
    #: Whether the child was ever handed what it was supposed to act on. Its own
    #: fact, beside ``status`` and ``exit_code`` rather than folded into either,
    #: because it answers a question they cannot: a child that exits zero having
    #: read nothing has answered honestly about a task it was never given.
    #:
    #: The default is ``not_provided``, which is what an outcome built by a
    #: caller that offered no input truthfully says.
    stdin_state: str = STDIN_NOT_PROVIDED
    #: A boolean only: no environment value is copied into the outcome.
    output_contains_env_value: bool = False

    def __post_init__(self) -> None:
        if self.stdin_state not in STDIN_STATES:
            raise CommandSpecError(
                f"stdin_state must be one of {STDIN_STATES}, got "
                f"{self.stdin_state!r}")


class _Owned:
    """A live child, its termination group, and a bounded pump over its output."""

    def __init__(self, proc: "subprocess.Popen[bytes]", token: str, limit: int,
                 group: _procgroup.ProcessGroup,
                 stdin_bytes: bytes | None = None,
                 sensitive_values: tuple[bytes, ...] = ()) -> None:
        self.proc = proc
        self.token = token
        self.pid = proc.pid
        self.limit = limit
        self.group = group
        self._sensitive_values = sensitive_values
        self._buf = bytearray()
        self._truncated = False
        self._lock = threading.Lock()
        # ONE pump, because there is only ever one stream to read: stderr is
        # either merged into this one or sent to the null device, and neither
        # shape leaves a second pipe for this side to hold.
        self._pump = threading.Thread(target=self._drain, daemon=True)
        self._pump.start()
        # The feed starts AFTER the pump, and that order is the whole of the
        # deadlock argument: a child that answers while it is still being fed
        # would otherwise fill its stdout pipe and block, while this side blocks
        # writing, and neither would ever move again.
        # Fail-closed: the state starts at `incomplete` the moment a payload
        # exists and is raised to `delivered` only by a feed that finished every
        # step. A thread that never ran, or died before its last line, therefore
        # reports the truth rather than the default.
        self._feeder: threading.Thread | None = None
        self.stdin_state = STDIN_NOT_PROVIDED
        if stdin_bytes is not None:
            self.stdin_state = STDIN_INCOMPLETE
            self._feeder = threading.Thread(
                target=self._feed, args=(stdin_bytes,), daemon=True)
            self._feeder.start()

    def _feed(self, payload: bytes) -> None:
        """Hand the child its whole input, then EOF. Never raises, always closes.

        EOF is the point. A print-mode child reading its prompt from stdin waits
        for the stream to end before it begins, so a writer that returned
        without closing would hang the child until its own timeout -- an
        expensive way to say nothing.

        The write LOOPS because the child was spawned unbuffered: a raw stream
        may take fewer bytes than it was offered, and one `write` call is not a
        promise that all of them arrived.

        Every failure here is expected rather than exceptional. A child that
        exits before reading breaks the pipe; a terminated one breaks it
        mid-write; either way the run's own account of what happened comes from
        its exit and its output, and never from this thread.
        """
        stream = self.proc.stdin
        if stream is None:
            return
        written_whole = False
        try:
            view = memoryview(payload)
            while view:
                written = stream.write(view)
                if not written:
                    break
                view = view[written:]
            if not view:
                stream.flush()
                written_whole = True
        except (OSError, ValueError):
            pass
        try:
            stream.close()
        except (OSError, ValueError):
            return
        # The close is the EOF, so it is part of the claim rather than cleanup
        # after it: a payload fully written to a stream that was never closed
        # leaves the child waiting for input that will never end.
        if written_whole:
            self.stdin_state = STDIN_DELIVERED

    def _drain(self) -> None:
        """Read the child's captured stream to EOF, keeping only what fits.

        The read continues past the bound and DISCARDS, rather than stopping:
        a pump that stopped reading would leave the pipe to fill and the child
        blocked on its next write, which turns a bound on what the parent keeps
        into a bound on what the child may say.
        """
        stream = self.proc.stdout
        if stream is None:
            return
        fd = stream.fileno()
        while True:
            try:
                chunk = os.read(fd, _READ_CHUNK)
            except OSError:
                break
            if not chunk:
                break
            with self._lock:
                room = self.limit - len(self._buf)
                if room > 0:
                    self._buf += chunk[:room]
                    if len(chunk) > room:
                        self._truncated = True
                else:
                    self._truncated = True

    def finish(self, status: str) -> ProcessOutcome:
        # The feeder is joined FIRST, and only ever after the caller has waited
        # on the child and terminated its group -- so a write still blocked on a
        # full pipe is already failing rather than waiting. Joining it at all is
        # what makes the four exits one exit: completed, timed out, stopped and
        # early-exit all arrive here, and none of them leaves a thread holding
        # the child's input open.
        if self._feeder is not None:
            self._feeder.join()
        self._pump.join()
        with self._lock:
            output, truncated = bytes(self._buf), self._truncated
        contains_env = any(value in output for value in self._sensitive_values)
        code = self.proc.returncode
        return ProcessOutcome(
            status=status, exit_code=code if status == "completed" else None,
            output=output, output_truncated=truncated, output_limit=self.limit,
            pid=self.pid, token=self.token, stdin_state=self.stdin_state,
            output_contains_env_value=contains_env)


class ProcessRunner:
    """Starts, bounds, times out, and stops only the children it started.

    A runner is bound to one project root at construction; every cwd it accepts
    is validated strictly beneath that resolved root. The parent variables it
    may reference come from ``environ`` (the live process environment by
    default), never from an implicit inheritance of it into the child.
    """

    def __init__(self, project_root: str | os.PathLike[str], *,
                 environ: Mapping[str, str] | None = None) -> None:
        self._root = Path(project_root).resolve()
        self._environ = dict(os.environ if environ is None else environ)
        self._owned: dict[str, _Owned] = {}
        self._lock = threading.Lock()

    def start(self, spec: CommandSpec) -> OwnedProcess:
        """Spawn and return an ownership token that must be explicitly stopped.

        Day-1 exposes no asynchronous success/reap claim: launchers may exit
        before their real child, so the group token remains owned until ``stop``
        retires the whole group.  Synchronous completion belongs to ``run``.
        """
        owned = self._spawn(spec)
        return OwnedProcess(token=owned.token, pid=owned.pid)

    def run(self, spec: CommandSpec) -> ProcessOutcome:
        """Spawn, wait up to the timeout, terminate on overrun, and account for it."""
        owned = self._spawn(spec)
        try:
            try:
                owned.proc.wait(timeout=spec.timeout_seconds)
                status = "completed"
            except subprocess.TimeoutExpired:
                owned.group.terminate()
                owned.proc.wait()
                status = "timed_out"
            # A leader may exit while descendants still run.  Terminate the
            # group BEFORE joining the inherited output pipe: a descendant may
            # still hold that pipe open after the leader exits.
            owned.group.terminate()
            return owned.finish(status)
        finally:
            self._release(owned)

    def stop(self, token: str) -> ProcessOutcome:
        """Terminate the child this token names; refuse a token never minted here."""
        with self._lock:
            owned = self._owned.get(token)
        if owned is None:
            raise OwnershipError(
                f"stop names token {token!r}, which this runner did not mint or no "
                "longer holds; it terminates only a child it started and still owns")
        if owned.proc.poll() is not None:
            try:
                # The group handle, not a caller PID, remains the ownership
                # witness; retire descendants before retiring the token.
                owned.group.terminate()
                owned.finish("stopped")  # join the pump after descendants close the pipe
            finally:
                self._release(owned)
            raise OwnershipError(
                f"stop names token {token!r}, whose leader already finished; "
                "its owned descendants were retired with the group")
        owned.group.terminate()
        owned.proc.wait()
        try:
            return owned.finish("stopped")
        finally:
            self._release(owned)

    def active_tokens(self) -> tuple[str, ...]:
        """The tokens of children this runner still owns; empty means none leaked."""
        with self._lock:
            return tuple(sorted(self._owned))

    def _spawn(self, spec: CommandSpec) -> _Owned:
        cwd = self._resolve_cwd(spec.cwd)  # refuses before any child exists
        env = self._child_env(spec)
        sensitive_values = tuple(
            env[name].encode("utf-8") for name in spec.env_allow
            if name in env and env[name])
        # No payload means DEVNULL, byte for byte the spawn every provider got
        # before this field existed. A payload means a pipe, and nothing else
        # about the spawn changes.
        payload = spec.stdin_bytes
        proc = subprocess.Popen(
            list(spec.argv), cwd=str(cwd), env=env, shell=False, bufsize=0,
            stdin=subprocess.DEVNULL if payload is None else subprocess.PIPE,
            stdout=subprocess.PIPE,
            # Separated stderr goes to the null device, never to a pipe: this
            # build has no reader for a vendor's diagnostics, and a pipe nobody
            # drains stalls the child that fills it.
            stderr=(subprocess.DEVNULL if spec.separate_stderr
                    else subprocess.STDOUT),
            **_procgroup.popen_kwargs())
        try:
            group = _procgroup.make_group(proc)
        except BaseException:
            self._cleanup_failed_spawn(proc, None)
            raise
        try:
            token = secrets.token_hex(16)
            owned = _Owned(
                proc, token, spec.output_limit, group, payload,
                sensitive_values)
        except BaseException:
            self._cleanup_failed_spawn(proc, group)
            raise
        with self._lock:
            self._owned[token] = owned
        return owned

    @staticmethod
    def _cleanup_failed_spawn(
            proc: "subprocess.Popen[bytes]",
            group: _procgroup.ProcessGroup | None) -> None:
        """Bounded fail-closed cleanup after Popen but before ownership publish."""
        try:
            if group is not None:
                try:
                    group.terminate()
                except BaseException:
                    pass  # direct handle kill below remains mandatory
            if proc.poll() is None:
                proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        finally:
            if group is not None:
                group.close()
            if proc.stdout is not None:
                proc.stdout.close()
            if proc.stderr is not None:
                proc.stderr.close()
            # And the input, which `Popen(stdin=PIPE)` opened on this side. A
            # spawn that fails between `Popen` and the ownership publish has no
            # `_Owned` to close it later and no token anyone could stop, so the
            # parent's write handle would live until the garbage collector
            # happened to notice -- holding a pipe to a child already killed.
            if proc.stdin is not None:
                try:
                    proc.stdin.close()
                except (OSError, ValueError):
                    pass

    def _release(self, owned: _Owned) -> None:
        with self._lock:
            self._owned.pop(owned.token, None)
        owned.group.close()

    def _resolve_cwd(self, raw_cwd: str) -> Path:
        walked, violation = assess_cwd_route(self._root, raw_cwd)
        if violation is not None:
            raise ContainmentError(render_cwd_violation(violation))
        return walked

    def _child_env(self, spec: CommandSpec) -> dict[str, str]:
        env: dict[str, str] = {}
        for name in spec.env_allow:
            if name in self._environ:
                env[name] = self._environ[name]
        for name, value in spec.env.items():
            env[name] = value
        return env


def _spec_from_arguments(
        arguments: Mapping[str, object], timeout_seconds: int) -> CommandSpec:
    """Read a dispatch request's structured command; refuse a malformed one."""
    if not isinstance(arguments, Mapping):
        raise AdapterContractError("dispatch arguments must be a JSON object")
    try:
        validate_dispatch_arguments(arguments)
        return CommandSpec(
            argv=arguments.get("argv"),
            cwd=arguments.get("cwd"),
            env_allow=arguments.get("env_allow", ()),
            output_limit=arguments.get("output_limit", DEFAULT_OUTPUT_LIMIT),
            timeout_seconds=timeout_seconds)
    except (CommandSpecError, DispatchArgumentError, TypeError, ValueError) as e:
        raise AdapterContractError(
            f"dispatch arguments are not a valid command: {e}") from e


def _payload_from_spec(spec: CommandSpec) -> dict[str, object]:
    """The adapter payload: a plain-JSON echo of the validated command."""
    return {
        "argv": list(spec.argv), "cwd": spec.cwd,
        "env_allow": list(spec.env_allow),
        "output_limit": spec.output_limit,
    }


def _spec_from_payload(payload: Mapping[str, object], timeout_seconds: int) -> CommandSpec:
    return CommandSpec(
        argv=tuple(payload["argv"]), cwd=payload["cwd"],
        env_allow=payload["env_allow"],
        output_limit=payload["output_limit"], timeout_seconds=timeout_seconds)


def _detail(outcome: ProcessOutcome, summary: str) -> str:
    note = f"{summary}; captured {len(outcome.output)} bytes"
    if outcome.output_truncated:
        note += f", truncated at the {outcome.output_limit}-byte capture bound"
    return note


def _map_outcome(outcome: ProcessOutcome) -> tuple[str, str]:
    """Project a process outcome onto the receipt vocabulary; timeout is not success.

    Undelivered input is checked inside the ``completed`` arm rather than ahead
    of everything, so a timeout stays a timeout and a stop stays a cancellation:
    those two already say the run did not succeed, and overwriting them would
    trade one true fact for another. What may never happen is a ZERO becoming a
    success while the child never received what it was meant to act on.
    """
    if outcome.status == "completed":
        if outcome.exit_code == 0:
            if outcome.stdin_state == STDIN_INCOMPLETE:
                return "failed", _detail(
                    outcome,
                    "the process exited zero, but the input it was to act on "
                    "was never delivered whole, so the zero answers a question "
                    "this build never finished asking")
            return "succeeded", _detail(outcome, "the process exited zero")
        return "failed", _detail(outcome, f"the process exited {outcome.exit_code}")
    if outcome.status == "timed_out":
        return "failed", _detail(
            outcome, "the process exceeded its timeout and was terminated")
    if outcome.status == "stopped":
        return "cancelled", _detail(outcome, "the process was stopped by the runner")
    raise AdapterContractError(f"unknown process status {outcome.status!r}")


class ProcessAdapter:
    """A minimal CMD-3 adapter that dispatches through the owned-process runner.

    It holds exactly two controls and says so: it can ``observe`` (honestly, and
    without probing the machine) and ``dispatch`` (run one structured command and
    report the result). It claims no pause, resume, stop, retry, switch, review,
    evidence, or independent verification -- those controls are absent from its
    manifest, never present-but-empty. ``verify`` returns ``unavailable`` because
    watching a process exit is not evidence that the requested effect occurred.
    """

    def __init__(self, adapter_id: str, runner: ProcessRunner, *,
                 clock: Callable[[], str], ids: Callable[[str], str],
                 display_name: str = "Owned Process",
                 vendor: str = "December Command", version: str = "1") -> None:
        self.manifest = AdapterManifest(
            adapter_id=adapter_id, display_name=display_name, vendor=vendor,
            version=version, capabilities=("observe", DISPATCH_CAPABILITY))
        self._runner = runner
        self._clock = clock
        self._ids = ids

    def observe(self, instance_id: str, run_id: str) -> AdapterObservation:
        return AdapterObservation(
            adapter_id=self.manifest.adapter_id, instance_id=instance_id,
            run_id=run_id, observed_at=self._clock(), health="unknown",
            available_capabilities=(),
            detail="the owned-process adapter does not probe; liveness is unknown "
                   "until a dispatch runs")

    def prepare(self, request: ActionRequest) -> PreparedAction:
        if not isinstance(request, ActionRequest):
            raise AdapterContractError("request must be a validated ActionRequest")
        if request.capability != DISPATCH_CAPABILITY:
            raise UnsupportedCapability(
                f"the owned-process adapter only prepares {DISPATCH_CAPABILITY!r}, "
                f"not {request.capability!r}")
        spec = _spec_from_arguments(request.arguments, request.timeout_seconds)
        return PreparedAction(
            adapter_id=self.manifest.adapter_id, request=request,
            adapter_payload=_payload_from_spec(spec))

    def execute(self, prepared: PreparedAction) -> ActionResultReceipt:
        if not isinstance(prepared, PreparedAction):
            raise AdapterContractError("prepared must be a validated PreparedAction")
        request = prepared.request
        spec = _spec_from_payload(prepared.adapter_payload, request.timeout_seconds)
        outcome = self._runner.run(spec)
        mapped, detail = _map_outcome(outcome)
        return ActionResultReceipt(
            receipt_id=self._ids("receipt"), action_id=request.action_id,
            run_id=request.run_id, attempt_id=request.attempt_id,
            instance_id=request.instance_id, outcome=mapped,
            observed_at=self._clock(), detail=detail, exit_code=outcome.exit_code)

    def verify(
            self, request: ActionRequest, result: ActionResultReceipt,
    ) -> AdapterVerification:
        if not isinstance(request, ActionRequest) or not isinstance(
                result, ActionResultReceipt):
            raise AdapterContractError("verify needs a validated request and result")
        return AdapterVerification(
            adapter_id=self.manifest.adapter_id, action_id=request.action_id,
            state="unavailable", observed_at=self._clock(),
            detail="the owned-process adapter observes the process outcome only; it "
                   "holds no independent check of the requested effect",
            evidence_refs=())
    argument_schemas = {DISPATCH_CAPABILITY: "structured-process-v1"}
