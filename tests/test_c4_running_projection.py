"""A claimed Core task must display working while its provider is still pending."""
import asyncio
from datetime import datetime,UTC
import json,os,shutil,sqlite3,sys
from pathlib import Path
import httpx,pytest
from tests.gate_c4 import product_smoke as local
from tests.gate_c4.server import candidate_server
from src.application.miniapp import MiniAppCore
from src.workers.codex_cli import CodexCliError
from src.core.policy import task_contract_digest

PRIVATE='SYNTHETIC_PRIVATE_PROVIDER_PATH_C:/private/exception.txt'

class FaultProvider:
    generation_available=True
    def __init__(self,code):
        self.code=code;self.calls=[];self.entered=asyncio.Event();self.release=asyncio.Event()
    async def start(self):pass
    async def close(self):pass
    async def execute(self,contract):
        self.calls.append(task_contract_digest(contract));self.entered.set()
        await self.release.wait()
        raise CodexCliError(self.code) from RuntimeError(PRIVATE)

@pytest.mark.asyncio
@pytest.mark.parametrize('code,expected_calls',[('worker_failed',2),('worker_timeout',1)])
async def test_claimed_task_is_working_until_provider_failure_without_duplicate(tmp_path,code,expected_calls):
    old=local.old
    workspace=tmp_path/'workspace';temp=workspace/'temp';temp.mkdir(parents=True)
    state=old.SQLiteTelegramState(tmp_path/'telegram.sqlite3')
    actions=old.DurableTelegramActionStore(state)
    gateway=old.TelegramGateway(actor_bindings={(old.USER,old.USER):old.ActorBinding(
        tenant_id=old.TENANT,actor_identity='telegram:c4-synthetic-owner',role='owner',auth_context_ref=old.AUTH)},
        update_id_store=old.PollingCheckpointUpdateIdStore(),callback_token_store=actions)
    api=local.LocalTransport(tmp_path,None)
    runtime=old.build_gate5a4_runtime(gateway=gateway,sqlite_path=tmp_path/'tasks.sqlite3',
        destination_refs={old.TENANT:old.DEST},worktree=workspace,codex_executable=old.bundled_codex_path(),
        git_executable=shutil.which('git'),python_executable=sys.executable,codex_home=Path.home()/'.codex',
        system_root=os.environ.get('SystemRoot','C:/Windows'),temp_root=temp,
        path_entries=(Path(sys.executable).parent,Path(shutil.which('git')).parent),owner_read_root=None,project_context=None,nobus_memory=None)
    provider=FaultProvider(code)
    # Only the external provider boundary is replaced. ResilientCodexAdapter,
    # Gate5A4Runtime, durable admission/queue, failure projection and HTTP remain real.
    runtime._worker._primary=provider
    control=old.DurableProductTelegramControlPlane(gateway,api,task_runtime=runtime,
        task_confirmations=old.DurableTaskConfirmationStore(state),patch_confirmations=old.DurablePatchConfirmationStore(state),
        action_store=actions,voice_service=None,enable_semantic_admission=False,enable_extended_routes=False,
        execution_concurrency=1,telegram_state=state,task_tenants=(old.TENANT,),
        task_status_sender=old.TelegramStatusSender(api,{old.TENANT:(old.DEST,old.USER)},technical_details=False))
    clock=local.Clock()
    core=MiniAppCore(store=runtime._store,task_admission=control,bot_token=local.BOT_TOKEN,owner_user_id=old.USER,tenant_id=old.TENANT,clock=clock)
    ingress=gateway.process_update(old.update('Составь три пункта плана проверки проекта.',None))
    message,envelope=ingress.payload,ingress.envelope
    prepared=await runtime.build_instruction('[profile:semantic.no_effect]\nСоставь три пункта плана проверки проекта.',envelope)
    assert prepared.contract.quality_profile=='gate-c1-semantic-no-effect@1'
    try:
        assert await control._submit_draft(prepared,message,envelope,deferred_admission=True)
        await asyncio.wait_for(provider.entered.wait(),5)
        async with candidate_server(core) as origin:
            async with httpx.AsyncClient(base_url=origin,timeout=5) as client:
                journey=local.HttpJourney(client,clock)
                await journey.authenticate()
                for path in ['/','/app.js','/styles.css']:await journey.request('GET',path)
                task_id=str(prepared.contract.task_id)
                before=(await journey.request('GET','/api/tasks/'+task_id)).json()
                assert before['terminal'] is False
                assert before['status'] == 'working'
                assert before['status_label'] == 'В работе'
                assert 'ждёт выполнения' not in before['reason_label']
                snapshot=runtime._store.read_task(old.TENANT,prepared.contract.task_id)
                assert snapshot.projection.status.value == 'parsing'
                assert not (await journey.request('GET','/api/tasks/'+task_id+'/result?revision=1',expected=404)).is_success
                provider.release.set()
                async with asyncio.timeout(8):
                    while True:
                        detail=(await journey.request('GET','/api/tasks/'+task_id)).json()
                        if detail['terminal'] and state.queue_counts()==(0,0):break
                        await asyncio.sleep(.03)
                assert detail['status']!='ready'
                result=await journey.request('GET','/api/tasks/'+task_id+'/result?revision=1',expected=404)
                events=(await journey.request('GET','/api/tasks/'+task_id+'/events')).json()
                await control.deliver_pending()
                counts_before=len(runtime._store.list_tasks(old.TENANT))
                assert counts_before==1 and len(provider.calls)==expected_calls
                assert len(set(provider.calls))==1
                # Exact same admitted envelope/contract re-enqueued after completion.
                # The real restore path must recognize terminal authority without a second worker run.
                assert await control._submit_draft(prepared,message,envelope,deferred_admission=True)
                async with asyncio.timeout(5):
                    while state.queue_counts()!=(0,0):await asyncio.sleep(.03)
                await control.deliver_pending()
                assert len(provider.calls)==expected_calls and len(runtime._store.list_tasks(old.TENANT))==1
                rendered=json.dumps({'detail':detail,'events':events,'rows':api.rows,'status':control._status_text()},ensure_ascii=False)
                assert PRIVATE not in rendered and 'C:/private' not in rendered and 'worker_failed' not in rendered and 'worker_timeout' not in rendered
                with sqlite3.connect(runtime._store._path) as db:
                    outbox=db.execute('SELECT status,COUNT(*) FROM outbox_messages GROUP BY status').fetchall()
                    tasks=db.execute('SELECT COUNT(*) FROM task_snapshots').fetchone()[0]
                assert outbox==[('acked',1)] and tasks==1
                assert not state.list_progress()
    finally:
        provider.release.set()
        await control.close()
        await runtime.close()
