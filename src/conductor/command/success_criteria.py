"""What counts as success for one step, derived from the rules that operate.

The Studio carried a "Success criteria" label for as long as it had an inspector,
and for all of that time it said the product could not store one. That was true
and it was also the wrong thing to say, because success for a step is not a
field somebody types -- it is already decided, by rules this build enforces
whether or not anybody writes them down:

- a terminal success must carry a verification that PROVES something
  (``verify_holds`` refuses one that does not, before the receipt is written);
- exactly one identity may answer for that verification, and WHICH one is a fact
  of the frozen plan (``graph_causality.permitted_verifier``);
- a review's own output is a durable artifact that must answer the request that
  asked for it (``artifacts._artifact_answers_its_request``);
- and a plan may demand the verification NAME something (``required_evidence``,
  spent by ``graph_causality.demanded_evidence``).

So the row became a READING rather than a control. Nothing here decides
anything: each clause restates one rule that already runs, and names the layer
that runs it, so a reader can go and check. There is no new durable field, no
new edit word, and nothing a person can set.

WHY IT IS DERIVED HERE AND NOT IN THE BROWSER. Every clause below is a rule
somebody could re-implement in JavaScript from the same node facts, and the copy
would be right until the day the rule moved. A source guard refuses the rule's
words in the Studio's own files for that reason: the window renders the
sentences this module served and holds no opinion about them.

ON THE WORD "SIGNED". This product has no cryptographic signature anywhere --
not a key, not a certificate, not a digest anybody countersigns. A verification
is an adapter's typed answer that this build accepted from one permitted
identity. So the clauses say "Verified by", and a test pins the absence of
"signer", "signature" and "signed" from every sentence this module produces: the
one thing worse than a missing guarantee is a person believing they have it.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import REVIEW_CAPABILITY
from .graph_values import REQUIRED_EVIDENCE

#: What each clause says it was read from. Named rather than described, so a
#: person who doubts a sentence can open the thing that enforces it.
VERIFIED_SOURCE = "the runtime's verification rule"
PLAN_SOURCE = "the frozen plan"
CHAIN_SOURCE = "the store's artifact chain rule"
DEMAND_SOURCE = "the plan's evidence requirement"

#: Words that would promise a guarantee this build does not provide. Held out of
#: every sentence above by a test rather than by care.
FORBIDDEN_WORDS = ("signer", "signature", "signed", "countersign")


def criteria_rows(
        *, kind: object, capability: object, verifier: object, doer: object,
        required_evidence: object,
        arguments: Mapping[str, Any] | None, locale: str = "en") -> tuple[dict[str, str], ...]:
    """Every clause that really operates on one step, in the order they apply.

    A step that carries nothing out answers an empty tuple: nothing is executed
    for it, so no verification is owed and there is nothing to state. That is a
    reading a screen can show as "none", and it is not the same as a step whose
    criteria happen to be short.

    Args:
        kind: The step's kind word.
        capability: What it carries out, or None.
        verifier: The identity the plan names as verifier, or None.
        doer: The identity that carries the step out, or None.
        required_evidence: What the plan demands the verification name.
        arguments: The step's own capability arguments.

    Returns:
        One row per clause, each with the sentence and the layer it was read
        from.
    """
    if kind != "task" or capability is None:
        return ()
    held = arguments if isinstance(arguments, Mapping) else {}
    rows = [
        {"text": _pick("The result must be verified. A step that finished is not a "
                 "step that succeeded, and an unverified result never counts "
                 "as one.", "Результат должен пройти проверку. Завершение шага само по себе не означает успех: непроверенный результат успешным не считается.", locale),
         "source": _pick(VERIFIED_SOURCE, "правило проверки результата", locale)},
        _verified_by(verifier, doer, locale=locale),
    ]
    if capability == REVIEW_CAPABILITY:
        rows.append(_publishes(held, locale=locale))
    if required_evidence in REQUIRED_EVIDENCE:
        rows.append(
            {"text": _pick(f"The verification must name a {required_evidence}. This "
                     "plan asks for more proof than the runtime demands of "
                     "every step, and a verification without it is refused.", f"Проверка должна ссылаться на {required_evidence}. План требует это дополнительное доказательство; без него проверка не принимается.", locale),
             "source": _pick(DEMAND_SOURCE, "требование плана к доказательствам", locale)})
    return tuple(rows)


def _verified_by(verifier: object, doer: object, *, locale="en") -> dict[str, str]:
    """WHO may answer for the verification, and which of the two it is.

    The difference is stated rather than smoothed over. A plan that names a
    separate verifier means evidence from the doer is precisely what must be
    refused; a plan that names none means the identity that did the work is the
    one that answers. A sentence that said only "Verified by X" would read the
    same in both cases and hide the fact a person is choosing between.
    """
    if isinstance(verifier, str) and verifier:
        return {"text": _pick(f"Verified by {verifier}, which this plan names as "
                        "the step's verifier. Evidence from anybody else is "
                        "refused, including from the instance that did the "
                        "work.", f"Проверяет {verifier}, назначенный проверяющим в плане. Доказательства от других участников, включая исполнителя, не принимаются.", locale),
                "source": _pick(PLAN_SOURCE, "замороженный план", locale)}
    if isinstance(doer, str) and doer:
        return {"text": _pick(f"Verified by {doer}, the instance that does the work "
                        "— this plan names no separate verifier.", f"Проверяет {doer}, выполняющий работу: отдельный проверяющий в этом плане не назначен.", locale),
                "source": _pick(PLAN_SOURCE, "замороженный план", locale)}
    return {"text": _pick("Verified by the instance that does the work. This step "
                    "binds none yet, so there is nobody to name.", "Проверяет исполнитель работы. Этот шаг пока не привязан к участнику.", locale),
            "source": _pick(PLAN_SOURCE, "замороженный план", locale)}


def _publishes(arguments: Mapping[str, Any], *, locale="en") -> dict[str, str]:
    """A review's own output, named by the reference its request asked for."""
    ref = arguments.get("result_artifact_ref")
    named = ref if isinstance(ref, str) and ref else None
    if named is None:
        return {"text": _pick("A review must publish its result as a durable "
                        "artifact. This step names no result reference yet, so "
                        "there is nothing for one to answer.", "Рецензия должна сохранить свой результат как артефакт. Ссылка на результат в этом шаге пока не задана.", locale),
                "source": _pick(CHAIN_SOURCE, "правило происхождения артефактов", locale)}
    return {"text": _pick(f"The artifact {named} must stand, published by this "
                    "step's own action and answering the request that asked "
                    "for it — the same reference, from the inputs it named.", f"Артефакт {named} должен быть опубликован действием этого шага и соответствовать его запросу: та же ссылка и указанные входные материалы.", locale),
            "source": _pick(CHAIN_SOURCE, "правило происхождения артефактов", locale)}


def for_plan_node(node: Any, *, locale="en") -> tuple[dict[str, str], ...]:
    """One step of a run's FROZEN plan, read by the names that contract uses."""
    return criteria_rows(
        kind=node.kind, capability=node.capability,
        verifier=node.verifier_instance_id, doer=node.instance_id,
        required_evidence=node.required_evidence, arguments=node.arguments, locale=locale)


def for_template_node(node: Any, *, locale="en") -> tuple[dict[str, str], ...]:
    """One step of a DRAWING, read by the names that contract uses.

    A template binds roles rather than instances, so the identities are the
    role names -- which is what a person drawing sees and what materialization
    will resolve. The clauses are otherwise the same ones, because the rules
    that will operate on the run are the same rules.
    """
    return criteria_rows(
        kind=node.kind, capability=node.capability,
        verifier=node.verifier_role_id, doer=node.role_id,
        required_evidence=node.required_evidence, arguments=node.arguments, locale=locale)


def for_plan(nodes: Any, *, locale="en") -> dict[str, list[dict[str, str]]]:
    """Every step of one plan, keyed by node id, for a read to carry."""
    return {node.node_id: [dict(row) for row in for_plan_node(node, locale=locale)]
            for node in nodes}


def for_document(nodes: Any, *, locale="en") -> dict[str, list[dict[str, str]]]:
    """Every step of one drawing, keyed by node id, for a read to carry."""
    return {node.node_id: [dict(row) for row in for_template_node(node, locale=locale)]
            for node in nodes}


def _pick(english, russian, locale):
    return russian if locale == "ru" else english
