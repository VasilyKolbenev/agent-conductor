"""Check the standalone pinned file set without starting a vendor or installing a product."""
import hashlib
import os
from pathlib import Path
import subprocess
from zipfile import ZipFile

import pytest


@pytest.fixture
def kit(tmp_path, monkeypatch):
    from scripts import kimi_windows_kit as tool

    archive = tmp_path / "kimi.zip"
    with ZipFile(archive, "w") as package:
        package.writestr("kimi.exe", b"vendor exe")
    git = tmp_path / "git"
    git.mkdir()
    contents = {"kimi.exe": b"vendor exe", "shell/sh.exe": b"vendor shell",
                "shell/msys-2.0.dll": b"vendor runtime"}
    for path, payload in contents.items():
        if path.startswith("shell/"):
            (git / Path(path).name).write_bytes(payload)
    digest = lambda data: hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(tool, "FILES", {k: (len(v), digest(v)) for k, v in contents.items()})
    monkeypatch.setattr(tool, "ZIP", (archive.stat().st_size, digest(archive.read_bytes())))
    return tool, archive, git, tmp_path / "bundle", contents


def prepared(kit):
    tool, archive, git, dest, contents = kit
    dest.mkdir()
    (dest / "shell").mkdir()
    for name, data in contents.items():
        (dest / name).write_bytes(data)
    return tool, dest


@pytest.mark.parametrize("name", ["kimi.exe", "shell/sh.exe", "shell/msys-2.0.dll"])
def test_checker_rejects_same_size_replacement(kit, name):
    tool, dest = prepared(kit)
    result = tool.inspect(dest)
    assert result["shell"] == str(dest / "shell" / "sh.exe")
    assert set(result["files"]) == {"kimi.exe", "shell/sh.exe", "shell/msys-2.0.dll"}
    path = dest / name
    path.write_bytes(b"X" * path.stat().st_size)
    with pytest.raises(tool.KitRefused, match="digest"):
        tool.inspect(dest)


@pytest.mark.parametrize("bad", ["extra", "missing", "hardlink"])
def test_exact_layout_refuses_unreviewed_objects(kit, bad):
    tool, dest = prepared(kit)
    if bad == "extra":
        (dest / "shell/version.dll").write_bytes(b"unreviewed dll")
    elif bad == "missing":
        (dest / "shell/msys-2.0.dll").unlink()
    else:
        os.link(dest / "shell/sh.exe", dest.parent / "outside")
    with pytest.raises(tool.KitRefused):
        tool.inspect(dest)


@pytest.mark.skipif(os.name != "nt", reason="Windows no-replace directory publication")
def test_staging_is_new_only_and_fails_without_publishing_a_partial_kit(kit):
    tool, archive, git, dest, contents = kit
    (git / "msys-2.0.dll").write_bytes(b"X" * len(contents["shell/msys-2.0.dll"]))
    with pytest.raises(tool.KitRefused):
        tool.stage(archive, git, dest)
    assert not dest.exists()
    (git / "msys-2.0.dll").write_bytes(contents["shell/msys-2.0.dll"])
    result = tool.stage(archive, git, dest)
    assert result == tool.inspect(dest)
    with pytest.raises(tool.KitRefused, match="exists"):
        tool.stage(archive, git, dest)
    assert (dest / "kimi.exe").read_bytes() == contents["kimi.exe"]


def test_builder_rejects_the_actual_protected_install_path_before_writing(kit):
    tool, archive, git, _, _ = kit
    with pytest.raises(tool.KitRefused, match="protected"):
        tool.stage(archive, git, Path.home() / "DecemberCommand/harnesses/kimi-code/0.38.0")


@pytest.mark.skipif(os.name != "nt", reason="Windows sharing and ACL inheritance")
def test_verified_files_stay_held_and_an_inheritance_cut_refuses_the_kit(kit):
    tool, dest = prepared(kit)
    file = dest / "shell/msys-2.0.dll"
    with tool.verified_bundle(dest):
        with pytest.raises(PermissionError):
            file.write_bytes(b"replace")
    before = file.read_bytes()
    subprocess.run(["icacls", str(dest), "/inheritance:d"], capture_output=True, check=True)
    with pytest.raises(tool.KitRefused, match="inheritance"):
        tool.inspect(dest)
    assert file.read_bytes() == before


@pytest.mark.skipif(os.name != "nt", reason="Windows no-replace directory publication")
def test_unreviewed_zip_layout_refuses_before_directory_publication(kit, monkeypatch):
    tool, archive, git, dest, _ = kit
    with ZipFile(archive, "a") as package:
        package.writestr("../other.exe", b"extra")
    # A valid digest cannot grant an additional member, even under a different input pin.
    monkeypatch.setattr(tool, "ZIP", (archive.stat().st_size,
                                      hashlib.sha256(archive.read_bytes()).hexdigest()))
    with pytest.raises(tool.KitRefused, match="archive layout"):
        tool.stage(archive, git, dest)
    assert not dest.exists() and not (dest.parent / "other.exe").exists()
