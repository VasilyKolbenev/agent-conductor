# `GET /command/runs/<run_id>/controls` — the current contract

**Additive addendum** to `docs/specs/2026-08-13-cockpit-command-api.md` §6.2.

That document's body is the C/API-0 freeze: the record of what was agreed when
it was frozen, two arrays and five provider names. It is not edited to match the
route as it stands now, because a frozen record rewritten to look current stops
being a record of anything. This describes the answer this build sends TODAY,
and the example below is compared with a real `CommandApi.handle` response by
`tests/test_controls_current_contract.py` — so a route that moves without this
document moving reds in the fast suite.

Everything here is ADDITIVE under §6.1: a consumer that reads only the frozen
fields keeps working, and every field named below is one that was not there
before.

## The three top-level arrays

| name | what it answers |
| --- | --- |
| `instances` | this RUN's frozen bindings: what each may be asked to do, and what protects it |
| `providers` | this BUILD and this MACHINE: the reviewed roster, whether or not an operator configured a row |
| `isolation_facts` | the WORDS, once — the sentence each isolation row is rendered with |

`isolation_facts` rides the answer once and is joined to a binding's standings
**by `name`**. It is not repeated under every instance: two copies of a sentence
are two sentences the moment one of them is edited, and the one a person reads
would be the one nobody checks against the guards.

## A provider row: seven names

`provider_id`, `display_name`, `availability`, `implementation`, `controls` are
the frozen five and are unchanged. Two more:

- **`auth`** — the login the operator's own row pinned: `api_key`,
  `subscription`, or `unpinned` where no row named one. It is a fact about
  CONFIGURATION and is no evidence that the login works.
- **`vendor_sandbox`** — the vendor's own sandbox mode, per road, in the
  vendor's own flag words. **Three answers, and they are not two:**
  - `null` — this integration declares nothing. NOT a finding about the vendor.
  - `[]` — declared, and this integration requests no such mode on any road.
  - `[[road, tokens], ...]` — declared, and these are the tokens each road pins.

  A consumer MUST NOT render any of the three as proof that an operating system
  confined anything. What the field reports is what this build ASKS a vendor
  for; whether the vendor's platform enforces it is the vendor's business.

`availability`, `implementation` and `auth` remain three separate closed
vocabularies sharing no value, and `display_name` remains a label to render and
never a fact to parse.

## An instance row: `isolation`, keyed by road

The frozen five (`instance_id`, `adapter_id`, `model`, `controls`,
`argument_schemas`) are unchanged. `isolation` is added, and it is a MAP from
capability to that road's standings — not a list.

It is keyed by road because what protects a step is a fact about the transport
bound to it AND the capability that step takes. A review and a dispatch on one
binding do not run the same checks: a dispatch resolves an instruction and can
promise its bytes, a review is read-only and its output is scanned. One list for
both would have to be their union or their intersection, and each of those is
false for one of the two steps a person confirms.

**Only capabilities the row declares in `controls` appear as keys.** A binding
whose adapter is not registered carries `controls: []` and `isolation: {}` — no
road, and a standing lives on a road.

## A standing: four words, one of which is a protection

| standing | what it says |
| --- | --- |
| `active` | this build applies this check, for this binding, on this road |
| `not_applicable` | this build implements it, and NOT on this road for this transport |
| `stated_absence` | this build openly does not do this |
| `unknown` | nobody established it either way for this configuration |

**Only `active` may be rendered as a protection.** The other three are not
guarantees, and a consumer MUST distinguish them in words a person reads rather
than in an attribute: "nobody measured this" and "this build openly does not do
it" are different things to know before authorizing a run.

A standing is `active` only where the bound transport's own code carries the
check. It is derived from what the implementing class declares and from the
capability, never from the provider's identity — and an adapter that declares
nothing gets `unknown`, never "there are none": a plugin this build has not been
told about is not a plugin this build may report as unprotected.

The vendor's row additionally carries **`vendor_detail`**, whose three answers
are the provider row's three. The KEY marks the row as the vendor's question;
rows without it are not about a vendor mechanism at all.

## The current examples

Two, produced by the route and not written by hand, because one cannot show what
this document claims. Together they carry all four standings and all three
answers of the vendor's sandbox; separately, each is the answer for a kind of
transport a consumer will really meet.

**The first** has one binding whose transport declares two guards on its one
road — so `active` for those, `not_applicable` for everything else this build
implements, and `stated_absence` for the two things it openly does not do — and
beside it one binding nothing is registered for, which is where the empty road
map is seen. An empty road map is not a standing: it is the absence of any road
to carry one.

<!-- CANONICAL:controls_current -->
```json
{
  "instances": [
    {
      "instance_id": "unregistered",
      "adapter_id": "nothing-registered",
      "model": null,
      "controls": [],
      "argument_schemas": {},
      "isolation": {}
    },
    {
      "instance_id": "worker",
      "adapter_id": "example-transport",
      "model": null,
      "controls": [
        "dispatch"
      ],
      "argument_schemas": {
        "dispatch": "deep-arguments-v1"
      },
      "isolation": {
        "dispatch": [
          {
            "name": "uncontained_route",
            "category": "refused_before_spawn",
            "standing": "active"
          },
          {
            "name": "inherited_home_residue",
            "category": "refused_before_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "login_directory_carries_configuration",
            "category": "refused_before_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "unroutable_model",
            "category": "refused_before_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "instruction_bytes_moved",
            "category": "refused_before_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "work_outside_the_item",
            "category": "detected_after_spawn",
            "standing": "active"
          },
          {
            "name": "environment_value_echoed",
            "category": "detected_after_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "profile_home_retained",
            "category": "detected_after_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "login_directory_gained_state",
            "category": "detected_after_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "review_changed_the_tree",
            "category": "detected_after_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "scope_is_declarative",
            "category": "not_isolated",
            "standing": "stated_absence"
          },
          {
            "name": "no_operating_system_boundary",
            "category": "not_isolated",
            "standing": "stated_absence"
          },
          {
            "name": "vendor_sandbox_is_the_vendors",
            "category": "not_isolated",
            "standing": "active",
            "vendor_detail": [
              [
                "dispatch",
                "--sandbox workspace-write"
              ]
            ]
          }
        ]
      }
    }
  ],
  "providers": [
    {
      "provider_id": "example-transport",
      "display_name": "Example Transport",
      "availability": "available",
      "implementation": "real_experimental",
      "auth": "api_key",
      "controls": [
        "dispatch"
      ],
      "vendor_sandbox": [
        [
          "dispatch",
          "--sandbox workspace-write"
        ]
      ]
    }
  ],
  "isolation_facts": [
    {
      "name": "uncontained_route",
      "category": "refused_before_spawn",
      "sentence": "A work route that leaves the project root -- through a portal, a junction or a link planted at a name this build owns -- stops the dispatch. No task is spawned and nothing outside the root is written."
    },
    {
      "name": "inherited_home_residue",
      "category": "refused_before_spawn",
      "sentence": "State of unknown ownership left under the profile home root by an earlier attempt stops the next dispatch before it mints its own."
    },
    {
      "name": "login_directory_carries_configuration",
      "category": "refused_before_spawn",
      "sentence": "A pinned login directory that also carries configuration is refused before any task: configuration there could redirect the provider."
    },
    {
      "name": "unroutable_model",
      "category": "refused_before_spawn",
      "sentence": "A model this provider has no road for is refused before the workspace turn is taken, so nothing is minted for a run that cannot happen."
    },
    {
      "name": "instruction_bytes_moved",
      "category": "refused_before_spawn",
      "sentence": "When a proposal promised the digest of the instruction it previewed and the bytes no longer match, the dispatch stops before the spawn."
    },
    {
      "name": "work_outside_the_item",
      "category": "detected_after_spawn",
      "sentence": "Files changed elsewhere INSIDE the observed work tree -- another work item beside this one -- are found by comparing that tree before and after the child ran. The comparison covers `work/` and nothing above it: a write the child makes outside that tree is not observed here and may not be detected at all. What a detected change costs is publication and independent verification; it is not undone."
    },
    {
      "name": "environment_value_echoed",
      "category": "detected_after_spawn",
      "sentence": "A child that repeated an allowed environment value into its output is caught by scanning what it produced, after it produced it."
    },
    {
      "name": "profile_home_retained",
      "category": "detected_after_spawn",
      "sentence": "A profile home this build could not take back is discovered when the attempt ends. The work is not published and not verified."
    },
    {
      "name": "login_directory_gained_state",
      "category": "detected_after_spawn",
      "sentence": "Undeclared state appearing in the pinned login directory is measured after the spawn, by comparing it with what was declared."
    },
    {
      "name": "review_changed_the_tree",
      "category": "detected_after_spawn",
      "sentence": "A read-only review that wrote to the work tree is found by reading the tree afterwards, and its result is refused."
    },
    {
      "name": "scope_is_declarative",
      "category": "not_isolated",
      "sentence": "`scope` says what a step is FOR. It is recorded, shown and judged against what was touched -- it does not stop the child reading or writing anywhere this user's own account may."
    },
    {
      "name": "no_operating_system_boundary",
      "category": "not_isolated",
      "sentence": "This build starts an ordinary process with this user's rights. It creates no container, no jail and no separate account, and it cannot confine what that process does outside the routes it watches."
    },
    {
      "name": "vendor_sandbox_is_the_vendors",
      "category": "not_isolated",
      "sentence": "Where a vendor ships a sandbox of its own, this build pins it and records it on that provider's own row -- and where a vendor ships none, nothing is claimed. Either way the mechanism is the vendor's, not this build's: a mode it was ASKED for, which its own platform may or may not enforce, and never proof that the operating system confined anything. Which providers have one is answered beside this table rather than inside it."
    }
  ]
}
```

**The second** is the commoner case: transports that declare no guards at
all. Every adapter written before the declaration existed lands here, and so
does every plugin. All of their guard rows read `unknown` — the standing
that says nobody established it, which is not the same as this build having
looked and found nothing.

Their two vendor answers differ, and that is the pair the first example
cannot show: `worker` runs under a provider whose integration reviewed it and
requests no sandbox mode (`[]`, `stated_absence`), and `unmeasured` under one
carrying no reviewed declaration at all (`null`, `unknown`).

<!-- CANONICAL:controls_current_silent -->
```json
{
  "instances": [
    {
      "instance_id": "unmeasured",
      "adapter_id": "unmeasured-transport",
      "model": null,
      "controls": [
        "dispatch"
      ],
      "argument_schemas": {
        "dispatch": "deep-arguments-v1"
      },
      "isolation": {
        "dispatch": [
          {
            "name": "uncontained_route",
            "category": "refused_before_spawn",
            "standing": "active"
          },
          {
            "name": "inherited_home_residue",
            "category": "refused_before_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "login_directory_carries_configuration",
            "category": "refused_before_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "unroutable_model",
            "category": "refused_before_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "instruction_bytes_moved",
            "category": "refused_before_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "work_outside_the_item",
            "category": "detected_after_spawn",
            "standing": "active"
          },
          {
            "name": "environment_value_echoed",
            "category": "detected_after_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "profile_home_retained",
            "category": "detected_after_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "login_directory_gained_state",
            "category": "detected_after_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "review_changed_the_tree",
            "category": "detected_after_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "scope_is_declarative",
            "category": "not_isolated",
            "standing": "stated_absence"
          },
          {
            "name": "no_operating_system_boundary",
            "category": "not_isolated",
            "standing": "stated_absence"
          },
          {
            "name": "vendor_sandbox_is_the_vendors",
            "category": "not_isolated",
            "standing": "unknown",
            "vendor_detail": null
          }
        ]
      }
    },
    {
      "instance_id": "worker",
      "adapter_id": "silent-transport",
      "model": null,
      "controls": [
        "dispatch"
      ],
      "argument_schemas": {
        "dispatch": "deep-arguments-v1"
      },
      "isolation": {
        "dispatch": [
          {
            "name": "uncontained_route",
            "category": "refused_before_spawn",
            "standing": "active"
          },
          {
            "name": "inherited_home_residue",
            "category": "refused_before_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "login_directory_carries_configuration",
            "category": "refused_before_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "unroutable_model",
            "category": "refused_before_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "instruction_bytes_moved",
            "category": "refused_before_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "work_outside_the_item",
            "category": "detected_after_spawn",
            "standing": "active"
          },
          {
            "name": "environment_value_echoed",
            "category": "detected_after_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "profile_home_retained",
            "category": "detected_after_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "login_directory_gained_state",
            "category": "detected_after_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "review_changed_the_tree",
            "category": "detected_after_spawn",
            "standing": "not_applicable"
          },
          {
            "name": "scope_is_declarative",
            "category": "not_isolated",
            "standing": "stated_absence"
          },
          {
            "name": "no_operating_system_boundary",
            "category": "not_isolated",
            "standing": "stated_absence"
          },
          {
            "name": "vendor_sandbox_is_the_vendors",
            "category": "not_isolated",
            "standing": "stated_absence",
            "vendor_detail": []
          }
        ]
      }
    }
  ],
  "providers": [
    {
      "provider_id": "silent-transport",
      "display_name": "Silent Transport",
      "availability": "available",
      "implementation": "real_experimental",
      "auth": "api_key",
      "controls": [
        "dispatch"
      ],
      "vendor_sandbox": []
    },
    {
      "provider_id": "unmeasured-transport",
      "display_name": "Unmeasured Transport",
      "availability": "available",
      "implementation": "real_experimental",
      "auth": "api_key",
      "controls": [
        "dispatch"
      ],
      "vendor_sandbox": null
    }
  ],
  "isolation_facts": [
    {
      "name": "uncontained_route",
      "category": "refused_before_spawn",
      "sentence": "A work route that leaves the project root -- through a portal, a junction or a link planted at a name this build owns -- stops the dispatch. No task is spawned and nothing outside the root is written."
    },
    {
      "name": "inherited_home_residue",
      "category": "refused_before_spawn",
      "sentence": "State of unknown ownership left under the profile home root by an earlier attempt stops the next dispatch before it mints its own."
    },
    {
      "name": "login_directory_carries_configuration",
      "category": "refused_before_spawn",
      "sentence": "A pinned login directory that also carries configuration is refused before any task: configuration there could redirect the provider."
    },
    {
      "name": "unroutable_model",
      "category": "refused_before_spawn",
      "sentence": "A model this provider has no road for is refused before the workspace turn is taken, so nothing is minted for a run that cannot happen."
    },
    {
      "name": "instruction_bytes_moved",
      "category": "refused_before_spawn",
      "sentence": "When a proposal promised the digest of the instruction it previewed and the bytes no longer match, the dispatch stops before the spawn."
    },
    {
      "name": "work_outside_the_item",
      "category": "detected_after_spawn",
      "sentence": "Files changed elsewhere INSIDE the observed work tree -- another work item beside this one -- are found by comparing that tree before and after the child ran. The comparison covers `work/` and nothing above it: a write the child makes outside that tree is not observed here and may not be detected at all. What a detected change costs is publication and independent verification; it is not undone."
    },
    {
      "name": "environment_value_echoed",
      "category": "detected_after_spawn",
      "sentence": "A child that repeated an allowed environment value into its output is caught by scanning what it produced, after it produced it."
    },
    {
      "name": "profile_home_retained",
      "category": "detected_after_spawn",
      "sentence": "A profile home this build could not take back is discovered when the attempt ends. The work is not published and not verified."
    },
    {
      "name": "login_directory_gained_state",
      "category": "detected_after_spawn",
      "sentence": "Undeclared state appearing in the pinned login directory is measured after the spawn, by comparing it with what was declared."
    },
    {
      "name": "review_changed_the_tree",
      "category": "detected_after_spawn",
      "sentence": "A read-only review that wrote to the work tree is found by reading the tree afterwards, and its result is refused."
    },
    {
      "name": "scope_is_declarative",
      "category": "not_isolated",
      "sentence": "`scope` says what a step is FOR. It is recorded, shown and judged against what was touched -- it does not stop the child reading or writing anywhere this user's own account may."
    },
    {
      "name": "no_operating_system_boundary",
      "category": "not_isolated",
      "sentence": "This build starts an ordinary process with this user's rights. It creates no container, no jail and no separate account, and it cannot confine what that process does outside the routes it watches."
    },
    {
      "name": "vendor_sandbox_is_the_vendors",
      "category": "not_isolated",
      "sentence": "Where a vendor ships a sandbox of its own, this build pins it and records it on that provider's own row -- and where a vendor ships none, nothing is claimed. Either way the mechanism is the vendor's, not this build's: a mode it was ASKED for, which its own platform may or may not enforce, and never proof that the operating system confined anything. Which providers have one is answered beside this table rather than inside it."
    }
  ]
}
```
