"""The transport's two network doors and its seal, the real module in a real Chromium (spec 4.5.1).

The real `desk-transport.js` is imported into a page of a real server (a stylesheet of it, so no
desk boots and the only requests are the test's own) and the `/command/*` routes are answered in
the page. What this module holds: the single GET and the single POST carry `X-Conduct-Project`
exactly when the window is bound to a project, the session read is one of the GETs and carries
it, the claim is asked at the moment of each request, and a sealed transport (the terminal state
of a desk open for another project) closes its stream, refuses every read, write and stream, and
asks for no session, without one request. The desk that uses them is in
`test_desk_bound_project.py`.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Page, Route

from browser_tests.desk_identity import identified_server
from browser_tests.test_desk_rail_scene import _seed, seeded_url  # noqa: F401  (a fixture)
from tests.test_store import good_lane, write_project

PROJECT_A, PROJECT_B = "a" * 32, "b" * 32
HEADER = "x-conduct-project"
#: The document every transport test stands on: a stylesheet of the same origin. It boots no
#: desk, so the only requests a test sees are the ones it makes.
STAND = "/panel/desk.css"
MODULE = "/panel/desk-transport.js"


@dataclass
class Wire:
    """Every `/command/*` request the page made: (method, path, header values)."""

    asked: list[tuple[str, str, list[str]]] = field(default_factory=list)


def _json(route: Route, body: object, status: int = 200) -> None:
    route.fulfill(status=status, content_type="application/json", body=json.dumps(body))


def _wire(page: Page, origin: str) -> Wire:
    """Answer the `/command/*` routes a transport test uses, and record what arrived."""
    wire = Wire()

    def answer(route: Route) -> None:
        request = route.request
        path = urlsplit(request.url).path
        claims = [one["value"] for one in request.headers_array()
                  if one["name"].lower() == HEADER]
        wire.asked.append((request.method, path, claims))
        if path == "/command/session":
            _json(route, {"csrf_token": "token-1", "origin": origin})
        else:
            _json(route, {"ok": True})

    page.route("**/command/**", answer)
    return wire


@pytest.fixture
def stand(chromium: Browser,
          seeded_url: str,  # noqa: F811
          ) -> Iterator[Callable[[], tuple[Page, Wire]]]:
    """A page of the desk's origin with the real transport importable, and its wire."""
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(seeded_url))
    contexts = []

    def make() -> tuple[Page, Wire]:
        context = chromium.new_context()
        contexts.append(context)
        page = context.new_page()
        wire = _wire(page, origin)
        page.goto(origin + STAND, wait_until="load")
        return page, wire

    yield make
    for context in contexts:
        context.close()


#: One evaluation: make a transport bound to `id` (a value that may change), then read, write
#: and read the session, and answer what came back.
DOORS = """async ([module, bound]) => {
  const {createTransport, path} = await import(module);
  let id = bound;
  const door = createTransport(() => "en", () => id);
  const read = await door.readJson(path.tasks());
  const wrote = await door.submit("tasks", null, {});
  id = null;
  const later = await door.readJson(path.runs());
  return {read, wrote, later};
}"""


def _by_path(wire: Wire) -> dict[str, list[str]]:
    return {f"{method} {path}": claims for method, path, claims in wire.asked}


def test_a_read_the_session_and_a_write_each_carry_the_bound_project_once(stand):
    page, wire = stand()
    page.evaluate(DOORS, [MODULE, PROJECT_A])
    seen = _by_path(wire)
    assert seen["GET /command/session"] == [PROJECT_A]
    assert seen["GET /command/tasks"] == [PROJECT_A]
    assert seen["POST /command/tasks"] == [PROJECT_A]
    assert len(wire.asked) == 4


def test_the_claim_is_read_at_the_moment_of_each_request(stand):
    page, wire = stand()
    page.evaluate(DOORS, [MODULE, PROJECT_A])
    seen = _by_path(wire)
    assert seen["GET /command/tasks"] == [PROJECT_A]
    assert seen["GET /command/runs"] == []


def test_a_transport_bound_to_nothing_sends_no_claim(stand):
    page, wire = stand()
    page.evaluate(DOORS, [MODULE, None])
    assert [claims for _method, _path, claims in wire.asked] == [[]] * len(wire.asked)
    assert len(wire.asked) == 4


#: After `seal()`: the token is forgotten and nothing reaches the wire. The answers are what a
#: caller sees: the read throws the refusal's code, the write answers refused with it.
SEALED = """async ([module, bound]) => {
  const {createTransport, path} = await import(module);
  const door = createTransport(() => "en", () => bound);
  await door.submit("tasks", null, {});
  door.seal();
  let read = null;
  try { await door.readJson(path.tasks()); } catch (error) { read = error.message; }
  const wrote = await door.submit("tasks", null, {});
  return {read, wrote};
}"""


def test_a_sealed_transport_makes_no_request_and_refuses_every_read_and_write(stand):
    page, wire = stand()
    before = len(wire.asked)
    answer = page.evaluate(SEALED, [MODULE, PROJECT_A])
    assert answer["read"] == "project_mismatch"
    assert answer["wrote"] == {"status": "refused", "code": "project_mismatch"}
    assert len(wire.asked) - before == 2, "only the first write (session and post) was made"


def test_a_seal_closes_the_stream_the_window_opened_and_no_other_is_opened(stand):
    page, _wire_seen = stand()
    answer = page.evaluate("""async ([module, bound]) => {
      const {createTransport} = await import(module);
      const door = createTransport(() => "en", () => bound);
      const stream = door.openStream();
      const before = stream.readyState;
      door.seal();
      let again = null;
      try { door.openStream(); } catch (error) { again = error.message; }
      return {before, after: stream.readyState, again};
    }""", [MODULE, PROJECT_A])
    assert answer == {"before": 0, "after": 2, "again": "project_mismatch"}


def test_a_write_after_a_seal_does_not_fetch_a_new_session(stand):
    page, wire = stand()
    answer = page.evaluate("""async ([module, bound]) => {
      const {createTransport} = await import(module);
      const door = createTransport(() => "en", () => bound);
      door.seal();
      return door.submit("tasks", null, {});
    }""", [MODULE, PROJECT_A])
    assert answer == {"status": "refused", "code": "project_mismatch"}
    assert wire.asked == []


# -- the materials write and the two document reads, through the real doors -------------------

#: One evaluation: the write twice (a retry after a lost answer is the same document), a write
#: the route refuses, the list of documents, and a document the project does not hold.
MATERIALS = """async ([module, run]) => {
  const {createTransport, path} = await import(module);
  const door = createTransport(() => "en", () => null);
  const body = {lang: "en", items: []};
  const first = await door.submit("materials", run, body);
  const again = await door.submit("materials", run, body);
  const extra = await door.submit("materials", run, {...body, path: "x"});
  const listing = await door.readJson(path.projectDocuments());
  let unknown = null;
  try { await door.readJson(path.projectDocument("d-" + "0".repeat(32))); }
  catch (error) { unknown = error.message; }
  return {first, again, extra, listing, unknown};
}"""


def test_the_materials_write_and_the_document_reads_work_through_the_real_doors(
        chromium: Browser, tmp_path_factory: pytest.TempPathFactory):
    root = write_project(tmp_path_factory.mktemp("desk-materials"), lanes={"claude": good_lane()})
    _seed(root)
    with identified_server(root, None) as origin:
        context = chromium.new_context()
        try:
            page = context.new_page()
            page.goto(origin + STAND, wait_until="load")
            said = page.evaluate(MATERIALS, [MODULE, "run-docs"])
        finally:
            context.close()
    assert said["first"]["status"] == "accepted" and said["again"]["status"] == "accepted"
    assert said["again"]["payload"] == said["first"]["payload"]
    assert (said["extra"]["status"], said["extra"]["code"]) == ("refused", "contract_invalid")
    assert said["listing"] == {"base": None, "documents": [], "truncated": False}
    assert said["unknown"] == "materials_refused"
