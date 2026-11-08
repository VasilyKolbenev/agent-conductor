# Your first real project

[English](first-run-v1.en.md) · [Русский](first-run-v1.md) · [Documentation](index.md)

**Goal:** open Studio for a new project, connect a coding tool, and understand how to start work deliberately.
If you only want to see the interface, start with the [account-free demo](../README.md#try-the-demo).

If your project and subscriptions are already connected, open **Desk → New task**.

1. **Result and project.** Describe the result you want, for example “Find why the
   counter includes failed runs”. Choose where the task gets its files.
2. **Team and cycle.** Use the standard Dalio cycle or choose your own. Check who
   will do the work and who will verify it. Expand the role settings to change an assignment.
3. **Review and start.** Read the action and time limits and where the cycle will
   wait for you. Enter your name and press **Start** when the terms match your task.
   At the final decision, open the result and the independent check before you accept.

For a published cycle, the wizard shows the selected revision. If a teammate continues
editing that workflow, your task keeps the displayed version, including after a reload.

You need Python 3.11+, a V1 candidate build, and the native coding tools you intend to use.
A **wheel** is a Python installation file ending in `.whl`; a **virtual environment** is a folder that keeps this installation separate.

If you already have a local project folder, use it after installing the build. First configure the
shared harness profile once in a terminal: `conduct providers --profile`. Then stop other
`conduct up` processes and agents working in that folder, and explicitly add it:

```text
conduct projects add --dir "<absolute path to folder>" --legacy-writers-stopped
```

Replace the bracketed text with the folder's actual absolute path. The command checks the folder
and git, creates project data if needed, copies the profile configuration, and registers the
project. It does not start a harness or make a paid call. If `conduct hub` is already running,
the project appears on its page after a data refresh; the command does not change the active
project.
For development from source, use [CONTRIBUTING](../CONTRIBUTING.md).

## 1. Install the identified build

Use the wheel and SHA256 published for the candidate by the maintainer or its linked CI run.
Do not assume that a default-branch install or a package named `0.1.0` is the same candidate.
The [release notes](release-notes-v1-alpha.md) record acceptance evidence; this tutorial is not a platform-certification claim.

<details open>
<summary><strong>Windows · PowerShell</strong></summary>

On a fresh PC, first create an empty `%USERPROFILE%\DecemberCommand` folder. In Explorer, open its Properties → Security → Advanced. Disable inheritance and keep Full control for your account, SYSTEM and local Administrators only, applied to this folder, subfolders and files. Check these entries before putting programs or logins here. If the folder already contains an installation, check its existing permissions and build with the maintainer. Obtain the wheel and its SHA256 from the same identified release. Run the following in your own PowerShell, changing `$wheel` if the file is elsewhere.

```powershell
$env:PYTHONPATH = ''
$wheel = Join-Path $env:USERPROFILE 'Downloads\agent_conductor-0.1.0-py3-none-any.whl'
$expected = Read-Host 'Candidate wheel SHA256'
if ($expected -notmatch '^[0-9a-fA-F]{64}$' -or (Get-FileHash -LiteralPath $wheel).Hash -ne $expected) { throw 'Wheel SHA256 mismatch' }
$source = Read-Host 'Source commit of this wheel (40 hex digits)'
if ($source -notmatch '^[0-9a-fA-F]{40}$') { throw 'Invalid source commit' }
$install = Join-Path $env:USERPROFILE ("DecemberCommand\product\" + $source.Substring(0,12) + "\venv")
if (Test-Path -LiteralPath $install) { throw 'This build directory already exists' }
py -3 -m venv $install
if ($LASTEXITCODE) { throw 'venv failed' }
$python = Join-Path $install 'Scripts\python.exe'
$conduct = Join-Path $install 'Scripts\conduct.exe'
& $python -m pip install --no-index --no-deps $wheel
if ($LASTEXITCODE) { throw 'wheel installation failed' }
& $conduct --help
```

If `py` is not installed, use the full path to a Python 3.11+ `python.exe` instead of `py -3`.

Use this protected product directory for subscription tasks and its sibling `harnesses` directory for the pinned Windows binaries.

</details>

<details>
<summary><strong>macOS / Linux · terminal</strong></summary>

Use a fresh installation directory and the actual wheel path. Compare its hash with the supplied SHA256.
Keep this terminal open for the next steps.

```sh
wheel="$HOME/Downloads/agent_conductor-0.1.0-py3-none-any.whl"
python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$wheel"
install_dir="$HOME/.local/share/december-command/app-v1"
python3 -m venv "$install_dir"
python_bin="$install_dir/bin/python"
conduct="$install_dir/bin/conduct"
"$python_bin" -m pip install "$wheel"
"$conduct" --help
```

</details>

**You should see:** CLI help containing `ownership`, `providers`, and `up`.
If they are missing, check the executable path and build before continuing.

Check that the maintainer identifies the wheel, its hash and its supported operations together. The older build described by the September release notes predates this Windows isolation.

## 2. Create a fresh trial project

Use a new folder for your first run. Choose a different name if `DecemberTrial` already contains project data.

On Windows keep the project path short: at most 82 characters, like `%USERPROFILE%\DecemberTrial`.
`init`, activation, and `up` work at any length, but saving a workflow draft is refused with
`windows_path_too_long` when the project path plus 49 plus the length of the workflow identifier
(up to 128 characters) exceeds 259, the path budget this build keeps for a draft.
For a draft the project-root limit is 82 (root + 49 + identifier ≤ 259).
`conduct projects add` has its own, separate refusal, `root_path_too_long`, with its own limit: the
project path must not exceed 100 characters; it does not affect `init`, activation, or `up`.

**Windows**

```powershell
$project = Join-Path $env:USERPROFILE 'DecemberTrial'
New-Item -ItemType Directory -Path $project | Out-Null
& $conduct init --template default-orbit --dir $project
& $conduct ownership activate --legacy-writers-stopped --dir $project
& $conduct ownership status --dir $project
```

**macOS / Linux**

```sh
project="$HOME/DecemberTrial"
mkdir "$project"
"$conduct" init --template default-orbit --dir "$project"
"$conduct" ownership activate --legacy-writers-stopped --dir "$project"
"$conduct" ownership status --dir "$project"
```

**You should see:** a bootstrap instruction after `init`, then ownership state `active` after activation.
The bootstrap text helps an agent fill out the project map; printing it does not start that agent.

Ownership means that this instance controls writes to the project's records.
Activation moves `conductor/` data to `conductor.v3/`, creates `.conduct/` service records,
and leaves a file named `conductor` to refuse older writers. Do not rename or remove these objects manually.
The flag `--legacy-writers-stopped` confirms that old writing processes have stopped; a fresh trial has none.
This is a new-project tutorial, not a migration procedure for existing runs.

## 3. Connect the tools you will use

A **provider** is a configured connection to a harness: its executable, login profile, and allowed environment.
You do not have to connect all five just to explore; executing a chosen workflow requires all participants it uses to be ready.

Run the interactive wizard, once for each needed connection:

```powershell
# Windows
& $conduct providers --dir $project
```

```sh
# macOS / Linux
"$conduct" providers --dir "$project"
```

| Tool | Version pinned by this candidate | Supply to the wizard | Task road in V1 |
| --- | --- | --- | --- |
| Claude Code | 2.1.239 | Native `claude.exe`; set `CLAUDE_CONFIG_DIR` to the dedicated login folder. | Windows subscription tasks; a live Goal completed. |
| Codex | 0.164.0 | The native Windows x64 executable in the layout below; set `CODEX_HOME` to the dedicated login folder. | Windows subscription tasks; the recorded Goal used `gpt-6.1-sol`. |
| Kimi Code | 0.38.0 | Native Kimi CLI; dedicated `KIMI_CODE_HOME` and subscription sign-in. | The current pin supports the subscription usage source. Its subscription task is refused before spawn in this build; no live task result is verified. |
| Grok Build | 1.0.13 | Native `grok.exe`; dedicated `GROK_HOME` and subscription sign-in. | Read-only review on Windows. A live subscription diagnosis completed and passed the rehearsal gate. |
| DeepSeek Harness | 0.1.0-rc.7 | Node executable **and** DSH script entrypoint; API-key mode; allowed name `DEEPSEEK_API_KEY`. | The same API-key mode. |

A configured connection does not mean a task will run: see [Where tasks run in this build](#where-tasks-run-in-this-build).

### Where to get the pinned builds

Install each pinned tool under `%USERPROFILE%\DecemberCommand\harnesses\<name>\<version>\`. Use the protected root from step 1. The wheel does not install the vendor tools. Use trusted release files matching the reviewed hashes.

- **Claude Code 2.1.239.** Take `claude.exe` of that version from the release store that the
  vendor's own installer reads, and compare its sha256 with `platforms.win32-x64.checksum` in the
  `manifest.json` of the same version there:

  ```text
  https://downloads.claude.ai/claude-code-releases/2.1.239/win32-x64/claude.exe
  https://downloads.claude.ai/claude-code-releases/2.1.239/manifest.json
  ```

  Place the file in `...\harnesses\claude-code\2.1.239\`.
- **Codex 0.164.0, Windows x64.** Get `@openai/codex@0.164.0` and `@openai/codex@0.164.0-win32-x64` from the npm registry. Compare their SHA256 with the GitHub release assets before extraction. The main tarball is `afb117ec0d382744583dd13154ba0ca6b0f1980f8ed6a23bffb3aaadb6226e30`; the Windows tarball is `4fbd23473a2fc223396cdd8490d3f658d368438134c12a3f1dac9d1e2041a65b`. Extract the contents of each `package/` into `...\harnesses\codex\0.164.0\node_modules\@openai\codex` and `...\harnesses\codex\0.164.0\node_modules\@openai\codex-win32-x64` respectively. Keep the complete packages, including resources beside `vendor\x86_64-pc-windows-msvc\bin\codex.exe`. [Reviewed files and hashes](recovery/2026-10-20/tasks/H5-CODEX-COMPAT-A-INVENTORY.json).
- **Grok Build 1.0.13, Windows x64.** Check the vendor's pinned `grok.exe` against SHA256 `bf43dc75f5478a106eab1e86d422c963e4dbe9666cf14dab363733d27bf1e672` before copying it to `...\harnesses\grok-build\1.0.13\grok.exe`. [WinGet manifest](https://raw.githubusercontent.com/microsoft/winget-pkgs/master/manifests/x/xAI/GrokBuild/1.0.13/xAI.GrokBuild.installer.yaml).
- **Kimi Code 0.38.0, Windows x64.** For subscription quota reads, download `kimi-code-win32-x64.zip` from the CLI release. Verify the archive SHA-256, `80e4de3f2bd7c33ba10cfe3c2282492b0758fae9887537f4ff79ec2022957004`. Extract `kimi.exe` and check its SHA-256, `b7e658d06176284384d1e9eb627d11e5a26627b3964bf8787f197915d1484b1e`. Supply `...\harnesses\kimi-code\0.38.0\kimi.exe` to the wizard. [MoonshotAI release](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai%2Fkimi-code%400.38.0).

Windows x64 downloads: [Codex main archive](https://registry.npmjs.org/@openai/codex/-/codex-0.164.0.tgz), [Codex Windows archive](https://registry.npmjs.org/@openai/codex/-/codex-0.164.0-win32-x64.tgz), [Grok binary](https://x.ai/cli/grok-1.0.13-windows-x86_64.exe). Use `Get-FileHash -Algorithm SHA256 -LiteralPath <downloaded-file>` and compare with the matching value above before extraction or execution.

**Run the wizard while the server is stopped** (Ctrl+C in its window; the command refuses with
`owner_busy` otherwise), then start `conduct up` again: providers are read once, at startup.

In the wizard the question about the login reads: `1` is the tool's own subscription login, `2` is a
credential read from the environment. Under it the wizard prints a note (English only) that says
what `1` does for this tool:

Choose `1` for your subscription. For Claude Code, Codex and Grok Build, enter `%USERPROFILE%\DecemberCommand\logins\<id>` as an expanded full path. For example, enter the path returned by `Join-Path $env:USERPROFILE "DecemberCommand\logins\codex"`. The tool signs in there. During an admitted Windows task the isolated process receives a temporary copy without the refresh token. The Agents screen shows which roles you can assign. For Kimi, check the capability of your wheel and treat execution as pending until the live test passes.

`env_allow` is the list of allowed environment variable names (never values).

To reuse these connections in several projects, configure the shared profile once
in a terminal with `conduct providers --profile` (repeat for each connection).
It lives at `~/.december-command/providers.json`, or under your `CONDUCT_HOME`.
Then apply it to each **stopped** project:

```powershell
& $conduct providers --dir $project --from-profile
```

```sh
"$conduct" providers --dir "$project" --from-profile
```

Applying the profile asks no questions. It replaces connections with the same
provider id and preserves other project connections. Login directories stay in
place; credentials and login files are not copied. A malformed profile refuses
the whole operation and leaves the project file unchanged. You can still use
the project-specific wizard above for an individual project.

For the four subscription tools, use the native executable, not a `.cmd` or PowerShell wrapper.
The wizard checks paths; the native call checks the pinned version. A newer release is not automatically interchangeable.
The DSH desktop application is not a substitute for the CLI entrypoint in this configuration.

For a subscription, use a dedicated login folder of the product, never your own profile of the tool.
Create the login folder with `New-Item` and run the wizard's commands **in a separate PowerShell window**.
They set the login directory and call the vendor's sign-in command. For Kimi, one additional line
disables CLI updates in that window. For example:

```powershell
# Claude Code
$login = Join-Path $env:USERPROFILE 'DecemberCommand\logins\claude-code'
New-Item -ItemType Directory -Force -Path $login | Out-Null
$env:CLAUDE_CONFIG_DIR = $login
$claude = Join-Path $env:USERPROFILE 'DecemberCommand\harnesses\claude-code\2.1.239\claude.exe'
& $claude auth login --claudeai
```

```powershell
# Codex (the pair -c ... keeps the login in a file, which the product can copy)
$login = Join-Path $env:USERPROFILE 'DecemberCommand\logins\codex'
New-Item -ItemType Directory -Force -Path $login | Out-Null
$env:CODEX_HOME = $login
$codex = Join-Path $env:USERPROFILE 'DecemberCommand\harnesses\codex\0.164.0\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe'
& $codex --% -c cli_auth_credentials_store=\"file\" login
```

```powershell
# Grok Build
$login = Join-Path $env:USERPROFILE 'DecemberCommand\logins\grok-build'
New-Item -ItemType Directory -Force -Path $login | Out-Null
$env:GROK_HOME = $login
$grok = Join-Path $env:USERPROFILE 'DecemberCommand\harnesses\grok-build\1.0.13\grok.exe'
& $grok --no-auto-update login
```

```powershell
# Kimi Code — subscription sign-in for available quota readings
$login = Join-Path $env:USERPROFILE 'DecemberCommand\logins\kimi-code'
New-Item -ItemType Directory -Force -Path $login | Out-Null
$env:KIMI_CODE_HOME = $login
$env:KIMI_CODE_NO_AUTO_UPDATE = '1'
$kimi = Join-Path $env:USERPROFILE 'DecemberCommand\harnesses\kimi-code\0.38.0\kimi.exe'
& $kimi login
```

Run the commands with the paths your wizard printed.
Complete the sign-in in the browser with your subscription account. Without the variable the tool
signs in to your own profile, and the product's folder stays empty. A working login does not need
to be repeated, but its access token has a limited life: before every task the product requires it
to outlast the step's timeout by ten minutes, and otherwise refuses the task before it starts and
asks you to sign in again, with the same two lines. The product does not refresh a login for you
outside the boundary in this version, and it never copies the refresh token into a task.
Extra hooks, plugins, MCP configuration, or nonstandard routing may make a login folder unsuitable.
While Studio uses it, do not use the same folder for a parallel personal session: per-step session
cleanup cannot distinguish that other session's files.

At the environment question, enter **variable names**, never secret values.
A usual Windows base is `SYSTEMROOT WINDIR PATH TEMP TMP`; add only names your tool requires.
Do not pass API-key variables to the subscription route: that changes which payment route is used.
Names that replace the login or reroute its traffic (a token, a proxy, a base URL, certificates)
are refused for it as you type them. For a task on an API key set up the connection with choice `2`
above: the variable name in `env_allow`, the value in the server's environment.

### Where tasks run in this build

On Windows the pinned executable, its login directory and the requested role must all be eligible. The Agents screen shows `boundary` when the execution boundary can be provided, or `refused` when it cannot. A version that cannot run has no such chip. Quota and sign-in checks run on the host using the dedicated login. An admitted subscription task runs in isolation on a temporary copy of its access token, without a refresh token or write-back. If the step is refused, check its role, executable, login directory and the reason shown in Runs.

- **macOS and Linux.** The boundary is not provided on these systems. Installation, project
  creation, Studio, the workflow editor, decisions, and the Agents screen work, but every step that
  would run a task is refused before anything starts, with the same message, whatever the login.
  The macOS / Linux commands above set up and inspect a project; they do not yet execute work.

### What has been checked with the real vendor

- **Claude Code 2.1.239.** A real subscription Goal ran inside AppContainer, produced `artifact-goal` and cleaned up. Identify then timed out. [Run report](recovery/2026-10-20/tasks/H5-B-RUN2-REPORT.md).
- **Codex 0.164.0.** In the shared cycle `gpt-6.1-sol` completed Goal, Identify and Design on subscription. Do ended without changes on 7 November. The new patch route has been checked separately with fixed model replies. [Live cycle](recovery/2026-10-20/HANDOFF-2026-11-07.md) · [Offline Do](recovery/2026-10-20/tasks/DO-PATCH-V1-REPORT.md).
- **Grok Build 1.0.13.** The live G6 diagnosis on subscription passed its rehearsal gate. In the shared cycle Grok identified the faulty code and missing test. Its role is read-only review. A quota response can omit usage percentages. [G6 report](recovery/2026-10-20/tasks/G6-GROK-1013-REPORT.md) · [Live cycle](recovery/2026-10-20/HANDOFF-2026-11-07.md).
- **Kimi Code 0.38.0.** The native CLI accepted synthetic credentials offline in isolation. Quota reads from a real account still need verification. The product refuses subscription tasks before spawn while isolation of writable CLI state is under development. [Native check](recovery/2026-10-20/tasks/H5-KIMI-NATIVE-BASELINE.md) · [Execution boundary](recovery/2026-10-20/tasks/H5-KIMI-PROMPT-OFFLINE-REPORT.md).

A complete independently checked Dalio cycle with Codex and Grok still needs a successful live acceptance run.

### DeepSeek: balance, key, and server restart

Top up the balance **at DeepSeek**. Configure direct DeepSeek API, with the key available in the environment as `DEEPSEEK_API_KEY`.
The wizard records the permitted name; it never asks you to paste the key into Studio or a project file.
On Windows you can set a user environment variable in the system's **Environment Variables** dialog,
then open a new terminal to pick it up. On other systems, supply the variable to the server process using your local environment setup.
The balance source supports the direct `https://api.deepseek.com`; a custom base URL does not establish the same balance reading.

Finish provider configuration before starting Studio. If login configuration or environment changes later,
stop the server with Ctrl+C and start it again from an environment that contains the new values.

## 4. Open Studio

These blocks restore the paths if you opened a new terminal after setting a key.
Use the installation and project locations you chose above if you changed the examples.

```powershell
# Windows
$conduct = Join-Path $env:LOCALAPPDATA 'DecemberCommand\app-v1\Scripts\conduct.exe'
$project = Join-Path $env:USERPROFILE 'DecemberTrial'
& $conduct up --dir $project --port 7777
```

```sh
# macOS / Linux
conduct="$HOME/.local/share/december-command/app-v1/bin/conduct"
project="$HOME/DecemberTrial"
"$conduct" up --dir "$project" --port 7777
```

Open the printed local address. The server occupies this terminal until you press **Ctrl+C**.
Ownership is `opened` while it serves, then `closed` after a clean stop.
The next `up` opens it again. Studio provides EN/RU and light/dark switches.

Stop the server only with Ctrl+C in its own window, and only after the address has been printed.
Do not start it hidden in the background (`-WindowStyle Hidden`): Ctrl+C from another window does
not reach it. A forced end (for example `Stop-Process`) leaves ownership `opened`: the next `up`
refuses with `recovery_required`, and `ownership status` cannot tell a live server from a killed
one. Recovery on Windows is in the table below.

**You should see:** Overview explaining the new project's state, and the Workflow, Runs, Decisions, and Agents screens.
An empty new project is normal. A permanent spinner or blank page is not.

On **Agents**, inspect the configured tools and their quota readings. A tool you have not set up
is a row marked `unconfigured`. The screen does not print the setup command for such a row: take it
from step 3 (`conduct providers`, with the server stopped). In the row of a tool this machine can
start, with a subscription login, next to the `subscription` chip, read the chip `boundary` or
`refused`: `boundary` means a task of this tool runs inside the execution boundary on this
machine, `refused` means it is refused before it starts, and the sentence beside it names the
possible reasons. A row where this computer cannot start the tool (its availability is not
`available`: `unconfigured`, `executable_absent` or `version_mismatch`) shows no road.
Opening Studio reads quota sources; it does not start model work. Refreshing the page's readings reads the server cache.
Read the source, timestamp, and status as well as the number: unavailable is not zero usage,
and a deferred update keeps the previous observation's age. DeepSeek shows money and currency; reset does not apply.
For what has actually passed live checks, consult the [candidate notes](release-notes-v1-alpha.md).

## 5. Understand the first real task

1. Create a small task with an observable result, for example a short document for the trial project.
2. In Workflow, start with **Standard cycle** (`dalio-v5`) and assign its participants, including a separate checker.
3. Publish the workflow revision and open a run bound to the intended task. Check the task identity and working location.
4. Supply the task instruction and any required input documents. Inspect the proposal and preview before authorizing execution.
5. Start in **Confirm** mode to decide on each action. For **Policy**, review the concrete budgets and grant a bounded run separately.
6. Follow Runs and Decisions. Handle human gates yourself; review the checker result before accepting the work.

Policy does not bypass human gates. Pause, revoke, and explicit resume are different actions.
A rejected result can be corrected only within the plan and permission; an uncertain result is not silently retried as success.
To exercise a task, use Windows and choose an available harness with the capability needed by that step. Grok is eligible only for a read-only review. Choose Claude Code or Codex for a role that must edit files. If no eligible harness appears, stop the server and run `conduct providers` as in step 3.

A task that ends with `unknown` is never repeated: do not run it again, and start no other
attempt. Two signs say to stop the server (Ctrl+C) first:

- The Runs screen says `adapter execute lost its result`. The result of the step was lost, and the
  ownership of the project is intact, so these words alone need no restart.
- A step stays started with no result, and Studio answers every action that writes with "The run
  store is unavailable." Ownership of the project turned uncertain, for example because the pinned
  tool could not start inside the isolation, and nothing can be recorded any more. Ctrl+C then
  prints `stop uncertain`, and the next `conduct up` refuses with `recovery_required`.

If `conduct up` or an action refuses with `recovery_required` or `login_recovery_required`, restart
Windows (**Restart**) and run the recovery command for the code you saw (see the table below). An
action the Runs screen sends "outside this window" is closed with `conduct reconcile`, not with a
restart (see the table).
For a guided, observable sequence use [owner acceptance](owner-acceptance.md) or [two-task acceptance](acceptance-two-tasks.md).

## If something is blocked

| You see | What to do next |
| --- | --- |
| No `ownership` command | Check the executable path and identified build. |
| `owner_busy` | Stop the other server using this project cleanly. Reloading the browser does not release ownership. |
| `recovery_required` | Run `conduct ownership recover --dir <project>` for the explicit recovery check; do not delete service records. This does not start model work. On Windows, a record from an older build needs a [prepared restart](#recovery-of-an-old-windows-record) first. If a server of this build was ended by force (not with Ctrl+C), Windows needs a full Restart (**Restart**, not shut down), then the same command; `--prepare-restart` is not needed for such a record, and the command says so. You see this code at `conduct up`, not on the Runs screen: a project that needs recovery records no receipt. If the command refuses with `recovery_refused: there is no abandoned owner session to recover`, the project has nothing to recover: that is not an obstacle. |
| `login_recovery_required` | The same road for the shared login lease: a [prepared restart](#recovery-of-an-old-windows-record) if it asks for one, then `conduct ownership recover-login --auth-home <login directory>`. This does not start model work. You see this code on the Runs screen as `adapter reported failed: the shared login lease was refused: the shared login has a lease that was not closed (login_recovery_required)`. Stop the server first. Only the command for the code you saw is needed (after a step that stays started with no result, both: see the row for it): if `recover-login` refuses with `login_owner_busy: shared login recovery cannot hold its resource` while no server or tool works through the login, this login has no abandoned lease. There is nothing to recover, and that is not an obstacle. This holds only when `<login directory>` is the exact absolute path of the existing login folder of step 3: a mistyped path or a folder that does not exist gets the same words. |
| `not_authenticated` | Complete the native login in the configured dedicated profile, then retry the appropriate reading. |
| DSH has no data | Check that the permitted key name is configured and the server started with that environment variable. |
| Provider cannot start | Check its native path and pinned version; `available` alone is not proof of login. |
| Port 7777 is busy | Stop the other server or use another port, such as `--port 8080`. |
| A step is refused: `demands sandbox route 'execution-boundary'` | Check Windows, the pinned executable, the product login folder and whether this harness supports the role requested by the step. Read the reason in Runs. [Where tasks run](#where-tasks-run-in-this-build). |
| The Runs screen says `adapter reported failed: the pinned login expires before the attempt would end; sign in again` (or `…: when the pinned login expires is not known; sign in again`) | The access token of the Claude Code or Codex login does not outlast the step's timeout by ten minutes, or its expiry cannot be read. Nothing was started. Sign in again with the two lines `conduct providers` prints (step 3: the variable that points at the login folder, then the tool's own sign-in), then retry. Signed in without the variable, the tool fills your own profile and the folder stays as it was. |
| The Runs screen says `adapter reported failed: the pinned login has no credential file to copy`, `…'s credential file is damaged` (or `is not an ordinary file`, `is too large`, `is in a shape this build does not know`), `…holds no access token`, `…holds an API key, which is not a subscription`, `…is on the API-billing plan` or `…does not say which plan it is on` | Nothing was started. The login folder holds no plain subscription login this build can copy. No file or a damaged one: sign in again in that folder (step 3). An API key or a console plan: sign in in that folder with a subscription account; a task on an API key is the other road (choice `2` in `conduct providers`). Any other sentence about the pinned login or its relay (`the pinned login …`, `the account of the pinned login …`, `the login lease of the attempt does not name the pinned login`, and the like) names a fact of the login, of its folders or of the attempt's lease: nothing was started, and the words are what a bug report needs. After a sentence that begins `the pinned login`, sign in again in the folder first (step 3). |
| The Runs screen says `adapter reported failed: the environment of the attempt replaces the pinned login or reroutes its traffic` | Nothing was started. The server's environment, or the names allowed for this provider, carries a name that replaces the login or reroutes its traffic (a token, a proxy, a base URL, certificates). Remove it: stop the server, run `conduct providers` again without it, and start the server from an environment that does not have it. |
| The Runs screen says `adapter reported failed: the relay folder of the pinned login is not usable` | Nothing was started, and the login is not the cause: do not sign in again. The folder `...\DecemberCommand\relay` is not as the product needs it (for example it has an extra entry in its access list). That folder is shared by every project and every login of this `DecemberCommand` folder: stop every server and the hub that work through these logins, remove the folder, start the server: the product makes it again. Do not protect it by hand. |
| The Runs screen says `adapter reported failed: a folder of the pinned login or of its relay is open to an isolated child` | Nothing was started, and the login is not the cause: do not sign in again. The access list of the login folder, of the `logins` folder above it, of a file at the top of the login folder, or of a relay folder has an entry for ALL APPLICATION PACKAGES, for an application package or for a capability, so an isolated task could read it. The product never edits these lists: remove the entry and retry. For the `relay` folder, stop every server and the hub that work through these logins and remove it (previous row). If you cannot tell which folder it is, keep the words and ask the maintainer to check the `DecemberCommand` folders with the preflight. |
| The Runs screen says `adapter reported failed: the attempt's relay home could not be made` (or `the attempt's relay home could not be used`, `the attempt's relay home was not empty`, `the login could not be copied into the attempt's relay home`, `the attempt's command could not be built`, `the execution boundary refused the attempt's relay home`, `the action could not be claimed for the attempt`) | Nothing was started, and the login is not the cause: do not sign in again. Retry the step once; if the same words come back, keep them for a bug report. |
| The Runs screen says only `adapter reported failed`, with no words after it, after an attempt that was interrupted | A home of that attempt may have stayed: the product removes such a home itself, and refuses the next attempt only when it could not remove it. Nothing was started. Stop every server and the hub that work through these logins (the folder is shared by all projects and logins), remove the folder `...\DecemberCommand\relay` (the product makes it again), start the server, then retry once. If the words stay bare, the leftover lies in the folder of attempt homes inside the project itself: keep the words for a bug report and do not delete it by hand. |
| The Runs screen says `adapter reported failed: the claim of the action could not be completed and its marker stands` | The action may have been claimed: do not repeat it. Keep the words for a bug report. If the server later refuses with `recovery_required`, follow the `recovery_required` rows of this table. |
| The Runs screen says `Outside this window: conduct reconcile` (an action a crash stranded before it could start) | Run `conduct reconcile --dir <project>`: it lists the stranded actions, one `<run> <action>` line each. `conduct reconcile --dir <project> --run <RUN> --action <ACTION>` closes exactly one with a terminal `unknown` receipt. It starts nothing and never reports success. It is not the road for `recovery_required` and needs no restart. The list can be read while the server runs; the closing command takes ownership of the project, so stop the server first (Ctrl+C), or it refuses with `owner_busy`. |
| A task ended `unknown` and the Runs screen says `adapter execute lost its result` | Do not repeat the task or start another attempt: it may have run. Stop the server (Ctrl+C). These words mean that the result of the step was lost while the ownership of the project is intact. They do not name a cause, and alone they need no restart. If `conduct up`, or the next action, then refuses with `recovery_required` or `login_recovery_required`, restart Windows (**Restart**) and run the command for that code (the `recovery_required` and `login_recovery_required` rows). |
| A step stays started with no result, and Studio answers each action that writes with "The run store is unavailable." (Ctrl+C then prints `stop uncertain`) | Nothing can be recorded: the ownership of the project turned uncertain, for example because the pinned tool could not start inside the isolation, so the result of the step could not be written. Do not repeat the step or any other action. Stop the server (Ctrl+C). The next `conduct up` refuses with `recovery_required`. Restart Windows (**Restart**), then run `conduct ownership recover --dir <project>`, and on the subscription road also, at once, `conduct ownership recover-login --auth-home <login directory>`: the lease of the login was left open too. A refusal that says there is nothing to recover is not an obstacle (the `recovery_required` and `login_recovery_required` rows). After the recovery the step may be closed `unknown` with the words `effect lease has no durable observation; execution was not repeated`: the product did not repeat it, and you do not either. |
| Saving a draft: `windows_path_too_long` | Shorten the workflow identifier or move the project to a shorter path (see step 2). |

### Recovery of an old Windows record

A project record or a shared login lease that an older build wrote on Windows cannot prove by itself
that the computer was restarted. For such a record `conduct ownership recover` refuses and points here.
The road has three steps; do them in order. First stop the project's server, the hub for it and any
tool working through the shared login: a live holder makes the command refuse and write nothing.

1. Prepare. Each command writes one record, releases nothing, starts nothing, and reads no token or
   login file. It prints that ownership is NOT released and which command to run after the restart.

   ```text
   conduct ownership recover --prepare-restart --dir "<absolute path to project>"
   conduct ownership recover-login --prepare-restart --auth-home "<absolute path to login directory>"
   ```

   Run the first line for `recovery_required` and the second for `login_recovery_required`.
2. Restart Windows from the Start menu with **Restart**. Do not use **Shut down** or **Update and
   restart**: this road covers only a full Restart.
3. Recover with the plain command:

   ```text
   conduct ownership recover --dir "<absolute path to project>"
   conduct ownership recover-login --auth-home "<absolute path to login directory>"
   ```

Between steps 1 and 3 the project does not open: a prepared record is not a release. If step 3 still
asks for a restart, do a full Restart and repeat only step 3. If step 3 says that the recorded boot
environment is not the current one, another Restart does not help: run step 1 again. Only that command,
run by you, prepares the record in the current environment (it adds a new preparation and keeps the
earlier ones); then do a full Restart and repeat step 3. If it refuses for another reason, keep its
output for a bug report and do not delete service records. A record that needs no preparation says so;
for it the plain command is enough.

Two more kinds of record follow the same road with the same flag. They are the unfinished clone
attempts of the hub and the container attempt loans of an activated project (Windows only). Stop the
hub first for the clone attempts: a running hub holds them, and the command refuses. For the container
loans recover the project first, as above:

```text
conduct ownership recover-clones --prepare-restart
conduct ownership recover-containers --prepare-restart --dir "<absolute path to project>"
```

Do a full Restart, then run the same commands without the flag. Nothing is removed until a restart is
proven for the record: a plain run only lists what is unfinished and names the action for each. A
preparation prints that nothing was cleaned up.

Still stuck? Include the command, expected and actual behavior, OS, and candidate identity in a bug report.
Remove keys and private project content. [Contributor guide](../CONTRIBUTING.md) · [How the pieces fit](architecture.md).
