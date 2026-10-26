# Your first real project

[English](first-run-v1.en.md) · [Русский](first-run-v1.md) · [Documentation](index.md)

**Goal:** open Studio for a new project, connect a coding tool, and understand how to start work deliberately.
If you only want to see the interface, start with the [account-free demo](../README.md#try-the-demo).

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

Open PowerShell from the Start menu, not from the terminal inside the Claude or Codex app: a window
started by those apps keeps what it installs under `%LOCALAPPDATA%` in the app's own package folder,
where your own window does not see it.

Replace the first path with the actual wheel location. Run the blocks below in the same terminal so `$conduct` stays defined.

```powershell
$wheel = 'C:\Downloads\agent_conductor-0.1.0-py3-none-any.whl'
Get-FileHash -Algorithm SHA256 -LiteralPath $wheel
$install = Join-Path $env:LOCALAPPDATA 'DecemberCommand\app-v1'
py -3 -m venv $install
$python = Join-Path $install 'Scripts\python.exe'
$conduct = Join-Path $install 'Scripts\conduct.exe'
& $python -m pip install $wheel
& $conduct --help
```

If `py` is not installed, use the full path to a Python 3.11+ `python.exe` instead of `py -3`.

This install folder is the general one. The maintainer's own check of the subscription road installs
the build under the protected `%USERPROFILE%\DecemberCommand\product\<build id>`, beside the tools
and logins of step 3; this tutorial does not change the folder above.

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

Use a build that has the subscription road for Claude Code and Codex. You tell it in step 3: the
login question of `conduct providers` says that with `1` a task runs inside the execution boundary
on a copy of the login. An older build does not say so. One made before the execution boundary (the
build the release notes describe, of 25 September) runs a task on a subscription login without
isolation; one made after the boundary and before this road refuses every such task. No published
candidate has the subscription road yet: the maintainer will name the one that does.

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
| Claude Code | 2.1.239 | Native executable under `%USERPROFILE%\DecemberCommand\harnesses\claude-code\2.1.239\`; subscription login in `%USERPROFILE%\DecemberCommand\logins\claude-code`, signed in with `CLAUDE_CONFIG_DIR` set to that folder. | The build runs a task on the subscription login inside the execution boundary, with no API key. Not yet run with the real vendor: one real answer came from a copy of a login outside the isolation, and no task has run inside it (see [what has been checked](#what-has-been-checked-with-the-real-vendor)). An API key (the name `ANTHROPIC_API_KEY` in `env_allow`) is an optional second road. |
| Codex | 0.112.0 | Native executable under `%USERPROFILE%\DecemberCommand\harnesses\codex\0.112.0\`; subscription login in `%USERPROFILE%\DecemberCommand\logins\codex`, signed in with `CODEX_HOME` set to that folder. | The build runs a task on the subscription login inside the execution boundary, with no API key. No task has run on it with the real vendor yet: the vendor's server refused both probes of this version (on the model), so a task may end with `the process exited non-zero` (see [what has been checked](#what-has-been-checked-with-the-real-vendor)). An API key (the name `OPENAI_API_KEY` in `env_allow`) is an optional second road. |
| Kimi Code | 0.38.0 | Native executable, subscription login (quotas are read), dedicated `KIMI_CODE_HOME` with managed OAuth login. | A subscription login for it is not supported inside the boundary yet: quotas are read, a task is refused before it starts. A task needs an API key: a variable name in `env_allow`. The product has not checked its API-key operation with the real vendor. |
| Grok Build | 1.0.5 | Native executable, subscription login (quotas are read), dedicated `GROK_HOME` with native login. | A subscription login for it is not supported inside the boundary yet: quotas are read, a task is refused before it starts. A task needs an API key: a variable name in `env_allow`. The product has not checked its API-key operation with the real vendor. |
| DeepSeek Harness | 0.1.0-rc.7 | Node executable **and** DSH script entrypoint; API-key mode; allowed name `DEEPSEEK_API_KEY`. | The same API-key mode. |

A configured connection does not mean a task will run: see [Where tasks run in this build](#where-tasks-run-in-this-build).

**Run the wizard while the server is stopped** (Ctrl+C in its window; the command refuses with
`owner_busy` otherwise), then start `conduct up` again: providers are read once, at startup.

In the wizard the question about the login reads: `1` is the tool's own subscription login, `2` is a
credential read from the environment. Under it the wizard prints a note (English only) that says
what `1` does for this tool:

- **Claude Code and Codex.** Choice `1` is the road without an API key: "On Windows, with 1 a task
  runs inside the execution boundary on a copy of that login that has no refresh token; the login
  folder itself is never given to a task." That sentence says what this build does with the login;
  it does not say that the vendor's tool accepts it (see
  [what has been checked with the real vendor](#what-has-been-checked-with-the-real-vendor)).
  The wizard asks for the login folder. It must be named
  `<something>\DecemberCommand\logins\<name>`; type it as a full path, for example
  `C:\Users\you\DecemberCommand\logins\claude-code` (that is
  `%USERPROFILE%\DecemberCommand\logins\<id>`, which the wizard prints with the tool's id). Any
  other folder is refused on the spot and asked again: a row saved with another folder would have
  every task refused before it starts.
- **Kimi Code and Grok Build.** Choice `1` keeps any folder you name; the quotas are read, and
  "every task is refused before it starts: a subscription login for this harness is not supported
  inside the execution boundary yet". For tasks choose `2` and allow the variable name.

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
The wizard prints two lines for you to run **in your own PowerShell**; it does not sign in for you.
The first points the tool at the login folder, the second is the tool's own sign-in:

```powershell
# Claude Code
$env:CLAUDE_CONFIG_DIR = Join-Path $env:USERPROFILE 'DecemberCommand\logins\claude-code'
$claude = Join-Path $env:USERPROFILE 'DecemberCommand\harnesses\claude-code\2.1.239\claude.exe'
& $claude auth login --claudeai
```

```powershell
# Codex (the pair -c ... keeps the login in a file, which the product can copy)
$env:CODEX_HOME = Join-Path $env:USERPROFILE 'DecemberCommand\logins\codex'
$codex = Join-Path $env:USERPROFILE 'DecemberCommand\harnesses\codex\0.112.0\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\codex\codex.exe'
& $codex -c cli_auth_credentials_store="file" login
```

The wizard prints these lines with the paths you gave it: copy its lines, not these examples.
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

A task runs inside an execution boundary, and only from a login or a key this build can give it.

- **Windows.** The boundary exists. The pinned build must be installed in a folder shaped
  `...\harnesses\<name>\<version>\` (the owner's protected place is
  `%USERPROFILE%\DecemberCommand\harnesses\<name>\<version>\`); otherwise the boundary cannot be
  provided and the step is refused. There are two roads.
  - **A subscription login of Claude Code or Codex**, with no API key. The login is kept in
    `...\DecemberCommand\logins\<name>`. Before a task the product checks that the login is a
    plain subscription login that outlasts the step, then copies its access token, **without the
    refresh token**, into a fresh relay folder under `...\DecemberCommand\relay\` outside the
    project. The task runs inside the boundary with that folder as the tool's home; the folder is
    read back and removed when the attempt ends. The login folder itself is never given to a task,
    and nothing is copied back into it. The version check, the login status and the quota request
    (the vendor's RPC) still run **outside** the boundary on the login folder, so keep only
    standard configuration in it. A task is refused before anything starts if the login folder is
    named otherwise, the login is missing, an API key or a console plan, or too short-lived, or if
    the environment carries a name that replaces the login. That the vendor's tool then works on
    the copy has not been shown with the real vendor yet: see
    [what has been checked with the real vendor](#what-has-been-checked-with-the-real-vendor).
  - **An API key**, for any tool: the wizard allows the variable *name* (for example
    `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`) and the value lives in the
    environment of the server you start.
- **A subscription login of Kimi Code or Grok Build.** It is not supported inside the boundary yet:
  the step is refused before anything starts, and the subscription serves to read quotas. Reading
  quotas is not a task, but it does launch the vendor's CLI: the version check and the quota
  request run **outside** the boundary, with the real login directory of your dedicated profile.
  The refusal reads like this:

  | Where | What it says |
  | --- | --- |
  | Plan and API (the plan's door) | `step '…' demands sandbox route 'execution-boundary' that this build does not provide` |
  | Desk wizard, the run step (`wizard.chain.boundary`) | "This step needs the isolation (execution boundary), and this computer cannot give it to the agent chosen, so nothing was started. A task runs in the isolation only on Windows and only from a build installed under `...\harnesses\<name>\<version>\`." |
  | Desk wizard, when a chosen agent signs in by subscription and its task road is refused (`wizard.chain.boundary_login`) | the same, then: "The agent chosen signs in with a subscription, and a task on that login is refused before it starts: its login directory must be named `...\DecemberCommand\logins\<name>` (set it up with conduct providers while the server is stopped), and a subscription login for some harnesses is not supported inside the isolation yet. Choose another agent, or one that signs in with an API key." |
  | The attempt's receipt (appears only if the transport is called around the doors; on the usual path the plan's door refuses the step earlier) | Kimi Code, Grok Build: `this <tool> connection signs in with a subscription, which is not supported inside the execution boundary for this harness yet, so no task was spawned`; the Runs screen reads it in the runtime's words: `a subscription login for this harness is not supported inside the execution boundary yet`. Claude Code, Codex: `the <tool> login is not ready for an isolated attempt: <reason>, so no task was spawned` (with `; sign in again with …` when only a new sign-in repairs it), or `the <tool> attempt could not start in isolation: <reason>, so no task was spawned`; the Runs screen never shows these sentences, it shows the runtime's words, `adapter reported failed: <words>` (for example `adapter reported failed: the pinned login expires before the attempt would end; sign in again`), and the table [If something is blocked](#if-something-is-blocked) is keyed on those words. The subscription is named as the reason only when it is the single missing reason; on macOS / Linux, for a build installed outside `harnesses\<name>\<version>` and for a login folder not named `DecemberCommand\logins\<name>` the receipt says the general thing: the boundary is not provided for this attempt. |
  | Agents screen, the row of a tool this machine can start: the chip `boundary` or `refused` and the text next to the `subscription` chip | `boundary`: "Configured to use the vendor's own login, kept in its own directory. A task runs inside the execution boundary on a copy of that login that has no refresh token; the login directory itself is never given to the task." `refused`: "… A task on this login is refused before it starts. Possible reasons: a subscription login for this harness is not supported inside the execution boundary yet; its login directory is not named `...\DecemberCommand\logins\<name>`; or this machine cannot give the boundary (it needs Windows and a build installed under `...\harnesses\<name>\<version>`)." |
  | `conduct providers` | the note under the login question and, for Claude Code and Codex, the refusal of a folder not named `<something>\DecemberCommand\logins\<name>` (see above) |

- **macOS and Linux.** The boundary is not provided on these systems. Installation, project
  creation, Studio, the workflow editor, decisions, and the Agents screen work, but every step that
  would run a task is refused before anything starts, with the same message, whatever the login.
  The macOS / Linux commands above set up and inspect a project; they do not yet execute work.

### What has been checked with the real vendor

The subscription road of Claude Code and Codex is built and tested with fake tools and fake logins.
With the real vendors:

- **Claude Code.** One real answer was obtained from the tool on a copy of a login that had no
  refresh token, outside the isolation. A task inside the isolation, on the product's own copy, has
  not been run yet; the first such run will be the first check, not a repeat of one.
- **Codex.** No task has run on it with the real vendor. The vendor's server refused both probes of
  the pinned version 0.112.0 (on the model), so a task may end with `the process exited non-zero`.
  A newer version to pin is not chosen yet.

The wizard's notes and the chips on the Agents screen say what this build does with the folder and
the machine. None of them says that the vendor accepts the login.

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

On **Agents**, inspect the configured tools and their quota readings. In the row of a tool this
machine can start, with a subscription login, next to the `subscription` chip, read the chip
`boundary` or `refused` (a row that says `unconfigured` shows no road yet):
`boundary` means a task of this tool runs inside the execution boundary on this machine, `refused`
means it is refused before it starts, and the sentence beside it names the possible reasons.
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
Steps 4–6 assume a task runs: on macOS / Linux, on a subscription login of Kimi Code or Grok Build,
and on a Claude Code or Codex login kept outside `...\DecemberCommand\logins\<name>` such a step is
refused before it starts (see [Where tasks run in this build](#where-tasks-run-in-this-build)).
In the desk wizard the roles step offers the available tools; assign Claude Code or
Codex on their subscription login, and the preparation step names the reason in the sentence above
if a chosen tool cannot be given the boundary. A task that ends with `unknown` is never repeated:
do not run it again. If the error says `could not start the pinned build`, or the server refuses
with `recovery_required` or `login_recovery_required`, stop, restart Windows (**Restart**) and run
the two recovery commands of the table below. An action the Runs screen sends "outside this window"
is closed with `conduct reconcile`, not with a restart (see the table).
For a guided, observable sequence use [owner acceptance](owner-acceptance.md) or [two-task acceptance](acceptance-two-tasks.md).

## If something is blocked

| You see | What to do next |
| --- | --- |
| No `ownership` command | Check the executable path and identified build. |
| `owner_busy` | Stop the other server using this project cleanly. Reloading the browser does not release ownership. |
| `recovery_required` | Run `conduct ownership recover --dir <project>` for the explicit recovery check; do not delete service records. This does not start model work. On Windows, a record from an older build needs a [prepared restart](#recovery-of-an-old-windows-record) first. If a server of this build was ended by force (not with Ctrl+C), Windows needs a full Restart (**Restart**, not shut down), then the same command; `--prepare-restart` is not needed for such a record, and the command says so. |
| `login_recovery_required` | The same road for the shared login lease: a [prepared restart](#recovery-of-an-old-windows-record) if it asks for one, then `conduct ownership recover-login --auth-home <login directory>`. This does not start model work. |
| `not_authenticated` | Complete the native login in the configured dedicated profile, then retry the appropriate reading. |
| DSH has no data | Check that the permitted key name is configured and the server started with that environment variable. |
| Provider cannot start | Check its native path and pinned version; `available` alone is not proof of login. |
| Port 7777 is busy | Stop the other server or use another port, such as `--port 8080`. |
| A step is refused: `demands sandbox route 'execution-boundary'`; in the desk wizard "This step needs the isolation (execution boundary)…" (`wizard.chain.boundary`, `wizard.chain.boundary_login`); in a receipt `this <tool> connection signs in with a subscription…` | This is the boundary refusing; nothing was started. On macOS / Linux this build does not run tasks. A subscription login of Kimi Code or Grok Build does not run tasks yet: use another agent or an API key (choice `2` in `conduct providers`). For Claude Code and Codex check that the login folder is named `...\DecemberCommand\logins\<name>` and the tool is installed under `...\harnesses\<name>\<version>\`. Details: [Where tasks run in this build](#where-tasks-run-in-this-build). |
| The Runs screen says `adapter reported failed: the pinned login expires before the attempt would end; sign in again` (or `…: when the pinned login expires is not known; sign in again`) | The access token of the Claude Code or Codex login does not outlast the step's timeout by ten minutes, or its expiry cannot be read. Nothing was started. Sign in again with the two lines `conduct providers` prints (step 3: the variable that points at the login folder, then the tool's own sign-in), then retry. Signed in without the variable, the tool fills your own profile and the folder stays as it was. |
| The Runs screen says `adapter reported failed: the pinned login has no credential file to copy`, `…'s credential file is damaged` (or `is not an ordinary file`, `is too large`, `is in a shape this build does not know`), `…holds no access token`, `…holds an API key, which is not a subscription`, `…is on the API-billing plan` or `…does not say which plan it is on` | Nothing was started. The login folder holds no plain subscription login this build can copy. No file or a damaged one: sign in again in that folder (step 3). An API key or a console plan: sign in in that folder with a subscription account; a task on an API key is the other road (choice `2` in `conduct providers`). Any other `the pinned login …` sentence names a fact of the login or of its folders; sign in again in the folder, and keep the words for a bug report if it repeats. |
| The Runs screen says `adapter reported failed: the environment of the attempt replaces the pinned login or reroutes its traffic` | Nothing was started. The server's environment, or the names allowed for this provider, carries a name that replaces the login or reroutes its traffic (a token, a proxy, a base URL, certificates). Remove it: stop the server, run `conduct providers` again without it, and start the server from an environment that does not have it. |
| The Runs screen says `adapter reported failed: the attempt's relay home could not be made` (or `the attempt's command could not be built`, `the execution boundary refused the attempt's relay home`, `the action could not be claimed for the attempt`) | Nothing was started, and the login is not the cause: do not sign in again. Retry the step once; if the same words come back, keep them for a bug report. |
| The Runs screen says `adapter reported failed: the claim of the action could not be completed and its marker stands` | The action may have been claimed: do not repeat it. Keep the words for a bug report. If the server later refuses with `recovery_required`, follow the `recovery_required` rows of this table. |
| The Runs screen says `Outside this window: conduct reconcile` (an action a crash stranded before it could start) | Run `conduct reconcile --dir <project>`: it lists the stranded actions, one `<run> <action>` line each. `conduct reconcile --dir <project> --run <RUN> --action <ACTION>` closes exactly one with a terminal `unknown` receipt. It starts nothing and never reports success. It is not the road for `recovery_required` and needs no restart. |
| A task failed with `the … harness could not start the pinned build`, or `recovery_required` / `login_recovery_required` after a task | Stop and do not repeat the task: it may have run. Close the server (Ctrl+C), restart Windows (**Restart**), then run `conduct ownership recover --dir <project>` and `conduct ownership recover-login --auth-home <login directory>` (see below). A task that ended `unknown` without any of these words needs no restart; it is not repeated either. |
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
