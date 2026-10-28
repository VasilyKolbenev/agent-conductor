# H5-CODEX-A-P6P7 — measured quota protocol and home census

Codex decision, 28.10.2026. Parent DESIGN `69c2a7d`, R4/P6/P7 and A-I1 `8a4fe5f`.
Scope follows the owner's instruction to connect the subscription Codex harness.

## Evidence

`Documents/Codex/work/cdx164-live-prep/evidence/20261028T114205982864Z-p6.json`:
two access-only sessions completed exit 0 (1.046/0.766 seconds); source and copies unchanged;
refresh/provenance absent from copies, no refresh diagnostic or secret echo; processes retired,
relays and temporary root removed. Original P6 quota decoder refused unsolicited notifications.
Observed methods only: `account/updated`, `remoteControl/status/changed`.
Fresh server cache: client 0.164.0, ten server models, `gpt-6.1-sol` visibility `list`.
No model call was made. P11 separately observed `log` directory after owner login.

## R4: exact opt-out, strict decoder retained

Named files: `src/conductor/command/adapters/codex_quota.py`,
`tests/test_subscription_quota.py`. Add initialize.params.capabilities.optOutNotificationMethods
with exactly the two observed methods above, without experimentalApi or wildcard suppression.
Keep `SubscriptionRpc.decode` strict; an unrequested/unknown notification still refuses.
Test via the actual quota read payload, simulating the CLI boundary's notification behavior.
Red without opt-out, green with it, missing-method/no-op/unknown-notification mutants as relevant.
Changing the fixed RPC changes provider authority as the existing digest contract requires.

## P7: account only for measured names

Named implementation file: `src/conductor/command/adapters/codex_cli.py`; tests in
`tests/test_codex_compatibility.py`. Do not change shared cleanup/permission mechanisms.
Root will confirm exact classification before implementation. Both metadata homes contained:
`.sandbox`, `auth.json`, `goals_1.sqlite`, `goals_1.sqlite-shm`, `goals_1.sqlite-wal`,
`installation_id`, `logs_2.sqlite`, `logs_2.sqlite-shm`, `logs_2.sqlite-wal`,
`memories_1.sqlite`, `memories_1.sqlite-shm`, `memories_1.sqlite-wal`, `models_cache.json`,
`queue_1.sqlite`, `queue_1.sqlite-shm`, `queue_1.sqlite-wal`, `skills`,
`state_5.sqlite`, `state_5.sqlite-shm`, `state_5.sqlite-wal`, `tmp`.
P11 also measured `log`. Preserve pre-existing operator files; only newly added scratch is removed.
No wildcard sqlite allowlist, new config authority or arbitrary unknown-file tolerance.
Behavioral witness: native quota road creates measured names, returns quota and accounts for
its residue; an unknown new name still refuses. No test merely comparing constants.

## Completion and next live measurement

One implementation/review pass, meaningful mutants, both encodings of affected suites and caps.
Code/test commits separate from this decision. Final full core on a clean exact candidate SHA.
Build a new protected candidate after both changes; do not replace B3.
R4 permits ONE corrected quota-only metadata session, 15 seconds, actual revised QUOTA_RPC,
the same protected/source-lease/access-only/retirement/secret-projection checks as initial P6.
Do not repeat model/list, P11, P8/P9 or infer with a model in this step.
Failure records the exact safe reason and stops; no retries, alternate model or API key.
M2 remains the separately approved single 60-second `0.164.0 / gpt-6.1-sol` probe after prerequisites.
