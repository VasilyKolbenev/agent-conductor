# Conduct

[![CI](https://github.com/VasilyKolbenev/agent-conductor/actions/workflows/ci.yml/badge.svg)](https://github.com/VasilyKolbenev/agent-conductor/actions/workflows/ci.yml)

**Your agents write lanes. You conduct.**

Conduct is a self-hosted control plane for the AI coding harnesses already working on
your code — Claude Code, Codex, or anything that can write a JSON file. Each agent keeps
one file — its lane — saying what it is doing, what it found, and what it needs from you.

*Alpha — protocol v1.*

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
conduct init        # scaffolds conductor/ — the map it writes is already valid
# edit conductor/map.toml: swap in your nodes, roles, and phases
conduct validate    # prints nothing when the map and lanes are valid
conduct prompt --role implementer --author claude
conduct up          # panel at http://127.0.0.1:7777/
```

`conduct prompt` prints the working instructions for one agent — paste the output into
Claude Code, Codex, or whatever harness holds that role. The agent then keeps its lane
file (`conductor/lanes/claude.json`) up to date, and the panel reflects every write
live.

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
- The demo scenario: `demo/README.md`

## Status

Alpha. Protocol v1. Python 3.11+, zero runtime dependencies. CI on Windows and Linux.
MIT license.
