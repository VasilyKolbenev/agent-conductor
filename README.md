# December

[![CI](https://github.com/VasilyKolbenev/agent-conductor/actions/workflows/ci.yml/badge.svg)](https://github.com/VasilyKolbenev/agent-conductor/actions/workflows/ci.yml)

**Build your Orbit. Control the cycle.**

*Your agents write lanes. You conduct.*

December Command is a self-hosted control plane for the AI coding harnesses already working on
your code — Claude Code, Codex, or anything that can write a JSON file. Each agent keeps
one file — its lane — saying what it is doing, what it found, and what it needs from you.

*Alpha — Protocol v1. The distribution is `agent-conductor`; the CLI is `conduct`.*

## 60-second quickstart

Requires Python 3.11+. Not on PyPI yet — install from GitHub:

```sh
pip install git+https://github.com/VasilyKolbenev/agent-conductor.git
```

or clone and install editable:

```sh
git clone https://github.com/VasilyKolbenev/agent-conductor.git
cd agent-conductor
pip install -e .
```

Then run the bundled demo:

```sh
conduct demo
```

Open the printed URL (`http://127.0.0.1:7777/`, or `conduct demo --port 8080` if 7777 is
taken). You are looking at a release that went wrong: a red release gate, three findings,
one reviewer disagreement, and one decision waiting for you (`demo/README.md` explains
the scenario).

## Use it on your own project

```sh
cd your-project
conduct init        # asks three questions in a terminal; --template skips them
# edit conductor/map.toml: swap in your nodes, roles, and phases
conduct validate    # prints nothing when the map and lanes are valid
conduct doctor      # says what is not ready and gives the next command
conduct prompt --role implementer --author claude
conduct report      # the merged state as Markdown, on stdout
conduct up          # panel at http://127.0.0.1:7777/
```

`conduct prompt` prints the working instructions for one agent — paste the output into
Claude Code, Codex, or whatever harness holds that role. The agent then keeps its lane
file (`conductor/lanes/claude.json`) up to date, and the panel reflects every write
live.

`conduct report` renders the same merged state the panel serves, as Markdown on stdout:
the decision brief, the human queue, the findings, and a section naming what that state
does not know. Nothing about it is interactive, so it goes in a pull request comment, a
CI log, or a file.

`conduct doctor` answers a different question from `validate`: not only whether the files
parse, but whether the project is set up to work. Each finding names the next command to
run, and the command exits 0 only when every readiness check is OK. It reads project files
and the bundled harness registry; it never probes your machine for installed tools.

In the panel, select an agent lane to see its current harness, role, assigned stage, runtime
phase, task, findings, and human requests. **Copy handoff packet** copies a deterministic
Markdown packet rendered from that same `state.json`; fields Protocol v1 does not have — model,
prompt, skills, runtime controls — are not guessed or shown as empty placeholders.

### What `conduct init` writes

`conduct init` never inspects your machine. It does not look for installed harnesses, and
the answers it takes only label who does what, in the map and in the panel.

- **In a terminal** it asks three questions — the project name, which harness runs the
  implementing roles, and which harness reviews their work. Enter takes the default on
  each. Answering the reviewer question with the `(none)` row writes the `single-harness`
  map; every other answer writes `default-orbit`.
- **`--template NAME`** skips the questions and writes one named map, and
  `conduct init --help` lists them:
  - `default-orbit` — the recommended five-stage process, goal, detect, diagnose,
    design, deliver, and what init writes when nothing else is asked for.
  - `single-harness` — one implementing role plus a human decision, and no reviewer.
  - `empty` — the minimum that validates: one placeholder node and no cycle.
  - `minimal` — the protocol spec's own §2 example map, quoted verbatim.
- **Where there is no terminal** — a pipe, a CI runner — it writes `default-orbit`
  without waiting for an answer, so it cannot block a script.

Every path writes the same three things: `conductor/map.toml`, `conductor/lanes/` and
`conductor/events.jsonl`. It then validates what it wrote, and puts on stdout — and on
stdout alone — a bootstrap prompt for the agent that fills the map in, so
`conduct init > setup.txt` leaves you that prompt and nothing else. What the prompt says
about your `[[nodes]]` blocks is read out of the map that was just written: where they are
placeholders it tells the agent to replace them with your real components, and where they
already name components — as in `minimal`, which quotes the spec's example — it tells the
agent to check each one against your project instead. An existing `conductor/`
is never touched: init says so and exits 1.

## What it is

- **Files are the API.** All state lives in a `conductor/` directory inside your
  project: `map.toml` (the project map), `lanes/<author>.json` (one file per agent),
  and `events.jsonl` (an append-only log). Any tool that writes JSON can participate.
- **Silence is not consent.** An agent that stops reporting does not stay green — it goes
  stale, and the panel says so. Disagreements, staleness, review coverage, and the human
  queue are all computed from the raw lanes, so no agent can bury a conflict by declining
  to write it down. Nothing unknown shows green.
- **The panel is read-only and local.** It never calls an LLM, never spawns agents,
  and binds to 127.0.0.1 only. It shows what needs your attention and what to decide.

## What it is not

- Not a chat with your agents.
- Not an orchestrator or scheduler — it never runs agents for you.
- Not a trace warehouse.
- Not a cloud service — no account, no network access, no API keys.

## How it works

Each agent owns exactly one lane file and rewrites it as it works: current task, node
statuses, findings, verdicts on other agents' findings, and questions for the human.
The merge step reads the map and every lane and computes the project state
deterministically — same inputs, same state, no model in the loop. The panel renders
that state live and hands you a copyable decision brief for each wait. You answer; the
agents move on.

## Documentation

- Current normative protocol: `spec/PROTOCOL.md`
- Accepted Harness control-plane model: `docs/adr/0001-harness-control-plane-model.md`
- Product direction and the post-alpha December Command strike:
  `docs/specs/2026-08-03-hcp-competitive-product-direction.md`
- The demo scenario: `demo/README.md`
- The release smoke test, run against a release candidate before publishing:
  `docs/release-smoke.md`

## Browser-level panel checks

The regular test suite stays dependency-light and checks the panel's source-level
contracts. A separate suite opens the live loopback panel in Chromium and checks
the rendered DOM, computed styles, responsive Orbit, and composited status colours:

```console
python -m pip install -e ".[browser]"
python -m playwright install chromium
python -m pytest -q browser_tests
```

Playwright is an optional development/CI dependency. It is not installed with the
runtime wheel, the panel remains one static HTML file, and no build step is added.

## Status

December Command v0.1.0 alpha. Protocol v1. Python 3.11+, zero runtime dependencies. CI on Windows and Linux.
MIT license.
