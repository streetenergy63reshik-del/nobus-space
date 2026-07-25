"""Retry policy at the shared Google transport boundary."""

from __future__ import annotations

import pytest

from src.integrations.google_transport import execute_request


class _Request:
    def __init__(self) -> None:
        self.retries: list[int] = []

    def execute(self, *, num_retries: int):
        self.retries.append(num_retries)
        return {"ok": True}


def test_mutation_is_not_retried_by_default() -> None:
    request = _Request()

    assert execute_request(request) == {"ok": True}
    assert request.retries == [0]


def test_safe_read_must_explicitly_opt_in_to_retries() -> None:
    request = _Request()

    assert execute_request(request, retries=2) == {"ok": True}
    assert request.retries == [2]


@pytest.mark.parametrize("value", [-1, 3, True, 1.0])
def test_retry_count_is_strict_and_bounded(value: object) -> None:
    with pytest.raises(ValueError, match="google_request_retries_invalid"):
        execute_request(_Request(), retries=value)  # type: ignore[arg-type]
