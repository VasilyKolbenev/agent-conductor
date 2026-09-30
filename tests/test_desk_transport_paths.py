"""The routes the desk's transport names are routes of the command canon, and no other.

`desk-transport.js` spells each route it may ask as a function of the ids it is handed. Lane L
handed over three (spec 6.2.2, 6.2.3, 9.1.6): the write `POST /command/runs/<run_id>/materials`
and the two reads of a project's documents. This runs the real module under Node, builds the
paths, and asks the server's own `match_route` which route each one reaches, so a spelling that
drifted from the canon, or an id that could slip into another route, is red here and not in a
browser. A path is also shown to be reachable by NO other verb than the one its row names.
"""
from __future__ import annotations

import pytest

from conductor.command.api_refusals import ApiRefusal
from conductor.command.command_routes import match_route
from tests.desk_node import run_js

MODULES = {"transport": "desk-transport.js"}
DOC = "d-" + "0123456789abcdef" * 2
RUN = "run-2026-09-30.a"


def _paths(rows: list[list[str]]) -> list[str]:
    """`path.<name>(arg)` for each row of (name, argument) under Node."""
    return run_js("""
      console.log(JSON.stringify(d.map(([name, arg]) => transport.path[name](arg))));
    """, MODULES, rows)


def test_the_materials_and_document_paths_are_the_three_rows_of_route_canon_3():
    materials, listing, one = _paths([["materials", RUN], ["projectDocuments", ""],
                                      ["projectDocument", DOC]])
    assert materials == f"/command/runs/{RUN}/materials"
    assert listing == "/command/project/documents"
    assert one == f"/command/project/documents/{DOC}"
    assert match_route("POST", materials).name == "materials"
    assert match_route("GET", listing).name == "project_documents"
    reached = match_route("GET", one)
    assert (reached.name, reached.doc_id) == ("project_document", DOC)
    assert match_route("POST", materials).run_id == RUN


def test_the_flag_path_is_the_one_spec_4_3_4_gives_and_is_the_canons_once_it_has_the_row():
    """One path, read and written. Its canon row is lane H's, handed to lane L with a patch that
    lane L had not applied when this was written, so until then the canon does not know it; the
    day it does, this holds the route it names."""
    (path,) = _paths([["autoContinue", ""]])
    assert path == "/command/project/auto-continue"
    try:
        reached = match_route("GET", path)
    except ApiRefusal as refused:
        assert refused.code == "route_not_found"
    else:
        assert reached.name == "project_auto_continue"
        assert match_route("POST", path).name == "project_auto_continue"


def test_each_of_the_three_is_refused_under_the_other_verb():
    materials, listing, one = _paths([["materials", RUN], ["projectDocuments", ""],
                                      ["projectDocument", DOC]])
    for method, path in (("GET", materials), ("POST", listing), ("POST", one)):
        with pytest.raises(ApiRefusal) as refused:
            match_route(method, path)
        assert refused.value.code == "method_not_allowed", (method, path)


@pytest.mark.parametrize("hostile", ["../x", "a/b", "a%2Fb", "..", "d-x", DOC.upper(),
                                     DOC + "0", f"{DOC}/extra", "", "a b", "a?b=1"])
def test_an_id_that_is_no_id_of_the_grammar_reaches_no_route(hostile):
    """The ids are encoded, so a slash, a dot run or a query cannot become part of the path."""
    materials, one = _paths([["materials", hostile], ["projectDocument", hostile]])
    for method, path in (("POST", materials), ("GET", one)):
        reached = None
        try:
            reached = match_route(method, path)
        except ApiRefusal as refused:
            assert refused.code == "route_not_found", (method, path, refused.code)
        if reached is not None:  # only a well-formed id may name a run or a document
            assert reached.name in {"materials", "project_document"}
            assert reached.run_id == hostile or reached.doc_id == hostile
            assert "/" not in hostile and "?" not in hostile and ".." not in hostile
