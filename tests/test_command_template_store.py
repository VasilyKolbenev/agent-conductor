"""Where a reusable plan lives, and what a second write of one revision means.

Every claim is made against a real directory through the real contracts. The
template is the SHIPPED file wherever one will do, because a fixture written
beside the test would only prove that two pieces of this file agree.
"""
from __future__ import annotations

import json
import os
import traceback

import pytest

from conductor.command.graph_template import (
    GraphTemplate,
    TemplateError,
    load_template,
)
from conductor.command.containment import RouteViolationCode
from conductor.command.store_errors import RecordConflict, StoreError
from conductor.command.template_store import (
    RevisionConflict,
    RouteNotOwned,
    TemplateStore,
)


def dalio() -> GraphTemplate:
    return load_template("dalio-v1")


def test_a_revision_is_published_once_and_reads_back_through_the_contract(tmp_path):
    """What comes back is what `from_dict` accepts, not what we happened to write."""
    store = TemplateStore(tmp_path)
    template = dalio()
    path = store.save(template)
    assert path.is_file()
    assert store.load(template.template_id, template.revision) == template
    assert store.revisions(template.template_id) == (template.revision,)


def test_writing_the_same_revision_again_is_a_retry_and_not_a_conflict(tmp_path):
    """A client whose reply was lost must not be refused what it already wrote.

    The graph route answers a repeated write the same way, and for the same
    reason: the second request either IS the first or contradicts it, and only
    the second of those is anybody's mistake.
    """
    store = TemplateStore(tmp_path)
    template = dalio()
    first = store.save(template)
    assert store.save(template) == first
    assert store.save(GraphTemplate.from_dict(template.as_dict())) == first
    assert store.revisions(template.template_id) == (1,)


def test_a_revision_that_says_something_else_is_refused_under_that_name(tmp_path):
    """A revision is an identity, so two plans may not wear one.

    This is the promise `graph_template` already makes -- an edit is a new
    revision -- kept by the only storage that can keep it. A revision whose
    bytes could change would leave every run that materialized from it
    replaying against a plan nobody can reconstruct.
    """
    store = TemplateStore(tmp_path)
    template = dalio()
    store.save(template)
    edited = template.as_dict()
    edited["nodes"][0]["title"] = "Goal, restated"
    with pytest.raises(RevisionConflict) as refusal:
        store.save(GraphTemplate.from_dict(edited))
    assert "an edit is a new revision" in str(refusal.value)
    # And the stored revision is untouched by the attempt.
    assert store.load(template.template_id, 1) == template


def test_an_edit_is_a_new_revision_and_both_of_them_stand(tmp_path):
    """The past does not move, which is the whole point of numbering them."""
    store = TemplateStore(tmp_path)
    template = dalio()
    store.save(template)
    edited = template.as_dict()
    edited["revision"] = 2
    edited["nodes"][0]["title"] = "Goal, restated"
    store.save(GraphTemplate.from_dict(edited))
    assert store.revisions(template.template_id) == (1, 2)
    assert store.load(template.template_id, 1) == template
    assert store.load(template.template_id, 2).nodes[0].title == "Goal, restated"


def test_a_revision_that_is_not_there_is_refused_without_naming_the_disk(tmp_path):
    """The refusal owes the caller the two facts they supplied, and nothing else."""
    store = TemplateStore(tmp_path)
    with pytest.raises(TemplateError) as refusal:
        store.load("template-dalio", 7)
    assert refusal.value.__cause__ is None
    assert refusal.value.__suppress_context__ is True
    printed = "".join(traceback.format_exception(
        type(refusal.value), refusal.value, refusal.value.__traceback__))
    assert str(store.templates_root) not in printed
    assert "template-dalio" in str(refusal.value) and "7" in str(refusal.value)


@pytest.mark.parametrize("name", ["../escape", "has space", "", "a/b"])
def test_a_name_the_contract_refuses_never_reaches_a_path(tmp_path, name):
    """The set of names this store accepts is the set the CONTRACT accepts.

    Not a path check of this module's invention -- one rule, in one place, so a
    name that could reach a directory is refused by the same door that refuses
    it everywhere else in this product.
    """
    store = TemplateStore(tmp_path)
    with pytest.raises(StoreError):
        store.revision_path(name, 1)
    with pytest.raises(StoreError):
        store.revisions(name)


@pytest.mark.parametrize("revision", [0, -1, "1", 1.0, True])
def test_a_revision_that_is_not_a_counting_number_is_refused(tmp_path, revision):
    store = TemplateStore(tmp_path)
    with pytest.raises(StoreError):
        store.revision_path("template-dalio", revision)


def test_a_stored_document_the_contract_would_refuse_is_refused_on_the_way_out(tmp_path):
    """Written by us is not a reason to trust it coming back.

    A build that stored a revision and a later build that no longer speaks that
    schema are the same situation as an operator's own file: it goes through
    `from_dict`, so it is refused whole rather than half-read.
    """
    store = TemplateStore(tmp_path)
    template = dalio()
    path = store.save(template)
    stale = template.as_dict()
    stale["schema_version"] = 99
    path.write_text(json.dumps(stale), encoding="utf-8", newline="\n")
    with pytest.raises(TemplateError, match="schema_version"):
        store.load(template.template_id, 1)


def test_the_revisions_are_read_off_the_directory_and_not_an_index(tmp_path):
    """An index of oneself can come to disagree with oneself; the files ARE it."""
    store = TemplateStore(tmp_path)
    template = dalio()
    store.save(template)
    for revision in (2, 3):
        document = template.as_dict()
        document["revision"] = revision
        store.save(GraphTemplate.from_dict(document))
    assert store.revisions(template.template_id) == (1, 2, 3)
    # A file that is not a revision is not one, whatever it is called.
    directory = store.revision_path(template.template_id, 1).parent
    (directory / "notes.txt").write_text("x", encoding="utf-8", newline="\n")
    (directory / "draft.json").write_text("{}", encoding="utf-8", newline="\n")
    assert store.revisions(template.template_id) == (1, 2, 3)
    assert store.revisions("template-nobody-stored") == ()


def test_a_revision_conflict_is_the_store_conflict_every_road_already_names(tmp_path):
    """One vocabulary for one fact, so a caller catches what it already catches."""
    store = TemplateStore(tmp_path)
    template = dalio()
    store.save(template)
    edited = template.as_dict()
    edited["title"] = "Something else"
    with pytest.raises(RecordConflict):
        store.save(GraphTemplate.from_dict(edited))


def test_the_store_takes_a_template_and_no_lookalike(tmp_path):
    """A subclass may answer for itself; this door does not accept one."""
    class Sneaky(GraphTemplate):
        pass

    store = TemplateStore(tmp_path)
    template = dalio()
    with pytest.raises(StoreError, match="exactly a GraphTemplate"):
        store.save(Sneaky(template_id="t", revision=1, title="T",
                          nodes=template.nodes, edges=template.edges))
    with pytest.raises(StoreError):
        store.save(template.as_dict())


# --- the route this store writes through, and what it refuses to reach ---


def _portal(link: Path, target: Path, *, directory: bool) -> bool:
    """Make one symlink, or report that this machine will not let us.

    Windows needs a privilege for these, so the test says why it skipped rather
    than passing quietly on a platform where the relation was never exercised.
    """
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError):
        return False
    return True


def test_a_portal_on_the_route_is_refused_without_naming_the_path(tmp_path):
    """A name here whose content is elsewhere sends this store's bytes there.

    The refusal names the KIND, because that is what a caller can act on. It
    does not name the path: `containment` reports typed facts precisely so a
    caller need not parse a rendering, and its own renderer carries the path --
    which is this server's directory layout handed to whoever asked.
    """
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    project = tmp_path / "project"
    (project / "conductor").mkdir(parents=True)
    if not _portal(project / "conductor" / "templates", elsewhere, directory=True):
        pytest.skip("this machine does not permit creating a symbolic link")
    store = TemplateStore(project)
    template = dalio()
    with pytest.raises(RouteNotOwned) as refusal:
        store.save(template)
    assert "symbolic link" in str(refusal.value)
    for secret in (str(tmp_path), str(elsewhere), str(store.templates_root)):
        assert secret not in str(refusal.value)
    assert not list(elsewhere.iterdir()), "it wrote through the portal anyway"


def test_a_portal_that_appears_after_a_write_is_refused_on_the_way_out(tmp_path):
    """A reader trusting bytes from elsewhere is the same defect as a writer.

    The route is judged on the way IN and on the way OUT, so a revision written
    honestly and later replaced by a name pointing somewhere else is refused
    rather than read back as though nothing had happened.
    """
    store = TemplateStore(tmp_path)
    template = dalio()
    path = store.save(template)
    assert store.load(template.template_id, 1) == template
    other = tmp_path / "other.json"
    other.write_text(path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    path.unlink()
    if not _portal(path, other, directory=False):
        pytest.skip("this machine does not permit creating a symbolic link")
    with pytest.raises(RouteNotOwned) as refusal:
        store.load(template.template_id, 1)
    assert "symbolic link" in str(refusal.value)
    assert str(tmp_path) not in str(refusal.value)


def test_a_revision_that_carries_a_second_name_is_refused(tmp_path):
    """`os.link` arbitrates the NAME and says nothing about the bytes behind it.

    A second hard link makes the same bytes reachable somewhere this store
    cannot account for, so publishing at our name changes only one view of
    state nobody owns -- and the exclusive create cannot see that at all.
    """
    store = TemplateStore(tmp_path)
    template = dalio()
    path = store.save(template)
    twin = tmp_path / "twin.json"
    try:
        os.link(path, twin)
    except (OSError, NotImplementedError):
        pytest.skip("this machine does not permit creating a hard link")
    with pytest.raises(RouteNotOwned) as refusal:
        store.load(template.template_id, 1)
    assert "more than one name" in str(refusal.value)
    assert str(tmp_path) not in str(refusal.value)
    with pytest.raises(RouteNotOwned):
        store.save(template)


def test_a_revision_that_is_not_a_regular_file_is_refused(tmp_path):
    """What stands at the name matters, not only whether something does."""
    store = TemplateStore(tmp_path)
    template = dalio()
    path = store.revision_path(template.template_id, 1)
    path.parent.mkdir(parents=True)
    path.mkdir()
    with pytest.raises(RouteNotOwned) as refusal:
        store.load(template.template_id, 1)
    assert "not a regular file" in str(refusal.value)
    assert str(tmp_path) not in str(refusal.value)


def test_a_route_component_that_is_a_file_is_refused_as_a_route(tmp_path):
    """A store cannot write through something that is not a directory."""
    project = tmp_path / "project"
    (project / "conductor").mkdir(parents=True)
    (project / "conductor" / "templates").write_text("x", encoding="utf-8",
                                                     newline="\n")
    store = TemplateStore(project)
    with pytest.raises(RouteNotOwned) as refusal:
        store.save(dalio())
    assert "not a directory" in str(refusal.value)
    assert str(tmp_path) not in str(refusal.value)


def test_every_structural_reason_has_a_sentence_that_names_no_path():
    """The refusal table is closed, and closed against the typed vocabulary.

    Derived rather than listed: every reason this store can actually raise must
    have a sentence, so a `containment` code reaching it without one would be a
    `KeyError` at the worst possible moment instead of a refusal.
    """
    from conductor.command.template_store import _ROUTE_REFUSAL

    assert _ROUTE_REFUSAL, "the refusal table is empty"
    for code, sentence in _ROUTE_REFUSAL.items():
        assert isinstance(code, RouteViolationCode)
        assert sentence and not any(mark in sentence for mark in ("/", "\\", ":")), (
            code, sentence)
