"""The files and folders an agent reads as instructions from a project (spec 6.2.1, 9.2, L31).

They are facts about the vendors' own tools, so they live with the adapters and not with the
request path, which names no vendor (`tests/test_alpha1_gate_g_provider_breadth.py`). The seed
leaves them out of a task's folder unless the owner asks, the add-project door only looks for
them, and `product_names` hands the same tuple on under its own name.
"""
from __future__ import annotations

#: A trailing slash marks a folder. Found at any depth and compared without regard to case; never
#: copied into a task by default.
AGENT_INSTRUCTION_NAMES = ("AGENTS.md", "CLAUDE.md", ".claude/", ".codex/", ".grok/", ".kimi/")
