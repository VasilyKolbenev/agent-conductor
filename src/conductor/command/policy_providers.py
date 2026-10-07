"""Bind operator pins and registered transport facts without sampling secrets."""
from dataclasses import asdict, is_dataclass

from .adapters.provider import reconstruct_config, reconstruct_contract
from .contract_values import ContractError, _content_digest
from .contracts import frozen_config_bindings


class ProviderAuthority:
    """Built with the same configs, descriptors and registry as execution."""

    def __init__(self, configs, contracts, registry):
        self._configs = {row.provider_id: reconstruct_config(row) for row in configs}
        self._contracts = {row.provider_id: reconstruct_contract(row) for row in contracts}
        self._registry = registry

    def digest(self, config):
        return _content_digest(self.facts(config))

    def facts(self, config):
        selected = sorted(set(frozen_config_bindings(config).values()))
        return {"providers": [self._facts(provider_id) for provider_id in selected]}

    def _facts(self, provider_id):
        config = self._configs.get(provider_id)
        contract = self._contracts.get(provider_id)
        if config is None or contract is None or not contract.available:
            raise ContractError("automation requires a configured available provider")
        adapter = self._registry.resolve(provider_id)
        manifest = next(row for row in self._registry.manifests() if row.adapter_id == provider_id)
        profile = getattr(type(adapter), "profile", None)
        # Profiles contain code-owned arguments, finite caps and login NAME rules,
        # never sampled credentials.
        transport = asdict(profile) if is_dataclass(profile) else {}
        from .adapters.deep_commands import OUTPUT_LIMIT_BYTES
        from .adapters.harness_workspace import FILE_BUDGET, INSTRUCTION_LIMIT
        from .adapters.independent_check import FRAME_LIMIT
        from .adapters.process import STDIN_LIMIT
        return {"config": reconstruct_config(config).as_dict(),
                "contract": reconstruct_contract(contract).as_dict(),
                "manifest": manifest.as_payload(), "transport": transport,
                "output_limits": dict(OUTPUT_LIMIT_BYTES), "file_budget": FILE_BUDGET,
                "input_limits": {"frame": FRAME_LIMIT, "stdin": STDIN_LIMIT,
                                 "instruction": INSTRUCTION_LIMIT},
                "task_channel": task_channel_fact(profile)}


def task_channel_fact(profile):
    """The bound this adapter's task is refused at before its claim (headless_cli._dispatch).

    Review ruling R2: frozen with its unit and scope, so a changed limit changes the digest and an
    old grant is refused rather than reread. None when the class declares no profile.
    """
    if not is_dataclass(profile):
        return None
    from .adapters._procgroup import COMMAND_LINE_LIMIT
    from .adapters.harness_profile import TASK_CHANNEL_STDIN
    from .adapters.process import STDIN_LIMIT
    if profile.task_channel == TASK_CHANNEL_STDIN:
        return {"channel": "stdin", "limit": STDIN_LIMIT, "unit": "utf8_bytes", "scope": "task"}
    return {"channel": "argv", "limit": COMMAND_LINE_LIMIT, "unit": "utf16_units",
            "scope": "command_line"}
