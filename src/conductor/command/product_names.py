"""The names the product owns at the top of a project folder, and how they are kept out of git.

Every name is imported from the constant that owns it and never spelled a second time, so a name
the product renames moves here by itself. The harness folders come from the harness modules; a
guard rebuilds the expected list from the provider catalog, so a harness that is added and not
listed here turns a test red (spec 9.2, L14).
"""
from __future__ import annotations

from ..ownership_records import ACTIVE, HOME, LEGACY
from .adapters import claude_code, codex_cli, dsh_harness, grok_build, kimi_code
from .adapters.harness_workspace import INSTRUCTION_DIR
from .work_layout import WORK_DIR

#: The staging folder a task's seed is prepared in before it moves under `work/` (spec 9.1.2).
SEED_STAGING_DIR = ".conduct-seed"
#: What a retired ownership folder is renamed to; `ownership_transition` appends a nonce to it.
RETIRED_PATTERN = f"{HOME}-retired-*"
#: The harness modules whose own home folder and marker sit beneath a project root, in the order
#: the exclude block lists them.
_HARNESSES = (claude_code, codex_cli, grok_build, kimi_code, dsh_harness)
_HARNESS_NAMES = tuple((module.HOME_DIR, module.MARKER_DIR) for module in _HARNESSES)

#: One constant for every top-level name a project folder holds because of the product.
PRODUCT_TOP_NAMES = (
    HOME, LEGACY, ACTIVE, RETIRED_PATTERN, SEED_STAGING_DIR, WORK_DIR, INSTRUCTION_DIR,
    *(name for pair in _HARNESS_NAMES for name in pair),
)

#: Files and folders that carry instructions for an agent. A trailing slash marks a folder. Found
#: at any depth and compared without regard to case (spec 6.2.1); never copied by default.
AGENT_INSTRUCTION_NAMES = ("AGENTS.md", "CLAUDE.md", ".claude/", ".codex/", ".grok/", ".kimi/")

#: The lines of the block written into `.git/info/exclude`: the single spelling of spec 9.2.
#: Folders end in a slash; a harness marker has none, so it is excluded whatever it is.
EXCLUDE_LINES = (
    f"/{LEGACY}/", f"/{ACTIVE}/", f"/{HOME}*", f"/{WORK_DIR}/", f"/{INSTRUCTION_DIR}/",
    *(line for home, marker in _HARNESS_NAMES for line in (f"/{home}/", f"/{marker}")),
)
