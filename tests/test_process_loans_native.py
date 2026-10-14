"""One controlled Windows child works on EXISTING folders loaned to its AppContainer.

`work/<id>`, the per-spawn home and the pinned install folder exist before the attempt and are not
deleted by it. The runner loans them (modify, modify, read-and-execute), the child changes what it
may and only that, and at exit each folder has the DACL it had before and no entry of the profile
is left beneath it.
"""
from __future__ import annotations

import os
import subprocess

import pytest

from conductor import ownership, ownership_transition
from conductor.command.adapters.process import CommandSpec, ContainmentError, ProcessRunner
from conductor.command.adapters.process_boundary import AttemptFolders

pytestmark = pytest.mark.skipif(os.name != "nt", reason="native AppContainer ACL loans")


def _quoted(path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


class Site:
    """An activated project with seeded work, a home, and an install folder beside it."""

    def __init__(self, base):
        self.base = base
        self.root = (base / "project").resolve()
        (self.root / "conductor").mkdir(parents=True)
        (self.root / ".git").mkdir()
        (self.root / ".git" / "index").write_text("index", encoding="utf-8")
        (self.root / "source.txt").write_text("owner", encoding="utf-8")
        (self.root / "work" / "t1" / "sub").mkdir(parents=True)
        (self.root / "work" / "t1" / "seed.txt").write_text("seed", encoding="utf-8")
        (self.root / "work" / "t1" / "sub" / "f.txt").write_text("f", encoding="utf-8")
        (self.root / ".kit-home" / "a").mkdir(parents=True)
        self.install = (base / "harnesses" / "kit" / "1.0").resolve()
        self.install.mkdir(parents=True)
        (self.install / "tool.txt").write_text("tool", encoding="utf-8")
        self.folders = AttemptFolders(work="work/t1", home=".kit-home/a", install=str(self.install))
        ownership_transition.activate(self.root, legacy_writers_stopped=True)

    def locations(self):
        return {"work": self.root / "work" / "t1", "home": self.root / ".kit-home" / "a",
                "install": self.install}


def snapshot(path):
    from conductor.command.adapters import _winlaunch
    from conductor.ownership_native import NativeHold
    hold = NativeHold(path, directory=True)
    try:
        return _winlaunch.acl_snapshot(hold)
    finally:
        hold.close()


def same_acl(first, second) -> bool:
    """Equal ACL bytes, protection and owner: the contract of a returned DACL.

    The SDDL text can differ in the descriptor's `AI` control flag, which the OS sets on a DACL it
    has processed for inheritance; it is not an entry and grants nothing, so it is not compared.
    """
    from conductor.command.adapters import _winlaunch
    return first[1:] == second[1:] and _winlaunch.acl_equal(first[0], second[0])


def entries_naming(path, sid) -> list[str]:
    """Every line `icacls /T` prints for the tree under `path` that names `sid`."""
    done = subprocess.run(["icacls", str(path), "/T", "/C"], capture_output=True)
    text = done.stdout.decode("oem", errors="replace")
    return [line for line in text.splitlines() if sid in line]


def child_script(site, *, writes_work) -> str:
    from tests.os_boundary_box import WITHOUT_CMDLETS
    work_write = ("[IO.File]::WriteAllText('seed.txt','changed'); "
                  "[IO.File]::WriteAllText('sub\\f.txt','changed'); "
                  "[IO.File]::WriteAllText('made.txt','new'); "
                  "$o += 'work=written;'; " if writes_work else
                  "try { [IO.File]::WriteAllText('seed.txt','bad'); $o += 'work=writable;' } "
                  "catch { $o += 'work=denied;' }; "
                  "$o += 'seed=' + [IO.File]::ReadAllText('seed.txt') + ';'; ")
    home = site.locations()["home"] / "h.txt"
    tool = site.install / "tool.txt"
    return (WITHOUT_CMDLETS + "$o = ''; " + work_write
            + f"[IO.File]::WriteAllText({_quoted(home)},'home'); $o += 'home=written;'; "
            + f"$o += 'tool=' + [IO.File]::ReadAllText({_quoted(tool)}) + ';'; "
            + f"try {{ [IO.File]::WriteAllText({_quoted(tool)},'bad'); "
            + "$o += 'install=writable;' } catch { $o += 'install=denied;' }; "
            + f"try {{ [IO.File]::WriteAllText({_quoted(site.root / 'source.txt')},'bad'); "
            + "$o += 'source=writable;' } catch { $o += 'source=denied;' }; "
            + f"try {{ [IO.File]::WriteAllText({_quoted(site.root / '.git' / 'index')},'bad'); "
            + "$o += 'git=writable' } catch { $o += 'git=denied' }; [Console]::Out.Write($o)")


def run_child(site, mode):
    from tests import os_boundary_windows as ac
    from tests.os_boundary_box import base_environment
    runner = ProcessRunner(site.root)
    seen = {}
    with ownership.acquire_owner(site.root):
        before = {k: snapshot(p) for k, p in site.locations().items()}
        with runner.container_profile(mode=mode, folders=site.folders) as (boundary, paths):
            seen["paths"], seen["sid"] = dict(paths), boundary.sid
            spec = CommandSpec(
                (str(ac.POWERSHELL), "-NoProfile", "-NonInteractive", "-Command",
                 child_script(site, writes_work=mode == "dispatch")), "work/t1",
                env=base_environment(paths["runtime"]), boundary=boundary, timeout_seconds=30)
            seen["outcome"] = runner.run(spec)
            seen["during"] = {k: snapshot(p) for k, p in site.locations().items()}
        seen["after"] = {k: snapshot(p) for k, p in site.locations().items()}
    seen["before"] = before
    return seen


@pytest.fixture
def site(tmp_path):
    return Site(tmp_path)


def test_a_dispatch_child_changes_the_loaned_work_and_home_and_nothing_else(site):
    seen = run_child(site, "dispatch")
    assert seen["outcome"].status == "completed" and seen["outcome"].exit_code == 0
    assert seen["outcome"].output == (b"work=written;home=written;tool=tool;install=denied;"
                                      b"source=denied;git=denied")
    work = site.locations()["work"]
    assert (work / "seed.txt").read_text() == "changed"
    assert (work / "sub" / "f.txt").read_text() == "changed"
    assert (work / "made.txt").read_text() == "new"
    assert (site.locations()["home"] / "h.txt").read_text() == "home"
    assert (site.install / "tool.txt").read_text() == "tool"
    assert (site.root / "source.txt").read_text() == "owner"
    assert (site.root / ".git" / "index").read_text() == "index"


def test_a_review_child_reads_the_loaned_work_and_cannot_change_it(site):
    seen = run_child(site, "review")
    assert seen["outcome"].output == (b"work=denied;seed=seed;home=written;tool=tool;"
                                      b"install=denied;source=denied;git=denied")
    assert (site.locations()["work"] / "seed.txt").read_text() == "seed"


def test_the_paths_a_block_yields_are_the_loaned_folders_and_two_fresh_ones(site):
    seen = run_child(site, "dispatch")
    paths = seen["paths"]
    assert set(paths) == {"parent", "runtime", "work", "home", "install"}
    assert paths["work"] == site.locations()["work"] and paths["home"] == site.locations()["home"]
    assert paths["install"] == site.install
    assert paths["runtime"].parent == paths["parent"] and not paths["parent"].exists()


def test_while_the_attempt_runs_each_loaned_folder_names_the_profile_and_at_exit_it_does_not(site):
    seen = run_child(site, "dispatch")
    for key, path in site.locations().items():
        assert seen["sid"] in seen["during"][key][0], key
        assert same_acl(seen["after"][key], seen["before"][key]), key
        assert path.is_dir()
        assert entries_naming(path, seen["sid"]) == [], f"an entry of the profile is left in {key}"


def test_what_the_child_made_in_the_work_folder_belongs_to_the_owner_afterwards(site):
    run_child(site, "dispatch")
    work = site.locations()["work"]
    made = work / "made.txt"
    made.write_text("owner again", encoding="utf-8")
    assert made.read_text(encoding="utf-8") == "owner again"
    made.unlink()
    (work / "sub" / "f.txt").unlink()
    assert (work / "seed.txt").read_text() == "changed"


def test_a_route_through_a_junction_is_refused_before_anything_is_journalled(site):
    elsewhere = site.base / "elsewhere"
    elsewhere.mkdir()
    link = site.root / "work" / "link"
    done = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(elsewhere)],
                          capture_output=True)
    assert done.returncode == 0, done.stderr
    runner = ProcessRunner(site.root)
    folders = AttemptFolders(work="work/link", home=None, install=str(site.install))
    with ownership.acquire_owner(site.root):
        with pytest.raises(ContainmentError):
            with runner.container_profile(mode="dispatch", folders=folders):
                pytest.fail("the block must not be entered")
    journal = site.root / "conductor.v3" / "process-profiles"
    assert not journal.exists() or list(journal.glob("*")) == []
