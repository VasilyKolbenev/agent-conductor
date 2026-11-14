"""Launch the bundled offline Windows pilot in a fresh local environment."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import os
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
WHEEL = "agent_conductor-0.1.0-py3-none-any.whl"
WHEEL_SHA = "214bf5e5beb0822f4616ded0dce44161e76e1f9d557d9c5507ec40939acd40fe"
PAYLOAD = {WHEEL, "demo.zip", "show-demo.py", "utility-lab.py", "examples/echo-peer.py"}


def verify():
    sums = {}
    for line in (HERE / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        if name in sums or name not in PAYLOAD:
            raise ValueError("Unexpected file in SHA256SUMS")
        sums[name] = digest
    if set(sums) != PAYLOAD or sums[WHEEL] != WHEEL_SHA:
        raise ValueError("This is not the 7f6b825 pilot manifest")
    for name, expected in sums.items():
        if hashlib.sha256((HERE / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Checksum mismatch: " + name)


def unpack(project):
    with ZipFile(HERE / "demo.zip") as archive:
        for entry in archive.infolist():
            path = PurePosixPath(entry.filename)
            if (path.is_absolute() or ".." in path.parts or ":" in entry.filename
                    or "\\" in entry.filename or entry.is_dir()):
                raise ValueError("Invalid demo entry")
            target = project.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as out:
                out.write(archive.read(entry))


def child_env(work):
    # Only basic Windows facilities and this pilot's own directories are inherited.
    env = {key: os.environ[key] for key in
           ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT",
            "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS") if key in os.environ}
    profile = work / "profile"
    for key, path in (("HOME", profile), ("USERPROFILE", profile),
                      ("APPDATA", profile / "Roaming"), ("LOCALAPPDATA", profile / "Local"),
                      ("TEMP", work / "tmp"), ("TMP", work / "tmp"),
                      ("CONDUCT_HOME", work / "hub")):
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    env["PIP_CONFIG_FILE"] = os.devnull
    env["PIP_NO_INDEX"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    return env


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("mode", nargs="?", default="demo", choices=["demo", "utilities", "echo", "verify"])
    args.add_argument("--port", type=int, default=0, choices=range(65536), metavar="0..65535")
    args.add_argument("--work-parent", type=Path, default=Path.home() / "ArachnidPilot")
    options = args.parse_args()
    verify()
    print("Wheel SHA-256 verified:", WHEEL_SHA, flush=True)
    if options.mode == "verify":
        return 0
    if os.name != "nt" or sys.version_info[:2] not in ((3, 11), (3, 12)):
        raise ValueError("Use Python 3.11 or 3.12 on Windows.")
    base = options.work_parent.resolve()
    base.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="p-", dir=base))
    env = child_env(work)
    project = work / "project"
    venv = work / "venv"
    py = venv / "Scripts/python.exe"
    print("Pilot folder:", work, flush=True)
    subprocess.run([sys.executable, "-I", "-m", "venv", str(venv)],
                   env=env, cwd=work, check=True)
    subprocess.run([str(py), "-I", "-m", "pip", "--isolated", "--disable-pip-version-check",
                    "install", "--no-deps", "--no-index", "--no-cache-dir", str(HERE / WHEEL)],
                   env=env, cwd=work, check=True)
    if options.mode == "echo":
        origin = input("Paste the loopback URL from the utilities window: ").strip().rstrip("/")
        match = re.fullmatch(r"http://127\.0\.0\.1:([1-9][0-9]{0,4})", origin)
        if not match or int(match[1]) > 65535:
            raise ValueError("Use the local utilities URL with its port.")
        peer = HERE / "examples/echo-peer.py"
        answers = str(py) + "\n" + json.dumps(["-I", "-B", str(peer)], ensure_ascii=True) + "\n"
        bridge = [str(py), "-I", "-B", "-X", "utf8", "-m", "conductor", "utility-bridge",
                  "--server", origin, "--utility", "local-echo", "--once"]
        return subprocess.run(bridge, input=answers.encode("utf-8"), cwd=work, env=env).returncode
    if options.mode == "demo":
        unpack(project)
        script = HERE / "show-demo.py"
    else:
        script = HERE / "utility-lab.py"
    cmd = [str(py), "-I", "-B", "-X", "utf8", str(script),
           "--dir", str(project), "--port", str(options.port)]
    proc = subprocess.Popen(cmd, cwd=work, env=env)
    try:
        return proc.wait()
    except KeyboardInterrupt:
        # Both share the console. Allow the foreground server to finish its normal shutdown.
        return proc.wait()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print("Pilot:", exc, file=sys.stderr)
        raise SystemExit(1)
