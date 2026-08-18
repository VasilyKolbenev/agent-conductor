"""Owner gate G, backend half: the request path does not know who the provider is.

Three claims, none of them a substring wish.

The first is a relation over the source of the HTTP, API, runtime and coordinator
modules, and the identities it looks for are DERIVED from the catalog rather than
typed here -- so a provider added tomorrow is covered by this guard today. Two
tiers, because the two halves carry different weight:

- every backend module, the provider seam included and nothing exempted, is held
  to the load-bearing half: no comparison and no match pattern decides anything
  by a provider's identity;
- every backend module except two named fixture modules is held to the stronger
  half as well: a provider identity does not appear in it at all, in a literal or
  in an identifier. The two exemptions each pin one frozen demo configuration
  whose instance names a product; the exemption covers that mention and nothing
  else, and both files are still held to the load-bearing half above.

The second claim is behavioural and is the one that matters: a provider this
build's source has never heard of, admitted through the registry ALONE, has its
proven control appear in the Cockpit projection and becomes spawn-capable --
with no HTTP, API, runtime or coordinator file mentioning it anywhere.

The third is the other direction: an UNPROVEN control stays absent. A control the
adapter class binds no argument schema to cannot be declared into a catalog
entry, and a control the adapter's own manifest merely claims never reaches the
projection.

The Cockpit half of this gate is not here. It is the existing, unedited panel
source guard `test_the_only_places_that_know_what_product_is_running_are_named_here`
in tests/test_panel_harness.py, with its load-bearing companion
`test_nothing_that_decides_an_order_a_status_or_a_queue_position_knows_a_product`.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from conductor import server
from conductor.command import providers as provider_factory
from conductor.command import runtime
from conductor.command.adapters import (
    AdapterManifest,
    AdapterObservation,
    AdapterVerification,
    PreparedAction,
)
from conductor.command.adapters.deep_contracts import DeepProtocol
from conductor.command.adapters.provider import (
    ProviderCatalogEntry,
    ProviderConfig,
    ProviderConfigError,
    provider_projection,
)
from conductor.command.contracts import ActionResultReceipt
from conductor.command.providers import PROVIDER_CATALOG, resolve_providers

NOW = "2026-08-18T12:00:00Z"
COMMAND_PACKAGE = Path(runtime.__file__).resolve().parent
CONDUCTOR_PACKAGE = COMMAND_PACKAGE.parent
#: The provider seam: the one module allowed to name every provider it catalogues.
PROVIDER_SEAM = "providers.py"
#: Words a provider id shares with every other provider id. Dropping them leaves
#: the family tokens -- and the test below pins what that leaves, so a filter
#: that quietly swallowed a real family would fail rather than pass silently.
GENERIC_ID_WORDS = frozenset({"code", "harness", "preview", "cli", "agent"})
#: Two modules each pin ONE frozen demo configuration whose instance names a
#: product. The exemption covers that mention and nothing else: both are still
#: held to the no-branching half, proved separately below.
FIXTURE_MODULES = {
    "control_loop.py": "the frozen control-loop configuration and its instance id",
    "preview.py": "the frozen preview configuration and its refusing demo adapter",
}


def _backend_sources() -> tuple[Path, ...]:
    """Every HTTP, API, runtime and coordinator module, plus the server itself."""
    package = tuple(sorted(COMMAND_PACKAGE.glob("*.py")))
    return (*package, Path(server.__file__).resolve())


def _family_tokens() -> frozenset[str]:
    """The provider families, read off the catalog's own ids."""
    return frozenset(
        part
        for provider_id in PROVIDER_CATALOG
        for part in provider_id.split("-")
        if part not in GENERIC_ID_WORDS)


def _identity_tokens() -> frozenset[str]:
    """Every string that names a catalogued provider: id, protocol, vendor, family."""
    tokens = set(_family_tokens())
    for provider_id, entry in PROVIDER_CATALOG.items():
        tokens.update({provider_id, entry.protocol, entry.vendor.lower()})
    return frozenset(tokens)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _string_constants(tree: ast.Module) -> list[str]:
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def _identifiers(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
    return names


def _deciding_literals(tree: ast.Module) -> list[str]:
    """Every string a comparison or a match pattern would decide by."""
    literals: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            literals.extend(
                operand.value for operand in operands
                if isinstance(operand, ast.Constant) and isinstance(operand.value, str))
        elif isinstance(node, ast.MatchValue) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                literals.append(node.value.value)
    return literals


def _hits(text: str, tokens: frozenset[str]) -> list[str]:
    lowered = text.lower()
    return sorted(token for token in tokens if token in lowered)


# --- the derived identity set is the right one, and it is not empty ---


def test_the_identities_this_gate_looks_for_are_derived_from_the_catalog():
    """A guard over an empty set proves nothing, so the set is pinned here."""
    assert _family_tokens() == {"claude", "codex", "deepseek", "kimi"}
    identities = _identity_tokens()
    for provider_id, entry in PROVIDER_CATALOG.items():
        assert provider_id in identities and entry.protocol in identities
    assert len(identities) >= len(PROVIDER_CATALOG) * 2


def test_the_modules_this_gate_covers_are_the_ones_it_names():
    names = {path.name for path in _backend_sources()}
    assert {"http_api.py", "http_transport.py", "api_contracts.py", "runtime.py",
            "coordinator.py", "service.py", "server.py"} <= names
    assert PROVIDER_SEAM in names, "the seam is covered by the no-branching half too"
    assert set(FIXTURE_MODULES) <= names, "an exemption names no module"


# --- tier A: nothing anywhere decides by a provider identity ---


@pytest.mark.parametrize(
    "path", _backend_sources(), ids=lambda path: path.name)
def test_no_backend_comparison_decides_anything_by_a_provider_identity(path):
    identities = _identity_tokens()
    offending = [
        literal for literal in _deciding_literals(_tree(path))
        if _hits(literal, identities)]
    assert offending == [], f"{path.name} branches on {offending}"


# --- tier B: the request path does not even know a provider's name ---


@pytest.mark.parametrize(
    "path",
    [path for path in _backend_sources()
     if path.name not in FIXTURE_MODULES and path.name != PROVIDER_SEAM],
    ids=lambda path: path.name)
def test_no_request_path_module_names_a_provider_at_all(path):
    identities = _identity_tokens()
    tree = _tree(path)
    for literal in _string_constants(tree):
        assert not _hits(literal, identities), (
            f"{path.name} carries a provider identity in a literal: "
            f"{_hits(literal, identities)}")
    for name in _identifiers(tree):
        assert not _hits(name, _family_tokens()), (
            f"{path.name} names an identifier after a provider: {name}")


def test_each_exempted_fixture_module_is_exempt_only_from_the_mention():
    """The narrow half of the exemption, stated as a fact rather than as trust."""
    for name, what in FIXTURE_MODULES.items():
        path = COMMAND_PACKAGE / name
        assert path.is_file() and what
        mentions = [literal for literal in _string_constants(_tree(path))
                    if _hits(literal, _identity_tokens())]
        assert mentions, f"{name} needs no exemption; remove it"


# --- a provider the source has never heard of, admitted through the registry ---


PROBE_ID = "gate-probe"
PROBE_DISPLAY = "Gate G probe provider"
PROBE_PROTOCOL = DeepProtocol.FAKE_CODEX_V1.value
PROBE_CONTROL = "dispatch"
#: The manifest claims a control the class binds no schema to. It is UNPROVEN,
#: and the projection must not carry it.
PROBE_UNPROVEN_CONTROL = "stop"


class GateProbeAdapter:
    """A provider no shipped source file mentions, built only by the factory."""

    argument_schemas = {PROBE_CONTROL: "deep-arguments-v1"}

    def __init__(self, config, runner, *, clock, ids) -> None:
        self.manifest = AdapterManifest(
            adapter_id=PROBE_ID, display_name=PROBE_DISPLAY, vendor="gate g",
            version="probe-v1",
            capabilities=("observe", PROBE_CONTROL, PROBE_UNPROVEN_CONTROL),
            docs_url="")
        self._clock = clock
        self._ids = ids

    def observe(self, instance_id, run_id):
        return AdapterObservation(
            adapter_id=PROBE_ID, instance_id=instance_id, run_id=run_id,
            observed_at=self._clock(), health="unknown", available_capabilities=(),
            detail="the probe provider probes nothing")

    def prepare(self, request):
        return PreparedAction(
            adapter_id=PROBE_ID, request=request,
            adapter_payload={"work_item_id": request.arguments["work_item_id"]})

    def execute(self, prepared):
        request = prepared.request
        return ActionResultReceipt(
            receipt_id=self._ids("receipt"), action_id=request.action_id,
            run_id=request.run_id, attempt_id=request.attempt_id,
            instance_id=request.instance_id, outcome="succeeded",
            observed_at=self._clock(), detail="the probe completed", exit_code=0)

    def verify(self, request, result):
        return AdapterVerification(
            adapter_id=PROBE_ID, action_id=request.action_id, state="unavailable",
            observed_at=self._clock(), detail="the probe checks nothing",
            evidence_refs=())


def _probe_entry(**changes) -> ProviderCatalogEntry:
    values = {
        "provider_id": PROBE_ID, "display_name": PROBE_DISPLAY, "vendor": "gate g",
        "protocol": PROBE_PROTOCOL, "capabilities": ("observe", PROBE_CONTROL),
        "schema_pairs": ((PROBE_CONTROL, "deep-arguments-v1"),),
        "lifecycle": ("execute", "observe", "prepare", "verify"),
        "adapter_class": GateProbeAdapter}
    values.update(changes)
    return ProviderCatalogEntry(**values)


def _probe_resolution(tmp_path, entry: ProviderCatalogEntry):
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    executable = tmp_path / "probe.exe"
    executable.write_text("", encoding="utf-8", newline="\n")
    config = ProviderConfig(
        provider_id=PROBE_ID, executable=str(executable.resolve()),
        protocol=PROBE_PROTOCOL)
    counter = {"n": 0}

    def mint(kind: str) -> str:
        counter["n"] += 1
        return f"{kind}-{counter['n']}"

    return resolve_providers(
        [config], root=root, clock=lambda: NOW, ids=mint, environ={},
        catalog={PROBE_ID: entry})


def test_a_provider_added_through_the_registry_alone_reaches_the_projection(tmp_path):
    resolution = _probe_resolution(tmp_path, _probe_entry())
    rows = provider_projection(resolution.contracts)
    assert [row["provider_id"] for row in rows] == [PROBE_ID]
    assert rows[0]["available"] is True
    assert rows[0]["controls"] == [PROBE_CONTROL]
    assert resolution.spawn_capable(PROBE_ID) is True
    assert resolution.registry.resolve(PROBE_ID).manifest.adapter_id == PROBE_ID


def test_the_probe_provider_is_named_in_no_shipped_source_file():
    """This is what "with no other file changed" means, checked rather than said."""
    assert PROBE_ID not in PROVIDER_CATALOG
    assert PROBE_ID not in {entry.provider_id for entry in PROVIDER_CATALOG.values()}
    for path in sorted(CONDUCTOR_PACKAGE.rglob("*.py")):
        assert PROBE_ID not in path.read_text(encoding="utf-8"), path.name
    assert PROBE_ID not in Path(provider_factory.__file__).read_text(encoding="utf-8")


# --- an unproven control stays absent ---


def test_a_control_the_manifest_merely_claims_never_reaches_the_projection(tmp_path):
    resolution = _probe_resolution(tmp_path, _probe_entry())
    claimed = resolution.registry.controls(PROBE_ID)
    assert PROBE_UNPROVEN_CONTROL in claimed, "the adapter really does claim it"
    row = provider_projection(resolution.contracts)[0]
    assert PROBE_UNPROVEN_CONTROL not in row["controls"]
    assert row["controls"] == [PROBE_CONTROL]


def test_a_control_the_adapter_binds_no_schema_to_cannot_be_declared(tmp_path):
    entry = _probe_entry(
        capabilities=("observe", PROBE_CONTROL, PROBE_UNPROVEN_CONTROL),
        schema_pairs=((PROBE_CONTROL, "deep-arguments-v1"),
                      (PROBE_UNPROVEN_CONTROL, "deep-arguments-v1")))
    with pytest.raises(ProviderConfigError, match="exact argument schema"):
        _probe_resolution(tmp_path, entry)


def test_a_declared_control_with_no_schema_is_refused_before_the_catalog_exists():
    with pytest.raises(ProviderConfigError, match="every control capability"):
        _probe_entry(capabilities=("observe", PROBE_CONTROL, PROBE_UNPROVEN_CONTROL))
