"""The Desk acceptance UI confirms only a fresh preview for its selected run."""
from __future__ import annotations

from tests.desk_wizard_node import run_js


DOM = """
globalThis.document = {createTextNode(text) {return {textContent: text}}, createElement(tag) {
  return {tag, children: [], listeners: {}, textContent: '', disabled: false,
    setAttribute(name, value) {this[name] = value},
    addEventListener(name, fn) {this.listeners[name] = fn},
    append(...nodes) {this.children.push(...nodes)},
    replaceChildren(...nodes) {this.children = nodes}, remove() {this.children = []}};
}};
const find = (node, label) => node.textContent === label ? node :
  (node.children || []).map((child) => find(child, label)).find(Boolean);
const hasText = (node, value) => String(node.textContent || '').includes(value)
  || (node.children || []).some((child) => hasText(child, value));
const keyed = (node, key) => node['data-focus-key'] === key ? node :
  (node.children || []).map((child) => keyed(child, key)).find(Boolean);
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
const detail = (task, run) => ({run: {run_id: run}, config: {task: {id: task}},
  graph: {definition: {nodes: []}}, records: []});
const desk = (task, run) => ({taskId: task, actor: 'Owner', mode: 'active',
  run: {phase: 'ready', detail: detail(task, run)}});
let chosen = {taskId: 'task-one', runId: 'run-one', foreign: false,
  mode: 'active', connection: 'open', ready: true};
const preview = {run_id: 'run-one', task_id: 'task-one', kind: 'files',
  accept_digest: 'sha256:' + 'a'.repeat(64), base: {commit: 'b'.repeat(40)},
  branch: 'conduct/run-one', author: {name: 'Owner', email: 'o@example.com'},
  files: [], skipped: [], documents: [], warnings: [], message: 'Reviewed',
  patch: {text: '', truncated: false}};
"""


def test_accept_confirmation_carries_exact_digest_and_actor_and_displays_record():
    out = run_js(DOM + """
      const sent = [];
      const door = {readJson: async () => ({kind: 'files', basis: {}, commit: null}),
        submit: async (target, run, body) => {sent.push({target, run, body});
          return target === 'acceptPreview' ? {status: 'accepted', payload: {accept: preview}}
            : {status: 'accepted', payload: {commit: {accept_digest: preview.accept_digest,
              branch: preview.branch, commit: 'c'.repeat(40)}}};}};
      const host = acceptHost.createAcceptHost({door, binding: () => chosen,
        locale: () => 'en', onChange: () => {}, onForeign: () => {}});
      host.render(desk('task-one', 'run-one'), false); await tick();
      host.render(desk('task-one', 'run-one'), false);
      const compact = {open: !!find(host.pult, 'Open acceptance details'),
        title: !!keyed(host.pult, 'desk.accept.title'),
        preview: !!find(host.pult, 'Read preview')};
      host.render(desk('task-one', 'run-one'), true);
      find(host.detail, 'Read preview').listeners.click(); await tick();
      host.render(desk('task-one', 'run-one'), true);
      find(host.detail, 'Review confirmation').listeners.click();
      host.render(desk('task-one', 'run-one'), true);
      find(host.detail, 'Create local branch and commit').listeners.click(); await tick();
      host.render(desk('task-one', 'run-one'), true);
      console.log(JSON.stringify({sent, compact,
        commitShown: hasText(host.detail, 'c'.repeat(40))}));
    """, modules={"acceptHost": "desk-accept-host.js"})
    assert out["sent"] == [
        {"target": "acceptPreview", "run": "run-one", "body": {}},
        {"target": "acceptCommit", "run": "run-one", "body": {
            "accept_digest": "sha256:" + "a" * 64, "actor": "Owner"}},
    ]
    assert out["commitShown"]
    assert out["compact"] == {"open": True, "title": False, "preview": False}


def test_late_preview_cannot_confirm_after_run_changes():
    out = run_js(DOM + """
      let release, writes = 0;
      const door = {readJson: async () => ({kind: 'files', basis: {}, commit: null}),
        submit: (target) => {writes += 1; return new Promise((resolve) => {release = resolve})}};
      const host = acceptHost.createAcceptHost({door, binding: () => chosen,
        locale: () => 'en', onChange: () => {}, onForeign: () => {}});
      host.render(desk('task-one', 'run-one'), true); await tick();
      host.render(desk('task-one', 'run-one'), true);
      find(host.detail, 'Read preview').listeners.click(); await tick();
      chosen = {...chosen, taskId: 'task-two', runId: 'run-two'};
      host.render(desk('task-two', 'run-two'), true); await tick();
      release({status: 'accepted', payload: {accept: preview}}); await tick();
      host.render(desk('task-two', 'run-two'), true);
      console.log(JSON.stringify({writes,
        staleConfirm: !!find(host.detail, 'Review confirmation'),
        staleDigest: hasText(host.detail, preview.accept_digest)}));
    """, modules={"acceptHost": "desk-accept-host.js"})
    assert out == {"writes": 1, "staleConfirm": False, "staleDigest": False}


def test_changing_preview_terms_retires_its_pending_answer():
    out = run_js(DOM + """
      let release, writes = [];
      const door = {readJson: async () => ({kind: 'files', basis: {}, commit: null}),
        submit: (target, run, body) => {writes.push(body);
          return new Promise((resolve) => {release = resolve})}};
      const host = acceptHost.createAcceptHost({door, binding: () => chosen,
        locale: () => 'en', onChange: () => {}, onForeign: () => {}});
      host.render(desk('task-one', 'run-one'), true); await tick();
      host.render(desk('task-one', 'run-one'), true);
      find(host.detail, 'Read preview').listeners.click(); await tick();
      const title = keyed(host.detail, 'desk.accept.title');
      title.value = 'New title'; title.listeners.input();
      host.render(desk('task-one', 'run-one'), true);
      release({status: 'accepted', payload: {accept: preview}}); await tick();
      host.render(desk('task-one', 'run-one'), true);
      const oldShown = !!find(host.detail, 'Review confirmation');
      find(host.detail, 'Read preview').listeners.click(); await tick();
      console.log(JSON.stringify({oldShown, writes}));
    """, modules={"acceptHost": "desk-accept-host.js"})
    assert out == {"oldShown": False, "writes": [{}, {"title": "New title"}]}


#: The desk draws the run it holds as `stale` while it reads the run again (`desk.js`,
#: whileReading): `stale` is the earlier read, and the binding is not ready until the new one
#: has landed.
STALE = """
const stale = (task, run) => ({...desk(task, run),
  run: {phase: 'stale', detail: detail(task, run)}});
const changed = (task, run) => ({...desk(task, run), run: {phase: 'ready',
  detail: {...detail(task, run), run: {run_id: run, status: 'active'}}}});
const make = (door) => acceptHost.createAcceptHost({door, binding: () => chosen,
  locale: () => 'en', onChange: () => {}, onForeign: () => {}});
const ready = (host) => {
  chosen = {...chosen, ready: true}; host.render(desk('task-one', 'run-one'), true);};
const reread = (host) => {
  chosen = {...chosen, ready: false}; host.render(stale('task-one', 'run-one'), true);};
const facts = async () => ({kind: 'files', basis: {}, commit: null});
const typeTitle = (host, value) => {
  const title = keyed(host.detail, 'desk.accept.title');
  title.value = value; title.listeners.input();};
"""
MODULES = {"acceptHost": "desk-accept-host.js"}


def test_a_stale_read_of_the_same_run_keeps_entries_and_stage_and_refuses_presses_until_it_lands():
    out = run_js(DOM + STALE + """
      const sent = [];
      let reads = 0;
      const door = {readJson: async () => {reads += 1; return facts();},
        submit: async (target) => {sent.push(target);
          return target === 'acceptPreview' ? {status: 'accepted', payload: {accept: preview}}
            : {status: 'accepted', payload: {commit: {accept_digest: preview.accept_digest,
              branch: preview.branch, commit: 'c'.repeat(40)}}};}};
      const host = make(door), press = (label) => find(host.detail, label).listeners.click();
      ready(host); await tick(); ready(host);
      typeTitle(host, 'Mine'); ready(host);
      press('Read preview'); await tick(); ready(host);
      reread(host);
      const kept = {title: keyed(host.detail, 'desk.accept.title').value,
        digest: hasText(host.detail, preview.accept_digest),
        reviewOff: find(host.detail, 'Review confirmation').disabled};
      press('Review confirmation'); reread(host);
      const reviewed = !!find(host.detail, 'Create local branch and commit');
      ready(host); press('Review confirmation'); ready(host);
      reread(host);
      const commitOff = find(host.detail, 'Create local branch and commit').disabled;
      press('Create local branch and commit'); await tick();
      const sentWhileStale = [...sent];
      ready(host); press('Create local branch and commit'); await tick(); ready(host);
      console.log(JSON.stringify({kept, reviewed, commitOff, sentWhileStale, sent, reads,
        commitShown: hasText(host.detail, 'c'.repeat(40))}));
    """, modules=MODULES)
    assert out == {"kept": {"title": "Mine", "digest": True, "reviewOff": True},
                   "reviewed": False, "commitOff": True, "sentWhileStale": ["acceptPreview"],
                   "sent": ["acceptPreview", "acceptCommit"], "reads": 1, "commitShown": True}


def test_a_preview_answer_that_lands_during_a_stale_read_is_kept_and_usable_once_it_lands():
    out = run_js(DOM + STALE + """
      let release;
      const sent = [];
      const door = {readJson: facts, submit: (target) => {sent.push(target);
        return new Promise((resolve) => {release = resolve})}};
      const host = make(door);
      ready(host); await tick(); ready(host);
      find(host.detail, 'Read preview').listeners.click(); await tick();
      reread(host);
      release({status: 'accepted', payload: {accept: preview}}); await tick();
      reread(host);
      const during = {digest: hasText(host.detail, preview.accept_digest),
        reviewOff: find(host.detail, 'Review confirmation').disabled};
      ready(host);
      console.log(JSON.stringify({during, sent,
        reviewOff: find(host.detail, 'Review confirmation').disabled}));
    """, modules=MODULES)
    assert out == {"during": {"digest": True, "reviewOff": True}, "sent": ["acceptPreview"],
                   "reviewOff": False}


def test_a_stale_read_that_lands_with_a_changed_run_state_resets_entries_and_reads_facts_again():
    out = run_js(DOM + STALE + """
      let reads = 0;
      const door = {readJson: async () => {reads += 1; return facts();},
        submit: async () => ({status: 'accepted', payload: {accept: preview}})};
      const host = make(door);
      ready(host); await tick(); ready(host);
      typeTitle(host, 'Mine'); ready(host);
      find(host.detail, 'Read preview').listeners.click(); await tick(); ready(host);
      reread(host);
      chosen = {...chosen, ready: true};
      host.render(changed('task-one', 'run-one'), true); await tick();
      host.render(changed('task-one', 'run-one'), true);
      console.log(JSON.stringify({title: keyed(host.detail, 'desk.accept.title').value,
        digest: hasText(host.detail, preview.accept_digest), reads}));
    """, modules=MODULES)
    assert out == {"title": "", "digest": False, "reads": 2}


def test_a_stale_read_that_shows_another_run_of_the_task_resets_and_reads_that_run():
    out = run_js(DOM + STALE + """
      const asked = [];
      const door = {readJson: async (target) => {asked.push(target); return facts();},
        submit: async () => ({status: 'accepted', payload: {accept: preview}})};
      const host = make(door);
      ready(host); await tick(); ready(host);
      typeTitle(host, 'Mine'); ready(host);
      chosen = {...chosen, ready: false, runId: 'run-two'};
      host.render(stale('task-one', 'run-two'), true);
      const noRun = hasText(host.detail, 'Choose a run first.');
      chosen = {...chosen, ready: true};
      host.render(desk('task-one', 'run-two'), true); await tick();
      host.render(desk('task-one', 'run-two'), true);
      console.log(JSON.stringify({noRun, asked,
        title: keyed(host.detail, 'desk.accept.title').value}));
    """, modules=MODULES)
    assert out["noRun"] is True and out["title"] == ""
    assert len(out["asked"]) == 2 and out["asked"][0] != out["asked"][1]
