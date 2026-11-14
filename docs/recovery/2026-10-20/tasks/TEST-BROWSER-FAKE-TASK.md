# TEST-BROWSER-FAKE

The Windows browser gate on 9c0032c recorded five setup errors in test_desk_accept_publish.
The pinned test executable for gh could not run its version check (WinError 4551).
The generated executable is already registered with the project's Windows test subprocess
fixture, but browser tests are outside tests/conftest.py's discovery scope.

Reuse that exact fixture in the browser modules which build registered fake executables.
Keep the real subprocess, version check, local bare remote, acceptance evidence and product
code unchanged. Check both publication and the Studio layout case that builds a fake CLI.
Preserve the original gate result separately. Never run a real push or PR in this check.

The same Studio layout module exposed a separate stale roster: it expected seven ready
starters, while the catalog ships eight including dalio-v6. The isolated Chromium test
failed at 8 != 7. Pin the actual public IDs of the ready starters and keep the caveat and
rendered note assertions. No change to the catalog or the displayed choices.
