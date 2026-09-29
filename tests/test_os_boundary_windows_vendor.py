"""Windows AppContainer: a native binary, the network, a vendor home, and the account's ACLs.

Still a controlled child and throwaway directories: a copy of a System32 binary stands
in for a vendor executable, a dedicated directory for the vendor home, and no model is
called. What a green run here says is that the OS lets those things through with the
rights an attempt owns; it does not say a real vendor binary works in the container.
Two tests witness OS behaviour that a newer Windows may change (loopback, ReplaceFile).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from tests.os_boundary_layout import operations_for

pytestmark = pytest.mark.skipif(
    os.name != "nt", reason="needs Windows: AppContainer is a Windows mechanism")

if os.name == "nt":
    import winreg

    from tests import os_boundary_windows as ac
    from tests.os_boundary_box import (  # noqa: F401
        base_environment, container, implement_box, make_box, serve_loopback)

EXTERNAL = "https://example.com"
PRIVATE_NETWORK_CLIENT_SERVER = "S-1-15-3-3"
_MAPPINGS = (r"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion"
             r"\AppContainer\Mappings")
_UPDATE = "[IO.File]::WriteAllText('@VENDOR@\\auth.json','token=updated')"


def _install_binary(directory: Path) -> Path:
    directory.mkdir()
    target = directory / "whoami.exe"
    shutil.copy(ac.SYSTEM32 / "whoami.exe", target)
    return target


def _curl(url: str, *flags: str) -> str:
    return " ".join(['"' + str(ac.CURL) + '"', *flags, url])


@pytest.fixture
def internet():
    done = subprocess.run(
        [str(ac.CURL), "-s", "-m", "8", "-o", "NUL", "-w", "%{http_code}", EXTERNAL],
        capture_output=True, timeout=30, check=False)
    if done.returncode != 0 or done.stdout.strip() != b"200":
        pytest.skip("the test host has no outbound HTTPS route to example.com: a container "
                    "lacking one would prove nothing")


_START_SIBLINGS = (
    "function Try-Start($path) { try { $i = New-Object Diagnostics.ProcessStartInfo; "
    "$i.FileName = $path; $i.Arguments = '/user'; $i.UseShellExecute = $false; "
    "$i.RedirectStandardOutput = $true; $q = [Diagnostics.Process]::Start($i); "
    "[void]$q.StandardOutput.ReadToEnd(); $q.WaitForExit(); 'started' } catch { 'denied' } }; "
    "Write-Output ('granted=' + (Try-Start '@GRANTED@')); "
    "Write-Output ('ungranted=' + (Try-Start '@UNGRANTED@'))"
)


def test_the_runner_starts_a_binary_from_an_ungranted_directory_and_the_child_is_confined(
        implement_box):
    """CreateProcess maps the image with the CREATOR's rights: the container is not asked."""
    box = implement_box
    ungranted = _install_binary(box.layout.base / "ungranted-bin")
    started = box.run_line('"' + str(ungranted) + '" /groups')
    assert started.started and started.exit_code == 0, started
    assert "S-1-16-4096" in started.output, "the child ran, but not at the container's level"


def test_a_confined_child_can_start_a_helper_binary_only_from_a_directory_it_was_granted(
        implement_box):
    box = implement_box
    granted = _install_binary(box.layout.tmp / "bin")
    ungranted = _install_binary(box.layout.base / "ungranted-bin")
    script = _START_SIBLINGS.replace("@GRANTED@", str(granted))
    script = script.replace("@UNGRANTED@", str(ungranted))
    confined = box.run_script(script)
    control = box.run_script(script, confined=False)
    assert "granted=started" in confined.output and "ungranted=denied" in confined.output, confined
    assert "ungranted=started" in control.output, "the unconfined control cannot start it either"


def test_outbound_network_needs_the_internet_client_capability(implement_box, internet):
    box = implement_box
    line = _curl(EXTERNAL, "-s", "-m", "12", "-o", "NUL", "-w", "%{http_code}")
    without = box.run_line(line)
    granted = box.run_line(line, capabilities=(ac.INTERNET_CLIENT,))
    assert without.output.strip() != "200", "the container reached the network with no capability"
    assert granted.output.strip() == "200", granted


def test_loopback_to_a_server_of_the_parent_is_blocked_even_with_the_network_capabilities(
        implement_box):
    box = implement_box
    with serve_loopback() as served:
        control = subprocess.run([str(ac.CURL), "-s", "-m", "5", served.url],
                                 capture_output=True, timeout=30, check=False)
        assert control.stdout == b"served-by-parent", "the parent's own server does not answer"
        blocked = box.run_line(
            _curl(served.url, "-s", "-m", "6"),
            capabilities=(ac.INTERNET_CLIENT, PRIVATE_NETWORK_CLIENT_SERVER))
        assert "served-by-parent" not in blocked.output, blocked
        assert len(served.hits) == 1, "only the parent's own request may have arrived"


def test_a_dedicated_vendor_home_takes_a_credential_update_in_place_without_a_copy(
        implement_box):
    box = implement_box
    vendor = box.layout.vendor_home
    before = os.stat(vendor / "auth.json")
    outcome = box.run_script(_UPDATE)
    assert outcome.started and outcome.exit_code == 0, outcome
    assert (vendor / "auth.json").read_bytes() == b"token=updated"
    assert os.stat(vendor / "auth.json").st_ino == before.st_ino, "a different file now stands"
    assert os.listdir(vendor) == ["auth.json"], "the update left a second file behind"


def test_a_credential_file_can_be_replaced_by_a_native_rename_over_it_in_the_vendor_home(
        implement_box):
    box = implement_box
    vendor = box.layout.vendor_home
    (vendor / "new.tmp").write_bytes(b"NEW")
    outcome = box.run_native_move_replace("@VENDOR@\\new.tmp", "@VENDOR@\\auth.json")
    assert outcome.output.strip() == "ok=True", outcome
    assert (vendor / "auth.json").read_bytes() == b"NEW"


def test_replacefile_over_the_credential_file_is_refused_with_the_rights_this_grant_gives(
        implement_box):
    box = implement_box
    vendor = box.layout.vendor_home
    script = ("[IO.File]::Replace('@VENDOR@\\new.tmp','@VENDOR@\\auth.json',"
              "'@VENDOR@\\auth.bak')")
    (vendor / "new.tmp").write_bytes(b"NEW")
    box.run_script(script)
    assert (vendor / "auth.json").read_bytes() != b"NEW", "ReplaceFile now works in the container"
    box.run_script(script, confined=False)
    assert (vendor / "auth.json").read_bytes() == b"NEW", "the control replace did not work"


def test_the_project_stays_unreadable_in_the_launch_that_updates_the_vendor_home(
        implement_box):
    box = implement_box
    script = (_UPDATE + "; try { [void][IO.File]::ReadAllText('@SRC@\\file.txt'); "
              "Write-Output 'project=readable' } catch { Write-Output 'project=unreadable' }")
    outcome = box.run_script(script)
    assert "project=unreadable" in outcome.output, outcome
    assert (box.layout.vendor_home / "auth.json").read_bytes() == b"token=updated"


def _acls(base: Path) -> dict[str, str]:
    """The ACL text of what an attempt must never change: the account's and the project's."""
    watched = [base, base.parent, Path(tempfile.gettempdir()), Path(os.environ["USERPROFILE"]),
               ac.CMD, ac.POWERSHELL]
    return {str(path): ac.acl_text(path) for path in watched}


def test_no_watched_acl_changes_across_the_profile_lifetime_and_each_grant_is_one_entry(tmp_path):
    """The baseline precedes the profile and the grants, and is compared after its deletion."""
    before = _acls(tmp_path)
    with ac.Container() as owned:
        box = make_box(tmp_path, owned, ac.MODIFY)
        layout, sid = box.layout, owned.sid
        source_before = box.snapshot("source")
        for operation in operations_for("source"):
            box.run(operation, root="source")
        box.run_script(_UPDATE)
        assert _acls(tmp_path) == before, "an ACL changed while the profile existed"
        assert box.snapshot("source") == source_before
        for granted in (layout.tmp, layout.home, layout.vendor_home, layout.work):
            assert ac.acl_text(granted).count(sid) == 1, granted
        for untouched in (layout.source, layout.base):
            assert sid not in ac.acl_text(untouched), untouched
    assert _acls(tmp_path) == before, "an ACL changed once the profile was deleted"


def test_deleting_the_profile_removes_its_mapping_and_folder_and_a_launch_for_it_fails():
    packages_root = Path(os.environ["LOCALAPPDATA"]) / "Packages"
    with ac.Container() as gone:
        name, sid = gone.name, gone.sid
        assert (packages_root / name).exists()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _MAPPINGS + "\\" + sid):
            pass
    assert not (packages_root / name).exists()
    with pytest.raises(FileNotFoundError):
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, _MAPPINGS + "\\" + sid)
    scratch = Path(tempfile.gettempdir())
    with pytest.raises(OSError):
        ac.launch('"' + str(ac.CMD) + '" /d /c exit 0', sid=sid, cwd=str(scratch),
                  env=base_environment(scratch))
