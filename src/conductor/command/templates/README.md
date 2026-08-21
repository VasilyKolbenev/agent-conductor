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
never heard of it. Which model runs is the business of the configuration
behind the assigned instance: this build has no provider-config field spelled
`model`, but it does pass operator-pinned environment NAMES through to a spawn
(`ProviderConfig.env_allow`), which is the channel `adapters/kimi_code.py`
documents for exactly this. A `sandbox` row is different and stays — it names
what the work may touch, which is a fact about the work.

**Correcting the default cycle is editing one of these files.** Nothing in
Python or JavaScript has to move: `load_template` reads the file through the
same `GraphTemplate.from_dict` an operator's own file would go through, so what
ships is held to the contract rather than trusted for being ours.

**A change is a new revision.** Bump `revision` when the work changes. A run
that already materialized keeps the definition it was given — that record is
immutable and replays byte for byte — so an edit here can never rewrite what a
past run followed.

The one exception is a template that has never been anywhere, and it is worth
stating rather than leaving for a reader to infer from a diff: `dalio-v1` was
corrected at `revision` 1 while there is still no template store, no route and
no run that has ever materialized from it. Nothing exists that a bump would
distinguish this from. The moment one does, this exception is spent.

The document is closed: every field is one the contract names, and a key it
does not name is refused rather than ignored. Explanations belong in this file.
