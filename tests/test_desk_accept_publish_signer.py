"""Whom "send again" and "create again" are pressed for, and with which fields (spec 9.7).

Both presses repeat an outside action after a look found it absent, so both may repeat only what
one named person confirmed on the card: their terms, their fields, their name. The press that
first made the step "absent" can come after the person at the desk changed (while the answer was
awaited, or between an unknown answer and its check) or after the language changed. In each case
the card must go back to its review instead of offering the repeat. The real host runs under
Node with a fake door, as in `test_desk_accept_publish.py`.
"""
from __future__ import annotations

from tests.test_desk_accept_publish import PR_PREFIX, PREFIX, PUSH_CLICK, _js


def test_a_check_by_another_person_that_finds_no_pull_request_asks_for_the_review_again():
    out = _js("""
      const r = rig({facts: {push: PUSHED}, pull: [unknown, ok('pull_request', null),
        ok('pull_request', PULL)]});
      await opened(r);
      for (const key of ['review', 'pr.action']) await press(r, 'accept:pr:desk.accept.' + key);
      const unknownStage = live(r.host.detail);
      signer = 'Other'; shown(r);
      const otherAtDesk = live(r.host.detail);
      await press(r, 'accept:pr:desk.accept.check');
      const checked = {buttons: live(r.host.detail), sent: r.sent.length};
      await pressIf(r, 'accept:pr:desk.accept.pr.again');
      const pressedAgain = r.sent.length;
      await pressIf(r, 'accept:pr:desk.accept.review');
      const confirm = {text: hasText(r.host.detail, said('en', 'desk.accept.pr.confirm_text', {
        repo: 'o/r', head: 'conduct/run-one', base: 'main', actor: 'Other'})),
        buttons: live(r.host.detail), sent: r.sent.length};
      await pressIf(r, 'accept:pr:desk.accept.pr.action');
      console.log(JSON.stringify({unknownStage, otherAtDesk, checked, pressedAgain, confirm,
        kinds: kinds(r), actors: r.sent.map(({body}) => body.actor)}));
    """)
    assert out["unknownStage"] == out["otherAtDesk"] == [PR_PREFIX + "check"]
    assert out["checked"] == {"buttons": [PR_PREFIX + "review"], "sent": 2}
    assert out["pressedAgain"] == 2
    assert out["confirm"] == {"text": True, "sent": 2,
                              "buttons": [PR_PREFIX + "pr.action", PR_PREFIX + "pr.back"]}
    assert out["kinds"] == ["send", "check", "send"]
    assert out["actors"] == ["Owner", "Other", "Other"]


def test_a_push_that_timed_out_after_the_person_changed_asks_for_the_review_not_send_again():
    out = _js("""
      const r = rig({push: [ok('push_terms', TERMS), refused('push_timed_out'),
        ok('push', PUSHED)]});
      await opened(r);
      await press(r, d[0]); await press(r, d[1]);
      const awaited = r.door.submit;
      r.door.submit = async (target, run, body) => {
        const answer = await awaited(target, run, body);
        if (!body.preview) { signer = 'Other'; shown(r); }
        return answer; };
      await press(r, d[2]);
      const afterTimeout = {buttons: live(r.host.detail), sent: r.sent.length,
        terms: hasText(r.host.detail, TERMS.command)};
      await pressIf(r, 'accept:push:desk.accept.push.again');
      const pressedAgain = r.sent.length;
      await pressIf(r, d[1]);
      const confirm = {text: hasText(r.host.detail, said('en', 'desk.accept.push.confirm_text', {
        commit: OID.slice(0, 7), repo: 'o/r', ref: REF, digest: TERMS.push_digest,
        actor: 'Other'})), buttons: live(r.host.detail), sent: r.sent.length};
      await pressIf(r, d[2]);
      console.log(JSON.stringify({afterTimeout, pressedAgain, confirm, last: r.sent.at(-1).body}));
    """, list(PUSH_CLICK))
    assert out["afterTimeout"] == {"buttons": [PREFIX + "review"], "sent": 2, "terms": True}
    assert out["pressedAgain"] == 2
    assert out["confirm"] == {"text": True, "sent": 2,
                              "buttons": [PREFIX + "push.action", PREFIX + "push.back"]}
    assert out["last"]["actor"] == "Other" and "check" not in out["last"]


def test_a_check_by_another_person_that_finds_no_push_asks_for_the_review_again():
    out = _js("""
      const r = rig({push: [ok('push_terms', TERMS), refused('push_unconfirmed'),
        ok('push', null), ok('push', PUSHED)]});
      await opened(r);
      for (const key of d) await press(r, key);
      const unknownStage = live(r.host.detail);
      signer = 'Other'; shown(r);
      const otherAtDesk = live(r.host.detail);
      await press(r, 'accept:push:desk.accept.check');
      const checked = {buttons: live(r.host.detail), sent: r.sent.length};
      await pressIf(r, 'accept:push:desk.accept.push.again');
      const pressedAgain = r.sent.length;
      await pressIf(r, d[1]); await pressIf(r, d[2]);
      console.log(JSON.stringify({unknownStage, otherAtDesk, checked, pressedAgain,
        kinds: kinds(r), actors: r.sent.map(({body}) => body.actor)}));
    """, list(PUSH_CLICK))
    assert out["unknownStage"] == out["otherAtDesk"] == [PREFIX + "check"]
    assert out["checked"] == {"buttons": [PREFIX + "review"], "sent": 3}
    assert out["pressedAgain"] == 3
    assert out["kinds"] == ["terms", "send", "check", "send"]
    assert out["actors"] == [None, "Owner", "Other", "Other"]


def test_create_again_after_a_change_of_language_sends_the_fields_that_were_confirmed():
    out = _js("""
      const over = {facts: {push: PUSHED}, pull: [unknown, ok('pull_request', null),
        ok('pull_request', PULL)]};
      const r = rig(over);
      await opened(r);
      for (const key of ['review', 'pr.action', 'check']) {
        await press(r, 'accept:pr:desk.accept.' + key);
      }
      const absent = live(r.host.detail);
      over.locale = 'ru'; shown(r);
      const shownNow = {buttons: live(r.host.detail),
        title: keyed(r.host.detail, 'desk.accept.pr.title').value,
        body: keyed(r.host.detail, 'desk.accept.pr.body').value};
      await pressIf(r, 'accept:pr:desk.accept.pr.again');
      console.log(JSON.stringify({absent, shownNow, bodies: r.sent.map(({body}) => body),
        title: said('en', 'desk.accept.pr.default_title', {run: 'run-one'})}));
    """)
    assert out["absent"] == [PR_PREFIX + "pr.again"]
    first, checked, again = out["bodies"]
    assert first["title"] == out["title"] and checked == {**first, "check": True}
    assert again == first
    assert out["shownNow"] == {"buttons": [PR_PREFIX + "pr.again"], "title": first["title"],
                               "body": first["body"]}
