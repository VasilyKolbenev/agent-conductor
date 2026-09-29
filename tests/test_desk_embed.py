"""Embed mode's pure half (spec 4.5.5), from the real module under Node.

`desk-embed.js` decides whether a desk is embedded by a hub and, when it is, says its location
to the page that frames it in ONE message. The decision is a function of four facts -- is the
window framed, what does the hash ask, what did the server's project claim answer -- so it is
tested as a table, spelled out here and not read back from the module. What the desk does with
the decision is `browser_tests/test_desk_embed.py`'s; the one-`postMessage` rule is
`test_desk_address_source.py`'s.
"""
from __future__ import annotations

from tests.desk_node import run_js

MODULES = {"embed": "desk-embed.js", "address": "desk-hash.js"}
PROJECT = "0123456789abcdef0123456789abcdef"
OTHER = "fedcba9876543210fedcba9876543210"
HUB = "http://127.0.0.1:7700"
ASKS = f"project={PROJECT}&embed=hub"


def _claim(project_id=PROJECT, hub_origin=HUB) -> dict:
    return {"project_id": project_id, "hub_origin": hub_origin, "demo": False, "mode": "active"}


def _decide(rows: list[tuple[bool, str, object]]) -> list:
    """`embedTarget` for each (framed, hash, claim)."""
    return run_js("""
      console.log(JSON.stringify(d.map(([framed, hash, claim]) => embed.embedTarget(
        {framed, address: address.readDeskHash(hash), claim}))));
    """, MODULES, [list(row) for row in rows])


def test_a_framed_window_that_asks_for_embed_and_whose_claim_agrees_embeds_at_the_hubs_origin():
    assert _decide([(True, ASKS, _claim())]) == [HUB]
    assert _decide([(True, f"embed=hub&task=t1&project={PROJECT}&lang=ru", _claim())]) == [HUB]


def test_every_condition_of_embed_alone_keeps_a_desk_from_embedding():
    rows = [
        (False, ASKS, _claim()),                                  # not framed
        (True, f"project={PROJECT}", _claim()),                   # the hash does not ask
        (True, f"project={PROJECT}&embed=parent", _claim()),      # asks for something else
        (True, f"project={PROJECT}&embed=hub&embed=hub", _claim()),  # a repeated key is absent
        (True, "embed=hub", _claim()),                            # asks, with no project claim
        (True, "project=zz&embed=hub", _claim()),                 # a claim that is no project id
        (True, f"project={PROJECT}&project={PROJECT}&embed=hub", _claim()),  # a repeated project
        (True, ASKS, None),                                       # the read gave no claim
        (True, ASKS, "http://127.0.0.1:7700"),                    # a claim that is not an object
        (True, ASKS, [PROJECT, HUB]),                             # nor a list
        (True, ASKS, _claim(project_id=OTHER)),                   # another project's claim
        (True, ASKS, _claim(project_id=None)),                    # a claim of no project
        (True, ASKS, {"project_id": PROJECT}),                    # no hub origin at all
        (True, ASKS, _claim(hub_origin=None)),                    # a project no hub started
    ]
    assert _decide(rows) == [None] * len(rows)


def test_the_hub_origin_must_be_exactly_a_loopback_origin_with_a_port_and_nothing_else():
    refused = ["http://localhost:7700", "https://127.0.0.1:7700", "http://127.0.0.1:7700/",
               "http://127.0.0.1:7700/x", "http://127.0.0.1:0", "http://127.0.0.1:65536",
               "http://127.0.0.1:07700", "http://127.0.0.2:7700", "http://127.0.0.1",
               "http://127.0.0.1:7700 ", " http://127.0.0.1:7700", "HTTP://127.0.0.1:7700",
               "http://127.0.0.1:770a", "http://127.0.0.1:123456", "*", "", "null", 7700, True,
               ["http://127.0.0.1:7700"]]
    accepted = ["http://127.0.0.1:1", "http://127.0.0.1:7700", "http://127.0.0.1:65535"]
    rows = [(True, ASKS, _claim(hub_origin=origin)) for origin in refused + accepted]
    got = _decide(rows)
    assert got[:len(refused)] == [None] * len(refused)
    assert got[len(refused):] == accepted


def test_embed_is_asked_only_by_a_framed_window_whose_hash_says_hub_and_names_a_project():
    rows = [(True, ASKS), (False, ASKS), (True, f"project={PROJECT}"), (True, "embed=hub"),
            (True, f"embed=hub&project={PROJECT}&task=t1")]
    got = run_js("""
      console.log(JSON.stringify(d.map(([framed, hash]) => embed.embedAsked(
        {framed, address: address.readDeskHash(hash)}))));
    """, MODULES, [list(row) for row in rows])
    assert got == [True, False, False, False, True]


def test_the_message_carries_the_location_and_nothing_else_to_the_origin_it_was_given():
    out = run_js("""
      const calls = [];
      const parent = {postMessage: (data, origin) => calls.push([data, origin])};
      embed.announceLocation(parent, d.origin, {project_id: d.project, task_id: "t1",
        run_id: null, secret: "csrf-token", kind: "other", extra: {deep: 1}});
      embed.announceLocation(parent, d.origin, {project_id: d.project, task_id: null,
        run_id: null});
      console.log(JSON.stringify({calls, frozen: calls.map(([data]) => Object.isFrozen(data))}));
    """, MODULES, {"origin": HUB, "project": PROJECT})
    first, second = out["calls"]
    assert first[1] == second[1] == HUB
    assert first[0] == {"kind": "desk-location", "project_id": PROJECT, "task_id": "t1",
                        "run_id": None}
    assert list(first[0]) == ["kind", "project_id", "task_id", "run_id"]
    assert second[0] == {"kind": "desk-location", "project_id": PROJECT, "task_id": None,
                         "run_id": None}
    assert out["frozen"] == [True, True]
