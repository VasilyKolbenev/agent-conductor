# Account quota observations — backend foundation, 21 September 2026

## Native subscription integration addendum

The later subscription slice adds `SessionContext`, a separate internal
account-unknown subject for native quota readers. `CredentialContext` remains
balance-only. Both contexts are random collector-lifetime handles, never an
email, alias, home path, token digest or account ID. They do not group or sum
different bindings. Existing generation tickets, rebind rejection, TTL and
clock-regression rules apply unchanged. HTTP continues to omit the internal
connection and returns `account: null`, `account_status: unknown`.

The Codex supplier uses the dispatch adapter's exact executable, constructor
environment allowlist, forced environment and pinned subscription `auth_home`.
It shares the existing workspace turn and spawn/cleanup road, including version
check, login-home configuration refusal, credential echo checks and residue
checks. API-key mode has no subscription reader. Account metadata is used only
to establish the native subscription authentication method and is not exposed.
Pinned 0.112.0 does not provide a native account ID in `account/read`.

`NativeQuotaReader` is a private trusted supplier value, consumed only by the
server-owned serial collector. It changes no public command, grant or provider
configuration shape. The collector publishes native windows or a closed error;
a new error replaces prior successful values. GET remains cache-only. A read that
cannot take the harness root within its bounded wait (a step holds it) is
deferred, not failed: nothing is published, and the binding records `deferred_at`
(Codex ruling J, 23 September 2026).

The finite app-server metadata batch contains initialize, initialized,
account/read with refreshToken false, and account/rateLimits/read. The existing
ProcessRunner can hold stdin until a bounded, complete final stdout response
arrives, then send EOF. This was necessary: immediate EOF on the pinned native
binary returned only initialization. The completion marker is not validation:
the provider additionally requires all exact response IDs, unambiguous replies
and subscription authentication. Stderr cannot release the wait. Invalid JSON,
bounded-output overflow, missing response, timeout, interruption or native
error never becomes observed quota facts. The 15-second process deadline and
existing owned process-group retirement apply.

Native empty-profile calibration proves the local protocol and shutdown, not
real account quota, external network isolation or all four subscription
integrations. No real credentials, login, model turn or paid inference were
used. Native rate-limit collection may refresh its own managed login; the
product does not claim that refreshToken false suppresses native refresh on
the separate rate-limit call.

The original foundation scope below remains historical; the later DSH and
native reader additions do not retroactively make its tests live acceptance.

This slice does **not** close the V1 quota release gate. It supplies strict value
contracts, native reply parsers, an in-memory latest-observation service and a
cache-only HTTP read. There are no live collectors, account probes, polling or UI wiring.
No account credentials are accessed. Native
protocol compatibility with this product's pinned harness versions remains to
be verified before connecting collectors. ProviderConfig, authentication modes,
frozen run bindings and execution authority are unchanged.

## Cache-only HTTP read

`GET /command/quotas` returns exactly `as_of` (the server clock in UTC ISO form),
`max_age_seconds` (300 by default), `providers` (the existing reviewed provider
projection) and `snapshots`. `CommandApi` optionally receives a `QuotaService`
and a positive `quota_max_age`; its default is a new empty cache. The route
never creates a collector, reads credentials, resolves providers, starts an
adapter, touches a run, refreshes the cache or performs network I/O.

Every supplied catalog contract contributes its `provider_id` as a cache
binding id, including unconfigured providers. Cache bindings absent from that
provided catalog are not exposed. An unbound provider is an individual
`state: missing`, `reason: no_data`, `freshness: missing` row, with no invented
account, source, window, usage or reset. Source facts come from cached readings,
never from a display label. A confirmed account/source can group several
selected binding ids; percentages and monetary amounts are never summed.

Snapshots preserve cached `binding_ids`, `account`, `source.kind/version`,
`observed_at`, `state`, `reason`, windows and their reset/freshness fields.
Freshness is reconstructed at each read using the current server clock; elapsed
TTL, a passed reset or clock rollback makes observations stale without
resetting usage. A window whose own reset has passed carries `freshness:
reset_passed` (the others `current` or `stale`): its figures are kept as facts but
are not a current remainder, and Studio does not show them as one. Every row also
carries `deferred_at` (UTC instant or null): the last time a collector update for
that binding generation was deferred because a step held the harness root. The
observation beside it keeps its own `observed_at`, age and resets; a completed
read, a rebinding, an unbind or a retirement clears it, and an unbound row never
has one. Decimal DSH `balances`, currencies, native `is_available` and
`reset_applicability: not_applicable` remain distinct from subscription windows.

The HTTP projection deliberately differs from the internal cache value: it
omits `connection` entirely, including the context UUID, and adds
`account_status: unknown` when `account` is null (`verified` otherwise).
Separate unknown contexts remain separate rows, identified only by their
binding ids, even when their monetary readings are equal. No context UUID or
private `NativeQuotaConnection` becomes an account claim or a browser field.

The exact Host guard and existing bounded framing rules apply. Only the exact
path is served; query strings, even a bare `?`, fragments, trailing path
components and `/refresh` are refused. All other verbs, including POST, return
`method_not_allowed`; there is no mutation, refresh or selection body. GET
rejects a supplied body, nonzero Content-Length, duplicate Content-Length and
Transfer-Encoding. An explicit valid zero Content-Length is bodyless. Responses
use the server's existing no-store JSON headers. A malformed reconstructed
cache value receives the closed `service_refused` envelope without raw prose.

Real collectors, server-owned scheduling and UI remain separate integration
work; this read surface does not close the V1 requirement for real observations.

## Collector API

`conductor.command.quota` holds immutable `AccountIdentity`, `QuotaSource`,
`QuotaWindow`, `QuotaObservation`, balance contracts, generic `parse_observation`
and failure constructors. Native parsers and their `QUOTA_POLICY` declarations
belong to the five existing provider modules: `adapters/codex_cli.py`,
`claude_code.py`, `kimi_code.py`, `grok_build.py` and `dsh_harness.py`.
`adapters/quota_contracts.py` supplies provider-neutral decoded inputs and a
parameterized keyed-window helper. It has only SDK-allowed value imports.
No provider registry, provider-name branch or SDK import exemption is needed.
The core reconstructs policies and revalidates every decoded field, including
objects claimed to be frozen. Providers own accepted identity sources, native
field names, timestamp encoding, observation kind and supported currencies;
the core owns exact decimal and datetime conversion and generic value bounds.
The native parser stamps each decoded reading with its own module-owned policy;
the core requires that stamp to match the requested policy. Renaming the policy
around another provider's parser therefore cannot relabel its native facts.
This is a trusted-code seam, not a cryptographic authentication or HTTP boundary.
`conductor.command.quota_service.QuotaService` owns collection bindings and
latest observations. A collector performs the following bounded sequence:

1. Establish the native billing account through the harness's supported account
   interface. Construct `AccountIdentity.from_verified_native_id(policy, ...)`, choosing
   the named native identity source. This is a **trusted collector boundary**,
   not a proof verifier: never expose it as an API accepting a browser's claim
   that an alias is a verified account. Raw native ids are hashed with the vendor
   namespace; they are not carried into snapshots. A hash is not anonymization.
   The verified native id must identify the complete billing scope, including
   region/workspace where the vendor scopes ids that way. If the native interface
   cannot establish that identity, the collector must not bind an alias instead.
2. Call `service.bind(binding_id, account, QuotaSource(policy, native_version))` and
   retain the returned generation ticket. The binding id is an internal handle,
   never evidence that two accounts are the same. Rebind when authentication or
   the pinned source changes. Every rebind invalidates earlier in-flight tickets.
3. Read the quota through that same native account context. Pass the decoded
   reply to `parse_observation(payload, policy=QUOTA_POLICY, ...)`, with the verified account, exact source
   version and an aware `observed_at`. Never put raw logs or credentials here.
   Codex/Grok parsers take the method result, not the JSON-RPC envelope. Kimi
   takes the complete REST response envelope. Claude takes the statusline JSON.
4. On transport/auth/schema failure, construct `failed_observation` with a closed
   reason code. Never include an upstream message: it may contain secrets.
5. `publish(ticket, observation, now=...)` validates and copies the observation.
   It rejects a mismatched account/source or future timestamp; it returns false
   for an obsolete ticket, older sample or differing sample at the same time.
   An identical same-time replay succeeds. Collectors must retain the sample
   timestamp, not relabel an old reply as newly observed when retrying publish.
   Each publication replaces that account/source's complete supported snapshot;
   a partial change notification must trigger a full read or be assembled by the
   collector under its native protocol before it is published.
6. Read `snapshot(binding_id, now=..., max_age=timedelta(...))`, or `snapshots`
   for multiple bindings. Reads never poll, spawn, mutate or refresh authority.

An error supersedes older success, and a deferral never brings an older success
back over a newer error. A success containing no supported numeric or
reset facts is `unavailable`; an unobserved binding is `missing`. Null is never
zero. Reset without percent, or percent without reset, remains partial and keeps
the missing field null. Freshness expires at the configured age or when a
window's reported reset is reached. Usage is never automatically reset to zero.
Clock rollback also makes a retained observation stale. When one window expires,
the snapshot is stale and each window exposes its individual freshness.

Grouping uses `(vendor, confirmed account digest, source kind)`; windows within
it use `(limit_id, window_id)`. Aliases never merge accounts. Multiple participants
on one confirmed account/source get one shared snapshot, not summed capacity.
Source version is recorded on each observation, not used to multiply an account.
Cross-source account equivalence is not inferred. No snapshot authorizes,
reassigns, stops or resumes a run, buys credits or consumes reset credits.

## Official source shapes checked on 21 September

- [Codex App Server](https://learn.chatgpt.com/docs/app-server#auth-endpoints):
  `account/rateLimits/read` result; prefer `rateLimitsByLimitId` when non-null,
  including an explicitly empty map. Otherwise use legacy `rateLimits`, whose
  missing/null `limitId` denotes the legacy Codex bucket. Native `primary` and
  `secondary` carry `usedPercent`, `windowDurationMins`, Unix-second `resetsAt`.
- [Claude Code statusline](https://code.claude.com/docs/en/statusline):
  subscription `rate_limits.five_hour`/`seven_day` with `used_percentage` and
  Unix-second `resets_at`. `spend_limit` is a different monetary policy and is
  deliberately excluded. Data may be absent until after a model response; a
  compatible headless collection mechanism is still unproven here.
- [Kimi local server API](https://github.com/MoonshotAI/kimi-code/blob/main/docs/en/reference/server-api.md):
  `GET /api/v1/oauth/usage`, envelope `code` plus `data.kind`; a nonzero code or
  `kind: error` is an error even on HTTP200. `quota.usages` contains the optional
  `limit5h`, `limit7d`, `monthTotal`, `monthCode` windows, `usedRatio` and RFC3339
  `resetAt`. Monthly durations are not guessed. Extra-usage money is excluded.
- [Grok native billing extension](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-shell/src/extensions/billing.rs):
  ACP `x.ai/billing`, percentage-based `config.creditUsagePercent` and
  `currentPeriod.type/start/end`. Weekly/monthly periods remain account-wide.
  Legacy monetary `monthlyLimit`/`used`, prepaid balances and per-product usage
  are not substituted for subscription percentage.

Provider payloads may include unrelated fields; only the reviewed quota fields
are projected. A future unknown quota window is not claimed to be supported.
Malformed reviewed fields raise `QuotaError` with fixed, non-payload messages.
The collector must publish a sanitized failure rather than retain a false fresh
success. Native account identity verification and complete provider-window
coverage require live collector acceptance; a fixture proves neither.

DeepSeek's [API balance](https://api-docs.deepseek.com/api/get-user-balance/)
reports money, not a periodic subscription reset. **Explicit owner decision,
21 September 2026:** DSH uses the direct DeepSeek API; the V1 requirement for this
one harness is actual balance, currency, native `is_available`, source and
freshness. Reset is displayed as **not applicable**. The other four harnesses
still require real subscription quota/reset; this is not a general exemption.

`BalanceAmount`, `BalanceObservation` and the DSH-owned `QUOTA_POLICY` implement this
separate shape. They never turn money into token limits or percentages. Decimal
strings are parsed with `Decimal` and retained as exact decimal strings, never
rounded through float. Availability is the native boolean, never inferred from
the amount. Duplicate currencies, missing amounts/availability and malformed
decimal strings are refused. Supported currencies come from the provider policy;
the generic amount value only validates a three-letter currency code. Both
supported currencies remain separate; no exchange rate
or sum across currencies is invented. `failed_balance_observation` supplies a
sanitized error. The same service supports balance snapshots, grouping and TTL;
`reset_applicability: not_applicable` and `resets_at: null` stay explicit.

The balance endpoint does not itself establish account identity. Its collector
still needs a verified native billing-account binding to deduplicate accounts;
equal aliases or different API keys do not establish account equivalence.
Live DeepSeek collection and UI remain unimplemented in this slice.

## Monetary observations when the account is unknown

An absent native account-id endpoint does not prevent displaying a balance read
through the same credential and origin context as dispatch. `CredentialContext`
is a separate trusted-collector subject for this case, supported only by a
monetary policy. It does not assert billing-account identity. The collector calls
`CredentialContext.create(policy)` to mint a random UUID4 handle; a constructor
can reconstruct that handle, but is not an HTTP input door. UUID validation is
format validation, not proof of randomness or authentication. Never derive the
handle from a key, key hash, alias, native telemetry id or unverified account id.
Never place a credential, URL or upstream text in its fields.

Use `service.bind(binding_id, None, source, connection=context)`, and pass
`account=None, connection=context` to `parse_observation` or
`failed_balance_observation`. Exactly one verified account or credential context
is required. The context's complete provider-owned policy must match the source;
the native parser's policy stamp is still checked. Subscription observations
continue to require a verified `AccountIdentity`; a context cannot replace it.

The collector owns the evidence that dispatch and the balance request use the
same resolved credential/origin snapshot. It must mint a new context and rebind
when that snapshot changes. No resolver, collector or such evidence is supplied
by this slice. Constructor calls alone do not prove this relationship.

Connection observations serialize `account: null` and an explicit `connection`
object with `kind: credential_context`, its opaque `context_id`, vendor and
`account_status: unknown`. Missing and failed snapshots retain this subject while
money and availability remain absent. Exact decimal strings and
`reset_applicability: not_applicable` are unchanged. Verified account snapshots
retain their existing identity fields and carry no connection claim.

Connection samples are cached per binding generation, never grouped or summed,
even if trusted code supplies the same context to two bindings. Rebinding starts
with no observation, including A-to-B-to-A and reusing the same context handle;
old in-flight tickets cannot publish. Unbinding discards that generation's
sample. A mismatch of context or source is refused. Within one generation, the
existing older/equal-time, failure-replaces-success, future timestamp and TTL /
clock-rollback rules apply unchanged. Verified account grouping remains as
specified above. Different contexts or keys provide no evidence of different
billing accounts, so the UI must never total their balances or imply deduplication.
