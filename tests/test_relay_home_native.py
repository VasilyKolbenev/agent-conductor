"""One controlled Windows child works in a RELAY home, inside a real AppContainer.

The relay home is a throw-away folder `DecemberCommand/relay/<key>/c-<16 hex>` made under the pytest
base directory, beside a login home `DecemberCommand/logins/x` that holds a file which only looks
like a credential. Nothing here touches the operator's folders or reads a credential. The product's
side is played by the test: the relay folder is made with its protected DACL
(`ProcessRunner.ensure_relay_root`), and the files a product copies in are written BEFORE the
attempt starts. The runner loans the home like any per-spawn home; the child rewrites a leaf in
place, by a native rename over it and by delete-then-move, and creates a file. It may not delete or
move the home, write the key folder or the relay folder or another project's relay home, read or
write the real login home, or write the lease's box; and at exit the profile is named nowhere and
every DACL is as it was.

Every refusal is the OS's own: a probe reports the type and the HRESULT of the error (`_probe`), and
a test asks for access denied, so a mistyped path or a sharing violation cannot pass for an ACL.
The capability of the child (`internet_client=True`) is measured, not assumed. The gate of the
leased login home stays shut throughout (`LOGIN_LOAN_OPEN`): the relay home is a home, not a login
home.
"""
from __future__ import annotations

import os
import re
import shutil

import pytest

from conductor import ownership, ownership_login, ownership_transition
from conductor.command.adapters import process_boundary, process_loans
from conductor.command.adapters.process import CommandSpec, ProcessRunner
from conductor.command.adapters.process_boundary import AttemptFolders
from conductor.command.adapters.process_profile import ProfileRefused
from conductor.command.adapters.relay_home import relay_acl_refusal, relay_key, relay_root_sddl
from conductor.ownership_native import identity
from tests._ps1 import describe, strict_text, write_ps1
from tests.test_process_loans_native import entries_naming, same_acl
from tests.test_process_login_native import _EVERYONE, _NATIVE, _q, snapshot_of

pytestmark = pytest.mark.skipif(os.name != "nt", reason="native AppContainer ACL loans")

HEX = "0123456789abcdef"
DELETE, WRITE_DAC, WRITE_OWNER, DELETE_CHILD = 0x10000, 0x40000, 0x80000, 0x40
CREDENTIAL = "placeholder, not a credential"
LEAVES = (".credentials.json", ".claude.json", "swap.json")
#: What the OS says when an ACL refuses a call (`_probe`): ERROR_ACCESS_DENIED, which .NET raises as
#: an UnauthorizedAccessException. Anything else (a mistyped path, a sharing violation) is not it.
DENIED = "UnauthorizedAccessException/80070005"
#: The same answer for the move and the delete of a folder, which .NET Framework raises as an
#: IOException: for the move with the same code, for `Directory.Delete` with the generic HRESULT of
#: its access-denied branch. A sharing violation is `IOException/80070020` for both (measured).
MOVE_DENIED, DELETE_DENIED = "IOException/80070005", "IOException/80131620"


class RelaySite:
    """An activated project, a pinned install folder, a login home and the relay layout beside it.

    The relay folder is made by `ensure_relay_root`, the key folder and the relay home by the
    test; the relay home holds the leaves a product copies in before the attempt, and another
    project's relay home stands beside the key folder.
    """

    def __init__(self, base, *, relay: bool = True):
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
        self.top = (base / "DecemberCommand").resolve()
        self.logins = self.top / "logins"
        self.login = self.logins / "x"
        self.login.mkdir(parents=True)
        (self.login / ".credentials.json").write_text(CREDENTIAL, encoding="utf-8")
        self.control = base / "control"
        self.control.mkdir()
        (self.control / "with.txt").write_text("capability", encoding="utf-8")
        (self.control / "without.txt").write_text("nothing", encoding="utf-8")
        from tests import os_boundary_windows as ac
        ac.grant(self.control / "with.txt", ac.INTERNET_CLIENT, "R")
        ownership_transition.activate(self.root, legacy_writers_stopped=True)
        self.relay = self.top / "relay"
        self.key = self.relay / relay_key(identity(self.root))
        self.home = self.key / f"c-{HEX}"
        self.other = self.relay / relay_key((1, 2)) / f"c-{HEX}"
        if relay:
            self.make_relay()
        self.folders = AttemptFolders(work="work/t1", home=str(self.home),
                                      install=str(self.install))

    def make_relay(self) -> None:
        assert ProcessRunner.ensure_relay_root(self.login) == self.relay
        self.home.mkdir(parents=True)
        self.other.mkdir(parents=True)
        for name in LEAVES:
            (self.home / name).write_text("access-only", encoding="utf-8")
        (self.other / "other.json").write_text(CREDENTIAL, encoding="utf-8")

    def locations(self) -> dict:
        return {"work": self.root / "work" / "t1", "install": self.install, "home": self.home}

    def untouched(self) -> dict:
        """What the attempt has no grant on and must leave exactly as it found it."""
        return {"key": self.key, "relay": self.relay, "other": self.other,
                "other-key": self.other.parent, "login": self.login, "logins": self.logins}


def everywhere(site: RelaySite) -> dict:
    return {**site.locations(), **site.untouched()}


def _probe(label: str, body: str) -> str:
    """`label=ok;` when `body` works, else `label=<exception type>/<HRESULT>;` of the real error.

    The error is the one the OS gave, not just a failure: an ACL that refuses a file is
    `UnauthorizedAccessException/80070005` (ERROR_ACCESS_DENIED), a mistyped path is
    `FileNotFoundException/80070002`, and a folder the runner holds open is `IOException/80070020`
    (a sharing violation). A probe that only said "denied" could not tell them apart.
    """
    return (f"try {{ {body}; $o += '{label}=ok;' }} catch {{ $e = $_.Exception; "
            "if ($e.InnerException) { $e = $e.InnerException }; "
            f"$o += '{label}=' + $e.GetType().Name + '/' + ('{{0:X8}}' -f $e.HResult) + ';' }}; ")


def _try_read(label: str, path) -> str:
    return _probe(label, f"[void][IO.File]::ReadAllText({_q(path)})")


def _try_write(label: str, path) -> str:
    return _probe(label, f"[IO.File]::WriteAllText({_q(path)},'bad')")


def child_script(site: RelaySite) -> str:
    from tests.os_boundary_box import WITHOUT_CMDLETS
    home, creds = site.home, site.home / ".credentials.json"
    box = ownership_login.box_key(str(site.login))[1]
    refresh = (
        _probe("inplace", f"[IO.File]::WriteAllText({_q(creds)},'token=refreshed')")
        + _probe("created", f"[IO.File]::WriteAllText({_q(home / 'made.txt')},'state')")
        + _probe("nested", f"[void][IO.Directory]::CreateDirectory({_q(home / 'sub')}); "
                 f"[IO.File]::WriteAllText({_q(home / 'sub' / 'n.txt')},'n')")
        + f"[IO.File]::WriteAllText({_q(home / '.claude.json.new')},'rotated'); "
        + f"$o += 'rename=' + $n::MoveFileExW({_q(home / '.claude.json.new')},"
          f"{_q(home / '.claude.json')},1) + ';'; "
        + f"[IO.File]::WriteAllText({_q(home / 'swap.new')},'swapped'); "
        + _probe("delmove", f"[IO.File]::Delete({_q(home / 'swap.json')}); "
                 f"[IO.File]::Move({_q(home / 'swap.new')},{_q(home / 'swap.json')})"))
    # the capability the child holds (`internet_client=True`) is a fact of the token, so it is
    # measured: a file whose only entry names it reads, a file with none does not
    capability = (_try_read("cap_with", site.control / "with.txt")
                  + _try_read("cap_without", site.control / "without.txt"))
    refused = (
        _try_read("own_read", creds)
        + _probe("home_move", f"[IO.Directory]::Move({_q(home)},{_q(str(home) + '-moved')})")
        + _probe("home_delete", f"[IO.Directory]::Delete({_q(home)})")
        + _probe("dacl_read", f"$a = [IO.FileInfo]::new({_q(creds)}).GetAccessControl()")
        + _probe("dacl_write", _EVERYONE + f"$a.AddAccessRule($r); "
                 f"[IO.FileInfo]::new({_q(creds)}).SetAccessControl($a)")
        + _try_write("key_write", site.key / "bad.txt")
        + _probe("key_mkdir", f"[void][IO.Directory]::CreateDirectory({_q(site.key / 'bad')})")
        + _try_write("relay_write", site.relay / "bad.txt")
        + _probe("relay_mkdir", f"[void][IO.Directory]::CreateDirectory({_q(site.relay / 'bad')})")
        + _try_write("other_write", site.other / "other.json")
        + _try_write("other_create", site.other / "bad.txt")
        + _try_read("other_read", site.other / "other.json")
        + _try_read("real_read", site.login / ".credentials.json")
        + _try_write("real_write", site.login / ".credentials.json")
        + _try_write("real_create", site.login / "bad.txt")
        + _probe("real_list", f"[void][IO.Directory]::GetFileSystemEntries({_q(site.login)})")
        + _try_write("logins_create", site.logins / "bad.txt")
        + _try_write("box", box / "active.json")
        + _try_write("install", site.install / "tool.txt")
        + _try_write("source", site.root / "source.txt")
        + _try_write("git", site.root / ".git" / "index")
        + _probe("work", f"[IO.File]::WriteAllText({_q(site.root / 'work' / 't1' / 'seed.txt')},"
                 "'changed')"))
    return (WITHOUT_CMDLETS + "$o = ''; " + _NATIVE + refresh + capability + refused
            + "[Console]::Out.Write($o)")


def run_child(site: RelaySite, mode: str = "dispatch") -> dict:
    from tests import os_boundary_windows as ac
    from tests.os_boundary_box import base_environment
    runner, seen = ProcessRunner(site.root), {}
    entry = write_ps1(site.install / "entry.ps1", child_script(site))
    homes = (site.login,)
    with pytest.MonkeyPatch.context() as patch:
        # the project's providers.json would name the login home; its reading has its own tests
        patch.setattr(process_loans, "configured_login_sources",
                      lambda data_root: process_loans.ConfiguredLogins(homes))
        with ownership.acquire_owner(site.root):
            seen["before"] = {k: snapshot_of(p) for k, p in everywhere(site).items()}
            seen["identity"] = os.stat(site.home / ".credentials.json").st_ino
            with ProcessRunner.login_write_guard(site.root, str(site.login)):
                with runner.container_profile(internet_client=True, mode=mode,
                                              folders=site.folders) as (boundary, paths):
                    seen["paths"], seen["sid"] = dict(paths), boundary.sid
                    spec = CommandSpec(
                        (str(ac.POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                         "Bypass", "-File", str(entry)), "work/t1",
                        env=base_environment(paths["runtime"]), boundary=boundary,
                        timeout_seconds=60)
                    seen["outcome"] = runner.run(spec)
                    seen["during"] = {k: snapshot_of(p) for k, p in everywhere(site).items()}
            seen["after"] = {k: snapshot_of(p) for k, p in everywhere(site).items()}
    return seen


@pytest.fixture(scope="module")
def dispatch(tmp_path_factory):
    site = RelaySite(tmp_path_factory.mktemp("relay-dispatch"))
    return site, run_child(site)


def facts(seen) -> dict:
    return dict(item.split("=") for item in strict_text(seen["outcome"].output).split(";") if item)


def test_a_child_rewrites_a_leaf_of_the_relay_home_in_place_keeping_the_file(dispatch):
    site, seen = dispatch
    outcome = seen["outcome"]
    assert outcome.status == "completed" and outcome.exit_code == 0, describe(outcome)
    assert facts(seen)["inplace"] == "ok"
    assert (site.home / ".credentials.json").read_text(encoding="utf-8") == "token=refreshed"
    assert os.stat(site.home / ".credentials.json").st_ino == seen["identity"]


def test_a_child_replaces_a_leaf_by_a_native_rename_over_it_and_by_delete_then_move(dispatch):
    site, seen = dispatch
    assert facts(seen)["rename"] == "True" and facts(seen)["delmove"] == "ok"
    assert (site.home / ".claude.json").read_text(encoding="utf-8") == "rotated"
    assert (site.home / "swap.json").read_text(encoding="utf-8") == "swapped"


def test_a_child_creates_its_own_files_and_a_nested_directory_in_the_relay_home(dispatch):
    site, seen = dispatch
    assert facts(seen)["created"] == "ok" and facts(seen)["nested"] == "ok"
    assert (site.home / "made.txt").read_text(encoding="utf-8") == "state"
    assert (site.home / "sub" / "n.txt").read_text(encoding="utf-8") == "n"


def test_the_child_cannot_move_or_delete_the_relay_home_or_change_an_acl_in_it(dispatch):
    # The runner holds the home without FILE_SHARE_DELETE, which refuses a move and a delete of it
    # whoever asks (a sharing violation). But the OS checks the right first: a profile WITHOUT
    # DELETE is told access denied, and one that had it would be told `IOException/80070020`
    # (measured with a profile given DELETE on the home, the mutant of the report). So the answer
    # below is the absence of the right, not the runner's hold.
    site, seen = dispatch
    assert facts(seen)["home_move"] == MOVE_DENIED and facts(seen)["home_delete"] == DELETE_DENIED
    assert facts(seen)["dacl_write"] == DENIED
    assert facts(seen)["dacl_read"] == "ok", "the probe did read the ACL it was refused to change"
    assert site.home.is_dir() and not (site.key / (site.home.name + "-moved")).exists()


def test_the_child_holds_the_internet_client_capability_the_attempt_asks_for(dispatch):
    # `internet_client=True` is a setting until it is measured: a file whose only entry names
    # the capability reads, the file beside it with no such entry does not.
    _, seen = dispatch
    assert facts(seen)["cap_with"] == "ok" and facts(seen)["cap_without"] == DENIED


def test_the_entry_the_profile_holds_on_the_relay_home_itself_has_no_delete_and_no_write_dac(
        dispatch):
    _, seen = dispatch
    entries = re.findall(r"\(A;([A-Z]*);(0x[0-9a-f]+);;;" + seen["sid"] + r"\)",
                         seen["during"]["home"][0])
    own = [int(mask, 16) for flags, mask in entries if "IO" not in flags]
    handed_down = [int(mask, 16) for flags, mask in entries if "IO" in flags]
    assert own == [0x1201BF], "the folder itself is read, written into and traversed"
    assert not own[0] & (DELETE | WRITE_DAC | WRITE_OWNER | DELETE_CHILD)
    assert handed_down == [0x1301BF], "what is inside may be deleted and replaced, not re-ACLed"
    assert not handed_down[0] & (WRITE_DAC | WRITE_OWNER | DELETE_CHILD)


def test_the_child_cannot_write_the_key_folder_the_relay_folder_or_another_projects_home(dispatch):
    site, seen = dispatch
    names = ("key_write", "key_mkdir", "relay_write", "relay_mkdir", "other_write",
             "other_create", "other_read")
    assert {k: facts(seen)[k] for k in names} == dict.fromkeys(names, DENIED)
    for path in (site.key / "bad.txt", site.key / "bad", site.relay / "bad.txt",
                 site.relay / "bad", site.other / "bad.txt"):
        assert not path.exists(), path
    assert (site.other / "other.json").read_text(encoding="utf-8") == CREDENTIAL


def test_the_child_can_neither_read_nor_write_the_real_login_home_nor_the_leases_box(dispatch):
    site, seen = dispatch
    names = ("real_read", "real_write", "real_create", "real_list", "logins_create", "box")
    assert {k: facts(seen)[k] for k in names} == dict.fromkeys(names, DENIED)
    assert facts(seen)["own_read"] == "ok", "the same read works on the leaf in the relay home"
    assert (site.login / ".credentials.json").read_text(encoding="utf-8") == CREDENTIAL
    assert not (site.login / "bad.txt").exists() and not (site.logins / "bad.txt").exists()
    box = ownership_login.box_key(str(site.login))[1]
    assert box.parent == site.logins and not (box / "bad").exists()


def test_the_child_writes_nowhere_else_but_the_work_folder_of_a_dispatch(dispatch):
    site, seen = dispatch
    names = ("install", "source", "git")
    assert {k: facts(seen)[k] for k in names} == dict.fromkeys(names, DENIED)
    assert facts(seen)["work"] == "ok"
    assert (site.root / "work" / "t1" / "seed.txt").read_text(encoding="utf-8") == "changed"
    assert (site.install / "tool.txt").read_text(encoding="utf-8") == "tool"


def test_the_paths_a_block_yields_name_the_relay_home_as_the_attempts_home(dispatch):
    site, seen = dispatch
    assert set(seen["paths"]) == {"parent", "runtime", "work", "home", "install"}
    assert seen["paths"]["home"] == site.home and seen["paths"]["work"] == site.locations()["work"]


def test_while_the_attempt_runs_only_the_relay_home_names_the_profile_among_the_relay_folders(
        dispatch):
    site, seen = dispatch
    for key in site.locations():
        assert seen["sid"] in seen["during"][key][0], key
    for key in site.untouched():
        assert seen["sid"] not in seen["during"][key][0], f"{key} was granted to the profile"


def test_at_exit_every_dacl_is_as_it_was_and_icacls_names_the_profile_nowhere(dispatch):
    site, seen = dispatch
    for key in everywhere(site):
        assert same_acl(seen["after"][key], seen["before"][key]), key
    for folder in (site.relay, site.login, site.logins, site.install, site.root / "work" / "t1"):
        assert entries_naming(folder, seen["sid"]) == [], f"an entry is left in {folder}"
    assert seen["before"]["relay"][1] is True, "the relay folder is protected"
    assert process_boundary.LOGIN_LOAN_OPEN is False
    assert process_boundary.login_loan_provided() is False


def test_the_real_dacls_the_readiness_reads_are_judged_good_in_this_layout(dispatch):
    from conductor.command.adapters import _winlaunch
    site, _ = dispatch
    assert relay_acl_refusal(_winlaunch, site.login) is None
    assert relay_acl_refusal(_winlaunch, site.login, site.home) is None


def test_what_the_child_made_in_the_relay_home_belongs_to_the_owner_afterwards(dispatch):
    # last of the module: it removes the home, as the product's discard does
    site, _ = dispatch
    (site.home / "made.txt").write_text("owner again", encoding="utf-8")
    shutil.rmtree(site.home)
    assert not site.home.exists() and site.key.is_dir() and site.other.is_dir()


def test_the_relay_folder_is_made_protected_with_system_and_its_owner_only_and_checked_again(
        tmp_path):
    from conductor.command.adapters import _winlaunch
    site = RelaySite(tmp_path)
    sddl, protected, owner = snapshot_of(site.relay)
    assert protected is True and _winlaunch.acl_equal(sddl, relay_root_sddl(owner))
    assert ProcessRunner.ensure_relay_root(site.login) == site.relay, "a second call only checks"
    assert snapshot_of(site.relay)[:2] == (sddl, protected)


@pytest.mark.parametrize("how", [
    "inheritance", "everyone", "all-application-packages", "internet-client"])
def test_a_relay_folder_with_another_dacl_is_refused_by_the_helper_and_by_the_runner(
        tmp_path, how):
    from tests import os_boundary_windows as ac
    site = RelaySite(tmp_path)
    if how == "inheritance":
        ac._icacls(str(site.relay), "/inheritance:e")
    else:
        sid = {"everyone": "S-1-1-0", "all-application-packages": "S-1-15-2-1",
               "internet-client": "S-1-15-3-1"}[how]
        ac.grant(site.relay, sid, "R")
    before = snapshot_of(site.relay)
    with pytest.raises(ProfileRefused, match="protected with SYSTEM and its owner"):
        ProcessRunner.ensure_relay_root(site.login)
    assert snapshot_of(site.relay) == before, "the helper repairs nothing"
    refused_before_a_profile(site, "protected with SYSTEM and its owner")


@pytest.mark.parametrize("sid, where", [
    ("S-1-15-2-1", "key"), ("S-1-15-3-1", "key"), ("S-1-15-2-1", "home"), ("S-1-15-3-1", "home")])
def test_a_key_folder_or_relay_home_with_an_entry_for_a_container_is_refused_by_the_runner(
        tmp_path, sid, where):
    # The phrase is the rule for a container's entry (`ace_refusal`), which is judged before the
    # rule that a folder holds no entry of its own: either would refuse, only one says why.
    from tests import os_boundary_windows as ac
    site = RelaySite(tmp_path)
    ac.grant(site.key if where == "key" else site.home, sid, "R")
    refused_before_a_profile(
        site, f"the {'key folder' if where == 'key' else 'relay home'} has an entry for ALL "
              "APPLICATION PACKAGES, a package or a capability")


@pytest.mark.parametrize("where", ["key", "relay home"])
def test_a_key_folder_or_relay_home_with_an_entry_of_its_own_is_refused_by_the_runner(
        tmp_path, where):
    # An entry for no container at all (Everyone), but one the folder did not inherit: the rule
    # that they hold only what they inherit, which the container phrase above never reaches.
    from tests import os_boundary_windows as ac
    site = RelaySite(tmp_path)
    ac.grant(site.key if where == "key" else site.home, "S-1-1-0", "R")
    refused_before_a_profile(
        site, f"the {'key folder' if where == 'key' else where} has an entry of its own")


@pytest.mark.parametrize("sid", ["S-1-15-2-1", "S-1-15-3-1"])
def test_a_leaf_of_the_real_login_home_with_its_own_entry_for_a_container_is_refused(
        tmp_path, sid):
    # The leaf is what a container reads (next test), so its own DACL is judged beside the home's
    # and the parent's: by the readiness, and again by the runner at the grant.
    from conductor.command.adapters import _winlaunch
    from tests import os_boundary_windows as ac
    site = RelaySite(tmp_path)
    leaf = site.login / ".credentials.json"
    assert relay_acl_refusal(_winlaunch, site.login, site.home) is None
    ac.grant(leaf, sid, "R")
    why = ("the login home entry .credentials.json has an entry for ALL APPLICATION PACKAGES, "
           "a package or a capability")
    assert relay_acl_refusal(_winlaunch, site.login, site.home) == why
    assert relay_acl_refusal(_winlaunch, site.login) == why
    refused_before_a_profile(site, why)
    ac._icacls(str(leaf), "/remove:g", f"*{sid}")
    assert relay_acl_refusal(_winlaunch, site.login, site.home) is None


def test_the_runners_own_question_is_the_one_the_transport_asks_before_and_after_the_home(
        tmp_path):
    """`ProcessRunner.relay_acl_refusal` hands the helper its native calls, with or without a home.

    The transport asks it twice (`relay_attempt`): with the login only, at its readiness, and with
    the relay home it has just made. The login side is the same answer for both; the relay side
    only the second one reads.
    """
    from tests import os_boundary_windows as ac
    site = RelaySite(tmp_path)
    assert ProcessRunner.relay_acl_refusal(site.login) is None
    assert ProcessRunner.relay_acl_refusal(site.login, site.home) is None
    ac.grant(site.login / ".credentials.json", "S-1-15-2-1", "R")
    login_side = ("the login home entry .credentials.json has an entry for ALL APPLICATION "
                  "PACKAGES, a package or a capability")
    assert ProcessRunner.relay_acl_refusal(site.login) == login_side
    assert ProcessRunner.relay_acl_refusal(site.login, site.home) == login_side


def test_the_runners_own_question_reads_the_relay_home_only_when_it_is_given_one(tmp_path):
    from tests import os_boundary_windows as ac
    site = RelaySite(tmp_path)
    ac.grant(site.home, "S-1-1-0", "R")

    assert ProcessRunner.relay_acl_refusal(site.login) is None
    assert ProcessRunner.relay_acl_refusal(site.login, site.home) == (
        "the relay home has an entry of its own: it may hold only what it inherits")


def test_a_leaf_with_an_all_packages_entry_is_read_by_a_child_though_its_home_is_closed(tmp_path):
    # The control of the refusal above: without it a child reads the leaf by its full path. The
    # entry is added AFTER the runner's check, so the attempt starts: the exposure itself, which
    # the check keeps from ever reaching a child (the home and `logins` stay closed throughout).
    from tests import os_boundary_windows as ac
    from tests.os_boundary_box import WITHOUT_CMDLETS, base_environment
    site = RelaySite(tmp_path)
    leaf = site.login / ".credentials.json"
    script = (WITHOUT_CMDLETS + "$o = ''; " + _try_read("leaf_read", leaf)
              + _probe("list", f"[void][IO.Directory]::GetFileSystemEntries({_q(site.login)})")
              + "[Console]::Out.Write($o)")
    entry, runner = write_ps1(site.install / "entry.ps1", script), ProcessRunner(site.root)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(process_loans, "configured_login_sources",
                      lambda data_root: process_loans.ConfiguredLogins((site.login,)))
        with ownership.acquire_owner(site.root):
            with runner.container_profile(internet_client=True, mode="dispatch",
                                          folders=site.folders) as (boundary, paths):
                ac.grant(leaf, "S-1-15-2-1", "R")
                outcome = runner.run(CommandSpec(
                    (str(ac.POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                     "Bypass", "-File", str(entry)), "work/t1",
                    env=base_environment(paths["runtime"]), boundary=boundary,
                    timeout_seconds=60))
    read = dict(item.split("=") for item in strict_text(outcome.output).split(";") if item)
    assert read == {"leaf_read": "ok", "list": DENIED}, describe(outcome)


def test_a_real_login_home_or_logins_folder_with_an_entry_for_a_container_is_refused_twice(
        tmp_path):
    # by the readiness (`relay_acl_refusal`) and again by the runner at the grant, which reads the
    # same folders itself and creates no profile
    from conductor.command.adapters import _winlaunch
    from tests import os_boundary_windows as ac
    site = RelaySite(tmp_path)
    assert relay_acl_refusal(_winlaunch, site.login, site.home) is None
    for sid in ("S-1-15-2-1", "S-1-15-3-1"):
        for folder, what in ((site.login, "login home"), (site.logins, "logins folder")):
            ac.grant(folder, sid, "R")
            reason = relay_acl_refusal(_winlaunch, site.login, site.home)
            assert reason is not None and reason.startswith(f"the {what} has an entry for"), (
                sid, what, reason)
            refused_before_a_profile(site, f"the {what} has an entry for ALL APPLICATION PACKAGES")
            ac._icacls(str(folder), "/remove:g", f"*{sid}")
            assert relay_acl_refusal(_winlaunch, site.login, site.home) is None, (sid, what)


def test_another_projects_relay_home_or_a_home_outside_the_relay_folder_is_refused_by_the_runner(
        tmp_path):
    site = RelaySite(tmp_path)
    elsewhere = tmp_path / "elsewhere" / "h"
    elsewhere.mkdir(parents=True)
    for home, reason in ((site.other, "another project"), (elsewhere, "relay home is refused")):
        refused_before_a_profile(site, reason, AttemptFolders(
            work="work/t1", home=str(home), install=str(site.install)))


def refused_before_a_profile(site: RelaySite, reason: str, folders=None) -> None:
    """The runner refuses the block's entry before a profile, a record or a grant exists."""
    runner, before = ProcessRunner(site.root), {k: snapshot_of(p) for k, p in everywhere(
        site).items() if p.exists()}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(process_loans, "configured_login_sources",
                      lambda data_root: process_loans.ConfiguredLogins((site.login,)))
        with ownership.acquire_owner(site.root):
            with pytest.raises(ProfileRefused, match="profile_acl_invalid: .*" + reason):
                with runner.container_profile(
                        internet_client=True, mode="dispatch",
                        folders=site.folders if folders is None else folders):
                    pytest.fail("the block must not be entered")
    journal = site.root / "conductor.v3" / "process-profiles"
    assert not journal.exists() or list(journal.glob("*")) == []
    for key, path in everywhere(site).items():
        if path.exists():
            assert snapshot_of(path) == before[key], key


@pytest.mark.parametrize("permissive", [False, True])
@pytest.mark.parametrize("leaf_name", ["kimi-code.json", "kimi-code-env-0e4f99c69cc27850.json"])
@pytest.mark.parametrize("relay", [True, False])
@pytest.mark.parametrize("managed", [True, False])
def test_claude_loan_checks_nested_kimi_source_before_grant(
        tmp_path, permissive, leaf_name, relay, managed):
    from conductor.command import operator_config
    from conductor.command.adapters.claude_code import CLAUDE_PROTOCOL
    from conductor.command.adapters.kimi_code import KIMI_PROTOCOL
    from conductor.command.adapters.provider import ProviderConfig
    from conductor.command.adapters.relay_home import ace_refusal
    from tests import os_boundary_windows as ac
    from tests.os_boundary_box import WITHOUT_CMDLETS, base_environment

    site = RelaySite(tmp_path)
    kimi = (site.logins if managed else tmp_path / "operator-selected") / "second-account"
    leaf = kimi / "credentials" / leaf_name
    leaf.parent.mkdir(parents=True)
    leaf.write_bytes(b"synthetic Windows ACL witness")
    unrelated = kimi / "other" / "ignored.txt"
    unrelated.parent.mkdir()
    unrelated.touch()
    ac.grant(unrelated, "S-1-15-2-1", "R")
    with ownership.acquire_owner(site.root):
        path = operator_config.provider_config_path(site.root / "conductor.v3")
        operator_config.save_provider_configs(path, [
            ProviderConfig(label, str(site.install / "tool.exe"), protocol,
                           auth="subscription", auth_home=str(home))
            for label, protocol, home in [("first", CLAUDE_PROTOCOL, site.login),
                                          ("second", KIMI_PROTOCOL, kimi)]], project_root=site.root)
        assert set(process_loans.configured_login_homes(path.parent)) == {site.login, kimi}
        for parent in (site.logins, kimi, leaf.parent):
            assert ace_refusal(snapshot_of(parent)[0]) is None, "fixture parent grants a package"
        if permissive:
            ac.grant(leaf, "S-1-15-2-1", "R")
        before = (snapshot_of(leaf), identity(leaf), leaf.stat().st_size)
        assert bool(ace_refusal(before[0][0])) == permissive, "fixture leaf DACL is incorrect"
        body = f"$s = [IO.File]::OpenRead({_q(leaf)}); $s.Dispose()"
        script = WITHOUT_CMDLETS + "$o=''; " + _probe("open", body) + "[Console]::Out.Write($o)"
        entry = write_ps1(site.install / "w4-open.ps1", script)
        runner = ProcessRunner(site.root)
        folders = site.folders if relay else AttemptFolders(
            work="work/t1", home=None, install=str(site.install))
        try:
            with runner.container_profile(internet_client=True, mode="dispatch",
                                          folders=folders) as (boundary, paths):
                outcome = runner.run(CommandSpec(
                    (str(ac.POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                     "Bypass", "-File", str(entry)), "work/t1",
                    env=base_environment(paths["runtime"]), boundary=boundary, timeout_seconds=60))
                actual = strict_text(outcome.output)
        except ProfileRefused as error:
            assert "the configured Kimi source has an entry for ALL APPLICATION PACKAGES" in str(
                error)
            journal = site.root / "conductor.v3" / "process-profiles"
            assert not journal.exists() or not list(journal.iterdir())
            actual = "refused before spawn"
        assert (snapshot_of(leaf), identity(leaf), leaf.stat().st_size) == before
        assert actual == ("refused before spawn" if permissive else f"open={DENIED};")


def test_a_custom_kimi_login_not_created_yet_allows_a_sibling_loan(tmp_path):
    from conductor.command import operator_config
    from conductor.command.adapters.claude_code import CLAUDE_PROTOCOL
    from conductor.command.adapters.kimi_code import KIMI_PROTOCOL
    from conductor.command.adapters.provider import ProviderConfig

    site = RelaySite(tmp_path)
    missing = tmp_path / "uncreated" / "logins elsewhere" / "new account"
    with ownership.acquire_owner(site.root):
        path = operator_config.provider_config_path(site.root / "conductor.v3")
        operator_config.save_provider_configs(path, [
            ProviderConfig(label, str(site.install / "tool.exe"), protocol,
                           auth="subscription", auth_home=str(home))
            for label, protocol, home in [("first", CLAUDE_PROTOCOL, site.login),
                                          ("second", KIMI_PROTOCOL, missing)]],
            project_root=site.root)
        with ProcessRunner(site.root).container_profile(
                internet_client=False, mode="dispatch", folders=site.folders) as (boundary, paths):
            assert boundary.sid and paths["home"] == site.home
        assert not (tmp_path / "uncreated").exists()


@pytest.mark.parametrize("replacement", ["new-file", "new-region", "junction", "hardlink"])
def test_changed_kimi_source_is_refused_at_actual_grant(tmp_path, monkeypatch, replacement):
    from conductor.command import operator_config
    from conductor.command.adapters.kimi_code import KIMI_PROTOCOL
    from conductor.command.adapters.process_profile import ProfileJournal
    from conductor.command.adapters.provider import ProviderConfig
    from tests._deep_tree import junction

    site = RelaySite(tmp_path)
    kimi = site.login
    directory = kimi / "credentials"
    directory.mkdir()
    leaf = directory / "kimi-code.json"
    leaf.touch()
    external = tmp_path / "independent"
    external.mkdir()
    sentinel = external / "kimi-code.json"
    sentinel.write_bytes(b"sentinel")
    sid_before = snapshot_of(sentinel)
    existing_id = identity(leaf)

    real_create = ProfileJournal.create_profile

    def replace_after_preflight(journal):
        result = real_create(journal)
        if replacement == "new-file":
            leaf.rename(directory / "old")
            leaf.touch()
            assert identity(leaf) != existing_id
        elif replacement == "new-region":
            (directory / "kimi-code-env-0e4f99c69cc27850.json").touch()
        elif replacement == "junction":
            directory.rename(kimi / "old")
            junction(directory, external)
        else:
            os.link(leaf, external / "other")
        return result

    monkeypatch.setattr(ProfileJournal, "create_profile", replace_after_preflight)
    with ownership.acquire_owner(site.root):
        path = operator_config.provider_config_path(site.root / "conductor.v3")
        operator_config.save_provider_configs(path, [ProviderConfig(
            "pinned", str(site.install / "tool.exe"), KIMI_PROTOCOL,
            auth="subscription", auth_home=str(kimi))], project_root=site.root)
        with pytest.raises(ProfileRefused, match="configured Kimi source"):
            with ProcessRunner(site.root).container_profile(
                    internet_client=False, mode="dispatch", folders=site.folders):
                pytest.fail("runner handed the child a changed source")
        assert snapshot_of(sentinel) == sid_before
        assert not list((path.parent / "process-profiles").glob("loan-*.json"))


def test_region_created_during_acl_change_refuses_the_child_and_returns_the_loan(
        tmp_path, monkeypatch):
    from conductor.command import operator_config
    from conductor.command.adapters import _winlaunch
    from conductor.command.adapters.kimi_code import KIMI_PROTOCOL
    from conductor.command.adapters.provider import ProviderConfig
    from tests import os_boundary_windows as ac

    site = RelaySite(tmp_path)
    kimi = site.logins / "independent-name"
    sibling = kimi / "credentials" / "kimi-code-env-0e4f99c69cc27850.json"
    sibling.parent.mkdir(parents=True)
    (sibling.parent / "kimi-code.json").touch()
    before = {key: snapshot_of(path) for key, path in site.locations().items()}
    real_set = _winlaunch.acl_set

    def appear(hold, sddl, *, protected):
        real_set(hold, sddl, protected=protected)
        if hold.path == site.home and not sibling.exists():
            sibling.touch()
            ac.grant(sibling, "S-1-15-2-1", "R")

    monkeypatch.setattr(_winlaunch, "acl_set", appear)
    with ownership.acquire_owner(site.root):
        path = operator_config.provider_config_path(site.root / "conductor.v3")
        operator_config.save_provider_configs(path, [ProviderConfig(
            "pinned", str(site.install / "tool.exe"), KIMI_PROTOCOL,
            auth="subscription", auth_home=str(kimi))], project_root=site.root)
        with pytest.raises(ProfileRefused, match="configured Kimi source has an entry"):
            with ProcessRunner(site.root).container_profile(
                    internet_client=False, mode="dispatch", folders=site.folders):
                pytest.fail("the process must not start after a grant-time ACL change")
        assert sibling.exists(), "control must insert the second region while granting the home"
        for key, target in site.locations().items():
            assert same_acl(snapshot_of(target), before[key]), key
