"use strict";
import {element} from "./command-view.js";
import {projectProviders} from "./studio-model.js";
import {projectQuotas} from "./studio-quotas-model.js";
import {snapshotCard} from "./studio-quotas.js";

export const hasSubscriptionSetup = id => id === "codex" || id === "grok-build";
const guideRoot = "https://github.com/VasilyKolbenev/agent-conductor/blob/"
  + "8ab4f0f980db1b0626c56ffc5e2995516d7d35ec/docs/";

export async function readProviderFacts(door) {
  const [catalog, cache] = await Promise.allSettled([door.catalog(), door.quotas()]);
  const providers = projectProviders(catalog.value?.providers);
  const quotas = cache.value ? projectQuotas(cache.value) : null;
  return {providers, quotas};
}

function fact(label, value) {
  return element("div", {}, [element("dt", {text: label}), element("dd", {text: value})]);
}

function quotaState(snapshot) {
  if (!snapshot || snapshot.state !== "observed") return "no_reading";
  return snapshot.freshness === "current" ? "current_reading" : "stale_reading";
}

function subscriptionSnapshot(quotas, row) {
  if (!quotas || row?.auth !== "subscription") return null;
  const pin = quotas.providers.find(p => p.provider_id === row.providerId);
  if (pin?.auth !== "subscription") return null;
  return quotas.snapshots.find(s => s.binding_ids.includes(row.providerId)
    && !Object.hasOwn(s, "balances"));
}

function loginState(row, snapshot) {
  if (row.auth === "unpinned") return "login_unconfigured";
  if (row.auth === "api_key") return "login_api";
  if (snapshot?.reason === "not_authenticated" && snapshot.freshness === "current") {
    return "login_required";
  }
  return "login_subscription";
}

function roleState(row) {
  if (!row) return "no_catalog";
  if (row.availability !== "available" || row.implementation !== "real_experimental"
      || row.auth !== "subscription") return "role_refused";
  if (row.taskRoad === "boundary" && row.controls.includes("dispatch")) return "role_boundary";
  if (row.taskRoad !== "refused" && row.controls.includes("review")) return "role_review_only";
  return "role_refused";
}

export function providerEvidence(id, facts, tr, locale) {
  const area = element("div", {className: "utility-provider-evidence"});
  if (facts) {
    const row = facts.providers.find(p => p.providerId === id);
    const snapshot = subscriptionSnapshot(facts.quotas, row);
    area.append(element("dl", {className: "utility-facts"}, [
      fact(tr("install"), tr(row ? "install_" + row.availability : "no_catalog")),
      fact(tr("login"), tr(row ? loginState(row, snapshot) : "no_catalog")),
      fact(tr("quota"), tr(facts.quotas ? quotaState(snapshot) : "cache_unavailable")),
      fact(tr("role"), tr(roleState(row))),
    ]));
    if (snapshot?.source) {
      const names = new Map(facts.quotas.providers.map(p => [p.provider_id, p.display_name]));
      area.append(element("details", {}, [element("summary", {text: tr("quota_details")}),
        snapshotCard(snapshot, names, {locale, hideStaleQuotas: true})]));
    }
  } else {
    area.append(element("p", {text: tr("reading_facts")}));
  }
  return area;
}

export function subscriptionCard(main, id, facts, tr, locale, active, copy) {
  if (!active) {
    main.append(element("p", {text: tr("setup_active")}));
    return;
  }
  main.append(providerEvidence(id, facts, tr, locale));
  const command = "& $conduct providers --dir $project --subscription " + id;
  const guide = locale === "ru" ? "first-run-v1.md#где-взять-закреплённые-сборки"
    : "first-run-v1.en.md#where-to-get-the-pinned-builds";
  const version = id === "codex" ? "Codex 0.164.0" : "Grok Build 1.0.13";
  main.append(element("h4", {text: tr("setup_subscription")}),
    element("a", {href: guideRoot + guide, target: "_blank", rel: "noopener noreferrer",
      text: tr("install_guide", {version})}),
    element("p", {text: tr("setup_terminal")}), element("code", {text: command}), copy(command),
    element("details", {}, [element("summary", {text: tr("another_terminal")}),
      element("p", {text: tr("setup_paths")})]),
    element("p", {text: tr("setup_finish")}));
}
