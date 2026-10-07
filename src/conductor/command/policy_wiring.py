"""Server-owned policy dependencies; construction never starts a driver."""
from .policy_providers import ProviderAuthority
from .policy_service import PolicyService


def owner_check(root):
    from conductor.ownership import require_owner, OwnerRefused
    from .runtime_values import AuthorizationError
    try:
        require_owner(root).check()
    except OwnerRefused:
        raise AuthorizationError("a live project owner is required for bounded execution") from None


def notify_run(api, publish):
    def notify(run_id):
        publish(run_id)
        policy = getattr(api, "_policy", None)
        if policy is not None and policy.driver is not None:
            policy.driver.wake(run_id)
    return notify


def make_policy(api, configs):
    facts = ProviderAuthority(configs, api._providers, api._registry)
    return PolicyService(api._store, api._registry, budget=api._budget, clock=api._clock,
        provider_digest=facts.digest, owner_check=lambda: owner_check(api._store.project_root),
        session=api._session, notify=api._publish_run, provider_facts=facts.facts)
