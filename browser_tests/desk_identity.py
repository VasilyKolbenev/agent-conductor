"""A real server that serves an identified project, for the desk's browser tests (spec 4.5.1).

Not a test module: pytest does not collect it (no `test_` prefix). A server built by
`server.build` over a seeded directory serves no identified project, because the identity of a
server is the nonce of the activation it owns and these directories were never activated. So it
answers `GET /command/project` with `project_id: null`, and, as the spec says, it refuses every
request that claims a project. A desk whose hash names a project needs a server that really is
that project, and this gives one: the built server's identity is replaced by the one an
activated project's `conduct up` would have, in the two places the server keeps it, and from then
on the server's own check of `X-Conduct-Project` and its own answer to the claim read are the
real ones. Nothing else of the server changes.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from conductor import server
from conductor.command.project_claim import ProjectIdentity


def identify(httpd: server.ConductServer, project_id: str | None, *,
             hub_origin: str | None = None, mode: str = "active") -> ProjectIdentity:
    """Give a built server the identity of an activated project and return it."""
    identity = ProjectIdentity(project_id, hub_origin, False, mode, None, None)
    httpd.project_identity = identity
    httpd.command_api._identity = identity
    return identity


@contextmanager
def identified_server(root: Path, project_id: str | None, *, hub_origin: str | None = None,
                      mode: str = "active") -> Iterator[str]:
    """Serve `root` as the project `project_id` on a free loopback port; yield its origin."""
    httpd = server.build(root, 0, hub_origin=hub_origin)
    identify(httpd, project_id, hub_origin=hub_origin, mode=mode)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "desk server did not stop"
