"""A tree deeper than the classic 260-character path limit, made through the extended-length form.

A child inside the boundary can make one (its TEMP, a vendor's project folders), and the product
must walk and remove it. The tree is made here by the test, so the length is a fact the test
creates and checks (`LONGEST`), not a setting of the machine: where long plain names work, the
tree is still longer than the limit, and only the Windows machine with `LongPathsEnabled` = 0
shows the failure these tests are for. `without_long_paths` gives any machine that failure.

The second thing it makes is a name the system reads as another one when given in its plain
form (`odd_name`): `foo ` and `foo.` are `foo`, `...` is the folder above. Only the
extended-length form says such a name as it is, so it is built and asked about as it is.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

#: The form that names a deep path on Windows; nothing is needed where a plain name works.
PREFIX = "\\\\?\\" if os.name == "nt" else ""
CLASSIC_LIMIT = 260
#: The folders and their width: with a short pytest base the deepest file is about 350 characters.
LEVELS, WIDTH = 11, 25
#: For a test of a name that exists as itself only on Windows (see `odd_name`).
reads_as_another = pytest.mark.skipif(
    os.name != "nt", reason="only Windows reads a name with a trailing dot or space as another")


def plain(path) -> str:
    """A path without the extended-length prefix, as a person would write it."""
    text = os.fspath(path)
    return text[len(PREFIX):] if PREFIX and text.startswith(PREFIX) else text


def named(path) -> str:
    """The extended-length name of a path, for the calls the test itself makes.

    A name that already has the prefix is returned as it is, as `extended` does: it is the name
    of one entry, and cleaning it again would ask about another (`...` is the folder above).
    """
    text = os.fspath(path)
    if PREFIX and text.startswith(PREFIX):
        return text
    return PREFIX + plain(os.path.abspath(text))


def deep_tree(top, *, content: bytes = b"deep") -> SimpleNamespace:
    """Make `LEVELS` nested folders and files under `top`; return where everything is.

    A file at the deepest level, one in a side folder half way down and one at the top, so a walk
    that stops early leaves something behind.

    Returns:
        `bottom` (the deepest folder), `leaf` (the file in it), `files` (every file made) and
        `folders` (every folder made, shallowest first), all as extended-length strings.
    """
    top = os.path.abspath(plain(top))
    chain = [top]
    for _ in range(LEVELS):
        chain.append(os.path.join(chain[-1], "d" * WIDTH))
    bottom = chain[-1]
    side = os.path.join(chain[LEVELS // 2], "side")
    os.makedirs(PREFIX + bottom)
    os.makedirs(PREFIX + side)
    files = [os.path.join(bottom, "log.txt"), os.path.join(side, "side.txt"),
             os.path.join(top, "top.txt")]
    for file in files:
        Path(PREFIX + file).write_bytes(content)
    assert len(files[0]) > CLASSIC_LIMIT, (
        f"the deepest file is {len(files[0])} characters: not past the {CLASSIC_LIMIT}-character "
        "limit this test is about; the base folder is too shallow or the tree too short")
    return SimpleNamespace(
        bottom=PREFIX + bottom, leaf=PREFIX + files[0],
        files=[PREFIX + file for file in files], folders=[PREFIX + item for item in chain[1:]])


def odd_name(parent, name: str) -> str:
    """`parent\\name` as written, in the extended-length form: `name` may be `foo `, `foo.`, `...`.

    A parent that is already such a name (`named` leaves it as it is) is joined as it is.
    """
    return os.path.join(named(parent), name)


def without_long_paths(monkeypatch, limit: int = CLASSIC_LIMIT) -> None:
    """Answer "not found" to a plain name of `limit` characters or more, as Windows does with
    `LongPathsEnabled` = 0, whatever the machine; a name in the extended-length form goes to the
    real system. Where the machine already refuses them this changes nothing.
    """
    def refusing(real):
        def ask(path=".", *args, **kwargs):
            text = os.fspath(path) if isinstance(path, (str, os.PathLike)) else ""
            if PREFIX and len(text) >= limit and not text.startswith(PREFIX):
                raise FileNotFoundError(3, "The system cannot find the path specified", text)
            return real(path, *args, **kwargs)
        return ask

    for call in ("lstat", "stat", "scandir", "listdir", "rmdir", "unlink"):
        monkeypatch.setattr(os, call, refusing(getattr(os, call)))


def junction(link, target) -> None:
    """A directory junction at `link` (which may be a deep, extended-length name) to `target`;
    a symbolic link where there are no junctions."""
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(plain(target), os.fspath(link))
    else:
        os.symlink(os.fspath(target), os.fspath(link), target_is_directory=True)


def hard_link(existing, new) -> None:
    os.link(os.fspath(existing), os.fspath(new))


def standing(path) -> bool:
    """Whether anything stands at `path`, asked in the extended-length form: a deep name is seen,
    and a name with the prefix (`odd_name`) is asked as it is."""
    return os.path.lexists(named(path))


def remove(path) -> None:
    """Take a test's own deep tree away when the product's code could not (a failing test).

    It never removes the folder the tests run from, or one above it: an empty name is the working
    folder, and a command that removes a tree must not be one slip from removing the project.
    """
    base = os.path.abspath(plain(path))
    try:
        above = os.path.commonpath([os.getcwd(), base]) == base
    except ValueError:  # another drive: not above the working folder
        above = False
    if above:
        raise ValueError(f"refusing to remove {base}: it is the working folder or holds it")
    target = named(base)
    if os.name == "nt" and os.path.lexists(target):
        subprocess.run(["cmd", "/c", "rd", "/s", "/q", target], capture_output=True)
