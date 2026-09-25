"""Project ownership and bounded driver lifetime belong to the server."""


def acquire_server_owner(subject, root):
    from .ownership import acquire_owner, is_activated
    if is_activated(root):
        subject.project_owner = acquire_owner(root)


def start_policy(subject, clock, ids):
    if subject.project_owner is None:
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
