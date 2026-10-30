Итог: владелец разрешил активацию, новую сборку и живые проверки; стоп при 25% остатка.

# H5-GROK-ACTIVATE: first Codex + Grok Dalio

Authority: owner message 30.10.2026, additional 15 percentage points from 40% remaining.
Hard stop: 75% account usage. Read counter at checkpoints; save state before stopping.
Base: 63fd1f2; DESIGN H5-GROK-DIAGNOSE-DESIGN at 183904f, I2/I3A/I3B reports.
Codex substitutes for unavailable Opus under existing PROC-CODEX-RETURN decision.

## Decisions and scope

Activate DESIGN section 3 atomically: review capability/schema; file task channel;
GROK_RELAY; 48 KiB output; review_enabled=True, serves_checks=False,
task_modes=("review",). Exact review argv from design: Read/Grep/Glob allowed,
Edit/Bash/WebFetch/WebSearch/MCPTool denied, prompt-file only. No model flag.
Keep dispatch implementation only for explicitly enabled test subclass / future work.
Do not relax refusal, isolation, echo scan, quota, cleanup or task verification.

Accept section 4 seed recommendation: exclude AGENT.md, CLAUDE.local.md and .cursor
alongside existing instructions, for every harness. Prove actual seed omits them;
keep ordinary source files. The G6 canary remains in source, outside seeded work.

Pinned Codex 0.164.0 / gpt-6.1-sol and Grok Build 1.0.5 remain unchanged.
New live projects contain only Codex and Grok; do not poll or call Claude.
This supersedes design's historical unchanged-Claude-row and Claude-fallback wording.
No automatic fallback or repeated failed live probe. New run IDs and new owner grants;
the exhausted codex-first-goal and old once probes are never reused.

## Parallel ownership and proof

Implementation owns src/conductor/command/adapters/grok_build.py, tests/_fakegrok.py,
tests/test_command_grok*.py, tests/test_grok*.py and new test_grok_activation.py.
Tell lead before any additional file. Lead owns seed change/tests, CAPPED, shared docs,
commits, protected install and orchestration. Independent reviewer reads diff only.

Red comparisons on base, green focused UTF-8/cp1251, real fake CLI reads task file;
prove access-only copy, no task in argv, production dispatch/checker refused,
review success and cleanup. Preserve Claude/Codex core snapshots. Meaningful mutants
in isolated copies, then independent review. Full core in a clean detached worktree
on final code SHA in both encodings before building. No CI or release claim.

## Machine and live sequence

Read current protected inventory and staged binary first. Prepare stage_grok2 and
preflight v2 exactly as design section 6; preserve v1 and old installed products.
Owner authorization covers new protected installation and live checks. Secrets stay
in dedicated login homes, never Git/logs/chat. Only names, types, hashes and TTL out.
Prepare concrete login command only if current Grok login needs renewal; owner signs in.

G2 shape/TTL and source scan, then optional one P under design preconditions.
If personal hooks/MCP make P require another owner approval, skip P and make G6 the
first real task in isolation (allowed design alternative); record that decision.
Protected new wheel and stage-A preflight precede G6. G6: separate project, one review
action/600 seconds and final human gate; test preview before any grant.
If G6 succeeds and cleans up, prepare fresh Dalio with Grok only diagnose, Codex main
roles plus separate Codex checker. Owner clicks grants and human gates in application.
Use measured runtime/quota and design TTL margin; no repeated guessing of timeouts.
On a failed live witness stop that road, preserve evidence and diagnose within budget.

At each checkpoint: last proven | first undone | do not repeat. Code and report commits
separate, local only; update verified local Git bundle before final handoff.
