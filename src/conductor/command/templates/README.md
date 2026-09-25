# Shipped graph templates

Each file here is one `GraphTemplate` as data: the steps of a reusable cycle,
their topology, the gates, the bounded feedback, and — for every step that
acts — the capability it needs and the arguments it needs it with.

**Roles, never instances.** A template names a `role_id` and nothing about a
deployment: no provider, no instance, no adapter. That is what lets one file
run on more than one machine. A run supplies a `RunBinding` mapping each role
to a configured `instance_id`, and `graph_template.materialize` produces that
run's own immutable `GraphDefinition` from the pair.

**No model, either.** A resource row names the thing a step attaches *by
name*, so a model named in a template is a durable demand. A definition
materialized onto a Qwen, a GLM or a Grok instance would still stand in the
journal asking for Sonnet — a record demanding something of a product that has
never heard of it. A `sandbox` row is different and stays — it names what the
work may touch, which is a fact about the work.

Which model runs is the business of the configuration behind the assigned
instance, and that configuration now says so in a field of its own. **A run's
frozen configuration may pin `model` on an instance**, beside the `adapter`
that drives it; `contracts.frozen_config_models` reads it, the runtime hands it
to the bound adapter, and a transport whose profile declares its vendor's flag
puts the two on the command line. An instance that pins none routes none, and
what runs then is whatever the provider's own configuration decides.

This paragraph used to end differently, and the difference is worth keeping:
it said this build had no provider-config field spelled `model` and pointed at
operator-pinned environment NAMES (`ProviderConfig.env_allow`) as the nearest
channel. That is no longer true, and the sentence went with the fact rather
than being left standing. The env-name channel remains what it always was —
a way to let a secret through — and is not how a model is chosen.

None of this reaches a template. The instance is named by a run's binding, the
model by that run's configuration, and the reusable cycle above still names
only a role.

**Correcting the default cycle is editing one of these files.** Nothing in
Python or JavaScript has to move: `load_template` reads the file through the
same `GraphTemplate.from_dict` an operator's own file would go through, so what
ships is held to the contract rather than trusted for being ours.

**A change is a new revision.** Bump `revision` when the work changes. A run
that already materialized keeps the definition it was given — that record is
immutable and replays byte for byte — so an edit here can never rewrite what a
past run followed.

**That exception is spent.** It read: `dalio-v1` may be corrected at `revision`
1 while there is no template store, no route and no run that has ever
materialized from it. All three now exist — `template_store.TemplateStore`
publishes a revision exclusively and refuses to rewrite one, the
`graph/from-template` route materializes through it, and runs have. So revision
1 is frozen: its bytes are what a past run replays against, and the ALPHA-3
definition fixture carries its shape.

`dalio-v2` is what a change looks like now. It is revision 1 plus one field per
review step — `result_artifact_ref`, which names where that step publishes and
so turns the artifact chain from prose into data. It is DERIVED from revision 1
rather than written beside it, and `tests/test_alpha6_dalio_revision.py`
re-performs that derivation and pins both revisions' digests, so neither can
move without a review and the two cannot silently become different cycles.

Revision 1 stays loadable and stays a replay witness. It names no outputs, so a
review materialized from it has nowhere to publish and the transport refuses to
run one — which is the honest consequence of it predating the field, not a
defect to smooth over.

The document is closed: every field is one the contract names, and a key it
does not name is refused rather than ignored. Explanations belong in this file.

`dalio-v4` was the **Стандартный цикл** until revision 5 (below), and stays
selectable as it is. It keeps revision 3's stages, artifact references, human gates and
bounded return to `identify`, and adds `role-checker` as the required verifier
of `do`. Binding that role to the doer's own instance is refused. A separate
instance of the same harness is allowed; no vendor or model is prescribed.

This revision does not automate human decisions. A rejection remains a failed
verification; the operator may request changes at the result gate, complete the
reopened planning steps and approve the next execution. Each execution again
requires the bound independent checker. The instruction document remains a
separate input supplied before execution, as in revision 3. Autonomous feedback
and cycle authorization are separate runtime work.

The current server default permits eight actions. A full second pass needs
nine (four initial planning steps, execution, three replanning steps, execution),
so that default stops before the second execution. Three complete passes need
thirteen actions. The standard does not raise the server budget; configuring and
authorizing an appropriate finite cycle budget remains separate work.

Revisions 1, 2 and 3 remain unchanged and explicitly selectable. A new starter
does not alter a previously saved custom workflow, published revision or run.

`dalio-v5` is the current **Стандартный цикл**, offered first when creating a
workflow. It is revision 4 plus the road a rejected execution is corrected by,
and nothing else: `do` reaches the result gate only `on_succeeded`, and on
`on_failed` it enters `correct`, a loop of bound 2 home to `do`. Revision 4 had
no such road — the Policy runtime corrects only along a failed step's `on_failed`
roads (`policy_frontier.correction_frontier`), so a checker's rejection there
ended the authorized work, and correcting it by replanning needed nine actions
against the default eight.

Under one authorization the correction is exactly one more pass of `do`: it
carries the original instruction and the checker's exact typed feedback, and it
is checked again by the same independent checker. A second rejection exhausts
the loop and stops the run; it is never a success, and a person's approval at
the result gate cannot stand in for the check, because that gate opens only on a
checked result. A rejection without usable feedback is not corrected by invented
data. The bound counts passes of `do` for the whole run, not per outer lap.

Everything else is revision 4's: the stages, roles, artifact references, the
required independent checker, both human gates, and the outer return from the
result gate's `on_changes_requested` to `identify`. A clean pass costs five
actions and one correction six, both within the default eight; a full replanned
second lap still needs nine and is not promised under that default.
`graph_dalio.validate_dalio_correction_template` holds this revision to its own
shape; the one-loop check for revisions 1–4 is unchanged.
