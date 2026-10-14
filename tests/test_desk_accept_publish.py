"""The accept card sends the accepted commit to GitHub and opens its pull request (spec 9.7).

Two steps after the commit, each its own press with its own record: the push shows its terms
(the three facts and the exact command) before it asks for a confirmation that carries the digest
and the actor; the pull request is made from fields the owner edits. The real host runs under Node
with a fake door, so what is held is what the card draws and what it sends. The rule held through
every test: an outside action is never repeated by the card itself, and an answer that is not
known leaves only "Check again", which the server answers by looking and never by acting.
"""
from __future__ import annotations

import pytest

from tests.desk_wizard_node import run_js
from tests.test_desk_accept_host import DOM, MODULES, STALE

ALL = {**MODULES, "i18n": "studio-i18n.js"}
PREFIX = "accept:push:desk.accept."
PR_PREFIX = "accept:pr:desk.accept."
#: The server, as far as the card can see it: the acceptance facts, the project's Git facts, and
#: the answers the push and the pull request routes give, taken in order.
SERVER = """
const ACC = 'acc-' + 'a'.repeat(32), REF = 'refs/heads/conduct/run-one', OID = 'c'.repeat(40);
const COMMIT = {schema_version: 1, acceptance_id: ACC, run_id: 'run-one', task_id: 'task-one',
  kind: 'files', base_commit: 'b'.repeat(40), commit: OID, tree: 'd'.repeat(40),
  branch: 'conduct/run-one', accept_digest: 'sha256:' + 'a'.repeat(64),
  accept_manifest_digest: 'sha256:' + 'f'.repeat(64), file_count: 3, requested_by: 'Owner',
  recorded_at: '2026-10-14T10:00:00Z'};
const TERMS = {commit: OID, remote: 'origin', push_url: 'https://github.com/o/r.git', repo: 'o/r',
  ref: REF, command: 'git -C /p push --porcelain --no-follow-tags ' + OID + ':' + REF,
  push_digest: 'sha256:' + 'e'.repeat(64)};
const PUSHED = {schema_version: 1, acceptance_id: ACC, remote: 'origin', push_url: TERMS.push_url,
  remote_repo: 'o/r', ref: REF, commit: OID, push_digest: TERMS.push_digest, remote_oid: OID,
  requested_by: 'Owner', pushed_at: '2026-10-14T10:05:00Z'};
const PULL = {schema_version: 1, acceptance_id: ACC, repo: 'o/r', number: 7,
  url: 'https://github.com/o/r/pull/7', draft: false, base: 'main', head_ref: 'conduct/run-one',
  head_oid: OID, mismatch: null, requested_by: 'Owner', created_at: '2026-10-14T10:06:00Z'};
const GIT = {git: {state: 'repo', head: {ref: 'refs/heads/main', commit: 'b'.repeat(40)},
  remotes: [{name: 'origin', github: 'o/r', url_has_credentials: false}]}};
const ok = (key, value) => ({status: 'accepted', payload: {[key]: value}});
const refused = (reason, over = {}) => ({status: 'refused', code: 'accept_refused', payload:
  {error: {code: 'accept_refused', detail: {reason, ...over}}}});
const unknown = {status: 'unknown'};
const base = (over) => ({kind: 'files', basis: {}, commit: COMMIT, push: null,
  pull_request: null, ...over});
const rig = (over = {}) => {
  const served = {facts: base(over.facts), git: over.git ?? GIT};
  const sent = [], reads = [], left = {acceptPush: [...(over.push ?? [])],
    acceptPullRequest: [...(over.pull ?? [])]};
  let foreign = false;
  const door = {readJson: async (target) => { reads.push(target);
      if (target === '/command/project/git') {
        if (over.gitFails) throw new Error('store_error');
        return served.git;
      }
      return served.facts; },
    submit: async (target, run, body) => { sent.push({target, run, body});
      const next = left[target].shift();
      return next === undefined ? {status: 'unknown'} : next; }};
  const host = acceptHost.createAcceptHost({door, binding: () => chosen,
    locale: () => over.locale ?? 'en', onChange: () => {}, onForeign: () => { foreign = true; }});
  return {host, sent, reads, left, served, isForeign: () => foreign};
};
let signer = 'Owner';
const shown = (r, mode = 'active') => r.host.render(
  {...desk('task-one', 'run-one'), mode, actor: signer}, true);
const opened = async (r) => { shown(r); await tick(); shown(r); };
const press = async (r, key) => { keyed(r.host.detail, key).listeners.click(); await tick();
  shown(r); };
// A press the card may not offer: a missing button is a thing to assert, not a crash.
const pressIf = async (r, key) => { if (keyed(r.host.detail, key)) await press(r, key); };
const keysOf = (node, out = []) => { if (node.tag === 'button') out.push(node['data-focus-key']);
  for (const child of node.children || []) keysOf(child, out); return out; };
const live = (node) => { const out = [];
  const walk = (one) => {
    if (one.tag === 'button' && !one.disabled) out.push(one['data-focus-key']);
    for (const child of one.children || []) walk(child); };
  walk(node); return out; };
const statuses = (node, out = []) => { if (node.role === 'status') out.push(node.textContent);
  for (const child of node.children || []) statuses(child, out); return out; };
const kinds = (r) => r.sent.map(({body}) => body.preview ? 'terms' : body.check ? 'check' : 'send');
const said = (locale, key, params) => i18n.localize({locale}, key, params);
"""
PUSH_CLICK = ("accept:push:desk.accept.push.terms", "accept:push:desk.accept.review",
              "accept:push:desk.accept.push.action")


def _js(body: str, data=None):
    return run_js(DOM + STALE + SERVER + body, data=data, modules=ALL)


def test_the_push_step_reads_the_terms_then_sends_only_the_digest_and_actor_the_card_showed():
    out = _js("""
      const r = rig({push: [ok('push_terms', TERMS), ok('push', PUSHED)]});
      await opened(r);
      const first = live(r.host.detail);
      await press(r, 'accept:push:desk.accept.push.terms');
      const card = r.host.detail;
      const terms = {repo: hasText(card, 'o/r'), url: hasText(card, TERMS.push_url),
        ref: hasText(card, REF), command: hasText(card, TERMS.command),
        digest: hasText(card, TERMS.push_digest), commit: hasText(card, OID),
        send: !!keyed(card, 'accept:push:desk.accept.push.action'), buttons: live(card)};
      await press(r, 'accept:push:desk.accept.review');
      const reviewing = {text: hasText(r.host.detail, said('en', 'desk.accept.push.confirm_text',
        {commit: OID.slice(0, 7), repo: 'o/r', ref: REF, digest: TERMS.push_digest,
         actor: 'Owner'})), buttons: live(r.host.detail), sentSoFar: r.sent.length};
      await press(r, 'accept:push:desk.accept.push.action');
      const done = {sent: hasText(r.host.detail, 'Sent to GitHub'),
        oid: hasText(r.host.detail, OID), buttons: live(r.host.detail)};
      console.log(JSON.stringify({sent: r.sent, reads: r.reads, first, terms, reviewing, done}));
    """)
    assert out["first"] == [PREFIX + "push.terms"]
    assert out["reads"] == ["/command/runs/run-one/accept", "/command/project/git"]
    assert out["terms"] == {
        "repo": True, "url": True, "ref": True, "command": True, "digest": True, "commit": True,
        "send": False, "buttons": [PREFIX + "review"]}
    assert out["reviewing"] == {"text": True, "sentSoFar": 1, "buttons": [
        PREFIX + "push.action", PREFIX + "push.back"]}
    assert out["sent"] == [
        {"target": "acceptPush", "run": "run-one", "body": {
            "acceptance_id": "acc-" + "a" * 32, "remote": "origin", "preview": True}},
        {"target": "acceptPush", "run": "run-one", "body": {
            "acceptance_id": "acc-" + "a" * 32, "remote": "origin",
            "push_digest": "sha256:" + "e" * 64, "actor": "Owner"}}]
    assert out["done"]["sent"] and out["done"]["oid"]
    assert out["done"]["buttons"] == ["accept:pr:desk.accept.review"]


def test_an_unknown_push_answer_leaves_only_check_again_and_the_check_never_sends():
    out = _js("""
      const r = rig({push: [ok('push_terms', TERMS), unknown, ok('push', null),
        ok('push', PUSHED)]});
      await opened(r);
      for (const key of d) await press(r, key);
      const unknownStage = {buttons: live(r.host.detail),
        says: hasText(r.host.detail, said('en', 'desk.accept.push.unknown')),
        command: hasText(r.host.detail, TERMS.command)};
      for (let turn = 0; turn < 3; turn += 1) { await tick(); shown(r); }
      const quiet = r.sent.length;
      await press(r, 'accept:push:desk.accept.check');
      const absent = {buttons: live(r.host.detail),
        says: hasText(r.host.detail, said('en', 'desk.accept.push.absent'))};
      await press(r, 'accept:push:desk.accept.push.again');
      console.log(JSON.stringify({kinds: kinds(r), sent: r.sent.slice(1), unknownStage, quiet,
        absent, done: hasText(r.host.detail, 'Sent to GitHub')}));
    """, list(PUSH_CLICK))
    assert out["kinds"] == ["terms", "send", "check", "send"]
    assert out["unknownStage"] == {"buttons": [PREFIX + "check"], "says": True, "command": True}
    assert out["quiet"] == 2
    assert out["absent"] == {"buttons": [PREFIX + "push.again"], "says": True}
    bodies = [row["body"] for row in out["sent"]]
    assert bodies[1] == {**bodies[0], "check": True}
    assert bodies[2] == bodies[0] and out["done"]


#: What the card offers after each refusal of the confirmation: only "Check again" when the
#: answer left it unknown, "Send again" when the look found no branch there, and a fresh read of
#: the terms for every refusal that is final.
AFTER_PUSH_REFUSAL = {
    "push_unconfirmed": ["check"], "push_auth_failed": ["check"],
    "push_timed_out": ["push.again"], "git_failed": ["push.again"],
    "git_timed_out": ["push.again"],
    "push_rejected": ["push.terms"], "push_terms_changed": ["push.terms"],
    "push_not_permitted": ["push.terms"], "push_url_ambiguous": ["push.terms"],
    "push_destination_mismatch": ["push.terms"], "remote_url_has_credentials": ["push.terms"],
    "gh_not_logged_in": ["push.terms"], "push_requires_commit": ["push.terms"],
}


def test_each_refusal_of_the_confirmation_is_said_and_leaves_exactly_the_right_next_press():
    out = _js("""
      const result = {};
      for (const reason of Object.keys(d)) {
        const r = rig({push: [ok('push_terms', TERMS), refused(reason)]});
        await opened(r);
        for (const key of ['accept:push:desk.accept.push.terms',
          'accept:push:desk.accept.review', 'accept:push:desk.accept.push.action']) {
          await press(r, key);
        }
        result[reason] = {buttons: live(r.host.detail),
          says: hasText(r.host.detail, said('en', 'accept.reason.' + reason)),
          sent: r.sent.length};
      }
      console.log(JSON.stringify(result));
    """, AFTER_PUSH_REFUSAL)
    for reason, offered in AFTER_PUSH_REFUSAL.items():
        assert out[reason] == {"buttons": [PREFIX + name for name in offered],
                               "says": True, "sent": 2}, reason


def test_a_refusal_that_is_not_an_acceptance_refusal_is_said_by_its_code():
    out = _js("""
      const wire = {status: 'refused', code: 'tool_unavailable', payload: {error: {
        code: 'tool_unavailable', detail: {tool: 'gh', reason: 'not_pinned'}}}};
      const r = rig({push: [ok('push_terms', TERMS), wire]});
      await opened(r);
      for (const key of d) await press(r, key);
      console.log(JSON.stringify({buttons: live(r.host.detail),
        says: hasText(r.host.detail, said('en', 'error.tool_unavailable'))}));
    """, list(PUSH_CLICK))
    assert out == {"buttons": [PREFIX + "push.terms"], "says": True}


def test_several_github_remotes_are_chosen_by_the_owner_and_only_that_one_is_asked_about():
    out = _js("""
      const git = {git: {...GIT.git, remotes: [
        {name: 'backup', github: null, url_has_credentials: false},
        {name: 'origin', github: 'o/r', url_has_credentials: false},
        {name: 'upstream', github: 'u/r', url_has_credentials: false}]}};
      const r = rig({git, push: [ok('push_terms', {...TERMS, remote: 'upstream', repo: 'u/r'})]});
      await opened(r);
      await press(r, 'accept:push:desk.accept.push.terms');
      const choice = {buttons: live(r.host.detail), sent: r.sent.length,
        says: hasText(r.host.detail, said('en', 'desk.accept.push.choose'))};
      await press(r, 'accept:push:remote:upstream');
      console.log(JSON.stringify({choice, sent: r.sent, reads: r.reads.length,
        terms: hasText(r.host.detail, 'u/r')}));
    """)
    assert out["choice"] == {
        "buttons": ["accept:push:remote:origin", "accept:push:remote:upstream"],
        "sent": 0, "says": True}
    assert out["sent"] == [{"target": "acceptPush", "run": "run-one", "body": {
        "acceptance_id": "acc-" + "a" * 32, "remote": "upstream", "preview": True}}]
    assert out["reads"] == 2 and out["terms"]


def test_a_project_with_no_github_remote_asks_nothing_and_a_failed_read_can_be_pressed_again():
    out = _js("""
      const none = {git: {...GIT.git, remotes: [
        {name: 'backup', github: null, url_has_credentials: false}]}};
      const a = rig({git: none});
      await opened(a);
      await press(a, 'accept:push:desk.accept.push.terms');
      const empty = {sent: a.sent.length, buttons: live(a.host.detail),
        says: hasText(a.host.detail, said('en', 'desk.accept.push.no_remote'))};
      const b = rig({gitFails: true});
      await opened(b);
      await press(b, 'accept:push:desk.accept.push.terms');
      const failed = {sent: b.sent.length, buttons: live(b.host.detail),
        says: hasText(b.host.detail, said('en', 'desk.accept.push.remotes_failed'))};
      console.log(JSON.stringify({empty, failed}));
    """)
    again = [PREFIX + "push.terms"]
    assert out == {"empty": {"sent": 0, "buttons": again, "says": True},
                   "failed": {"sent": 0, "buttons": again, "says": True}}


def test_terms_that_do_not_name_the_accepted_commit_branch_and_remote_are_not_shown():
    out = _js("""
      const wrong = [{...TERMS, commit: 'e'.repeat(40)}, {...TERMS, ref: 'refs/heads/other'},
        {...TERMS, remote: 'upstream'}, {...TERMS, push_digest: 'sha256:xyz'}];
      const result = [];
      for (const terms of wrong) {
        const r = rig({push: [ok('push_terms', terms)]});
        await opened(r);
        await press(r, 'accept:push:desk.accept.push.terms');
        result.push({buttons: live(r.host.detail), shown: hasText(r.host.detail, terms.command)});
      }
      console.log(JSON.stringify(result));
    """)
    assert out == [{"buttons": [PREFIX + "push.terms"], "shown": False}] * 4


def test_the_pull_request_step_shows_only_after_the_push_record_and_sends_what_the_owner_edited():
    out = _js("""
      const early = rig();
      await opened(early);
      const noPull = keysOf(early.host.detail).filter((key) => key.startsWith('accept:pr:'));
      const r = rig({facts: {push: PUSHED}, pull: [ok('pull_request', PULL)]});
      await opened(r);
      const card = () => r.host.detail;
      const fields = {base: keyed(card(), 'desk.accept.pr.base').value,
        title: keyed(card(), 'desk.accept.pr.title').value,
        body: keyed(card(), 'desk.accept.pr.body').value};
      const typed = (key, value) => { const node = keyed(card(), key); node.value = value;
        node.listeners.input(); shown(r); };
      typed('desk.accept.pr.base', 'trunk');
      typed('desk.accept.pr.title', 'My title');
      typed('desk.accept.pr.body', 'Line one\\nLine two');
      const box = keyed(card(), 'desk.accept.pr.draft'); box.checked = true;
      box.listeners.change(); shown(r);
      const command = Array.from(function* walk(n) { if (n.tag === 'pre') yield n.textContent;
        for (const c of n.children || []) yield* walk(c); }(card()))[0];
      await press(r, 'accept:pr:desk.accept.review');
      const confirm = {text: hasText(card(), said('en', 'desk.accept.pr.confirm_text', {
        repo: 'o/r', head: 'conduct/run-one', base: 'trunk', actor: 'Owner'})),
        buttons: live(card()), sent: r.sent.length};
      await press(r, 'accept:pr:desk.accept.pr.action');
      const links = [];
      const walk = (n) => { if (n.tag === 'a') links.push({href: n.href, rel: n.rel,
        target: n.target, text: n.textContent}); (n.children || []).forEach(walk); };
      walk(card());
      console.log(JSON.stringify({noPull, fields, command, confirm, sent: r.sent, links,
        number: hasText(card(), '#7'), merge: hasText(card(), said('en', 'desk.accept.pr.merge')),
        buttons: live(card())}));
    """)
    assert out["noPull"] == []
    assert out["fields"] == {
        "base": "main", "title": "Accepted result of run run-one",
        "body": ("Run: run-one\nAccepted by: Owner\nBranch: conduct/run-one\n"
                 "Commit: " + "c" * 40 + "\nFiles: 3")}
    assert out["command"] == ("gh pr create --repo o/r --base trunk --head conduct/run-one "
                              "--title 'My title' --body-file - --draft")
    assert out["confirm"]["text"] and out["confirm"]["sent"] == 0
    assert out["confirm"]["buttons"] == [PR_PREFIX + "pr.action", PR_PREFIX + "pr.back"]
    assert out["sent"] == [{"target": "acceptPullRequest", "run": "run-one", "body": {
        "acceptance_id": "acc-" + "a" * 32, "base": "trunk", "title": "My title",
        "body": "Line one\nLine two", "draft": True, "actor": "Owner"}}]
    assert out["links"] == [{"href": "https://github.com/o/r/pull/7", "rel": "noopener noreferrer",
                             "target": "_blank", "text": "https://github.com/o/r/pull/7"}]
    assert out["number"] and out["merge"] and out["buttons"] == []


def test_an_unknown_pull_request_answer_leaves_only_check_again_and_the_check_never_creates():
    out = _js("""
      const r = rig({facts: {push: PUSHED}, pull: [unknown, ok('pull_request', null),
        ok('pull_request', PULL)]});
      await opened(r);
      await press(r, 'accept:pr:desk.accept.review');
      await press(r, 'accept:pr:desk.accept.pr.action');
      const unknownStage = {buttons: live(r.host.detail),
        says: hasText(r.host.detail, said('en', 'desk.accept.pr.unknown')),
        locked: keyed(r.host.detail, 'desk.accept.pr.title').disabled};
      for (let turn = 0; turn < 3; turn += 1) { await tick(); shown(r); }
      const quiet = r.sent.length;
      await press(r, 'accept:pr:desk.accept.check');
      const absent = {buttons: live(r.host.detail),
        says: hasText(r.host.detail, said('en', 'desk.accept.pr.absent')),
        locked: keyed(r.host.detail, 'desk.accept.pr.title').disabled};
      await press(r, 'accept:pr:desk.accept.pr.again');
      console.log(JSON.stringify({kinds: kinds(r), bodies: r.sent.map(({body}) => body),
        unknownStage, quiet, absent, number: hasText(r.host.detail, '#7')}));
    """)
    assert out["kinds"] == ["send", "check", "send"]
    assert out["unknownStage"] == {"buttons": [PR_PREFIX + "check"], "says": True, "locked": True}
    assert out["quiet"] == 1
    assert out["absent"] == {"buttons": [PR_PREFIX + "pr.again"], "says": True, "locked": False}
    first, checked, again = out["bodies"]
    assert checked == {**first, "check": True} and again == first and out["number"]


@pytest.mark.parametrize("field", ["base", "title", "body", "draft"])
def test_an_edit_while_the_pull_request_is_absent_sends_nothing_and_asks_for_the_review_again(
        field):
    out = _js("""
      const r = rig({facts: {push: PUSHED}, pull: [unknown, ok('pull_request', null),
        ok('pull_request', PULL)]});
      await opened(r);
      for (const key of ['review', 'pr.action', 'check']) {
        await press(r, 'accept:pr:desk.accept.' + key);
      }
      const absent = live(r.host.detail);
      const values = {base: 'trunk', title: 'New title', body: 'New body', draft: true};
      if (d === 'draft') { const box = keyed(r.host.detail, 'desk.accept.pr.draft');
        box.checked = true; box.listeners.change(); }
      else { const node = keyed(r.host.detail, 'desk.accept.pr.' + d);
        node.value = values[d]; node.listeners.input(); }
      shown(r);
      const edited = {buttons: live(r.host.detail), sent: r.sent.length,
        says: hasText(r.host.detail, said('en', 'desk.accept.pr.absent'))};
      await pressIf(r, 'accept:pr:desk.accept.review');
      const confirm = {text: hasText(r.host.detail, said('en', 'desk.accept.pr.confirm_text', {
        repo: 'o/r', head: 'conduct/run-one', base: d === 'base' ? 'trunk' : 'main',
        actor: 'Owner'})), buttons: live(r.host.detail), sent: r.sent.length};
      await pressIf(r, 'accept:pr:desk.accept.pr.action');
      console.log(JSON.stringify({absent, edited, confirm, kinds: kinds(r),
        bodies: r.sent.map(({body}) => body), value: values[d]}));
    """, field)
    assert out["absent"] == [PR_PREFIX + "pr.again"]
    assert out["edited"] == {"buttons": [PR_PREFIX + "review"], "sent": 2, "says": False}
    assert out["confirm"] == {"text": True, "sent": 2,
                              "buttons": [PR_PREFIX + "pr.action", PR_PREFIX + "pr.back"]}
    assert out["kinds"] == ["send", "check", "send"]
    first, _checked, edited = out["bodies"]
    assert edited == {**first, field: out["value"]}


def test_a_changed_actor_returns_an_absent_push_to_review_and_the_press_names_the_new_one():
    out = _js("""
      const r = rig({push: [ok('push_terms', TERMS), refused('push_timed_out'),
        ok('push', PUSHED)]});
      await opened(r);
      for (const key of d) await press(r, key);
      const absent = {buttons: live(r.host.detail), terms: hasText(r.host.detail, TERMS.command)};
      signer = 'Other'; shown(r);
      const moved = {buttons: live(r.host.detail), terms: hasText(r.host.detail, TERMS.command),
        sent: r.sent.length};
      await pressIf(r, 'accept:push:desk.accept.review');
      const confirm = {text: hasText(r.host.detail, said('en', 'desk.accept.push.confirm_text', {
        commit: OID.slice(0, 7), repo: 'o/r', ref: REF, digest: TERMS.push_digest,
        actor: 'Other'})), buttons: live(r.host.detail), sent: r.sent.length};
      await pressIf(r, 'accept:push:desk.accept.push.action');
      console.log(JSON.stringify({absent, moved, confirm, last: r.sent.at(-1).body}));
    """, list(PUSH_CLICK))
    assert out["absent"] == {"buttons": [PREFIX + "push.again"], "terms": True}
    assert out["moved"] == {"buttons": [PREFIX + "review"], "terms": True, "sent": 2}
    assert out["confirm"] == {"text": True, "sent": 2,
                              "buttons": [PREFIX + "push.action", PREFIX + "push.back"]}
    assert out["last"]["actor"] == "Other" and "check" not in out["last"]


def test_a_changed_actor_returns_an_absent_pull_request_to_review_and_names_the_new_one():
    out = _js("""
      const r = rig({facts: {push: PUSHED}, pull: [unknown, ok('pull_request', null),
        ok('pull_request', PULL)]});
      await opened(r);
      for (const key of ['review', 'pr.action', 'check']) {
        await press(r, 'accept:pr:desk.accept.' + key);
      }
      const absent = live(r.host.detail);
      signer = 'Other'; shown(r);
      const moved = {buttons: live(r.host.detail), sent: r.sent.length,
        says: hasText(r.host.detail, said('en', 'desk.accept.pr.absent'))};
      await pressIf(r, 'accept:pr:desk.accept.review');
      const confirm = {text: hasText(r.host.detail, said('en', 'desk.accept.pr.confirm_text', {
        repo: 'o/r', head: 'conduct/run-one', base: 'main', actor: 'Other'})),
        buttons: live(r.host.detail), sent: r.sent.length};
      await pressIf(r, 'accept:pr:desk.accept.pr.action');
      console.log(JSON.stringify({absent, moved, confirm, last: r.sent.at(-1).body}));
    """)
    assert out["absent"] == [PR_PREFIX + "pr.again"]
    assert out["moved"] == {"buttons": [PR_PREFIX + "review"], "sent": 2, "says": False}
    assert out["confirm"] == {"text": True, "sent": 2,
                              "buttons": [PR_PREFIX + "pr.action", PR_PREFIX + "pr.back"]}
    assert out["last"]["actor"] == "Other" and "check" not in out["last"]


AFTER_PR_REFUSAL = {
    "pr_create_failed": ["check"], "push_auth_failed": ["check"],
    "gh_not_logged_in": ["review"], "pr_requires_push": ["review"],
}


def test_each_refusal_of_the_pull_request_is_said_and_leaves_exactly_the_right_next_press():
    out = _js("""
      const result = {};
      for (const reason of Object.keys(d)) {
        const r = rig({facts: {push: PUSHED}, pull: [refused(reason)]});
        await opened(r);
        await press(r, 'accept:pr:desk.accept.review');
        await press(r, 'accept:pr:desk.accept.pr.action');
        result[reason] = {buttons: live(r.host.detail),
          says: hasText(r.host.detail, said('en', 'accept.reason.' + reason)),
          login: hasText(r.host.detail, 'gh auth login --hostname github.com --web')};
      }
      console.log(JSON.stringify(result));
    """, AFTER_PR_REFUSAL)
    for reason, offered in AFTER_PR_REFUSAL.items():
        assert out[reason] == {
            "buttons": ["accept:pr:desk.accept." + name for name in offered], "says": True,
            "login": reason == "gh_not_logged_in"}, reason


#: Spec 9.7: the check before the creation narrows the window and cannot close it, and the desk
#: does not present it as closed. What the owner reads must not promise "none on a moved branch".
PROMISES = {"en": ("none is", "only for the same commit", "none was created"),
            "ru": ("не создаётся ни одного", "только для того же коммита", "не создан")}
MAY_BE_MADE = {"en": "may still be made", "ru": "всё равно может быть создан"}


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_the_pull_request_card_never_promises_that_a_moved_branch_makes_no_pull_request(locale):
    out = _js("""
      const r = rig({locale: d, facts: {push: PUSHED}});
      await opened(r);
      const effect = said(d, 'desk.accept.pr.effect');
      const effectShown = hasText(r.host.detail, effect);
      await press(r, 'accept:pr:desk.accept.review');
      const confirm = said(d, 'desk.accept.pr.confirm_text',
        {repo: 'o/r', head: 'conduct/run-one', base: 'main', actor: 'Owner'});
      console.log(JSON.stringify({effect, effectShown, confirm,
        confirmShown: hasText(r.host.detail, confirm)}));
    """, locale)
    assert out["effectShown"] and out["confirmShown"], "the card draws exactly these two texts"
    for shown in (out["effect"], out["confirm"]):
        for promise in PROMISES[locale]:
            assert promise not in shown.lower(), (promise, shown)
    assert MAY_BE_MADE[locale] in out["confirm"]


#: A refusal of a press that may create names that press: "this press made none" is true, since
#: the server refuses before it calls gh, and it says nothing about an earlier press.
THIS_PRESS = {"en": "This press made", "ru": "Это нажатие"}
#: What a refusal that answers a press that only looks must not say: what was or was not made.
NOT_ABOUT_MAKING = {"en": ("created", "made", "none was"), "ru": ("создан", "создал", "нажатие")}
WORDS = ("remote_head_moved", "other_head", "other_base", "cross_repository")


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_a_mismatch_is_said_by_its_own_word_in_the_owners_language_and_creates_nothing(locale):
    out = _js("""
      const result = {};
      for (const word of ['remote_head_moved', 'other_head', 'other_base', 'cross_repository']) {
        const r = rig({locale: d, facts: {push: PUSHED},
          pull: [refused('pr_mismatch', {mismatch: word})]});
        await opened(r);
        await press(r, 'accept:pr:desk.accept.review');
        await press(r, 'accept:pr:desk.accept.pr.action');
        result[word] = {says: hasText(r.host.detail,
          said(d, 'desk.accept.pr.mismatch.' + word)), buttons: live(r.host.detail),
          generic: hasText(r.host.detail, said(d, 'accept.reason.pr_mismatch')),
          text: said(d, 'desk.accept.pr.mismatch.' + word)};
      }
      console.log(JSON.stringify(result));
    """, locale)
    texts = {word: row.pop("text") for word, row in out.items()}
    review = ["accept:pr:desk.accept.review"]
    assert out == {word: {"says": True, "buttons": review, "generic": False} for word in WORDS}
    for word, text in texts.items():
        assert THIS_PRESS[locale] in text, (word, text)


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_a_mismatch_that_answers_a_check_says_what_is_there_and_not_what_was_made(locale):
    out = _js("""
      const sayOr = (key) => { try { return said(d, key); } catch (_failure) { return null; } };
      const result = {};
      for (const word of ['remote_head_moved', 'other_head', 'other_base', 'cross_repository']) {
        const r = rig({locale: d, facts: {push: PUSHED},
          pull: [unknown, refused('pr_mismatch', {mismatch: word})]});
        await opened(r);
        for (const key of ['review', 'pr.action', 'check']) {
          await press(r, 'accept:pr:desk.accept.' + key);
        }
        result[word] = {texts: statuses(r.host.detail), kinds: kinds(r),
          expected: sayOr('desk.accept.pr.checked.' + word), buttons: live(r.host.detail)};
      }
      console.log(JSON.stringify(result));
    """, locale)
    for word, row in out.items():
        assert row["kinds"] == ["send", "check"], word
        assert row["expected"] is not None, f"no copy for a check that met {word}"
        assert row["texts"] == [row["expected"]], word
        assert row["buttons"] == ["accept:pr:desk.accept.review"], word
        for claim in NOT_ABOUT_MAKING[locale]:
            assert claim not in row["expected"].lower(), (word, claim, row["expected"])


def test_a_check_that_finds_the_pull_request_of_a_moved_branch_shows_it_with_what_it_points_to():
    out = _js("""
      const moved = {...PULL, mismatch: {head_oid: 'f'.repeat(40), base: 'main',
        cross_repository: false}};
      const r = rig({facts: {push: PUSHED}, pull: [unknown, ok('pull_request', moved)]});
      await opened(r);
      for (const key of ['review', 'pr.action', 'check']) {
        await press(r, 'accept:pr:desk.accept.' + key);
      }
      console.log(JSON.stringify({kinds: kinds(r),
        says: hasText(r.host.detail, said('en', 'desk.accept.pr.moved', {oid: 'f'.repeat(40)})),
        number: hasText(r.host.detail, '#7'), buttons: live(r.host.detail)}));
    """)
    assert out == {"kinds": ["send", "check"], "says": True, "number": True, "buttons": []}


def test_a_pull_request_made_for_a_moved_branch_is_shown_with_what_it_points_to_and_its_link():
    out = _js("""
      const moved = {...PULL, mismatch: {head_oid: 'f'.repeat(40), base: 'main',
        cross_repository: false}};
      const r = rig({facts: {push: PUSHED, pull_request: moved}});
      await opened(r);
      console.log(JSON.stringify({
        says: hasText(r.host.detail, said('en', 'desk.accept.pr.moved', {oid: 'f'.repeat(40)})),
        number: hasText(r.host.detail, '#7'), buttons: live(r.host.detail)}));
    """)
    assert out == {"says": True, "number": True, "buttons": []}


def test_a_link_that_is_not_a_pull_request_of_github_is_text_and_never_a_link():
    out = _js("""
      const odd = {...PULL, url: 'javascript:alert(1)'};
      const r = rig({facts: {push: PUSHED, pull_request: odd}});
      await opened(r);
      const links = [];
      const walk = (n) => { if (n.tag === 'a') links.push(n.href);
        (n.children || []).forEach(walk); };
      walk(r.host.detail);
      console.log(JSON.stringify({links, text: hasText(r.host.detail, 'javascript:alert(1)')}));
    """)
    assert out == {"links": [], "text": True}


def test_the_compact_card_tells_the_standing_records_and_leaves_the_steps_to_the_details():
    out = _js("""
      const draw = (r) => { r.host.render(desk('task-one', 'run-one'), false);
        return r.host.pult; };
      const none = rig();
      none.host.render(desk('task-one', 'run-one'), false); await tick();
      const afterCommit = live(draw(none));
      const pushed = rig({facts: {push: PUSHED}});
      pushed.host.render(desk('task-one', 'run-one'), false); await tick();
      const pult = draw(pushed);
      const sent = {text: hasText(pult, 'Sent to GitHub'), buttons: live(pult)};
      const done = rig({facts: {push: PUSHED, pull_request: PULL}});
      done.host.render(desk('task-one', 'run-one'), false); await tick();
      const finished = draw(done);
      console.log(JSON.stringify({afterCommit, sent, pr: hasText(finished, '#7'),
        buttons: live(finished),
        writes: none.sent.length + pushed.sent.length + done.sent.length}));
    """)
    assert out == {"afterCommit": ["accept:pult:desk.accept.open"],
                   "sent": {"text": True, "buttons": ["accept:pult:desk.accept.open"]},
                   "pr": True, "buttons": [], "writes": 0}


def test_while_the_run_is_read_again_the_steps_are_off_and_a_press_on_them_sends_nothing():
    out = _js("""
      const r = rig({push: [ok('push_terms', TERMS), ok('push', PUSHED)]});
      await opened(r);
      await press(r, 'accept:push:desk.accept.push.terms');
      reread(r.host);
      const during = {live: live(r.host.detail), all: keysOf(r.host.detail)};
      ready(r.host);
      await press(r, 'accept:push:desk.accept.review');
      reread(r.host);
      const confirming = {live: live(r.host.detail), all: keysOf(r.host.detail)};
      keyed(r.host.detail, 'accept:push:desk.accept.push.action').listeners.click(); await tick();
      const whileStale = r.sent.length;
      ready(r.host);
      await press(r, 'accept:push:desk.accept.push.action');
      console.log(JSON.stringify({during, confirming, whileStale, sent: r.sent.length}));
    """)
    assert out["during"] == {"live": [], "all": [PREFIX + "review"]}
    assert out["confirming"] == {"live": [PREFIX + "push.back"],
                                 "all": [PREFIX + "push.action", PREFIX + "push.back"]}
    assert out["whileStale"] == 1 and out["sent"] == 2


def test_an_answer_that_lands_while_the_run_is_read_again_is_kept_and_usable_once_it_is_over():
    out = _js("""
      let release;
      const held = new Promise((resolve) => { release = resolve; });
      const door = {readJson: async (target) => target === '/command/project/git' ? GIT : base(),
        submit: async () => { await held; return ok('push_terms', TERMS); }};
      const host = acceptHost.createAcceptHost({door, binding: () => chosen, locale: () => 'en',
        onChange: () => {}, onForeign: () => {}});
      ready(host); await tick(); ready(host);
      keyed(host.detail, 'accept:push:desk.accept.push.terms').listeners.click(); await tick();
      reread(host);
      release(); await tick();
      reread(host);
      const during = {digest: hasText(host.detail, TERMS.push_digest),
        review: keyed(host.detail, 'accept:push:desk.accept.review')?.disabled};
      ready(host);
      console.log(JSON.stringify({during,
        review: keyed(host.detail, 'accept:push:desk.accept.review')?.disabled}));
    """)
    assert out == {"during": {"digest": True, "review": True}, "review": False}


def test_an_answer_for_the_run_that_was_left_changes_nothing_on_the_new_one():
    out = _js("""
      let release;
      const held = new Promise((resolve) => { release = resolve; });
      const host = acceptHost.createAcceptHost({door: {readJson: async (target) =>
        target === '/command/project/git' ? GIT : base(),
        submit: async () => { await held; return ok('push_terms', TERMS); }},
        binding: () => chosen, locale: () => 'en', onChange: () => {}, onForeign: () => {}});
      const draw = (task, run) => host.render(desk(task, run), true);
      draw('task-one', 'run-one'); await tick(); draw('task-one', 'run-one');
      keyed(host.detail, 'accept:push:desk.accept.push.terms').listeners.click(); await tick();
      chosen = {...chosen, taskId: 'task-two', runId: 'run-two'};
      draw('task-two', 'run-two'); await tick(); draw('task-two', 'run-two');
      release(); await tick(); draw('task-two', 'run-two');
      console.log(JSON.stringify({terms: hasText(host.detail, TERMS.push_digest),
        buttons: live(host.detail)}));
    """)
    assert out == {"terms": False, "buttons": [PREFIX + "push.terms"]}


def test_a_project_open_for_viewing_cannot_send_or_open_anything():
    out = _js("""
      chosen = {...chosen, mode: 'view'};
      const r = rig({facts: {push: PUSHED}});
      shown(r, 'view'); await tick(); shown(r, 'view');
      console.log(JSON.stringify({live: live(r.host.detail), all: keysOf(r.host.detail),
        says: hasText(r.host.detail, said('en', 'desk.run.view_blocked'))}));
    """)
    assert out["live"] == [] and out["says"]
    assert PR_PREFIX + "review" in out["all"]


def test_the_steps_speak_russian_when_the_owner_does():
    out = _js("""
      const r = rig({locale: 'ru', push: [ok('push_terms', TERMS)]});
      await opened(r);
      const heading = hasText(r.host.detail, 'Отправить на GitHub');
      await press(r, 'accept:push:desk.accept.push.terms');
      console.log(JSON.stringify({heading, command: hasText(r.host.detail, 'Точная команда'),
        english: hasText(r.host.detail, 'Send to GitHub')}));
    """)
    assert out == {"heading": True, "command": True, "english": False}
