"""Install ONE selected wheel into a clean venv and walk the installed road on POSIX (Linux, macOS).

The CI job and a local run use this same runner. It refuses to run as root; copies the wheel into
the work directory and refuses it unless its sha256 is the one given; proves a genuine SIGINT on a
plain sleeper first; then: a stdlib venv, an offline install of that wheel alone (--no-index
--no-deps), provenance from installed_probe.py under -I (the package must import from the venv),
installed bytes == wheel bytes, every packaged panel file served, `conduct --help`, init ->
ownership activate -> status, and two `conduct up` lifetimes -- each checked over HTTP, stopped by
SIGINT to the server's own process group, and followed by `closed` ownership.
Before every other step, a bounded child times the stdlib HTTPServer start (its bind ends in a
reverse lookup of the bound address); that row is recorded as a diagnostic and never judged.
No provider is configured: this is the platform road, not a vendor account.

Ported from the WSL smoke that attested wheel 83dc8d85 on 25.09.2026; the Windows road is the
separate console-Ctrl+C runner, because POSIX signals do not exist there.

Usage: python scripts/wheel_road.py --wheel W --sha256 HEX [--work DIR] [--require-filesystem ext4]
Writes DIR/report.json and one .log per command. Exit 0 only when every step held.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
import traceback
import urllib.request
import zipfile

ENDPOINTS = ("/state.json", "/harnesses.json", "/command/session", "/command/tasks",
             "/command/workflows", "/command/runs", "/command/quotas")
SCREENS = ("Overview", "Workflow", "Runs", "Decisions", "Agents")
PROBE = Path(__file__).resolve().with_name("installed_probe.py")
#: The ORIGINAL stdlib start the product no longer takes: HTTPServer's bind ends in
#: socket.getfqdn(host). Timed in its own child, then the lookup alone a second time: a second
#: value near the first says no cache helped, so a fast candidate start is the product's own.
STDLIB_BIND_CONTROL = "\n".join((
    "import http.server, socket, time",
    "started = time.monotonic()",
    "server = http.server.HTTPServer(('127.0.0.1', 0), http.server.BaseHTTPRequestHandler)",
    "print('seconds_http_server_cold', round(time.monotonic() - started, 3), flush=True)",
    "server.server_close()",
    "started = time.monotonic()",
    "socket.getfqdn('127.0.0.1')",
    "print('seconds_getfqdn_second', round(time.monotonic() - started, 3), flush=True)"))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Road:
    """One walk: its work directory, the child environment and the report it fills."""

    def __init__(self, work: Path) -> None:
        self.work = work
        # C.UTF-8 is a Linux locale; macOS ships en_US.UTF-8. UTF-8 mode holds either way.
        locale = "en_US.UTF-8" if sys.platform == "darwin" else "C.UTF-8"
        self.env = {"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), "LANG": locale,
                    "PYTHONNOUSERSITE": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
                    # A server that never prints its address is asked for every thread's stack
                    # (SIGABRT, see wait_url): the first macOS run of frozen-19 was silent for 30 s.
                    "PYTHONFAULTHANDLER": "1"}
        self.report: dict = {"host": platform_facts(), "work": str(work), "commands": [],
                             "servers": [], "success": False}

    def run(self, name: str, argv: list, timeout: int = 300) -> str:
        """Run one command in the work directory; its output is kept as NAME.log."""
        argv = [str(part) for part in argv]
        done = subprocess.run(argv, env=self.env, cwd=self.work, capture_output=True, text=True,
                              timeout=timeout)
        (self.work / f"{name}.log").write_text(done.stdout + done.stderr, encoding="utf-8")
        self.report["commands"].append({"name": name, "argv": argv, "exit_code": done.returncode})
        if done.returncode != 0:
            raise RuntimeError(f"{name} exited {done.returncode}: {done.stderr[-400:]}")
        return done.stdout


def platform_facts() -> dict:
    return {"uname": dict(zip(("sysname", "nodename", "release", "version", "machine"),
                              os.uname())),
            "platform": platform.platform(), "mac_ver": platform.mac_ver()[0],
            "python": sys.version, "uid": os.getuid(), "euid": os.geteuid()}


def filesystem_of(path: Path) -> str:
    """The mount type holding PATH where /proc/mounts says so; 'unknown' elsewhere (macOS)."""
    mounts = Path("/proc/mounts")
    if not mounts.is_file():
        return "unknown"
    best = ("", "unknown")
    for line in mounts.read_text().splitlines():
        _device, point, kind = line.split()[:3]
        if str(path).startswith(point) and len(point) > len(best[0]):
            best = (point, kind)
    return best[1]


def control(road: Road) -> None:
    """The instrument's own witness: a plain sleeper must die of the SIGINT this runner sends.

    Its KeyboardInterrupt traceback is the expected death and goes to control-sleeper.log.
    """
    with (road.work / "control-sleeper.log").open("wb") as log:
        sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                   env=road.env, cwd=road.work, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            time.sleep(1.0)
            os.killpg(sleeper.pid, signal.SIGINT)
            code = sleeper.wait(timeout=10)
        finally:
            if sleeper.poll() is None:  # a failed delivery must not leave the sleeper behind
                os.killpg(sleeper.pid, signal.SIGKILL)
                sleeper.wait(timeout=10)
    road.report["control_sleeper_exit"] = code
    if code not in (-signal.SIGINT, 128 + signal.SIGINT):
        raise RuntimeError(f"SIGINT did not stop a plain sleeper (exit {code}); "
                           "the runner cannot attest a stop")


def stdlib_bind_control(road: Road, timeout: float = 120.0) -> None:
    """Time the stdlib HTTPServer start in a separate child, first; recorded, never judged.

    It runs before any other step of this walk, so no step of the walk has touched the resolver
    yet; the CI steps before the walk are not controlled. Whatever it measures, the road's
    verdict stays the candidate's. At the deadline its process group is killed and the row says
    timed_out; its output is kept as stdlib-bind-control.log.
    """
    row: dict = {"seconds_http_server_cold": None, "seconds_getfqdn_second": None,
                 "exit_code": None, "timed_out": False}
    road.report["stdlib_bind_control"] = row
    log = road.work / "stdlib-bind-control.log"
    try:
        with log.open("wb") as out:
            child = subprocess.Popen([sys.executable, "-I", "-c", STDLIB_BIND_CONTROL],
                                     env=road.env, cwd=road.work, stdin=subprocess.DEVNULL,
                                     stdout=out, stderr=subprocess.STDOUT,
                                     start_new_session=True)
            try:
                child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                row["timed_out"] = True
            finally:
                if child.poll() is None:  # a deadline never leaves the control behind
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=10)
        row["exit_code"] = child.returncode
        text = log.read_text(errors="replace")
        for name, seconds in re.findall(r"^(seconds_\w+) (\d+(?:\.\d+)?)$", text, re.M):
            if name in row:
                row[name] = float(seconds)
    except (OSError, subprocess.SubprocessError) as error:  # recorded; the road goes on
        row["error"] = repr(error)


def http_checks(url: str, provenance: dict) -> int:
    """Each served asset byte-equal to its installed file, the five screens, each read endpoint."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    checks = 0
    for route, facts in sorted(provenance["routes"].items()):
        with opener.open(url + route, timeout=5) as response:
            body = response.read()
            assert response.status == 200 and response.geturl() == url + route, route
            assert response.headers["Content-Type"] == facts["content_type"], route
        assert sha(body) == provenance["files"]["panel/" + facts["file"]], route
        if route == "/":
            shell = body.decode("utf-8")
            for screen in SCREENS:
                assert f'id="screen{screen}"' in shell and f'id="nav{screen}"' in shell, screen
        checks += 1
    packaged = {name[len("panel/"):] for name in provenance["files"] if name.startswith("panel/")}
    served = {facts["file"] for facts in provenance["routes"].values()}
    assert packaged == served, {"unserved": sorted(packaged - served),
                                "missing": sorted(served - packaged)}
    for route in ENDPOINTS:
        with opener.open(url + route, timeout=5) as response:
            assert response.status == 200 and response.geturl() == url + route, route
            assert isinstance(json.loads(response.read()), (dict, list)), route
        checks += 1
    return checks


def wait_url(process: subprocess.Popen, log: Path, row: dict, timeout: float) -> str:
    """The address `conduct up` prints and how long it took; a silence is diagnosed, not waited.

    An exit and a silence are told apart. A server still silent at the deadline gets SIGABRT, and
    PYTHONFAULTHANDLER writes every thread's stack to its stderr log before it dies.
    """
    started = time.monotonic()
    while not (found := re.search(r"http://127\.0\.0\.1:\d+/", log.read_text(errors="replace"))):
        if process.poll() is not None:
            row["exit_before_address"] = process.returncode
            raise RuntimeError(f"conduct up exited {process.returncode} before printing an address")
        if time.monotonic() - started > timeout:
            row["silent_after_seconds"] = timeout
            os.kill(process.pid, signal.SIGABRT)
            process.wait(timeout=10)
            raise RuntimeError(f"conduct up printed no address in {timeout} s; its thread stacks "
                               "are in its stderr log")
        time.sleep(0.05)
    row["seconds_to_address"] = round(time.monotonic() - started, 2)
    return found.group(0).rstrip("/")


def serve_once(road: Road, conduct: Path, project: Path, number: int, timeout: float) -> None:
    """One `conduct up` lifetime: HTTP checks, SIGINT to its own group, exit 0, then `closed`.

    The row is kept in the report whatever breaks, so a failure keeps its own facts.
    """
    out, err = road.work / f"server-{number}.stdout.log", road.work / f"server-{number}.stderr.log"
    row: dict = {"graceful_stop": False}
    road.report["servers"].append(row)
    with out.open("wb") as stdout, err.open("wb") as stderr:
        process = subprocess.Popen([str(conduct), "up", "--port", "0", "--dir", str(project)],
                                   cwd=project, env=road.env, stdin=subprocess.DEVNULL,
                                   stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            url = wait_url(process, out, row, timeout)
            row["http_checks"] = http_checks(url, road.report["provenance"])
            os.killpg(process.pid, signal.SIGINT)
            started = time.monotonic()
            row["exit_code"] = process.wait(timeout=30)
            row["seconds_to_exit"] = round(time.monotonic() - started, 2)
            row["graceful_stop"] = row["exit_code"] == 0
        finally:
            if process.poll() is None:  # emergency cleanup is recorded, never a passing stop
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
                row["forced_cleanup"] = True
    status = road.run(f"status-after-{number}", [conduct, "ownership", "status", "--dir", project])
    row["status_after"] = json.loads(status)["state"]
    if not row["graceful_stop"] or row["status_after"] != "closed":
        raise RuntimeError(f"server {number} did not stop cleanly: {row}")


def install(road: Road, source: Path, expected: str) -> tuple[Path, Path]:
    """Copy and verify the ONE selected wheel, install it alone, and prove what was installed."""
    wheel = road.work / source.name
    shutil.copyfile(source, wheel)
    road.report["wheel"] = {"source": str(source), "sha256": sha(wheel.read_bytes())}
    if road.report["wheel"]["sha256"] != expected:
        raise RuntimeError("the copied wheel does not match the selected sha256")
    venv = road.work / "venv"
    road.run("venv", [sys.executable, "-I", "-m", "venv", venv])
    python, conduct = venv / "bin/python", venv / "bin/conduct"
    road.run("install", [python, "-I", "-m", "pip", "--isolated", "install", "--no-index",
                         "--no-deps", "--no-compile", "--disable-pip-version-check", wheel])
    road.report["provenance"] = json.loads(road.run("provenance", [python, "-I", PROBE]))
    with zipfile.ZipFile(wheel) as package:
        packaged = {name[len("conductor/"):]: sha(package.read(name))
                    for name in package.namelist()
                    if name.startswith("conductor/") and not name.endswith("/")}
    if packaged != road.report["provenance"]["files"]:
        raise RuntimeError("the installed package differs from the wheel")
    road.report["installed_files"] = len(packaged)
    return python, conduct


def walk(road: Road, args: argparse.Namespace) -> None:
    stdlib_bind_control(road)
    road.report["work_filesystem"] = filesystem_of(road.work)
    if args.require_filesystem and road.report["work_filesystem"] != args.require_filesystem:
        raise RuntimeError(f"work directory is on {road.report['work_filesystem']}, "
                           f"not {args.require_filesystem}")
    control(road)
    _python, conduct = install(road, args.wheel, args.sha256)
    if "ownership" not in road.run("help", [conduct, "--help"]):
        raise RuntimeError("conduct --help names no ownership command")
    project = road.work / "project"
    project.mkdir()
    road.run("init", [conduct, "init", "--template", "default-orbit", "--dir", project])
    road.run("activate", [conduct, "ownership", "activate", "--legacy-writers-stopped",
                          "--dir", project])
    status = road.run("status-active", [conduct, "ownership", "status", "--dir", project])
    road.report["status_active"] = json.loads(status)["state"]
    if road.report["status_active"] != "active":
        raise RuntimeError(f"ownership after activation is {road.report['status_active']}")
    for number in (1, 2):
        serve_once(road, conduct, project, number, args.up_timeout)


def arguments(argv: list[str] | None) -> argparse.Namespace:
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wheel", type=Path, required=True, help="the one selected wheel")
    parser.add_argument("--sha256", required=True, help="its expected sha256, lower-case hex")
    parser.add_argument("--work", type=Path, default=Path.home() / "dc-wheel-road" / stamp,
                        help="a new directory for the venv, project, logs and report.json")
    parser.add_argument("--up-timeout", type=float, default=120.0,
                        help="seconds `conduct up` may take to print its address (recorded)")
    parser.add_argument("--require-filesystem", default="",
                        help="refuse unless the work directory is on this mount type (WSL: ext4)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = arguments(argv)
    if os.name != "posix":
        raise SystemExit("a POSIX runner: SIGINT to a process group does not exist on Windows")
    if os.getuid() == 0 or os.geteuid() == 0:
        raise SystemExit("refusing to run as root")
    args.work.mkdir(parents=True)
    road = Road(args.work)
    try:
        walk(road, args)
        road.report["success"] = True
    except Exception:  # any failed step is recorded with its traceback; the exit code says it
        road.report["error"] = traceback.format_exc()
    finally:
        provenance = road.report.pop("provenance", None)
        if provenance is not None:
            road.report["provenance"] = {key: provenance[key]
                                         for key in ("python", "prefix", "package", "version")}
        (args.work / "report.json").write_text(json.dumps(road.report, indent=1), encoding="utf-8")
    print(json.dumps({"success": road.report["success"], "work": str(args.work),
                      "stdlib_bind_control": road.report.get("stdlib_bind_control"),
                      "servers": road.report["servers"],
                      "error": road.report.get("error", "")[-600:]}))
    return 0 if road.report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
