"""The reusable half of a graph: a plan written in ROLES, before any deployment.

``graph_definition`` owns one run's immutable plan. It names an ``instance_id``
per acting node, which is exactly right for a record that must never change --
and exactly wrong for something a person wants to keep, edit and run again
somewhere else. A template that carried an instance would be a plan that could
only ever be run on the machine it was written on.

So this module owns the other half. A ``GraphTemplate`` says what the work IS:
the steps, their topology, the gates, the bounded feedback, which capability
each acting step needs and with what arguments -- and WHO does it only as a
``role_id``, a name the template itself defines. A ``RunBinding`` says who the
roles are for one run. ``materialize`` puts the two together and produces the
existing, unchanged ``GraphDefinition``.

What is left HERE is the deployment: ``RunBinding``, the frozen-configuration
check it is held to, and ``materialize``. The document itself -- ``TemplateNode``,
``GraphTemplate`` and the ``_build`` a template proves itself with -- moved to
``graph_template_document`` when this file crossed the 800-line cap, along that
same seam, and every one of its names is imported back below under the spelling
it has always had. The two paragraphs after this one describe the document, and
they stay because this is still where a reader looks for it.

Two things the template document refuses, and each is the point of it:

- **a field this contract does not name, at any level.** The document is
  CLOSED, so a provider, an instance, an adapter or a run's pass counter is
  refused the way any unknown key is -- there is no second by-name walk beside
  that, because a closed shape leaves one nothing to catch. What a closed shape
  cannot catch is a field ADDED under one of those names later, so
  ``DEPLOYMENT_ONLY_FIELDS`` is held against this contract's own ``_FIELDS``,
  in both directions, by ``tests/test_command_graph_template.py``.
- **a topology this product's base contract would not accept.** Rather than
  restate those rules in a second place where they could drift, a template
  PROVES itself by materializing: the constructor builds a throwaway definition
  against placeholder assignments and throws it away. A template that exists is
  therefore one that materializes, and the rules it is held to are the ones
  ``GraphDefinition`` already owns.

What it does NOT decide: whether the adapter behind an instance can actually
DO the work a role needs. That question already has ONE authority in this
product -- the bound adapter, the schema family it serves a capability
through, and the registry-owned ``validate_arguments`` -- and a contract
module may not ask a registry anything.

It was briefly answered here anyway, from a ``served`` mapping of
``{adapter_id: capabilities}`` the caller supplied. That made a dictionary a
second authority over a fact the registry owns: a capability name nobody
validated, no argument schema, no family, and a synthetic provider that
satisfied the whole check with no registry in the room. A second authority
that can disagree with the first is worse than none, so the verdict moved to
the service and HTTP layer, which may ask.

One claim is RETIRED rather than relocated, and it should be read as a
decision rather than an oversight: ``served``'s "this build has no available
provider for that adapter" was about AVAILABILITY, which ``AdapterRegistry``
has no concept of -- an adapter can be registered while its provider is
unavailable. Availability re-enters through ``provider_projection``, at the
layer that can see it.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import (
    ContractError,
    _freeze_json,
    _id,
    canonical_json,
    frozen_config_bindings,
)
from .graph_definition import GraphDefinition
from .graph_values import _json_object
from .task_contracts import frozen_config_task
#: The document half, re-exported under the names it has always had. Every
#: caller of this module -- five in `conductor.command`, nine in the suite --
#: was importing a template contract and a deployment road from one place, and
#: a split a caller can see is a split that breaks callers to save a file.
from .graph_template_document import (  # noqa: F401 -- re-exported under old names
    DEPLOYMENT_ONLY_FIELDS,
    EXEMPT_FIELD,
    MAX_ROLES,
    SCHEMA_VERSION,
    GraphTemplate,
    TemplateError,
    TemplateNode,
    _build,
    _dispatch_payload,
    _rebuilt_edge,
    _rebuilt_node,
    _revision,
    _schema_spoken,
)
#: Re-exported for the same reason, from one layer further down: it reached
#: callers through this module before the document contract had a file of its
#: own, and `tests/test_command_node_position.py` still asks this module for it.
from .graph_values import (  # noqa: F401 -- re-exported under old names
    POSITION_LIMIT,
    NodePosition,
)


@dataclass(frozen=True)
class RunBinding:
    """Who the roles are, for one run. A total map, and nothing else.

    One instance may carry several roles: a small deployment might have exactly
    one, doing all of them. What is refused is a role the template does not
    name, and a role the template names that this binding leaves out -- either
    would make a plan whose steps nobody, or somebody unnamed, carries out.
    """

    assignments: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # The raw value, and `_json_object` FIRST. Calling `dict(...)` on it
        # first ran the caller's own `keys` before anything had judged it, so a
        # hostile mapping's exception left as this contract's answer -- and a
        # `dict` subclass was laundered into a plain one rather than refused,
        # which is the same door `graph_definition` shuts for the same reason.
        rows = _json_object("run binding assignments", self.assignments)
        settled = {
            _id("role_id", role): _id("instance_id", instance)
            for role, instance in sorted(rows.items())
        }
        # Frozen, not merely rebuilt. A plain dict handed back is one a caller
        # edits in place -- and `covers` reads the role KEYS, so swapping the
        # instance a role runs on passed every check this contract makes.
        object.__setattr__(self, "assignments", _freeze_json(settled))
        object.__setattr__(self, "_assignments_text", canonical_json(settled))
        object.__setattr__(self, "_assignments_witness", self.assignments)

    def bound(self) -> dict[str, str]:
        """The assignments this contract settled, rebuilt from its own record.

        The same identity check the nodes carry, for the same reason: a mapping
        put here afterwards answers `items` however it likes, and this contract
        would have reported whatever it answered as the binding a run follows.
        """
        if self.assignments is not self._assignments_witness:
            raise TemplateError(
                "run binding assignments were replaced after they were "
                "validated; this contract answers only for what it settled"
            ) from None
        return json.loads(self._assignments_text)

    @property
    def instances(self) -> tuple[str, ...]:
        """Every distinct instance this binding uses, sorted."""
        return tuple(sorted(set(self.bound().values())))

    def covers(self, template: GraphTemplate) -> None:
        """Refuse anything but an exact, total cover of the template's roles."""
        wanted, given = set(template.roles), set(self.bound())
        missing, extra = sorted(wanted - given), sorted(given - wanted)
        if missing:
            raise TemplateError(
                f"binding leaves role(s) {missing!r} unassigned; every role a "
                "template names must be carried by some instance")
        if extra:
            raise TemplateError(
                f"binding assigns role(s) {extra!r} the template does not name; "
                "a binding answers for this template and no other")

    def as_dict(self) -> dict[str, Any]:
        return {"assignments": self.bound()}

    @classmethod
    def from_dict(cls, value: object) -> "RunBinding":
        data = dict(_json_object("run binding", value))
        unknown = sorted(set(data) - {"assignments"})
        if unknown:
            raise TemplateError(f"run binding carries unsupported field(s) {unknown!r}")
        return cls(assignments=_json_object(
            "run binding assignments", data.get("assignments", {})))


def _declared(binding: RunBinding, bound: Mapping[str, str]) -> None:
    """Every assigned instance is one the run's FROZEN configuration declares.

    The one fact about a deployment this module may hold, and it holds it from
    the configuration snapshot the run already replays -- not from a caller's
    say-so. Which capabilities an adapter actually serves is a different kind
    of fact, and it is no longer asked here at all: see `materialize`.
    """
    for role, instance in sorted(binding.bound().items()):
        if instance not in bound:
            raise TemplateError(
                f"role {role!r} is assigned instance {instance!r}, which "
                "the run's frozen configuration does not declare")


def _work_scope(config: Mapping[str, Any]) -> str | None:
    """The namespace this run files its work items under, or ``None`` for none.

    Read off the frozen configuration through the same kind of strict reader
    the instance bindings go through. ``None`` is a real answer: a task-less
    run keeps the template's own work item byte for byte.

    What this does NOT do is judge whether a plan's steps agree with the
    binding. That is an admission rule -- a fact about whether this run may be
    GIVEN this plan -- and it lives at the create doors
    (`plan_admission.work_scope_admits`). Asked here, a rule of that kind also
    fired on the comparison road, where a standing plan is re-materialized only
    to compare bytes: a journal frozen before the rule existed was re-judged by
    it, and an honest retry became a refusal of something nobody was writing.

    Args:
        config: The run's frozen configuration snapshot.

    Returns:
        The frozen task's work scope, or ``None`` when this run binds no task.

    Raises:
        ContractError: The frozen task binding is malformed.
    """
    task = frozen_config_task(config)
    return None if task is None else task.work_scope


def materialize(template: GraphTemplate, binding: RunBinding,
                config: Mapping[str, Any], *,
                graph_id: str, run_id: str, created_at: str) -> GraphDefinition:
    """Turn a reusable template and one run's binding into that run's own plan.

    Three steps, and all of them happen before a single field of a durable
    record is written:

    1. the binding covers exactly the template's roles;
    2. every assigned instance is one the run's FROZEN configuration declares,
       which is the only authority on which adapter drives it;
    3. only then is the definition built -- every dispatching step's work item
       filed under the task the configuration binds, or, binding none, held off
       the task shape (`_work_scope`) -- and it is built by the existing,
       unchanged ``GraphDefinition``, which judges the topology as it always has.

    Whether an adapter can DO the work is not decided here, and used to be;
    the module docstring says why not, and where that verdict lives now.

    Args:
        template: The reusable plan, written in roles.
        binding: Who the roles are, for this run.
        config: The run's frozen configuration snapshot.
        graph_id: The stable identity of the plan this run will follow.
        run_id: The run the plan belongs to.
        created_at: The server's clock, never a caller's.

    Returns:
        The immutable ``GraphDefinition`` this run follows.

    Raises:
        TemplateError: The binding or an assigned instance was refused.
        ContractError: The materialized graph is not one this product can
            build, or the frozen task binding is malformed or pushes a work
            item out of the id grammar.
    """
    if type(template) is not GraphTemplate:
        raise TemplateError("materialize takes exactly a GraphTemplate")
    if type(binding) is not RunBinding:
        raise TemplateError("materialize takes exactly a RunBinding")
    binding.covers(template)
    _declared(binding, frozen_config_bindings(config))
    # The run's task, off the same frozen configuration and through the same
    # kind of strict reader: absent is a task-less run whose plan is byte for
    # byte what it always was; present, its scope files every work item.
    return _build(template, binding.bound(), graph_id=graph_id,
                  run_id=run_id, created_at=created_at,
                  work_scope=_work_scope(config))


#: Where the shipped templates live. Data, not code: correcting the default
#: cycle is editing one of these files, and nothing in Python or JavaScript
#: has to move for a corrected cycle to be the one a run materializes from.
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def load_template(name: str) -> GraphTemplate:
    """Read one shipped template by name, through the same door as any other.

    It goes through ``from_dict`` exactly as an operator's own file would, so
    what ships is held to the contract rather than trusted for being ours.
    """
    if not _id("template file", name).replace("-", "").replace(".", "").isalnum():
        raise TemplateError(f"template name {name!r} is not a plain file name")
    path = TEMPLATE_DIR / f"{name}.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        # `from None`, and the OSError is not bound at all. Its `str` carries
        # the FULL path it failed on -- `TEMPLATE_DIR` joined with whatever the
        # caller asked for -- so chaining it printed this server's directory
        # layout under any traceback or error-reporting boundary. The name the
        # caller already knows is the whole of what this refusal owes them.
        raise TemplateError(f"no shipped template named {name!r}") from None
    except json.JSONDecodeError as error:
        raise TemplateError(f"shipped template {name!r} is not JSON: {error}") from None
    return GraphTemplate.from_dict(document)
