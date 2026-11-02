# Kimi Code 0.38.0 starts in the Windows boundary

Two offline runs on 2026-11-02 used the original Windows x64 binary from the
[0.38.0 vendor release](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai%2Fkimi-code%400.38.0).
The published asset digest, publisher checksum file and downloaded archive agreed:
`80e4de3f2bd7c33ba10cfe3c2282492b0758fae9887537f4ff79ec2022957004`.
The ZIP had one entry, kimi.exe. Its SHA-256 was
`b7e658d06176284384d1e9eb627d11e5a26627b3964bf8787f197915d1484b1e`.

Each process used a temporary project, a distinct install and empty Kimi home,
and the product's Windows AppContainer with internetClient disabled. No account
profile was mounted. The first witness returned exit 0 and the exact version
line `0.38.0`. The second sent only the ACP initialize frame; the CLI returned
exit 0, a valid result and an advertised login method. No authenticate frame,
prompt or model request was sent. The first fixture setup was refused before
spawn because it named a home root instead of an individual attempt directory.
Both measured runs used the normal two-level attempt home.

Base f542382. Outside-Git evidence: Documents/Codex/work/kimi-native-038/
version-evidence.json and acp-evidence.json. This is a native startup check.
Subscription execution still needs a secure credential copy, a real subscription
and an independently checked result. Kimi Desktop is not this pinned binary.
