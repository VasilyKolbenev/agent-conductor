# Shipped graph templates

Each file here is one `GraphTemplate` as data: the steps of a reusable cycle,
their topology, the gates, the bounded feedback, and — for every step that
acts — the capability it needs and the arguments it needs it with.

**Roles, never instances.** A template names a `role_id` and nothing about a
deployment: no provider, no instance, no adapter. That is what lets one file
run on more than one machine. A run supplies a `RunBinding` mapping each role
to a configured `instance_id`, and `graph_template.materialize` produces that
run's own immutable `GraphDefinition` from the pair.

**Correcting the default cycle is editing one of these files.** Nothing in
Python or JavaScript has to move: `load_template` reads the file through the
same `GraphTemplate.from_dict` an operator's own file would go through, so what
ships is held to the contract rather than trusted for being ours.

**A change is a new revision.** Bump `revision` when the work changes. A run
that already materialized keeps the definition it was given — that record is
immutable and replays byte for byte — so an edit here can never rewrite what a
past run followed.

The document is closed: every field is one the contract names, and a key it
does not name is refused rather than ignored. Explanations belong in this file.
