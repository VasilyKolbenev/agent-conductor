"""The shared provider profile and its explicit, configuration-only project copy."""
from __future__ import annotations

from pathlib import Path

from . import store
from .command import operator_config
from .hub import home


def profile_path(configs=()) -> Path:
    """Return the fixed profile path, refusing overlap with project or login data."""
    try:
        folder = home.conduct_home_path().resolve()
        home.require_placement(folder)
        for row in configs:
            if not row.auth_home:
                continue
            login = Path(row.auth_home).resolve()
            if folder.is_relative_to(login):
                raise operator_config.OperatorConfigError(
                    "conduct_home_overlaps_login: the profile home lies in a login directory")
            if login.is_relative_to(folder):
                raise operator_config.OperatorConfigError(
                    "login_home_in_conduct_home: login data must remain outside the profile home")
        return folder / operator_config.PROVIDER_CONFIG_FILENAME
    except (OSError, ValueError) as error:
        raise operator_config.OperatorConfigError(f"conduct_home_invalid: {error}") from None


def open_profile():
    path = profile_path()
    try:
        rows = operator_config.load_provider_configs(path)
        profile_path(rows)
        return path, rows
    except operator_config.OperatorConfigError as error:
        raise operator_config.OperatorConfigError(f"profile_invalid: {error}") from None


def apply_profile(directory: str | Path) -> Path:
    """Replace matching provider rows in one guarded atomic write; never copy login files."""
    path = profile_path()
    if not path.exists():
        raise operator_config.OperatorConfigError(f"profile_absent: {path}")
    _, incoming = open_profile()
    destination = operator_config.provider_config_path(store.conductor_dir(directory))
    standing = operator_config.load_provider_configs(destination)
    replacements = {row.provider_id: row for row in incoming}
    merged = [replacements.pop(row.provider_id, row) for row in standing]
    merged.extend(replacements.values())
    profile_path(merged)
    return operator_config.save_provider_configs(destination, merged, project_root=directory)
