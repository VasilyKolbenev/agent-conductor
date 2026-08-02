# Conduct demo

`conduct demo` serves a bundled, fictional release-gate scenario for a plain web project:
a release whose smoke gate went red with three blockers. The reviewer confirms two
findings and partially disputes the third (the panel computes exactly one disagreement
from that), and one genuine ops decision — bake the payment config into the release image
or provision it per environment — sits in the human queue. Everything on screen is derived
by the merge rules from the fixture files; nothing is hand-written state. The fixture
ships inside the package at `src/conductor/_demo/conductor/` (map.toml, lanes/claude.json,
lanes/codex.json, events.jsonl) and is copied to a throwaway temp directory each run, so
poking at the served files never mutates the packaged copy.
