"""Release identity must agree across the surfaces shipped to a user."""
from __future__ import annotations

import tomllib
from pathlib import Path

import conductor


ROOT = Path(__file__).resolve().parents[1]


def _project() -> dict[str, object]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]


def test_distribution_runtime_and_release_prose_name_the_same_version():
    project = _project()
    version = project["version"]
    assert version == conductor.__version__
    assert f"December Command v{version} alpha" in (
        ROOT / "README.md"
    ).read_text(encoding="utf-8")
    assert f"`{version}`" in (
        ROOT / "docs" / "release-smoke.md"
    ).read_text(encoding="utf-8")


def test_alpha_keeps_the_published_distribution_and_cli_names():
    project = _project()
    assert project["name"] == "agent-conductor"
    assert project["scripts"] == {"conduct": "conductor.__main__:main"}
