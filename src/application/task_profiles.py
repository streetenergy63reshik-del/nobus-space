"""Closed task-profile registry for capability routing and L4 decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TaskProfile(str, Enum):
    ANSWER_READ = "answer.read"
    RESEARCH_WEB = "research.web"
    ARTIFACT_CREATE = "artifact.create"
    DOWNLOAD_QUARANTINE = "download.quarantine"
    NETWORK_COMMAND = "network.command"


@dataclass(frozen=True, slots=True)
class ProfilePolicy:
    permissions: tuple[str, ...]
    requires_l4: bool
    effect: str


PROFILE_POLICIES = {
    TaskProfile.ANSWER_READ: ProfilePolicy(
        ("repo.read", "process.run_allowlisted"), False, "read-only"
    ),
    TaskProfile.RESEARCH_WEB: ProfilePolicy(
        ("repo.read", "process.run_allowlisted", "web.search"), False, "network-read"
    ),
    TaskProfile.ARTIFACT_CREATE: ProfilePolicy(
        ("artifact.write",), False, "owner-command-filesystem-write"
    ),
    TaskProfile.DOWNLOAD_QUARANTINE: ProfilePolicy(
        ("network.download", "artifact.write"), False, "owner-command-download"
    ),
    TaskProfile.NETWORK_COMMAND: ProfilePolicy(
        ("network.command",), False, "owner-command-network-effect"
    ),
}


def profile_for_command(command: str) -> TaskProfile | None:
    """Map only explicit product commands; never infer authority from prose."""
    return {
        "/research": TaskProfile.RESEARCH_WEB,
        "/document": TaskProfile.ARTIFACT_CREATE,
        "/download": TaskProfile.DOWNLOAD_QUARANTINE,
        "/network": TaskProfile.NETWORK_COMMAND,
    }.get(command.casefold() if isinstance(command, str) else "")
