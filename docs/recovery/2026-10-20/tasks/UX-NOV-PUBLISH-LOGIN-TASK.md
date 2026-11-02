# Copyable owner login commands

Design for the two-line providers wizard. A person can paste its Codex sign-in command into Windows PowerShell or a POSIX shell and the CLI must receive the measured literal `cli_auth_credentials_store="file"`. A Grok sign-in must use the tested `--no-auto-update login` arguments. Windows PowerShell strips literal quotes even within a single-quoted argument passed to a native Windows process; POSIX shells also consume unquoted shell quotes. A display-only command generator should preserve argv for each shell. Keep simple commands readable and keep the native runner's process argument list untouched.

Use the actual wizard CLI contract and verify the received arguments with a harmless native executable on Windows and a shell on POSIX where available. Show the unmodified existing test failure first. No login, provider, download, deployment or additional model invocation.
