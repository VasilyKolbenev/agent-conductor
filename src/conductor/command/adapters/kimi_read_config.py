"""Bind a code-owned Kimi Read profile to a single offline Windows review attempt."""
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import tomllib

from ...ownership_native import NativeHold
from .login_relay import CREDENTIAL_LIMIT
from .process_profile import ProfileRefused


def _refused(detail):
    return ProfileRefused("profile_acl_invalid", detail)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class KimiReadConfig:
    profile_sha256: str
    config_sha256: str
    content: bytes = field(repr=False)


def read_role_config(source, *, tools=("Read",)):
    """Render the selected managed model and region into a fresh, fixed-tool config."""
    from .kimi_code import _managed_profile

    if tools != ("Read",):
        raise _refused("only the fixed Kimi Read tool set is admitted")
    if not isinstance(source, bytes) or not 0 < len(source) <= CREDENTIAL_LIMIT:
        raise _refused("Kimi source profile has an invalid size")
    try:
        config = tomllib.loads(source.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise _refused("Kimi source profile is not valid TOML") from None
    key = _managed_profile(config)
    if key is None:
        raise _refused("Kimi source profile is not a managed login")
    alias = config["default_model"]
    model = config["models"][alias].get("model")
    slug = r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}"
    if (not re.fullmatch("kimi-code/" + slug, alias) or not isinstance(model, str)
            or not re.fullmatch(slug, model)):
        raise _refused("Kimi selected model is not supported by the Read profile")
    provider = config["providers"]["managed:kimi-code"]
    lines = [
        f"default_model = {json.dumps(alias)}", '[providers."managed:kimi-code"]',
        'type = "kimi"', 'base_url = ' + json.dumps(provider["base_url"]), 'api_key = ""',
        '[providers."managed:kimi-code".oauth]', 'storage = "file"', 'key = ' + json.dumps(key),
    ]
    if "oauth_host" in provider["oauth"]:
        lines.append('oauth_host = ' + json.dumps(provider["oauth"]["oauth_host"]))
    lines.extend([f'[models.{json.dumps(alias)}]', 'provider = "managed:kimi-code"',
                  'model = ' + json.dumps(model), '[tools]', 'enabled = ["Read"]'])
    content = ("\n".join(lines) + "\n").encode("utf-8")
    return KimiReadConfig(_sha(source), _sha(content), content)


def _read(path):
    with path.open("rb") as stream:
        data = stream.read(CREDENTIAL_LIMIT + 1)
    if len(data) > CREDENTIAL_LIMIT:
        raise _refused("Kimi profile exceeds its size limit")
    return data


@contextmanager
def bind_read_config(paths, expected, sid, native):
    """Hold the staged source and fixed file until the attempt gives up its profile."""
    if type(expected) is not KimiReadConfig:
        raise _refused("Kimi read-role preview is missing")
    source = paths["home"] / "config.toml"
    target = paths["kimi_state"] / "config.toml"
    with closing(NativeHold(source)) as source_hold:
        actual = read_role_config(_read(source))
        if actual != expected:
            raise _refused("Kimi source profile or preview digest changed")
        source_hold.check()
        try:
            fresh = target.open("xb")
        except FileExistsError:
            raise _refused("Kimi config already exists in the attempt") from None
        with fresh as stream:
            stream.write(actual.content)
            stream.flush()
            os.fsync(stream.fileno())
            created = os.fstat(stream.fileno())
        with closing(NativeHold(target, grants=True)) as hold:
            if not os.path.samestat(created, target.lstat()) or _read(target) != actual.content:
                raise _refused("Kimi generated configuration changed")
            _, _, owner = native.acl_snapshot(hold)
            acl = f"O:{owner}D:P(A;;FA;;;SY)(A;;FA;;;{owner})(A;;0x120089;;;{sid})"
            native.acl_set(hold, acl, protected=True)
            observed, protected, actual_owner = native.acl_snapshot(hold)
            if not protected or actual_owner != owner or not native.acl_equal(observed, acl):
                raise _refused("Kimi generated configuration ACL differs")
            yield {"source_sha256": actual.profile_sha256, "config_sha256": actual.config_sha256,
                   "identity": list(hold.identity)}
            hold.check()
            source_hold.check()


def valid_binding(binding):
    fields = {"source_sha256", "config_sha256", "identity"}
    if not isinstance(binding, dict) or set(binding) != fields:
        return False
    ident = binding["identity"]
    return (type(ident) is list and len(ident) == 2
            and all(type(i) is int and i >= 0 for i in ident)
            and all(type(binding[key]) is str and re.fullmatch("[0-9a-f]{64}", binding[key])
                    for key in ("source_sha256", "config_sha256")))


def check_retiring_config(state, binding, *, retiring):
    target = Path(state) / "config.toml"
    try:
        target.lstat()
    except FileNotFoundError:
        if retiring:
            return
        raise _refused("Kimi bound configuration disappeared before retirement") from None
    with closing(NativeHold(target)) as hold:
        if (list(hold.identity) != binding["identity"]
                or _sha(_read(target)) != binding["config_sha256"]):
            raise _refused("Kimi bound configuration changed before retirement")
        hold.check()
