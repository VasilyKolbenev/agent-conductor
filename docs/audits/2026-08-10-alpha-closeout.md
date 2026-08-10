# December Command v0.1.0 alpha closeout

- **Date:** 2026-08-10
- **Measured commit:** `3a00544959422e1d8d028ac1eb4c371767719a5d`
- **Distribution / CLI:** `agent-conductor` / `conduct`
- **Protocol:** v1

## Release identity and wheel

The distribution metadata, `conductor.__version__`, README status and release-smoke procedure
all name `0.1.0`. The wheel was built through the isolated PEP 517 backend and installed with
`--no-index --no-deps` into a newly created virtual environment outside the source worktree.
It was then exercised from a different working directory with `PYTHONPATH` absent.

| Check | Result |
|---|---|
| Wheel | `agent_conductor-0.1.0-py3-none-any.whl`, 118298 bytes |
| SHA-256 | `450A2B63ADFF08149349E5C1DEA39F0DB2491F9C97E96F7C9103DE330DF7B979` |
| Installed metadata and runtime version | both `0.1.0` |
| Imports | schema, merge, store, prompts, server, demo, report, doctor and harnesses imported |
| CLI | all seven subcommands visible; init, validate, doctor, report and demo exercised |
| Server | panel, `state.json` and canonical `/handoff/claude.md` each returned HTTP 200 |
| Bind and branding | loopback URL used; served panel title named December |

The fresh Default Orbit scaffold validated cleanly. Its doctor exit was 1 because it remained a
generic, lane-free scaffold; that is the documented readiness result, not a packaging failure.

## Frozen-HEAD gate

One accepted process ran all three DO-7 gates in order. `TEMP` and `TMP` pointed to a dedicated
workspace directory for the entire process tree so the nested mutation-instrument tests used the
same accessible environment as the parent suite.

| Gate | Result |
|---|---|
| Full suite | **1750 passed, 4 skipped** in 118.81 s |
| Mutation baseline | **102 targeted tests green** on unmutated source |
| Mutation catalogue | **15/15 killed**, exit 0 |
| Mutation provenance | `source root` and `conductor.merge` both resolved inside the export |
| Source worktree after the run | **clean** |

An earlier attempt was invalid, not a competing measurement: the parent pytest had an explicit
base temp but two nested pytest processes reached the sandbox-denied system temp. It ended with
1748 passed, 4 skipped and 2 environment errors; the mutation phase never ran. The accepted run
changed only the process environment and kept the same frozen commit.

## Scope statement

The alpha observes, explains and prepares deterministic handoffs. Its panel is read-only and
local; it does not execute a harness, infer a model or prompt, or turn an absent request into a
decision. Interactive execution, receipts, run identity, policy and visual Orbit editing remain
post-alpha work under the tracked December Command product direction.
