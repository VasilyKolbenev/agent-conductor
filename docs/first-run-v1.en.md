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

## 2. Create a fresh trial project

Use a new folder for your first run. Choose a different name if `DecemberTrial` already contains project data.

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

| Tool | Version pinned by this candidate | Supply to the wizard |
| --- | --- | --- |
| Claude Code | 2.1.239 | Native executable, subscription login, dedicated `CLAUDE_CONFIG_DIR`. |
| Codex | 0.112.0 | Native executable, subscription login, dedicated `CODEX_HOME`. |
| Kimi Code | 0.38.0 | Native executable, subscription login, dedicated `KIMI_CODE_HOME` with managed OAuth login. |
| Grok Build | 1.0.5 | Native executable, subscription login, dedicated `GROK_HOME` with native login. |
| DeepSeek Harness | 0.1.0-rc.7 | Node executable **and** DSH script entrypoint; API-key mode; allowed name `DEEPSEEK_API_KEY`. |

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

For a subscription, choose the dedicated profile in which you have completed the native login.
The wizard prints the login instructions; it does not sign in for you. A working dedicated login does not need to be repeated.
Extra hooks, plugins, MCP configuration, or nonstandard routing may make a profile unsuitable.
While Studio uses it, do not use the same profile for a parallel personal session: per-step session cleanup cannot distinguish that other session's files.

At the environment question, enter **variable names**, never secret values.
A usual Windows base is `SYSTEMROOT WINDIR PATH TEMP TMP`; add only names your tool requires.
Do not pass API-key variables to the subscription route: that changes which payment route is used.

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

**You should see:** Overview explaining the new project's state, and the Workflow, Runs, Decisions, and Agents screens.
An empty new project is normal. A permanent spinner or blank page is not.

On **Agents**, inspect the configured tools and their quota readings.
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
For a guided, observable sequence use [owner acceptance](owner-acceptance.md) or [two-task acceptance](acceptance-two-tasks.md).

## If something is blocked

| You see | What to do next |
| --- | --- |
| No `ownership` command | Check the executable path and identified build. |
| `owner_busy` | Stop the other server using this project cleanly. Reloading the browser does not release ownership. |
| `recovery_required` | Run `conduct ownership recover --dir <project>` for the explicit recovery check; do not delete service records. This does not start model work. On Windows, a record from an older build needs a [prepared restart](#recovery-of-an-old-windows-record) first. |
| `login_recovery_required` | The same road for the shared login lease: a [prepared restart](#recovery-of-an-old-windows-record) if it asks for one, then `conduct ownership recover-login --auth-home <login directory>`. This does not start model work. |
| `not_authenticated` | Complete the native login in the configured dedicated profile, then retry the appropriate reading. |
| DSH has no data | Check that the permitted key name is configured and the server started with that environment variable. |
| Provider cannot start | Check its native path and pinned version; `available` alone is not proof of login. |
| Port 7777 is busy | Stop the other server or use another port, such as `--port 8080`. |

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
