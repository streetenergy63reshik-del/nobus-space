"""Real persistent state/recovery seam, without an external model."""
import pytest
from src.application.gate5a4 import Gate5A4Runtime
from src.models.task import TaskStatus
from tests.test_contracts import make_envelope
from tests.test_telegram_task_control import build_harness, TENANT_ID


@pytest.mark.asyncio
async def test_pending_restart_preserves_creation_and_can_record_worker_start(tmp_path):
    first=build_harness(tmp_path)
    envelope=make_envelope(tenant_id=TENANT_ID,idempotency_key='c2-pending-restart')
    prepared=await first.runtime.prepare_instruction('Объясни дату, встречу не создавай.',envelope)
    contract=prepared.contract
    before=first.runtime._store.read_task(TENANT_ID,contract.task_id)
    assert before.projection.status is TaskStatus.PENDING
    first.clock.advance(10)
    second=build_harness(tmp_path,clock=first.clock)
    assert await Gate5A4Runtime.recover_prepared(second.runtime,prepared,envelope)
    restored=await second.runtime._state.get(contract.task_id)
    assert restored.created_at==before.projection.created_at
    assert restored.updated_at==before.projection.updated_at
    await second.runtime._start_worker(contract,restored)
    after=second.runtime._store.read_task(TENANT_ID,contract.task_id)
    assert after.projection.status is TaskStatus.PARSING
    assert after.projection.created_at==before.projection.created_at
    assert second.runtime._store.read_latest_event(TENANT_ID,contract.task_id).sequence==1
