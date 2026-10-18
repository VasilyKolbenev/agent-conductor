"""One controlled Windows child works in a leased login home, inside a real AppContainer.

The home is a THROWAWAY one, made under the pytest base directory in the shape the product keeps its
logins in (`DecemberCommand/logins/<name>`), with files that only look like a login. Nothing here
touches the operator's folders or reads a credential. The attempt holds the shared login lease on
the home, the runner loans it for the attempt's life, and the child refreshes a login file the three
ways a vendor does: in place, by a native rename over it, and by delete-then-move, at the top of the
home and in a nested directory. Whatever the grant does not give stays refused (deleting or moving
the home or a nested directory, changing an ACL, replacing the two hook objects Grok keeps there,
writing beside or outside the home), and at exit the profile is named nowhere.
"""
from __future__ import annotations

import os

import pytest

from conductor import ownership, ownership_login, ownership_transition
from conductor.command.adapters.process import CommandSpec, ProcessRunner
from conductor.command.adapters.process_boundary import AttemptFolders
from conductor.command.adapters.process_profile import ProfileRefused
from tests.login_gate import login_loan_open_module  # noqa: F401 -- a fixture
from tests.test_process_loans_native import entries_naming, same_acl, snapshot

pytestmark = [pytest.mark.skipif(os.name != "nt", reason="native AppContainer ACL loans"),
              pytest.mark.usefixtures("login_loan_open_module")]

#: ``MoveFileExW(a, b, MOVEFILE_REPLACE_EXISTING)`` through a P/Invoke method the script emits
#: itself: ``Add-Type`` is a cmdlet, and a probe runs without the cmdlet modules.
_NATIVE = (
    "$t = [AppDomain]::CurrentDomain.DefineDynamicAssembly("
    "[Reflection.AssemblyName]::new('h'), [Reflection.Emit.AssemblyBuilderAccess]::Run)"
    ".DefineDynamicModule('h').DefineType('N'); "
    "$m = $t.DefinePInvokeMethod('MoveFileExW', 'kernel32.dll', 'Public,Static,PinvokeImpl', "
    "'Standard', [bool], [Type[]]@([string], [string], [int]), 'Winapi', 'Unicode'); "
    "$m.SetImplementationFlags('PreserveSig'); $n = $t.CreateType(); ")
#: A rule that adds an entry for Everyone: .NET writes a DACL only when it was changed, so a probe
#: of WRITE_DAC must change it, or "set the ACL I just read" is a no-op that succeeds.
_EVERYONE = (
    "$r = [Security.AccessControl.FileSystemAccessRule]::new("
    "[Security.Principal.SecurityIdentifier]::new('S-1-1-0'), "
    "[Security.AccessControl.FileSystemRights]::FullControl, "
    "[Security.AccessControl.AccessControlType]::Allow); ")
CREDENTIAL = "placeholder, not a credential"
FILES = ("auth.json", "rotate.json", "swap.json", "replace.json")
HOOKS = ("hooks", "hooks-paths")


def _q(path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _tries(label: str, body: str) -> str:
    return f"try {{ {body}; $o += '{label}=ok;' }} catch {{ $o += '{label}=denied;' }}; "


def snapshot_of(path):
    """The ACL of a folder or a file, read without being able to change it."""
    if path.is_dir():
        return snapshot(path)
    from conductor.command.adapters import _winlaunch
    from conductor.ownership_native import NativeHold
    hold = NativeHold(path)
    try:
        return _winlaunch.acl_snapshot(hold)
    finally:
        hold.close()


class LoginSite:
    """An activated project, a pinned install folder, and two login homes in one logins folder.

    The leased home holds login files at its top and in a nested directory, an empty nested
    directory, and the two hook objects Grok keeps, made before the attempt with their inheritance
    cut (the shape the vendor's own rule asks for).
    """

    def __init__(self, base):
        from tests import os_boundary_windows as ac
        self.base = base
        self.root = (base / "project").resolve()
        (self.root / "conductor").mkdir(parents=True)
        (self.root / ".git").mkdir()
        (self.root / ".git" / "index").write_text("index", encoding="utf-8")
        (self.root / "source.txt").write_text("owner", encoding="utf-8")
        (self.root / "work" / "t1").mkdir(parents=True)
        (self.root / "work" / "t1" / "seed.txt").write_text("seed", encoding="utf-8")
        self.install = (base / "harnesses" / "kit" / "1.0").resolve()
        self.install.mkdir(parents=True)
        (self.install / "tool.txt").write_text("tool", encoding="utf-8")
        self.logins = (base / "DecemberCommand" / "logins").resolve()
        self.login, self.other = self.logins / "claude-code", self.logins / "codex"
        for home in (self.login, self.other):
            home.mkdir(parents=True)
            for name in FILES:
                (home / name).write_text(CREDENTIAL, encoding="utf-8")
        self.nested = self.login / "sub"
        (self.nested).mkdir()
        (self.login / "empty").mkdir()
        for name in FILES:
            (self.nested / name).write_text(CREDENTIAL, encoding="utf-8")
        (self.login / "hooks").mkdir()
        (self.login / "hooks-paths").write_bytes(b"")
        for name in HOOKS:
            ac.protect_entry(self.login / name)
        ownership_transition.activate(self.root, legacy_writers_stopped=True)
        self.folders = AttemptFolders(work="work/t1", home=None, install=str(self.install),
                                      login=str(self.login))

    def locations(self) -> dict:
        return {"work": self.root / "work" / "t1", "install": self.install, "login": self.login}

    def untouched(self) -> dict:
        """What the attempt has no grant on and must leave exactly as it found it."""
        return {"other": self.other, "logins": self.logins,
                "hooks": self.login / "hooks", "hooks-paths": self.login / "hooks-paths"}


def refresh(directory, prefix: str) -> str:
    """The three ways a vendor refreshes a login file, and ReplaceFile, in one directory."""
    def path(name):
        return _q(directory / name)
    return (
        _tries(prefix + "inplace",
               f"[IO.File]::WriteAllText({path('auth.json')},'token=refreshed')")
        + _tries(prefix + "created", f"[IO.File]::WriteAllText({path('made.txt')},'state')")
        + f"[IO.File]::WriteAllText({path('rotate.new')},'token=rotated'); "
        + f"$o += '{prefix}rename=' + $n::MoveFileExW({path('rotate.new')},"
          f"{path('rotate.json')},1) + ';'; "
        + f"[IO.File]::WriteAllText({path('swap.new')},'token=swapped'); "
        + _tries(prefix + "delmove", f"[IO.File]::Delete({path('swap.json')}); "
                 f"[IO.File]::Move({path('swap.new')},{path('swap.json')})")
        + f"[IO.File]::WriteAllText({path('replace.new')},'token=replaced'); "
        + _tries(prefix + "replacefile", f"[IO.File]::Replace({path('replace.new')},"
                 f"{path('replace.json')},{path('replace.bak')})"))


def refused(site: LoginSite) -> str:
    """What the grant must leave refused: structure, ACLs, the hook objects, everything outside."""
    home, sub, auth = site.login, site.nested, site.login / "auth.json"
    structure = (
        _tries("home_move", f"[IO.Directory]::Move({_q(home)},{_q(str(home) + '-moved')})")
        + _tries("sub_move", f"[IO.Directory]::Move({_q(sub)},{_q(str(sub) + '-moved')})")
        + _tries("empty_delete", f"[IO.Directory]::Delete({_q(home / 'empty')})")
        + _tries("dacl_read", f"$a = [IO.FileInfo]::new({_q(auth)}).GetAccessControl()")
        + _tries("dacl_write", _EVERYONE + f"$a.AddAccessRule($r); "
                 f"[IO.FileInfo]::new({_q(auth)}).SetAccessControl($a)"))
    hooks = (
        _tries("hooks_paths_write", f"[IO.File]::WriteAllText({_q(home / 'hooks-paths')},'x')")
        + _tries("hooks_paths_delete", f"[IO.File]::Delete({_q(home / 'hooks-paths')})")
        + _tries("hooks_paths_move", f"[IO.File]::Move({_q(home / 'hooks-paths')},"
                 f"{_q(home / 'hp2')})")
        + _tries("hooks_create", f"[IO.File]::WriteAllText({_q(home / 'hooks' / 'x')},'x')")
        + _tries("hooks_delete", f"[IO.Directory]::Delete({_q(home / 'hooks')})")
        + _tries("hooks_move", f"[IO.Directory]::Move({_q(home / 'hooks')},{_q(home / 'h2')})"))
    box = ownership_login.box_key(str(site.login))[1]
    outside = "".join(_tries(label, f"[IO.File]::WriteAllText({_q(path)},'bad')")
                      for label, path in (
        ("work", site.root / "work" / "t1" / "seed.txt"),
        ("install", site.install / "tool.txt"),
        ("beside", site.logins / "beside.txt"),
        ("other", site.other / "auth.json"),
        ("lease", box / "active.json"),
        ("source", site.root / "source.txt"),
        ("git", site.root / ".git" / "index")))
    return structure + hooks + outside


def child_script(site: LoginSite) -> str:
    from tests.os_boundary_box import WITHOUT_CMDLETS
    return (WITHOUT_CMDLETS + "$o = ''; " + _NATIVE + refresh(site.login, "")
            + refresh(site.nested, "sub_") + refused(site) + "[Console]::Out.Write($o)")


def everywhere(site: LoginSite) -> dict:
    return {**site.locations(), **site.untouched()}


def mutexes_are_free(site: LoginSite) -> bool:
    """None of the loaned folders has its DACL mutex held: the runner holds it per change only."""
    from conductor.command.adapters import _winlaunch
    from conductor.ownership_native import NativeHold
    for path in site.locations().values():
        hold = NativeHold(path, directory=True)
        try:
            with _winlaunch.acl_exclusive(hold, wait=0.5):
                pass
        except TimeoutError:
            return False
        finally:
            hold.close()
    return True


def run_child(site: LoginSite, mode: str, script: str | None = None) -> dict:
    from tests import os_boundary_windows as ac
    from tests.os_boundary_box import base_environment
    runner, seen = ProcessRunner(site.root), {}
    entry = site.install / "entry.ps1"
    entry.write_text(child_script(site) if script is None else script, encoding="utf-8")
    with ownership.acquire_owner(site.root):
        seen["before"] = {k: snapshot_of(p) for k, p in everywhere(site).items()}
        seen["identity"] = os.stat(site.login / "auth.json").st_ino
        with ProcessRunner.login_write_guard(site.root, str(site.login)):
            with runner.container_profile(mode=mode, folders=site.folders) as (boundary, paths):
                seen["paths"], seen["sid"] = dict(paths), boundary.sid
                seen["mutexes_free"] = mutexes_are_free(site)
                spec = CommandSpec(
                    (str(ac.POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                     "Bypass", "-File", str(entry)), "work/t1",
                    env=base_environment(paths["runtime"]), boundary=boundary, timeout_seconds=60)
                seen["outcome"] = runner.run(spec)
                seen["during"] = {k: snapshot_of(p) for k, p in everywhere(site).items()}
        seen["after"] = {k: snapshot_of(p) for k, p in everywhere(site).items()}
    return seen


@pytest.fixture(scope="module")
def dispatch(tmp_path_factory, login_loan_open_module):
    site = LoginSite(tmp_path_factory.mktemp("login-dispatch"))
    return site, run_child(site, "dispatch")


@pytest.fixture(scope="module")
def review(tmp_path_factory, login_loan_open_module):
    site = LoginSite(tmp_path_factory.mktemp("login-review"))
    return site, run_child(site, "review")


def facts(seen) -> dict:
    return dict(item.split("=") for item in seen["outcome"].output.decode().split(";") if item)


def test_a_child_rewrites_a_login_file_in_place_keeping_the_file_and_leaving_no_second_one(
        dispatch):
    site, seen = dispatch
    assert seen["outcome"].status == "completed" and seen["outcome"].exit_code == 0
    assert facts(seen)["inplace"] == "ok"
    assert (site.login / "auth.json").read_text(encoding="utf-8") == "token=refreshed"
    assert os.stat(site.login / "auth.json").st_ino == seen["identity"], "another file stands now"


def test_a_child_replaces_a_login_file_by_a_native_rename_over_it_and_by_delete_then_move(
        dispatch):
    site, seen = dispatch
    assert facts(seen)["rename"] == "True" and facts(seen)["delmove"] == "ok"
    assert (site.login / "rotate.json").read_text(encoding="utf-8") == "token=rotated"
    assert (site.login / "swap.json").read_text(encoding="utf-8") == "token=swapped"


def test_a_child_does_the_same_three_things_to_a_login_file_in_a_nested_directory(dispatch):
    site, seen = dispatch
    assert facts(seen)["sub_inplace"] == "ok" and facts(seen)["sub_rename"] == "True"
    assert facts(seen)["sub_delmove"] == "ok" and facts(seen)["sub_created"] == "ok"
    assert (site.nested / "auth.json").read_text(encoding="utf-8") == "token=refreshed"
    assert (site.nested / "rotate.json").read_text(encoding="utf-8") == "token=rotated"
    assert (site.nested / "swap.json").read_text(encoding="utf-8") == "token=swapped"


def test_a_child_creates_its_own_state_in_the_login_home_and_replacefile_stays_refused(dispatch):
    site, seen = dispatch
    assert facts(seen)["created"] == "ok" and (site.login / "made.txt").exists()
    for prefix, directory in (("", site.login), ("sub_", site.nested)):
        assert facts(seen)[prefix + "replacefile"] == "denied", "ReplaceFile now works: a finding"
        assert (directory / "replace.json").read_text(encoding="utf-8") == CREDENTIAL


def test_the_child_cannot_delete_or_move_the_home_or_a_nested_directory_or_change_an_acl(dispatch):
    site, seen = dispatch
    names = ("home_move", "sub_move", "empty_delete", "dacl_write")
    assert {k: facts(seen)[k] for k in names} == dict.fromkeys(names, "denied")
    assert facts(seen)["dacl_read"] == "ok", "the probe did read the ACL it was refused to change"
    assert site.login.is_dir() and site.nested.is_dir() and (site.login / "empty").is_dir()


def test_the_two_hook_objects_survive_every_attempt_to_write_delete_move_or_fill_them(dispatch):
    from tests.test_os_boundary_windows_protected import INTACT, protected_state
    site, seen = dispatch
    names = ("hooks_paths_write", "hooks_paths_delete", "hooks_paths_move", "hooks_create",
             "hooks_delete", "hooks_move")
    assert {k: facts(seen)[k] for k in names} == dict.fromkeys(names, "denied")
    assert protected_state(site.login) == INTACT


def test_no_mutex_of_a_loaned_folder_is_held_while_the_agent_works(dispatch):
    _, seen = dispatch
    assert seen["mutexes_free"], "the grant kept a folder's ACL mutex for the attempt's life"


def test_a_child_writes_nowhere_outside_the_folders_granted_to_it(dispatch):
    site, seen = dispatch
    names = ("install", "beside", "other", "lease", "source", "git")
    assert {k: facts(seen)[k] for k in names} == dict.fromkeys(names, "denied")
    assert facts(seen)["work"] == "ok", "the dispatch work folder is the granted one"
    assert (site.other / "auth.json").read_text(encoding="utf-8") == CREDENTIAL
    assert not (site.logins / "beside.txt").exists()
    assert (site.root / "source.txt").read_text(encoding="utf-8") == "owner"


def test_the_paths_a_login_block_yields_name_the_leased_home_and_no_per_spawn_home(dispatch):
    site, seen = dispatch
    assert set(seen["paths"]) == {"parent", "runtime", "work", "install", "login"}
    assert seen["paths"]["login"] == site.login
    assert seen["paths"]["work"] == site.locations()["work"]


def test_while_the_attempt_runs_the_login_home_names_the_profile_and_at_exit_it_does_not(dispatch):
    site, seen = dispatch
    assert seen["sid"] in seen["during"]["login"][0]
    for key in everywhere(site):
        assert same_acl(seen["after"][key], seen["before"][key]), key
    for key in site.untouched():
        assert seen["sid"] not in seen["during"][key][0], f"{key} was granted to the profile"


def test_after_exit_icacls_names_the_profile_nowhere_in_the_login_home_or_beside_it(dispatch):
    site, seen = dispatch
    assert entries_naming(site.login, seen["sid"]) == []
    assert entries_naming(site.logins, seen["sid"]) == [], "an entry is left in the logins folder"
    assert entries_naming(site.install, seen["sid"]) == []
    assert entries_naming(site.root / "work" / "t1", seen["sid"]) == []


def test_what_the_child_made_in_the_login_home_belongs_to_the_owner_afterwards(dispatch):
    site, _ = dispatch
    made = site.login / "made.txt"
    made.write_text("owner again", encoding="utf-8")
    assert made.read_text(encoding="utf-8") == "owner again"
    made.unlink()


def test_a_review_child_refreshes_the_login_home_and_cannot_change_the_work_folder(review):
    site, seen = review
    assert facts(seen)["inplace"] == "ok" and facts(seen)["rename"] == "True"
    assert facts(seen)["work"] == "denied"
    assert (site.root / "work" / "t1" / "seed.txt").read_text(encoding="utf-8") == "seed"
    assert entries_naming(site.login, seen["sid"]) == []


def test_an_attempt_without_the_login_lease_is_refused_before_anything_is_journalled(tmp_path):
    site = LoginSite(tmp_path)
    runner, before = ProcessRunner(site.root), snapshot(site.login)
    with ownership.acquire_owner(site.root):
        with pytest.raises(ProfileRefused, match="holds no login lease"):
            with runner.container_profile(mode="dispatch", folders=site.folders):
                pytest.fail("the block must not be entered")
    journal = site.root / "conductor.v3" / "process-profiles"
    assert not journal.exists() or list(journal.glob("*")) == []
    assert same_acl(snapshot(site.login), before)
    assert entries_naming(site.login, "S-1-15-2-") == [], "no AppContainer profile is named"


def test_a_hook_object_that_inherits_is_refused_before_the_native_profile_exists(tmp_path):
    site = LoginSite(tmp_path)
    from tests import os_boundary_windows as ac
    # inherit again: the rights the loan hands down would reach the file
    ac._icacls(str(site.login / "hooks-paths"), "/inheritance:e")
    runner, before = ProcessRunner(site.root), snapshot(site.login)
    with ownership.acquire_owner(site.root):
        with ProcessRunner.login_write_guard(site.root, str(site.login)):
            with pytest.raises(ProfileRefused, match="inherits its rights"):
                with runner.container_profile(mode="dispatch", folders=site.folders):
                    pytest.fail("the block must not be entered")
    journal = site.root / "conductor.v3" / "process-profiles"
    assert not journal.exists() or list(journal.glob("*")) == []
    assert same_acl(snapshot(site.login), before)
