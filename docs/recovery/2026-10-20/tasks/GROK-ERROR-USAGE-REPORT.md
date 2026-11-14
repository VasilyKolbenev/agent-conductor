# Grok failure evidence — locally checked

On a terminal failure the action journal can now distinguish recorded token usage,
incomplete usage data and an otherwise unexplained error. The receipt always
records failure and emits no artifact. These flags cannot recover why the original
grok-g6-kinds attempt failed.

TASK 23ce8bd, code 37dd0aa. The vendor reference is [headless.rs at
9fabade](https://github.com/xai-org/grok-build/blob/9fabade/crates/codegen/xai-grok-pager/src/headless.rs#L357).
The terminal response does not expose a standalone HTTP status. Missing usage is
inconclusive. No vendor text, raw counters, IDs or unknown fields are forwarded.

RED: 2 failed, 1 passed. Checking the adapter alone initially missed a second
problem: the runtime's closed vocabulary only recognized the generic prefix.
After fixing that boundary, 96 tests passed in UTF-8 and 76 in the Windows
system encoding (the second run excludes the unchanged generic transport suite).
M0 passed 3 cases on a detached copy; removing accounting, admitting a boolean
as a token count, and dropping incomplete usage each caused a distinct failure.
Each mutant was reverted and the original hash verified. Evidence:
Documents/Codex/work/nov-ux-evidence. No real vendor call was part of these tests.

Next real check: one owner-authorized read-only diagnose using an eligible wheel
and a fresh login. A meaningful result must explain the fixture discrepancy from
its supplied inputs. A failed action cannot close the Grok acceptance gate.
