"""Construct the command workers from one resolved operator configuration."""
from datetime import datetime



def start_command(subject, root, registry, providers, budget, clock, ids, token_factory):
    from .server import (_resolved_providers, EXECUTION_WORKERS, ExecutionCoordinator,
                         CommandApi, CommandSession, RunStore, QuotaCollector)
    assigned_port = subject.server_address[1]
    subject.command_session = CommandSession.mint(assigned_port, token_factory)
    subject.command_store = RunStore(root)
    resolution = _resolved_providers(registry, providers, root, clock, ids)
    subject.command_registry = resolution.registry
    subject.command_providers = resolution.contracts
    subject.quota_collector = QuotaCollector(
        subject.command_quotas, resolution.quota_plans,
        clock=lambda: datetime.fromisoformat(clock().replace("Z", "+00:00")))
    subject.command_api = CommandApi(
        subject.command_store, subject.command_registry,
        session=subject.command_session, budget=budget, clock=clock, ids=ids,
        publish_run=subject.clients.publish_run, providers=subject.command_providers,
        quota_service=subject.command_quotas,
        project=subject.broker.project_name, provider_configs=providers)
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
