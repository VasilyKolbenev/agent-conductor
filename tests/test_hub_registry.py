"""The registry of projects, `<conduct-home>/registry.json` (spec 4.1.3, 4.1.13 item 8, 8.2 step 7).

What is judged, in file order: the bytes (canonical, read back whole); the strict read (every
way a file can be not the schema, each refused `registry_invalid` by name, and the file is
never rewritten over what the owner must look at); the lock (two real processes adding at once
lose nothing, a held lock is `registry_busy`, the lock file is made when it is absent); the
rules of the entries (uniqueness, the suffix of a name, `name_invalid`, the ports); and the
small writes the hub makes itself (remove an entry, the projects folder).

The registry touches no project folder: the root and its identity arrive as values, so none of
these tests needs a project on disk.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import conductor
from conductor import ownership_records
from conductor.hub import registry
from conductor.ownership_native import NativeHold

PROJECT_ID = "3f9c0d5a7b2e4c168a90d3e1f4b7a625"
OTHER_ID = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
NOW = "2026-09-30T10:00:00Z"
ROOT = "C:\\Users\\User\\Projects\\web-app" if os.name == "nt" else "/home/user/projects/web-app"
OTHER_ROOT = ROOT.replace("web-app", "landing")
REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path(conductor.__file__).resolve().parents[1]


def a_project(**changes) -> dict:
    """One project as the file spells it."""
    record = {"project_id": PROJECT_ID, "name": "web-app", "root": ROOT,
              "root_identity": [1234, 5678], "port": 7701, "source": "folder", "repo": None,
              "added_at": NOW}
    return {**record, **changes}


def a_file(*projects: dict, **changes) -> dict:
    return {**{"schema_version": 1, "projects_home": None, "projects": list(projects)}, **changes}


def write_file(home: Path, document: object) -> Path:
    path = home / "registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(document if isinstance(document, bytes)
                     else json.dumps(document).encode("utf-8"))
    return path


def add(home: Path, *, project_id=PROJECT_ID, root=ROOT, identity=(1234, 5678), **more):
    return registry.add_project(
        project_id=project_id, root=root, root_identity=identity, folder=home, now=NOW, **more)


# -- the bytes ----------------------------------------------------------------------------


def test_a_missing_file_is_an_empty_registry_and_reading_writes_nothing(tmp_path):
    assert registry.load(tmp_path) == registry.Registry(None, ())
    assert list(tmp_path.iterdir()) == []


def test_the_file_is_canonical_json_and_reads_back_whole(tmp_path):
    project, how = add(tmp_path)
    assert how == "new" and project.port == 7701
    document = a_file(a_project())
    assert (tmp_path / "registry.json").read_bytes() == ownership_records.canonical(document)
    loaded = registry.load(tmp_path)
    assert loaded.projects == (project,) and loaded.projects_home is None
    assert loaded.projects[0].root_identity == (1234, 5678)


def test_the_digest_changes_with_the_bytes_and_is_none_without_a_file(tmp_path):
    assert registry.digest(tmp_path) is None
    add(tmp_path)
    first = registry.digest(tmp_path)
    add(tmp_path, project_id=OTHER_ID, root=OTHER_ROOT, identity=(9, 9))
    assert first is not None and registry.digest(tmp_path) not in (None, first)


# -- the strict read ---------------------------------------------------------------------

BAD_DOCUMENTS = {
    "an unknown key at the top": a_file(a_project(), extra=1),
    "an unknown key in a project": a_file({**a_project(), "extra": 1}),
    "a missing key in a project": a_file({k: v for k, v in a_project().items() if k != "repo"}),
    "a schema version of 2": a_file(schema_version=2),
    "a schema version that is true": a_file(schema_version=True),
    "a schema version that is a string": a_file(schema_version="1"),
    "projects that is not a list": a_file(projects={}),
    "a project that is not an object": a_file("web-app"),
    "projects_home that is a number": a_file(projects_home=5),
    "projects_home that is relative": a_file(projects_home="ConductProjects"),
    "a project id in capitals": a_file(a_project(project_id=PROJECT_ID.upper())),
    "a project id of 31 characters": a_file(a_project(project_id=PROJECT_ID[:-1])),
    "a name with a line break": a_file(a_project(name="web\napp")),
    "an empty name": a_file(a_project(name="")),
    "a name of 65 characters": a_file(a_project(name="x" * 65)),
    "a root that is relative": a_file(a_project(root="web-app")),
    "a root with a NUL": a_file(a_project(root=ROOT + "\u0000")),
    "an identity of three numbers": a_file(a_project(root_identity=[1, 2, 3])),
    "an identity of floats": a_file(a_project(root_identity=[1.0, 2.0])),
    "an identity that is negative": a_file(a_project(root_identity=[-1, 2])),
    "an identity that is true": a_file(a_project(root_identity=[True, 2])),
    "a port below the range": a_file(a_project(port=7700)),
    "a port above the range": a_file(a_project(port=7800)),
    "the port of the standalone up": a_file(a_project(port=7777)),
    "a port that is a string": a_file(a_project(port="7701")),
    "a port that is true": a_file(a_project(port=True)),
    "an unknown source": a_file(a_project(source="ftp")),
    "a repo without an owner": a_file(a_project(repo="web-app")),
    "a repo with a space": a_file(a_project(repo="owner/web app")),
    "a time without the Z": a_file(a_project(added_at="2026-09-30T10:00:00")),
    "a time that is not a time": a_file(a_project(added_at="2026-13-45T10:00:00Z")),
    "a project id twice": a_file(a_project(), a_project(name="other", port=7702, root=OTHER_ROOT,
                                                         root_identity=[7, 7])),
    "a root twice": a_file(a_project(), a_project(project_id=OTHER_ID, name="other", port=7702,
                                                   root_identity=[7, 7])),
    "an identity twice": a_file(a_project(), a_project(project_id=OTHER_ID, name="other",
                                                        port=7702, root=OTHER_ROOT)),
    "a name twice without regard to case": a_file(a_project(), a_project(
        project_id=OTHER_ID, name="WEB-APP", port=7702, root=OTHER_ROOT, root_identity=[7, 7])),
    "a port twice": a_file(a_project(), a_project(
        project_id=OTHER_ID, name="other", root=OTHER_ROOT, root_identity=[7, 7])),
}
BAD_BYTES = {
    "broken JSON": b"{not json",
    "an array": b"[]",
    "a key twice": (b'{"schema_version":1,"schema_version":1,"projects_home":null,'
                    b'"projects":[]}'),
    "NaN": b'{"schema_version":1,"projects_home":NaN,"projects":[]}',
    "bytes that are not UTF-8": b'{"schema_version":1,"projects_home":"\xff","projects":[]}',
    "a file over 256 KiB": b" " * (256 * 1024 + 1),
}


@pytest.mark.parametrize("what", sorted({**BAD_DOCUMENTS, **BAD_BYTES}))
def test_a_file_that_is_not_the_schema_is_registry_invalid_by_name_and_never_rewritten(
        tmp_path, what):
    document = {**BAD_DOCUMENTS, **BAD_BYTES}[what]
    path = write_file(tmp_path, document)
    before = path.read_bytes()
    with pytest.raises(registry.RegistryError) as caught:
        registry.load(tmp_path)
    assert caught.value.code == "registry_invalid" and "registry.json" in caught.value.detail
    with pytest.raises(registry.RegistryError) as again:
        add(tmp_path, project_id=OTHER_ID, root=OTHER_ROOT, identity=(9, 9))
    assert again.value.code == "registry_invalid"
    assert path.read_bytes() == before, "the owner's file was rewritten"


def test_the_grammar_accepts_what_the_spec_shows_so_the_refusals_above_mean_something(tmp_path):
    write_file(tmp_path, a_file(a_project(), a_project(
        project_id=OTHER_ID, name="Проект «один»", root=OTHER_ROOT, root_identity=[7, 7],
        port=7799, source="github", repo="owner/web-app.v2"), projects_home=ROOT))
    loaded = registry.load(tmp_path)
    assert [project.name for project in loaded.projects] == ["web-app", "Проект «один»"]
    assert loaded.projects_home == ROOT and loaded.projects[1].repo == "owner/web-app.v2"


# -- the lock -----------------------------------------------------------------------------

_WORKER = """
import sys
from pathlib import Path
from conductor.hub import registry
home, tag, count = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
for number in range(count):
    root = (home.parent / "projects" / f"{tag}-{number}").as_posix()
    registry.add_project(
        project_id=f"{int(tag[-1]):08x}{number:024x}", root=root,
        root_identity=(int(tag[-1]), number + 1), name=f"{tag}-{number}", folder=home,
        now="2026-09-30T10:00:00Z")
"""


def _worker_environment() -> dict[str, str]:
    env = dict(os.environ)
    env.update(PYTHONPATH=os.pathsep.join((str(SOURCE_ROOT), str(REPO_ROOT))),
               PYTHONDONTWRITEBYTECODE="1")
    return env


def test_three_processes_adding_at_once_lose_nothing_and_share_no_port_or_name(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    workers = [subprocess.Popen(
        [sys.executable, "-c", _WORKER, str(home), f"p{tag}", "8"], env=_worker_environment(),
        stderr=subprocess.PIPE) for tag in range(3)]
    outputs = [worker.communicate(timeout=120)[1].decode() for worker in workers]
    assert [worker.returncode for worker in workers] == [0, 0, 0], outputs
    loaded = registry.load(home)
    assert len(loaded.projects) == 24
    assert len({project.port for project in loaded.projects}) == 24
    assert {project.port for project in loaded.projects} == set(range(7701, 7725))
    assert len({project.name.casefold() for project in loaded.projects}) == 24
    assert [entry.name for entry in home.iterdir() if entry.name.endswith(".tmp")] == []


def test_a_held_lock_is_registry_busy_after_its_bounded_tries_and_nothing_is_written(tmp_path):
    add(tmp_path)
    before = (tmp_path / "registry.json").read_bytes()
    hold = NativeHold(tmp_path / "registry.lock", exclusive=True)
    try:
        with pytest.raises(registry.RegistryError) as caught:
            registry.add_project(project_id=OTHER_ID, root=OTHER_ROOT, root_identity=(9, 9),
                                 folder=tmp_path, now=NOW, attempts=3, pause=0.001)
        assert caught.value.code == "registry_busy"
        assert (tmp_path / "registry.json").read_bytes() == before
    finally:
        hold.close()
    add(tmp_path, project_id=OTHER_ID, root=OTHER_ROOT, identity=(9, 9))
    assert len(registry.load(tmp_path).projects) == 2


def test_the_lock_file_is_made_when_it_is_absent_and_reading_takes_no_lock(tmp_path):
    hold_path = tmp_path / "registry.lock"
    assert not hold_path.exists()
    add(tmp_path)
    assert hold_path.is_file()
    hold = NativeHold(hold_path, exclusive=True)
    try:
        assert len(registry.load(tmp_path).projects) == 1, "a reader waited for the writer's lock"
    finally:
        hold.close()


# -- the rules of the entries --------------------------------------------------------------


def test_a_second_add_of_the_same_root_and_id_is_existing_and_writes_nothing(tmp_path):
    first, _ = add(tmp_path)
    before = (tmp_path / "registry.json").read_bytes()
    again, how = add(tmp_path, name="another name", source="github", repo="owner/web-app")
    assert how == "existing" and again == first
    assert (tmp_path / "registry.json").read_bytes() == before


@pytest.mark.parametrize(("project_id", "root", "identity"), [
    (OTHER_ID, ROOT, (1234, 5678)), (OTHER_ID, ROOT, (9, 9)),
    (OTHER_ID, OTHER_ROOT, (1234, 5678)), (PROJECT_ID, OTHER_ROOT, (9, 9))],
    ids=["same root and identity", "same root", "same identity", "same id at another root"])
def test_a_root_or_an_id_already_held_by_another_entry_is_root_already_registered(
        tmp_path, project_id, root, identity):
    add(tmp_path)
    before = (tmp_path / "registry.json").read_bytes()
    with pytest.raises(registry.RegistryError) as caught:
        add(tmp_path, project_id=project_id, root=root, identity=identity)
    assert caught.value.code == "root_already_registered"
    assert (tmp_path / "registry.json").read_bytes() == before


@pytest.mark.skipif(os.name != "nt", reason="only Windows folds the case of a path")
def test_a_root_spelled_in_another_case_is_the_same_root_on_windows(tmp_path):
    add(tmp_path)
    with pytest.raises(registry.RegistryError) as caught:
        add(tmp_path, project_id=OTHER_ID, root=ROOT.upper(), identity=(9, 9))
    assert caught.value.code == "root_already_registered"


def test_a_name_that_is_taken_gets_a_suffix_without_regard_to_case_and_the_root_is_untouched(
        tmp_path):
    made = []
    for number, name in enumerate(["web-app", "web-app", "WEB-APP", None], start=1):
        root = ROOT if number == 1 else f"{OTHER_ROOT}-{number}"
        project, _ = add(tmp_path, project_id=f"{number:032x}", root=root, identity=(number, 1),
                         name=name)
        made.append((project.name, project.root, root))
    assert [name for name, _, _ in made] == ["web-app", "web-app 2", "WEB-APP 3", "landing-4"]
    assert all(stored == given for _, stored, given in made), "a root was rewritten"


def test_the_default_name_is_the_name_of_the_last_folder_of_the_root(tmp_path):
    project, _ = add(tmp_path, name=None)
    assert project.name == "web-app"


def test_a_suffix_never_pushes_a_name_past_64_characters(tmp_path):
    long_name = "n" * 64
    add(tmp_path, name=long_name)
    second, _ = add(tmp_path, project_id=OTHER_ID, root=OTHER_ROOT, identity=(9, 9),
                    name=long_name)
    assert second.name == "n" * 62 + " 2" and len(second.name) == 64


@pytest.mark.parametrize("name", [
    "", " edge", "edge ", "a\nb", "a\tb", "a\u0000b", "\u202eevil", "a\u2028b", "x" * 65,
    "a\ud800b"], ids=repr)
def test_a_name_with_a_control_character_an_edge_space_or_a_wrong_length_is_name_invalid(
        tmp_path, name):
    with pytest.raises(registry.RegistryError) as caught:
        add(tmp_path, name=name)
    assert caught.value.code == "name_invalid"
    assert not (tmp_path / "registry.json").exists()


@pytest.mark.parametrize(
    "name", ["web-app", "Проект «один»", "C++ tools", "a.b_c (2)", "日本語", "x"])
def test_a_name_of_letters_digits_spaces_and_punctuation_of_any_script_is_accepted(
        tmp_path, name):
    assert add(tmp_path, name=name)[0].name == name


def test_the_ports_are_the_first_free_one_of_7701_to_7799_without_7777_and_the_hubs(tmp_path):
    assert registry.next_port(set(), None) == 7701
    assert registry.next_port({7701, 7703}, None) == 7702
    assert registry.next_port(set(), 7701) == 7702
    assert registry.next_port(set(range(7701, 7777)), None) == 7778
    assert registry.next_port(set(range(7701, 7777)) | {7778}, 7779) == 7780
    first, _ = add(tmp_path, hub_port=7701)
    assert first.port == 7702


def test_all_98_ports_used_is_ports_exhausted_and_nothing_is_written(tmp_path):
    every = [registry.Project(f"{number:032x}", f"p{number}", f"{OTHER_ROOT}-{number}",
                              (number, 1), port, "folder", None, NOW)
             for number, port in enumerate(
                 [p for p in range(7701, 7800) if p != 7777], start=1)]
    registry.mutate(lambda current: registry.Registry(None, tuple(every)), tmp_path)
    before = (tmp_path / "registry.json").read_bytes()
    assert len(every) == 98
    with pytest.raises(registry.RegistryError) as caught:
        add(tmp_path, project_id=OTHER_ID, root=ROOT, identity=(9999, 1))
    assert caught.value.code == "ports_exhausted"
    assert (tmp_path / "registry.json").read_bytes() == before


def test_a_written_registry_that_would_break_a_rule_is_refused_before_it_reaches_the_disk(
        tmp_path):
    add(tmp_path)
    before = (tmp_path / "registry.json").read_bytes()
    twin = registry.Project(OTHER_ID, "twin", OTHER_ROOT, (9, 9), 7701, "folder", None, NOW)
    with pytest.raises(registry.RegistryError) as caught:
        registry.mutate(lambda current: registry.Registry(
            current.projects_home, (*current.projects, twin)), tmp_path)
    assert caught.value.code == "registry_invalid" and "port" in caught.value.detail
    assert (tmp_path / "registry.json").read_bytes() == before


# -- the small writes the hub makes itself --------------------------------------------------


def test_removing_an_entry_keeps_the_others_and_the_files_of_the_project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "keep.txt").write_text("x", encoding="utf-8")
    add(tmp_path, root=str(root))
    add(tmp_path, project_id=OTHER_ID, root=OTHER_ROOT, identity=(9, 9))
    left = registry.remove_project(PROJECT_ID, folder=tmp_path)
    assert [project.project_id for project in left.projects] == [OTHER_ID]
    assert registry.load(tmp_path) == left and (root / "keep.txt").read_text() == "x"


def test_removing_an_entry_that_is_not_there_writes_nothing(tmp_path):
    add(tmp_path)
    before = (tmp_path / "registry.json").read_bytes()
    assert len(registry.remove_project(OTHER_ID, folder=tmp_path).projects) == 1
    assert (tmp_path / "registry.json").read_bytes() == before


def test_the_projects_folder_is_kept_in_the_file_and_null_puts_back_the_default(tmp_path):
    chosen = ROOT.replace("web-app", "MyProjects")
    assert registry.set_projects_home(chosen, folder=tmp_path).projects_home == chosen
    assert registry.load(tmp_path).projects_home == chosen
    assert registry.set_projects_home(None, folder=tmp_path).projects_home is None
    with pytest.raises(registry.RegistryError) as caught:
        registry.set_projects_home("relative", folder=tmp_path)
    assert caught.value.code == "registry_invalid"


def test_a_folder_that_cannot_be_written_is_registry_unwritable(tmp_path):
    blocker = tmp_path / "blocked"
    blocker.write_text("a file where the folder must be", encoding="utf-8")
    with pytest.raises(registry.RegistryError) as caught:
        add(blocker)
    assert caught.value.code == "registry_unwritable"


def test_an_error_code_outside_the_spec_and_the_proposals_cannot_be_built():
    with pytest.raises(ValueError, match="registry_gone"):
        registry.RegistryError("registry_gone", "no")
    assert registry.SPEC_CODES >= {"registry_invalid", "registry_busy", "ports_exhausted",
                                   "name_invalid", "root_already_registered"}
    assert registry.PROPOSED_CODES == {"registry_unwritable"}
