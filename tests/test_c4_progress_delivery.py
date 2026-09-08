"""Only the exact final outbox ACK permits deletion of an owned progress message."""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from src.application.durable_product import DurableProductTelegramControlPlane
from src.models.task import TaskStatus
from src.orchestrator.state_manager import StateManager
from src.storage import OutboxStatus, SQLiteStore
from src.storage.outbox import delivery_parts
from tests.test_c3_delivery_parts import Clock, runtime
from tests.test_durable_telegram_state import _store
from tests.test_miniapp_result import _answered_store, DESTINATION
from tests.test_sqlite_store import persist, envelope, contract_for


class Sender:
    def __init__(self, *, fail_document=False):
        self.calls = []
        self.fail_document = fail_document

    def delivery_manifest(self, message):
        content = (message.user_message or 'Не удалось выполнить задачу.').encode('utf-8')
        return delivery_parts(message, (('text', content), ('document', content)))

    async def send_part(self, message, part):
        self.calls.append((message.message_id, part.index))
        if part.index == 1 and self.fail_document:
            raise RuntimeError('synthetic TXT timeout')
        return True


class Api:
    def __init__(self):
        self.deleted = []
        self.edits = []
        self.delete_failure = False

    async def delete_message(self, chat_id, message_id):
        if self.delete_failure:
            raise RuntimeError('synthetic delete unavailable')
        self.deleted.append((chat_id, message_id))

    async def edit_message_text(self, chat_id, message_id, text, *, buttons=None):
        self.edits.append((chat_id, message_id, text, buttons))


def control_for(store, state, clock, sender, api):
    control = object.__new__(DurableProductTelegramControlPlane)
    control._admission_readiness = None
    control._task_runtime = control._product_runtime = runtime(store, clock)
    control._task_status_sender = sender
    control._task_tenants = ('tenant-a',)
    control._telegram_state = state
    control._api = api
    return control


@pytest.fixture
def setup(tmp_path):
    store, task, message = _answered_store(tmp_path / 'tasks.sqlite3')
    foreign = persist(store, tenant_id='tenant-b')
    state = _store(tmp_path)
    ref = state.save_progress(tenant_id=task.tenant_id, task_id=task.id,
                              chat_id=42, message_id=321)
    clock = Clock()
    sender, api = Sender(), Api()
    control = control_for(store, state, clock, sender, api)
    return control, store, state, task, message, clock, sender, api, ref, foreign


@pytest.mark.asyncio
async def test_text_ack_and_txt_timeout_preserve_progress_until_remaining_part_ack(setup):
    c, store, state, task, message, clock, sender, api, ref, _ = setup
    sender.fail_document = True
    assert await c.deliver_pending() == 0
    assert store.read_outbox_message(task.tenant_id, message.message_id).status is OutboxStatus.PENDING
    assert [ack is not None for _, ack in store.read_delivery_parts(task.tenant_id, message.message_id)] == [True, False]
    await c._settle_task_progress(task.tenant_id, task.id, show_pending=True)
    assert state.read_progress(tenant_id=task.tenant_id, task_id=task.id) == ref
    assert not api.deleted
    assert 'Доставка ответа ещё не подтверждена' in api.edits[-1][2]
    sender.fail_document = False
    clock.advance(2)
    assert await c.deliver_pending() == 1
    assert sender.calls == [(message.message_id, 0), (message.message_id, 1), (message.message_id, 1)]
    assert api.deleted == [(42, 321)]
    assert state.read_progress(tenant_id=task.tenant_id, task_id=task.id) is None
    assert await c.deliver_pending() == 0
    assert len(sender.calls) == 3 and api.deleted == [(42, 321)]


@pytest.mark.asyncio
async def test_restart_after_ack_before_cleanup_uses_saved_ref_without_resending(setup, tmp_path):
    c, store, state, task, message, clock, sender, api, ref, _ = setup
    outcome = await c._task_runtime.deliver_pending(task.tenant_id, sender)
    assert outcome[0].status is OutboxStatus.ACKED
    assert state.read_progress(tenant_id=task.tenant_id, task_id=task.id) == ref
    reopened = control_for(SQLiteStore(store._path), _store(tmp_path), clock, sender, api)
    assert await reopened.deliver_pending() == 0
    assert sender.calls == [(message.message_id, 0), (message.message_id, 1)]
    assert api.deleted == [(42, 321)] and not reopened._telegram_state.list_progress()


@pytest.mark.asyncio
async def test_delete_failure_keeps_reference_and_next_cycle_retries_only_cleanup(setup):
    c, store, state, task, message, clock, sender, api, ref, _ = setup
    api.delete_failure = True
    assert await c.deliver_pending() == 1
    assert state.read_progress(tenant_id=task.tenant_id, task_id=task.id) == ref
    assert not api.deleted
    api.delete_failure = False
    assert await c.deliver_pending() == 0
    assert api.deleted == [(42, 321)] and not state.list_progress()
    assert sender.calls == [(message.message_id, 0), (message.message_id, 1)]


@pytest.mark.asyncio
async def test_foreign_task_or_tenant_ack_cannot_delete_an_unrelated_reference(setup):
    c, store, state, task, message, clock, sender, api, ref, foreign = setup
    foreign_ref = state.save_progress(tenant_id=foreign.tenant_id, task_id=foreign.id,
                                     chat_id=84, message_id=987)
    unknown_ref = state.save_progress(tenant_id=task.tenant_id, task_id=uuid4(),
                                     chat_id=42, message_id=654)
    same_id_foreign_ref = state.save_progress(tenant_id=foreign.tenant_id, task_id=task.id,
                                             chat_id=84, message_id=456)
    assert await c.deliver_pending() == 1
    assert api.deleted == [(42, 321)]
    assert set(state.list_progress()) == {foreign_ref, unknown_ref, same_id_foreign_ref}


@pytest.mark.asyncio
async def test_stale_snapshot_cannot_authorize_deletion_using_another_revision_ack(setup, monkeypatch):
    c, store, state, task, message, clock, sender, api, ref, _ = setup
    assert (await c._task_runtime.deliver_pending(task.tenant_id, sender))[0].status is OutboxStatus.ACKED
    snapshot = store.read_task(task.tenant_id, task.id)
    # Simulate an old projection read. The real verified-answer reader rechecks
    # the current SQLite snapshot instead of accepting this stale revision.
    monkeypatch.setattr(store, 'read_task', lambda tenant, task_id:
                        snapshot.model_copy(update={'revision': snapshot.revision - 1}))
    await c._settle_task_progress(task.tenant_id, task.id)
    assert state.read_progress(tenant_id=task.tenant_id, task_id=task.id) == ref
    assert not api.deleted


def failed_notice(store, tenant_id, destination):
    incoming = envelope(tenant_id=tenant_id, idempotency_key='failed-' + tenant_id,
                        external_message_id='failed:' + tenant_id)
    contract = contract_for(incoming)
    manager = StateManager()
    task = asyncio.run(manager.create_from_contract(contract))
    created, _ = store.claim_ingress_with_task(incoming, contract, task)
    assert created
    parsing = asyncio.run(manager.update(task.id, status=TaskStatus.PARSING))
    store.save_task(parsing, expected_revision=1)
    failed = asyncio.run(manager.update(task.id, status=TaskStatus.FAILED,
                                       error_message='synthetic stopped task'))
    message = store.save_task_and_enqueue_status(failed, expected_revision=2,
                                                destination_ref=destination).message
    return failed, message


@pytest.fixture
def failed_setup(tmp_path):
    store = SQLiteStore(tmp_path / 'tasks.sqlite3')
    failed, _ = failed_notice(store, 'tenant-a', DESTINATION)
    state, clock, sender, api = _store(tmp_path), Clock(), Sender(), Api()
    ref = state.save_progress(tenant_id=failed.tenant_id, task_id=failed.id,
                              chat_id=42, message_id=321)
    return control_for(store, state, clock, sender, api), failed, state, api, ref


@pytest.mark.asyncio
async def test_failed_terminal_notice_requires_its_own_fingerprint_ack(failed_setup):
    c, task, state, api, ref = failed_setup
    await c._settle_task_progress(task.tenant_id, task.id)
    assert state.read_progress(tenant_id=task.tenant_id, task_id=task.id) == ref
    assert not api.deleted
    assert await c.deliver_pending() == 1
    assert api.deleted == [(42, 321)] and not state.list_progress()


@pytest.fixture
def foreign_ack_setup(setup):
    c, store, state, task, message, clock, sender, api, ref, _ = setup
    destination = 'sha256:' + 'f' * 64
    foreign, foreign_message = failed_notice(store, 'tenant-b', destination)
    foreign_ref = state.save_progress(tenant_id=foreign.tenant_id, task_id=foreign.id,
                                     chat_id=84, message_id=987)
    other_runtime = runtime(store, clock)
    other_runtime._destination_refs = {'tenant-b': destination}
    return c, state, api, other_runtime, foreign_message, foreign_ref, Sender()


@pytest.mark.asyncio
async def test_valid_foreign_ack_in_shared_store_cannot_authorize_cleanup(foreign_ack_setup):
    c, state, api, other_runtime, foreign_message, foreign_ref, other_sender = foreign_ack_setup
    outcomes = await other_runtime.deliver_pending('tenant-b', other_sender)
    assert len(outcomes) == 1 and outcomes[0].status is OutboxStatus.ACKED
    assert outcomes[0].message_id == foreign_message.message_id
    assert await c.deliver_pending() == 1
    assert api.deleted == [(42, 321)]
    assert state.read_progress(tenant_id='tenant-b', task_id=foreign_ref.task_id) == foreign_ref
