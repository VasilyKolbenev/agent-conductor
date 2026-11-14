"""The pure rules of connecting git and of the first commit: the shapes, the bodies, the commands.

`desk-wizard-git.js` imports nothing and keeps nothing, so every claim here is a plain value in and
a plain value out under Node. The answers are the stand-ins under `tests/fixtures/wizard/`; what a
press does with them is `tests/test_desk_wizard_git_run.py`, and what is drawn is the browser's.
"""
from __future__ import annotations

from typing import Any

from conductor.command.api_refusals import GIT_SETUP_REASONS
from tests.desk_wizard_node import fixture, run_js

MODULES = {"git": "desk-wizard-git.js", "i18n": "studio-i18n.js"}
PENDING = ("unfinished", "unfinished_unborn", "empty", "signature", "signature_sha256",
           "damaged")
DATA: dict[str, Any] = {
    "preview": fixture("wizard", "setup_preview_snapshot.json"),
    "preview_empty": fixture("wizard", "setup_preview_empty.json"),
    "preview_signing": fixture("wizard", "setup_preview_signing.json"),
    "receipt": fixture("wizard", "setup_receipt_commit.json"),
    "receipt_signed": fixture("wizard", "setup_receipt_commit_signed.json"),
    "init": fixture("wizard", "setup_receipt_init.json"),
    "pending": {name: fixture("wizard", f"git_pending_{name}.json")["git"]["first_commit_pending"]
                for name in PENDING},
    "reads": {"repo": fixture("wizard", "git_repo.json")["git"],
              **{name: fixture("wizard", f"git_pending_{name}.json")["git"] for name in PENDING}},
}
#: Helpers every claim shares: `ok` and `refused` build the door's own results, `bad` builds a
#: copy of a value with one path changed, `frozenDeep` asks whether anything in it can be changed.
PRELUDE = """
const show = (value) => console.log(JSON.stringify(value));
const ok = (payload) => ({status: "accepted", code: null, payload});
const refused = (code, payload = null) => ({status: "refused", code, payload});
const reasonOf = (reason) => refused("git_setup_refused", {error: {code: "git_setup_refused",
  message: "x", detail: {reason}}});
const copy = (value) => JSON.parse(JSON.stringify(value));
const without = (value, key) => { const next = copy(value); delete next[key]; return next; };
const frozenDeep = (value) => value === null || typeof value !== "object"
  || (Object.isFrozen(value) && Object.values(value).every(frozenDeep));
"""


def js(body: str) -> Any:
    return run_js(PRELUDE + body, DATA, modules=MODULES)


def test_the_switch_is_one_boolean_and_the_slice_copies_it_and_only_true_opens_it():
    """What the literal IS today is not pinned here: the flip is one literal, and the guard that
    holds it behind lane L's own switch is `test_desk_wizard_git_guards.py`."""
    out = js("""
      show({literal: git.FIRST_COMMIT_CONFIRM_OPEN, closed: git.initialGit(false).open,
        open: git.initialGit(true).open, junk: [git.initialGit(undefined).open,
        git.initialGit("yes").open, git.initialGit(1).open], slice: git.initialGit(false)});
    """)
    assert isinstance(out["literal"], bool), "the switch is one boolean"
    assert out["closed"] is False and out["open"] is True
    assert out["junk"] == [False, False, False], "only the boolean true opens it"
    assert out["slice"] == {"open": False, "door": True, "panel": None, "mode": None,
                            "preview": None, "list": False, "seq": 0, "sending": None,
                            "result": None, "chain": None}


def test_a_preview_is_taken_only_with_its_exact_keys_and_for_the_mode_asked():
    out = js("""
      const good = d.preview, snap = (value) => git.projectPreview(value, "snapshot");
      const extra = copy(good); extra.setup.stray = 1;
      const row = copy(good); row.setup.files[0].stray = 1;
      const odd = copy(good); odd.setup.files[0].git_mode = "120000";
      const digest = copy(good); digest.setup.paths_digest = "sha256:abc";
      const oid = copy(good); oid.setup.files[1].git_oid = "XYZ";
      const version = copy(good); version.setup.digest_version = 1;
      const head = copy(good); head.setup.head = {ref: "refs/heads/x", commit: "a".repeat(40)};
      const word = copy(good); word.setup.warnings = ["Shouting!"];
      const filled = copy(d.preview_empty); filled.setup.files = copy(good.setup.files);
      const wrapped = {...good, other: 1};
      const taken = snap(good);
      show({good: taken !== null, deep: frozenDeep(taken), rows: taken.files.length,
        asEmpty: git.projectPreview(good, "empty"), asOther: git.projectPreview(good, "other"),
        emptyOk: git.projectPreview(d.preview_empty, "empty") !== null,
        emptyWithFiles: git.projectPreview(filled, "empty"),
        signing: git.projectPreview(d.preview_signing, "snapshot").signing,
        missing: snap(without(good, "setup")), bare: snap(good.setup), nothing: snap(null),
        extra: snap(extra), row: snap(row), mode: snap(odd), digest: snap(digest), oid: snap(oid),
        version: snap(version), head: snap(head), word: snap(word), wrapped: snap(wrapped),
        noKey: snap({setup: without(good.setup, "manual")})});
    """)
    assert out["good"] is True and out["deep"] is True and out["rows"] == 4
    assert out["signing"] is True and out["emptyOk"] is True
    for name in ("asEmpty", "asOther", "emptyWithFiles", "missing", "bare", "nothing", "extra",
                 "row", "mode", "digest", "oid", "version", "head", "word", "wrapped", "noKey"):
        assert out[name] is None, name


def test_a_receipt_is_taken_only_with_its_thirteen_exact_keys():
    out = js("""
      const taken = git.projectReceipt(d.receipt);
      const extra = copy(d.receipt); extra.setup.stray = 1;
      const emptyDigest = copy(d.receipt); emptyDigest.setup.mode = "empty";
      const snapNull = copy(d.receipt); snapNull.setup.paths_digest = null;
      const level = copy(d.receipt); level.setup.signature = "valid";
      const step = copy(d.receipt); step.setup.step = "init";
      const count = copy(d.receipt); count.setup.file_count = -1;
      show({good: taken !== null, deep: frozenDeep(taken), branch: taken.target_ref,
        signed: git.projectReceipt(d.receipt_signed).signature,
        extra: git.projectReceipt(extra), missing: git.projectReceipt({setup: without(
          d.receipt.setup, "commit")}), emptyDigest: git.projectReceipt(emptyDigest),
        snapNull: git.projectReceipt(snapNull), level: git.projectReceipt(level),
        step: git.projectReceipt(step), count: git.projectReceipt(count),
        bare: git.projectReceipt(d.receipt.setup), none: git.projectReceipt(undefined)});
    """)
    assert out["good"] is True and out["deep"] is True and out["signed"] == "present"
    assert out["branch"] == "refs/heads/main"
    for name in ("extra", "missing", "emptyDigest", "snapNull", "level", "step", "count", "bare",
                 "none"):
        assert out[name] is None, name


def test_a_step_receipt_is_taken_only_for_the_step_that_was_asked():
    out = js("""
      const nested = copy(d.init); nested.setup.warnings = ["nested_repository"];
      const odd = copy(d.init); odd.setup.warnings = ["something_else"];
      const place = copy(d.init); place.setup.exclude = "absent";
      const exclude = copy(d.init); exclude.setup.step = "exclude";
      show({init: git.projectStepReceipt(d.init, "init") !== null,
        asExclude: git.projectStepReceipt(d.init, "exclude"),
        exclude: git.projectStepReceipt(exclude, "exclude") !== null,
        nested: git.projectStepReceipt(nested, "init") !== null,
        odd: git.projectStepReceipt(odd, "init"), place: git.projectStepReceipt(place, "init"),
        commit: git.projectStepReceipt(d.receipt, "init"),
        other: git.projectStepReceipt(d.init, "first_commit"),
        missing: git.projectStepReceipt({setup: without(d.init.setup, "warnings")}, "init")});
    """)
    assert out["init"] is True and out["exclude"] is True and out["nested"] is True
    for name in ("asExclude", "odd", "place", "commit", "other", "missing"):
        assert out[name] is None, name


def test_the_pending_read_is_taken_in_its_closed_shapes_and_anything_else_is_unreadable():
    out = js("""
      const read = (value) => git.projectPending(value);
      const states = Object.fromEntries(Object.entries(d.pending).map(
        ([name, value]) => [name, read(value).state]));
      const awaiting = d.pending.signature;
      const moved = copy(awaiting); moved.signing.target_ref = "refs/heads/other";
      const unsafe = copy(awaiting); unsafe.terms.target_ref = "refs/heads/a$(calc)";
      unsafe.signing.target_ref = "refs/heads/a$(calc)";
      const shortTree = copy(awaiting); shortTree.signing.tree = "abc";
      const path = copy(awaiting); path.signing.message_path = "../msg.txt";
      const reasoned = {state: "damaged", reason: "torn"};
      const emptyDigest = copy(d.pending.empty); emptyDigest.terms.paths_digest =
        d.pending.unfinished.terms.paths_digest;
      const snapNull = copy(d.pending.unfinished); snapNull.terms.paths_digest = null;
      const count = copy(d.pending.unfinished); count.terms.file_count = 5001;
      const author = copy(d.pending.unfinished); author.terms.author.email = "";
      const control = copy(d.pending.unfinished); control.terms.requested_by = "A\\nB";
      const lone = copy(d.pending.unfinished); delete lone.terms;
      show({states, none: read(null), absent: read(undefined).state, junk: read("x").state,
        list: read([]).state, moved: read(moved).state, unsafe: read(unsafe).state,
        shortTree: read(shortTree).state, path: read(path).state, reasoned: read(reasoned).state,
        waiting: read({state: "waiting"}).state, emptyDigest: read(emptyDigest).state,
        snapNull: read(snapNull).state, count: read(count).state, author: read(author).state,
        control: read(control).state, lone: read(lone).state,
        deep: frozenDeep(read(awaiting)), same: read(awaiting).signing.tree});
    """)
    assert out["states"] == {"unfinished": "unfinished", "unfinished_unborn": "unfinished",
                             "empty": "unfinished", "signature": "awaiting_signature",
                             "signature_sha256": "awaiting_signature", "damaged": "damaged"}
    assert out["none"] is None and out["deep"] is True
    for name in ("absent", "junk", "list", "moved", "unsafe", "shortTree", "path", "reasoned",
                 "waiting", "emptyDigest", "snapNull", "count", "author", "control", "lone"):
        assert out[name] == "unreadable", name


def test_the_pending_of_a_read_is_none_for_an_unlanded_read_and_for_a_server_older_than_the_key():
    out = js("""
      const read = (git) => ({status: "ok", code: null, payload: {git}});
      const old = {state: "repo"};
      const odd = {state: "repo", first_commit_pending: {state: "torn"}};
      const real = (name) => git.pendingOf(read(d.reads[name]));
      show({failed: git.pendingOf({status: "failed", code: "store_error", payload: null}),
        unread: git.pendingOf(undefined), noPayload: git.pendingOf({status: "ok", payload: null}),
        old: git.pendingOf(read(old)), odd: git.pendingOf(read(odd)).state,
        none: real("repo"), awaiting: real("signature").state, damaged: real("damaged").state});
    """)
    assert out["failed"] is None and out["unread"] is None and out["noPayload"] is None
    assert out["old"] is None, "an older server has no operation of the product to leave pending"
    assert out["odd"] == "unreadable", "a key that is there but is not a closed shape is not none"
    assert out["none"] is None and out["awaiting"] == "awaiting_signature"
    assert out["damaged"] == "damaged"


def test_the_two_commands_are_composed_from_signing_alone_with_a_zero_id_as_long_as_the_tree():
    out = js("""
      const sha1 = d.pending.signature.signing, sha256 = d.pending.signature_sha256.signing;
      show({sha1: git.signCommands(sha1), sha256: git.signCommands(sha256),
        arity: git.signCommands.length, deep: frozenDeep(git.signCommands(sha1))});
    """)
    sha1, sha256 = out["sha1"], out["sha256"]
    path = "conductor.v3/git/msg-first-0123456789abcdef0123456789abcdef.txt"
    assert sha1["commit"] == f"git commit-tree {'9c3e5f1a7b2d4086e1f3a5c7d9b0e2f4a6c8d1e3'} " \
        f"-S -F {path}"
    assert sha1["update"] == f"git update-ref refs/heads/main <oid> {'0' * 40}"
    assert sha256["update"].endswith(" " + "0" * 64) and "<oid>" in sha256["update"]
    assert out["arity"] == 1 and out["deep"] is True


def test_no_command_is_composed_when_a_value_leaves_its_safe_set():
    out = js("""
      const base = d.pending.signature.signing;
      const with_ = (key, value) => ({...copy(base), [key]: value});
      const cases = {
        branch_sub: with_("target_ref", "refs/heads/a$(calc)"),
        branch_semi: with_("target_ref", "refs/heads/x;y"),
        branch_tick: with_("target_ref", "refs/heads/q" + String.fromCharCode(96) + "r"),
        branch_amp: with_("target_ref", "refs/heads/x&y"),
        branch_cyrillic: with_("target_ref", "refs/heads/\\u0432\\u0435\\u0442\\u043a\\u0430"),
        branch_space: with_("target_ref", "refs/heads/a b"),
        branch_other_ns: with_("target_ref", "refs/tags/v1"),
        branch_bare: with_("target_ref", "refs/heads/"),
        branch_long: with_("target_ref", "refs/heads/" + "a".repeat(240)),
        tree_upper: with_("tree", base.tree.toUpperCase()),
        tree_short: with_("tree", "abc"),
        tree_between: with_("tree", "a".repeat(50)),
        path_up: with_("message_path", "../msg-first-" + "a".repeat(32) + ".txt"),
        path_name: with_("message_path", "conductor/git/other.txt"),
        path_abs: with_("message_path", "/tmp/conductor/git/msg-first-" + "a".repeat(32) + ".txt"),
        path_ext: with_("message_path", "conductor/git/msg-first-" + "a".repeat(32) + ".sh"),
        extra: {...copy(base), stray: 1}, missing: without(base, "tree"), none: null,
        text: "git commit-tree"};
      show(Object.fromEntries(Object.entries(cases).map(([name, value]) =>
        [name, git.signCommands(value)])));
    """)
    assert out and all(value is None for value in out.values()), out


def test_the_confirm_body_carries_the_previewed_digest_for_a_snapshot_and_null_for_empty():
    out = js("""
      const snap = git.projectPreview(d.preview, "snapshot");
      const empty = git.projectPreview(d.preview_empty, "empty");
      show({snapshot: git.confirmBody("snapshot", snap, "Anna"),
        empty: git.confirmBody("empty", empty, "Anna"),
        emptyPreviewDigest: empty.paths_digest, init: git.stepBody("init", "Anna"),
        preview: git.previewBody("empty")});
    """)
    assert out["snapshot"] == {"step": "first_commit", "mode": "snapshot", "actor": "Anna",
                               "paths_digest": DATA["preview"]["setup"]["paths_digest"]}
    assert out["empty"] == {"step": "first_commit", "mode": "empty", "actor": "Anna",
                            "paths_digest": None}
    assert out["emptyPreviewDigest"].startswith("sha256:"), "the preview keeps its digest"
    assert out["init"] == {"step": "init", "actor": "Anna"}
    assert out["preview"] == {"step": "first_commit", "mode": "empty", "preview": True}


def test_the_continue_body_is_built_from_the_stored_terms_and_the_actor_of_now():
    out = js("""
      const terms = git.projectPending(d.pending.unfinished).terms;
      const empty = git.projectPending(d.pending.empty).terms;
      show({body: git.continueBody(terms, "Anna"), empty: git.continueBody(empty, "Anna"),
        requestedBy: terms.requested_by});
    """)
    stored = DATA["pending"]["unfinished"]["terms"]
    assert out["requestedBy"] == "Owner" != "Anna"
    assert out["body"] == {"step": "first_commit", "mode": "snapshot",
                           "paths_digest": stored["paths_digest"], "actor": "Anna"}
    assert out["empty"] == {"step": "first_commit", "mode": "empty", "paths_digest": None,
                            "actor": "Anna"}


def test_an_answer_the_desk_did_not_read_is_lost_and_never_a_refusal():
    out = js("""
      const kinds = ["init", "exclude", "preview", "confirm", "continue"];
      const lost = (kind, result) => git.classify(kind, result, "snapshot");
      const odd = reasonOf("not_a_reason");
      const bare = refused("git_setup_refused", null);
      const wrongRoute = refused("git_setup_refused", {error: {detail: "x"}});
      const out = {};
      for (const kind of kinds) {
        out[kind] = [lost(kind, {status: "unknown"}), lost(kind, refused("store_error")),
          lost(kind, refused("csrf_denied")), lost(kind, refused("same_origin_denied")),
          lost(kind, refused("a_made_up_code")), lost(kind, odd), lost(kind, bare),
          lost(kind, wrongRoute), lost(kind, refused("")), lost(kind, {status: "weird"}),
          lost(kind, ok({setup: {}})), lost(kind, ok(null)), lost(kind, null),
          lost(kind, ok({stray: 1}))].map((one) => one.status);
      }
      show({out, unknownKind: git.classify("made_up", ok(d.receipt)).status});
    """)
    for kind, statuses in out["out"].items():
        assert statuses == ["lost"] * 14, (kind, statuses)
    assert out["unknownKind"] == "lost"


def test_an_exact_answer_is_done_for_the_press_that_asked_and_for_no_other():
    out = js("""
      const c = (kind, result, mode = "snapshot") => git.classify(kind, result, mode);
      show({init: c("init", ok(d.init)).status, receipt: c("init", ok(d.init)).receipt.step,
        exclude: c("exclude", ok(d.init)).status,
        preview: c("preview", ok(d.preview)).status, previewDeep: frozenDeep(c("preview",
          ok(d.preview))), previewRows: c("preview", ok(d.preview)).preview.files.length,
        previewEmpty: c("preview", ok(d.preview_empty), "empty").status,
        previewOtherMode: c("preview", ok(d.preview), "empty").status,
        confirm: c("confirm", ok(d.receipt)).status, branch: c("confirm", ok(d.receipt))
          .receipt.target_ref, repeat: c("continue", ok(d.receipt)).status,
        continueKind: c("continue", ok(d.receipt)).kind,
        confirmWithInit: c("confirm", ok(d.init)).status,
        previewWithReceipt: c("preview", ok(d.receipt)).status});
    """)
    assert out["init"] == "done" and out["receipt"] == "init" and out["exclude"] == "lost"
    assert out["preview"] == "done" and out["previewDeep"] is True and out["previewRows"] == 4
    assert out["previewEmpty"] == "done" and out["previewOtherMode"] == "lost"
    assert out["confirm"] == "done" and out["branch"] == "refs/heads/main"
    assert out["repeat"] == "done" and out["continueKind"] == "continue"
    assert out["confirmWithInit"] == "lost" and out["previewWithReceipt"] == "lost"


def test_each_of_the_twenty_reasons_and_four_codes_is_a_closed_refusal():
    out = js("""
      const rows = git.GIT_SETUP_REASONS.map((reason) =>
        git.classify("confirm", reasonOf(reason)));
      const codes = git.GIT_SETUP_CODES.map((code) => git.classify("confirm", refused(code)));
      const tool = git.classify("confirm", refused("tool_unavailable", {error: {code:
        "tool_unavailable", message: "x", detail: {tool: "git", reason: "not_pinned"}}}));
      const hostile = git.classify("confirm", refused("tool_unavailable", {error: {detail:
        {tool: "<b>x</b>", reason: "../.."}}}));
      show({reasons: rows.map((one) => [one.status, one.reason, one.code]),
        codes: codes.map((one) => [one.status, one.reason, one.code]), tool: tool.tool,
        hostile: hostile.tool, deep: frozenDeep(rows[0])});
    """)
    reasons = list(GIT_SETUP_REASONS)
    assert out["reasons"] == [["refused", reason, "git_setup_refused"] for reason in reasons]
    assert out["codes"] == [["refused", None, code] for code in (
        "project_not_active", "contract_invalid", "windows_path_too_long", "tool_unavailable")]
    assert out["tool"] == {"name": "git", "reason": "not_pinned"}
    assert out["hostile"] is None, "a tool detail that is not a closed word is not drawn"
    assert out["deep"] is True


def test_a_press_the_desks_own_door_turned_away_is_unsent_and_not_an_unknown_outcome():
    out = js("""
      show(["init", "confirm"].flatMap((kind) => ["route_not_found", "project_mismatch"].map(
        (code) => git.classify(kind, {status: "refused", code}))).map(
        (one) => [one.status, one.kind, one.code]));
    """)
    assert out == [["unsent", "init", "route_not_found"], ["unsent", "init", "project_mismatch"],
                   ["unsent", "confirm", "route_not_found"],
                   ["unsent", "confirm", "project_mismatch"]]


def test_every_reason_has_exactly_one_action_and_the_actions_are_closed():
    out = js("""
      show({reasons: git.GIT_SETUP_REASONS, actions: git.REFUSAL_ACTIONS,
        frozen: Object.isFrozen(git.REFUSAL_ACTIONS)});
    """)
    assert sorted(out["actions"]) == sorted(out["reasons"])
    assert set(out["actions"].values()) == {"none", "retry", "new_preview", "wait", "original"}
    assert out["actions"]["index_locked"] == "retry" == out["actions"]["git_timed_out"]
    assert out["actions"]["paths_changed"] == "new_preview"
    assert out["actions"]["signing_required"] == "wait"
    assert out["frozen"] is True


def test_the_desks_twenty_reasons_are_the_routes_own_tuple_in_its_order():
    out = js("""show({reasons: git.GIT_SETUP_REASONS});""")
    assert out["reasons"] == list(GIT_SETUP_REASONS)
    assert len(out["reasons"]) == 20
