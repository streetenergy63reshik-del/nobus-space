"""Local fake-only composition used by Telegram Gate 5A.3."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from src.application.durable_runtime import DurableFakeRuntime
from src.application.fake_vertical import VerificationInput
from src.contracts import (
    TaskContract,
    VerificationLevel,
    VerificationLevelStatus,
)
from src.contracts.models import canonical_json_digest
from src.core.policy import InMemoryPolicyStore, TrustedVerifierRegistry
from src.orchestrator.state_manager import StateManager
from src.storage import SQLiteStore
from src.transport.telegram import TelegramGateway
from src.workers import CodexCliResult


_VERIFIER_IDENTITIES = {
    1: "verifier:gate5a3-fake:l1",
    2: "verifier:gate5a3-fake:l2",
    3: "verifier:gate5a3-fake:l3",
}


class _LocalFakeWorker:
    async def execute(self, contract: TaskContract) -> CodexCliResult:
        TaskContract.model_validate(contract.model_dump(mode="json"))
        return CodexCliResult(
            message="Local fake worker completed without filesystem or network effects."
        )


class _LocalFakeVerifier:
    def __init__(self, level: int, clock: Callable[[], datetime]) -> None:
        self._level = level
        self._clock = clock

    async def __call__(self, candidate: VerificationInput) -> VerificationLevel:
        verified_at = self._clock()
        if verified_at.tzinfo is None or verified_at.utcoffset() is None:
            raise ValueError("fake verifier clock is invalid")
        identity = _VERIFIER_IDENTITIES[self._level]
        return VerificationLevel(
            status=VerificationLevelStatus.PASSED,
            method=f"gate5a3-fake-l{self._level}",
            verifier_identity=identity,
            verified_at=verified_at.astimezone(UTC),
            evidence_refs=(f"evidence:gate5a3:fake:l{self._level}",),
            evidence_digest=canonical_json_digest(
                {
                    "contract_digest": candidate.contract_digest,
                    "level": self._level,
                    "output_digest": candidate.output_digest,
                    "result_digest": candidate.result_digest,
                    "task_id": str(candidate.task_id),
                }
            ),
        )


def build_gate5a3_runtime(
    *,
    gateway: TelegramGateway,
    sqlite_path: str | Path,
    destination_refs: Mapping[str, str],
    allowed_path: str | Path,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> DurableFakeRuntime:
    """Build the accepted durable runtime with no live worker/provider."""
    registry = TrustedVerifierRegistry(
        {level: {identity} for level, identity in _VERIFIER_IDENTITIES.items()}
    )
    return DurableFakeRuntime(
        gateway=gateway,
        store=SQLiteStore(sqlite_path, verifier_registry=registry),
        destination_refs=destination_refs,
        policy_store=InMemoryPolicyStore(),
        state_manager=StateManager(registry),
        worker=_LocalFakeWorker(),
        verifiers=tuple(
            _LocalFakeVerifier(level, clock) for level in (1, 2, 3)
        ),
        allowed_path=allowed_path,
        clock=clock,
    )
