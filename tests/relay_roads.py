"""A subscription harness on the RELAY road, driven end to end over fakes and a real login lease.

What is real here: the activated project and its live owner, the shared login lease of a login
home at `<tmp>/DecemberCommand/logins/x` (the lease of `ownership_login`, never replaced), the
product's transport, the owned-process runner under the fake boundary, and a real child process
(on Windows the current Python running the fixture, `tests/_fakeprocess.py`, so native PE startup
is not claimed). What is a double: the boundary entry of the runner
(`tests/_fakeboundary.py`), which confines nothing and records every call, and the vendor CLIs
(`tests/_fakeclaude.py`, `tests/_fakecodex.py`), which take their login from the folder they are
handed. Every credential is
the synthetic one of `tests/relay_credentials.py`; nothing is read from, or made in, the home of the
person who runs the tests.

The expected sentences, words and folders in the tests that use this are spelled in them by hand.
"""
from __future__ import annotations

import contextlib
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from conductor import ownership, ownership_login
from conductor import ownership_transition as transition
from conductor.command.adapters.process import ProcessRunner
from conductor.command.adapters.relay_home import relay_key, relay_root_for
from conductor.ownership_native import identity

from tests import _fakeclaude, _fakecodex
from tests import test_command_claude_transport as claude_t
from tests import test_command_codex_transport as codex_t
from tests._fakeboundary import confined
from tests.relay_credentials import claude_leaf, claude_profile, codex_leaf, epoch_seconds, jwt
from tests.relay_credentials import millis, put

#: The instant the product's clock names in these tests (`claude_t.NOW`).
CLOCK = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
LIFE = timedelta(hours=4)


@dataclass(frozen=True)
class Vendor:
    """What differs between the two relay harnesses, as the tests need it."""

    name: str
    module: object
    fake: object
    leaf: str
    home_row: str
    kind: str
    tool: str


CLAUDE = Vendor("claude-code", claude_t, _fakeclaude, ".credentials.json", "claude_home", "c",
                "Claude Code")
CODEX = Vendor("codex", codex_t, _fakecodex, "auth.json", "codex_home", "x", "Codex CLI")


def codex_access(life: timedelta = LIFE) -> str:
    """The access token (a JWT) of a Codex login that ends `life` after the product's clock."""
    return jwt({"sub": "fake-subject", "exp": epoch_seconds(CLOCK + life)})


def write_login(vendor: Vendor, login: Path, *, life: timedelta = LIFE, leaf=None, profile=None):
    """The files a vendor's own login would have written, with fake credentials, in `login`."""
    if vendor is CLAUDE:
        put(login, ".credentials.json",
            claude_leaf(expiresAt=millis(CLOCK + life)) if leaf is None else leaf)
        put(login, ".claude.json", claude_profile() if profile is None else profile)
    else:
        put(login, "auth.json",
            codex_leaf(access_token=codex_access(life)) if leaf is None else leaf)


def digests(folder: Path) -> dict[str, str]:
    """SHA-256 of every file under a folder, by its relative path: a snapshot to compare."""
    return {path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(folder.rglob("*")) if path.is_file()}


class Site:
    """An activated project, a real login home, a harness pinned to it and a recording boundary.

    `root`, when given, is a project an earlier `Site` already activated; `login`, a login home an
    earlier `Site` already wrote (a second project over the same login). `name` is the folder the
    harness is installed under and, unless `login` says otherwise, the login home is named after.
    """

    def __init__(self, base: Path, vendor: Vendor = CLAUDE, *, root: Path | None = None,
                 root_name: str = "root", login: Path | None = None, name: str = "x",
                 life: timedelta = LIFE, leaf=None, profile=None, activate: bool = True,
                 **knobs):
        self.vendor, self.base, self.activated = vendor, base, activate or root is not None
        if root is None:
            self.root = (base / root_name).resolve()
            (self.root / "conductor").mkdir(parents=True)
            if activate:
                transition.activate(self.root, legacy_writers_stopped=True)
        else:
            self.root = root
        self.login = (base / "DecemberCommand" / "logins" / name).resolve() if login is None \
            else login
        if login is None:
            write_login(vendor, self.login, life=life, leaf=leaf, profile=profile)
        #: A value too long and too particular to turn up in a frame the checker is shown, which
        #: is scanned for every value of the allowed environment.
        knobs = {vendor.fake.HOME_REPORT: "enabled-home-report", **knobs}
        self.adapter, _root, self.log = vendor.module.a_harness(
            base / f"harness-{name}", root=self.root, auth="subscription",
            auth_home=str(self.login), **knobs)
        self.runner = confined(self.adapter, base / f"scratch-{name}", platform="win32",
                               auth_homes=(self.login,))

    # -- where things are ----------------------------------------------------------------

    @property
    def relay_root(self) -> Path:
        return relay_root_for(self.login)

    @property
    def relay_dir(self) -> Path:
        return self.relay_root / relay_key(identity(self.root))

    @property
    def box(self) -> Path:
        return ownership_login.box_key(str(self.login))[1]

    def leftovers(self) -> list[str]:
        """The relay homes standing now, by name."""
        found = self.relay_dir
        return sorted(path.name for path in found.iterdir()) if found.is_dir() else []

    def leaf_path(self) -> Path:
        return self.login / self.vendor.leaf

    # -- driving it ------------------------------------------------------------------------

    @contextlib.contextmanager
    def owned(self):
        """The project's live owner, which the shared login lease needs (None: not activated)."""
        if not self.activated:
            yield None
            return
        with ownership.acquire_owner(self.root) as owner:
            yield owner

    def request(self, **options):
        return self.vendor.module.a_request(**options)

    def run(self, request=None):
        """One dispatch, as the runtime drives it: prepare, then execute; returns the receipt."""
        request = self.request() if request is None else request
        with self.owned():
            return self.vendor.module.run_once(self.adapter, request)

    # -- what the fake children saw ----------------------------------------------------------

    def rows(self) -> list[dict]:
        return self.vendor.fake.spawns(self.log)

    def tasks(self) -> list[dict]:
        fake = self.vendor.fake
        return fake.prompt_spawns(self.log) if self.vendor is CLAUDE else fake.task_spawns(self.log)

    def preflights(self) -> list[dict]:
        """The spawns that were questions (a version print, a login status), not tasks."""
        tasks = self.tasks()
        return [row for row in self.rows() if row not in tasks]

    def claimed(self, request) -> bool:
        return self.adapter._workspace.is_claimed(request.run_id, request.action_id)

    def lease_is_free(self) -> bool:
        """Whether the shared login lease can be taken now (a lease left uncertain refuses)."""
        with self.owned():
            with ProcessRunner.login_write_guard(self.root, str(self.login)):
                return True

    def closed_leases(self) -> list[str]:
        return sorted(path.name for path in self.box.glob("closed-*.json"))
