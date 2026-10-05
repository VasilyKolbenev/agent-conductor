"""Hold the answers of one URL of a desk page, so a window of the desk's reads can be judged.

Every full refresh the desk makes (the stream's open and the first frame the server sends on it,
any later state frame, the run panel's refresh door) reads the chosen run again, and while that
read is out the scene says the run is "stale". The scene's read is the run and its controls
together, and the controls read is the one that is held here: it is made for the scene alone (the
closing reads of finished tasks read the run too), so a held controls read is a scene that stands
as stale until it lands. Nothing is slowed and nothing is raced: every window of the re-read can
be judged.

A window whose answers are rewritten has a call in flight whenever one is being fetched, and a desk
whose stream is live makes reads of its own at any time. `close_context` closes such a window
without leaving that call's error for the next test.

This is a helper and not a test module.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from playwright.sync_api import BrowserContext, Page, Route, expect


class Hold:
    """The answers of one URL: passed on until `hold()`, then kept back until `land()`.

    A set `rewrite` changes the JSON body of every answer that is passed on.
    """

    def __init__(self, page: Page, pattern: str) -> None:
        self.rewrite: Callable[[dict], dict] | None = None
        self._holding, self._kept = False, []
        page.route(pattern, self._answer)

    def _answer(self, route: Route) -> None:
        if self._holding:
            self._kept.append(route)
        else:
            self._pass_on(route)

    def _pass_on(self, route: Route) -> None:
        if self.rewrite is None:
            route.continue_()
        else:
            response = route.fetch()
            route.fulfill(response=response, json=self.rewrite(response.json()))

    def hold(self) -> None:
        self._holding = True

    def reached(self) -> bool:
        return bool(self._kept)

    def land(self) -> None:
        self._holding = False
        kept, self._kept = self._kept, []
        for route in kept:
            self._pass_on(route)

    def abort(self) -> None:
        kept, self._kept = self._kept, []
        for route in kept:
            route.abort()


def close_context(context: BrowserContext) -> None:
    """Close a window some of whose route handlers may be fetching, and leave nothing behind.

    A handler that calls `route.fetch()` is a call in flight until the answer is back. Closing the
    context disposes the request context under it; the fetch then raises "Request context
    disposed" in the handler, and Playwright raises that in the NEXT synchronous call of the
    process -- the first call of the next test, which then fails for a reason that is none of its
    own. Every route is unrouted first, telling the handlers in flight that their errors are
    nobody's (`ignoreErrors`). `wait` is not used: it waits for every handler to finish, and a
    handler that holds a route for the test to answer never does. Unrouting the last route turns
    the page's interception off, which can strand a read paused across the switch, but the page
    is closed on the next line and has nobody left to be waiting for it.
    """
    for page in context.pages:
        page.unroute_all(behavior="ignoreErrors")
    context.unroute_all(behavior="ignoreErrors")
    context.close()


def until(page: Page, what: str, done: Callable[[], Any]) -> None:
    """Wait, pumping the page, until a fact of this side of the wire holds."""
    for _ in range(160):
        if done():
            return
        page.wait_for_timeout(50)
    raise AssertionError(f"the page never reached: {what}")


def read_again(page: Page, controls: Hold, start: Callable[[], None]) -> None:
    """`start` makes a full refresh; the desk stands on its earlier read of the run until
    `land_read`: the controls read the new one needs is held."""
    controls.hold()
    start()
    until(page, "the scene's read of the run is held", controls.reached)
    expect(page.locator("#deskScene")).to_have_attribute("data-state", "stale")


def land_read(page: Page, controls: Hold) -> None:
    """The held read lands and the scene is ready again."""
    controls.land()
    expect(page.locator("#deskScene")).to_have_attribute("data-state", "ready")
