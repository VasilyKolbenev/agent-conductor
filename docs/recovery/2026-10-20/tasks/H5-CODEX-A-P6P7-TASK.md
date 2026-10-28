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
The fixed metadata RPC is not part of `ProviderAuthority.facts`; do not claim its payload alone
changes the grant digest. The accompanying P7 login-name profile changes are included via
`asdict(profile)`. First product use receives a fresh owner grant; no existing grant is reused.

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
Codex classification: scratch is `tmp`, `log`, `.sandbox` and the fifteen exact SQLite names
above (five databases plus their `-shm`/`-wal` companions). Expected retains the existing
auth/skills/version names and adds only `models_cache.json` and `installation_id`.
The pinned upstream `models-manager/src/cache.rs` defines the persistent model cache;
`core/src/installation_id.rs` creates/reuses a UUID. Neither name grants project configuration.
Source: https://github.com/openai/codex/tree/rust-v0.164.0/codex-rs .
`log` is scratch so newly added nested logs are measured even under a pre-existing directory;
pre-existing files remain. Test both new residue and pre-existing sentinel preservation.
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

## Protected build launcher on this Windows host

Build of code `9788eb9289bb61d5055061e7fdf3309dcc78de92` completed wheel/venv/import, then
`product_install.py:149` failed at generated `conduct.exe --help` with WinError 4551.
Evidence: `Documents/Codex/work/codex-r4-product-build.log`. Protected venv Python signature
is Valid; pip's generated console launcher is NotSigned. Windows protection remains enabled.

Codex permits completing this exact existing installation without rebuilding or deleting it:
verify archive, wheel members versus installed files, base inventory and module origin; smoke
the documented equivalent `[venv_python, -I, -m, conductor, --help]`. `pyproject.toml` maps
`conduct` to `conductor.__main__:main`. Record this launch argv and the blocked wrapper in a new
protected manifest; the existing wrapper remains inventoried, never launched again by this task.
This is a local invocation choice, not proof that an unsigned installer is ready for distribution.
External bounded finalizer only; no product source/test changes, exemptions or policy changes.
