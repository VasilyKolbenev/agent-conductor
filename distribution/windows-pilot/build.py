"""Rebuild the original Windows Pilot 1 archive from its verified CI wheel."""
import argparse
import hashlib
import io
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


SOURCE = Path(__file__).resolve().parent
WHEEL = "agent_conductor-0.1.0-py3-none-any.whl"
FILENAME = "Arachnid-Windows-Pilot-7f6b825.zip"
ZIP_SHA = "7bff7440611c009782885d7eb47d1e4aef48efa42a56f6aa2ac40005dc468dd2"
WINDOWS_GUIDES = {"START-HERE.txt", "HARNESSES.txt"}


def build(wheel: Path, output_dir: Path) -> Path:
    """Check every release input before publishing the single verified output file."""
    archive = io.BytesIO()
    manifest = (SOURCE / "members.tsv").read_text(encoding="ascii").splitlines()
    with ZipFile(archive, "w") as output:
        for line in manifest:
            name, clock, expected = line.split("\t")
            path = wheel if name == WHEEL else SOURCE / name
            data = path.read_bytes()
            if name in WINDOWS_GUIDES or name == "Start.cmd":
                # The public guides and launcher shipped as Windows text. Git stores LF.
                if b"\r" in data or data.startswith(b"\xef\xbb\xbf"):
                    raise ValueError(f"{name} source must use LF and UTF-8 without a BOM")
                data = data.replace(b"\n", b"\r\n")
                if name in WINDOWS_GUIDES:
                    data = b"\xef\xbb\xbf" + data
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError(f"SHA-256 mismatch for {name}")
            hour, minute, second = map(int, clock.split(":"))
            info = ZipInfo(name, (2026, 11, 13, hour, minute, second))
            info.create_system = 0  # MS-DOS in the original ZIP central directory.
            info.external_attr = (0o100777 if name == "Start.cmd" else 0o100666) << 16
            output.writestr(info, data, compress_type=ZIP_DEFLATED, compresslevel=6)

    raw = archive.getvalue()
    if hashlib.sha256(raw).hexdigest() != ZIP_SHA:
        raise ValueError("Final ZIP differs from Windows Pilot 1; check the DEFLATE runtime")
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / FILENAME
    staging = NamedTemporaryFile(dir=output_dir, delete=False)
    staged = Path(staging.name)
    try:
        with staging:
            staging.write(raw)
        os.replace(staged, target)
    finally:
        staged.unlink(missing_ok=True)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True, help="path to the CI wheel")
    parser.add_argument("--output-dir", type=Path, required=True, help="ZIP destination directory")
    args = parser.parse_args()
    try:
        result = build(args.wheel, args.output_dir)
    except (ValueError, OSError) as error:
        parser.exit(1, f"{error}\n")
    print(f"{ZIP_SHA}  {result}")
