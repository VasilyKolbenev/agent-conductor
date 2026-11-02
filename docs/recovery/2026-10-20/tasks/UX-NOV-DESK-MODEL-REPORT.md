# Desk preserves the owner's exact model — locally verified

An owner can set a full model ID in a role's detailed assignment when the
registered harness has a reviewed model flag. Blank means the harness
default. The profile says nothing about an account's entitlement to a
particular model. TASK/DESIGN e4c65d9, code 8b1a21a, based on 0148af5.

The served browser journey configured the Codex checker as `gpt-6.1-sol`
and a Grok diagnostic role with its default. Switching away from Codex and
back cleared the pin. Back and a same-task refresh preserved the owner's
new entry. The POST, frozen run config and reviewed grant card exposed the
same values. A root cause uncovered by this witness was the disappearance
of the Dalio draft after F5. The wizard now reads the existing project draft
when it exists, instead of overwriting it with the bundled starter.

The workflows roster adds `model_pin_supported` (true/false for a registered
harness profile, null for unknown). The older response shape is still admitted.
A forged pin on a known default-only profile was refused with HTTP 422 before
creating the run. Its default was accepted. An identical retry of a standing
Codex run still returned 200 after a simulated installation capability change.
Changing the model after preview retired the preview and produced no authorization
for the old terms. Existing adapter checks for unsupported pins, aliases and the
frozen source of model IDs stay in force.

Evidence: RED was missing the editable model field. The broad selection of
adapter/routing, HTTP, graph, source, line-cap, Desk model and served browser
witnesses passed 496 tests. The three critical witnesses passed separately in
the system encoding. The baseline M0 passed before mutating isolated copies.
Dropping the model from the run request, accepting a known unsupported pin
and retaining the old preview each made its regression witness fail. Original
digests were restored after each mutant.

Last proven: the chosen ID reaches the frozen project and owner card using
local deterministic adapters. First remaining: integrate with the release
branch's approved transient draft-cache transport and rerun the focused F5
journey there. This branch only adds a validated `models` answer to the
draft codec. The browser persistence mechanism inherited from its base is
under independent SEALED review; this slice does not validate or authorize
that mechanism. No subscription model was called or probed in this work.
