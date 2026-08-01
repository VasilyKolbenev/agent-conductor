# Conduct demo

`conduct demo` serves a bundled snapshot of a real release-gate moment, sanitized for
publication: a desktop voice app whose offline smoke gate went red with three blockers.
The reviewer confirmed two findings and partially disputed the third (the panel computes
exactly one disagreement from that), and one genuine product decision — bundle a ~500 MB
speech-to-text model or download it on first run — sits in the human queue. Everything on
screen is derived by the merge rules from the fixture files; nothing is hand-written state.
The fixture ships inside the package at `src/conductor/_demo/conductor/` (map.toml,
lanes/claude.json, lanes/codex.json, events.jsonl) and is copied to a throwaway temp
directory each run, so poking at the served files never mutates the packaged copy.
