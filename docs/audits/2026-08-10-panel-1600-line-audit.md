# Panel 1600-line architecture audit

Measured on `codex/do6-handoff` at `9541746`, immediately after DO-6 crossed the mandatory
audit trigger. This is the waiver's required stop and re-review, not a request to raise its
ceiling.

## Measurement

`src/conductor/panel/index.html` is 1657 lines: the style block ends at line 413, the static
document occupies lines 414–520, and the script occupies lines 521–1655. The source remains
unminified and its section banners remain intact. The largest script section is the data-driven
Orbit (roughly 264 lines); the new agents/handoff section is roughly 102 lines. The panel's
invariant circuits remain outside the asset in focused `tests/test_panel_*.py` modules.

The approved alpha ceiling is 2000 lines, leaving 343. That remainder is defect headroom, not
authorization for another feature slice.

## Decision

Keep the panel single-file for v0.1.0. Splitting CSS or JavaScript now would change the asset and
serving contract during release closeout, while minifying would destroy the readability for
which the waiver exists. DO-6 added one bounded read-only surface and did not add a build step,
dependency, protocol key or runtime action.

No new alpha UI feature follows DO-6. DO-7 may reconcile documentation and repair release
blockers. Any post-alpha interactive control surface begins by proposing the split — including
asset boundaries, cache behaviour, packaging, Content Security Policy and how the current
source-level test circuits attach to the new files — before implementation. Crossing 2000 in
the alpha remains a stop.

## Structural checks

- CSS, static markup and script still have explicit boundaries.
- Script responsibilities remain bannered: shell, KPI, map, harness identity, Orbit, attention,
  agents/handoff, findings, feed, render, interaction and data source.
- The handoff packet is not reimplemented in JavaScript. `conductor.report.handoff` is the
  canonical pure renderer and `/handoff/<author>.md` is a read-only route over the same brokered
  `state.json`; the panel only fetches and copies those bytes.
- Missing v1 data is named as unrecorded. Model, prompt, skills and runtime-action placeholders
  are absent because §6.1 does not project them.
- The DO-6 profile at the audit point is 974 passed, 4 skipped; the whole-tree gate is re-run
  after this audit and recorded by the integrating commit, not inferred from this profile.
