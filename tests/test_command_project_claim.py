"""The identity a project's server holds and the claim a request may make on it (spec 4.5.1).

`project_id` is the activation nonce: 32 lowercase hex, made once by `activate`, the same
across ownership generations, and the key of the hub's registry. A child learns it from its
OWNER (`ProjectOwner.project_id`, the head the owner holds), never from a value read earlier.
`ProjectIdentity` freezes what `GET /command/project` answers and what a request that carries
`X-Conduct-Project` is held to. The route row, the constructor parameter of `CommandApi` and
the one call of `check` are lane L's lines (`H-to-L-project-route.patch`), so this module
tests the handler and the check directly, not through the router.
"""
from __future__ import annotations

import re

from conductor import ownership, ownership_records
from tests._drain_harness import DrainProject

HEX32 = re.compile(r"[0-9a-f]{32}")


def _activated(tmp_path):
    project = DrainProject.build(tmp_path)
    return project.root, project.project_id


# -- ProjectOwner.project_id --------------------------------------------------------


def test_the_owner_of_an_activated_project_reports_the_nonce_of_its_head(tmp_path):
    root, nonce = _activated(tmp_path)
    with ownership.acquire_owner(root) as owner:
        assert owner.project_id == nonce == ownership_records.state(root)[1]["nonce"]
        assert HEX32.fullmatch(owner.project_id)


def test_the_nonce_is_the_same_after_the_owner_closes_and_a_new_one_opens(tmp_path):
    root, nonce = _activated(tmp_path)
    first = ownership.acquire_owner(root)
    seen = [first.project_id]
    first.release()
    second = ownership.acquire_owner(root)
    seen.append(second.project_id)
    second.release()
    assert seen == [nonce, nonce]
