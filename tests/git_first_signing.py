"""The signed first commit as the owner makes it: a throwaway key and the two shown commands.

Nothing here is a real key. `signing_key` makes one in the test's own folder with the machine's
`ssh-keygen`, `signing_project` points the REPOSITORY configuration of that one project at it, and
the owner's commands run with the account's Git settings and agent out of sight. The commands are
composed from the typed detail of the refusal by the fixed template of the handoff, and run for
real; nothing about the product's own Git changes, which only ever reads on this road.
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.git_first_bench import confirm, project, terms_of
from tests.git_repo_helpers import GIT, ISOLATED, empty_home_environment

SSH_KEYGEN = shutil.which("ssh-keygen")
FORMATS = ["sha1", "sha256"]
COMMANDS = ("git commit-tree {tree} -S -F {message_path}",
            "git update-ref {target_ref} {oid} {zero}")


@pytest.fixture
def signing_key(tmp_path) -> Path:
    """A throwaway ed25519 key made in the test's folder: it never leaves it.

    The test is skipped, and the skip is reported, where the machine has no `ssh-keygen`."""
    if SSH_KEYGEN is None:
        pytest.skip("no ssh-keygen")
    key = tmp_path / "throwaway-key"
    made = subprocess.run([SSH_KEYGEN, "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
                          capture_output=True, check=False)
    assert made.returncode == 0, made.stderr.decode(errors="replace")
    return key


def signing_project(tmp_path, key: Path, files=None, **options):
    """A project whose repository requires signing, with `key` as the signing key."""
    folder = project(tmp_path, files, **options)
    for name, value in (("commit.gpgsign", "true"), ("gpg.format", "ssh"),
                        ("user.signingkey", key.as_posix()), ("gpg.ssh.program", SSH_KEYGEN)):
        folder.git("config", name, value, cwd=folder.root)
    return folder


def owner_environment() -> dict[str, str]:
    """The owner's terminal: the repository's own configuration only, and no agent to sign with."""
    return {**os.environ, **ISOLATED, **empty_home_environment(), "SSH_AUTH_SOCK": ""}


def command_lines(detail: dict, oid: str = "<oid>") -> list[str]:
    """The two commands, from the facts of the refusal alone and the fixed template."""
    return [line.format(tree=detail["tree"], message_path=detail["message_path"],
                        target_ref=detail["target_ref"], oid=oid, zero="0" * len(detail["tree"]))
            for line in COMMANDS]


def run_owner(folder, line: str, *, env=None, unsigned=False):
    """Run one shown command line in the project folder, with the current Git."""
    args = shlex.split(line, posix=True)
    assert args[0] == "git"
    if unsigned:
        args = [word for word in args if word != "-S"]
    return subprocess.run([GIT, *args[1:]], cwd=folder.root, capture_output=True, check=False,
                          env={**owner_environment(), **(env or {})})


def owner_makes_the_commit(folder, detail: dict, *, unsigned=False, publish=True, env=None):
    """The owner pastes both commands. Returns the object id `commit-tree` printed."""
    made = run_owner(folder, command_lines(detail)[0], unsigned=unsigned, env=env)
    assert made.returncode == 0, made.stderr.decode(errors="replace")
    oid = made.stdout.decode().strip()
    if publish:
        moved = run_owner(folder, command_lines(detail, oid)[1], env=env)
        assert moved.returncode == 0, moved.stderr.decode(errors="replace")
    return oid


def waits(folder, mode="snapshot", digest=None, actor="Owner") -> dict:
    """Confirm and return the typed detail of the signature wait the answer carries."""
    answer = confirm(folder, mode, digest=digest or terms_of(folder, mode), actor=actor)
    assert answer.status == 409, answer.payload
    assert answer.payload["error"]["code"] == "git_setup_refused"
    return answer.payload["error"]["detail"]
