"""The roster projection's implementation and auth arms, held to the two they replaced.

`projectProviders` used to drop a row for an unknown `implementation` in one statement and for
an unknown `auth` in the next:

    if (!PROVIDER_IMPLEMENTATION.includes(row.implementation)) continue;
    if (!PROVIDER_AUTH.includes(row.auth)) continue;

The two became one condition, and the source ledger's count of `continue;` arms went from 14 to
13 with them (tests/test_studio_source.py). A count cannot say that the merge dropped the same
rows and no more, so these witnesses run the packaged module itself and say it. They are pure
Node over one module: no browser, no server, no other project file.
"""
from __future__ import annotations

from tests.desk_node import run_js

#: A roster row for every pairing of a member of each vocabulary, or an odd value, in the two
#: slots the arms judge. Everything else on the row is valid, so the arms are the only judges.
_CORPUS = r"""
const ODD = [
  ["unknown word", "bogus"], ["empty string", ""], ["blank", " "], ["wrong case", "API_KEY"],
  ["padded", " api_key"], ["inherited name", "constructor"], ["prototype key", "__proto__"],
  ["null", null], ["undefined", undefined], ["zero", 0], ["NaN", NaN], ["true", true],
  ["empty array", []], ["array of a member", ["api_key"]], ["empty object", {}],
  ["boxed member", new String("unproven")], ["function", () => "api_key"],
  ["symbol", Symbol.iterator], ["bigint", 10n],
];
const slot = (words) => [...words.map((word) => [`member ${word}`, word]), ...ODD];
const rowFor = (id, implementation, auth) => ({
  provider_id: `p${id}`, display_name: `Provider ${id}`, availability: "available",
  implementation, auth, controls: ["c1"], vendor_sandbox: null,
});
const rows = [];
for (const [implLabel, impl] of slot(m.PROVIDER_IMPLEMENTATION)) {
  for (const [authLabel, auth] of slot(m.PROVIDER_AUTH)) {
    rows.push({ label: `${implLabel} / ${authLabel}`, row: rowFor(rows.length, impl, auth) });
  }
}
"""

_MODULES = {"m": "studio-model.js"}


def test_the_merged_roster_arm_drops_exactly_the_rows_the_two_arms_it_replaced_dropped():
    """Same rows kept, same rows dropped, over every pairing of members and odd values.

    The old statements are replayed one after the other as the oracle. The row is kept when the
    real projection returns it, so a merged condition that joined the halves with `&&`, lost one
    of them, or read a value differently disagrees on a named pairing.
    """
    body = _CORPUS + r"""
    const replaced = (row) => {
      if (!m.PROVIDER_IMPLEMENTATION.includes(row.implementation)) return false;
      if (!m.PROVIDER_AUTH.includes(row.auth)) return false;
      return true;
    };
    const kept = (row) => m.projectProviders([row]).length === 1;
    console.log(JSON.stringify({
      rows: rows.length,
      kept: rows.filter((r) => kept(r.row)).length,
      members: m.PROVIDER_IMPLEMENTATION.length * m.PROVIDER_AUTH.length,
      disagree: rows.filter((r) => kept(r.row) !== replaced(r.row)).map((r) => r.label),
    }));
    """
    answer = run_js(body, _MODULES)

    assert answer["disagree"] == [], f"the merged arm judges differently: {answer['disagree']}"
    assert answer["kept"] == answer["members"], "only the member pairings may be kept"
    assert answer["rows"] > answer["members"], "the corpus holds no odd value, so it proves nothing"


def test_the_roster_projection_answers_every_odd_implementation_and_auth_with_a_frozen_list():
    """A value the arms do not know is a dropped row, never a thrown error or a refused payload.

    This is the decoration side of the module's rule: the roster is poorer and the rest of the
    answer still renders. A merged condition that dereferenced the value, or that answered with
    `null`, would take the whole read down with one bad row.
    """
    body = _CORPUS + r"""
    const refused = rows.filter(({ row }) => {
      try {
        const out = m.projectProviders([row]);
        return !(Array.isArray(out) && Object.isFrozen(out));
      } catch (error) {
        return true;
      }
    }).map((r) => r.label);
    console.log(JSON.stringify({ rows: rows.length, refused }));
    """
    answer = run_js(body, _MODULES)

    assert answer["refused"] == [], f"the projection refused instead of dropping: {answer}"
    assert answer["rows"] > 9, "the corpus holds no odd value, so it proves nothing"
