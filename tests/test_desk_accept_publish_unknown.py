"""An answer that does not say whether the outside action happened is unknown (R4-O2, G8).

The card cannot tell a 500 `store_error`, a body that is not JSON or a `git_failed` that came
before the push from one that came after it: the server answers all of them alike. After a send or
a check of either step such an answer therefore leaves the step unknown, with only "Check again",
never "Send again" or "Create again". A check says "absent" only by its own `null`. What stays
absent after a send is what the server says when nothing landed: `git_timed_out`, which comes
before any push, and `push_timed_out`, which comes after a look that found no ref.
The real host runs under Node with a fake door, as in `test_desk_accept_publish.py`.
"""
from __future__ import annotations

import json

import pytest

from tests.test_desk_accept_publish import PR_PREFIX, PREFIX, PUSH_CLICK, _js

#: The answers that leave it open whether the outside action happened, by the name the parameter
#: `d` gives them in the script that is run (`git_timed_out` only after a check: after a send it
#: is said before the push), and the three presses that confirm the push.
ANSWERS = """
const AMBIGUOUS = {
  store_500: {status: 'refused', code: 'store_error',
    payload: {error: {code: 'store_error', message: 'interrupted'}}},
  unreadable: {status: 'refused', code: 'store_error', payload: null},
  git_failed: refused('git_failed'), git_timed_out: refused('git_timed_out'), lost: unknown};
const CLICK = %s;
""" % json.dumps(list(PUSH_CLICK))


@pytest.mark.parametrize("answer", ["store_500", "unreadable", "git_failed", "lost"])
def test_an_unclear_answer_to_the_push_leaves_only_check_and_the_check_carries_the_same_body(
        answer):
    out = _js(ANSWERS + """
      const r = rig({push: [ok('push_terms', TERMS), AMBIGUOUS[d], ok('push', PUSHED)]});
      await opened(r);
      for (const key of CLICK) await press(r, key);
      const unclear = {buttons: live(r.host.detail), command: hasText(r.host.detail, TERMS.command),
        says: hasText(r.host.detail, said('en', 'desk.accept.push.unknown'))};
      for (let turn = 0; turn < 3; turn += 1) { await tick(); shown(r); }
      const quiet = kinds(r);
      await pressIf(r, 'accept:push:desk.accept.check');
      console.log(JSON.stringify({unclear, quiet, kinds: kinds(r),
        bodies: r.sent.map(({body}) => body), actor: r.sent.at(-1).body.actor,
        done: hasText(r.host.detail, 'Sent to GitHub')}));
    """, answer)
    assert out["unclear"] == {"buttons": [PREFIX + "check"], "command": True, "says": True}
    assert out["quiet"] == ["terms", "send"]
    assert out["kinds"] == ["terms", "send", "check"] and out["kinds"].count("send") == 1
    first, checked = out["bodies"][1:]
    assert checked == {**first, "check": True} and out["actor"] == "Owner"
    assert out["done"]


@pytest.mark.parametrize("answer", ["store_500", "git_failed", "git_timed_out", "lost"])
def test_an_unclear_answer_to_the_push_check_keeps_check_and_never_offers_send_again(answer):
    out = _js(ANSWERS + """
      const r = rig({push: [ok('push_terms', TERMS), refused('push_unconfirmed'), AMBIGUOUS[d],
        ok('push', null)]});
      await opened(r);
      for (const key of CLICK) await press(r, key);
      await pressIf(r, 'accept:push:desk.accept.check');
      const afterFirst = {buttons: live(r.host.detail),
        says: hasText(r.host.detail, said('en', 'desk.accept.push.unknown')),
        absent: hasText(r.host.detail, said('en', 'desk.accept.push.absent'))};
      await pressIf(r, 'accept:push:desk.accept.check');
      console.log(JSON.stringify({afterFirst, afterSecond: live(r.host.detail),
        kinds: kinds(r)}));
    """, answer)
    assert out["afterFirst"] == {"buttons": [PREFIX + "check"], "says": True, "absent": False}
    assert out["afterSecond"] == [PREFIX + "push.again"]
    assert out["kinds"] == ["terms", "send", "check", "check"]


@pytest.mark.parametrize("answer", ["store_500", "git_failed"])
def test_an_unclear_answer_to_the_pull_request_or_its_check_leaves_only_check(answer):
    out = _js(ANSWERS + """
      const r = rig({facts: {push: PUSHED}, pull: [AMBIGUOUS[d], AMBIGUOUS[d],
        ok('pull_request', PULL)]});
      await opened(r);
      for (const key of ['review', 'pr.action']) await press(r, 'accept:pr:desk.accept.' + key);
      const stage = () => ({buttons: live(r.host.detail),
        says: hasText(r.host.detail, said('en', 'desk.accept.pr.unknown')),
        locked: keyed(r.host.detail, 'desk.accept.pr.base').disabled});
      const afterSend = stage();
      await pressIf(r, 'accept:pr:desk.accept.check');
      const afterCheck = stage();
      await pressIf(r, 'accept:pr:desk.accept.check');
      console.log(JSON.stringify({afterSend, afterCheck, kinds: kinds(r),
        url: hasText(r.host.detail, PULL.url), number: hasText(r.host.detail, '#7'),
        buttons: live(r.host.detail)}));
    """, answer)
    stage = {"buttons": [PR_PREFIX + "check"], "says": True, "locked": True}
    assert out["afterSend"] == out["afterCheck"] == stage
    assert out["kinds"] == ["send", "check", "check"]
    assert out["url"] and out["number"] and out["buttons"] == []
