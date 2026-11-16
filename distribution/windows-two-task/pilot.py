"""Open Arachnid Studio on Windows with the sample run or your saved tasks."""
from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
WHEEL = "agent_conductor-0.1.1-py3-none-any.whl"
DEMO_SHA256 = "812aebdae11ac0114a24b7e94e04fa1ae1bc8097889643d18647276a2a2c6941"
MEMBERS = (WHEEL, "demo.zip", "pilot.py", "first_task.py", "studio.py", "START.cmd",
           "START-HERE.txt")
FLAGS = ("-I", "-B", "-X", "utf8")


def verify():
    entries = {}
    for line in (HERE / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        if name not in MEMBERS or name in entries or not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("Invalid SHA256SUMS.txt entry")
        entries[name] = digest
    if set(entries) != set(MEMBERS):
        raise ValueError("Incomplete SHA256SUMS.txt")
    if entries["demo.zip"] != DEMO_SHA256:
        raise ValueError("Unexpected offline example: demo.zip")
    for name, expected in entries.items():
        if hashlib.sha256((HERE / name).read_bytes()).hexdigest() != expected:
            raise ValueError("SHA-256 mismatch: " + name)
    return entries[WHEEL]


def field(prompt, limit, optional=False):
    while True:
        value = input(prompt + " ").strip()
        if (value or optional) and len(value) <= limit and (not value or value.isprintable()):
            return value
        print(f"Введите одну строку длиной до {limit} знаков.")


def collect_record():
    print("Выберите завершённую задачу и следующую, для которой пригодится её опыт.")
    first = field("Первая задача:", 200)
    second = field("Вторая задача:", 200)
    print("Запишите по порядку проверки, которые вы действительно выполнили в первой задаче.")
    checks = []
    for number in range(1, 13):
        question = f"Проверка {number}" + (" (Enter — закончить)" if checks else "") + ":"
        label = field(question, 160, optional=bool(checks))
        if not label:
            break
        checks.append((label, field("Что показала эта проверка?", 600)))
    performer = field("Кто выполнил работу? (Enter — пропустить)", 100, optional=True)
    outcome = field("Итог первой задачи (Enter — пропустить):", 600, optional=True)
    reviewer = field("Кто подтверждает запись? Укажите имя или псевдоним:", 100)
    print(f"\nПервая задача — {first}\nВторая задача — {second}\nИсточник: со слов оператора.")
    for index, (label, observation) in enumerate(checks, 1):
        print(f"{index}. {label}\n   Наблюдение: {observation}")
    if performer:
        print("Исполнитель:", performer)
    if outcome:
        print("Итог:", outcome)
    print("Запись подтверждает:", reviewer)
    answer = input("Введите ПРИНЯТЬ, чтобы сохранить эту запись, или Enter для отмены: ")
    if answer.strip().casefold() not in ("принять", "accept"):
        return None
    return dict(first=first, second=second, checks=checks, reviewer=reviewer,
                performer=performer, outcome=outcome, accepted=True)


def child_env(work):
    env = {key: os.environ[key] for key in
           ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT",
            "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS") if key in os.environ}
    profile = work / "profile"
    folders = {"HOME": profile, "USERPROFILE": profile, "APPDATA": profile / "Roaming",
               "LOCALAPPDATA": profile / "Local", "TEMP": work / "tmp", "TMP": work / "tmp",
               "CONDUCT_HOME": work / "hub"}
    for key, path in folders.items():
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    env.update(PIP_CONFIG_FILE=os.devnull, PIP_NO_INDEX="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    return env


def unpack_demo(project):
    # The installed Studio calls this helper so it can use the product's long-path handling.
    from conductor.command.long_path import extended

    data = (HERE / "demo.zip").read_bytes()
    if hashlib.sha256(data).hexdigest() != DEMO_SHA256:
        raise ValueError("Unexpected offline example: demo.zip")
    destination = Path(extended(project))
    destination.mkdir()
    with ZipFile(BytesIO(data)) as archive:
        archive.extractall(destination)


def install_runtime(work):
    env = child_env(work)
    venv = work / "venv"
    subprocess.run([sys.executable, *FLAGS, "-m", "venv", str(venv)], env=env, cwd=work, check=True)
    python = str(venv / "Scripts/python.exe")
    subprocess.run([python, *FLAGS, "-m", "pip", "--isolated", "--disable-pip-version-check",
                    "install", "--no-index", "--no-deps", "--no-cache-dir", str(HERE / WHEEL)],
                   env=env, cwd=work, check=True)
    return python


def install_pair(base, record, wheel_sha):
    base.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="p-", dir=base))
    print("Папка задач:", work, flush=True)
    python = install_runtime(work)
    subprocess.run([python, *FLAGS, str(HERE / "studio.py"), "create", str(work)],
                   env=child_env(work), cwd=work, input=json.dumps(record).encode("ascii"), check=True)
    (work / "wheel.sha256").write_text(wheel_sha, encoding="ascii")
    with tempfile.NamedTemporaryFile(dir=base, delete=False) as pointer:
        pointer.write(work.name.encode("ascii"))
    Path(pointer.name).replace(base / "latest.txt")
    return work


def open_studio(runtime, data, action, options):
    cmd = [str(runtime / "venv/Scripts/python.exe"), *FLAGS, str(HERE / "studio.py"),
           action, str(data), "--port", str(options.port)]
    if options.no_browser:
        cmd.append("--no-browser")
    if options.stop_on_stdin_eof:
        cmd.append("--stop-on-stdin-eof")
    process = subprocess.Popen(cmd, env=child_env(runtime), cwd=runtime)
    try:
        return process.wait()
    except KeyboardInterrupt:
        return process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("open", "new", "demo", "verify"), nargs="?")
    parser.add_argument("--port", type=int, choices=range(65536), default=0, metavar="0..65535")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--stop-on-stdin-eof", action="store_true",
                        help="close Studio normally when the controlling input pipe closes")
    parser.add_argument("--work-parent", type=Path)
    options = parser.parse_args()
    wheel_sha = verify()
    print("Wheel SHA-256:", wheel_sha, flush=True)
    if options.mode == "verify":
        return 0
    if os.name != "nt" or sys.version_info[:2] not in ((3, 11), (3, 12)):
        raise ValueError("Use Python 3.11 or 3.12 on Windows.")
    base = (options.work_parent or Path.home() / "ArachnidStudio").resolve()
    latest = base / "latest.txt"
    if options.work_parent is None and not latest.exists():
        legacy = Path.home() / "ArachnidPilot2" / "latest.txt"
        if legacy.is_file():
            latest = legacy
    mode = options.mode or ("open" if latest.exists() else "demo")
    if mode == "demo":
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="demo-", dir=base) as directory:
            work = Path(directory)
            install_runtime(work)
            return open_studio(work, work, "demo", options)
    if mode == "new" or not latest.exists():
        record = collect_record()
        if record is None:
            print("Создание пары отменено.")
            return 0
        work = install_pair(base, record, wheel_sha)
    else:
        name = latest.read_text(encoding="ascii").strip()
        if not re.fullmatch(r"p-[a-z0-9_]+", name):
            raise ValueError("Invalid latest.txt. Use START.cmd new to start a separate pair.")
        work = latest.parent / name
        saved_sha = (work / "wheel.sha256").read_text(encoding="ascii")
        if not re.fullmatch("[0-9a-f]{64}", saved_sha):
            raise ValueError("Invalid saved wheel SHA-256. Check the saved task folder.")
        if saved_sha != wheel_sha or latest.parent != base:
            # Serve the existing records with the downloaded wheel in a separate environment.
            base.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="view-", dir=base) as directory:
                runtime = Path(directory)
                install_runtime(runtime)
                return open_studio(runtime, work, "open", options)
    print("Открываем сохранённую пару:", work, flush=True)
    return open_studio(work, work, "open", options)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EOFError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print("Arachnid Studio:", exc, file=sys.stderr)
        raise SystemExit(1)
