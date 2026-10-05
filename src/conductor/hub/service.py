"""The answers of the hub's routes, apart from the socket (spec 4.6.3, 4.6.4).

`HubService` is what an HTTP shell asks: the three reads (`projects`, `limits`, `setup`) in the
forms of 4.6.4, and the writes that change which project is active or open (`activate`, `view`,
`stop`, `forget`, `queue_order`). A write answers at once with the status of 4.6.3 and its progress
is in `state`, `working` and `state_code` of the row; every refusal is a `HubRefusal` of the closed
list, raised BEFORE anything is written, so a refused move leaves `hub-state.json` as it was.

It holds no socket and no thread. `tick()` is the pass the hub's loop makes once a second: the
supervisor's, then the reader's, then the frames for whatever changed (the page reads again on a
frame). Everything about a child comes from `ChildReader` and the supervisor; the service adds the
two facts neither knows, whether a project's folder is still the folder that was listed, and the
setup of the hub itself.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from conductor import ownership_native, ownership_records, tool_pins
from conductor.command import project_git, operator_config, providers
from conductor.hub import (
    clone, dialogs, events, github, instance, job, lifecycle, operations, reader, refusals, registry, snapshots, state, summary,
    supervisor, project_targets)
from conductor.hub.refusals import HubRefusal

DEFAULT_PROJECTS_HOME = "ConductProjects"
PROFILE_FILE = "providers.json"
_INSTANT = "%Y-%m-%dT%H:%M:%SZ"
_ID = re.compile(r"[0-9a-f]{32}")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_ALIVE = ("starting", "running", "stopping", "stop_overdue")
_UNRECOVERED = ("recovery_required", "stop_uncertain")
_TOOLS = ("gh", "git")
_RECOVER_CLONES = ("to finish them, stop the hub, then run: conduct ownership recover-clones "
                   "(run it with --prepare-restart first when it says a preparation is needed)")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime(_INSTANT)


def _tell(lines: list[str]) -> None:
    """Write what stays unfinished at start to the hub's stderr, then the way to finish it.

    The page has only the closed row of `GET /hub/setup`, so the sentence that names the next
    action reaches a person here, and the banner points at the command.
    """
    for line in lines:
        print("conduct hub: " + " ".join(line.split()), file=sys.stderr)
    if lines:
        print("conduct hub: " + _RECOVER_CLONES, file=sys.stderr, flush=True)


class HubService:
    """The hub's routes, answered."""

    def __init__(self, home: Path | str, sup: supervisor.Supervisor, store: state.HubStateStore,
                 snapshot_store: snapshots.SnapshotStore, child_reader: reader.ChildReader,
                 ledger: summary.ObservedLedger, bus: events.EventBus, *,
                 now: Callable[[], datetime] = _utc_now,
                 verify_tool: Callable[..., tool_pins.ToolPin] = tool_pins.verify_pin,
                 job_policy: Callable[[], str] = job.own_policy,
                 folder_ok: Callable[[registry.Project], bool] | None = None,
                 pick_resolver: Callable[[str], operations.FolderPick | None] | None = None,
                 operation_popen=None, dialog_popen=None) -> None:
        self._home = Path(home)
        self._sup, self._store, self._snapshots = sup, store, snapshot_store
        self._reader, self._ledger, self._bus = child_reader, ledger, bus
        self._now, self._verify_tool, self._job_policy = now, verify_tool, job_policy
        self._folder_ok = folder_ok or _folder_is_the_listed_one
        self._verified: dict[str, tuple[tool_pins.ToolPin, str]] = {}
        self._last_projects: str | None = None
        self._last_setup: dict[str, Any] | None = None
        self._add_lock = threading.RLock()
        self._github = github.Github(self._home)
        self._clones = clone.Clones(self._home)
        self._clone_recovery: tuple[str | None, ...] = ()
        dialog_options = {} if dialog_popen is None else {"popen": dialog_popen}
        self._dialogs = dialogs.Dialogs(self._home, bus, **dialog_options)
        self._pick_resolver = pick_resolver or self._dialogs.resolve
        self._consume_pick = self._dialogs.consume if pick_resolver is None else lambda _ident: None
        options = {} if operation_popen is None else {"popen": operation_popen}
        self._operations = operations.Operations(self._home, bus, start=self._start_added,
            status=self._added_status, clone_cancel=self._clones.cancel, **options)

    def start(self) -> None:
        """Seed the ledger of first-seen moments from the snapshots the last hub left."""
        try:
            self._clone_recovery = self._clones.recover()
            said = [f"clone attempt {ident} is unfinished: {self._clones.unfinished[ident]}"
                    for ident in self._clone_recovery]
        except clone.CloneFailed as error:
            self._clone_recovery = (None,)
            said = ["the clone attempts cannot be read: "
                    + (" ".join(error.stderr) or "a record cannot be read")]
        _tell(said)
        try:
            listed = registry.load(self._home).projects
        except registry.RegistryError:
            return
        for project in listed:
            snap = self._snapshots.get(project.project_id)
            if snap is not None:
                self._ledger.seed(project.project_id, snap.tasks)

    def tick(self) -> None:
        """One pass of the hub's loop: the supervisor, the reader, then the frames for changes."""
        self._sup.tick()
        self._reader.step()
        self._announce_changes()

    # -- the reads ---------------------------------------------------------------------------------

    def projects(self) -> dict[str, Any]:
        """`GET /hub/projects` (4.6.4), with `unlisted_closing` (a closing entry off the list)."""
        listed = self._registry()
        current = self._state()
        rows = [self._row(project, current) for project in listed.projects]
        return {"computed_at": _iso(self._now()), "active_project_id": current.active_project_id,
                "project_queue": list(current.queue),
                "projects_home": self._projects_home(listed.projects_home), "projects": rows,
                "unlisted_closing": [
                    {"project_id": one.project_id, "since": one.since, "action": one.action}
                    for one in self._sup.unlisted_closing()]}

    def limits(self) -> dict[str, Any]:
        """`GET /hub/limits`: the active project's live read, else `limits.json`, else nothing."""
        active = self._state().active_project_id
        live = None if active is None else self._reader.live(active)
        return summary.limits_response(_iso(self._now()), active_project_id=active, live=live,
                                       stored=self._snapshots.get_limits())

    def setup(self) -> dict[str, Any]:
        """`GET /hub/setup`: the profile, `<projects-home>`, the pins, and the hub's own job.

        `logins` is empty until the profile is read (a later slice): the boxes of the logins are
        found from the profile and the registered projects' `providers.json`.
        """
        try:
            home_value = registry.load(self._home).projects_home
        except registry.RegistryError:
            home_value = None
        return {"profile": self._profile(),
                "projects_home": {**self._projects_home(home_value),
                                  "default_name": DEFAULT_PROJECTS_HOME},
                "tools": {tool: self._tool(tool) for tool in _TOOLS}, "logins": [],
                "hub_job": self._job_policy(),
                "clone_recovery": [{"operation_id": ident, "code": "clone_cleanup_incomplete"}
                                   for ident in self._clone_recovery]}

    def operation(self, operation_id: str) -> dict[str, Any]:
        """The latest state of one bounded in-memory add operation."""
        return self._operations.get(operation_id)

    def github_status(self):
        return self._github.status()

    def github_repos(self, owner=None):
        return self._github.repositories(owner)

    def folder_dialog(self, body: dict[str, Any]) -> tuple[int, dict[str, str]]:
        return 202, {"pick_id": self._dialogs.begin(body["purpose"])}

    def dialog(self, pick_id: str) -> dict[str, Any]:
        return self._dialogs.get(pick_id)

    def cancel_dialog(self, pick_id: str) -> tuple[int, dict[str, str]]:
        self._dialogs.cancel(pick_id)
        return 200, {"pick_id": pick_id, "state": "cancelled"}

    def close_dialog(self) -> None:
        self._dialogs.close()

    def close_operations(self) -> bool:
        return self._operations.close_clones()

    def add_project(self, body: dict[str, Any]) -> tuple[int, dict[str, str]]:
        """Accept only a trusted folder pick; the browser cannot name a filesystem path."""
        with self._add_lock:
            return self._add_project(body)

    def _add_project(self, body: dict[str, Any]) -> tuple[int, dict[str, str]]:
        if type(body["source"]) is not str or body["source"] not in {"folder", "github", "scratch"}:
            raise HubRefusal("contract_invalid")
        if body["source"] == "scratch":
            return self._scratch_project(body)
        if body["source"] == "github":
            return self._github_project(body)
        if body["source"] != "folder":
            raise HubRefusal("route_not_found", {"reason": "source not in this build"})
        if set(body) != {"source", "pick_id", "name", "legacy_writers_stopped"}:
            raise HubRefusal("contract_invalid")
        if (not isinstance(body["pick_id"], str)
                or re.fullmatch(r"pick-[0-9a-f]{32}", body["pick_id"]) is None
                or type(body["legacy_writers_stopped"]) is not bool):
            raise HubRefusal("contract_invalid")
        pick = self._pick_resolver(body["pick_id"])
        if pick is None or pick.project not in {"none", "legacy", "activated"}:
            raise HubRefusal("pick_invalid")
        problem = registry.name_problem(body["name"])
        if problem is not None:
            raise HubRefusal("name_invalid", {"reason": problem})
        path = Path(pick.path)
        if not path.is_absolute():
            raise HubRefusal("pick_invalid")
        legacy = (os.path.lexists(path / "conductor") and not os.path.lexists(path / ".conduct")
                  and not os.path.lexists(path / "conductor.v3"))
        if os.path.lexists(path / ".conduct"):
            try:
                legacy = ownership_records.chain(path)["phase"] in {"prepared", "moved", "rolled_back"}
            except (ownership_records.OwnerRefused, OSError):
                pass  # The CLI's admit/activate step owns the precise refusal.
        if legacy and body["legacy_writers_stopped"] is not True:
            raise HubRefusal("legacy_writers_unconfirmed")
        if project_git.has_git_entry(path):
            tool = self._tool("git")["state"]
            code = {"not_pinned": "git_not_pinned", "changed": "git_changed",
                    "too_old": "git_too_old", "unreadable": "tool_version_unreadable"}.get(tool)
            if code is not None:
                raise HubRefusal(code)
        confirmed = body["legacy_writers_stopped"] is True or not legacy
        ident = self._operations.begin(pick, body["name"], confirmed)
        self._consume_pick(body["pick_id"])
        return 202, {"operation_id": ident}

    def _github_project(self, body):
        if set(body) != {"source", "repo", "folder", "name"}:
            raise HubRefusal("contract_invalid")
        if type(body["repo"]) is not str or clone.REPO.fullmatch(body["repo"]) is None:
            raise HubRefusal("repo_invalid")
        problem = registry.name_problem(body["name"])
        if problem is not None:
            raise HubRefusal("name_invalid", {"reason": problem})
        admitted = project_targets.ticket(self._home, body["folder"])
        git_state = self._tool("git")["state"]
        git_code = {"not_pinned": "git_not_pinned", "changed": "git_changed",
                    "too_old": "git_too_old", "unreadable": "tool_version_unreadable"}.get(git_state)
        if git_code:
            raise HubRefusal(git_code)
        gh_state = self._tool("gh")["state"]
        gh_code = {"not_pinned": "gh_not_pinned", "changed": "gh_changed",
                   "unreadable": "gh_changed"}.get(gh_state)
        if gh_code:
            raise HubRefusal(gh_code)
        repo = body["repo"]
        ident = self._operations.begin(operations.FolderPick(str(admitted.path), "none"),
            body["name"], True, source="github", repo=repo,
            prepare=lambda ident: self._clones.clone(ident, repo, admitted))
        return 202, {"operation_id": ident}

    def cancel_operation(self, operation_id: str):
        self._operations.cancel(operation_id)
        return 202, {"operation_id": operation_id}

    def projects_home(self, body):
        if set(body) == {"default"} and body["default"] is True:
            value = None
        elif set(body) == {"pick_id"} and type(body["pick_id"]) is str:
            selected = self._dialogs.resolve_home(body["pick_id"])
            if selected is None:
                raise HubRefusal("pick_invalid")
            value = str(project_targets.admit_home(selected, self._home))
        else:
            raise HubRefusal("contract_invalid")
        try:
            self._operations.configure_parent(lambda: registry.set_projects_home(value, self._home))
        except registry.RegistryError as error:
            raise HubRefusal("registry_invalid") from error
        if value is not None:
            self._dialogs.consume(body["pick_id"])
        self._bus.publish("setup")
        return 200, {"projects_home": self._projects_home(value)}

    def _scratch_project(self, body):
        if set(body) != {"source", "folder", "name"}:
            raise HubRefusal("contract_invalid")
        problem = registry.name_problem(body["name"])
        if problem is not None:
            raise HubRefusal("name_invalid", {"reason": problem})
        admitted = project_targets.ticket(self._home, body["folder"])
        state = self._tool("git")["state"]
        code = {"not_pinned": "git_not_pinned", "changed": "git_changed",
                "too_old": "git_too_old", "unreadable": "tool_version_unreadable"}.get(state)
        if code:
            raise HubRefusal(code)
        try:
            configs = operator_config.load_provider_configs(self._home / PROFILE_FILE)
        except operator_config.OperatorConfigError:
            configs = ()
        if not any(row.provider_id in providers.PROVIDER_CATALOG
                   and "review" in providers.PROVIDER_CATALOG[row.provider_id].capabilities
                   and row.protocol == providers.PROVIDER_CATALOG[row.provider_id].protocol
                   for row in configs):
            raise HubRefusal("review_harness_missing")
        ident = self._operations.begin(operations.FolderPick(str(admitted.path), "none"),
            body["name"], True, source="scratch",
            prepare=lambda: project_targets.create(self._home, body["folder"], expected=admitted))
        return 202, {"operation_id": ident}

    def _start_added(self, project_id: str) -> None:
        if self._state().active_project_id is None:
            self.activate(project_id)
        else:
            self.view(project_id)

    def _added_status(self, project_id: str) -> tuple[str, str | None]:
        project = self._require(project_id)
        status = self._status(project).lifecycle
        return status.state, status.state_code

    # -- the writes --------------------------------------------------------------------------------

    def activate(self, project_id: str) -> tuple[int, dict[str, Any]]:
        """`POST .../activate`: make a project the active one; the old one drains first (4.1.7)."""
        project = self._require(project_id)
        status = self._status(project)
        self._require_usable(status, project_id)
        current = self._state()
        if current.active_project_id == project_id and status.lifecycle.state in _ALIVE:
            raise HubRefusal("already_active", {"project_id": project_id})
        self._require_the_active_can_yield(current, project_id)
        self._move(lambda: self._sup.activate(project_id, flag=self._flag_of(project_id)),
                   project_id)
        return 202, {"project_id": project_id, "working": "active"}

    def view(self, project_id: str) -> tuple[int, dict[str, Any]]:
        """`POST .../view`: open a project for viewing; a view child starts nothing itself."""
        project = self._require(project_id)
        status = self._status(project)
        self._require_usable(status, project_id)
        if self._state().active_project_id == project_id:
            raise HubRefusal("already_active", {"project_id": project_id})
        self._move(lambda: self._sup.view(project_id), project_id)
        return 202, {"project_id": project_id, "working": "view"}

    def stop(self, project_id: str) -> tuple[int, dict[str, Any]]:
        """`POST .../stop`: drain a project's child on its checkpoint; the queue may move on."""
        self._require(project_id)
        current = self._state()
        following = None
        if current.active_project_id == project_id:
            following = next((p for p in current.queue if p != project_id), None)
        flag = None if following is None else self._flag_of(following)
        self._move(lambda: self._sup.stop(project_id, next_flag=flag), project_id)
        return 202, {"project_id": project_id, "state": "stopping"}

    def forget(self, project_id: str) -> tuple[int, dict[str, Any]]:
        """`POST .../forget`: take a project off the list; its files are not touched."""
        self._require(project_id)
        self._move(lambda: self._sup.forget(project_id), project_id)
        return 200, {"project_id": project_id}

    def queue_order(self, order: object) -> tuple[int, dict[str, Any]]:
        """`POST /hub/queue/order`: reorder the queue; anything but a permutation writes nothing."""
        if not isinstance(order, list) or not all(
                isinstance(one, str) and _ID.fullmatch(one) for one in order):
            raise HubRefusal("contract_invalid", {"reason": "order is a list of project ids"})
        try:
            written = self._store.update(lambda s: state.reorder(s, order))
        except state.TransitionRefused as refused:
            raise HubRefusal("project_queue_changed") from refused
        except (state.HubStateError, instance.HubLockLost) as failure:
            raise HubRefusal("registry_invalid", {"file": "hub-state.json"}) from failure
        self._bus.publish("projects")
        return 200, {"project_queue": list(written.queue)}

    # -- looking -----------------------------------------------------------------------------------

    def _registry(self) -> registry.Registry:
        try:
            return registry.load(self._home)
        except registry.RegistryError as error:
            raise HubRefusal("registry_invalid", {"file": registry.FILE_NAME}) from error

    def _state(self) -> state.HubState:
        try:
            return self._store.load()
        except state.HubStateError as error:
            raise HubRefusal("registry_invalid", {"file": state.FILE_NAME}) from error

    def _require(self, project_id: str) -> registry.Project:
        found = self._registry().project(project_id)
        if found is None:
            raise HubRefusal("project_not_found", {"project_id": project_id})
        return found

    def _supervised(self, project_id: str) -> supervisor.ProjectStatus:
        """The supervisor's status of a project; its read of `hub-state.json` refuses in words."""
        try:
            return self._sup.status(project_id)
        except state.HubStateError as error:
            raise HubRefusal("registry_invalid", {"file": state.FILE_NAME}) from error

    def _status(self, project: registry.Project) -> supervisor.ProjectStatus:
        try:
            status = self._supervised(project.project_id)
        except supervisor.SupervisorRefused as refused:
            raise HubRefusal("project_not_found", {"project_id": project.project_id}) from refused
        if status.port is None and not self._folder_ok(project):
            return replace(status, lifecycle=lifecycle.Lifecycle("missing"))
        return status

    def _row(self, project: registry.Project, current: state.HubState) -> dict[str, Any]:
        status = self._status(project)
        live = self._reader.live(project.project_id)
        usable = live is not None and live.cycle.verdict in ("live", *summary.STOPPING_VERDICTS)
        snap = None if usable else self._snapshots.get(project.project_id)
        return summary.project_row(project, status, queue=current.queue, live=live, snapshot=snap)

    @staticmethod
    def _projects_home(value: str | None) -> dict[str, Any]:
        if value is None:
            return {"state": "default", "name": DEFAULT_PROJECTS_HOME}
        folder = Path(value)
        return {"state": "chosen" if folder.is_dir() else "invalid",
                "name": Path(value.replace("\\", "/")).name or None}

    def _profile(self) -> str:
        path = self._home / PROFILE_FILE
        if not path.exists():
            return "absent"
        try:
            if path.stat().st_size > registry.MAX_BYTES:
                return "invalid"
            return "present" if isinstance(json.loads(path.read_bytes().decode("utf-8")),
                                           dict) else "invalid"
        except (OSError, ValueError):
            return "invalid"

    def _tool(self, tool: str) -> dict[str, Any]:
        try:
            pin = tool_pins.read_pin(tool, self._home)
        except tool_pins.ToolPinError:
            return _tool_entry("unreadable", None)
        if pin is None:
            return _tool_entry("not_pinned", None)
        held = self._verified.get(tool)
        if held is None or held[0] != pin:
            held = (pin, self._verified_state(tool))
            self._verified[tool] = held
        return _tool_entry(held[1], pin)

    def _verified_state(self, tool: str) -> str:
        try:
            self._verify_tool(tool, folder=self._home)
        except tool_pins.ToolPinError as error:
            return {f"{tool}_changed": "changed", "git_too_old": "too_old"}.get(
                error.code, "unreadable")
        return "pinned"

    # -- refusing before writing ---------------------------------------------------------------

    def _require_usable(self, status: supervisor.ProjectStatus, project_id: str) -> None:
        found = status.lifecycle.state
        if found in ("identity_mismatch", "missing"):
            raise HubRefusal("project_unavailable", {"project_id": project_id})
        if found in _UNRECOVERED:
            raise HubRefusal("recovery_required", {"project_id": project_id})

    def _require_the_active_can_yield(self, current: state.HubState, project_id: str) -> None:
        active = current.active_project_id
        if active is None or active == project_id:
            return
        try:
            held = self._supervised(active).lifecycle.state
        except supervisor.SupervisorRefused:
            return                          # left the list: its closing entry blocks by itself
        if held in _UNRECOVERED:
            raise HubRefusal("active_not_closed", {"project_id": active})

    def _flag_of(self, project_id: str) -> state.Flag | None:
        """The flag of a project as the hub read it: live if it runs, else its snapshot."""
        live = self._reader.live(project_id)
        flag = live.cycle.auto_continue if live is not None and live.cycle.verdict == "live" \
            else None
        if flag is None:
            snap = self._snapshots.get(project_id)
            flag = None if snap is None else snap.auto_continue
        if not (isinstance(flag, dict) and flag.get("enabled") is True
                and flag.get("consumed") is None):
            return None
        flag_id, revision = flag.get("flag_id"), flag.get("revision")
        if isinstance(flag_id, str) and _UUID.fullmatch(flag_id) and type(revision) is int \
                and revision >= 1:
            return state.Flag(flag_id, revision)
        return None

    def _move(self, act: Callable[[], object], project_id: str) -> None:
        """Carry out a move of the supervisor; its refusals become the closed list's."""
        try:
            act()
        except supervisor.SupervisorRefused as refused:
            raise HubRefusal(refused.code, {"project_id": project_id}) from refused
        except state.TransitionRefused as refused:
            raise HubRefusal(refused.reason if refused.reason in refusals.HUB_ERROR_STATUS
                             else "project_busy", {"project_id": project_id}) from refused
        except (state.HubStateError, instance.HubLockLost) as failure:
            raise HubRefusal("registry_invalid", {"file": state.FILE_NAME}) from failure
        self._bus.publish("projects")

    # -- telling the page --------------------------------------------------------------------------

    def _announce_changes(self) -> None:
        """Publish `projects` and `setup` when what the page would read has changed."""
        try:
            signature = json.dumps(self._signature(), sort_keys=True, default=str)
        except HubRefusal:
            signature = "unreadable"
        if signature != self._last_projects:
            self._last_projects = signature
            self._bus.publish("projects")
        setup = self.setup()
        if self._last_setup is not None and setup != self._last_setup:
            self._bus.publish("setup")
        self._last_setup = setup

    def _signature(self) -> dict[str, Any]:
        listed, current = self._registry(), self._state()
        rows = []
        for project in listed.projects:
            status = self._status(project)
            rows.append([project.project_id, project.name, status.lifecycle.state,
                         status.lifecycle.state_code, status.working, status.mode, status.port,
                         status.instance, status.drain_deadline, status.stopped_at])
        return {"registry": registry.digest(self._home), "rows": rows,
                "active": current.active_project_id, "queue": list(current.queue),
                "closing": [entry.project_id for entry in current.closing]}



def _folder_is_the_listed_one(project: registry.Project) -> bool:
    """Whether the folder is still there and still the one that was listed (its identity)."""
    try:
        return tuple(ownership_native.identity(project.root)) == tuple(project.root_identity)
    except (OSError, ValueError):
        return False


def _tool_entry(found: str, pin: tool_pins.ToolPin | None) -> dict[str, Any]:
    display = None if pin is None else f"{Path(pin.path).parent.name}{os.sep}{Path(pin.path).name}"
    return {"state": found, "display": display, "version": None if pin is None else pin.version,
            "candidates": []}
