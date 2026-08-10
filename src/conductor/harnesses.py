"""The bundled registry of known harness products — presentation metadata only.

ADR 0001 §6 fixes both what this is and what it may never become. Branding is
UI/adapter metadata: the protocol carries the harness *string* a user wrote
and nothing else, no merge rule reads a field defined here, and `state.json`
is identical whether or not a project's harness happens to be listed. What the
registry supplies is the display name, the badge and the documentation link a
panel needs to render a harness as a product rather than as a slug — plus the
ids `conduct init` can offer by number instead of making a newcomer guess a
spelling.

Two values per harness, and the split is the whole point. The `id` is stable
and is what lands in `map.toml`; the `display_name` is presentation and never
reaches disk. Nothing maps one to the other: no normalisation, no slugify, no
quiet rewrite of `Claude Code` into `claude-code`. A user who types a harness
name as free text gets that exact string in their file, validated and
otherwise untouched — guessing which registry row they meant is how a
committed map ends up naming a product nobody chose.

Nothing here inspects the machine, and `executable_hints` is the one field
that could be mistaken for an invitation to. It is documentation for a person
reading this file: nothing looks it up, no code path turns it into a lookup,
and detecting installed harnesses is a capability class of its own that needs
its own ADR (privacy, sandboxing) before any of it exists.

The accents are OURS, not the vendors'. No official logo is bundled and no
brand colour is copied out of a book we cannot verify. They are data here and
nothing more — this module validates that they are well-formed hex in both
themes and supplies a neutral pair for anything unregistered, and it makes no
claim about how any of them look beside a status colour. **Identity and status
are separated by channel, not by hue**, and the channel rule is the contract
DEC-UI-3 inherits and enforces where the accent is actually applied:

- harness identity is carried by monogram, display name and a small local
  swatch; status is carried by glyph, text and a status chip or outline;
- a harness accent is FORBIDDEN on the node outline, on edges, on the progress
  path, on the primary action, on the focus ring, and on any status glyph;
- custom and unregistered harnesses stay neutral;
- a hue collision therefore cannot change a meaning, because colour is never
  the sole carrier of one.

A hue-distance rule was considered here and rejected: it does not scale as the
registry grows, it would distort colours users recognise, it does nothing for
colour-vision deficiency, and an HSV gap is not evidence that two things
cannot be confused. The scope restrictions above, plus a contrast audit, do
the work — downstream, where the colours are used.

DeepSeek deliberately has no `deepseek` registry entry. DeepSeek currently
provides models, APIs and official integration guides for third-party
harnesses; it does not identify a first-party public coding Harness named
DeepSeek. Third-party Harness products are registered under their own product
identities. Revisit if DeepSeek ships and documents a first-party Harness. The
distinction that decides every future row is the same one the product
direction draws when it says December has no model marketplace and no
inference routing: this registry lists harness products, not model or API
providers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Harness:
    """One known harness product, as presentation and onboarding metadata.

    Attributes:
        id: The stable value written into `map.toml` and carried by the
            protocol. This, never `display_name`, is what lands in a file.
        display_name: The product's name as its vendor writes it. Presentation
            only.
        monogram: One or two characters for the panel's badge (ADR 0001 §6).
            Every entry in the bundled registry below carries two; the
            fallback `resolve` builds for an unregistered id manages only one
            when the id holds a single word one character long that is still
            one character upper-cased — `c++` and `a-` are as short as `x`
            here, while `ß` upper-cases into `SS` — and `"?"` when the id holds
            no letter or digit at all. Words are Unicode, so the badge for
            `Кодекс` reads `КО` and the badge for `中文` reads `中文`.
        accent_dark: Badge accent on the dark theme, as `#rrggbb`.
        accent_light: Badge accent on the light theme, as `#rrggbb`.
        docs: The vendor's documentation entry point; `""` for `custom`, which
            names no vendor.
        adapter: The adapter id this harness would resolve to. A placeholder:
            no adapter layer exists yet and nothing resolves it, so the field
            reserves the ADR 0001 §6 key rather than promising a lookup.
        executable_hints: What the product is usually called on a command
            line. Documentation for a person — NOTHING looks these up.
    """

    id: str
    display_name: str
    monogram: str
    accent_dark: str
    accent_light: str
    docs: str
    adapter: str
    executable_hints: tuple[str, ...]


#: The id meaning "a harness Conduct does not know". A legitimate harness type
#: in ADR 0001 §1, not an error state, and the honest answer for every product
#: missing from the list below.
CUSTOM = "custom"

#: The neutral badge an unregistered harness gets (ADR 0001 §6: unknown
#: adapters get the neutral badge, never a guessed brand). `custom` carries the
#: same pair, so a declared custom harness and an unrecognised string look
#: alike — which is the truth about how much either one is known. Public
#: because a panel drawing an unregistered harness needs this pair by name,
#: and a private one would make a rename here a broken badge there.
NEUTRAL_DARK = "#8b93a1"
NEUTRAL_LIGHT = "#5a6472"

_KNOWN: tuple[Harness, ...] = (
    Harness(id="claude-code", display_name="Claude Code", monogram="CC",
            accent_dark="#6ea8ff", accent_light="#2258c9",
            docs="https://docs.claude.com/en/docs/claude-code",
            adapter="claude-code", executable_hints=("claude",)),
    Harness(id="codex", display_name="Codex", monogram="CX",
            accent_dark="#3fc9de", accent_light="#0a6f80",
            docs="https://developers.openai.com/codex/",
            adapter="codex", executable_hints=("codex",)),
    Harness(id="cursor", display_name="Cursor", monogram="CU",
            accent_dark="#b489ff", accent_light="#6033c4",
            docs="https://docs.cursor.com/",
            adapter="cursor", executable_hints=("cursor-agent",)),
    Harness(id="windsurf", display_name="Windsurf", monogram="WS",
            accent_dark="#55b0f0", accent_light="#0f6aa8",
            docs="https://docs.windsurf.com/",
            adapter="windsurf", executable_hints=("windsurf",)),
    Harness(id="kimi-code", display_name="Kimi Code", monogram="KC",
            accent_dark="#e58ad9", accent_light="#98268c",
            docs="https://www.kimi.com/code/docs/",
            adapter="kimi-code", executable_hints=("kimi",)),
    Harness(id="qwen-code", display_name="Qwen Code", monogram="QC",
            accent_dark="#9a90ff", accent_light="#4038c8",
            docs="https://github.com/QwenLM/qwen-code",
            adapter="qwen-code", executable_hints=("qwen",)),
    Harness(id="grok-build", display_name="Grok Build", monogram="GB",
            accent_dark="#9fb2c8", accent_light="#455a70",
            docs="https://docs.x.ai/build/overview",
            adapter="grok-build", executable_hints=("grok",)),
    Harness(id="github-copilot", display_name="GitHub Copilot coding agent",
            accent_dark="#cf8bf2", accent_light="#7a26ad", monogram="GH",
            docs="https://docs.github.com/en/copilot",
            adapter="github-copilot", executable_hints=("gh",)),
    # REG-1. OWNER-CONFIRMED 2026-08-10. Three fields of the two rows below
    # state external facts — `docs`, `display_name`, and `executable_hints` —
    # and the owner verified all six values against the vendors' official
    # documentation. Gemini CLI uses https://geminicli.com/docs/ and the
    # `gemini` command. OpenCode uses https://opencode.ai/docs/ and the
    # `opencode` command; its product spelling is title-cased even though its
    # executable and technical identifiers are lower-case. Tests pin the
    # confirmed literals locally; they deliberately make no network request.
    # The remaining fields state no vendor fact a test cannot reach: `id` and
    # `monogram` are pinned by test_every_entry_is_complete_and_unambiguous
    # and test_no_two_registered_harnesses_share_a_badge_and_a_collision_is_caught,
    # the accents by test_both_themes_carry_a_well_formed_accent plus the
    # contrast audit in test_harness_accent_contrast.py, and `adapter`
    # resolves to nothing yet — a placeholder whose one promise, staying off
    # the wire, is test_the_payload_is_json_ordered_and_carries_only_the_badge's.
    # test_the_reg1_disclosure_names_every_field_that_states_an_external_fact
    # derives the external set from the dataclass and requires each member
    # named here, so this list cannot narrow again without a test going red.
    Harness(id="gemini-cli", display_name="Gemini CLI", monogram="GC",
            accent_dark="#4fd1a5", accent_light="#0d6d5a",
            docs="https://geminicli.com/docs/",
            adapter="gemini-cli", executable_hints=("gemini",)),
    Harness(id="opencode", display_name="OpenCode", monogram="OC",
            accent_dark="#d3a88c", accent_light="#7d4a2c",
            docs="https://opencode.ai/docs/",
            adapter="opencode", executable_hints=("opencode",)),
    Harness(id=CUSTOM, display_name="Custom harness", monogram="CH",
            accent_dark=NEUTRAL_DARK, accent_light=NEUTRAL_LIGHT,
            docs="", adapter="", executable_hints=()),
)

_BY_ID = {harness.id: harness for harness in _KNOWN}

#: The ids `conduct init` offers by number, in the order it offers them. Short
#: on purpose: a wall of every product this file knows, at the first prompt, is
#: a worse opening minute than three names and a line saying where the rest
#: are — and the wall gets taller with every row added. Membership
#: here is an onboarding decision, not a claim that these work better.
RECOMMENDED = ("claude-code", "codex", "cursor")

#: Splits an id into words for the fallback monogram: a run of anything that is
#: not a Unicode word character, plus the underscore, separates two words.
#: Unicode because `templates.NAME_RE` validates by Unicode `\w` and December
#: declared no ASCII-only harness id — an ASCII split reads `Кодекс`, `ΩΩΩ` and
#: `中文` as having no words at all and badges every one of them `?`. The
#: underscore is added back as a separator because `\W` alone would keep it and
#: turn `my_own_agent` into one word. Not a validation rule — `templates.NAME_RE`
#: owns what a harness id may contain.
_WORD_RE = re.compile(r"[\W_]+")


def known() -> list[Harness]:
    """Every registered harness, in the order `conduct init` presents them.

    Returns:
        The entries as data. This module renders no UI: a caller decides how
        to spell a row, and nothing here returns display text.
    """
    return list(_KNOWN)


def vendors() -> list[Harness]:
    """Every registered entry that names a vendor — `known()` without `custom`.

    Returns:
        The entries in registry order, minus the `custom` row. `custom` is a
        legitimate harness type rather than an error state, but it names no
        product: it carries no documentation link, no accent of its own and no
        executable hint. A caller listing the products this file knows about
        therefore wants this; `known()` is for when the menu itself, `custom`
        row included, is the subject.
    """
    return [harness for harness in _KNOWN if harness.id != CUSTOM]


def as_payload() -> list[dict[str, str]]:
    """The registry as JSON-serialisable presentation data, in registry order.

    Returns:
        One fresh dict per entry — `known()`'s order, `custom` included, since
        a panel has to draw that badge too — carrying exactly what a badge is
        drawn from: id, display name, monogram, both accents and the
        documentation link (`""` for `custom`, which links to no vendor).

        Two fields are deliberately absent. `executable_hints` is documentation
        for a person reading this file and would become a lookup the moment it
        crossed a wire, which is the one thing this module promises it is not.
        `adapter` resolves to nothing today and shipping it would read as a
        promise that it does.

        The dicts are rebuilt on each call, so a caller that edits what it got
        back cannot reach the frozen entries anyone else resolves against.

    How this reaches the panel is NOT decided here. A dedicated
    `/harnesses.json` route and a server-side resolve into the state document
    are both open, and the choice belongs to DEC-UI-3; what this function
    settles is only the shape, so either route carries the same bytes.
    """
    return [{"id": harness.id, "display_name": harness.display_name,
             "monogram": harness.monogram, "accent_dark": harness.accent_dark,
             "accent_light": harness.accent_light, "docs": harness.docs}
            for harness in _KNOWN]


def get(harness_id: str) -> Harness | None:
    """The registry entry for `harness_id`, or None if it is not registered.

    Args:
        harness_id: A harness string exactly as a map or a lane carries it.

    Returns:
        The `Harness`, or None. None is an ordinary answer — most projects
        will name something this file has never heard of — so callers that
        need metadata regardless should use `resolve`.
    """
    return _BY_ID.get(harness_id)


def _monogram(harness_id: str) -> str:
    """One or two initials for an unregistered harness, from the string alone.

    Args:
        harness_id: A harness string with no registry entry.

    Returns:
        The first letter of each of the first two words, or the first two
        characters of a single word, upper-cased and then cut back to two code
        points — one character when that is all the upper-cased string has, and
        `"?"` when it holds no letter or digit at all. Words are runs of Unicode
        alphanumerics, so `Кодекс` gives `КО` rather than `?`. The cut comes
        after upper-casing because upper-casing can lengthen: `ß` becomes `SS`,
        so `ßa` would otherwise badge three characters wide.

        Neither short case is padded to two: there is no honest second
        character to add, and a badge that invents one states something about a
        harness nobody supplied.
    """
    words = [word for word in _WORD_RE.split(harness_id) if word]
    if len(words) >= 2:
        initials = words[0][0] + words[1][0]
    elif words:
        initials = words[0][:2]
    else:
        return "?"                    # no letters or digits at all
    return initials.upper()[:2]       # `ß`.upper() is `SS`: two out of one


def resolve(harness_id: str) -> Harness:
    """Presentation metadata for any harness string, registered or not.

    Args:
        harness_id: A harness string exactly as a map or a lane carries it.

    Returns:
        The registry entry when there is one, otherwise a deterministic
        fallback: the string as its own display name, initials as the
        monogram, and the neutral badge. The accent is neutral rather than
        derived from the string, deliberately — a hue hashed out of a name is
        a brand claim about a product we know nothing about, and a badge that
        admits it does not know is worth more than one that guesses.
    """
    known_harness = _BY_ID.get(harness_id)
    if known_harness is not None:
        return known_harness
    return Harness(id=harness_id, display_name=harness_id,
                   monogram=_monogram(harness_id),
                   accent_dark=NEUTRAL_DARK, accent_light=NEUTRAL_LIGHT,
                   docs="", adapter="", executable_hints=())
