"""Whom "send again" and "create again" are pressed for, and with which fields (spec 9.7).

Both presses repeat an outside action after a look found it absent, so both may repeat only what
one named person confirmed on the card: their terms, their fields, their name. The press that
first made the step "absent" can come after the person at the desk changed (while the answer was
awaited, or between an unknown answer and its check) or after the language changed. In each case
the card must go back to its review instead of offering the repeat. The real host runs under
Node with a fake door, as in `test_desk_accept_publish.py`.

A check is not such a press: it acts on nothing outside and looks for the press that was
confirmed, so it carries that press's signer whoever presses it, and a record it writes names
that person (the owner's decision R4-V1, 21 October 2026).
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
    assert out["actors"] == ["Owner", "Owner", "Other"]


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
    assert out["actors"] == [None, "Owner", "Owner", "Other"]


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


def test_a_check_pressed_by_another_person_names_the_signer_of_the_push_it_looks_for():
    out = _js("""
      const r = rig({push: [ok('push_terms', TERMS), refused('push_unconfirmed'), unknown,
        ok('push', PUSHED)]});
      await opened(r);
      for (const key of d) await press(r, key);
      signer = 'Other'; shown(r);
      const otherAtDesk = live(r.host.detail);
      await press(r, 'accept:push:desk.accept.check');
      const stillUnknown = live(r.host.detail);
      await press(r, 'accept:push:desk.accept.check');
      console.log(JSON.stringify({otherAtDesk, stillUnknown, kinds: kinds(r),
        bodies: r.sent.map(({body}) => body), sent: hasText(r.host.detail, 'Sent to GitHub'),
        after: live(r.host.detail)}));
    """, list(PUSH_CLICK))
    assert out["otherAtDesk"] == out["stillUnknown"] == [PREFIX + "check"]
    assert out["kinds"] == ["terms", "send", "check", "check"]
    first, checked, again = out["bodies"][1:]
    assert first["actor"] == "Owner"
    assert checked == again == {**first, "check": True}
    assert out["sent"] and out["after"] == [PR_PREFIX + "review"]


def test_a_check_pressed_by_another_person_names_the_signer_of_the_pull_request_it_looks_for():
    out = _js("""
      const r = rig({facts: {push: PUSHED}, pull: [unknown, unknown,
        ok('pull_request', PULL)]});
      await opened(r);
      for (const key of ['review', 'pr.action']) await press(r, 'accept:pr:desk.accept.' + key);
      signer = 'Other'; shown(r);
      const otherAtDesk = live(r.host.detail);
      await press(r, 'accept:pr:desk.accept.check');
      const stillUnknown = live(r.host.detail);
      await press(r, 'accept:pr:desk.accept.check');
      console.log(JSON.stringify({otherAtDesk, stillUnknown, kinds: kinds(r),
        bodies: r.sent.map(({body}) => body), number: hasText(r.host.detail, '#7'),
        after: live(r.host.detail)}));
    """)
    assert out["otherAtDesk"] == out["stillUnknown"] == [PR_PREFIX + "check"]
    assert out["kinds"] == ["send", "check", "check"]
    first, checked, again = out["bodies"]
    assert first["actor"] == "Owner"
    assert checked == again == {**first, "check": True}
    assert out["number"] and out["after"] == []


def test_every_check_names_the_signer_whoever_sits_at_the_desk_and_nobody_checks_alone():
    out = _js("""
      const r = rig({push: [ok('push_terms', TERMS), refused('push_unconfirmed'), unknown,
        unknown, ok('push', PUSHED)]});
      await opened(r);
      for (const key of d) await press(r, key);
      signer = 'Other'; shown(r);
      await press(r, 'accept:push:desk.accept.check');
      signer = null; shown(r);
      const nobody = live(r.host.detail);
      signer = 'Owner'; shown(r);
      await press(r, 'accept:push:desk.accept.check');
      signer = 'Third'; shown(r);
      await press(r, 'accept:push:desk.accept.check');
      console.log(JSON.stringify({nobody, actors: r.sent.map(({body}) => body.actor),
        kinds: kinds(r)}));
    """, list(PUSH_CLICK))
    assert out["nobody"] == []
    assert out["kinds"] == ["terms", "send", "check", "check", "check"]
    assert out["actors"] == [None, "Owner", "Owner", "Owner", "Owner"]


def test_a_check_after_send_again_names_the_signer_of_that_repeat_not_the_person_checking():
    out = _js("""
      const r = rig({push: [ok('push_terms', TERMS), refused('push_unconfirmed'),
        ok('push', null), refused('push_unconfirmed'), ok('push', PUSHED)]});
      await opened(r);
      for (const key of d) await press(r, key);
      await press(r, 'accept:push:desk.accept.check');
      const absent = live(r.host.detail);
      await press(r, 'accept:push:desk.accept.push.again');
      signer = 'Other'; shown(r);
      await press(r, 'accept:push:desk.accept.check');
      console.log(JSON.stringify({absent, kinds: kinds(r),
        actors: r.sent.map(({body}) => body.actor)}));
    """, list(PUSH_CLICK))
    assert out["absent"] == [PREFIX + "push.again"]
    assert out["kinds"] == ["terms", "send", "check", "send", "check"]
    assert out["actors"] == [None, "Owner", "Owner", "Owner", "Owner"]


def test_a_check_names_the_new_signer_when_another_person_confirmed_the_press_it_looks_for():
    out = _js("""
      const r = rig({push: [ok('push_terms', TERMS), refused('push_timed_out'),
        refused('push_unconfirmed'), ok('push', PUSHED)]});
      await opened(r);
      for (const key of d) await press(r, key);
      signer = 'Other'; shown(r);
      const review = live(r.host.detail);
      await press(r, d[1]); await press(r, d[2]);
      signer = 'Owner'; shown(r);
      await press(r, 'accept:push:desk.accept.check');
      console.log(JSON.stringify({review, kinds: kinds(r),
        actors: r.sent.map(({body}) => body.actor)}));
    """, list(PUSH_CLICK))
    assert out["review"] == [PREFIX + "review"]
    assert out["kinds"] == ["terms", "send", "send", "check"]
    assert out["actors"] == [None, "Owner", "Other", "Other"]


def test_a_final_refusal_to_a_check_goes_back_to_the_review_and_the_next_press_names_the_person():
    out = _js("""
      const r = rig({facts: {push: PUSHED}, pull: [unknown,
        refused('pr_mismatch', {mismatch: 'other_base'}), ok('pull_request', PULL)]});
      await opened(r);
      for (const key of ['review', 'pr.action']) await press(r, 'accept:pr:desk.accept.' + key);
      signer = 'Other'; shown(r);
      await press(r, 'accept:pr:desk.accept.check');
      const after = live(r.host.detail);
      await pressIf(r, 'accept:pr:desk.accept.review');
      await pressIf(r, 'accept:pr:desk.accept.pr.action');
      console.log(JSON.stringify({after, kinds: kinds(r),
        actors: r.sent.map(({body}) => body.actor)}));
    """)
    assert out["after"] == [PR_PREFIX + "review"]
    assert out["kinds"] == ["send", "check", "send"]
    assert out["actors"] == ["Owner", "Owner", "Other"]


def test_the_pull_request_that_follows_a_push_found_by_a_check_is_signed_by_the_person_now():
    out = _js("""
      const r = rig({push: [ok('push_terms', TERMS), refused('push_unconfirmed'),
        ok('push', PUSHED)], pull: [ok('pull_request', PULL)]});
      await opened(r);
      for (const key of d) await press(r, key);
      signer = 'Other'; shown(r);
      await press(r, 'accept:push:desk.accept.check');
      await press(r, 'accept:pr:desk.accept.review');
      await press(r, 'accept:pr:desk.accept.pr.action');
      console.log(JSON.stringify({sent: r.sent.map(({target, body}) =>
        [target, body.actor, !!body.check])}));
    """, list(PUSH_CLICK))
    assert out["sent"] == [["acceptPush", None, False], ["acceptPush", "Owner", False],
                           ["acceptPush", "Owner", True], ["acceptPullRequest", "Other", False]]


def test_a_standing_pull_request_naming_someone_else_is_still_the_record_the_check_asked_for():
    out = _js("""
      const theirs = {...PULL, requested_by: 'Other'};
      const r = rig({facts: {push: PUSHED}, pull: [unknown, ok('pull_request', theirs)]});
      await opened(r);
      for (const key of ['review', 'pr.action']) await press(r, 'accept:pr:desk.accept.' + key);
      await press(r, 'accept:pr:desk.accept.check');
      console.log(JSON.stringify({actors: r.sent.map(({body}) => body.actor),
        shown: r.host.detail && hasText(r.host.detail, '#7')}));
    """)
    assert out["actors"] == ["Owner", "Owner"]
    assert out["shown"] is True


def test_a_pr_check_names_the_pr_signer_even_when_another_person_signed_the_push():
    out = _js("""
      const r = rig({push: [ok('push_terms', TERMS), ok('push', PUSHED)],
        pull: [unknown, ok('pull_request', PULL)]});
      await opened(r);
      for (const key of d) await press(r, key);
      signer = 'Other'; shown(r);
      for (const key of ['review', 'pr.action']) await press(r, 'accept:pr:desk.accept.' + key);
      signer = 'Owner'; shown(r);
      await press(r, 'accept:pr:desk.accept.check');
      console.log(JSON.stringify({sent: r.sent.map(({target, body}) =>
        [target, body.actor, !!body.check])}));
    """, list(PUSH_CLICK))
    assert out["sent"] == [["acceptPush", None, False], ["acceptPush", "Owner", False],
                           ["acceptPullRequest", "Other", False],
                           ["acceptPullRequest", "Other", True]]


def test_a_check_after_a_change_of_language_still_carries_the_confirmed_fields_and_signer():
    out = _js("""
      const over = {facts: {push: PUSHED}, pull: [unknown, ok('pull_request', PULL)]};
      const r = rig(over);
      await opened(r);
      for (const key of ['review', 'pr.action']) await press(r, 'accept:pr:desk.accept.' + key);
      over.locale = 'ru'; signer = 'Other'; shown(r);
      await press(r, 'accept:pr:desk.accept.check');
      console.log(JSON.stringify({bodies: r.sent.map(({body}) => body)}));
    """)
    first, checked = out["bodies"]
    assert first["actor"] == "Owner" and checked == {**first, "check": True}
