Итог: задание I2 принято Codex по запросу владельца 30.10; база `5e6543c`.

# H5-GROK-I2: subscription relay and route admission

Authority: H5-GROK-DIAGNOSE-DESIGN section 2 and addendum 1 (`183904f`),
H5-GROK-COMPAT (`3ecad10`), owner continuation of 30.10.2026.
Overall budget remains 20-25% of the original 53% remaining; at this task start, 47% remains.
This slice prepares the relay without registering it in the production Grok profile.

## Contract and decisions

- New GrokRelay: kind g, auth.json only, exactly one fixed issuer/client scope;
  closed known field roster, oidc mode, nonempty string access key and user_id.
  Optional refresh_token is absent, null or string; optional expiry and oidc fields are strings.
  Every present issuer/client field must match its fixed expected value (issuer trailing slash
  may be removed); a half-present foreign routing pair must not pass through.
  Expiry uses clock_instant; missing/invalid/naive expiry refuses readiness.
- Copy removes refresh_token altogether, preserves access identity/expiry, copies no config,
  and never writes back. Use existing ready/copy_in/discard and fake credentials only.
- Move GROK_AUTH_FIELDS/CREDENTIALS to the value module; grok_build reexports them unchanged.
- Keep the existing six GROK_ROUTE_ENV names and add the exact names from design section 2
  and addendum 1. Wildcards GROK_TRACE_UPLOAD_* and GROK_INTERNAL_OTLP_* are prefix checks,
  not invalid literal environment names in RelaySpec.forbidden_env.
  GrokRelay.forbids and route_env_named use the same pure prefix/name decision.
- Do not add RelaySpec dataclass fields or change Claude/Codex forbidden tuples or snapshots.
- Add a separate grok_compat_switch: only exact declared false pairs, GROK_HOME,
  relay kind g, auth.json and the fixed Grok scope. Use it only in the forced-pair check of
  _route_selected. Operator-selected forbidden names still refuse, including value false and
  mixed case. An absent selected variable is not forwarded and does not refuse a direct pin.
- Rejected alternative: extending Codex access_only_switch. That predicate also strips its
  pair from metadata children; Grok compat pairs must remain on every child.
- Extend g relay-home recognition with existing path/name validation, no weaker checks.
- Production profile activation is a later atomic change with review-only task restrictions,
  checker refusal and UI support. This slice must not open existing dispatch to subscriptions.

## Scope, ownership and proof

Implementer owns only new adapters/grok_relay.py and tests/test_grok_relay.py.
Lead owns relay_env.py, relay_attempt.py, relay_home.py, login_relay.py wording,
grok_build.py reexports, test_grok_relay_environment.py, directly affected COMPAT tests and
CAPPED. An independent reviewer reads both diffs; no shared-file concurrent edits.

Red comparisons before production behavior: an old unregistered profile may be installed only
in the fake test fixture to exercise public ready/copy_in and transport/metadata callers.
Missing-module/import failures are setup evidence, never the red witness.
Prove positive copy, removal (not empty refresh), unchanged source after child edits/discard,
unknown/foreign/API/malformed/expired refusal, exact account, namespace and path admission.
Prove global subscription route refusal, direct-pin operator refusal before any child, safe
forced pairs accepted, and false pairs retained on metadata children. Keep API COMPAT override
witness; subscription positives no longer select forbidden operator names.

Scoped tests in UTF-8 and cp1251 plus unchanged 16 Claude/Codex snapshots. Meaningful mutants
for refresh removal, admit/no-op, expiry, route and forced-pair decisions; M0 first, copy restored
and removed. CAPPED/new file endings checked. No full core for an inactive module slice.
Code and report separate local commits; update handoff and verified local history bundle.

## Live gates and continuation

G2/P completion evidence was not found. Do not infer a successful probe or repeat permission.
Offline preparation before P is a lead sequencing decision for the current recovery budget;
it does not waive G2/P/G6 or claim the access-only form works on the real vendor.
No real CLI, login-home reads, paid calls, server, installation or push in I2.
Before activation, finish the read-only task/UI contract; before a live attempt, prepare the
bounded owner runbook and inspect the dedicated login through an approved names/counts-only
measurement. Keep owner login and in-app gates under the owner's control.
