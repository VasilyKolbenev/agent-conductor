"""Run the Windows ZIP entry point with and without an installed Python runtime."""
import hashlib
import os
import shutil
import subprocess
import venv
from pathlib import Path
from runpy import run_path
from threading import Event, Thread
from zipfile import ZipFile

import pytest


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows console entry point")
SOURCE = Path(__file__).resolve().parents[1] / "distribution/windows-two-task"


@pytest.fixture
def bundle(tmp_path):
    builder = run_path(str(SOURCE / "build.py"))
    wheel = tmp_path / builder["WHEEL"]
    wheel.write_bytes(b"sample wheel bytes")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    root = tmp_path / "Kit with spaces"
    with ZipFile(builder["build"](wheel, digest, tmp_path)) as package:
        package.extractall(root)
    return root


def launch_env(root):
    return {**os.environ, "PATH": str(root / "runtime/Scripts"),
            "LOCALAPPDATA": str(root / "local"),
            "PYLAUNCHER_ALLOW_INSTALL": "1", "PYLAUNCHER_ALWAYS_INSTALL": "1",
            "PYTHON_MANAGER_AUTOMATIC_INSTALL": "true"}


def cmd():
    return Path(os.environ["SystemRoot"]) / "System32/cmd.exe"


def stop_test_console(process):
    if process.poll() is None:
        # A failed assertion can leave cmd and choice holding the fixture's working directory.
        subprocess.run([str(cmd().with_name("taskkill.exe")), "/pid", str(process.pid), "/t", "/f"],
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=10)


@pytest.mark.parametrize("args", [[], ["verify"]])
def test_missing_python_returns_an_official_route_without_blocking(bundle, args):
    supply_manager(bundle, "qbz5n2kfra8p0", 1)
    result = subprocess.run([str(cmd()), "/d", "/c", "START.cmd", *args],
                            cwd=bundle, env=launch_env(bundle), stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=15)
    assert result.returncode == 1
    assert b"https://www.python.org/downloads/windows/" in result.stdout
    assert b"pymanager install 3.12" in result.stdout
    assert b"[O]" not in result.stdout
    assert not (bundle / "manager-calls").exists()


def test_supported_python_on_path_receives_verify_and_returns_wheel_hash(bundle):
    venv.EnvBuilder().create(bundle / "runtime")
    result = subprocess.run([str(cmd()), "/d", "/c", "START.cmd", "verify"],
                            cwd=bundle, env=launch_env(bundle), stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert hashlib.sha256(b"sample wheel bytes").hexdigest().encode() in result.stdout


def test_explicit_command_in_a_real_console_returns_without_requesting_a_key(bundle):
    (bundle / "verify.cmd").write_text(
        "@echo off\ncall START.cmd verify\n>status.txt echo %errorlevel%\n", encoding="ascii")
    command = [str(cmd().with_name("conhost.exe")), "--headless", str(cmd()), "/d", "/c",
               "verify.cmd"]
    with subprocess.Popen(command, cwd=bundle, env=launch_env(bundle), stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as process:
        try:
            process.wait(10)
        finally:
            stop_test_console(process)
        output = process.stdout.read()
    assert (bundle / "status.txt").read_text().strip() == "1"
    assert b"pymanager install 3.12" in output
    assert b"[Q]" not in output


def supply_manager(root, family, status):
    # A real venv executable doubles for the package alias. Only the "install" command is faked:
    # it records argv and makes a previously prepared runtime visible if the install succeeded.
    apps = root / "local/Microsoft/WindowsApps"
    fake = root / "stub-manager"
    venv.EnvBuilder().create(fake)
    alias = apps / f"PythonSoftwareFoundation.PythonManager_{family}"
    alias.mkdir(parents=True)
    shutil.copyfile(fake / "Scripts/python.exe", alias / "pymanager.exe")
    shutil.copyfile(fake / "pyvenv.cfg", alias / "pyvenv.cfg")
    (root / "install").write_text(
        "import sys\nfrom pathlib import Path\n"
        "with Path('manager-calls').open('a') as out: print(repr(sys.argv[1:]),file=out)\n"
        + ("Path('standby').rename('runtime')\n" if status == 0 else "") + f"sys.exit({status})\n",
        encoding="ascii")


@pytest.mark.parametrize(("key", "family", "install_status"), [
    ("Q", None, None), ("R", None, None), ("H", None, None),
    ("I", "3847v3x7pw1km", 0), ("I", "qbz5n2kfra8p0", 1),
])
def test_interactive_setup_requires_a_choice_and_continues_or_stops(bundle, key, family,
                                                                     install_status):
    # conhost's own exit code is independent of the child cmd's exit code.
    (bundle / "parent.cmd").write_text(
        "@echo off\ncall START.cmd\n>status.txt echo %errorlevel%\n", encoding="ascii")
    (bundle / "pilot.py").write_text(
        "import os,sys\nfrom pathlib import Path\n"
        "assert os.environ['PYTHON_MANAGER_AUTOMATIC_INSTALL'] == 'false'\n"
        "assert not {'PYLAUNCHER_ALLOW_INSTALL', 'PYLAUNCHER_ALWAYS_INSTALL'} & os.environ.keys()\n"
        "assert sys.argv[1:] == []\nPath('pilot-ran').touch()\n", encoding="ascii")
    if family:
        supply_manager(bundle, family, install_status)
    else:
        (bundle / "pymanager.exe").write_bytes(b"unrelated file beside the ZIP launcher")
    if key == "R" or install_status == 0:
        venv.EnvBuilder().create(bundle / "standby")
    command = [str(cmd().with_name("conhost.exe")), "--headless", "--width", "160",
               str(cmd()), "/d", "/c", "parent.cmd"]
    with subprocess.Popen(command, cwd=bundle, env=launch_env(bundle), stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as process:
        output = bytearray()
        ready, returned = Event(), Event()

        def watch_prompt():
            while block := os.read(process.stdout.fileno(), 1024):
                output.extend(block)
                if b"[Q] quit:" in output:
                    ready.set()
                if output.count(b"[Q] quit:") >= 2:
                    returned.set()
            ready.set()

        reader = Thread(target=watch_prompt, daemon=True)
        reader.start()
        try:
            assert ready.wait(15) and b"[Q] quit:" in output, bytes(output)
            assert process.poll() is None
            assert not (bundle / "manager-calls").exists()
            assert (b"[I]" in output) == bool(family)
            if key == "R":
                (bundle / "standby").rename(bundle / "runtime")
            process.stdin.write(key.encode())
            process.stdin.flush()
            if install_status == 1 or key == "H":
                assert returned.wait(15), bytes(output)
                detail = b"Installation did not complete" if key == "I" else b"START.cmd new"
                assert detail in output, bytes(output)
                process.stdin.write(b"Q")
                process.stdin.flush()
            process.wait(15)
        finally:
            stop_test_console(process)
            reader.join(5)
    did_launch = key == "R" or install_status == 0
    assert (bundle / "status.txt").read_text().strip() == ("0" if did_launch else "1")
    assert (bundle / "pilot-ran").exists() == did_launch
    if family:
        assert (bundle / "manager-calls").read_text().splitlines() == ["['3.12']"]
