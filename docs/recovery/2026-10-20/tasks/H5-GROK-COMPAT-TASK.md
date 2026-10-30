# H5-GROK-COMPAT: disable imports from personal Claude and Cursor profiles

Owner direction, 2026-10-30: stop export recovery and continue December Command within the
existing allowance. This is an offline prerequisite of Grok diagnose, not a live attempt.
Base: `120730a`; design authority: H5-GROK-DIAGNOSE-DESIGN, addendum 1 (`183904f`).

## Problem and contract

The recorded G0b inspection found that Grok 1.0.5 can import hooks, MCP and other configuration
from the owner's Claude/Cursor profiles by default, even outside the isolated task road.
Its product profile currently forces only four telemetry switches. Every product-created Grok
child must also receive these twelve exact code-owned pairs, with the string value `false`:

`GROK_{CLAUDE,CURSOR}_{SKILLS,RULES,AGENTS,MCPS,HOOKS,SESSIONS}_ENABLED=false`.

They apply to version, login-status, quota and task children. Operator-supplied environment
values cannot turn them on in the effective child environment. Keep the four original
telemetry pairs, all argv, pinned version, task capabilities and refusal paths unchanged.
The Grok profile digest must change; Claude and Codex snapshots must remain byte-identical.

## Scope and proof

- Edit only `adapters/grok_build.py`, `tests/_fakegrok.py`, a new
  `tests/test_grok_compat_isolation.py` and directly affected Grok test expectations.
  The lead owns the CAPPED entry and report.
- The fake independently records all twelve environment values; expectations are literals,
  not generated from the production constant. Test the actual child boundary on every road.
- Capture red on the old source, then green in UTF-8 and cp1251. Check the existing
  Claude/Codex snapshot. Mutants: remove a pair, change false to true, lose all pairs/no-op;
  each must fail on child environment, not setup or collection.
- Independent review of the diff; code and report in separate local commits. No full core,
  downloads, login-home access, live CLI/model calls, installation, push or new server.

## Boundaries and following I2 work

No GrokRelay or file-channel activation occurs here. New routing names, global subscription
allowlist refusals, review_only and role selection belong to the next slice.
There is a design conflict to resolve before activating the relay: `_route_selected` rejects
forced names which the relay forbids, and its only current exception belongs to Codex.
Grok will need a narrowly matched code-owned false-pair exception; operator-selected names
must still refuse. Do not reuse the Codex access-only exception, which also controls whether
a switch is removed from preflight and real-home metadata children.

The twelve switches are the mitigation already chosen in the accepted design, not proof of
all vendor behavior or a claim that Grok's read-only execution has passed live acceptance.
