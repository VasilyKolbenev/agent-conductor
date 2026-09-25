"""Local namespace admission usable by init without loading process ownership."""
from pathlib import Path

from .ownership_errors import OwnerRefused


def _present(path):
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def init_target(project_root):
    root = Path(project_root).resolve()
    if _present(root / ".conduct") or _present(root / "conductor.v3"):
        raise OwnerRefused("activation_present", "finish explicit ownership maintenance before init")
    return Path(project_root) / "conductor"


def read_data_root(project_root):
    root = Path(project_root).resolve()
    if not _present(root / ".conduct") and not _present(root / "conductor.v3"):
        return Path(project_root) / "conductor"
    from .ownership import data_root
    return data_root(root)
