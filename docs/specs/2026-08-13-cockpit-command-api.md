# Cockpit Command API — frozen interface (C/API-0)

- **Status:** FROZEN CONTRACT for Day-2 implementation (slice C/API-1)
- **Slice:** C/API-0, plan section 12.3 (December Command v2 four-day strike)
- **Date:** 2026-08-13
- **Owns:** the browser-facing command HTTP surface, the per-process anti-CSRF
  token, the same-origin rule, and the additive run-event extension of the
  existing SSE stream.
- **Binds to (read-only):** `src/conductor/command/contracts.py` (CMD-1),
  `run_store.py` (CMD-2), `adapters/base.py` (CMD-3), `service.py` (CMD-4),
  `server.py` (alpha SSE), `spec/PROTOCOL.md` (Protocol v1),
  `docs/adr/0001-harness-control-plane-model.md`, and
  `docs/adr/0004-command-panel-writes-and-human-decisions.md`.

## 0. What this freezes, and what it does not implement — FROZEN CONTRACT

This document is a **freeze**, not an implementation report. It fixes the URL,
method, JSON request/response shapes, refusal shapes, status codes, the
anti-CSRF token design, the same-origin rule, and the SSE extension so that the
runtime (lane A) and the Cockpit UI (C/UI-1) cannot invent incompatible command
shapes on Day 2. Every rule below is written in the contract mood: it states
what the Day-2 endpoint (C/API-1) and its callers **MUST** and **MUST NOT** do.

**No endpoint described here exists yet.** As of this SHA the loopback server
(`server.py`) serves only the read-only Protocol-v1 routes (`/`, `/state.json`,
`/harnesses.json`, `/lane/<author>.json`, `/handoff/<author>.md`, `/events`).
The `/command/*` routes, the anti-CSRF token, and the run-event SSE frames are
implemented by C/API-1 on Day 2. Keywords MUST, MUST NOT, SHOULD, and MAY are
used per their ordinary normative sense.

Every durable response shape below binds to the CMD-1 contracts **by field**.
Browser requests are stricter than `from_dict()`: every request shape is closed,
unknown fields are refused, and `arguments` is checked against the exact
capability schema in section 4.1 before any contract is built. A response is a
contract's `as_dict()` serialization. Section 7 states the field bindings; the
canonical examples (tagged
`<!-- CANONICAL:name -->`) are validated against `contracts.py` by
`tests/test_cockpit_command_api_freeze.py`.

The browser's writable surface is fixed by safety law 3: validated Command
requests, Human decision receipts, and explicitly confirmed design edits -- and
nothing else. At this freeze only the first two have routes. A design edit has
no HTTP route until C/EDIT-1 freezes its preview, validation, diff, digest,
fresh-confirmation, and atomic-write relation. This is deliberate fail-closed
scope, not permission for C/API-1 to invent a generic file-write endpoint.

## 1. Transport, origin, and the loopback surface — FROZEN CONTRACT

1. The command surface is served by the **same** loopback process as the panel.
   The server is bound to `127.0.0.1` only (never `0.0.0.0`), exactly as
   `build()` binds it today. `/command/*` MUST NOT be reachable off the loopback
   interface.
2. Command routes live under the `/command/` path prefix so they are visibly
   separate from the Protocol-v1 read routes and stay **outside the pure merge
   path** (plan section 4). No `/command/*` route reads or writes `state.json`.
   C/API-1 implements exactly this table; every other method/path pair is
   `method_not_allowed` or `route_not_found` and has no durable effect:

<!-- CANONICAL:route_table -->
```json
[
  {
    "method": "GET", "path": "/command/session", "mutation": false, "csrf": false
  },
  {
    "method": "GET", "path": "/command/runs/<run_id>", "mutation": false, "csrf": false
  },
  {
    "method": "GET", "path": "/command/runs/<run_id>/controls",
    "mutation": false, "csrf": false
  },
  {
    "method": "POST", "path": "/command/runs/<run_id>/proposals",
    "mutation": true, "csrf": true
  },
  {
    "method": "POST", "path": "/command/runs/<run_id>/actions",
    "mutation": true, "csrf": true
  },
  {
    "method": "POST", "path": "/command/runs/<run_id>/decisions",
    "mutation": true, "csrf": true
  }
]
```
3. Every **mutating** request (any method other than GET/HEAD on a `/command/*`
   route) MUST pass all three checks before any durable effect, and be refused
   if any fails:
   - **Host allowlist (anti-DNS-rebinding).** The `Host` header MUST be one of
     `127.0.0.1:<port>` or `localhost:<port>` for the port this process bound.
     Any other `Host` is refused `same_origin_denied` (403). This blocks a
     rebinding page that resolves an attacker domain to `127.0.0.1`.
   - **Same-origin.** The `Origin` header, when present, MUST equal `http://`
     plus that request's allowed `Host` value exactly; the two loopback aliases
     are not interchangeable inside one request. When `Origin` is absent, the
     `Referer` scheme and host:port MUST equal that origin. A mutating request
     carrying **neither** `Origin` nor
     `Referer` is refused `same_origin_denied` (403): the rule is fail-closed.
   - **Anti-CSRF token.** Section 2.
4. GET reads under `/command/*` (section 6) MUST also enforce the Host allowlist
   and are same-origin by construction (they return no ambient-authority
   response a cross-origin reader could observe), but they do **not** require the
   anti-CSRF token, because they cause no durable effect.
5. Responses are `application/json; charset=utf-8`. A request may use
   `application/json` or `application/json; charset=utf-8`, with a UTF-8 body.
   Any other parameter/media type, a non-object JSON body, duplicate JSON key,
   or invalid UTF-8/JSON is refused `malformed_request` (400).
   Validation starts from ordered raw header pairs and raw body bytes; it MUST
   NOT first collapse headers into a mapping. Header names compare
   case-insensitively. `Host`, `Content-Type`, and `X-Conduct-CSRF` occur exactly
   once; `Origin` and `Referer` occur at most once. A duplicate is refused even
   when its values agree. Precedence is: Host cardinality/allowlist →
   Origin/Referer cardinality/relation → CSRF cardinality/equality → Content-Type
   cardinality/value → UTF-8, JSON duplicate-key, syntax, and object checks.
    Their codes are respectively `same_origin_denied`, `same_origin_denied`,
    `csrf_denied`, `malformed_request`, and `malformed_request`.
   A known command POST has exactly one decimal, non-negative `Content-Length`
   no greater than 65,536 bytes. Missing, duplicate, negative, non-decimal, or
   larger lengths are `malformed_request`; any `Transfer-Encoding`, including a
   request that also carries `Content-Length`, is refused. The server rejects an
   unsafe framing declaration before reading a body and closes the connection
   after an over-limit or short read. Framing belongs to the final body phase:
   Host, Origin/Referer, CSRF, and Content-Type keep the precedence above.
6. These checks are the structural expression of safety law 4 ("every browser
   mutation requires same-origin validation and a per-process anti-CSRF token").
7. Command responses never emit `Access-Control-Allow-Origin` and the server
   never accepts command preflight as authority. Redirects are not followed or
   returned by a command route.
8. After HTTP/body validation but before replay that may lead to append,
   confirmation, or a Human receipt, every mutating route calls the shared
   writable-route containment/ownership gate over `conductor/runs/<run_id>` and
   its owned files. A portal, reparse point, hard-link alias, or irregular owned
   file is `route_unsafe`; the endpoint does not invoke the service/store/runtime
   mutation and returns an empty-effect refusal.

That last rule is **HELD** by the shared typed relation below. C/API-1 imports
the type and relation directly; any non-empty result maps to `route_unsafe`
without inspecting a violation's fields, renderer, exception, or text:

<!-- CANONICAL:route_dependency -->
```json
{
  "api_slice": "C/API-1",
  "public_module": "conductor.command.containment",
  "public_relation": "run_route_violations",
  "public_violation_type": "RouteViolation",
  "state": "held",
  "nonempty_result": "route_unsafe",
  "parse_exception_prose": false
}
```

## 2. The per-process anti-CSRF token — FROZEN CONTRACT

### 2.1 Issue

- The server process MUST mint **one** anti-CSRF token when it starts, from a
  cryptographically secure source (`secrets.token_urlsafe`, at least 32 bytes of
  entropy). The token is **per process**: a new process start mints a new token,
  and the previous token is thereby invalidated.
- The token MUST live only in process memory. It MUST NOT be written to
  `conductor/` state, to any run record, receipt, event, report, or to
  `state.json`. This keeps it consistent with safety law 8 (nothing secret-like
  is written to durable project state) even though the token is a per-process
  nonce, not a credential.

### 2.2 Transport

- A same-origin caller reads the current token from a dedicated GET endpoint:
  `GET /command/session` → `200`. `origin` is derived from that request's
  allowed Host, never copied from an Origin header:

<!-- CANONICAL:session_response -->
```json
{
  "csrf_token": "<process-token>",
  "origin": "http://127.0.0.1:7802"
}
```

  This endpoint enforces the Host allowlist (section 1). The panel fetches it on
  load and holds the token in memory only. Its response carries
  `Cache-Control: no-store`; the token is never embedded in static HTML or a URL.
- Every mutating request MUST carry the token in the custom request header
  `X-Conduct-CSRF`. The token MUST NOT be transported as a cookie: the surface
  uses **no cookies and no cookie-carried ambient authority**, so a classic form-POST CSRF has
  no credential to ride, and a custom header cannot be set by a cross-origin
  `<form>` or simple `fetch` without a CORS preflight the server never approves.

### 2.3 Validation relation

- On a mutating request the server MUST compare the presented `X-Conduct-CSRF`
  header against the token **this process minted at startup**, using a
  constant-time comparison, and refuse `csrf_denied` (403) unless they are
  equal.
- The relation has **two independent sides**: the presented token comes from the
  request header (the caller); the expected token comes from process memory
  (minted at startup, never read back from the request). A check that compared
  the request against itself would be vacuous — the fixtures in
  `tests/fixtures/cockpit_command_csrf_fixtures.json` encode the provenance of
  each token (`current_process`, `prior_process`, `attacker`, `none`) precisely
  so a Day-2 test cannot accidentally satisfy both sides from one source.
- The token does not rotate per request; within one live process a valid token
  is reusable by the same-origin panel. Against a browser-origin attacker its
  security comes from **secrecy plus origin**, not from single use:
  - **missing** (`X-Conduct-CSRF` absent) → refused `csrf_denied`.
  - **stale** (a token minted by a *previous* process) → unequal to this
    process's token → refused `csrf_denied`.
  - **foreign** (a token no Conduct process minted, attacker-chosen) → unequal →
    refused `csrf_denied`.
  - **replayed** (a token captured from an earlier process and replayed against
    this one) → unequal to this process's token → refused `csrf_denied`. A
    cross-origin page cannot read `/command/session` under the same-origin
    policy, so it cannot capture a *current* token to replay.

This is deliberately a **trusted single-user-host boundary**, not local-process
authentication. Any process running as the same OS user (including local
malware) can call `GET /command/session`, read the current token, and act as the
panel. The token and same-origin checks protect against browser cross-origin
requests and DNS rebinding only. Peer credentials, OS-user authentication, and
defence against a hostile local process are outside this preview/API freeze.

## 3. Envelope, status codes, and refusal shape — FROZEN CONTRACT

### 3.1 Success envelope

A successful mutating command returns the created record as its CMD-1
`as_dict()` serialization, directly as the JSON body (no wrapper), so the
response body round-trips through the same contract that validated it:

- `201 Created` when a new immutable record was appended.
- `200 OK` for GET reads and when an endpoint finds the exact immutable record
  already associated with the submitted receipt id or idempotency key. Reusing
  that identity with different facts is a conflict, never a successful retry.

### 3.2 Refusal shape and ethos

A refusal returns a JSON body of exactly this shape and nothing more:

<!-- CANONICAL:refusal_shape -->
```json
{
  "error": {
    "code": "service_refused",
    "message": "frozen config declares no instance 'ghost-dev'",
    "detail": { "run_id": "run-cockpit-001", "instance_id": "ghost-dev" }
  }
}
```

The refusal follows the repo's refusal ethos, identical to `project_status.detail`
("the fact only, never advice") and to the service/store exception messages it
translates:

- `code` is one of the frozen vocabulary in section 3.3 — a stable machine token.
- `message` states the **fact** in one sentence and names the **exact
  identifiers** involved (run id, instance id, adapter id, capability, digest,
  key, receipt id, gate id, field). It gives **no advice**: it never proposes a
  fix, a retry, or an object to change or delete.
- `detail` carries those same identifiers as structured fields for the UI. It
  MUST NOT carry a secret, a token, a stack trace, or a filesystem path outside
  the project.

The endpoint does **not** infer authority from exception prose. C/API-1 owns a
small translation seam from the semantic refusal produced by the contract,
service, authorization gate, route gate, or store to `(code, status)`. Runtime
exception class names and messages are not frozen here and MUST NOT be parsed to
choose a code.

### 3.3 Frozen error-code vocabulary and exception mapping

<!-- CANONICAL:error_codes -->
```json
[
  { "code": "same_origin_denied",    "status": 403, "source": "http_security" },
  { "code": "csrf_denied",           "status": 403, "source": "http_security" },
  { "code": "method_not_allowed",    "status": 405, "source": "routing" },
  { "code": "route_not_found",       "status": 404, "source": "routing" },
  { "code": "malformed_request",     "status": 400, "source": "http_shape" },
  { "code": "contract_invalid",      "status": 422, "source": "contract" },
  { "code": "run_corrupt",           "status": 409, "source": "store" },
  { "code": "store_error",           "status": 500, "source": "store" },
  { "code": "route_unsafe",          "status": 409, "source": "route_gate" },
  { "code": "service_refused",       "status": 409, "source": "service" },
  { "code": "capability_unsupported", "status": 409, "source": "capability" },
  { "code": "authorization_refused", "status": 409, "source": "authorization" },
  { "code": "record_conflict",       "status": 409, "source": "store" }
]
```

- `contract_invalid` includes an unknown request field, a capability argument
  shape mismatch, and a `ContractError` from a CMD-1 constructor.
- `run_corrupt` is the typed `CorruptRun` branch. Every other `StoreError` is
  `store_error`, except the typed `RecordConflict` branch, which is
  `record_conflict`. In particular, this freeze does not pretend the current
  generic missing-run error is type-distinguishable from other store failures.
- `service_refused` is one `ServiceError`: mode, instance, and adapter mismatch
  are facts in sanitized `message/detail`, not machine codes inferred from text.
  `capability_unsupported` remains distinct because `UnsupportedCapability` is
  already a distinct type.
- `authorization_refused` is one `AuthorizationError`: absent proposal,
  mismatched facts, changed digest, and temporal expiry are not falsely split
  into codes the current gate cannot type-distinguish.
- `route_unsafe` is held by the public typed dependency in section 1. API-1
  consumes only whether `run_route_violations` is empty; it never parses a
  rendered violation or `PreviewError` prose.

## 4. Command endpoints — FROZEN CONTRACT

The shared config's `instances` list is the adapter-binding authority (CMD-4):

<!-- CANONICAL:config -->
```json
{
  "cycle": { "id": "cockpit-orbit", "phases": ["dispatch", "review"] },
  "instances": [
    { "id": "claude-dev", "adapter": "claude-code", "token_env": "ANTHROPIC_API_KEY" },
    { "id": "codex-review", "adapter": "codex", "api_key_env": "OPENAI_API_KEY" }]
}
```

Its canonical config digest is
`sha256:0e0efae86b6ea79a902ef02935a2515e561e22de6b9bd6abebe8f4f174efa2e5`.

The browser never supplies an executable, argv, shell text, cwd, environment
value, PID, or filesystem destination. It submits one declared capability and
the endpoint validates `arguments` against this closed registry before calling
the service. Every listed key is required and no other key is accepted:

<!-- CANONICAL:argument_schemas -->
```json
{
  "dispatch": ["work_item_id", "instruction_ref", "profile", "artifact_refs",
    "output_limit_profile"],
  "review": ["work_item_id", "target_artifact_refs", "review_profile"],
  "evidence": ["target_action_id", "kinds"],
  "stop": ["target_attempt_id", "reason"],
  "retry": ["prior_action_id", "reason"],
  "switch": ["prior_action_id", "target_instance_id", "handoff_ref"]
}
```

This registry is derived from the six exact public types in
`DEEP_ARGUMENT_TYPES`; their `from_dict`/`as_dict` round trip is the authority,
including exact JSON-list fields and closed enum values. `message`, `pause`,
`resume`, and `notify` are absent because no proven deep adapter owns them.
`observe` is absent because observations are adapter-authored facts. A
capability absent here or from the bound adapter manifest is
`capability_unsupported`; malformed arguments for a present capability are
`contract_invalid`, never a generic arguments escape hatch.

### 4.1 `POST /command/runs/<run_id>/proposals` — mint an ActionProposal

Maps to `CommandService.propose`. Refused `service_refused` (409) when the run's
control mode is Observe. The request carries the browser-supplied fields; the
server injects `proposal_id` (minted), `proposed_at` (clock), `config_digest`
(the run's frozen digest), and `schema_version`.

Request:

<!-- CANONICAL:propose_request -->
```json
{
  "instance_id": "claude-dev", "attempt_id": "attempt-cockpit-001",
  "capability": "dispatch",
  "arguments": {
    "work_item_id": "work-cockpit-001", "instruction_ref": "instruction-cockpit-001",
    "profile": "implement", "artifact_refs": ["artifact-cockpit-001"],
    "output_limit_profile": "normal"
  },
  "scope": ["src", "tests"], "proposed_by": "claude-dev",
  "rationale": "The lane finished its handoff and asks to dispatch implementation.",
  "timeout_seconds": 900,
  "adapter_id": "claude-code"
}
```

The request has exactly these top-level fields. `adapter_id` is the sole
optional field; every other field shown is required. A recursive argument key
named `cmd`, `command`, `script`, `shell`, `argv`, `executable`, `cwd`, `path`,
`env`, or `env_allow` is refused `contract_invalid`, as is any key outside the
selected capability schema.

`adapter_id` is optional; when present it MUST equal the config-bound adapter or
the request is refused `service_refused` (409). Response `201` — an
`ActionProposal.as_dict()`:

<!-- CANONICAL:action_proposal -->
```json
{
  "schema_version": 2, "proposal_id": "proposal-cockpit-001",
  "run_id": "run-cockpit-001", "attempt_id": "attempt-cockpit-001",
  "instance_id": "claude-dev", "capability": "dispatch",
  "arguments": {
    "work_item_id": "work-cockpit-001", "instruction_ref": "instruction-cockpit-001",
    "profile": "implement", "artifact_refs": ["artifact-cockpit-001"],
    "output_limit_profile": "normal"
  },
  "scope": ["src", "tests"], "proposed_by": "claude-dev",
  "proposed_at": "2026-08-13T12:01:00Z", "timeout_seconds": 900,
  "rationale": "The lane finished its handoff and asks to dispatch implementation.",
  "config_digest": "sha256:0e0efae86b6ea79a902ef02935a2515e561e22de6b9bd6abebe8f4f174efa2e5",
  "preview_digest": "sha256:ef21f1ef6bfa392a6c6acb57469261a9b034fdb55cec95c2cf77db7ef2856c7f"
}
```

`preview_digest` is **derived** by the contract from the whole proposal body; the
UI MUST treat it as read-only and later echo it verbatim to confirm (section
4.3). Editing any significant field mints a different proposal with a different
digest.

### 4.2 `POST /command/runs/<run_id>/actions` — confirm one unchanged proposal

Maps to A/CONF-1 exactly as it exists at the planning base. The browser restates
the proposal facts the Human saw: `preview_digest`, `capability`, `scope`, and
`config_digest`. It also supplies `confirmed_by`. The endpoint injects
`confirmation_id` and `confirmed_at` from its id/clock providers, and supplies
the server-owned action/time/age budget. No caller controls an action id,
idempotency key, mode, timestamp, or budget.
Unknown fields are refused even when a CMD-1 response contract would preserve
them through `extra`. In particular the caller cannot supply `confirmation_id`,
`action_id`, `idempotency_key`, `mode`, either confirmation/request timestamp,
`run_id`, `schema_version`, or any budget field/object. Attempt, instance,
arguments, requested actor, and timeout come from the proposal/confirmation and
cannot be overridden either.

<!-- CANONICAL:confirm_request -->
```json
{
  "proposal_id": "proposal-cockpit-001",
  "preview_digest": "sha256:ef21f1ef6bfa392a6c6acb57469261a9b034fdb55cec95c2cf77db7ef2856c7f",
  "capability": "dispatch",
  "scope": ["src", "tests"],
  "config_digest": "sha256:0e0efae86b6ea79a902ef02935a2515e561e22de6b9bd6abebe8f4f174efa2e5",
  "confirmed_by": "release-owner"
}
```

Every restated fact MUST equal the durable proposal/run and the server timestamp
MUST be within the server budget's confirmation-age bound. Any changed,
expired, stale, or absent proposal fact is `authorization_refused` (409).
A/CONF-1 injects the remaining `ActionRequest` facts:
`action_id`, `requested_at`, `mode == confirm`, and the deterministic
`idempotency_key == "dispatch-" + proposal_id`; it copies attempt, instance,
arguments, and timeout from the proposal. Response `201` is its
`ActionRequest.as_dict()`:

<!-- CANONICAL:action_request -->
```json
{
  "schema_version": 2, "action_id": "action-cockpit-001",
  "run_id": "run-cockpit-001", "attempt_id": "attempt-cockpit-001",
  "instance_id": "claude-dev", "capability": "dispatch",
  "arguments": {
    "work_item_id": "work-cockpit-001", "instruction_ref": "instruction-cockpit-001",
    "profile": "implement", "artifact_refs": ["artifact-cockpit-001"],
    "output_limit_profile": "normal"
  },
  "scope": ["src", "tests"], "requested_by": "release-owner",
  "requested_at": "2026-08-13T12:02:00Z",
  "idempotency_key": "dispatch-proposal-cockpit-001",
  "timeout_seconds": 900,
  "preview_digest": "sha256:ef21f1ef6bfa392a6c6acb57469261a9b034fdb55cec95c2cf77db7ef2856c7f",
  "mode": "confirm"
}
```

The **unchanged-proposal relation** is frozen field by field:
`action.preview_digest == proposal.preview_digest`; `capability` and `scope`
equal both the Human confirmation and proposal; `attempt_id`, `instance_id`,
`arguments`, and `timeout_seconds` come from the proposal; `requested_by` is the
confirmed Human; and `mode` is exactly `confirm`. Policy is a separate Day-3
authority seam and cannot be selected through this endpoint. Confirming records
acceptance but does not execute here; execution is the runtime seam after it.

## 5. Human-decision endpoints — FROZEN CONTRACT

### 5.1 `POST /command/runs/<run_id>/decisions` — record a DecisionReceipt

Maps to `RunStore.append(DecisionReceipt)`. The store exclusive-creates the
receipt file and appends its journal line; a crash between them is reconciled by
replay and is not mislabeled atomic. The browser supplies a stable `receipt_id`
so an exact retry can find the same immutable decision. The server injects
`decided_at` from its clock and `config_digest` from the run. Request:

<!-- CANONICAL:decision_request -->
```json
{
  "receipt_id": "decision-cockpit-001", "gate_id": "release",
  "action": "approve", "actor": "release-owner",
  "reason": "Reviewed the streamed evidence; approving the release gate.",
  "scope_refs": ["src", "tests"], "evidence_refs": ["evidence-cockpit-001"],
  "supersedes": null
}
```

The request is closed: `run_id` comes from the path; `decided_at`,
`config_digest`, and `schema_version` are server-owned. `action_id` and any
unknown or recursively nested extension are refused rather than admitted via a
response contract's tolerant `extra` channel.

`action` MUST be one of `approve | reject | request_changes | waive`; `reason` is
required for `request_changes` and `waive` (the contract enforces this). A
`supersedes` naming an unknown or different-gate receipt is a sanitized
`store_error` under the current store taxonomy. An exact retry of the same
`receipt_id` and facts returns the existing receipt with 200; different facts
are `record_conflict`.
Response `201` is a new `DecisionReceipt.as_dict()`:

<!-- CANONICAL:decision_receipt -->
```json
{
  "schema_version": 2, "receipt_id": "decision-cockpit-001",
  "run_id": "run-cockpit-001", "gate_id": "release",
  "action": "approve", "actor": "release-owner",
  "decided_at": "2026-08-13T12:30:00Z",
  "reason": "Reviewed the streamed evidence; approving the release gate.",
  "scope_refs": ["src", "tests"],
  "config_digest": "sha256:0e0efae86b6ea79a902ef02935a2515e561e22de6b9bd6abebe8f4f174efa2e5",
  "evidence_refs": ["evidence-cockpit-001"], "supersedes": null
}
```

The gate lifecycle is **computed, never authored** (ADR 0001 §4, safety):
absence of a receipt is `idle`, never a pass. A gate's state is the projection
`gate_decision(receipts, run_id, gate_id)` over the run's receipts:
`approve → satisfied`, `reject → failed`, `request_changes → changes_requested`,
`waive → waived`, and no matching receipt → `idle`. The endpoint MUST NOT
compute or store a gate "pass" flag; the UI reads the projection.

## 6. Run read and the run-event SSE extension — FROZEN CONTRACT

### 6.1 `GET /command/runs/<run_id>` — replay one run read-only

The UI reads run state and history here (history/replay, C/UI-1; Human Gate,
C/HG-1). Maps to `RunStore.read`, which validates and replays without editing a
durable byte. Response `200` binds field by field to `RecoveredRun`: `run` is a
`RunEnvelope.as_dict()`, `config` is the frozen configuration object, `records`
is the append-ordered journal each wrapped exactly as the store wraps it
(`{ "record_type": <kind>, "record": <contract as_dict> }`), and `warnings` is
the replay warning list. A missing run is currently `store_error` (500), because
the planning-base store has no typed not-found branch and the endpoint may not
infer one from prose. The record kinds and their contracts are the closed v2 vocabulary:
`action_request` (`ActionRequest`), `action_result` (`ActionResultReceipt`),
`evidence` (`EvidenceRef`), `decision` (`DecisionReceipt`),
`action_proposal` (`ActionProposal`), `adapter_observation` (`ObservationRecord`),
and `attempt_event` (`AttemptEvent`).

<!-- CANONICAL:run_read_response -->
```json
{
  "run": {
    "schema_version": 2, "run_id": "run-cockpit-001", "cycle_id": "cockpit-orbit",
    "created_at": "2026-08-13T12:00:00Z",
    "config_digest": "sha256:0e0efae86b6ea79a902ef02935a2515e561e22de6b9bd6abebe8f4f174efa2e5",
    "mode": "confirm", "status": "active"
  },
  "config": {
    "cycle": { "id": "cockpit-orbit", "phases": ["dispatch", "review"] },
    "instances": [
      { "id": "claude-dev", "adapter": "claude-code", "token_env": "ANTHROPIC_API_KEY" },
      { "id": "codex-review", "adapter": "codex", "api_key_env": "OPENAI_API_KEY" }]
  },
  "records": [
    { "record_type": "action_proposal", "record": {
      "schema_version": 2, "proposal_id": "proposal-cockpit-001", "run_id": "run-cockpit-001",
      "attempt_id": "attempt-cockpit-001",
      "instance_id": "claude-dev", "capability": "dispatch",
      "arguments": {
        "work_item_id": "work-cockpit-001", "instruction_ref": "instruction-cockpit-001",
        "profile": "implement", "artifact_refs": ["artifact-cockpit-001"],
        "output_limit_profile": "normal" }, "scope": ["src", "tests"],
      "proposed_by": "claude-dev", "proposed_at": "2026-08-13T12:01:00Z",
      "timeout_seconds": 900,
      "rationale": "The lane finished its handoff and asks to dispatch implementation.",
      "config_digest": "sha256:0e0efae86b6ea79a902ef02935a2515e561e22de6b9bd6abebe8f4f174efa2e5",
      "preview_digest": "sha256:ef21f1ef6bfa392a6c6acb57469261a9b034fdb55cec95c2cf77db7ef2856c7f"
    } },
    { "record_type": "action_request", "record": {
      "schema_version": 2, "action_id": "action-cockpit-001", "run_id": "run-cockpit-001",
      "attempt_id": "attempt-cockpit-001", "instance_id": "claude-dev", "capability": "dispatch",
      "arguments": {
        "work_item_id": "work-cockpit-001", "instruction_ref": "instruction-cockpit-001",
        "profile": "implement", "artifact_refs": ["artifact-cockpit-001"],
        "output_limit_profile": "normal" }, "scope": ["src", "tests"],
      "requested_by": "release-owner", "requested_at": "2026-08-13T12:02:00Z",
      "idempotency_key": "dispatch-proposal-cockpit-001", "timeout_seconds": 900,
      "preview_digest": "sha256:ef21f1ef6bfa392a6c6acb57469261a9b034fdb55cec95c2cf77db7ef2856c7f",
      "mode": "confirm" } },
    { "record_type": "attempt_event", "record": {
      "schema_version": 2, "event_id": "event-lease-cockpit-001", "run_id": "run-cockpit-001",
      "action_id": "action-cockpit-001", "attempt_id": "attempt-cockpit-001",
      "instance_id": "claude-dev", "adapter_id": "claude-code", "phase": "effect_lease",
      "recorded_at": "2026-08-13T12:03:00Z",
      "request_digest": "sha256:4ff0ae5768792e2d8161e993399d2fc0720e1d2a42bde0380929f0688bc1c7a2",
      "recovery_ref": "recovery-cockpit-001", "outcome": null, "exit_code": null } },
    { "record_type": "attempt_event", "record": {
      "schema_version": 2, "event_id": "event-observed-cockpit-001", "run_id": "run-cockpit-001",
      "action_id": "action-cockpit-001", "attempt_id": "attempt-cockpit-001",
      "instance_id": "claude-dev", "adapter_id": "claude-code", "phase": "execution_observed",
      "recorded_at": "2026-08-13T12:20:00Z",
      "request_digest": "sha256:4ff0ae5768792e2d8161e993399d2fc0720e1d2a42bde0380929f0688bc1c7a2",
      "recovery_ref": "recovery-cockpit-001", "outcome": "succeeded", "exit_code": 0 } }
  ],
  "warnings": []
}
```

The two attempt phases are separate append-ordered facts. They bind to the same
durable request, frozen adapter, attempt, and opaque recovery reference:

<!-- CANONICAL:attempt_event_effect_lease -->
```json
{
  "schema_version": 2, "event_id": "event-lease-cockpit-001", "run_id": "run-cockpit-001",
  "action_id": "action-cockpit-001", "attempt_id": "attempt-cockpit-001",
  "instance_id": "claude-dev", "adapter_id": "claude-code", "phase": "effect_lease",
  "recorded_at": "2026-08-13T12:03:00Z",
  "request_digest": "sha256:4ff0ae5768792e2d8161e993399d2fc0720e1d2a42bde0380929f0688bc1c7a2",
  "recovery_ref": "recovery-cockpit-001", "outcome": null, "exit_code": null
}
```
<!-- CANONICAL:attempt_event_execution_observed -->
```json
{
  "schema_version": 2, "event_id": "event-observed-cockpit-001", "run_id": "run-cockpit-001",
  "action_id": "action-cockpit-001", "attempt_id": "attempt-cockpit-001",
  "instance_id": "claude-dev", "adapter_id": "claude-code", "phase": "execution_observed",
  "recorded_at": "2026-08-13T12:20:00Z",
  "request_digest": "sha256:4ff0ae5768792e2d8161e993399d2fc0720e1d2a42bde0380929f0688bc1c7a2",
  "recovery_ref": "recovery-cockpit-001", "outcome": "succeeded", "exit_code": 0
}
```

Two more record shapes the read returns (runtime-written, browser-read) are
frozen so the UI does not invent them:

<!-- CANONICAL:action_result_receipt -->
```json
{
  "schema_version": 2, "receipt_id": "receipt-cockpit-001",
  "action_id": "action-cockpit-001", "run_id": "run-cockpit-001",
  "attempt_id": "attempt-cockpit-001", "instance_id": "claude-dev",
  "outcome": "succeeded", "observed_at": "2026-08-13T12:20:00Z",
  "evidence_refs": ["evidence-cockpit-001"], "detail": null, "exit_code": 0
}
```

<!-- CANONICAL:evidence_ref -->
```json
{
  "schema_version": 2, "evidence_id": "evidence-cockpit-001",
  "run_id": "run-cockpit-001", "kind": "log",
  "uri": "conductor/runs/run-cockpit-001/evidence/dispatch.log",
  "label": "dispatch stdout", "created_by": "claude-code",
  "observed_at": "2026-08-13T12:19:00Z", "digest": null,
  "verification": "unverified", "verified_by": null, "verified_at": null
}
```

### 6.2 `GET /command/runs/<run_id>/controls` — capability-derived controls

The response carries two arrays that answer two different questions.

`instances` is derived from the frozen instance-to-adapter binding, the
registry's reviewed manifest value, and the argument schemas in section 4. It
contains only controls all three sources permit. The arrays are sorted and an
unsupported control is absent; there is no `enabled`, `disabled`, or tooltip
placeholder that could become a decorative unsupported control.

`providers` is the reviewed provider roster this build was given — every
CATALOGUED provider, sorted by `provider_id`, whether or not an operator
configured it. Each row carries exactly five names and nothing else:
`provider_id`, `display_name`, `availability`, `implementation`, `controls`.

`availability` and `implementation` are **separate closed vocabularies and MUST
NOT be mixed**; they share no value, so neither can be read as the other:

- `availability` — a fact about the operator's machine:
  `available` | `executable_absent` | `version_mismatch` | `unconfigured`.
  A provider no operator config named is `unconfigured`: nothing on the machine
  was looked at for it, and it is a different answer from a missing pinned file.
- `implementation` — a fact about this build's transport:
  `real_experimental` | `fixture_only` | `unproven`. A provider that declares
  none claims `unproven`.

A consumer joins these rows with `/harnesses.json` **by `provider_id`**. A
`display_name` is a label to render and MUST NOT be parsed for any fact.

<!-- CANONICAL:controls_response -->
```json
{
  "instances": [
    {
      "instance_id": "claude-dev", "adapter_id": "claude-code",
      "controls": ["dispatch", "retry", "review", "stop"]
    },
    {
      "instance_id": "codex-review", "adapter_id": "codex",
      "controls": ["dispatch", "retry", "review", "stop"]
    }
  ],
  "providers": [
    {
      "provider_id": "claude-code", "display_name": "Claude Code (fake protocol)",
      "availability": "available", "implementation": "fixture_only",
      "controls": ["dispatch", "evidence", "retry", "review", "stop", "switch"]
    },
    {
      "provider_id": "codex", "display_name": "Codex (fake protocol)",
      "availability": "unconfigured", "implementation": "fixture_only",
      "controls": ["dispatch", "evidence", "retry", "review", "stop", "switch"]
    },
    {
      "provider_id": "deepseek-harness",
      "display_name": "DeepSeek Harness (dsh, headless)",
      "availability": "executable_absent", "implementation": "real_experimental",
      "controls": ["dispatch"]
    },
    {
      "provider_id": "kimi-code",
      "display_name": "Kimi Code (experimental, no proven transport)",
      "availability": "version_mismatch", "implementation": "unproven",
      "controls": []
    }
  ]
}
```

Live observation does not widen the manifest. If observation later proves an
operation temporarily unavailable, C/UI-1 may omit it; it never fabricates a
control the reviewed manifest did not declare.

### 6.3 Run events extend the existing SSE path

- The existing stream is unchanged: `GET /events`, `text/event-stream`, one
  frame on connect and one per broker change, body `data: {"kind":"state"}\n\n`.
  That `{"kind":"state"}` frame MUST keep flowing byte for byte; a v1 consumer
  that understands only it MUST keep working (Protocol v1 tolerant reader; §6.1
  additivity).
- The extension is **additive**: the same `/events` stream MAY additionally emit
  run-event frames whose `kind` is a value other than `state`. `kind` becomes an
  open vocabulary with `state` reserved and `run` added. A consumer MUST ignore
  a frame whose `kind` it does not recognize.
- A run-event frame is a **signal**, exactly like the state frame — it carries
  identifiers only, never a record payload:
  `data: {"kind":"run","run_id":"run-cockpit-001"}\n\n`. On receiving it the UI
  re-reads authoritative bytes from `GET /command/runs/<run_id>` (section 6.1).
  Keeping records out of the SSE frame keeps the stream cheap and keeps any
  record content behind the same read path the contracts validate (and out of a
  place safety law 8 would have to police for secrets).
- This freeze does **not** modify `server.py`; wiring the run-event frame into
  the broker/SSE loop is C/API-1 work on Day 2.

The two frozen JSON frame bodies are:

<!-- CANONICAL:stream_frames -->
```json
[
  { "kind": "state" },
  { "kind": "run", "run_id": "run-cockpit-001" }
]
```

## 7. Field bindings to the CMD-1 contracts — FROZEN CONTRACT

Every durable record payload is a CMD-1 contract by construction. The endpoint
layer adds no record field a contract does not define; it only injects the
server-side fields named below and, for reads, wraps records exactly as
`RunStore` does. Each record body is that contract's `as_dict()`; the injected
fields are:

- `POST …/proposals` → `ActionProposal`: `proposal_id`, `proposed_at`,
  `config_digest`, `schema_version`, and `preview_digest` (derived by the
  contract from the body).
- `POST …/actions` → `ActionRequest`: `action_id`, `requested_at`, `mode`,
  `schema_version` are injected; `attempt_id`, `instance_id`, `capability`,
  `arguments`, `scope`, and `timeout_seconds` are copied unchanged from the
  referenced proposal; `requested_by` comes from `confirmed_by`, the
  idempotency key is derived from proposal id, and the digest comes from both
  the matching proposal and confirmation.
- `POST …/decisions` → `DecisionReceipt`: `decided_at`, `config_digest`, and
  `schema_version`; the client supplies the stable `receipt_id`.
- `GET …/runs/<id>` → `RecoveredRun`: nothing injected — a read-only replay whose
  records are wrapped exactly as the store wraps them,
  `{ "record_type": <kind>, "record": <as_dict> }`.

Invariants this freeze pins, all already enforced by the contracts (so the
endpoint inherits them, never re-encodes them):

- `accepted` (an `ActionRequest`) is a distinct record from `succeeded` (an
  `ActionResultReceipt` with `outcome == "succeeded"`); the API never collapses
  them into one boolean (safety law 9).
- A Human Gate is never `satisfied` without a valid `DecisionReceipt`
  (`gate_decision`); absence is `idle` (ADR 0001 §4).
- Every id, timestamp, scope path, and digest is validated by the contract; a
  malformed value is refused `contract_invalid` (422) at the boundary, never
  stored.
- Unknown top-level fields on a **durable response** survive a tolerant read via
  the contract's `extra` channel. Unknown fields on an HTTP **request** are
  refused before construction; the response-tolerance mechanism is never an
  extra browser mutation surface.

## 8. Out of scope for this freeze — named, not implemented

<!-- CANONICAL:mutation_boundary -->
```json
{
  "routed_now": [
    "validated_command_proposal", "fresh_action_confirmation", "human_decision_receipt"
  ],
  "reserved_after_own_freeze": ["explicitly_confirmed_design_edit"],
  "forbidden": [
    "agent_event", "agent_lane", "adapter_secret", "arbitrary_file", "prompt", "source_file"
  ]
}
```

This is the complete browser-write boundary. A new POST/PUT/PATCH/DELETE route
or a new request field is a contract change, not harmless implementation detail.

- **Design-edit endpoint** (Orbit editor, C/EDIT-1): a permitted *category* in
  safety law 3, but not an implemented or frozen route here. C/EDIT-1 must first
  freeze a target-id-derived destination, schema-valid source, diff, digest,
  expiry, and a separate exact confirmation. It may then add named routes by a
  reviewed additive API freeze; no generic path or file body is allowed.
- **Policy authorization** (A/POL-1): it is a separate Day-3 authority seam.
  This browser confirmation endpoint cannot select Policy mode.
- **Dispatch/review/evidence/stop/retry/switch controls**: capability-derived
  (C/UI-1) and each a `POST …/actions` with the matching `capability`; a control whose bound
  adapter does not declare the capability is **absent**, never a disabled button
  (safety law 10). No separate endpoint shape is frozen for them.

## 9. Executable pins and fixtures

- `tests/test_cockpit_command_api_freeze.py` parses every `<!-- CANONICAL:name -->`
  example from **this file** and pushes it through `contracts.py`
  (`from_dict`/`as_dict`/`canonical_json`), proving the frozen shapes can carry
  every example and that each is already canonical. Expected values are written
  test-locally, so the pin trips if either this document or a contract drifts.
- `tests/fixtures/cockpit_command_csrf_fixtures.json` holds request-shaped
  same-origin/CSRF fixtures (valid same-origin with token, cross-origin,
  missing/stale/foreign/replayed token) for the **pending** Day-2 C/API-1 gate.
  Each request carries a literal presented header; the independent process token
  is top-level fixture state, and provenance is separate metadata. Changing a
  presented value while leaving its provenance label untouched is therefore a
  real mismatch, not a word game. They are data for tests that do not exist yet,
  not a claim that any endpoint passes today. The pin test validates their
  internal accept/refuse relation against the frozen vocabulary above.
  Its hostile transport cases retain ordered raw header pairs and exact body
  bytes (hex-encoded); no fixture pre-normalizes away duplicates.
