"""A setup route with a memory, for the wizard's git block, on the bench host.

`desk_wizard_server.py` is the bench's whole project server; this is the one door the git block
talks to: it answers the standing `git` read and the four asks of the setup route the way lane L's
contract says, from a small `world` it keeps (the git state, the pending operation, the receipt),
so a press changes what the next read says. It is a stand-in for the route, not a model of Git:
the real route over real Git is `test_desk_wizard_git_fresh.py`.

The answers a test wants to control are knobs of the world, never timers:

* `hold` names asks that get no answer until the test releases them (`world.release(name)`), so
  the wait while a request works can be looked at and a second press tried against it;
* `hold_read` does the same for the next git read (`release_read` answers it): the wait between
  two writes of one press;
* `lose` names asks whose write LANDS but whose answer never arrives (an unknown outcome), and
  `drop` those whose write never landed either;
* `signing` makes Git sign: a confirm stores the wait and answers `signing_required`, and
  `owner_commit` is the person having run the two commands; `crash_after_ref` leaves an
  unfinished operation after the branch moved and loses the answer;
* `door` closed answers every confirm `422 contract_invalid`, as lane L's route does today.
"""
from __future__ import annotations

import json
from typing import Any

from playwright.sync_api import Page

from tests.desk_wizard_node import FIXTURES, fixture

WORLD_JS = """
(data) => {
  const world = {git: structuredClone(data.reads[data.start].git), door: data.door,
    signing: data.signing, owner_commit: false, crash_after_ref: false, receipt: null,
    hold: new Set(data.hold), lose: new Map(), drop: new Map(), force: new Map(), posts: [],
    reads: 0, receipt_ref: null, preview_patch: null, hold_read: false};
  const accepted = (payload) => ({status: "accepted", code: null, payload});
  const refuse = (code, detail) => ({status: "refused", code,
    payload: {error: {code, message: "x", detail}}});
  const refusal = (reason) => refuse("git_setup_refused", {reason});
  const take = (table, name) => {
    const left = table.get(name) ?? 0;
    if (left > 0) table.set(name, left - 1);
    return left > 0;
  };
  const termsOf = (body) => ({mode: body.mode, paths_digest: body.paths_digest,
    digest_version: 2, requested_by: body.actor, file_count: body.mode === "empty" ? 0 : 4,
    target_ref: "refs/heads/main", author: {name: "First Author", email: "first@example.invalid"}});
  const waitFor = (body) => ({state: "awaiting_signature", terms: termsOf(body),
    signing: data.reads.git_pending_signature.git.first_commit_pending.signing});
  const signingRefusal = (pending) => refuse("git_setup_refused",
    {reason: "signing_required", ...pending.signing});
  const commit = (body, pending, signature) => {
    const base = data.receipts[signature === "present" ? "signed" : "commit"].setup;
    world.receipt = {...base, mode: body.mode, paths_digest: body.paths_digest,
      target_ref: world.receipt_ref ?? base.target_ref,
      requested_by: pending ? pending.terms.requested_by : body.actor,
      file_count: body.mode === "empty" ? 0 : base.file_count};
    world.git = {...world.git, state: "repo", head: {ref: "refs/heads/main",
      commit: world.receipt.commit}, first_commit_pending: null};
    return accepted({setup: world.receipt});
  };
  const sameTerms = (body) => world.receipt !== null && world.receipt.mode === body.mode
    && world.receipt.paths_digest === body.paths_digest
    && world.receipt.requested_by === body.actor;
  const resume = (body, pending) => {
    if (world.git.state === "repo" && pending.state === "unfinished"
        && body.actor !== pending.terms.requested_by) return refusal("setup_terms_changed");
    if (pending.state === "awaiting_signature") {
      return world.owner_commit ? commit(body, pending, "present") : signingRefusal(pending);
    }
    return commit(body, pending, "not_required");
  };
  const confirm = (body) => {
    const pending = world.git.first_commit_pending;
    if (!world.door) return refuse("contract_invalid", {});
    if (sameTerms(body)) return accepted({setup: world.receipt});
    if (pending) return resume(body, pending);
    if (world.git.state !== "unborn") {
      return refusal(world.git.state === "repo" ? "head_exists" : "not_a_git_repository");
    }
    const shown = data.previews.snapshot.setup.paths_digest;
    if (body.mode === "snapshot" && body.paths_digest !== shown) return refusal("paths_changed");
    if (world.signing) {
      world.git = {...world.git, first_commit_pending: waitFor(body)};
      return signingRefusal(world.git.first_commit_pending);
    }
    if (world.crash_after_ref) {
      world.crash_after_ref = false;
      world.git = {...world.git, state: "repo", head: {ref: "refs/heads/main",
        commit: data.receipts.commit.setup.commit}, first_commit_pending:
        {state: "unfinished", terms: termsOf(body)}};
      return {status: "unknown"};
    }
    return commit(body, null, "not_required");
  };
  const step = (body, name) => {
    const found = {...data.receipts.init.setup, step: name, requested_by: body.actor};
    return accepted({setup: found});
  };
  const init = (body) => {
    if (world.git.state !== "not_git") return refusal("already_git");
    world.git = {...world.git, state: "unborn", exclude: "written", object_format: "sha1"};
    return step(body, "init");
  };
  const exclude = (body) => {
    world.git = {...world.git, exclude: world.git.exclude === "deferred" ? "written" : "present"};
    return step(body, "exclude");
  };
  const preview = (body) => {
    if (world.git.state !== "unborn") return refusal("head_exists");
    if (world.git.first_commit_pending) return refusal("index_locked");
    const found = structuredClone(data.previews[body.mode].setup);
    if (world.signing) Object.assign(found, {signing: true, warnings: ["signing_required"]});
    return accepted({setup: Object.assign(found, world.preview_patch ?? {})});
  };
  const route = (ask) => {
    world.posts.push({name: ask.name, body: structuredClone(ask.body)});
    if (take(world.drop, ask.name)) return {status: "unknown"};
    const forced = world.force.get(ask.name);
    if (forced) return forced.bare ? {status: "refused", code: forced.code}
      : (forced.reason ? refusal(forced.reason) : refuse(forced.code, forced.detail ?? {}));
    const acts = {git_init: init, git_exclude: exclude, git_preview: preview, git_confirm: confirm};
    const result = acts[ask.name](ask.body);
    return take(world.lose, ask.name) ? {status: "unknown"} : result;
  };
  world.release = (name) => {
    const ask = [...window.host.log].reverse().find((one) => one.name === name);
    world.hold.delete(name);
    return window.host.dispatch({type: "answered", ask, result: route(ask)});
  };
  world.release_read = () => {
    const ask = [...window.host.log].reverse().find((one) => one.name === "git");
    world.hold_read = false;
    world.reads += 1;
    return window.host.dispatch({type: "answered", ask,
      result: accepted({git: structuredClone(world.git)})});
  };
  window.host.world = world;
  window.host.fake = (ask) => {
    if (ask.name === "git") {
      if (world.hold_read) return undefined;
      world.reads += 1;
      return accepted({git: structuredClone(world.git)});
    }
    if (!Object.hasOwn({git_init: 1, git_exclude: 1, git_preview: 1, git_confirm: 1}, ask.name)) {
      return undefined;
    }
    return world.hold.has(ask.name) ? undefined : route(ask);
  };
}
"""


def _data(start: str, **options: Any) -> dict[str, Any]:
    reads = {path.stem: json.loads(path.read_text(encoding="utf-8"))
             for path in sorted((FIXTURES / "wizard").glob("git_*.json"))}
    return {"start": start, "reads": reads, "door": options.get("door", True),
            "signing": options.get("signing", False), "hold": options.get("hold", []),
            "previews": {"snapshot": fixture("wizard", "setup_preview_snapshot.json"),
                         "empty": fixture("wizard", "setup_preview_empty.json")},
            "receipts": {"commit": fixture("wizard", "setup_receipt_commit.json"),
                         "signed": fixture("wizard", "setup_receipt_commit_signed.json"),
                         "init": fixture("wizard", "setup_receipt_init.json")}}


class GitWorld:
    """The world on one bench page: install it before the wizard opens, then read what it saw."""

    def __init__(self, page: Page) -> None:
        self.page = page

    @classmethod
    def install(cls, bench: Any, start: str = "git_unborn", **options: Any) -> "GitWorld":
        """Put the route in front of the bench host. `start` names the git stand-in it begins as.

        Options: `door` (default open), `signing`, `hold` (ask names that get no answer yet)."""
        bench.page.evaluate(WORLD_JS, _data(start, **options))
        return cls(bench.page)

    def set(self, **changes: Any) -> None:
        """Change knobs of the world: `owner_commit`, `signing`, `door`, `crash_after_ref`."""
        self.page.evaluate("(changes) => { Object.assign(window.host.world, changes); }", changes)

    def swap(self, git: dict[str, Any]) -> None:
        """Replace the git state the route holds, as another process of the owner would."""
        self.page.evaluate("(git) => { window.host.world.git = git; }", git)

    def lose(self, name: str, times: int = 1, *, landed: bool = True) -> None:
        """The next `times` answers to `name` never arrive; the write landed unless `landed`
        is False."""
        table = "lose" if landed else "drop"
        self.page.evaluate(
            "([table, name, times]) => { window.host.world[table].set(name, times); }",
            [table, name, times])

    def force(self, name: str, **refusal: Any) -> None:
        """Answer every `name` with a refusal: `reason=` (a git_setup_refused reason), or `code=`
        (and `detail=`), or `code=` with `bare=True` (the desk's own door, no body)."""
        self.page.evaluate("([name, found]) => { window.host.world.force.set(name, found); }",
                           [name, refusal])

    def unforce(self, name: str) -> None:
        self.page.evaluate("(name) => { window.host.world.force.delete(name); }", name)

    def hold(self, name: str) -> None:
        self.page.evaluate("(name) => { window.host.world.hold.add(name); }", name)

    def release(self, name: str) -> None:
        """Answer the held ask `name` now, from the world as it stands."""
        self.page.evaluate("(name) => window.host.world.release(name)", name)

    def hold_read(self) -> None:
        """The next git read gets no answer until `release_read`: the wait between two requests.

        The bench host falls back to its table of canned answers for an ask the world leaves
        unanswered, so the canned git read is taken out: the world answers every git read itself."""
        self.page.evaluate("() => { delete window.host.auto.git; "
                           "window.host.world.hold_read = true; }")

    def release_read(self) -> None:
        """Answer the held git read now, from the world as it stands."""
        self.page.evaluate("() => window.host.world.release_read()")

    def posts(self) -> list[dict[str, Any]]:
        """Every write the route received, in order: `{name, body}`."""
        return self.page.evaluate("() => window.host.world.posts")

    def git(self) -> dict[str, Any]:
        return self.page.evaluate("() => window.host.world.git")

    def reads(self) -> int:
        return self.page.evaluate("() => window.host.world.reads")
