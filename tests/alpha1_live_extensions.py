"""The exact additive delta from frozen ALPHA-1 bytes to current live proposals.

The five historical JSON files stay untouched. A new deep proposal binds its
materials, which changes its preview and then the request's digest. These are
measured LITERAL pins, not values recomputed by the production digest function
being tested. Everything not explicitly named here must still match exactly.
"""


DIGESTS = {
    "sha256:e85b464251fe23eb47bab1239221f196b03ff02bdb86cceac29a329c5692e23e":
        "sha256:cbf9a8415dbee32cccff82af51e568884066197e239bcf0360c962d8fd0086b1",
    "sha256:f9e37cb3c294ac49208242669709146726997c88c66aef9bdc7a6db4d3f1a419":
        "sha256:58e66b100b669b014d6a033ba4a894afa56b15ae1f4c416eec1d8eee031258fc",
    "sha256:6baff3e6aa465eed1f810c6f7dde63f92e64574867245476ec837736d8e7436f":
        "sha256:4768bec1d42475683e836c11c14bdae859ce0b73615553935de572d023145128",
}
REFUSALS = {"proposal_rebind_required": 409}
#: The login each frozen provider row carries now that a row can pin one. Three
#: of them were configured before the field existed, so they carry the login that
#: shipped; the fourth is named by no row at all and carries none. These are
#: LITERAL per-row pins, not a rule recomputed from the row beside them.
LOGINS = {
    "claude-code": "api_key",
    "codex": "api_key",
    "codex-preview": "api_key",
    "codex-unpinned": "unpinned",
}
#: The VENDOR's own sandbox each frozen row now carries, per road. LITERAL
#: per-row pins, not a rule recomputed from the profile beside them -- the point
#: of a frozen artifact is that the expectation is written down, not derived by
#: the code under test.
#:
#: Every row is `null`, and measured to be: this lane's rows are GATED FIXTURE
#: adapters carrying no harness profile, so the integration declares nothing
#: about a vendor sandbox for them. `null` is not `[]`. Writing `[]` here would
#: have put a measured absence into an artifact that measured no such thing --
#: which is the confusion the nullable field exists to prevent, and which this
#: file's first draft made.
SANDBOXES = {
    "claude-code": None,
    "codex": None,
    "codex-preview": None,
    "codex-unpinned": None,
}
#: The third closed provider vocabulary, added to the frozen vocabulary document
#: the UI lane reads: a set the lane must not widen or narrow either.
LOGIN_STATES = ["api_key", "subscription", "unpinned"]
#: The projection document's own prose. It described the two questions a row
#: answered; a row answers three now, and a note that still said two would hand
#: the lane a document whose words contradict its data.
TWO_QUESTIONS = "A row answers two separate questions"
THREE_QUESTIONS = (
    "A row answers three separate questions and keeps them apart: "
    "`availability` is about the operator's machine, `implementation` is about "
    "this build's transport, `auth` is the login the operator's own row pinned "
    "and is no proof that it works, and the three vocabularies share no value. "
    "Rows are joined by `provider_id`; `display_name` is a label to render and "
    "never a fact to parse. Everything else the operator config and the "
    "reviewed contract carry is withheld.")


def current_form(value):
    """Copy a frozen fixture, applying only the independently pinned extension."""
    if isinstance(value, list):
        return [current_form(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: current_form(item) for key, item in value.items()}
    for key in ("preview_digest", "request_digest"):
        if key in result:
            result[key] = DIGESTS.get(result[key], result[key])
    if {"proposal_id", "proposed_at", "preview_digest"} <= result.keys():
        assert "input_binding" not in result, "historical fixture was rewritten"
        result["input_binding"] = "proposal-v1"
    if "refusal_codes" in result and "attempt_states" in result:
        assert not set(REFUSALS) & result["refusal_codes"].keys()
        result["refusal_codes"].update(REFUSALS)
    # Anchored on the key only the vocabulary document's TOP level carries: the
    # observed sub-document inside it repeats two of the state lists, and a
    # looser test would have written the whole closed set into the record of
    # what two runs happened to reach.
    if "observed_in_the_derived_runs" in result:
        assert "auth_states" not in result, "historical fixture was rewritten"
        result["auth_states"] = LOGIN_STATES
    if "note" in result and result["note"].startswith(TWO_QUESTIONS):
        result["note"] = THREE_QUESTIONS
    if {"row_fields", "withheld_from_rows", "rows"} <= result.keys():
        assert "auth" not in result["row_fields"], "historical fixture was rewritten"
        assert "vendor_sandbox" not in result["row_fields"], (
            "historical fixture was rewritten")
        result["row_fields"] = sorted(
            [*result["row_fields"], "auth", "vendor_sandbox"])
        # The login DIRECTORY is withheld from every row: the wire carries which
        # login was pinned and never where its credential is kept.
        result["withheld_from_rows"] = sorted(
            [*result["withheld_from_rows"], "auth_home"])
        for row in result["rows"]:
            row["auth"] = LOGINS[row["provider_id"]]
            row["vendor_sandbox"] = SANDBOXES[row["provider_id"]]
    return result
