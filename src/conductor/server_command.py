"""Construct the command workers from one resolved operator configuration."""
from datetime import datetime

from .command.project_claim import ProjectIdentity
from .command.quota_snapshot_view import LIMITS_FILE, HubLimitsView
from .hub.home import ConductHomeInvalid, conduct_home_path


def start_command(subject, root, registry, providers, budget, clock, ids, token_factory):
    from .server import (_resolved_providers, EXECUTION_WORKERS, ExecutionCoordinator,
                         CommandApi, CommandSession, RunStore, QuotaCollector)
    assigned_port = subject.server_address[1]
    owner, launch = subject.project_owner, subject.launch
    # The nonce is the OWNER's: what this process holds, not a value read before it did.
    subject.project_identity = ProjectIdentity(
        project_id=None if owner is None else owner.project_id,
        hub_origin=subject.hub_origin, demo=launch.demo, mode=launch.mode,
        transition_id=launch.transition_id, auto_continue=launch.auto_continue)
    subject.command_session = CommandSession.mint(assigned_port, token_factory)
    subject.command_store = RunStore(root)
    resolution = _resolved_providers(registry, providers, root, clock, ids,
                                     spawns_allowed=launch.mode == "active")
    subject.command_registry = resolution.registry
    subject.command_providers = resolution.contracts
    # A view process polls no quota source: the login is the active project's (4.3.1).
    subject.quota_collector = None if launch.mode == "view" else QuotaCollector(
        subject.command_quotas, resolution.quota_plans,
        clock=lambda: datetime.fromisoformat(clock().replace("Z", "+00:00")))
    subject.command_api = CommandApi(
        subject.command_store, subject.command_registry,
        session=subject.command_session, budget=budget, clock=clock, ids=ids,
        publish_run=subject.clients.publish_run, providers=subject.command_providers,
        quota_service=subject.command_quotas,
        project=subject.broker.project_name, provider_configs=providers)
    if launch.mode == "view":
        _answer_quotas_from_the_hub(subject)
    # The effect belongs to server-owned workers, never to a request thread:
    # the coordinator holds the API's own runtime, so it spends exactly the
    # grants that boundary minted and can spend no others. Each start() mints
    # one worker with its own queue and one token that retires only it.
    subject.command_execution = ExecutionCoordinator(subject.command_api.runtime)
    subject.command_api.attach_execution(subject.command_execution)
    for _worker in range(EXECUTION_WORKERS):
        subject.command_execution.start()
    from .server_policy import start_policy
    start_policy(subject, clock, ids)


def _answer_quotas_from_the_hub(subject) -> None:
    """A view process shows the active project's limits from `<conduct-home>/limits.json`.

    The API takes its quota reader from its constructor, and that parameter is lane L's (4.1.4);
    until it is there the reader is put in the one place the API reads it from, as the driver is
    put into the policy. A home that cannot be named is no data, not a failed start: a hub child
    already judged it when it judged `--status-file`.
    """
    try:
        path = conduct_home_path() / LIMITS_FILE
    except ConductHomeInvalid:
        path = None
    subject.command_api._quota_view = HubLimitsView(path)
