"""A remote that is not GitHub gets a terminal command from the card, and no step (spec 9.7).

Steps 2 and 3 of the accept card, the push and the pull request, are the desk's only for a
GitHub project. For a remote that is not GitHub's the card shows the command to run in a terminal,
`git push <remote> <branch>`, and nothing it can press. The card learns the remotes once, after
the commit record is known, from the project's Git facts; until they land it asks nothing and
offers nothing, and when they cannot be read it keeps the push step, whose own press reads them
again. The real host runs under Node with a fake door, as in `test_desk_accept_publish.py`.
"""
from __future__ import annotations

from tests.test_desk_accept_publish import _js

PUSH_TERMS = "accept:push:desk.accept.push.terms"
#: A remote row as `GET /command/project/git` gives it, and the project's facts around a list.
ROWS = """
const row = (name, github = null) => ({name, github, url_has_credentials: false});
const gitOf = (...remotes) => ({git: {...GIT.git, remotes}});
const card = (r) => r.host.detail;
const gone = (r, locale = 'en') => ({
  github: hasText(card(r), said(locale, 'desk.accept.push.heading')),
  pr: hasText(card(r), said(locale, 'desk.accept.pr.heading'))});
"""


def _rows(body: str, data=None):
    return _js(ROWS + body, data)


def test_a_project_whose_only_remote_is_not_github_shows_the_command_and_no_step():
    out = _rows("""
      const r = rig({git: gitOf(row('gitlab'))});
      await opened(r);
      console.log(JSON.stringify({buttons: live(card(r)), sent: r.sent.length, reads: r.reads,
        heading: hasText(card(r), said('en', 'desk.accept.terminal.heading')),
        effect: hasText(card(r), said('en', 'desk.accept.terminal.effect')),
        remote: hasText(card(r), 'gitlab'),
        command: hasText(card(r), 'git push gitlab conduct/run-one'), ...gone(r)}));
    """)
    assert out == {"buttons": [], "sent": 0, "reads": ["/command/runs/run-one/accept",
                                                       "/command/project/git"],
                   "heading": True, "effect": True, "remote": True, "command": True,
                   "github": False, "pr": False}


def test_the_terminal_command_and_its_words_are_the_same_in_russian_and_english():
    out = _rows("""
      const result = {};
      for (const locale of ['en', 'ru']) {
        const r = rig({locale, git: gitOf(row('gitlab'))});
        await opened(r);
        result[locale] = {heading: said(locale, 'desk.accept.terminal.heading'),
          shown: hasText(card(r), said(locale, 'desk.accept.terminal.heading')),
          effect: hasText(card(r), said(locale, 'desk.accept.terminal.effect')),
          command: hasText(card(r), 'git push gitlab conduct/run-one')};
      }
      console.log(JSON.stringify(result));
    """)
    assert out["en"].pop("heading") != out["ru"].pop("heading")
    assert out == {"en": {"shown": True, "effect": True, "command": True},
                   "ru": {"shown": True, "effect": True, "command": True}}


def test_each_remote_that_is_not_github_gets_its_own_command_and_a_github_one_gets_none():
    out = _rows("""
      const r = rig({git: gitOf(row('backup'), row('origin', 'o/r'), row('mirror'))});
      await opened(r);
      console.log(JSON.stringify({backup: hasText(card(r), 'git push backup conduct/run-one'),
        mirror: hasText(card(r), 'git push mirror conduct/run-one'),
        origin: hasText(card(r), 'git push origin'), buttons: live(card(r)),
        ...gone(r)}));
    """)
    assert out == {"backup": True, "mirror": True, "origin": False, "buttons": [PUSH_TERMS],
                   "github": True, "pr": False}


def test_a_branch_with_a_quote_is_quoted_and_a_remote_named_like_a_flag_is_left_out():
    out = _rows("""
      const odd = {commit: {...COMMIT, branch: "conduct/it's"}};
      const r = rig({facts: odd, git: gitOf(row('gitlab'), row('-f'), row('--mirror'))});
      await opened(r);
      const pres = [];
      const walk = (node) => { if (node.tag === 'pre') pres.push(node.textContent);
        for (const child of node.children || []) walk(child); };
      walk(card(r));
      console.log(JSON.stringify({shown: pres, flag: hasText(card(r), 'git push -f'),
        mirror: hasText(card(r), 'mirror')}));
    """)
    assert out == {"shown": ["git push gitlab 'conduct/it'\\''s'"], "flag": False,
                   "mirror": False}


def test_a_project_with_no_remote_says_there_is_nothing_to_send_to_and_shows_no_command():
    out = _rows("""
      const r = rig({git: gitOf()});
      await opened(r);
      console.log(JSON.stringify({buttons: live(card(r)), sent: r.sent.length,
        says: hasText(card(r), said('en', 'desk.accept.push.no_remote')),
        command: hasText(card(r), 'git push'), ...gone(r)}));
    """)
    assert out == {"buttons": [], "sent": 0, "says": True, "command": False, "github": False,
                   "pr": False}


def test_remotes_that_cannot_be_read_leave_the_push_step_and_show_no_command():
    out = _rows("""
      const result = {};
      const junk = {note: 'not the shape of the project facts'};
      for (const [name, over] of [['fails', {gitFails: true}], ['junk', {git: junk}]]) {
        const r = rig(over);
        await opened(r);
        result[name] = {buttons: live(card(r)), command: hasText(card(r), 'git push'),
          heading: hasText(card(r), said('en', 'desk.accept.push.heading'))};
      }
      console.log(JSON.stringify(result));
    """)
    shown = {"buttons": [PUSH_TERMS], "command": False, "heading": True}
    assert out == {"fails": shown, "junk": shown}


def test_while_the_remotes_are_being_read_the_card_offers_neither_a_step_nor_a_command():
    out = _rows("""
      let release;
      const r = rig({git: gitOf(row('gitlab'))});
      const slow = r.door.readJson;
      r.door.readJson = (target) => target === '/command/project/git'
        ? new Promise((done) => { release = () => done(gitOf(row('gitlab'))); }) : slow(target);
      await opened(r);
      const waiting = {buttons: live(card(r)), command: hasText(card(r), 'git push'),
        says: hasText(card(r), said('en', 'desk.accept.working')), ...gone(r)};
      release(); await tick(); shown(r);
      console.log(JSON.stringify({waiting, command: hasText(card(r), 'git push gitlab'),
        says: hasText(card(r), said('en', 'desk.accept.working'))}));
    """)
    assert out == {"waiting": {"buttons": [], "command": False, "says": True,
                               "github": False, "pr": False},
                   "command": True, "says": False}


def test_a_commit_made_by_this_card_makes_it_read_the_remotes_and_show_the_command():
    out = _rows("""
      const reads = [], sent = [];
      const door = {readJson: async (target) => { reads.push(target);
          return target === '/command/project/git' ? gitOf(row('gitlab'))
            : {kind: 'files', basis: {}, commit: null, push: null, pull_request: null}; },
        submit: async (target) => { sent.push(target);
          return target === 'acceptPreview' ? {status: 'accepted', payload: {accept: preview}}
            : {status: 'accepted', payload: {commit: COMMIT}}; }};
      const host = acceptHost.createAcceptHost({door, binding: () => chosen, locale: () => 'en',
        onChange: () => {}, onForeign: () => {}});
      const draw = () => host.render({...desk('task-one', 'run-one'), actor: 'Owner'}, true);
      draw(); await tick(); draw();
      const before = {reads: [...reads], command: hasText(host.detail, 'git push')};
      keyed(host.detail, 'accept:detail:desk.accept.preview').listeners.click();
      await tick(); draw();
      keyed(host.detail, 'accept:detail:desk.accept.review').listeners.click(); draw();
      keyed(host.detail, 'accept:detail:desk.accept.commit_action').listeners.click();
      await tick(); draw(); await tick(); draw();
      console.log(JSON.stringify({before, sent, reads,
        command: hasText(host.detail, 'git push gitlab conduct/run-one')}));
    """)
    assert out["before"] == {"reads": ["/command/runs/run-one/accept"], "command": False}
    assert out["sent"] == ["acceptPreview", "acceptCommit"]
    assert out["reads"] == ["/command/runs/run-one/accept", "/command/project/git"]
    assert out["command"]


def test_a_card_whose_commit_was_already_sent_to_github_reads_no_remotes_and_shows_no_command():
    out = _rows("""
      const r = rig({facts: {push: PUSHED}, git: gitOf(row('gitlab'))});
      await opened(r);
      console.log(JSON.stringify({reads: r.reads, command: hasText(card(r), 'git push'),
        sent: hasText(card(r), 'Sent to GitHub'), pr: hasText(card(r), 'Pull request')}));
    """)
    assert out == {"reads": ["/command/runs/run-one/accept"], "command": False, "sent": True,
                   "pr": True}


def test_the_terminal_words_own_that_a_push_by_remote_name_writes_the_remote_tracking_branch():
    """The unguarded command of a remote that is not GitHub's writes a local ref, and the card
    says so in both languages; it promises neither an untouched repository nor that the desk
    records anything about the push."""
    out = _rows("""
      console.log(JSON.stringify({en: said('en', 'desk.accept.terminal.effect'),
        ru: said('ru', 'desk.accept.terminal.effect')}));
    """)
    assert "also writes the remote-tracking branch of that remote" in out["en"]
    assert "и remote-tracking ветку этого remote" in out["ru"]
    assert "runs nothing and records nothing" in out["en"]
    assert "ничего не запускает и ничего не записывает" in out["ru"]
    for promise in ("no local", "untouched", "changes nothing", "не меняет", "без изменений"):
        assert promise not in out["en"].lower() and promise not in out["ru"].lower(), promise
