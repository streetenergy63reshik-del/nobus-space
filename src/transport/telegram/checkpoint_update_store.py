"""Update-id boundary for a polling loop with a durable outer checkpoint."""

from __future__ import annotations


class PollingCheckpointUpdateIdStore:
    """Delegate replay ownership to TelegramPollingBoundary's SQLite checkpoint.

    The gateway still validates update ids. Returning True here is deliberate:
    when a handler send fails, the outer checkpoint must be able to replay the
    same update instead of losing its reply to a premature in-memory claim.
    """

    @staticmethod
    def claim(value: int) -> bool:
        return type(value) is int and value >= 0
