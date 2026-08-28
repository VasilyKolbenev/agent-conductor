"""A project has a name, and three different things mean it has none.

Before this, `conduct init` named a project only when a person answered the
wizard. `--template` and the non-terminal path returned the template verbatim,
so every project scaffolded by a script or by CI carried the literal
`project = "your-project"` for the rest of its life. The Studio, meanwhile, read
no map at all and said so on screen: *"This build records no project name
anywhere."*

Both halves are closed here, and the second is the one with a trap in it.
Naming every project is easy; the trap is that the placeholder is already
written into every template, so a surface that simply displayed the field would
tell most readers their project is called "your-project" -- in the largest type
on the screen. A placeholder shown as a fact is worse than an absence shown as
an absence, which is why `project_identity.project_name` exists as one rule with
one home rather than a `.get("project")` at each reader.

The name reaches the Studio through the workflows route, handed IN by the
server. `conductor.command` holds no opinion about Protocol v1 documents and
imports nothing that reads one; what crosses that boundary is a name or None.
"""
from __future__ import annotations

import argparse

import pytest

import conductor.init
from conductor import project_identity, templates
from conductor.command import studio_routes


# -- what counts as a name --------------------------------------------------


def test_a_map_that_names_the_project_answers_with_that_name():
    assert project_identity.project_name({"project": "orbit"}) == "orbit"


@pytest.mark.parametrize("document, why", [
    ({}, "no key at all: every project scaffolded before this build"),
    ({"project": templates.UNNAMED}, "the placeholder every template ships"),
    ({"project": "   "}, "whitespace is not a name"),
    ({"project": ""}, "the empty string is not a name"),
    ({"project": 7}, "a number is not a name"),
    ({"project": None}, "an explicit null is not a name"),
    (None, "no map has been read yet"),
])
def test_what_is_not_a_name_answers_none_rather_than_something_to_display(
        document, why):
    """Each row is a document a real project carries, and none is a name.

    The placeholder row is the one that matters most: it is what every template
    writes, so a reader that trusted the field would show it to almost everyone.
    """
    assert project_identity.project_name(document) is None, why


def test_a_name_is_answered_without_the_whitespace_around_it():
    assert project_identity.project_name({"project": "  orbit  "}) == "orbit"


# -- init names the project on every road -----------------------------------


def _init(tmp_path, *extra):
    from conductor.__main__ import _build_parser

    return _build_parser().parse_args(
        ["init", "--dir", str(tmp_path), *extra])


def _map_of(tmp_path):
    import tomllib

    return tomllib.loads(
        (tmp_path / "conductor" / "map.toml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", [name for name, _ in templates.names()])
def test_every_template_road_writes_a_real_name_not_the_placeholder(
        tmp_path, name, capsys):
    """`--template` used to return the template verbatim, placeholder included.

    A project scaffolded by a script is a project nobody ever names by hand, so
    this was the road that produced almost every unnamed project.
    """
    project = tmp_path / "orbit-demo"
    project.mkdir()

    assert conductor.init.run(_init(project, "--template", name)) == 0

    written = _map_of(project).get("project")
    assert written == "orbit-demo"
    assert project_identity.project_name(_map_of(project)) == "orbit-demo"


def test_the_non_terminal_road_names_the_project_too(tmp_path, capsys):
    """No TTY, no `--template`: the road CI takes."""
    project = tmp_path / "ci-project"
    project.mkdir()

    assert conductor.init.run(_init(project)) == 0

    assert _map_of(project)["project"] == "ci-project"


def test_a_directory_whose_name_is_not_usable_falls_back_to_the_placeholder(
        tmp_path, capsys):
    """The fallback is the placeholder, never an invented name.

    A directory whose own name `NAME_RE` refuses cannot honestly name the
    project, and `templates.UNNAMED` is the value every reader already knows to
    treat as "nobody has chosen one yet" -- so the Studio says so in words
    rather than showing a mangled directory name as a fact.
    """
    project = tmp_path / "_leading-underscore"
    project.mkdir()

    assert conductor.init.run(_init(project)) == 0

    assert _map_of(project)["project"] == templates.UNNAMED
    assert project_identity.project_name(_map_of(project)) is None


def test_the_scaffolded_map_still_validates_clean_with_the_name_written_in(
        tmp_path, capsys):
    """A substituted name must not break the document it was written into."""
    from conductor import validate

    project = tmp_path / "named-project"
    project.mkdir()
    assert conductor.init.run(_init(project)) == 0

    errors, warnings = validate.check(project)

    assert (errors, warnings) == ([], [])


# -- the route carries it ---------------------------------------------------


def _empty_store(tmp_path):
    """A REAL template store over an empty project, never a stand-in.

    The route reads the store through its own door; a hand-written double would
    be this test describing the store rather than exercising it, and would go on
    passing after the door changed shape.
    """
    from conductor.command.template_store import TemplateStore

    (tmp_path / "conductor").mkdir(parents=True, exist_ok=True)
    return TemplateStore(tmp_path)


def test_the_workflows_route_carries_the_name_it_was_handed(tmp_path):
    status, payload = studio_routes.list_workflows(
        _empty_store(tmp_path), (), "orbit")

    assert status == 200
    assert payload["project"] == "orbit"


def test_the_route_carries_null_rather_than_omitting_an_absent_name(tmp_path):
    """Absent is a value on this wire, because the boundary requires the key.

    A payload that dropped the key when there was no name would be a second
    shape for the same route, and the window would refuse it whole.
    """
    status, payload = studio_routes.list_workflows(_empty_store(tmp_path), ())

    assert status == 200
    assert "project" in payload and payload["project"] is None


def test_the_command_boundary_is_handed_a_name_and_never_the_map():
    """The package holds no opinion about Protocol v1 documents.

    Asserted structurally rather than by reading the route: an import is what
    would make this package able to read a map, and there is none.
    """
    import conductor.command.studio_routes as routes
    import conductor.command.http_api as api

    for module in (routes, api):
        source = open(module.__file__, encoding="utf-8").read()
        assert "from conductor import" not in source, module.__name__
        assert "conductor.store" not in source, module.__name__
