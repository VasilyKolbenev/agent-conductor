"""Build a portable two-task pilot from a wheel and its independently verified SHA-256."""
import argparse
import hashlib
from io import BytesIO
import os
from pathlib import Path
import runpy
from tempfile import NamedTemporaryFile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

SOURCE = Path(__file__).resolve().parent
launcher = runpy.run_path(str(SOURCE / "pilot.py"))
WHEEL, MEMBERS = launcher["WHEEL"], launcher["MEMBERS"]
FILENAME = "Arachnid-Windows-Pilot-2.zip"


def atomic_write(target, data):
    stream = NamedTemporaryFile(dir=target.parent, delete=False)
    staging = Path(stream.name)
    try:
        with stream:
            stream.write(data)
        os.replace(staging, target)
    finally:
        staging.unlink(missing_ok=True)


def build(wheel: Path, expected: str, output_dir: Path) -> Path:
    if wheel.name != WHEEL:
        raise ValueError("Expected wheel filename: " + WHEEL)
    wheel_bytes = wheel.read_bytes()
    if hashlib.sha256(wheel_bytes).hexdigest() != expected.lower():
        raise ValueError("Wheel SHA-256 mismatch")
    payload = {}
    for name in MEMBERS:
        if name == WHEEL:
            data = wheel_bytes
        else:
            data = (SOURCE / name).read_bytes().replace(b"\r\n", b"\n")
        if name.endswith((".cmd", ".txt")):
            data = data.replace(b"\n", b"\r\n")
        if name == "START-HERE.txt":
            data = b"\xef\xbb\xbf" + data
        payload[name] = data
    payload["SHA256SUMS.txt"] = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\r\n" for name, data in payload.items()
    ).encode("ascii")
    raw = BytesIO()
    with ZipFile(raw, "w") as archive:
        for name, data in payload.items():
            info = ZipInfo(name)
            info.create_system = 0
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compress_type=ZIP_DEFLATED, compresslevel=6)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / FILENAME
    data = raw.getvalue()
    atomic_write(target, data)
    digest = hashlib.sha256(data).hexdigest()
    atomic_write(target.with_suffix(".zip.sha256"), f"{digest}  {FILENAME}\r\n".encode("ascii"))
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--wheel-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(build(args.wheel, args.wheel_sha256, args.output_dir))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
