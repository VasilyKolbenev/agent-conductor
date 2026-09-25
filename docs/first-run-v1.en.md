# First run of V1 on Windows

Russian original: [first-run-v1.md](first-run-v1.md). Both documents describe the same doors and are kept in step.

You need Python 3.11+, a verifiable December Command build and the supported harnesses already installed. These commands apply to the current V1 candidate: installing an older version from GitHub does not guarantee the new ownership layer, bounded automatic cycles or quota sources.

## Install the candidate

In PowerShell, point at the wheel you were given. For local development you may instead install the exact source tree under review with `pip install -e`.

```powershell
$candidate = 'C:\Downloads\agent_conductor-0.1.0-py3-none-any.whl'
$install = Join-Path $env:LOCALAPPDATA 'DecemberCommand\app-v1'
python -m venv $install
$python = Join-Path $install 'Scripts\python.exe'
$conduct = Join-Path $install 'Scripts\conduct.exe'
& $python -m pip install $candidate
& $conduct --help
```

The help must list the `ownership` command. The Python package version is still `0.1.0`: on its own it does not prove that the current V1 candidate is installed. Use the build file you were handed and its checksum.

The candidate's package files have been installed into a clean venv and checked on Windows (from a locally rebuilt archive whose package files are byte-equal to the candidate's) and, from the candidate wheel itself, on Linux (WSL Ubuntu): `init` → `ownership activate` → two server lifetimes, each stopped by Ctrl+C (SIGINT on Linux) → `closed`. Neither check configured a vendor account, and macOS has not been verified. The details are in the [release notes](release-notes-v1-alpha.md).

## A new project and ownership

For a first acquaintance use a new directory with no earlier December Command data. Your own project's code can be attached later; this scenario does not carry live runs over from another session.

```powershell
$project = 'C:\Projects\DecemberTrial'
New-Item -ItemType Directory -Path $project | Out-Null
& $conduct init --template default-orbit --dir $project
& $conduct ownership activate --legacy-writers-stopped --dir $project
& $conduct ownership status --dir $project
```

Right after activation, `status` reports `active`. The `--legacy-writers-stopped` flag confirms that earlier writing processes have been stopped; in a freshly created project there are none yet.

Activation moves the fresh `conductor/` directory to `conductor.v3/`, creates the `.conduct/` service records and leaves, under the name `conductor`, a file that fences earlier writers. This is the intended change of names: do not rename or delete these objects by hand. A repeated `init` is not needed for an activated project; the new commands find the current data directory themselves.

If the chosen project already holds working data, do not treat this short scenario as a migration. Activation has its own checks for stopped writers, unfinished actions and journal integrity. For a first acquaintance, pick a new directory.

## Connecting tools that are already signed in

Before starting the server, run in an interactive terminal:

```powershell
& $conduct providers --dir $project
```

Repeat for every provider you need. The command keeps the other entries and replaces the chosen provider by its ID. The protocol is chosen automatically.

| Provider | Pinned version | What to supply |
| --- | --- | --- |
| Claude Code | 2.1.239 | Full path to the native executable; `subscription`; the directory of an already completed native login (`CLAUDE_CONFIG_DIR`). |
| Codex | 0.112.0 | Full path to the native executable; `subscription`; the directory of an already completed native login (`CODEX_HOME`). |
| Kimi Code | 0.38.0 | Full path to the native executable; `subscription`; the `KIMI_CODE_HOME` directory with the standard managed OAuth profile. |
| Grok Build | 1.0.5 | Full path to the native executable; `subscription`; the `GROK_HOME` directory with the native cached-token login. |
| DeepSeek Harness | 0.1.0-rc.7 | Full path to Node and, separately, to the DSH entrypoint; `api_key`; the permitted name `DEEPSEEK_API_KEY`. |

For subscriptions choose the first login option and name **that separate native profile in which the login has already been completed**. The wizard prints the login commands but does not run them. A suitable profile that is already signed in needs no second login. An arbitrary main profile with extra plugins, MCP, hooks or a nonstandard model route may be refused: connecting is not the copying of a token file.

While the server runs, keep that profile to the product: do not start your own session of the same tool in it at the same time. After every step the product takes back the per-run state (sessions, shell snapshots) that appeared in the profile during the step, and it cannot tell a parallel session's state from the step's own.

The four native executables need no entrypoint; a `.cmd` or PowerShell wrapper is not a substitute for the native executable. The wizard checks that the paths exist; the match with the pinned version is confirmed at the native call.

At the environment question enter names only. For an ordinary Windows launch the base set is `SYSTEMROOT WINDIR PATH TEMP TMP`; add only the names your tool really needs. On the subscription road do not pass API-key variables: that is a different source of payment. DSH reads the existing value of `DEEPSEEK_API_KEY` from the environment of the process that starts the server. The key's value is never typed into the settings file or into the wizard's answers. For the balance the direct `https://api.deepseek.com` is supported; a nonstandard `DEEPSEEK_BASE_URL` yields no readings from this source.

Finish the configuration, and any work of your own with the same dedicated login profile, before starting the server. If you need to change the configuration later, first stop `conduct up`, then run the wizard and the server again. Provider settings and the selected environment values are read when the server starts.

## Studio and readings

```powershell
& $conduct up --dir $project --port 7777
```

Open the printed address, usually `http://127.0.0.1:7777/`. The terminal stays busy with the server; `Ctrl+C` ends it cleanly. Studio's settings offer Russian and English. While the server runs, the ownership state is `opened`; after a clean exit it is `closed`, and the next `up` can open the project again.

The **Agents** screen holds the configured harnesses and the section on limits, balance and reset. The server reads the sources one after another; the page refreshes its readings once a minute. "Refresh usage" re-reads the server's cache; it starts no model task and no separate request to a provider.

Only Claude's reading has been confirmed live so far. For Claude the product itself reads the subscription's 5-hour and 7-day windows; the observation time shown is the vendor cache's own. While a step of the project is running the reading is not refreshed: it shows "update deferred" with the previous data and its own time. Codex, Grok and Kimi show "The source did not confirm a signed-in account." (the state `not_authenticated`) until a login has been completed in the dedicated login directory named for them; Kimi's usage comes from the vendor's own OAuth usage endpoint and needs that login. DSH shows no data until `DEEPSEEK_API_KEY` is set; its reading is exact monetary amounts, the currency and the availability of funds as the source reports it, and reset does not apply. Missing authorization, an unsupported setting, a source error and a stale observation remain explicit states; none of them becomes a zero spend. "Billing account unknown" means the reading is not merged with the readings of other connections.

Opening Studio starts the quota reads, not model work. Create a task, choose or publish a workflow and open a run. A bounded automatic workflow needs the Policy mode, a preview of the concrete bounds and a separate permission to allow the bounded run. Human decisions that stand in the plan keep waiting for a human.

## Linux and macOS

The `conduct` commands are the same; only the virtual environment's paths (`bin/` instead of `Scripts\`) and the shell around them differ. On Linux (WSL Ubuntu) the install road above — clean venv, `init`, `ownership activate`, two server lifetimes each stopped by SIGINT, `closed` — has passed on the candidate wheel, as a non-root user on ext4, with no vendor account configured. macOS has not been verified: there was no Mac to run it on, and the prepared CI job for Linux and macOS has not run yet.

## If it did not work

- No `ownership` command: a different or older package is installed; check the path to `conduct.exe` and the installed candidate.
- `owner_busy`: the project is already open in another process; end that process cleanly. Re-reading the page does not release the owner.
- `recovery_required`: the previous ending was not confirmed. `ownership recover --dir ...` performs the explicit recovery check and starts no work; do not delete the service files to get past the refusal.
- A provider is unavailable: check the full path and the pinned version. `available` in the list does not yet prove a successful login.
- Quotas are unavailable: check the login mode and the chosen profile; for DSH, that the permitted variable is present in the environment before the server starts. After changing the environment, restart the server.

This document describes the doors as implemented in the source. It is not evidence of a clean wheel install or of a check against live accounts; those are recorded separately.
