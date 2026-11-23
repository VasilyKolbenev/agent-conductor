"""Bind one installed Windows harness from its Studio card in the owner's terminal.

The active project is held by the normal CLI dispatcher. The official sign-in takes
place in the owner's separate PowerShell while this terminal owns the dedicated login.
Only a verified local subscription file may become a new project connection.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

from . import provider_setup as wizard
from . import provider_install_security
from .command.adapters import login_home, login_relay
from .command.adapters.codex_patch import PatchRefused
from .command.adapters.local_test_plan import inventory_digest
from .command.adapters.provider import ProviderConfig, SUBSCRIPTION_AUTH
from .command.containment import first_directory_violation
from .command.providers import PROVIDER_CATALOG, login_hint
from .ownership import OwnerRefused, require_owner
from .ownership_login import LoginScopes

WINDOWS = os.name == "nt"
_WINDOWS_DNS_CARDS = frozenset({"codex", "grok-build"})


def _product():
    return Path.home() / "DecemberCommand"


def _now():
    return datetime.now(timezone.utc)


def _login_acl(path):
    from .command.adapters import _winlaunch, relay_home
    try:
        provider_install_security.verify_login_directory(path)
    except OwnerRefused:
        return "the dedicated login contains an unsafe path"
    return relay_home.login_side_refusal(_winlaunch, path)


def _installation(product, kind):
    adapter = PROVIDER_CATALOG[kind].adapter_class
    version = adapter.profile.reviewed_version
    reviewed = adapter.windows_subscription
    install = product / "harnesses" / kind / version
    if install.is_dir():
        provider_install_security.verify_install(product, install, reviewed.machine_policy)
    try:
        actual = inventory_digest(install, max_file=354558768)
    except (OSError, PatchRefused):
        actual = None
    if actual != reviewed.inventory:
        raise wizard.SetupError(
            f"Install the reviewed {kind} {version} in {install}. The installation does not "
            "match the complete Windows package. See 'Where to get the pinned builds' "
            "in the first-run guide.")
    return install / reviewed.executable


def _login_folder(product, kind):
    home = product / "logins" / kind
    if first_directory_violation((*reversed(home.parents), home)):
        raise wizard.SetupError("The dedicated login path contains an unsafe directory.")
    home.parent.mkdir(exist_ok=True)
    home.mkdir(exist_ok=True)
    return home


def _subscription(scope, kind):
    home = scope.held().home
    reason = _login_acl(home)
    if reason:
        raise wizard.SetupError(f"Cannot use the dedicated login: {reason}.")
    adapter = PROVIDER_CATALOG[kind].adapter_class
    profile = adapter.profile
    reviewed = adapter.windows_subscription
    spec = profile.login_relay
    expected = {*profile.login_scratch, *profile.login_expected, spec.credential,
                "config.toml", *reviewed.extra_login_entries}
    names = login_home.entries(str(home))
    if names is None or not names <= expected:
        raise wizard.SetupError("The dedicated login contains unreviewed files.")
    if not login_home.plain_config(str(home), "config.toml", reviewed.config_forms):
        raise wizard.SetupError("The dedicated login contains an unreviewed vendor configuration.")
    result = login_relay.ready(home, spec, _now(), timedelta(seconds=login_relay.MARGIN_SECONDS))
    return result if isinstance(result, login_relay.Refused) else None


def _check_or_sign_in(scope, config, ask):
    failure = _subscription(scope, config.provider_id)
    if failure is None:
        return True
    home = scope.held().home
    if failure.code not in ("leaf_absent", "expiry_short") or (
            failure.code == "leaf_absent" and any(home.iterdir())):
        wizard._say("The dedicated login was refused: " + failure.phrase
                    + ". Use the first-run guide to renew or repair it.")
        return False
    wizard._say("Open a clean PowerShell from Start without API keys or custom vendor endpoints. "
                "Run these commands and complete the vendor's sign-in there. "
                "Leave this window open:")
    hint = login_hint(config.protocol)
    for line in wizard._login_lines(str(home), config.executable, hint, windows=True):
        wizard._say("    " + line)
    finished = ask("Has the vendor command finished and exited? [y/N]: ")
    if finished.strip().lower() not in ("y", "yes"):
        return False
    failure = _subscription(scope, config.provider_id)
    if failure is not None:
        wizard._say("The dedicated login was refused: " + failure.phrase)
        return False
    return True


def connect(directory, path, standing, kind, ask):
    """Offer a fixed handoff after verifying the installation; persist a pin after owner consent."""
    if not WINDOWS:
        wizard._say("This subscription task connection requires Windows.")
        return 1
    try:
        require_owner(directory)
        product = _product()
        exe = _installation(product, kind)
        home = _login_folder(product, kind)
        config = ProviderConfig(provider_id=kind, protocol=PROVIDER_CATALOG[kind].protocol,
                                executable=str(exe), auth=SUBSCRIPTION_AUTH, auth_home=str(home))
        if kind in _WINDOWS_DNS_CARDS:
            # The reviewed Windows clients need SYSTEMROOT to reach their services.
            # Preserve other names only when reconnecting this same reviewed pin.
            names = next((row.env_allow for row in standing
                          if row.provider_id == kind and replace(row, env_allow=()) == config), ())
            allowed = ["SYSTEMROOT" if name.upper() == "SYSTEMROOT" else name for name in names]
            config = replace(config, env_allow=tuple(dict.fromkeys([*allowed, "SYSTEMROOT"])))
        scopes = LoginScopes()
        with scopes.borrow(str(home)):
            try:
                checked = _check_or_sign_in(scopes, config, ask)
            except (wizard.SetupError, OSError, EOFError) as error:
                wizard._say(str(error) or "The owner terminal closed.")
                return 1
            if not checked:
                return 1
            wizard._say("Verified the local subscription file. Restart Studio after saving to see "
                        "available roles and the provider's quota readings.")
            if kind in _WINDOWS_DNS_CARDS:
                wizard._say("This Windows CLI uses SYSTEMROOT for DNS. Check this name in "
                            "env_allow before confirming the project connection.")
            wizard._summarise(config, path, [row.provider_id for row in standing])
            if not wizard._confirmed(ask):
                return 1
            return wizard._write(path, standing, config, project_root=directory)
    except (OwnerRefused, OSError, wizard.SetupError) as error:
        wizard._say(str(error))
        return 1
