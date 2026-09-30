"""The Seatbelt profile the macOS checks run under: what its text says, on any POSIX host.

The profile is plain text, so its shape can be judged without macOS: writes are denied
everywhere first, allowed only in the directories the attempt owns, denied again for the
protected paths AFTER the allow that would otherwise cover them (a later rule wins), and
a directory that holds a protected entry cannot itself be unlinked or renamed away. These
tests do not say the OS enforces it; the darwin tests do, natively, on macOS CI.
"""
from __future__ import annotations

import os

import pytest

from tests.os_boundary_darwin import (
    SANDBOX_EXEC,
    ProfileError,
    sandbox_argv,
    seatbelt_profile,
)

pytestmark = pytest.mark.skipif(
    os.name == "nt", reason="needs POSIX paths: a Seatbelt profile names POSIX paths")


@pytest.fixture
def dirs(tmp_path):
    made = {}
    for name in ("tmp", "home", "work", "vendor", "source"):
        (tmp_path / name).mkdir()
        made[name] = (tmp_path / name).resolve()
    (made["vendor"] / "hooks").mkdir()
    return made


def _lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


def test_the_profile_denies_every_write_first_then_allows_only_the_named_directories(dirs):
    lines = _lines(seatbelt_profile(writable=[dirs["tmp"], dirs["work"]]))
    assert lines[0] == "(version 1)" and lines[1] == "(allow default)"
    assert lines[2] == "(deny file-write*)"
    allow = next(line for line in lines if line.startswith("(allow file-write*"))
    assert lines.index(allow) > 2
    assert f'(subpath "{dirs["tmp"]}")' in allow and f'(subpath "{dirs["work"]}")' in allow
    assert str(dirs["source"]) not in "\n".join(lines), "the source tree must not be named"


def test_the_protected_paths_are_denied_after_the_allow_that_covers_them(dirs):
    protected = dirs["vendor"] / "hooks"
    lines = _lines(seatbelt_profile(writable=[dirs["vendor"]], protected=[protected]))
    allow = next(i for i, line in enumerate(lines) if line.startswith("(allow file-write*"))
    deny = next(i for i, line in enumerate(lines)
                if line.startswith("(deny file-write*") and str(protected) in line)
    assert deny > allow, "a later rule wins, so the protected deny must come after the allow"


def test_a_writable_directory_cannot_itself_be_unlinked_or_renamed(dirs):
    text = seatbelt_profile(writable=[dirs["vendor"]], protected=[dirs["vendor"] / "hooks"])
    assert f'(deny file-write-unlink (literal "{dirs["vendor"]}"))' in text


def test_a_root_named_removable_loses_its_unlink_deny_and_the_others_keep_theirs(dirs):
    text = seatbelt_profile(writable=[dirs["tmp"], dirs["vendor"]], removable=[dirs["vendor"]])
    assert f'(deny file-write-unlink (literal "{dirs["tmp"]}"))' in text
    assert f'(deny file-write-unlink (literal "{dirs["vendor"]}"))' not in text
    assert f'(subpath "{dirs["vendor"]}")' in text, "a removable root is still writable"


def test_a_removable_root_that_is_not_writable_is_refused(dirs):
    with pytest.raises(ProfileError, match="removable but not writable"):
        seatbelt_profile(writable=[dirs["tmp"]], removable=[dirs["vendor"]])


def test_read_and_link_rules_appear_only_when_asked(dirs):
    plain = seatbelt_profile(writable=[dirs["tmp"]])
    assert "file-read" not in plain and "file-link" not in plain
    asked = seatbelt_profile(writable=[dirs["tmp"]], unreadable=[dirs["source"]],
                             deny_links=[dirs["source"]])
    assert f'(deny file-read* (subpath "{dirs["source"]}"))' in asked
    assert f'(deny file-link (subpath "{dirs["source"]}"))' in asked


def test_paths_are_written_as_real_paths_because_the_profile_matches_resolved_paths(
        dirs, tmp_path):
    (tmp_path / "alias").symlink_to(dirs["work"], target_is_directory=True)
    text = seatbelt_profile(writable=[tmp_path / "alias"])
    assert f'(subpath "{dirs["work"]}")' in text and "alias" not in text


@pytest.mark.parametrize("bad", ['/tmp/a"b', "/tmp/a\\b", "/tmp/a\nb", "/tmp/a\x00b"],
                         ids=["quote", "backslash", "newline", "nul"])
def test_a_path_that_cannot_be_quoted_safely_is_refused(bad):
    with pytest.raises(ProfileError):
        seatbelt_profile(writable=[bad])


def test_a_relative_path_is_refused():
    with pytest.raises(ProfileError):
        seatbelt_profile(writable=["relative/dir"])


def test_the_sandbox_command_carries_the_profile_then_the_command():
    profile = "(version 1)(allow default)"
    assert sandbox_argv(profile, ["/bin/sh", "-c", "true"]) == [
        SANDBOX_EXEC, "-p", profile, "/bin/sh", "-c", "true"]
