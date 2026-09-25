"""Retire all resources; release project ownership only after proven cleanup."""
from .server_policy import stop_policy, release_server_owner


def retire_workers(subject):
    try:
        try:
            stop_policy(subject)
        finally:
            try:
                if subject.command_execution is not None:
                    subject.command_execution.shutdown()
            finally:
                if subject.quota_collector is not None:
                    subject.quota_collector.stop()
    except BaseException:
        subject.retirement_uncertain = True
        raise


def retire_resources(subject, close_socket, poll_interval):
    try:
        try:
            subject._retire_execution()
        finally:
            try:
                subject.watcher.stop()
                if subject.watcher.is_alive():
                    subject.watcher.join(timeout=poll_interval * 2)
                if subject.watcher.is_alive():
                    raise RuntimeError("project watcher did not retire")
            finally:
                close_socket()
    except BaseException:
        subject.retirement_uncertain = True
        raise
    if not getattr(subject, "retirement_uncertain", False):
        release_server_owner(subject)
