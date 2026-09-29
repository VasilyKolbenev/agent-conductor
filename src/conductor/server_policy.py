"""Project ownership and bounded driver lifetime belong to the server."""


def acquire_server_owner(subject, root, expected_project_id=None):
    """Hold the root's owner, then confirm the project it holds is the one asked for (4.5.1).

    The check before the bind reads the head without holding anything; this is the second one,
    against the owner this process now has, and it closes a swap of the root between the two.
    """
    from .ownership import acquire_owner, is_activated
    from .ownership_errors import OwnerRefused
    if is_activated(root):
        subject.project_owner = acquire_owner(root)
    owner = subject.project_owner
    held = None if owner is None else owner.project_id
    if expected_project_id is not None and held != expected_project_id:
        raise OwnerRefused("project_identity_changed",
                           "the project folder holds another project than the one asked for; "
                           "it was activated again or replaced after it was checked")


def start_policy(subject, clock, ids):
    """Build and start the driver; a project without an owner, or opened for viewing, has none."""
    if subject.project_owner is None or subject.launch.mode == "view":
        return
    from .command.policy_driver import PolicyDriver
    policy = subject.command_api._policy
    driver = PolicyDriver(policy, subject.command_api.runtime, subject.command_execution,
                          clock=clock, ids=ids)
    policy.driver = driver
    subject.policy_driver = driver
    driver.start()


def stop_policy(subject):
    driver = getattr(subject, "policy_driver", None)
    if driver is not None:
        driver.stop()


def release_server_owner(subject):
    owner = getattr(subject, "project_owner", None)
    if owner is not None:
        owner.release()
        subject.project_owner = None
