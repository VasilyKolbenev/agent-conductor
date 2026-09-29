"""A fake queue, automation and preview door with a memory, for the wizard's step 6.

Not a test module (pytest does not collect it). It stands where the doors of spec 4.4.5-4.4.6 and
6.4.4-6.4.5 will stand, behind the asks the card makes (`launch_queue`, `launch_automation`,
`launch_run`, `launch_preview`, `launch_authorize`, `launch_enqueue`) and in front of whatever
answered before it. It keeps the slot, the queue's entries, the grant that was written and the
preview it last served, so a repeated write finds what stands, a lost answer can land without being
heard, and a refusal (with the slot it leaves behind) comes on demand.

The preview it serves after the chain's own is the standing one with fresh instants taken from the
host's clock (`launch.now`), so the countdown a test moves is the countdown the server would count;
`overrides[i]` is merged into the i-th repeat (its terms too) to make the server answer another
digest.
"""
from __future__ import annotations

from typing import Any

from tests.desk_wizard_node import fixture

QUEUE_JS = """
(setup) => {
  const queue = structuredClone(setup.queue);
  const world = {queue, automation: structuredClone(setup.automation), grants: {},
    authorize_calls: 0, enqueue_calls: 0, previews: 0, reads: {queue: 0, automation: 0, run: 0},
    authorize_bodies: [], enqueue_bodies: [], calls: [], lose: {...setup.lose},
    drop: {...setup.drop},
    refuse: structuredClone(setup.refuse), served: setup.preview, seen: {}};
  const said = (payload) => ({status: "accepted", code: null, payload});
  const refuse = (code, detail) => ({status: "refused", code, payload: {error: {code,
    message: code, detail: detail || {}}}});
  const answer = (name, payload) => {
    if ((world.lose[name] || 0) > 0) {
      world.lose[name] -= 1;
      return {status: "unknown", code: null, payload: null};
    }
    return said(payload);
  };
  const seconds = (iso) => Date.parse(iso) / 1000;
  const iso = (secs) => new Date(secs * 1000).toISOString().replace(".000Z", "Z");
  const same = (left, right) => JSON.stringify(left) === JSON.stringify(right);
  const AUTHORIZE = ["authorization_id", "authorized_by", "preview_digest", "supersedes", "terms"];
  const refused = (name) => {
    const rule = world.refuse[name];
    world.seen[name] = (world.seen[name] || 0) + 1;
    if (!rule || rule.count <= 0 || world.seen[name] <= (rule.after || 0)) return null;
    rule.count -= 1;
    if (rule.slot) world.queue.slot = rule.slot;
    return refuse(rule.code, rule.detail);
  };
  const repeat = () => {
    const at = world.previews;
    world.previews += 1;
    const over = setup.overrides[Math.min(at, setup.overrides.length - 1)] || {};
    const now = window.host.state.wizard.launch.now;
    const start = now === null ? seconds(setup.preview.previewed_at) : seconds(now);
    const next = structuredClone(setup.preview);
    Object.assign(next, over, {terms: {...next.terms, ...(over.terms || {})}});
    next.previewed_at = iso(start);
    next.valid_until = iso(start + 300);
    world.served = next;
    return next;
  };
  const grantOf = (body) => {
    const {duration_seconds: _window, ...terms} = body.terms;
    return {...terms, authorization_id: body.authorization_id, authorized_by: body.authorized_by,
      supersedes: body.supersedes, authorized_at: iso(seconds(world.served.previewed_at)),
      expires_at: iso(seconds(world.served.previewed_at) + body.terms.duration_seconds)};
  };
  const handlers = {
    launch_queue: () => { world.reads.queue += 1; return said(structuredClone(world.queue)); },
    launch_automation: () => {
      world.reads.automation += 1;
      return said(structuredClone(world.automation));
    },
    launch_run: () => { world.reads.run += 1; return said(setup.run); },
    launch_preview: () => answer("launch_preview", repeat()),
    launch_authorize: (ask) => {
      const body = ask.body, id = body.authorization_id;
      if (!same(Object.keys(body).sort(), AUTHORIZE)) return refuse("contract_invalid");
      if (world.grants[id] === undefined) {
        if (world.queue.slot.reason_code === "project_not_active") {
          return refuse("project_not_active");
        }
        if (world.queue.slot.state !== "free") {
          return refuse("slot_busy", {run_id: world.queue.slot.run_id});
        }
        if (body.preview_digest !== world.served.preview_digest) return refuse("preview_stale");
        world.grants[id] = grantOf(body);
        world.automation = {...world.automation, authorization: world.grants[id],
          state: "running", reason_code: null};
      }
      return answer("launch_authorize", {authorization_id: id});
    },
    launch_enqueue: (ask) => {
      const start = ask.body.start;
      const held = world.queue.entries.find((row) => row.run_id === ask.body.run_id);
      if (held === undefined) {
        const viewing = world.queue.slot.reason_code === "project_not_active";
        world.queue.entries.push({run_id: ask.body.run_id, task_id: "task-bench",
          title: "Fix login", position: world.queue.entries.length + 1, kind: "start",
          enqueued_at: "2026-09-29T10:01:00Z", enqueued_by: start.authorized_by,
          state: "preauthorized", reason_code: viewing ? "project_not_active" : "slot_busy",
          state_since: "2026-09-29T10:01:00Z",
          preauthorization: {authorized_by: start.authorized_by,
            preauthorized_at: "2026-09-29T10:01:00Z", digest: start.preview_digest}});
      }
      return answer("launch_enqueue", structuredClone(world.queue));
    },
  };
  const prior = window.host.fake;
  window.host.launchWorld = world;
  window.host.fake = (ask) => {
    if (!Object.hasOwn(handlers, ask.name)) return prior ? prior(ask) : undefined;
    world.calls.push({name: ask.name, subject: ask.subject, id: ask.id});
    //: A write is counted when it is sent, whatever becomes of it: lost, dropped or refused.
    if (ask.name === "launch_authorize") {
      world.authorize_calls += 1;
      world.authorize_bodies.push(ask.body);
    }
    if (ask.name === "launch_enqueue") {
      world.enqueue_calls += 1;
      world.enqueue_bodies.push(ask.body);
    }
    if ((world.drop[ask.name] || 0) > 0) {
      world.drop[ask.name] -= 1;
      return {status: "unknown", code: null, payload: null};
    }
    return refused(ask.name) || handlers[ask.name](ask);
  };
}
"""


def install(bench: Any, *, queue: str = "queue_free", automation: str = "automation_unconfigured",
            preview: Any = None, overrides: list[dict[str, Any]] | None = None,
            lose: dict[str, int] | None = None, drop: dict[str, int] | None = None,
            refuse: dict[str, dict[str, Any]] | None = None) -> None:
    """Put the fake queue door in front of the card's asks (after the chain's fake server).

    `queue` and `automation` name fixtures of `tests/fixtures/wizard/`; `refuse` maps an ask name
    to `{code, count, after?, detail?, slot?}`: the slot, when given, is what the queue reads
    after that refusal (a slot taken between the read and the press). `lose` counts writes that
    land and are answered `unknown`; `drop` counts writes that never land and are answered
    `unknown` the same way.
    """
    bench.page.evaluate(QUEUE_JS, {
        "queue": fixture("wizard", f"{queue}.json"),
        "automation": fixture("wizard", f"{automation}.json"),
        "preview": preview or fixture("wizard", "preview_standard.json"),
        "run": fixture("wizard", "run_detail.json"), "overrides": overrides or [{}],
        "lose": lose or {}, "drop": drop or {}, "refuse": refuse or {}})


def world(bench: Any) -> dict[str, Any]:
    """What the fake queue door holds now, as plain data."""
    return bench.page.evaluate("() => JSON.parse(JSON.stringify(window.host.launchWorld))")
