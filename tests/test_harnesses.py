"""Tests for `conductor.harnesses` — the bundled known-harness registry.

Two separable promises, and the second is the one that matters. The first is
that the data is well formed: ids unique, monograms two characters, accents
real hex, documentation links present. The second is that none of it can
reach a merge rule — ADR 0001 §6 makes branding UI/adapter metadata and the
protocol carries only the harness string, so `state.json` must be identical
whether or not a project's harness happens to be listed here. The additivity
block below is the same shape `role.stage` uses in test_merge_queue_phase.py,
for the same reason: an equality that a fixture could quietly make vacuous is
worth less than an equality plus a test that the fixture still has teeth.
"""
import ast
import json
import re
from dataclasses import fields, replace
from pathlib import Path

from conductor import harnesses, merge, templates
from tests.test_merge_queue_phase import NOW, ROLES_MAP, rich_lanes

HEX_RE = re.compile(r"\A#[0-9a-f]{6}\Z")

#: The field the registry documents and never resolves, spelled once so the
#: parse below, its own sabotage fixture and the findings it writes cannot
#: drift apart from each other.
HINTS = "executable_hints"

#: U+030C COMBINING CARON, named because it draws as nothing on its own. It is
#: what `ǰ` upper-cases into behind the `J`, and the reason the badge property
#: below counts the upper-casing rather than the letters and digits in it.
CARON = chr(0x030C)

#: The ids whose badges turn on how `_WORD_RE` splits words, rather than on
#: the alphabet they are written in. Seven are non-ASCII, and an ASCII `\w`
#: reads their letters as punctuation: that either strands the id with no words
#: at all — `Кодекс` badges `?` — or leaves it with the wrong ones, since `ßa`
#: then badges `A`. `my_own_agent` is pure ASCII and is here for the other
#: clause of the same rule, the underscore `_WORD_RE` adds back as a separator:
#: without it the id is one word and badges `MY`. Every one of them is checked
#: against `templates.NAME_RE` in the tests that use it, and that check is not
#: ceremony: a fixture that stopped being a legal harness id would go on
#: passing while pinning an input no user can reach, which is a test that
#: guards nothing dressed as a test that guards something.
UNICODE_IDS = ("Кодекс", "ΩΩΩ", "中文", "my_own_agent", "ß", "ßa", "ß-agent",
               "ǰ")


# --- the data itself ---


def test_the_registry_lists_the_products_it_says_it_does():
    # Pinned by id, in wizard order: a reordering or a quiet deletion is a
    # decision about what December claims to know, not an implementation detail.
    assert [h.id for h in harnesses.known()] == [
        "claude-code", "codex", "cursor", "windsurf", "kimi-code",
        "qwen-code", "grok-build", "github-copilot", "gemini-cli", "opencode",
        "custom"]

def test_deepseek_is_deliberately_absent():
    # Not because the integration story is missing — DeepSeek publishes models,
    # APIs and official guides for integrating them with third-party harnesses.
    # Because this registry lists HARNESS PRODUCTS, and DeepSeek identifies no
    # first-party public coding harness of its own; a third-party harness is
    # registered under its own product identity. Revisit if that changes. The
    # test exists so the row is a decision someone argues with, not a helpful
    # two-line edit.
    text = " ".join(f"{h.id} {h.display_name}" for h in harnesses.known()).lower()
    assert "deepseek" not in text
    assert harnesses.get("deepseek") is None

def test_the_gemini_row_is_the_cli_product_and_not_the_model_family():
    # The same rule that keeps DeepSeek out decides how Google gets in. Google
    # ships both a model family reached over an API and a first-party terminal
    # harness built on it, and only the second is a harness product — so the
    # row is `gemini-cli`/`Gemini CLI`, and the bare model name stays
    # unregistered. A user who types `gemini` gets that exact string and the
    # neutral badge, which is the honest answer: this file knows a CLI, not a
    # model. OpenCode needs no such distinction — it ships no model at all and
    # is pointed at whichever provider its user configures.
    assert harnesses.get("gemini-cli") is not None
    assert harnesses.get("gemini") is None
    assert harnesses.resolve("gemini").accent_dark == harnesses.NEUTRAL_DARK
    assert harnesses.get("opencode") is not None


def _repeated_monograms(entries):
    """Every monogram carried by more than one entry, in first-clash order.

    Args:
        entries: Registry rows, real or fabricated.

    Returns:
        One string per monogram that two rows share. Computed over the rows
        handed in rather than over `known()`, so the sabotage below can ask
        this the same question about a registry that does collide — a check
        spelled inline over the real registry can only ever answer about the
        registry that exists, and cannot show it would notice one that did not.
    """
    seen, repeated = set(), []
    for harness in entries:
        if harness.monogram in seen and harness.monogram not in repeated:
            repeated.append(harness.monogram)
        seen.add(harness.monogram)
    return repeated


def test_no_two_registered_harnesses_share_a_badge_and_a_collision_is_caught():
    # A hard invariant, not a preference: the monogram is the whole badge at
    # the size the panel draws it, so two rows sharing one make two products
    # indistinguishable wherever the display name does not also fit. New rows
    # therefore have to take a free pair — `GC` and `OC` were free.
    assert _repeated_monograms(harnesses.known()) == []
    # And the check has teeth. A row that duplicates a shipped badge is built
    # from a real entry, so the fabricated registry differs from the true one
    # in exactly the field under test and in no other.
    clash = replace(harnesses.get("gemini-cli"), id="gemini-cli-nightly")
    assert clash.monogram == harnesses.get("gemini-cli").monogram
    assert _repeated_monograms([*harnesses.known(), clash]) == ["GC"]


def test_the_registry_never_normalises_a_display_name_into_an_id():
    # No slugify, no case folding, no "they probably meant claude-code". A
    # lookup by display name is a miss, and a miss resolves to the neutral
    # badge under the string exactly as given.
    assert harnesses.get("Claude Code") is None
    resolved = harnesses.resolve("Claude Code")
    assert resolved.id == "Claude Code" and resolved.display_name == "Claude Code"
    assert resolved is not harnesses.get("claude-code")

def test_every_entry_is_complete_and_unambiguous():
    entries = harnesses.known()
    assert len({h.id for h in entries}) == len(entries)
    assert len({h.monogram for h in entries}) == len(entries)   # badges differ
    for harness in entries:
        assert harness.id and harness.display_name
        assert len(harness.monogram) == 2, harness.id
        assert HEX_RE.fullmatch(harness.accent_dark.lower()), harness.id
        assert HEX_RE.fullmatch(harness.accent_light.lower()), harness.id
        assert isinstance(harness.executable_hints, tuple)

def test_every_vendor_entry_carries_a_documentation_url():
    # `custom` is the exception and is meant to be: it names no vendor, so
    # there is no vendor documentation to link. Every other row must have one
    # — an entry we cannot point at is an entry we should not be claiming.
    for harness in harnesses.known():
        if harness.id == harnesses.CUSTOM:
            assert harness.docs == ""
        else:
            assert harness.docs.startswith("https://"), harness.id

def test_the_reg1_disclosure_names_every_field_that_states_an_external_fact():
    # REG1-01. The disclosure beside the two REG-1 rows once said the docs URL
    # was the ONE field that could not be checked in place. False: an owner
    # who read it would confirm two URLs and ship unverified vendor spellings,
    # because `display_name` (how the vendor writes it) and `executable_hints`
    # (what the command line calls it) are external facts of exactly the same
    # kind, verified by nothing in this repository. The external set is
    # DERIVED — every `Harness` field minus the ones the suite pins from the
    # repository alone — so a field added to the dataclass lands external by
    # default, and the comment cannot quietly narrow back down to one field:
    # each member of the set must be named, backticked, inside the REG-1
    # block, or this goes red.
    internal = {
        "id", "monogram",                # test_every_entry_is_complete_and_unambiguous
        "accent_dark", "accent_light",   # well-formedness here, contrast audit
        "adapter",                       # resolves to nothing: no fact to confirm
    }
    external = {field.name for field in fields(harnesses.Harness)} - internal
    assert external == {"docs", "display_name", "executable_hints"}
    lines = Path(harnesses.__file__).read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(lines)
                 if line.strip().startswith("# REG-1."))
    block = []
    for line in lines[start:]:
        if not line.strip().startswith("#"):
            break
        block.append(line.strip())
    disclosure = " ".join(block)
    assert "PROPOSED, not confirmed" in disclosure
    for name in sorted(external):
        assert f"`{name}`" in disclosure, name


def test_the_recommended_ids_are_registry_entries_and_exclude_custom():
    # The wizard numbers these. A recommended id with no entry would render a
    # row with no product behind it.
    assert harnesses.RECOMMENDED
    for harness_id in harnesses.RECOMMENDED:
        assert harnesses.get(harness_id) is not None
    assert harnesses.CUSTOM not in harnesses.RECOMMENDED


# --- the colours are validated as DATA, and only as data ---
# A hue-separation rule was written here and then removed on the owner's
# decision: an HSV gap does not scale with the registry, distorts colours users
# recognise, does nothing for colour-vision deficiency, and is not evidence
# that two things cannot be confused. Identity and status are separated by
# channel — monogram and swatch against glyph, text and chip — and the
# forbidden surfaces for a harness accent are listed in the module docstring
# and enforced structurally in DEC-UI, where the accent is applied. Do not
# reintroduce a colour-distance assertion here.


def test_both_themes_carry_a_well_formed_accent():
    for harness in harnesses.known():
        assert HEX_RE.fullmatch(harness.accent_dark.lower()), harness.id
        assert HEX_RE.fullmatch(harness.accent_light.lower()), harness.id
        assert harness.accent_dark != harness.accent_light, harness.id


# --- an unregistered harness: neutral and stable, never guessed ---


def test_an_unregistered_harness_resolves_to_a_neutral_badge():
    resolved = harnesses.resolve("in-house-sast")
    assert resolved.id == "in-house-sast"
    assert resolved.display_name == "in-house-sast"      # never invented
    assert resolved.monogram == "IH"                    # first two words
    assert resolved.docs == "" and resolved.executable_hints == ()
    custom = harnesses.get(harnesses.CUSTOM)
    assert resolved.accent_dark == custom.accent_dark    # the neutral badge
    assert resolved.accent_light == custom.accent_light

def test_resolving_a_registered_harness_returns_the_registry_entry():
    assert harnesses.resolve("claude-code") is harnesses.get("claude-code")

def test_the_fallback_monogram_is_stable_and_derived_from_the_string_alone():
    for value, monogram in [("kimi cli", "KC"), ("my_own_agent", "MO"),
                            ("gemini", "GE"), ("x", "X"), ("7", "7"),
                            ("(", "?")]:
        assert harnesses.resolve(value).monogram == monogram
    # The WHOLE fallback repeats, not one field of it. Two renders of the same
    # unregistered harness must agree on every attribute, and a field compared
    # with itself could not notice any other one drifting. The identity check
    # is what stops the equality being satisfied by a single shared object.
    first, second = harnesses.resolve("gemini"), harnesses.resolve("gemini")
    assert first == second and first is not second

def test_the_fallback_monogram_is_one_or_two_characters_and_never_padded():
    # An id with one alphanumeric word one character long has no honest second
    # character, and a string with no letter or digit has no first, so the
    # badge says so rather than inventing filler — stating something about a
    # harness nobody supplied is the one thing a badge may not do. `c++` is
    # that first case without being one character long, which is why the
    # promise is phrased over words rather than over the length of the id.
    for value, monogram in [("42", "42"), ("c++", "C"), ("a-", "A"),
                            ("...", "?"), ("-", "?")]:
        assert harnesses.resolve(value).monogram == monogram, value
    # Padding is not a length question — a filler character is the right length
    # and still shows something nobody supplied. So the property is: no more
    # characters than the id's letters and digits offer once upper-cased, and
    # every one of them taken FROM that upper-casing. Upper-casing is where the
    # count lives, because one code point can grow into two — `ß` gives `SS` —
    # and because what it grows into need not be a letter at all: `ǰ` gives `J`
    # plus a COMBINING CARON, so counting only the alphanumerics would call the
    # correct two-character badge padded. The badge is cut back to two rather
    # than padded up to them. `?` is the single character that comes from
    # nowhere, and only an id that offers no letter and no digit may reach it.
    # The table carries non-ASCII on purpose, and the table is the half that
    # does the work: while every row of it was ASCII this loop was green over a
    # `?` badge for `Кодекс`, because it never asked about one. Computing
    # `offered` by a Unicode rule is what makes an extended table fail instead
    # of pass.
    for value in ("x", "7", "42", "c++", "kimi cli", "in-house-sast", "...",
                  *UNICODE_IDS):
        if value in UNICODE_IDS:
            assert templates.NAME_RE.fullmatch(value), value
        monogram = harnesses.resolve(value).monogram
        offered = "".join(char for char in value if char.isalnum()).upper()
        assert 1 <= len(monogram) <= 2, value
        if offered:
            assert len(monogram) <= len(offered), value    # never padded
            assert set(monogram) <= set(offered), value    # never invented
        else:
            assert monogram == "?", value


def test_the_fallback_monogram_reads_a_unicode_id_as_words_not_as_punctuation():
    # `templates.NAME_RE` is Unicode-aware, so an id of nothing but letters is
    # legal in any script — and December never declared an ASCII-only harness
    # id. Splitting one by an ASCII rule finds no words at all and badges every
    # such id `?`, which is what the panel would then draw.
    for value in ("Кодекс", "ΩΩΩ", "中文", "my_own_agent"):
        assert templates.NAME_RE.fullmatch(value), value
    assert harnesses.resolve("Кодекс").monogram == "КО"
    assert harnesses.resolve("ΩΩΩ").monogram == "ΩΩ"
    assert harnesses.resolve("中文").monogram == "中文"
    # The underscore keeps separating words. It is a Unicode word character, so
    # a split that only asked for `\W` would read this as one word and answer
    # `MY` — the initials of three words are what this id has always got.
    assert harnesses.resolve("my_own_agent").monogram == "MO"


def test_a_badge_stays_two_characters_when_upper_casing_expands_a_letter():
    # `"ß".upper()` is `"SS"`: one code point in, two out. Both branches of the
    # fallback upper-case what they picked, so both need the cut afterwards —
    # without it `ßa` badges `SSA` and `ß-agent` badges `SSA` too, three
    # characters wide in a slot the registry sizes at two.
    for value in ("ß", "ßa", "ß-agent", "ǰ"):
        assert templates.NAME_RE.fullmatch(value), value
    assert "ß".upper() == "SS"
    assert harnesses.resolve("ß").monogram == "SS"
    assert harnesses.resolve("ßa").monogram == "SS"        # single-word branch
    assert harnesses.resolve("ß-agent").monogram == "SS"   # two-word branch
    # The other shape of the same expansion, and the one a length rule spelled
    # over alphanumerics gets wrong: `ǰ` upper-cases into `J` plus a COMBINING
    # CARON, two code points of which only the first is a letter. Both are the
    # badge — dropping the mark would leave a plain `J` this id never carried.
    # Built from `CARON` rather than pasted: a combining mark renders as
    # nothing of its own, and an expectation nobody can see is an expectation
    # nobody reviews.
    assert "ǰ".upper() == "J" + CARON
    assert harnesses.resolve("ǰ").monogram == "J" + CARON


# --- the seam a panel renders the registry through ---
# Three public names so DEC-UI-3 never reaches into a private one: a rename in
# here would otherwise land as a broken badge over there, with nothing in this
# suite to catch it in between.


def test_the_neutral_pair_is_public_and_is_what_an_unknown_harness_gets():
    # Only the NAME is new information here. That the pair is well formed is
    # test_both_themes_carry_a_well_formed_accent's job, and that a declared
    # `custom` carries the same pair is already
    # test_an_unregistered_harness_resolves_to_a_neutral_badge's. What nothing
    # else can catch is a rename that leaves every value intact and every
    # panel reaching for a name that is gone.
    unregistered = harnesses.resolve("no-such-harness")
    assert unregistered.accent_dark == harnesses.NEUTRAL_DARK
    assert unregistered.accent_light == harnesses.NEUTRAL_LIGHT


def test_vendors_is_the_registry_minus_the_row_that_names_no_vendor():
    assert [h.id for h in harnesses.vendors()] == [
        h.id for h in harnesses.known() if h.id != harnesses.CUSTOM]


def test_the_payload_is_json_ordered_and_carries_only_the_badge():
    payload = harnesses.as_payload()
    assert [row["id"] for row in payload] == [h.id for h in harnesses.known()]
    assert json.loads(json.dumps(payload)) == payload   # no tuples, no dataclass
    for row, harness in zip(payload, harnesses.known()):
        assert row == {"id": harness.id, "display_name": harness.display_name,
                       "monogram": harness.monogram,
                       "accent_dark": harness.accent_dark,
                       "accent_light": harness.accent_light,
                       "docs": harness.docs}
    # `executable_hints` is documentation for a person and would become a
    # lookup the moment it crossed a wire; `adapter` resolves to nothing yet
    # and would read as a promise that it does. Neither may ride along.
    for row in payload:
        assert "executable_hints" not in row and "adapter" not in row
    # A projection, not a view: editing what one caller got back may not reach
    # the entries every other caller resolves against.
    payload[0]["display_name"] = "Sabotage"
    assert harnesses.as_payload()[0]["display_name"] != "Sabotage"
    assert harnesses.known()[0].display_name != "Sabotage"


# --- additivity: the merger cannot tell a known harness from an unknown one ---


def _harnessed(map_data, primary, reviewer):
    """`ROLES_MAP` with its two harness labels replaced."""
    roles = [{**r, "harness": primary if r["id"] == "impl" else reviewer}
             for r in map_data["cycle"]["roles"]]
    return {**map_data, "cycle": {**map_data["cycle"], "roles": roles}}


def _without_harness(state):
    """`state` with every role's `harness` dropped — and nothing else touched.

    One key deep, like `without_stage`: a recursive scrub would also hide a
    harness label that had leaked into a lane, a finding or the action, which
    is exactly what this comparison exists to forbid.
    """
    roles = [{k: v for k, v in r.items() if k != "harness"}
             for r in state["cycle"]["roles"]]
    return {**state, "cycle": {**state["cycle"], "roles": roles}}


KNOWN_MAP = _harnessed(ROLES_MAP, "claude-code", "codex")
UNKNOWN_MAP = _harnessed(ROLES_MAP, "no-such-harness", "nor-is-this-one")


def test_the_additivity_fixture_has_something_to_protect():
    # The equality below is only as strong as the state it compares, and only
    # meaningful while one map is registered and the other is not.
    assert harnesses.get("claude-code") and harnesses.get("codex")
    assert harnesses.get("no-such-harness") is None
    state = merge.merge(KNOWN_MAP, None, rich_lanes(), [], 0, NOW)
    assert state["kpi"]["disagreements"] == 1 and state["kpi"]["queue"] == 1
    assert state["kpi"]["stale_lanes"] == 1
    assert state["map"]["nodes"][0]["status"] == "contested"

def test_being_in_the_registry_changes_nothing_but_the_label_itself():
    known = merge.merge(KNOWN_MAP, None, rich_lanes(), [], 0, NOW)
    unknown = merge.merge(UNKNOWN_MAP, None, rich_lanes(), [], 0, NOW)
    assert [r["harness"] for r in known["cycle"]["roles"]] != \
        [r["harness"] for r in unknown["cycle"]["roles"]]
    assert _without_harness(known) == _without_harness(unknown)

def test_being_in_the_registry_changes_no_merge_computed_value():
    # The equality above would catch all of these; naming them says which
    # promises DO-4 is making, so a regression reads as a broken promise.
    known = merge.merge(KNOWN_MAP, None, rich_lanes(), [], 0, NOW)
    unknown = merge.merge(UNKNOWN_MAP, None, rich_lanes(), [], 0, NOW)
    assert ([f["review_state"] for f in known["findings"]]
            == [f["review_state"] for f in unknown["findings"]] == ["disagreement"])
    assert known["project_status"] == unknown["project_status"]
    assert known["next_action"] == unknown["next_action"]
    assert known["human_queue"] == unknown["human_queue"]
    assert known["invariants"] == unknown["invariants"]
    assert known["kpi"] == unknown["kpi"]
    assert known["warnings"] == unknown["warnings"]

def test_the_registry_carries_its_hints_as_plain_strings():
    # The shape only. What this does NOT show is that nothing resolves them —
    # that claim is the test below, and this one used to carry its name.
    for harness in harnesses.known():
        assert all(isinstance(hint, str) for hint in harness.executable_hints)
    assert harnesses.get("claude-code").executable_hints == ("claude",)


def _hint_readers(path):
    """Every place in one module that reads an `executable_hints` back out.

    Args:
        path: A `conductor` source file.

    Returns:
        One string per reading site. Declaring the field and writing it are
        the two spellings a registry needs — the annotation in `Harness` and
        the keyword arguments that build the rows — and neither is a read, so
        neither is reported. An attribute access is: `h.executable_hints` is
        the first half of the reverse index, the `.get` on it the second. The
        literal string is reported too, because `getattr(h, "…")` is the same
        read with the name moved into data.
    """
    findings = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Attribute) and node.attr == HINTS:
            findings.append(f"{path.name}:{node.lineno} reads .{HINTS}")
        elif isinstance(node, ast.Constant) and node.value == HINTS:
            findings.append(f"{path.name}:{node.lineno} names {HINTS!r}")
    return findings


def _hint_findings(root):
    """Every hint-reading site under `root`, plus the files the walk parsed.

    Args:
        root: A directory to walk — the real package, or a fabricated tree.

    Returns:
        `(paths, findings)`: every `*.py` under `root`, subpackages included
        (`rglob`, because a package is a tree and a flat listing of it is a
        different, smaller claim), and every reading site found in them. The
        paths come back too because `findings == []` is also what an empty
        walk answers — a caller asserting emptiness has to anchor the walk
        before trusting it.
    """
    paths = sorted(root.rglob("*.py"))
    return paths, [f for path in paths for f in _hint_readers(path)]


def test_the_registry_carries_no_lookup_of_its_own_hints(tmp_path):
    # The module docstring says nothing looks these up and that no code path
    # turns them into a lookup. That is a claim about every module in the
    # package, so it is asked of every module in the package, by parsing —
    # the whole tree, not one level of it: a reviewer answered the flat
    # `glob("*.py")` walk with a real, importable reverse index in a
    # `conductor.adapters` subpackage, and the suite stayed green because
    # only top-level files were ever read. And the walk is anchored before
    # its emptiness is believed, because `findings == []` is also the answer
    # a walk of nothing gives.
    #
    # A REPOSITORY GUARD, not a sandbox, and for the same reason the probing
    # ban says so about itself: a name assembled at runtime walks straight
    # past it, and so does a positional read of the frozen row —
    # `astuple(row)[-1]` is this same field with its name gone entirely.
    # What it stops is a lookup arriving without the ADR the docstring says
    # one would need.
    paths, findings = _hint_findings(Path(harnesses.__file__).parent)
    assert Path(harnesses.__file__) in paths     # the walk saw the registry
    assert findings == []
    # And the parse has teeth: the exact shape it exists to refuse, written
    # out and read back, so an empty finding list is an answer rather than the
    # only thing this function knows how to produce.
    reverse_index = tmp_path / "reverse_index.py"
    reverse_index.write_text(
        f"_BY_HINT = {{hint: row for row in _KNOWN for hint in row.{HINTS}}}\n",
        encoding="utf-8")
    assert _hint_readers(reverse_index) == [f"reverse_index.py:1 reads .{HINTS}"]


def test_a_reverse_index_in_a_subpackage_is_inside_the_walk(tmp_path):
    # DO4-2, the reviewer's diversion, kept as a regression. The index below
    # is the shape that landed in `src/conductor/adapters/detect.py` and left
    # the registry guard green: real, importable, and one directory below the
    # only level the old flat walk ever read. Reachability was the whole hole
    # — the parse recognised the shape from the start — so what this pins is
    # the walk: the same index, one level down a fabricated package, must
    # come back as a finding, and the file that carries it must be among the
    # paths the walk reports having parsed.
    package = tmp_path / "adapters"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "detect.py").write_text(
        "from conductor.harnesses import known\n"
        f"_BY_HINT = {{hint: row for row in known() for hint in row.{HINTS}}}\n"
        "def harness_for(hint):\n"
        "    return _BY_HINT.get(hint)\n",
        encoding="utf-8")
    paths, findings = _hint_findings(tmp_path)
    assert package / "detect.py" in paths
    assert findings == [f"detect.py:2 reads .{HINTS}"]
