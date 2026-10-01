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
