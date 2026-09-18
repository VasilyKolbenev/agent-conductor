"""The frozen transport gate, asked of every route the Studio added.

Split from `test_command_workflow_routes.py` when that module reached the
project's 800-line cap, along the seam it already had. The question here is one
question, and it is not about workflows at all: does EVERY new route obey the
same door -- exact Host on a read, and Host plus Origin plus the per-process
CSRF token plus Content-Type plus one bounded Content-Length on a write?

It is parametrized over the live route table rather than a list written here,
so a route added to the allowlist is asked these questions whether or not
anybody remembered to write a test for it. That is the whole value of keeping
it together and apart: the module next door tests what the workflow routes DO,
and this one tests that none of them opened a second door to do it through.
"""
from __future__ import annotations

import pytest

from conductor.command.api_contracts import ERROR_STATUS
from conductor.command.command_routes import COMMAND_ROUTES
from conductor.command.http_transport import MAX_COMMAND_BODY_BYTES

from tests.test_command_workflow_routes import (
    BOTH_VERBS,
    FROZEN_TEN,
    HOST,
    NEW_POSTS,
    NEW_ROUTES,
    NEW_TARGETS,
    ORIGIN,
    SEEDED,
    TOKEN,
    WORKFLOW,
    a_document,
    api,
    code_of,
    drafting,
    durable_digest,
    encode,
    get,
    post,
    post_headers,
    publishing,
    seeded,
    target,
)

def test_the_new_routes_are_derived_from_the_live_table_and_are_the_ten(tmp_path):
    """What this file holds to the contract is what the allowlist actually says."""
    assert NEW_ROUTES == (
        ("GET", "/command/workflows"),
        ("GET", "/command/workflows/<workflow_id>"),
        ("GET", "/command/workflows/<workflow_id>/revisions/<revision>"),
        ("POST", "/command/workflows/<workflow_id>/draft"),
        ("POST", "/command/workflows/<workflow_id>/revisions"),
        ("GET", "/command/runs"),
        ("POST", "/command/runs"),
        ("GET", "/command/tasks"),
        ("POST", "/command/tasks"),
        ("GET", "/command/tasks/<task_id>"),
    )
    assert set(FROZEN_TEN) < set(COMMAND_ROUTES)


@pytest.mark.parametrize("method,path", NEW_TARGETS)
def test_every_new_route_refuses_a_host_this_process_never_minted(
        tmp_path, method, path):
    """Loopback binding keeps a stranger's packet off the socket and says
    nothing about whose PAGE sent one, so the Host allowlist is the gate."""
    subject, _store, _templates, events = api(tmp_path)
    if method == "GET":
        refused = get(subject, path, host="attacker.test")
    else:
        refused = post(subject, path, {}, host="attacker.test",
                       origin="http://attacker.test")
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["same_origin_denied"], "same_origin_denied")
    assert events == []


@pytest.mark.parametrize("method,path", NEW_TARGETS)
def test_every_new_route_refuses_a_query_string(tmp_path, method, path):
    """Command routes have no query surface, so a query is another route."""
    subject, _store, _templates, events = api(tmp_path)
    probed = f"{path}?v=1"
    if method == "GET":
        refused = get(subject, probed)
    else:
        refused = post(subject, probed, {})
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["route_not_found"], "route_not_found")
    assert events == []


@pytest.mark.parametrize("method,path", NEW_TARGETS)
def test_every_new_route_refuses_a_verb_the_table_does_not_name(
        tmp_path, method, path):
    """A known path under an unknown verb is `method_not_allowed`, not 404.

    The two are told apart before either is answered, so a probe cannot learn
    which routes exist by watching the refusal change.
    """
    subject, _store, _templates, _events = api(tmp_path)
    for verb in ("DELETE", "PUT", "PATCH", "HEAD"):
        refused = subject.handle(verb, path, (("Host", HOST),))
        assert (refused.status, code_of(refused)) == (
            ERROR_STATUS["method_not_allowed"], "method_not_allowed"), verb
    absent = subject.handle("DELETE", "/command/nothing-here", (("Host", HOST),))
    assert code_of(absent) == "route_not_found"


@pytest.mark.parametrize("method,path", NEW_TARGETS)
def test_every_new_route_but_the_two_dual_verb_lists_refuses_the_other_verb(
        tmp_path, method, path):
    """A read road is not a write road under another name, and the reverse.

    ``/command/runs`` and ``/command/tasks`` are the two deliberate exceptions,
    named here rather than skipped, so a third dual-verb route would have to
    be written down.
    """
    subject, _store, _templates, events = api(tmp_path)
    if path in BOTH_VERBS:
        assert get(subject, path).status == 200
        assert post(subject, path, {}).status == ERROR_STATUS["contract_invalid"]
        return
    refused = (post(subject, path, {}) if method == "GET"
               else get(subject, path))
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["method_not_allowed"], "method_not_allowed")
    assert events == []


@pytest.mark.parametrize("path", [target(path) for _m, path in NEW_POSTS])
@pytest.mark.parametrize("change,expected", [
    ({"drop": ("Origin",)}, "same_origin_denied"),
    ({"origin": "http://attacker.test"}, "same_origin_denied"),
    ({"drop": ("X-Conduct-CSRF",)}, "csrf_denied"),
    ({"token": "a-token-from-another-process"}, "csrf_denied"),
    ({"drop": ("Content-Type",)}, "malformed_request"),
    ({"length": MAX_COMMAND_BODY_BYTES + 1}, "malformed_request"),
])
def test_every_new_mutation_meets_the_whole_frozen_transport_gate(
        tmp_path, path, change, expected):
    """Origin, CSRF, content type and the body ceiling -- missing AND wrong,
    because a gate that read only the presented value would pass every request
    that presented none."""
    subject, _store, templates, events = seeded(tmp_path)
    before = durable_digest(tmp_path)
    refused = post(subject, path, a_document(), **change)
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS[expected], expected)
    assert events == [] and durable_digest(tmp_path) == before
    assert templates.load_draft(WORKFLOW) is None


@pytest.mark.parametrize("path", [target(path) for _m, path in NEW_POSTS])
def test_every_new_mutation_refuses_a_body_larger_than_the_ceiling(tmp_path, path):
    """A real oversized payload, not only an oversized declaration."""
    subject, _store, _templates, events = seeded(tmp_path)
    before = durable_digest(tmp_path)
    oversized = a_document(title="x" * (MAX_COMMAND_BODY_BYTES + 1))
    assert len(encode(oversized)) > MAX_COMMAND_BODY_BYTES
    refused = post(subject, path, oversized)
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["malformed_request"], "malformed_request")
    assert events == [] and durable_digest(tmp_path) == before


@pytest.mark.parametrize("path", [target(path) for _m, path in NEW_POSTS])
@pytest.mark.parametrize("raw", [b"[]", b'"a string"', b"7", b"null", b"", b"{"])
def test_every_new_mutation_refuses_a_body_that_is_not_one_json_object(
        tmp_path, path, raw):
    subject, _store, _templates, events = seeded(tmp_path)
    before = durable_digest(tmp_path)
    headers = (("Host", HOST), ("Origin", ORIGIN), ("X-Conduct-CSRF", TOKEN),
               ("Content-Type", "application/json"),
               ("Content-Length", str(len(raw))))
    refused = subject.handle("POST", path, headers, raw)
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["malformed_request"], "malformed_request")
    assert events == [] and durable_digest(tmp_path) == before


@pytest.mark.parametrize("method,path", NEW_TARGETS)
def test_no_new_route_publishes_a_frame_for_a_request_it_refused(
        tmp_path, method, path):
    """A frame is a claim that some run moved, and a refused request moved none."""
    subject, _store, _templates, events = seeded(tmp_path)
    before = durable_digest(tmp_path)
    if method == "GET":
        subject.handle(method, path, (("Host", "attacker.test"),))
    else:
        post(subject, path, {"nothing": "a template could carry"})
    assert events == [] and durable_digest(tmp_path) == before


def test_a_studio_read_is_gated_on_host_and_needs_no_csrf_token(tmp_path):
    """A read causes no durable effect, so it carries no anti-forgery token.

    The rule already written for the frozen reads, asserted for the new ones
    rather than assumed: a GET that skipped the Host gate would answer a page
    this process never handed a name to.
    """
    subject, _store, _templates, _events = api(tmp_path)
    assert post(subject, f"/command/workflows/{WORKFLOW}/draft",
                drafting(subject, WORKFLOW, a_document())).status == 201
    assert post(subject, f"/command/workflows/{WORKFLOW}/revisions",
                publishing(subject, WORKFLOW, 1)).status == 201
    for path in ("/command/workflows", "/command/runs",
                 f"/command/workflows/{WORKFLOW}/revisions/1"):
        assert subject.handle("GET", path, (("Host", HOST),)).status == 200
        denied = subject.handle("GET", path, (("Host", "attacker.test"),))
        assert code_of(denied) == "same_origin_denied"
