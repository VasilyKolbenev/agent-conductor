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
  },
  {
    "method": "POST", "path": "/command/runs/<run_id>/graph",
    "mutation": true, "csrf": true
  },
  {
    "method": "POST", "path": "/command/templates",
    "mutation": true, "csrf": true
  },
  {
    "method": "POST", "path": "/command/runs/<run_id>/graph/from-template",
    "mutation": true, "csrf": true
  },
  {
    "method": "POST", "path": "/command/runs/<run_id>/artifacts",
    "mutation": true, "csrf": true
  },
  {
    "method": "GET", "path": "/command/workflows", "mutation": false, "csrf": false
  },
  {
    "method": "GET", "path": "/command/workflows/<workflow_id>",
    "mutation": false, "csrf": false
  },
  {
    "method": "GET",
    "path": "/command/workflows/<workflow_id>/revisions/<revision>",
    "mutation": false, "csrf": false
  },
  {
    "method": "POST", "path": "/command/workflows/<workflow_id>/draft",
    "mutation": true, "csrf": true
  },
  {
    "method": "POST", "path": "/command/workflows/<workflow_id>/revisions",
    "mutation": true, "csrf": true
  },
  {
    "method": "GET", "path": "/command/runs", "mutation": false, "csrf": false
  },
  {
    "method": "POST", "path": "/command/runs", "mutation": true, "csrf": true
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
  { "code": "record_conflict",       "status": 409, "source": "store" },
  { "code": "draft_changed",         "status": 409, "source": "concurrency" }
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
- `draft_changed` is the one refusal that is about TIMING rather than about the
  request: the workflow draft was replaced between the read a client reviewed
  and the publish it confirmed. It is deliberately not `contract_invalid` --
  the body is well formed and the caller is not at fault -- and deliberately
  not `record_conflict`, which is about a durable identity being reused. A
  client receiving it must re-read the workflow and present the new draft for
  review; retrying the same body is guaranteed to be refused again.
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
  "review": ["work_item_id", "target_artifact_refs", "result_artifact_ref",
    "review_profile"],
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

#### 4.0.1 The pair authority — one verdict for one `(adapter, capability)`

A plan and a proposal describe the same work, so they MUST NOT disagree about
whether that work can be carried out.

**The bound adapter is resolved FIRST, before any question about the
capability.** The run's frozen configuration — never the caller, and never a
union of whatever manifests this process happens to hold — names the adapter
bound to an instance, so an instance that configuration does not declare is
`service_refused` (409) on both routes, carrying the same `{run_id,
instance_id}` detail, whatever capability the request also named. There is no
pair to ask about until the binding exists, and an answer given before it does
is an answer about the build rather than about this run: an empty registry, or
a ghost instance carrying a retired capability, drew two different words that
way.

**Both routes then ask one shared authority, over the triple
`(bound adapter, capability, arguments)`, in this order:**

1. the registry above MUST carry an argument schema for the capability at all;
2. the argument schema the adapter registry recorded for the pair
   `(adapter_id, capability)` MUST be exactly `deep-arguments-v1`, the one
   family this frozen API speaks;
3. `arguments` MUST satisfy that pair's schema through
   `AdapterRegistry.validate_arguments`.

The order IS the taxonomy, and it binds the payload twice over: until steps 1
and 2 have answered, `arguments` MUST NOT be judged **and MUST NOT be rebuilt
into their canonical form** either. An unsupported pair is unsupported whatever
its payload says. Canonicalizing first is how the proposal road came to answer
`contract_invalid` for an unsupported pair while the plan road answered
`capability_unsupported` for the same pair and the same payload.

Steps 1 and 2 are `capability_unsupported` (409):
this build cannot carry out that work at all, whatever the request said, so an
absent schema, a `structured-process-v1` schema, a schema swapped for one
capability of an otherwise conforming adapter, and a capability retired from
the registry above all answer with that one word. Step 3 is `contract_invalid`
(422): the work is servable and these particular values are not.

No refusal at any step writes a proposal or a graph, and none publishes a run
signal.

Asking only half of this was a defect on each route in turn. The plan route
consulted the global registry above and not the pair, so an adapter serving
`dispatch` under another family got an immutable plan it could never execute.
The proposal route consulted only the adapter manifest, so a proposal reached
Confirm through an adapter that had never declared how it reads those
arguments — while the plan describing that very work was refused. And a
capability the registry above does not carry answered `contract_invalid` on one
road and `capability_unsupported` on the other, for one fact about one pair.

### 4.1 `POST /command/runs/<run_id>/proposals` — mint an ActionProposal

Maps to `CommandService.propose`. Refused `service_refused` (409) when the run's
control mode is Observe. The request carries the browser-supplied fields; the
server injects `proposal_id` (minted), `proposed_at` (clock), `config_digest`
(the run's frozen digest), and `schema_version`.

Before anything durable is written, the triple
`(bound adapter, capability, arguments)` MUST pass the pair authority of
section 4.0.1 — the same authority, in the same order and with the same words,
that a plan naming the same work passes at section 4.4. Checking only the
adapter's manifest here let a proposal reach Confirm through an adapter that
had never declared how it reads those arguments.

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

The request has exactly these top-level fields. `adapter_id` and `node_id` are
the optional ones; every other field shown is required. A recursive argument key
named `cmd`, `command`, `script`, `shell`, `argv`, `executable`, `cwd`, `path`,
`env`, or `env_allow` is refused `contract_invalid`, as is any key outside the
selected capability schema.

`adapter_id` is optional; when present it MUST equal the config-bound adapter or
the request is refused `service_refused` (409).

`node_id` is optional and **not nullable**: a caller either omits the key or
names a real node. `null` is refused `contract_invalid`, because two spellings
of "unbound" would make the binding optional to CHECK as well as to carry. It is
absent for every run that follows no graph, and for every action written before
graphs existed — which is why the examples below that omit it are byte-identical
to the ones this spec has always carried. Section 4.3 says what a present one
must agree with. Response `201` — an `ActionProposal.as_dict()`:

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

### 4.3 Graph binding — which node an action carries out

A run may follow one immutable graph (`graph_definition`, section 6). When it
does, a proposal MAY name the node it carries out, and the server holds that
name to the plan rather than taking it on trust:

- the run must follow a graph, and the graph must carry that node;
- the node must declare a capability — a gate decides and does no work, so no
  proposal may claim one;
- the proposal's `instance_id`, `capability` and `arguments` MUST be the node's
  own. These three decide what actually runs, so a binding that let them differ
  would name one step while doing another.

`ActionRequest.node_id` is **inherited from the stored proposal and from nowhere
else**. The Confirm body has no `node_id` field and never will: what a Human
confirmed is the proposal they were shown, binding included, and a body that
could name a node could name a different one. The store holds the same causality
on every road into the journal, including a raw replay. A request that names a
proposal this run holds — found through the frozen `dispatch-<proposal_id>`
idempotency relation — MUST restate that proposal's whole unchanged-proposal
relation of section 4.2, `arguments` among them, and MUST carry its binding
exactly, in both directions. That holds whether or not either document names a
node: an action that runs different work under a confirmed proposal's name is
the same lie in a run that follows no plan. A named node is then re-checked
against the plan itself, and a request that names a node while repeating no
proposal this run holds is refused.

The binding is inside the digests that already exist rather than beside them: it
is part of the proposal body, so it moves `preview_digest`; the request document
carries it, so it moves the request digest every `AttemptEvent` pins; and the
idempotency key names the proposal, which is the document that carries it.
Nothing downstream repeats it — `AttemptEvent`, `ActionResultReceipt` and
`EvidenceRef` reach the node through `action_id`.

A graph-bound propose request:

<!-- CANONICAL:graph_bound_propose_request -->
```json
{
  "instance_id": "claude-dev",
  "attempt_id": "attempt-cockpit-001",
  "capability": "dispatch",
  "arguments": {
    "work_item_id": "work-cockpit-001",
    "instruction_ref": "instruction-cockpit-001",
    "profile": "implement",
    "artifact_refs": [
      "artifact-cockpit-001"
    ],
    "output_limit_profile": "normal"
  },
  "scope": [
    "src",
    "tests"
  ],
  "proposed_by": "claude-dev",
  "rationale": "The lane finished its handoff and asks to dispatch implementation.",
  "timeout_seconds": 900,
  "adapter_id": "claude-code",
  "node_id": "apply"
}
```

The graph it is bound to, as the run's journal holds it:

<!-- CANONICAL:graph_definition_record -->
```json
{
  "record_type": "graph_definition",
  "record": {
    "schema_version": 2,
    "graph_id": "graph-cockpit-001",
    "run_id": "run-cockpit-graph-001",
    "created_at": "2026-08-13T12:00:30Z",
    "nodes": [
      {
        "node_id": "plan",
        "kind": "task",
        "title": "Plan the change",
        "resources": [],
        "stage": "design"
      },
      {
        "node_id": "human-gate",
        "kind": "gate",
        "title": "Human Gate - Confirm Do",
        "resources": [],
        "gate_id": "gate-cockpit-do"
      },
      {
        "node_id": "apply",
        "kind": "task",
        "title": "Do",
        "resources": [
          {
            "kind": "model",
            "name": "sonnet"
          }
        ],
        "stage": "do",
        "instance_id": "claude-dev",
        "capability": "dispatch",
        "arguments": {
          "artifact_refs": [
            "artifact-cockpit-001"
          ],
          "instruction_ref": "instruction-cockpit-001",
          "output_limit_profile": "normal",
          "profile": "implement",
          "work_item_id": "work-cockpit-001"
        }
      },
      {
        "node_id": "retry",
        "kind": "loop",
        "title": "Reopen the work",
        "resources": [],
        "loop": {
          "bound": 2,
          "back_to": "plan"
        }
      }
    ],
    "edges": [
      {
        "from_node": "plan",
        "to_node": "human-gate"
      },
      {
        "from_node": "human-gate",
        "to_node": "apply"
      },
      {
        "from_node": "apply",
        "to_node": "retry"
      }
    ]
  }
}
```

The proposal the server records, with the binding inside its `preview_digest`:

<!-- CANONICAL:graph_bound_action_proposal -->
```json
{
  "schema_version": 2,
  "proposal_id": "proposal-cockpit-graph-001",
  "run_id": "run-cockpit-graph-001",
  "attempt_id": "attempt-cockpit-001",
  "instance_id": "claude-dev",
  "capability": "dispatch",
  "arguments": {
    "work_item_id": "work-cockpit-001",
    "instruction_ref": "instruction-cockpit-001",
    "profile": "implement",
    "artifact_refs": [
      "artifact-cockpit-001"
    ],
    "output_limit_profile": "normal"
  },
  "scope": [
    "src",
    "tests"
  ],
  "proposed_by": "claude-dev",
  "proposed_at": "2026-08-13T12:01:00Z",
  "timeout_seconds": 900,
  "rationale": "The lane finished its handoff and asks to dispatch implementation.",
  "config_digest": "sha256:d37d5ce92fbbfc0e736a215d7dbab9e216837d56c48705b9d5fdefc032fbbbbb",
  "node_id": "apply",
  "preview_digest": "sha256:4a01adccdf78f2bc9533172b0ff2aff8137130cf8319a43a3a5ca72d6f8f58b6"
}
```

And the request a Confirm authorizes from it — same node, inherited:

<!-- CANONICAL:graph_bound_action_request -->
```json
{
  "schema_version": 2,
  "action_id": "action-cockpit-graph-001",
  "run_id": "run-cockpit-graph-001",
  "attempt_id": "attempt-cockpit-001",
  "instance_id": "claude-dev",
  "capability": "dispatch",
  "arguments": {
    "work_item_id": "work-cockpit-001",
    "instruction_ref": "instruction-cockpit-001",
    "profile": "implement",
    "artifact_refs": [
      "artifact-cockpit-001"
    ],
    "output_limit_profile": "normal"
  },
  "scope": [
    "src",
    "tests"
  ],
  "requested_by": "release-owner",
  "requested_at": "2026-08-13T12:02:00Z",
  "idempotency_key": "dispatch-proposal-cockpit-graph-001",
  "timeout_seconds": 900,
  "preview_digest": "sha256:4a01adccdf78f2bc9533172b0ff2aff8137130cf8319a43a3a5ca72d6f8f58b6",
  "mode": "confirm",
  "node_id": "apply"
}
```

### 4.4 `POST /command/runs/<run_id>/graph` — write the one graph a run follows

Maps to `RunStore.append(GraphDefinition)`. A run follows at most one graph and
never edits it: editing, versioning, templates and a run list are a later
slice, so the only write this route performs is a run's first one.

The browser supplies the stable `graph_id` and the plan — `nodes` and `edges` —
and nothing else. The server injects `run_id` from the path, `created_at` from
its clock, and `schema_version`. No caller controls a timestamp, a record
wrapper, or the run this graph belongs to. The body is closed to exactly
`graph_id`, `nodes`, and `edges`; any other field, `run_id` and `created_at`
among them, is `contract_invalid` (422).

<!-- CANONICAL:graph_request -->
```json
{
  "graph_id": "graph-cockpit-001",
  "nodes": [
    { "node_id": "plan", "kind": "task", "title": "Plan the change",
      "stage": "design", "resources": [] },
    { "node_id": "human-gate", "kind": "gate", "title": "Human Gate - Confirm Do",
      "gate_id": "gate-cockpit-do", "resources": [] },
    { "node_id": "apply", "kind": "task", "title": "Do", "stage": "do",
      "instance_id": "claude-dev", "capability": "dispatch",
      "arguments": {
        "work_item_id": "work-cockpit-001",
        "instruction_ref": "instruction-cockpit-001",
        "profile": "implement", "artifact_refs": ["artifact-cockpit-001"],
        "output_limit_profile": "normal" },
      "resources": [{ "kind": "model", "name": "sonnet" }] },
    { "node_id": "retry", "kind": "loop", "title": "Reopen the work",
      "loop": { "bound": 2, "back_to": "plan" }, "resources": [] }
  ],
  "edges": [
    { "from_node": "plan", "to_node": "human-gate" },
    { "from_node": "human-gate", "to_node": "apply" },
    { "from_node": "apply", "to_node": "retry" }
  ]
}
```

Every bound node is held to this build and this run before the plan is durable:

- the `instance_id` MUST be one the run's frozen configuration declares, and
  that configuration — never the caller — names the adapter bound to it;
- the triple `(bound adapter, capability, arguments)` MUST pass the pair
  authority of section 4.0.1, which is the same authority a proposal passes,
  with the same order and the same words.

A node that names no binding does no work and is held to neither.

The pair matters, not the capability alone. A capability name is shared; the
payload family behind it is the adapter's. Judging a plan against the global
schema registry accepted graphs an adapter could never execute — the route
answered `201`, the first proposal against that node answered
`service_refused`, and the immutable plan stood in the journal with no way to
edit or remove it.

That last rule is not tidiness. A graph is **immutable**: a plan that reaches
the journal can never be edited or removed, so a payload admitted here is
admitted forever. Without the schema this route accepted any JSON object, which
put arbitrary caller text — a credential, an absolute path, an environment
name — into a durable record and onto every subsequent read, and produced plans
whose every proposal the propose door would then refuse. Every field of every
argument schema is a closed id or a closed vocabulary word, so the schema call
IS the screen: an unknown field, a path, a secret, or a value outside a
vocabulary is refused `contract_invalid` (422) with **zero durable bytes**, and
the refusal carries the fixed detached message with no submitted text in it.

The **default Dalio template ships as a plan that passes these schemas** — a
canonical graph the product could not execute would not be a default.

Three outcomes, and no fourth. The order they are decided in is part of the
contract: the standing graph is looked for FIRST, inside the transaction,
before the clock, the registry, or the frozen configuration is consulted at
all.

- **`200`** — a graph already stands and this request restates it exactly. The
  response is the stored `GraphDefinition.as_dict()`, byte for byte, including
  the `created_at` the first write settled. Nothing is appended and nothing is
  published. This answer MUST NOT depend on the registry, the adapters, or the
  frozen configuration: the record is already durable, and a client whose reply
  was lost is entitled to the same answer from a process that starts with a
  different registry. The stable `graph_id` is what makes the retry findable,
  exactly as `receipt_id` does for a decision (5.1).
- **`record_conflict` (409)** — a graph already stands and this request does
  not restate it: the same `graph_id` carrying different facts, or a second
  `graph_id` entirely. Two graphs under two identities would leave every reader
  to guess which plan the run follows, so the refusal names the graph standing.
  This answer, too, consults no registry.
- **`201`** — no graph stands. Only THIS path validates the plan against the
  configuration, the registry and the argument schemas, reads the clock, and
  appends.

This route is a mutation like any other: it passes the Host allowlist,
same-origin and anti-CSRF checks (sections 1 and 2) and the writable-route
containment/ownership gate before any durable effect, and on a `201` it
publishes the same identifier-only run frame (section 6.3).

The containment gate is checked twice — once before the store is opened and
once again inside the transaction, because a route can be made unsafe between
the two. **The second check MUST answer `route_unsafe` (409) like the first.**
It did not: a refusal is a frozen value, and the generator-based transaction
assigns `__traceback__` to an exception on its way out, which a frozen value
refuses — so the second check produced an untranslatable crash instead of the
one closed envelope this surface promises. A refusal now travels as an
exception while its three reviewed fields stay read-only. This applies to every
mutating route, all of which re-check containment under the same lock.

### 4.5 `POST /command/templates` — publish one immutable template revision

Maps to `TemplateStore.save(GraphTemplate)`. §4.4 said editing, versioning and
templates were a later slice; this is that slice, and it takes only the part
that can be frozen honestly. A published revision can be **read and listed** —
`GET /command/workflows`, `GET /command/workflows/<workflow_id>` and
`GET /command/workflows/<workflow_id>/revisions/<revision>` answer, and a draft
may be saved and replaced under its own name. What remains impossible, and
always will be, is **updating or deleting a published revision**: a revision is
an identity, and a surface that could rewrite one would contradict the promise
every other part of this contract is built on. Publishing goes through
`POST /command/workflows/<workflow_id>/revisions`, which carries the expected
next revision number so two editors cannot silently overwrite each other's
intent; `POST /command/templates` is unchanged.

The body is the canonical `GraphTemplate` document and nothing else — closed to
exactly `schema_version`, `template_id`, `revision`, `title`, `nodes` and
`edges`. Any other field is `contract_invalid` (422), `run_id` and `created_at`
among them: a template belongs to no run and carries no timestamp. It is read
through the same `GraphTemplate.from_dict` an operator's own file goes through,
so what a client publishes is held to the contract rather than trusted for
having arrived over the wire.

A template names ROLES and no deployment. `graph_template.DEPLOYMENT_ONLY_FIELDS`
is the vocabulary that would pin a plan to one machine, and the document is
closed at every level, so a `provider_id`, an `instance_id` or an `adapter`
arriving anywhere inside it is refused as the unknown key it is.

<!-- CANONICAL:template_request -->
```json
{
  "schema_version": 1,
  "template_id": "template-dalio",
  "revision": 1,
  "title": "Dalio five-step cycle",
  "nodes": [
    { "node_id": "goal", "kind": "task", "title": "Goal", "stage": "goal",
      "role_id": "role-thinker", "capability": "review",
      "arguments": { "work_item_id": "work-001",
                     "target_artifact_refs": ["artifact-brief"],
                     "result_artifact_ref": "artifact-goal",
                     "review_profile": "spec" },
      "resources": [] },
    { "node_id": "confirm-gate", "kind": "gate",
      "title": "Human Gate - Confirm Do", "gate_id": "gate-confirm-do",
      "resources": [] }
  ],
  "edges": [ { "from_node": "goal", "to_node": "confirm-gate" } ]
}
```

Three outcomes, and no fourth.

- **`201`** — this revision did not exist and now does. The response is the
  stored document, byte for byte.
- **`200`** — this revision exists and this request restates it EXACTLY. Nothing
  is written. A client whose reply was lost is entitled to the same answer, so
  this outcome depends on the stored bytes and on nothing else — no registry, no
  configuration, no clock.
- **`record_conflict` (409)** — this revision exists and says something else. An
  edit is a new revision; two plans may not wear one identity.

No run is published, because no run is involved: this route emits **no SSE frame
at all**, on any of the three outcomes.

The store writes through the containment/ownership gate like every other durable
write, judged with `lstat` and following nothing, over every directory it writes
through and the leaf it writes at. A portal or a second hard link answers
`route_unsafe` (409) and the refusal names the KIND and never the path — the
location is this server's directory layout, which is not the caller's to learn.

### 4.6 `POST /command/runs/<run_id>/graph/from-template` — materialize one plan

Maps to `graph_template.materialize` followed by `RunStore.append(GraphDefinition)`.
The run still follows exactly one graph and still never edits it; this route
differs from §4.4 only in how the plan is DESCRIBED. §4.4's body stays closed
and byte-compatible: a plan given as nodes and a plan given as a template are
two closed documents, not one document with two shapes.

The body is closed to exactly `graph_id`, `template_id`, `revision` and
`assignments`. The client supplies the stable `graph_id` — that is what makes a
retry findable, exactly as in §4.4 — plus the immutable revision to materialize
and the `RunBinding` mapping each role to a configured `instance_id`. The server
injects `run_id` from the path, `created_at` from its clock, and
`schema_version`. Any other field, `created_at` and `nodes` among them, is
`contract_invalid` (422).

<!-- CANONICAL:graph_from_template_request -->
```json
{
  "graph_id": "graph-cockpit-002",
  "template_id": "template-dalio",
  "revision": 1,
  "assignments": {
    "role-thinker": "codex-review",
    "role-diagnostician": "codex-review",
    "role-designer": "codex-review",
    "role-implementer": "claude-dev"
  }
}
```

Materialization is performed by the production constructor and by nothing else.
The endpoint does not assemble a `GraphDefinition` field by field, and there is
no second path that builds one: the plan a run follows through this route is the
plan `materialize` produces from the stored revision and the supplied binding,
or there is no plan.

**This route decides nothing by a provider's identity.** It compares no vendor
id, reads no harness name, and branches on no product. Which adapter drives an
instance is the run's FROZEN configuration's fact; whether that adapter can be
reached is a STATE, `availability`, carried in its own closed vocabulary beside
the identity and never derived from it. A binding to an unreachable provider and
a binding to a provider this build never heard of are refused by the same rule,
in the same words, and neither refusal knows which product it was.

Every binding pair is judged before one durable byte, in this order:

1. the binding covers exactly the template's roles, and every assigned instance
   is one the run's frozen configuration declares;
2. the adapter that configuration binds the instance to is **available**, read
   from the reviewed provider descriptors this API was given and projected
   through `provider_projection` — the one authority on that question, never a
   name and never a second table;
3. the pair — adapter and capability — serves that capability through the one
   argument-schema family this API speaks, and the materialized payload
   satisfies that pair's schema, through the registry's own door, the same one
   `CommandService.propose` calls.

Step 2 is this route's rule and **not** §4.4's. That route was frozen without
an availability check and stays byte-compatible: adding a refusal to a surface a
client already depends on is a change of behaviour however good the reason. The
two roads write the same record by different rights, and this one may ask
because it is new and this contract says so.

Steps 2 and 3 are `service_refused` and `capability_unsupported` respectively,
and step 1's missing instance is `service_refused`; a payload that is servable
and invalid is `contract_invalid`. **No refusal at any step writes a record or
publishes a signal.** These two routes introduce no error code: every outcome is
already in the frozen vocabulary of section 3.3.

Three outcomes, and no fourth. The order they are decided in is part of the
contract, and it is §4.4's order for §4.4's reason: the standing graph is looked
for FIRST, inside the transaction, before the clock, the registry, the provider
descriptors or the frozen configuration is consulted at all.

- **`200`** — a graph already stands and this request restates it exactly. The
  response is the stored `GraphDefinition.as_dict()`, including the `created_at`
  the first write settled, and the candidate it is compared against is
  re-materialized on THAT `created_at` — the caller never supplied one, so
  comparing anything else would call every honest retry a conflict. This answer
  MUST NOT depend on the registry, the provider descriptors or the frozen
  configuration: a client whose reply was lost is entitled to the same answer
  from a process that starts with a different registry, or with none.
- **`record_conflict` (409)** — a graph already stands and this request does not
  restate it. Also this code when the same `graph_id` would carry different
  facts, or a second `graph_id` entirely.
- **`201`** — no graph stands. Only THIS path reads the stored revision, judges
  availability and the pairs, reads the clock, and appends.

A revision this store does not hold is `service_refused` (409): it is a fact
about what this build has, like a frozen configuration that declares no
instance, and the refusal names the template and the revision and no path.

`created_at` is minted INSIDE the transaction, from the server's clock, on the
`201` path only. A retry answers with the durable timestamp rather than a second
one: a record's identity may not depend on when somebody asked about it twice.

One new append publishes exactly one identifier-only run frame (section 6.3). A
`200` retry and every refusal publish **zero** frames — a signal is a claim that
something changed, and on those paths nothing did.

This route is a mutation like any other: Host allowlist, same-origin, anti-CSRF
and the writable-route containment/ownership gate before any durable effect,
with the gate re-checked inside the transaction and answering `route_unsafe`
(409) both times.

### 4.7 `POST /command/runs/<run_id>/artifacts` — publish immutable handoff text

Maps to `RunStore.append(ArtifactDocument)`. This is the one durable content
door the `review` capability was waiting for: a `target_artifact_refs` value is
an identifier, not the thing to review, and no adapter may turn an identifier
into content by guessing a path or reading a caller-controlled URI.
`result_artifact_ref` names where that review publishes its own immutable
answer. It is explicit in the graph rather than derived from a stage, node or
provider name, so a user-edited cycle keeps its handoffs without a naming
convention hidden in runtime code.

The request is closed to exactly `artifact_id`, `artifact_ref`, `media_type` and
`content`. The server injects `run_id` from the path and `created_at` from its
clock. `source_action_id` is server-owned and absent on this operator-publish
road; a later runtime-produced artifact carries the action that produced it.
That produced document also carries `input_artifact_ids`: the exact immutable
documents the action read, in requested order. Neither server-owned field is
accepted from this route. Thus an output says which bytes led to it even after
a newer document is appended under the same logical reference.
The two admitted media types are `text/plain` and `text/markdown`. Content is
non-empty UTF-8 text, carries no NUL, and is bounded to 49,152 encoded bytes.
The command transport independently bounds the complete encoded JSON request to
65,536 bytes; both limits must pass, because JSON escaping can make its wire
spelling longer than the decoded text it carries.

<!-- CANONICAL:artifact_request -->
```json
{
  "artifact_id": "artifact-document-001",
  "artifact_ref": "artifact-brief",
  "media_type": "text/markdown",
  "content": "# Goal\nBuild the smallest releasable alpha without weakening its gates."
}
```

A logical `artifact_ref` may have several immutable documents over a bounded
loop. Consumers resolve the latest one in append order and receive its exact
content plus its computed digest; they never receive a filesystem path. The
record's `artifact_id` is its immutable identity. Thus a retry of the same id
and facts returns `200`, while the same id with different content is
`record_conflict` (409). A new document returns `201` and exactly one
identifier-only run frame; a retry and every refusal emit none.

The digest is computed from the canonical `ArtifactDocument` and is not stored
beside it. A stored digest could disagree with the content it purported to
name. The existing run read returns the document as an append-ordered
`record_type: "artifact"` row; SSE carries only `kind` and `run_id` as before.

An artifact is deliberately durable and visible through the authenticated
loopback run read. This route is not a redaction service: text submitted here is
an explicit request to retain and hand it to later roles. Raw harness stdout,
stderr, environment values and arbitrary files never enter through it.

The runtime-produced review road is narrower than the operator route and does
not make raw process output a general record source. The bound adapter must
declare `review`, resolve every requested immutable document before the task
spawn, and use a task channel that keeps those bytes out of argv. The reviewed
Claude road pins its vendor's read-only `plan` permission mode and independently
requires the authorized work tree to remain unchanged. Only a completed,
exit-zero, fully delivered, non-truncated stdout text answer is decoded as UTF-8
and admitted as the output `ArtifactDocument`. Stderr is separately drained and
bounded but is never artifact content; partial output, invalid text, empty text,
NUL, a changed tree, a missing input, and every failed process produce no output
artifact and no verification evidence.

Every non-empty value admitted through the operator-pinned `env_allow` names is
treated as sensitive on this value-producing road. If stdout repeats any such
value, the output is refused before an artifact or evidence row exists. The
runner retains only the boolean that a match occurred: the matched environment
value is never copied into an outcome, refusal, journal record, API response or
SSE frame.

On that road the runtime appends the output artifact only after the durable
`execution_observed` event, then appends one verified `EvidenceRef` whose digest
equals the computed artifact digest. Only that causal pair may let the terminal
`ActionResultReceipt` say `succeeded`. Dispatch follows the same law for an
actual contained tree change: its evidence digest covers the action identity,
the exact input artifact identities and the before/after hashes of every changed
path. Exit zero with no change still proves nothing and remains
`verification_failed`.

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
the replay warning list. A fifth key, `graph`, is described in 6.1.1 and is the
only part of this response that is not a durable record verbatim. A missing run
is currently `store_error` (500), because
the planning-base store has no typed not-found branch and the endpoint may not
infer one from prose. The record kinds and their contracts are the closed v2 vocabulary:
`action_request` (`ActionRequest`), `action_result` (`ActionResultReceipt`),
`evidence` (`EvidenceRef`), `decision` (`DecisionReceipt`),
`action_proposal` (`ActionProposal`), `adapter_observation` (`ObservationRecord`),
`attempt_event` (`AttemptEvent`), `graph_definition` (`GraphDefinition`), and
`artifact` (`ArtifactDocument`). One run follows at most one graph, and a second
under another id is refused.

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
  "warnings": [],
  "graph": { "definition": null, "definition_digest": null, "runtime": null }
}
```

This run follows no graph, and says so with three nulls rather than an absent
key: a reader that has to tell "no graph" from "old server" by the shape of a
response is a reader guessing.

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

#### 6.1.1 `graph` — the plan, its digest, and what the run did with it

`graph` carries exactly three keys and is present on every run read:

- `definition` — the `graph_definition` record's body verbatim, the same object
  `records` already carries. It is repeated here so a reader has the plan and
  the run's position side by side without rebuilding the join itself.
- `definition_digest` — `GraphDefinition.digest()`, **computed over that
  document and never stored beside it**. A digest of oneself that is written
  down can come to disagree with oneself.
- `runtime` — what this run was observed to do, **computed from the durable
  records and held nowhere else**. It is not a record, it is never appended,
  and no route writes it. A second mutable copy of a run's position would be a
  copy that can disagree with the journal it was copied from.

A run following no graph answers `null` for all three.

The projection and the definition share no word but the join. Every name a
`runtime` node carries is a name the definition REFUSES as a field
(`graph_definition.RUNTIME_ONLY_FIELDS`), so a ceiling and a position can never
be read as each other: `loop.bound` is the plan's, `pass` is the run's.

`phase`, `outcome`, `observed_at` and `evidence_refs` describe the node's
**current** action and no earlier one. The current action is the LAST document
in append order that binds this node — a proposal or a request — so a node
whose finished attempt is followed by a new proposal reads `proposed`, not
`observed`. A projection that aggregated a node's whole history would show a
green finished step while its next attempt was already being confirmed, which
is the one reading a Cockpit must never offer.

- `phase` — how far the current action's records carry it, one of `idle`,
  `proposed`, `requested`, `running`, `observed`, and never one step further.
  `observed` means an execution boundary was reached; it is NOT success
  (safety law 9).
- `outcome` — the current action's `ActionResultReceipt` outcome and **nothing
  else**. An attempt event carries an outcome of its own, and reading it here
  would let a watched process exit stand in for the immutable result a product
  success requires. No result for the current action, `null` — including when
  an earlier attempt on the same node succeeded.
- `attempt_ids` — every attempt this node was ever asked to carry out, sorted.
  This one IS the whole history, and it is the join to `records`: result
  receipts and attempt events name it, so a reader who wants an earlier
  attempt has the key to find it.
- `evidence_refs` and `observed_at` — identifiers and a timestamp from the
  current action's result receipts, never a previous attempt's. Never a URI, a
  label, a digest, or an exit code: those stay in `records`, where a contract
  validated them.
- `decision` — gate nodes only. `contracts.gate_decision`'s own answer: `idle`,
  `satisfied`, `failed`, `changes_requested`, or `waived`. A run holding more
  than one standing decision for one gate is `unknown`: the journal supports
  two answers, so it supports neither, and this projection does not choose.
- `pass` and `bound_reached` — loop nodes only. `pass` counts the distinct
  attempts recorded on the one node the loop reopens, its `back_to`. That step
  is attempted exactly once per trip, so its attempt count IS the trip the run
  is on, with no arithmetic invented on top of a durable fact. Work on the
  cycle's other steps is work done ON a pass and never evidence of another one,
  and a `back_to` nothing has attempted is `pass` 0: the loop has sent nothing
  around. `bound_reached` is `pass >= loop.bound`, so `bound` is the greatest
  pass the work may reach.

An action that names no node is projected nowhere: a graph does not make every
action part of it. A run whose journal does not replay has no projection at
all — the read refuses `run_corrupt` (409) rather than answering with a partial
one. The run's own phase is not restated here; it is `run.status`.

For the graph, proposal and request of section 4.3:

<!-- CANONICAL:graph_runtime_projection -->
```json
{
  "run_id": "run-cockpit-graph-001",
  "graph_id": "graph-cockpit-001",
  "nodes": [
    { "node_id": "plan", "phase": "idle", "attempt_ids": [],
      "outcome": null, "observed_at": null, "evidence_refs": [] },
    { "node_id": "human-gate", "phase": "idle", "attempt_ids": [],
      "outcome": null, "observed_at": null, "evidence_refs": [],
      "decision": "idle" },
    { "node_id": "apply", "phase": "requested",
      "attempt_ids": ["attempt-cockpit-001"],
      "outcome": null, "observed_at": null, "evidence_refs": [] },
    { "node_id": "retry", "phase": "idle", "attempt_ids": [],
      "outcome": null, "observed_at": null, "evidence_refs": [],
      "pass": 0, "bound_reached": false }
  ]
}
```

`apply` is `requested` and its `outcome` is `null`: a Human confirmed the work
and nothing has reported on it. `human-gate` is `idle` because no receipt
stands, never because a gate was assumed to pass. `retry` is on pass 0 against
a bound of two: the loop reopens `plan`, no attempt names `plan`, and the one
attempt this journal holds is `apply`'s — work on the way there, not a trip
around.

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

An `instances` row carries a third deployment fact: **`model`**, the model id
this run's frozen configuration pins for that instance, or `null` when it pins
none. It sits beside `adapter_id` because it is the same KIND of fact — what the
configuration says about a deployment — and it appears in no graph document,
where a plan names roles and never a machine.

`null` is not a default and MUST NOT be rendered as one. It says this build
chose no model for that instance, so what runs is whatever the provider's own
configuration decides; a consumer that printed a model name there would be
inventing the one fact the field exists to report. A consumer MUST NOT parse the
id for a vendor, a family or a size — it is an identifier to display and to join
on, exactly like `adapter_id`.

The example below exercises every value of both vocabularies, which is why its
last row is **illustrative and names no shipped product**: the alpha execution
roster carries no `unproven` row, because a catalogued row means this build can
describe *and* constructively serve that provider. `unproven` remains in the
vocabulary as the claim a row makes when it declares no implementation at all,
so a consumer MUST still be able to render it. Every other row in the example is
a provider this build really catalogues. Its two instance rows exercise both
states of `model` for the same reason.

<!-- CANONICAL:controls_response -->
```json
{
  "instances": [
    {
      "instance_id": "claude-dev", "adapter_id": "claude-code",
      "model": "claude-opus-5",
      "controls": ["dispatch", "retry", "review", "stop"]
    },
    {
      "instance_id": "codex-review", "adapter_id": "codex",
      "model": null,
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
      "provider_id": "grok-build",
      "display_name": "Grok Build (headless, experimental)",
      "availability": "unconfigured", "implementation": "real_experimental",
      "controls": ["dispatch"]
    },
    {
      "provider_id": "kimi-code",
      "display_name": "Kimi Code (headless, experimental)",
      "availability": "version_mismatch", "implementation": "real_experimental",
      "controls": ["dispatch"]
    },
    {
      "provider_id": "some-future-provider",
      "display_name": "A Provider With No Proven Transport",
      "availability": "unconfigured", "implementation": "unproven",
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
  Every mutating route publishes this one frame, and only when it appended a
  durable record: a request that changed nothing signals nothing, and a route
  that appended something signals it in exactly the same words as every other.
  The graph route (4.4) is no exception, and the graph a run follows reaches a
  browser only through the authoritative read — never through the stream.
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
- `POST …/graph` → `GraphDefinition`: `run_id`, `created_at`, and
  `schema_version`; the client supplies the stable `graph_id` and the plan.
- `GET …/runs/<id>` → `RecoveredRun`: nothing injected — a read-only replay whose
  records are wrapped exactly as the store wraps them,
  `{ "record_type": <kind>, "record": <as_dict> }`. Its `graph` key adds no
  record field either: `definition` is a record body verbatim, and
  `definition_digest` and `runtime` are computed from records the response
  already carries (6.1.1).

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
