"""The terminal's one ordered door for admitting an existing local folder (spec 8.2)."""
from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import Callable

from conductor import init, ownership, ownership_records, ownership_transition, provider_profile
from conductor import tool_env, tool_pins
from conductor.command import operator_config, path_admission, project_git, product_names
from conductor.command.adapters.process import ProcessRunner
from conductor.hub import home, registry

STEPS = ("admit", "git", "init", "activate", "providers", "exclude", "instructions", "register")
REFUSAL_CODES = frozenset({
    "root_invalid", "root_too_broad", "root_nested", "root_in_login_home",
    "root_already_registered", "root_path_too_long", "windows_name_unsafe",
    "conduct_home_invalid", "name_invalid", "git_not_pinned", "git_changed",
    "git_too_old", "tool_version_unreadable", "project_not_repo_root",
    "tracks_product_dir", "legacy_writers_must_stop", "unsettled_action",
    "recovery_required", "transition_conflict", "activation_present",
    "inventory_bound", "owner_busy", "ownership_lost", "git_exclude_failed",
    "ports_exhausted", "registry_busy", "registry_invalid", "subprocess_failed",
    "repo_invalid",
})


class AddRefused(Exception):
    def __init__(self, code: str, detail: str) -> None:
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}")


def _refuse(code: str, detail: object) -> None:
    raise AddRefused(code if code in REFUSAL_CODES else "subprocess_failed", str(detail))


def _same_or_beneath(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _plain_route(path: Path) -> None:
    """Judge each original path component before resolve can erase a link or junction."""
    for part in (path, *path.parents):
        found = os.lstat(part)
        if not stat.S_ISDIR(found.st_mode) or stat.S_ISLNK(found.st_mode) or (
                getattr(found, "st_reparse_tag", 0)):
            _refuse("root_invalid", f"{part} is not a plain directory")


def _ownership_state(root: Path):
    """Preserve a verified interrupted activation for the explicit resume step."""
    try:
        return ownership_records.state(root)
    except ownership_records.OwnerRefused as error:
        if error.code != "recovery_required":
            raise
        head = ownership_records.chain(root)
        if head["phase"] not in {"prepared", "moved"}:
            raise
        return root, head


def _admit(raw: str, name: str | None, folder: Path) -> tuple[Path, registry.Registry]:
    if not os.path.isabs(raw):
        _refuse("root_invalid", "--dir must be an absolute plain directory")
    root = Path(raw)
    try:
        _plain_route(root)
        root = root.resolve(strict=True)
    except (OSError, ownership_records.OwnerRefused) as error:
        _refuse("root_invalid", error)
    if name is not None:
        problem = registry.name_problem(name)
        if problem is not None:
            _refuse("name_invalid", problem)
    try:
        path_admission.admit_name(root.name, "project folder")
    except path_admission.WindowsNameError as error:
        _refuse("windows_name_unsafe", error)
    if os.name == "nt" and len(str(root).encode("utf-16-le")) // 2 > 100:
        _refuse("root_path_too_long", root)
    try:
        home.require_placement(folder)
        current = registry.load(folder)
    except (home.ConductHomeInvalid, home.ConductHomeOverlapsLogin) as error:
        _refuse("conduct_home_invalid", error)
    prior = current.find_root(str(root), ownership_records.identity(root))
    if prior is not None:
        try:
            _existing_root, existing_head = _ownership_state(root)
        except ownership_records.OwnerRefused as error:
            _refuse("root_already_registered", error)
        if existing_head is None or existing_head["nonce"] != prior.project_id:
            _refuse("root_already_registered", str(root))
    from conductor.hub.service import DEFAULT_PROJECTS_HOME
    broad = (Path(root.anchor), Path.home().resolve(), folder.resolve(),
             (Path.home() / DEFAULT_PROJECTS_HOME).resolve())
    if any(_same_or_beneath(place, root) for place in broad):
        _refuse("root_too_broad", root)
    if current.projects_home is not None and root == Path(current.projects_home).resolve():
        _refuse("root_too_broad", root)
    for project in current.projects:
        other = Path(project.root).resolve()
        if _same_or_beneath(root, other) or _same_or_beneath(other, root):
            if root != other:
                _refuse("root_nested", f"{root} overlaps {other}")
            # A repeated root is checked against its nonce after activation.
    for parent in root.parents:
        if any(os.path.lexists(parent / marker) for marker in home.PROJECT_MARKERS):
            _refuse("root_nested", f"{root} is inside {parent}")
    def unreadable(error: OSError) -> None:
        _refuse("root_invalid", f"cannot inspect {error.filename}: {error}")

    for walk, dirs, _files in os.walk(root, followlinks=False, onerror=unreadable):
        here = Path(walk)
        if here != root and any(os.path.lexists(here / marker) for marker in home.PROJECT_MARKERS):
            _refuse("root_nested", f"{root} contains {here}")
        kept = []
        for part in dirs:
            item = Path(walk) / part
            try:
                info = os.lstat(item)
            except OSError as error:
                _refuse("root_invalid", error)
            if not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_reparse_tag", 0):
                kept.append(part)
        dirs[:] = kept
    try:
        logins = _login_homes(current)
    except (home.ConductHomeInvalid, home.ConductHomeOverlapsLogin) as error:
        _refuse("conduct_home_invalid", error)
    for login in logins:
        if _same_or_beneath(root, login) or _same_or_beneath(login, root):
            _refuse("root_in_login_home", f"{root} overlaps {login}")
    return root, current


def _login_homes(current: registry.Registry) -> tuple[Path, ...]:
    try:
        profile = provider_profile.profile_path()
    except operator_config.OperatorConfigError as error:
        _refuse("conduct_home_invalid", error)
    paths = [(profile, False)]
    for project in current.projects:
        data = Path(project.root) / "conductor.v3"
        if not data.is_dir():
            data = Path(project.root) / "conductor"
        paths.append((data / "providers.json", True))
    found: list[Path] = []
    for path, registered in paths:
        try:
            found.extend(Path(row.auth_home).resolve() for row in
                         operator_config.load_provider_configs(path) if row.auth_home)
        except operator_config.OperatorConfigError as error:
            if registered:
                _refuse("root_in_login_home", f"cannot establish login homes from {path}: {error}")
            # A malformed optional shared profile is reported at the providers step.
    return tuple(found)


def _git(root: Path, folder: Path) -> project_git.RepositoryAdmission:
    if not project_git.has_git_entry(root):
        return project_git.RepositoryAdmission("not_git")
    pin = tool_pins.verify_pin("git", folder=folder)
    pins = tool_pins.load_pins(folder)
    environment = tool_env.tool_env(os.environ, pins, folder)
    # The requested cwd is strictly beneath this runner's root, without creating a folder.
    runner = ProcessRunner(root.parent, environ=environment)
    reader = project_git.process_git_read(runner, pin.path, str(root), env=environment)
    answer = project_git.repository_admission(root, reader)
    if answer.refusal is not None:
        _refuse(answer.refusal, ", ".join(answer.tracked) or root)
    if answer.state == "unsafe_directory":
        _refuse("git_failed", "git refused this directory's ownership")
    return answer


def _providers(root: Path) -> str:
    destination = ownership.data_root(root) / "providers.json"
    if destination.exists():
        return "kept"
    try:
        profile = provider_profile.profile_path()
        if not profile.exists():
            return "absent"
        provider_profile.open_profile()
    except operator_config.OperatorConfigError:
        return "profile_invalid"
    try:
        with ownership.acquire_owner(root):
            provider_profile.apply_profile(root)
    except ownership_records.OwnerRefused as error:
        if error.code == "owner_busy":
            return "deferred"
        raise
    except operator_config.OperatorConfigError:
        return "profile_invalid"
    return "copied"


def _instructions(root: Path) -> list[str]:
    found = []
    for entry in product_names.AGENT_INSTRUCTION_NAMES:
        name = entry.rstrip("/")
        if os.path.lexists(root / name):
            found.append(entry)
    return found


def add_folder(raw: str, *, name: str | None = None, legacy_writers_stopped: bool = False,
               source: str = "folder", repo: str | None = None,
               progress: Callable[[str], None] = lambda _step: None) -> dict:
    """Admit, activate and register one folder; emit a step only after it completes."""
    try:
        if (source not in {"folder", "github", "scratch"}
                or (source == "github" and (type(repo) is not str or
                    re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}", repo) is None))
                or (source != "github" and repo is not None)):
            _refuse("repo_invalid", "source and repository must describe the added project")
        folder = home.conduct_home_path()
        root, current = _admit(raw, name, folder)
        progress("admit")
        git = _git(root, folder)
        progress("git")
        _root, head = _ownership_state(root)
        made = head is None and not (root / "conductor").exists()
        if made:
            init.scaffold_default(root)
        progress("init")
        if head is None or head["phase"] in {"rolled_back", "prepared", "moved"}:
            if not legacy_writers_stopped:
                _refuse("legacy_writers_must_stop", "explicitly stop legacy writers before activation")
            head = (ownership_transition.resume_activation(root, legacy_writers_stopped=True)
                    if head is not None and head["phase"] in {"prepared", "moved"}
                    else ownership_transition.activate(root, legacy_writers_stopped=True))
            activated = "new"
        else:
            activated = "existing"
        progress("activate")
        providers = _providers(root)
        progress("providers")
        exclude = product_names.write_exclude_block(root / ".git") if git.state == "repo" else "not_git"
        progress("exclude")
        instructions = _instructions(root)
        progress("instructions")
        project_id = head["nonce"]
        prior = current.find_root(str(root), ownership_records.identity(root))
        if prior is not None and prior.project_id != project_id:
            _refuse("root_already_registered", str(root))
        project, registered = registry.add_project(project_id=project_id, root=str(root),
            root_identity=ownership_records.identity(root), source=source, repo=repo,
            name=name, folder=folder)
        progress("register")
        return {"project_id": project.project_id, "name": project.name, "root": project.root,
                "port": project.port, "registered": registered, "git": git.state,
                "activated": activated, "providers": providers, "exclude": exclude,
                "exclude_names": list(product_names.EXCLUDE_LINES) if git.state == "repo" else None,
                "agent_instructions": instructions, "folder": root.name,
                "projects_home_created": False}
    except (registry.RegistryError, tool_pins.ToolPinError,
            ownership_records.OwnerRefused, product_names.ExcludeWriteError) as error:
        _refuse(error.code, getattr(error, "detail", str(error)))
    except project_git.GitReadFailed as error:
        _refuse(error.code, error.code)
    except (OSError, ValueError) as error:
        _refuse("subprocess_failed", error)
