"""One controlled Windows child makes a tree deeper than 260 characters, inside a real AppContainer.

The first real attempt of cycle B ended `unknown` because Claude Code wrote its session files
336 characters deep under its TEMP and the cleanup at the exit of the boundary could not name them
(`process_acl._empty_owned`). This is that attempt with a PowerShell child, and nothing of the
vendor: in a real AppContainer on a loaned relay home (`test_relay_home_native`), the child makes a
deep tree in its TEMP (which the system puts under `runtime/Packages/<name>/AC/Temp` of the
attempt, whatever the environment says) and another in the relay home, through
the extended-length form, which is the only way a name that long can be made while
`LongPathsEnabled` is 0 (the child reports the length it made). The boundary is then left, and the
product's own steps follow: the attempt folder is gone, the profile is not known to the system, the
profile, the ACL record and the loan are retired, every DACL is as it was, and the relay home with
its deep tree is removed by the product's `login_relay.discard`.

One native file per process: `python -m pytest tests/test_long_path_native.py` alone, once per
code page.
"""
from __future__ import annotations

import json
import os

import pytest

from conductor import ownership
from conductor.command.adapters import login_relay, process_acl, process_boundary, process_loans
from conductor.command.adapters.process import CommandSpec, ProcessRunner
from conductor.ownership_journals_cli import recover_containers
from tests._boot_world import later_boot, measure
from tests._deep_tree import CLASSIC_LIMIT, LEVELS, WIDTH, named, plain, remove, standing
from tests._ps1 import describe, strict_text, write_ps1
from tests.test_process_loans_native import same_acl
from tests.test_process_login_native import _q, snapshot_of
from tests.test_relay_home_native import LEAVES, RelaySite, everywhere

pytestmark = pytest.mark.skipif(os.name != "nt", reason="native AppContainer ACL loans")

NAMES = (".credentials.json", ".claude.json")
#: `\\?\` for PowerShell, which reads a single-quoted string as it is written.
PREFIX = r"'\\?\'"


def making(label: str, base: str) -> str:
    """The child makes `LEVELS` folders of `WIDTH` characters under `base` and a file in the last.

    It reports the length of the path it made without the prefix, or the type and the HRESULT of
    the error the system gave, so a refused name is told from a name that was never tried.
    """
    return (f"try {{ $t = {PREFIX} + {base}; "
            f"for ($i = 0; $i -lt {LEVELS}; $i++) {{ $t += '\\' + ('d' * {WIDTH}) }}; "
            "[void][IO.Directory]::CreateDirectory($t); "
            "[IO.File]::WriteAllText($t + '\\log.txt', 'deep'); "
            f"$o += '{label}=' + ($t.Length - 4) + ';' }} catch {{ $e = $_.Exception; "
            f"$o += '{label}=' + $e.GetType().Name + '/' + ('{{0:X8}}' -f $e.HResult) + ';' }}; ")


def child_script(site: RelaySite) -> str:
    from tests.os_boundary_box import WITHOUT_CMDLETS
    temp = "[Environment]::GetEnvironmentVariable('TEMP')"
    return (WITHOUT_CMDLETS + "$o = ''; " + making("temp", temp) + making("relay", _q(site.home))
            + "[Console]::Out.Write($o)")


def deep_part(base) -> str:
    return os.path.join(str(base), *("d" * WIDTH for _ in range(LEVELS)))


class CutShort(Exception):
    """The exit of the boundary is cut short, as a crash does it: the cleanup never runs."""


def run_child(site: RelaySite, *, cut_short: bool = False) -> dict:
    from tests import os_boundary_windows as ac
    from tests.os_boundary_box import base_environment
    runner, seen = ProcessRunner(site.root), {"exit_error": None}
    entry = write_ps1(site.install / "entry.ps1", child_script(site))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(process_loans, "configured_login_homes", lambda data_root: (site.login,))
        if cut_short:
            def cut(self, record_path, **options):
                raise CutShort("the exit of the boundary was cut short")
            patch.setattr(process_acl.AttemptAclJournal, "retire", cut)
        with ownership.acquire_owner(site.root):
            seen["before"] = {k: snapshot_of(p) for k, p in everywhere(site).items()}
            with ProcessRunner.login_write_guard(site.root, str(site.login)):
                try:
                    with runner.container_profile(internet_client=True, mode="dispatch",
                                                  folders=site.folders) as (boundary, paths):
                        seen["paths"], seen["sid"] = dict(paths), boundary.sid
                        seen["outcome"] = runner.run(CommandSpec(
                            (str(ac.POWERSHELL), "-NoProfile", "-NonInteractive",
                             "-ExecutionPolicy", "Bypass", "-File", str(entry)), "work/t1",
                            env=base_environment(paths["runtime"]), boundary=boundary,
                            timeout_seconds=60))
                except Exception as error:  # noqa: BLE001 -- what leaving the boundary said:
                    # it is asserted by the tests, and the profile it left is taken away at the end
                    seen["exit_error"] = f"{type(error).__name__}: {error}"
            seen["after"] = {k: snapshot_of(p) for k, p in everywhere(site).items()}
    return seen


def take_away(site: RelaySite, seen: dict) -> None:
    """A run that was refused at its exit leaves a profile in the system and a deep tree on disk."""
    from conductor.command.adapters import _winlaunch
    sid = seen.get("sid")
    if sid is not None and (found := _winlaunch.inspect_profile(sid)) is not None:
        _winlaunch.delete_profile(found[0])
    remove(site.base)


@pytest.fixture(scope="module")
def attempt(tmp_path_factory):
    site = RelaySite(tmp_path_factory.mktemp("deep"))
    seen = {}
    try:
        seen.update(run_child(site))
        yield site, seen
    finally:
        take_away(site, seen)


def facts(seen) -> dict:
    return dict(item.split("=") for item in strict_text(seen["outcome"].output).split(";") if item)


def test_the_child_makes_a_tree_past_the_classic_limit_in_its_temp_and_in_the_relay_home(attempt):
    _site, seen = attempt
    assert "outcome" in seen, seen["exit_error"]
    outcome = seen["outcome"]
    assert outcome.status == "completed" and outcome.exit_code == 0, describe(outcome)
    made = facts(seen)
    assert set(made) == {"temp", "relay"}, made
    assert all(value.isdigit() and int(value) > CLASSIC_LIMIT for value in made.values()), (
        f"the child did not make two paths past {CLASSIC_LIMIT} characters: {made}")


def test_leaving_the_boundary_is_not_refused_for_the_tree_the_child_made(attempt):
    _site, seen = attempt
    assert seen["exit_error"] is None, seen["exit_error"]


def test_the_attempt_folder_with_the_childs_deep_temp_is_gone(attempt):
    _site, seen = attempt
    assert not standing(seen["paths"]["parent"]), "the attempt folder is still there"


def test_the_profile_is_no_longer_known_to_the_system(attempt):
    from conductor.command.adapters import _winlaunch  # the native helper, only to read the mapping
    _site, seen = attempt
    assert seen["sid"] is not None, seen["exit_error"]
    assert _winlaunch.inspect_profile(seen["sid"]) is None, "the profile mapping is still there"


def journal_of(site: RelaySite) -> dict:
    """The phase of each record of the journal, by kind: profile, ACL record and loan."""
    folder = site.root / "conductor.v3" / "process-profiles"
    return {path.name.split("-")[0]: json.loads(path.read_text(encoding="utf-8"))
            for path in (folder.iterdir() if folder.is_dir() else ())}


def phases(site: RelaySite) -> dict:
    return {kind: record["phase"] for kind, record in journal_of(site).items()}


def test_the_profile_the_acl_record_and_the_loan_are_retired_in_the_journal(attempt):
    site, _seen = attempt
    assert phases(site) == {"profile": "retired", "acl": "retired", "loan": "retired"}


def test_every_dacl_is_as_it_was_and_no_login_gate_was_opened(attempt):
    site, seen = attempt
    for key in everywhere(site):
        assert same_acl(seen["after"][key], seen["before"][key]), f"the DACL of {key} changed"
    assert process_boundary.LOGIN_LOAN_OPEN is False


def test_the_relay_home_with_its_deep_tree_is_removed_by_the_products_discard(attempt):
    site, _seen = attempt
    deep = deep_part(site.home)
    assert standing(deep + "\\log.txt"), "the child's deep tree is not in the relay home"
    assert sorted(path.name for path in site.home.iterdir()) == sorted((*LEAVES, "d" * WIDTH))

    assert login_relay.discard(site.home, NAMES) is True

    assert not standing(site.home) and not standing(deep), "the relay home is still there"
    assert site.key.is_dir() and site.other.is_dir(), "the product removed more than the home"


# --- the attempt a crash left: `conduct ownership recover-containers` ---------------------------


@pytest.fixture(scope="module")
def left_over(tmp_path_factory):
    """The same attempt, with the cleanup at its exit cut short: its folder and profile stay."""
    site = RelaySite(tmp_path_factory.mktemp("left"))
    seen = {}
    try:
        seen.update(run_child(site, cut_short=True))
        yield site, seen
    finally:
        take_away(site, seen)


def test_a_cut_short_exit_leaves_the_deep_attempt_folder_and_the_profile_standing(left_over):
    from conductor.command.adapters import _winlaunch
    site, seen = left_over
    assert seen["exit_error"] == "CutShort: the exit of the boundary was cut short", (
        seen["exit_error"])
    assert standing(seen["paths"]["parent"]), "the attempt folder is not there to be recovered"
    # the child's TEMP is not the folder it was told: the system puts it under `Packages\<name>`
    logs = [os.path.join(top, "log.txt") for top, _dirs, files in os.walk(named(
        seen["paths"]["runtime"])) if "log.txt" in files]
    assert len(logs) == 1 and len(plain(logs[0])) > CLASSIC_LIMIT, logs
    assert _winlaunch.inspect_profile(seen["sid"]) is not None
    assert phases(site)["acl"] == "applied" and phases(site)["profile"] == "created"


def test_without_a_restart_the_recovery_refuses_and_leaves_the_attempt_where_it_is(
        left_over, capsys):
    site, seen = left_over

    assert recover_containers(str(site.root), False) == 1

    assert "profile_acl_unproven" in capsys.readouterr().err
    assert standing(seen["paths"]["parent"]), "the recovery cleaned up without the proof"


def test_after_a_restart_the_recovery_removes_the_deep_attempt_folder_and_the_profile(
        left_over, monkeypatch, capsys):
    from conductor.command.adapters import _winlaunch
    site, seen = left_over
    measure(monkeypatch, later_boot(journal_of(site)["acl"]["boot"]))

    code = recover_containers(str(site.root), False)

    assert code == 0, capsys.readouterr().err
    assert not standing(seen["paths"]["parent"]), "the attempt folder is still there"
    assert _winlaunch.inspect_profile(seen["sid"]) is None, "the profile mapping is still there"
    assert phases(site) == {"profile": "retired", "acl": "retired", "loan": "retired"}
    for key in everywhere(site):
        assert same_acl(snapshot_of(everywhere(site)[key]), seen["before"][key]), key
