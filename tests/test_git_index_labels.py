"""The owned index carries a label per use; the first commit builds two of them per attempt."""
import os
import subprocess

import pytest

from conductor.command.accept_manifest import SnapshotRefused
from conductor.command.git_index import temporary_index
from tests.git_repo_helpers import GIT, ISOLATED, git, needs_git


def test_temporary_index_accepts_the_two_first_commit_labels_and_refuses_any_other_name(tmp_path):
    root = tmp_path.resolve()
    for label in ("first-" + "a" * 16 + "-a", "first-" + "b" * 16 + "-b"):
        with temporary_index(root, label, "sha1") as owned:
            assert owned.path.name.startswith(f"index-{label}-")
            assert owned.path.read_bytes().startswith(b"DIRC")
        assert not owned.path.exists()
    for label in ("first-" + "a" * 16, "first-" + "a" * 16 + "-c", "first-xyz-a", "acc-short",
                  "../x", "first-" + "A" * 16 + "-a", "first-" + "a" * 16 + "-a\n", ""):
        with pytest.raises(SnapshotRefused):
            with temporary_index(root, label, "sha1"):
                pass


@needs_git
@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_a_first_commit_label_index_is_an_empty_index_git_accepts_in_both_object_formats(
        tmp_path, fmt):
    repo = tmp_path / "r"
    repo.mkdir()
    if git("init", "-q", f"--object-format={fmt}", cwd=repo, check=False).returncode != 0:
        pytest.skip("this git cannot make a sha256 repository")
    with temporary_index(repo.resolve(), "first-" + "c" * 16 + "-a", fmt) as owned:
        listed = subprocess.run([GIT, "ls-files", "--stage"], cwd=repo, capture_output=True,
                                env={**os.environ, **ISOLATED, "GIT_INDEX_FILE": str(owned.path)})
    assert listed.returncode == 0 and listed.stdout == b""
