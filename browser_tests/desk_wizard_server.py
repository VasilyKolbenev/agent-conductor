"""A fake project server with a memory, for the wizard's chain (spec 6.4.1-6.4.3).

Not a test module (pytest does not collect it). It stands where the doors will stand: the host
of `desk_wizard_bench.py` hands every ask of the chain to `window.host.fake`, and this answers
them the way the routes are specified to. It keeps a `world` (the task, the seed, the flows'
revisions, the runs, the documents), so a repeated write finds what already stands and answers
200 instead of writing a second time, a lost answer can be made to land without being heard
(`lose`), and a refusal can be made to come a number of times (`refuse`). What a test asserts
about "no second task and no second run" is read off `world`.
"""
from __future__ import annotations

from typing import Any

from tests.desk_wizard_node import fixture

#: Installed once on the bench page, after the flow door (`Bench.door`) when one is used: its
#: `window.host.fake` answers the chain's asks and hands every other ask to the one before it.
SERVER_JS = """
(setup) => {
  const world = {task: null, tasks_written: 0, seed: null, seeds_written: 0, runs: {},
    runs_written: 0, revisions: {}, published: {}, docs: {}, doc_records: 0, materials: {},
    previews: 0, calls: [], seen: {}, lose: {...setup.lose}, refuse: {...setup.refuse},
    hidden: setup.hidden || [], stage: setup.stage || null};
  //: What stood before the page loaded: the task, and the runs other windows made.
  if (setup.task) {
    world.task = {task_id: "task-bench", title: "Fix login", work_scope: "task-bench",
      created_at: "2026-09-29T10:00:00Z"};
  }
  for (const preset of setup.runs) {
    world.runs[preset.run_id] = {...preset, body: preset.body || {},
      created_at: "2026-09-29T10:00:20Z"};
    world.revisions[preset.workflow_id] = preset.revision;
  }
  const stable = (value) => JSON.stringify(value, (key, item) => (item && typeof item === "object"
    && !Array.isArray(item) ? Object.fromEntries(Object.entries(item).sort()) : item));
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
  const refs = (workflow) => (setup.flows[workflow]?.budget?.inputs?.instructions ?? [])
    .map((row) => row.instruction_ref);
  const has = (run, ref) => (world.docs[run]?.[ref] ?? []).length > 0;
  const row = (run) => {
    const instructions = refs(run.workflow_id).filter((ref) => !has(run.run_id, ref))
      .map((ref) => ({node_id: ref.replace(/^instruction-/, ""), instruction_ref: ref}));
    const inputs = ["artifact-brief", "artifact-materials"].filter(
      (ref) => !has(run.run_id, ref));
    const stage = world.stage || (instructions.length + inputs.length > 0
      ? "documents_missing" : "ready_to_preview");
    return {run_id: run.run_id, created_at: run.created_at, workflow_id: run.workflow_id,
      revision: run.revision, stage, missing: {instructions, inputs}, grant: null, queue: null};
  };
  const numbers = () => [...Object.keys(world.runs).map((id) => Number(id.split("-r").at(-1))),
    ...world.hidden];
  const read = () => ({task: {schema_version: 1, ...world.task}, seed: world.seed,
    next_run_number: 1 + Math.max(0, ...numbers()),
    runs: Object.values(world.runs).map(row)});
  const handlers = {
    prep_task: (ask) => {
      if (world.task === null) {
        world.task = {task_id: ask.body.task_id, title: ask.body.title,
          work_scope: ask.body.task_id, created_at: "2026-09-29T10:00:00Z"};
        world.tasks_written += 1;
      } else if (world.task.title !== ask.body.title) return refuse("record_conflict");
      return answer("prep_task", world.task);
    },
    prep_read: () => (world.task === null ? refuse("service_refused", {task_id: "task-bench"})
      : said(read())),
    prep_seed: (ask) => {
      if (world.seed !== null && stable(world.seed.body) !== stable(ask.body)) {
        return refuse("seed_exists");
      }
      if (world.seed === null) {
        world.seed = {...setup.seed, body: ask.body, include_agent_instructions:
          ask.body.include_agent_instructions};
        world.seeds_written += 1;
      }
      return answer("prep_seed", world.seed);
    },
    prep_flow: (ask) => {
      const wf = ask.subject, body = ask.body, standing = window.host.standing || {};
      const draft = standing[wf] ?? null;
      const changed = body.expected_digest !== undefined ? body.expected_digest !== draft
        : draft !== null;
      if (changed) return refuse("draft_conflict");
      const same = world.published[wf] === stable(body.source);
      const revision = same ? world.revisions[wf] : body.publish_revision;
      world.published[wf] = stable(body.source);
      world.revisions[wf] = revision;
      standing[wf] = null;
      return answer("prep_flow", {...setup.flows[wf], source: "published", draft_digest: null,
        latest_revision: revision, next_revision: revision + 1,
        published: {revision, created: !same}});
    },
    prep_flow_read: (ask) => said({...setup.flows[ask.subject], source: "published",
      draft_digest: null, latest_revision: world.revisions[ask.subject] ?? 1}),
    prep_run: (ask) => {
      const body = ask.body, held = world.runs[body.run_id];
      if (held !== undefined && stable(held.body) !== stable(body)) {
        return refuse("record_conflict");
      }
      if (held === undefined) {
        world.runs[body.run_id] = {run_id: body.run_id, workflow_id: body.workflow_id,
          revision: body.revision, body, created_at: "2026-09-29T10:00:20Z"};
        world.runs_written += 1;
      }
      return answer("prep_run", {run: {run_id: body.run_id}});
    },
    prep_doc: (ask) => {
      const run = ask.subject, body = ask.body;
      if (world.runs[run] === undefined) return refuse("service_refused", {run_id: run});
      const list = world.docs[run] = world.docs[run] || {};
      const ids = list[body.artifact_ref] = list[body.artifact_ref] || [];
      if (!ids.includes(body.artifact_id)) {
        ids.push(body.artifact_id);
        world.doc_records += 1;
      }
      return answer("prep_doc", {artifact_id: body.artifact_id});
    },
    prep_materials: (ask) => {
      const run = ask.subject, key = stable(ask.body);
      if (world.runs[run] === undefined) return refuse("service_refused", {run_id: run});
      const list = world.docs[run] = world.docs[run] || {};
      const ids = list["artifact-materials"] = list["artifact-materials"] || [];
      if (!ids.includes(key)) {
        ids.push(key);
        world.doc_records += 1;
      }
      return answer("prep_materials", {artifact_ref: "artifact-materials"});
    },
    preview: (ask) => {
      world.previews += 1;
      return answer("preview", setup.preview);
    },
  };
  const prior = window.host.fake;
  window.host.world = world;
  window.host.fake = (ask) => {
    if (!Object.hasOwn(handlers, ask.name)) return prior ? prior(ask) : undefined;
    world.calls.push({name: ask.name, subject: ask.subject, hash: location.hash,
      keys: ask.body && typeof ask.body === "object" ? Object.keys(ask.body) : null});
    const refused = world.refuse[ask.name];
    world.seen[ask.name] = (world.seen[ask.name] || 0) + 1;
    if (refused && refused.count > 0 && world.seen[ask.name] > (refused.after || 0)) {
      refused.count -= 1;
      //: A clash is a run that already stands with another arrangement: make it stand.
      if (refused.create_run && world.runs[ask.body.run_id] === undefined) {
        world.runs[ask.body.run_id] = {run_id: ask.body.run_id, body: {other: true},
          workflow_id: ask.body.workflow_id, revision: ask.body.revision,
          created_at: "2026-09-29T10:00:20Z"};
        world.runs_written += 1;
      }
      return refuse(refused.code, refused.detail);
    }
    return handlers[ask.name](ask);
  };
}
"""


def install(bench: Any, *, flows: dict[str, Any], lose: dict[str, int] | None = None,
            refuse: dict[str, dict[str, Any]] | None = None, hidden: list[int] | None = None,
            stage: str | None = None, preview: Any = None, task: bool = False,
            runs: list[dict[str, Any]] | None = None) -> None:
    """Put the fake server in front of the asks of the chain (and behind nothing else).

    `task` and `runs` are what stood before the page loaded; `hidden` are run numbers the server
    counts and does not list (unreadable runs); `stage` overrides the stage every run reads.
    """
    bench.page.evaluate(SERVER_JS, {
        "flows": flows, "lose": lose or {}, "refuse": refuse or {}, "hidden": hidden or [],
        "stage": stage, "preview": preview or fixture("wizard", "preview_standard.json"),
        "seed": fixture("wizard", "preparation_seeded.json")["seed"], "task": task,
        "runs": runs or []})


def world(bench: Any) -> dict[str, Any]:
    """What the fake server holds now, as plain data."""
    return bench.page.evaluate("() => JSON.parse(JSON.stringify(window.host.world))")


def names(bench: Any) -> list[str]:
    """The asks the server was called with, in order."""
    return [call["name"] for call in world(bench)["calls"]]
