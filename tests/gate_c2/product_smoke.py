"""B02 actual product smoke, explicit opt-in; never runs inference on import.

Each invocation is one processing phase. Reopening the same --run/--scenario
in the next process exercises durable restart without manufacturing state.
Provider phases require an exact authorized trial; historical ledgers are never reset.
Zero-provider preparation uses the historical expired ledger without inference.
"""
from __future__ import annotations
import argparse
import ast
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / '.runtime/c2/closure/product-plan'
FIXTURES = ROOT / 'tests/gate_c2/PRODUCT-FIXTURES.json'
sys.path.insert(0, str(ROOT))
from codex_cli_bin import bundled_codex_path
from openai_codex import AsyncCodex
from openai_codex.generated.v2_all import ConfigReadResponse
from src.application.gate5a4 import build_gate5a4_runtime
from src.application.durable_product import DurableProductTelegramControlPlane
from src.application.durable_telegram_state import SQLiteTelegramState
from src.application.durable_confirmations import DurableTaskConfirmationStore, DurablePatchConfirmationStore, DurableTelegramActionStore
from src.application.durable_semantic import DurableSemanticClarificationStore
from src.application.semantic_admission import SemanticAdmissionService
from src.transport.telegram import TelegramGateway, ActorBinding, PollingCheckpointUpdateIdStore
from src.transport.telegram.bot_api import TelegramBotApi, TelegramStatusSender, TelegramPollingBoundary
from src.transport.telegram.sqlite_checkpoint import SQLitePollingCheckpointStore
from src.voice import IsolatedFasterWhisperTranscriber, VoicePreviewService
from src.storage.outbox import OutboxMessage,artifact_for_message
from src.transport.telegram.bot_api import _status_text,_status_message_chunks

TENANT = 'c2-synthetic-owner'
USER = 911001
AUTH = 'sha256:' + '1' * 64
DEST = 'sha256:' + '2' * 64
BASE = 'https://chatgpt.com/backend-api/codex'
MODEL = 'gpt-5.6-sol'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe(value):
    # No provider exception/diagnostic output is persisted. Reject accidental
    # credential-shaped strings even in the synthetic content path.
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    if re.search(r'(?i)(?:sk-[A-Za-z0-9_-]{15,}|Bearer\s+\S+|[A-Z]:\\Users\\|BEGIN (?:RSA |OPENSSH )?PRIVATE KEY)', encoded):
        raise RuntimeError('unsafe_evidence_content')
    return value


def write(path, value):
    data = json.dumps(safe(value), ensure_ascii=False, indent=2, default=str) + '\n'
    temporary = path.with_suffix(path.suffix + '.new')
    with temporary.open('w', encoding='utf-8') as handle:
        handle.write(data); handle.flush(); os.fsync(handle.fileno())
    temporary.replace(path)


class Budget:
    def __init__(self, run, *, max_turns=24, max_seconds=1200):
        self.max_turns = max_turns
        self.max_seconds = max_seconds
        self.path = run / 'budget.sqlite3'
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS budget (singleton INTEGER PRIMARY KEY CHECK(singleton=1), started REAL, turns INTEGER NOT NULL)')
            db.execute('INSERT OR IGNORE INTO budget VALUES(1,NULL,0)')
            db.execute('CREATE TABLE IF NOT EXISTS calls (n INTEGER PRIMARY KEY, scenario TEXT, kind TEXT, started REAL, finished REAL, status TEXT, usage TEXT)')
    def snapshot(self):
        with sqlite3.connect(self.path) as db:
            started, count = db.execute('SELECT started,turns FROM budget WHERE singleton=1').fetchone()
        return {'started_utc_epoch': started, 'turns_reserved': count, 'remaining_seconds': self.max_seconds if started is None else max(0, self.max_seconds - (time.time() - started))}
    def reserve(self, scenario, kind):
        with sqlite3.connect(self.path, timeout=5) as db:
            db.execute('BEGIN IMMEDIATE')
            started, count = db.execute('SELECT started,turns FROM budget WHERE singleton=1').fetchone()
            now = time.time()
            if count >= self.max_turns or (started is not None and now-started >= self.max_seconds):
                raise RuntimeError('authorization_budget_exhausted')
            db.execute('UPDATE budget SET started=COALESCE(started,?),turns=turns+1 WHERE singleton=1', (now,))
            n = count + 1
            db.execute('INSERT INTO calls VALUES(?,?,?,?,NULL,?,NULL)', (n, scenario, kind, now, 'RESERVED'))
        return n
    def finish(self, n, status, usage=None):
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE calls SET finished=?,status=?,usage=? WHERE n=?', (time.time(),status,json.dumps(usage),n))


class GuardedTurn:
    def __init__(self, real, number, budget, folder):
        self.real, self.number, self.budget, self.folder = real, number, budget, folder
    def __getattr__(self, name): return getattr(self.real, name)
    async def run(self):
        try:
            result = await self.real.run()
            usage = getattr(result, 'usage', None)
            self.budget.finish(self.number, 'RETURNED', usage.model_dump(mode='json') if usage is not None else None)
            write(self.folder / f'model-turn-{self.number:02d}.json', {'n': self.number, 'final_response': getattr(result, 'final_response', None), 'usage_available': usage is not None})
            return result
        except BaseException as error:
            self.budget.finish(self.number, type(error).__name__)
            raise


class GuardedThread:
    def __init__(self, real, budget, scenario, folder):
        self.real, self.budget, self.scenario, self.folder = real, budget, scenario, folder
    def __getattr__(self, name): return getattr(self.real, name)
    async def turn(self, *args, **kwargs):
        if kwargs.get('model') != MODEL or str(kwargs.get('effort')) not in {'high', 'ReasoningEffort.high'} or kwargs.get('service_tier') != 'fast':
            raise RuntimeError('model_settings_outside_authorization')
        if str(kwargs.get('approval_mode')) not in {'deny-all', 'deny_all', 'ApprovalMode.deny_all'} or str(kwargs.get('sandbox')) not in {'read-only', 'read_only', 'Sandbox.read_only'}:
            raise RuntimeError('turn_permissions_outside_authorization')
        schema = kwargs.get('output_schema', {})
        kind = 'compiler' if 'operations' in schema.get('properties', {}) else 'downstream'
        n = self.budget.reserve(self.scenario, kind)
        try:
            if kind == 'compiler':
                write(self.folder / f'model-input-{n:02d}.json', {
                    'n':n, 'prompt':json.loads(args[0]), 'schema_sha256':hashlib.sha256(
                        json.dumps(schema,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()})
            real = await self.real.turn(*args, **kwargs)
        except BaseException as error:
            self.budget.finish(n, type(error).__name__)
            raise
        return GuardedTurn(real, n, self.budget, self.folder)


class GuardedClient:
    def __init__(self, config, budget, scenario, folder):
        # Routing-only overrides; product model/protocol/tool sandbox stay real.
        config = replace(config, config_overrides=(*config.config_overrides,
            'model_provider="openai"', f'openai_base_url="{BASE}"',
            'forced_login_method="chatgpt"'))
        self.real = AsyncCodex(config)
        self.budget, self.scenario, self.folder = budget, scenario, folder
        self.proc = None
    def __getattr__(self, name): return getattr(self.real, name)
    async def __aenter__(self):
        stage = 'starting'
        try:
            await self.real.__aenter__()
            self.proc = self.real._client._sync._proc
            stage = 'account'
            account = await self.real.account(refresh_token=False)
            # Official SDK Account is a RootModel discriminated union.
            principal = account.account.root if account.account is not None else None
            if getattr(principal, 'type', None) != 'chatgpt':
                raise RuntimeError('sdk_account_not_chatgpt')
            stage = 'routing'
            response = await self.real._client.request('config/read', {'includeLayers': False}, response_model=ConfigReadResponse)
            cfg = response.config
            extra = cfg.model_extra or {}
            # Both keys were observed in installed 0.144.4 config/read.
            if cfg.model_provider != 'openai' or extra.get('openai_base_url') != BASE:
                raise RuntimeError('sdk_effective_endpoint_not_verified')
            write(self.folder / ('sdk-preflight-' + str(time.time_ns()) + '.json'), {
                'status': 'VERIFIED', 'account': 'chatgpt', 'provider': cfg.model_provider,
                'base_url': BASE, 'model': MODEL, 'reasoning': 'high', 'tier': 'fast',
                'region_retention': 'UNKNOWN', 'model_turns_before_guard': 0})
            return self
        except BaseException as error:
            write(self.folder / ('sdk-preflight-' + str(time.time_ns()) + '.json'), {
                'status': 'BLOCKED', 'stage': stage, 'error_class': type(error).__name__,
                'model_turns_before_guard': 0})
            await self.close()
            raise
    async def __aexit__(self, _exc_type, _exc, _tb):
        await self.close()
    async def thread_start(self, **kwargs):
        config = kwargs.get('config', {})
        if kwargs.get('ephemeral') is not True or config.get('web_search') != 'disabled' or config.get('mcp_servers') != {}:
            raise RuntimeError('thread_permissions_outside_authorization')
        if any(config.get('features', {}).get(key) is not False for key in ('apps','browser_use','code_mode','image_generation','multi_agent','shell_tool','unified_exec')):
            raise RuntimeError('thread_tools_outside_authorization')
        real = await self.real.thread_start(**kwargs)
        return GuardedThread(real, self.budget, self.scenario, self.folder)
    async def close(self):
        proc = self.proc or self.real._client._sync._proc
        await self.real.close()
        if proc is not None and proc.poll() is None:
            raise RuntimeError('app_server_remains_alive')


class LocalTransport(TelegramBotApi):
    # Deliberate transport-only substitute; no TelegramBotApi network client.
    def __init__(self, folder, audio=None):
        self.folder, self.audio = folder, audio
        self.updates = []
        self.log = folder / 'transport.json'
        self.rows = json.loads(self.log.read_text('utf-8')) if self.log.exists() else []
    def append(self, kind, **values):
        self.rows.append({'kind': kind, **values})
        write(self.log, self.rows)
        return len(self.rows)
    async def get_updates(self, *, offset=None, timeout=0, limit=100):
        # Telegram returns only updates at or beyond the durable offset.
        return [u for u in self.updates if offset is None or u['update_id'] >= offset][:limit]
    async def send_message(self, chat_id, text, **kwargs):
        if chat_id != USER: raise RuntimeError('foreign_delivery')
        return self.append('message', text=text, **kwargs)
    async def delete_message(self, chat_id, message_id):
        if chat_id != USER: raise RuntimeError('foreign_delivery')
        self.append('delete-local-message', message_id=message_id)
    async def answer_callback_query(self, query_id, **kwargs):
        self.append('answer-local-callback', **kwargs)
    async def download_file(self, file_id, *, size_limit):
        if file_id != 'c2-synthetic-audio' or self.audio is None:
            raise RuntimeError('unexpected_audio_source')
        data = self.audio.read_bytes()
        if not 0 < len(data) <= size_limit: raise RuntimeError('audio_size_invalid')
        self.append('local-download', sha256=hashlib.sha256(data).hexdigest())
        return data
    async def send_document(self, chat_id, filename, content, **kwargs):
        if chat_id != USER or Path(filename).name != filename:
            raise RuntimeError('foreign_document')
        # Product answer artifact, projected only to own synthetic evidence.
        target = self.folder / 'artifacts' / filename
        target.parent.mkdir(exist_ok=True)
        if target.exists() and target.read_bytes() != content: raise RuntimeError('artifact_collision')
        safe(content.decode('utf-8'))
        target.write_bytes(content)
        return self.append('document', filename=filename, sha256=digest(target))


async def poll_update(api, boundary, payload):
    api.updates = [payload]
    result = await boundary.poll_once(timeout=0)
    api.append('poll', next_offset=result.next_offset, acknowledged=result.acknowledged,
        retry_required=result.retry_required)
    if result.retry_required:
        raise RuntimeError('polling_update_not_acknowledged')


class ObservedVoice(VoicePreviewService):
    def __init__(self, engine, folder, phase):
        super().__init__(engine, folder/'voice-temp', 10*1024**2, 2000)
        self.folder = folder
        self.phase = phase
    async def preview_from_bytes(self, audio):
        if self.phase != 'admit':
            raise RuntimeError('asr_not_authorized_in_this_phase')
        result = await super().preview_from_bytes(audio)
        write(self.folder / ('asr-' + str(time.time_ns()) + '.json'), result.model_dump(mode='json'))
        return result


class ObservedAdmission(SemanticAdmissionService):
    def __init__(self, real_runtime, folder):
        super().__init__(real_runtime)
        self.folder = folder
    async def admit(self, canonical, bindings):
        result = await super().admit(canonical, bindings)
        path = self.folder / ('admission-' + str(time.time_ns()) + '.json')
        write(path, {'owner_text': canonical.owner_text, 'modality': canonical.modality,
            'proposal': result.proposal.model_dump(mode='json'),
            'decision': result.decision.model_dump(mode='json'),
            'trusted_context': result.context.model_dump(mode='json')})
        return result


def update(text=None, audio=None, reply=False, new_reply=False):
    msg = {'message_id': (103 if new_reply else 102) if reply else 101, 'from': {'id': USER}, 'chat': {'id': USER}}
    if text is not None: msg['text'] = text
    else:
        with wave.open(str(audio)) as wav:
            duration = max(1, int(wav.getnframes()/wav.getframerate()+.999))
        msg['voice'] = {'file_id': 'c2-synthetic-audio', 'file_unique_id': digest(audio), 'duration': duration, 'file_size': audio.stat().st_size}
    if reply: msg['reply_to_message'] = {'message_id': 101}
    return {'update_id': msg['message_id'], 'message': msg}


def cli_status(home, cwd):
    env = dict(os.environ, CODEX_HOME=str(home))
    result = subprocess.run([str(bundled_codex_path()), 'login', 'status'], cwd=cwd, env=env,
        capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    output = (result.stdout + result.stderr).decode('utf-8',errors='replace').lower()
    status = 'CHATGPT' if result.returncode == 0 and 'logged in using chatgpt' in output else 'BLOCKED'
    del result, output
    return status


def source_binding(model):
    paths = [p for p in subprocess.check_output(['git','ls-files','src','scripts'],cwd=ROOT,text=True).splitlines() if p.endswith('.py')]
    product = subprocess.check_output(['git','log','-1','--format=%H','--','src','scripts'],cwd=ROOT).decode().strip()
    return {'product_source_revision': product,
        'product_source_tree': subprocess.check_output(['git','rev-parse',product+'^{tree}'],cwd=ROOT).decode().strip(),
        'sources': {p:digest(ROOT/p) for p in paths}, 'harness_sha256': digest(__file__), 'executor_sha256': digest(ROOT/'tests/gate_c2/product_smoke_runner.py'),
        'resource_budget_helper_sha256': digest(ROOT/'tests/gate_c2/qualification/runner.py'),
        'fixtures_sha256': digest(FIXTURES),
        'protocol_sha256':digest(ROOT/'tests/gate_c2/qualification/PROTOCOL.json'),
        'asr_config':{'beam_size':8,'int8':True,'cpu':True,'local_only':True},
        'model_files':{p.name:digest(p) for p in sorted(model.iterdir()) if p.is_file()},
        'isolated_worker_sha256':digest(ROOT/'src/voice/isolated_worker.py'),
        'windows_job_sha256':digest(ROOT/'src/workers/windows_job.py')}


def outbox_projection(folder):
    with sqlite3.connect(f"file:{(folder/'tasks.sqlite3').as_posix()}?mode=ro",uri=True) as db:
        messages=[dict(zip(('message_id','task_id','status','message_digest'),row)) for row in db.execute('SELECT message_id,task_id,status,message_digest FROM outbox_messages ORDER BY message_id')]
        receipts=[dict(zip(('message_id','receipt_id','receipt_type','receipt_digest'),row)) for row in db.execute('SELECT message_id,receipt_id,receipt_type,receipt_digest FROM outbox_receipts ORDER BY message_id,receipt_id')]
    return {'messages':messages,'receipts':receipts}


def assert_ready_delivery(folder,api,state):
    with sqlite3.connect(f"file:{(folder/'tasks.sqlite3').as_posix()}?mode=ro",uri=True) as db:
        messages=[OutboxMessage.model_validate_json(row[0]) for row in db.execute('SELECT message_json FROM outbox_messages')]
        answered=[m for m in messages if m.task_status.value=='answered']
        if len(answered)!=1 or answered[0].status.value!='acked':raise RuntimeError('one_ready_outbox_not_proven')
        m=answered[0]
        acks=db.execute("SELECT COUNT(*) FROM outbox_receipts WHERE message_id=? AND receipt_type='ack'",(str(m.message_id),)).fetchone()[0]
        if acks!=1:raise RuntimeError('one_ready_ack_not_proven')
    artifact=artifact_for_message(m)
    if artifact is None:raise RuntimeError('ready_artifact_binding_missing')
    documents=[r for r in api.rows if r['kind']=='document']
    if len(documents)!=1 or documents[0]['filename']!=artifact.filename or documents[0]['sha256']!=''.join(artifact.content_digest.split(':')[1:]):
        raise RuntimeError('one_ready_document_not_proven')
    if (folder/'artifacts'/artifact.filename).read_bytes()!=artifact.content_bytes():raise RuntimeError('ready_artifact_bytes_mismatch')
    for chunk in _status_message_chunks(_status_text(m,technical_details=False)):
        if sum(r['kind']=='message' and r['text']==chunk for r in api.rows)!=1:raise RuntimeError('one_ready_message_not_proven')
    with sqlite3.connect(state.path) as db:
        if db.execute("SELECT COUNT(*) FROM telegram_jobs WHERE kind NOT IN ('voice','draft')").fetchone()[0]:raise RuntimeError('unexpected_effect_job')


def assert_terminal_no_task(folder,expected,runtime,state,budget,before):
    if runtime._store.list_tasks(TENANT) or outbox_projection(folder)['messages']:
        raise RuntimeError('unexpected_task_or_outbox')
    with sqlite3.connect(state.path) as db:
        if db.execute("SELECT COUNT(*) FROM telegram_jobs WHERE kind!='voice'").fetchone()[0]:
            raise RuntimeError('unexpected_draft_or_effect')
    admissions=list(folder.glob('admission-*.json'))
    if expected=='cancel':
        if admissions or budget.snapshot()['turns_reserved']!=before['turns_reserved']:
            raise RuntimeError('cancel_started_compiler')
        with sqlite3.connect(state.path) as db:
            if db.execute("SELECT COUNT(*) FROM telegram_jobs WHERE kind='voice' AND status!='finished'").fetchone()[0]:
                raise RuntimeError('cancel_not_finished')
    else:
        if len(admissions)!=1: raise RuntimeError('actual_unknown_admission_missing')
        actual=json.loads(admissions[0].read_text('utf-8')); decision=actual['decision']; predicate=actual['trusted_context']['predicate_evaluation']
        if predicate['outcome']!='UNKNOWN' or predicate['evaluator']!='MATERIAL_ITEM_STATE_V1' or decision['decision']!='CLARIFY' or decision['decision_stage']!='PREDICATE_UNKNOWN' or decision['predicate_outcome']!='UNKNOWN' or decision['task_contract_allowed'] is not False or decision['effect_allowed'] is not False or decision['selected_capability'] is not None:
            raise RuntimeError('supported_predicate_unknown_not_proven')


async def run(args):
    scope = (ROOT/'.runtime/c2/closure').resolve()
    runroot = args.run.resolve()
    if not runroot.is_relative_to(scope): raise RuntimeError('run_must_stay_in_closure')
    runroot.mkdir(parents=True, exist_ok=True)
    folder = runroot / args.scenario
    folder.mkdir(exist_ok=True)
    binding = source_binding(args.model.resolve())
    binding_path = runroot/'source-binding.json'
    if binding_path.exists() and json.loads(binding_path.read_text('utf-8')) != binding:
        raise RuntimeError('source_changed_since_trial_started')
    if not binding_path.exists(): write(binding_path,binding)
    budget_folder = FOLDER
    max_turns = 24
    max_seconds = 1200
    closure_trial = getattr(args, 'closure_authorized_trial', False)
    if closure_trial and args.unknown_authorized_trial:
        raise RuntimeError('conflicting_trial_authorizations')
    if closure_trial:
        if args.scenario not in {'transform_text','transform_voice','transform_correction_voice',
                                 'conditional_supported_unknown_text','conditional_supported_unknown_voice',
                                 'negation_text','negation_voice','cancel_voice'}:
            raise RuntimeError('scenario_outside_closure_authorization')
        authorization = json.loads((FOLDER/'CLOSURE-TRIAL.json').read_text('utf-8'))
        if authorization.get('status')!='AUTHORIZED' or authorization.get('max_turns')!=24 or authorization.get('continuous_seconds')!=1200:
            raise RuntimeError('closure_provider_trial_not_authorized')
        if authorization.get('binding') != binding:
            raise RuntimeError('closure_authorized_source_changed')
        budget_folder = FOLDER/'closure-trial-20260906'
        budget_folder.mkdir(exist_ok=True)
    if args.unknown_authorized_trial:
        if args.scenario not in {'conditional_supported_unknown_text','conditional_supported_unknown_voice'}:
            raise RuntimeError('scenario_outside_unknown_authorization')
        authorization = json.loads((FOLDER/'UNKNOWN-TRIAL.json').read_text('utf-8'))
        if authorization.get('status')!='AUTHORIZED' or authorization.get('max_turns')!=8 or authorization.get('continuous_seconds')!=600:
            raise RuntimeError('unknown_provider_trial_not_authorized')
        budget_folder = FOLDER/'unknown-trial-20260906'
        budget_folder.mkdir(exist_ok=True)
        max_turns = 8
        max_seconds = 600
    budget = Budget(budget_folder,max_turns=max_turns,max_seconds=max_seconds)  # Old exhausted ledger is never reset.
    fixture_id, modality = args.scenario.rsplit('_',1)
    fixtures = json.loads(FIXTURES.read_text('utf-8'))['cases']
    fixture = next(row for row in fixtures if row['id']==fixture_id)
    workspace = folder/'workspace'
    temp = workspace/'temp'
    workspace.mkdir(exist_ok=True); temp.mkdir(exist_ok=True)
    # No model calls, audio inference or app-server on inspection.
    if args.phase == 'inspect':
        write(folder/'inspect.json', {'binding':binding,'budget':budget.snapshot(),'inference':False})
        return
    if not args.authorized_run: raise RuntimeError('explicit_authorized_run_required')
    status = cli_status(args.codex_home, workspace)
    write(folder/'cli-preflight.json', {'status':status,'executable_sha256':digest(bundled_codex_path()),
        'sdk_version':importlib.metadata.version('openai-codex'),'model_calls':0})
    if status != 'CHATGPT': raise RuntimeError('cli_not_chatgpt')
    provider_phase = args.phase in {'confirm','drain'} or (args.phase=='admit' and modality=='text')
    if provider_phase and not (args.unknown_authorized_trial or closure_trial): raise RuntimeError('provider_trial_not_authorized')
    if provider_phase and budget.snapshot()['remaining_seconds'] <= 0: raise RuntimeError('authorization_time_exhausted')
    state = SQLiteTelegramState(folder/'telegram.sqlite3')
    actions = DurableTelegramActionStore(state)
    gateway = TelegramGateway(actor_bindings={(USER,USER):ActorBinding(tenant_id=TENANT,
        actor_identity='telegram:c2-synthetic-owner', role='owner', auth_context_ref=AUTH)},
        update_id_store=PollingCheckpointUpdateIdStore(),callback_token_store=actions)
    audio = args.audio.resolve() if args.audio else None
    if args.unknown_authorized_trial and modality=='voice' and audio != (ROOT/'.runtime/c2/synthetic-audio/conditional.wav').resolve():
        raise RuntimeError('audio_outside_unknown_authorization')
    if closure_trial and modality=='voice':
        audio_name = {'transform':'transform','transform_correction':'transform','negation':'negation',
                      'conditional_supported_unknown':'conditional','cancel':'direct'}[fixture_id]
        if audio != (ROOT/f'.runtime/c2/synthetic-audio/{audio_name}.wav').resolve():
            raise RuntimeError('audio_outside_closure_authorization')
    if modality == 'voice' and (audio is None or not audio.is_file()): raise RuntimeError('frozen_audio_required')
    if audio is not None:
        audio_binding = {'sha256':digest(audio),'size':audio.stat().st_size}
        existing = folder/'audio-binding.json'
        if existing.exists() and json.loads(existing.read_text('utf-8')) != audio_binding: raise RuntimeError('audio_changed')
        write(existing,audio_binding)
    api = LocalTransport(folder,audio)
    runtime = build_gate5a4_runtime(gateway=gateway,sqlite_path=folder/'tasks.sqlite3',destination_refs={TENANT:DEST},
        worktree=workspace,codex_executable=bundled_codex_path(),git_executable=shutil.which('git'),python_executable=sys.executable,
        codex_home=args.codex_home,system_root=os.environ.get('SystemRoot','C:/Windows'),temp_root=temp,
        path_entries=(Path(sys.executable).parent,Path(shutil.which('git')).parent),
        owner_read_root=None,project_context=None,nobus_memory=None)
    clients = []
    def factory(config):
        client=GuardedClient(config,budget,args.scenario,folder);clients.append(client);return client
    runtime._worker._primary._client_factory=factory
    from scripts.run_telegram_mvp1 import _build_voice_transcriber
    engine = _build_voice_transcriber(args.model.resolve())
    os.environ['HF_HUB_OFFLINE']='1'
    service = ObservedVoice(engine,folder,args.phase)
    control = DurableProductTelegramControlPlane(gateway,api,task_runtime=runtime,
        task_confirmations=DurableTaskConfirmationStore(state),patch_confirmations=DurablePatchConfirmationStore(state),action_store=actions,
        voice_service=service,semantic_admission=ObservedAdmission(runtime,folder),semantic_clarifications=DurableSemanticClarificationStore(state),
        enable_semantic_admission=True,enable_extended_routes=False,execution_concurrency=2,telegram_state=state,
        task_tenants=(TENANT,),task_status_sender=TelegramStatusSender(api,{TENANT:(DEST,USER)},technical_details=False))
    checkpoint = SQLitePollingCheckpointStore(folder/'polling.sqlite3', consumer_id='c2-product-smoke', lease_duration_seconds=240)
    polling = TelegramPollingBoundary(api, control.handle, checkpoint)
    async def intake(payload):
        await poll_update(api, polling, payload)
    phase_id = str(time.time_ns())
    before = budget.snapshot()
    transport_before=len(api.rows)
    result = 'FAIL'
    barrier = None
    with sqlite3.connect(budget.path) as db:
        downstream_before = db.execute("SELECT COUNT(*) FROM calls WHERE kind='downstream'").fetchone()[0]
    try:
        async with asyncio.timeout(min(120,budget.snapshot()['remaining_seconds']) if (args.unknown_authorized_trial or closure_trial) else 120):
            if args.phase == 'assemble':
                pass  # Constructors only: no client start, ASR or model inference.
            elif args.phase == 'admit':
                await intake(update(fixture['text'] if modality=='text' else None,audio))
                if modality=='voice':
                    job=state.claim(lease_owner=control._lease_owner,lease_seconds=60)
                    if job is None or job.kind!='voice': raise RuntimeError('voice_not_durable')
                    await control._execute_voice_with_lease(job)
                    persisted=state.read_voice(tenant_id=job.tenant_id,task_id=job.task_id)
                    if persisted is None or persisted.payload.get('stage')!='waiting' or not persisted.payload.get('preview',{}).get('transcript') or len(list(folder.glob('asr-*.json')))!=1:
                        raise RuntimeError('durable_transcript_preview_missing')
                    with sqlite3.connect(state.path) as db:
                        if db.execute("SELECT COUNT(*) FROM telegram_jobs WHERE kind!='voice'").fetchone()[0]:raise RuntimeError('draft_or_effect_before_confirmation')
                    await intake(update(None,audio))
                    if runtime._store.list_tasks(TENANT) or budget.snapshot()['turns_reserved']!=before['turns_reserved']:
                        raise RuntimeError('task_or_compiler_before_confirmation')
            elif args.phase in {'confirm','cancel'}:
                if modality!='voice': raise RuntimeError('voice_confirmation_required')
                if fixture.get('voice_requires_correction') and not args.correction: raise RuntimeError('explicit_supported_correction_required')
                accepted = 'нет' if args.phase=='cancel' else fixture['text'] if args.correction else 'да'
                write(folder/'owner-confirmation.json',{'text':accepted,'explicit_correction':args.correction,'asr_accuracy_credit':False if args.correction else 'ASSESS_SEPARATELY'})
                await intake(update(accepted,reply=True))
                job=state.claim(lease_owner=control._lease_owner,lease_seconds=60)
                if job is None or job.kind!='voice': raise RuntimeError('confirmed_voice_not_queued')
                # Directly drive the actual phase. Its compiler has a 45s deadline
                # inside the real 60s SQLite lease. Do not schedule a wrapper task
                # that could yield to new draft workers before the restart cut.
                await control._durable_voice.run(job)
                with sqlite3.connect(state.path) as db:
                    pending_drafts = db.execute("SELECT COUNT(*) FROM telegram_jobs WHERE kind='draft' AND status='pending'").fetchone()[0]
                with sqlite3.connect(budget.path) as db:
                    downstream_after = db.execute("SELECT COUNT(*) FROM calls WHERE kind='downstream'").fetchone()[0]
                barrier = {'kind':'actual_voice_run_after_handoff_before_downstream',
                    'uses_lease_heartbeat_wrapper':False,'pending_drafts':pending_drafts,
                    'downstream_turns_during_phase':downstream_after-downstream_before,
                    'authoritative_task_count':len(runtime._store.list_tasks(TENANT))}
                if downstream_after!=downstream_before:
                    raise RuntimeError('downstream_started_before_restart_barrier')
                if fixture['expected']=='ready' and (pending_drafts!=1 or barrier['authoritative_task_count']!=0):
                    raise RuntimeError('deferred_handoff_barrier_not_proven')
            elif args.phase == 'drain':
                await control.start()
                while state.queue_counts() != (0,0):
                    control.assert_healthy(); await asyncio.sleep(.15)
                await control.deliver_pending()
            elif args.phase == 'replay':
                original_tasks=[x.projection.model_dump(mode='json') for x in runtime._store.list_tasks(TENANT)]
                original_count=len(original_tasks)
                original_asr=sorted(p.name for p in folder.glob('asr-*.json'))
                original_outbox=outbox_projection(folder)
                original_ready_messages=[r for r in api.rows if r['kind']=='message' and any((x.get('answer') or '') and (x.get('answer') or '') in r.get('text','') for x in original_tasks)]
                original_budget=budget.snapshot()['turns_reserved']
                original_documents=sum(row['kind']=='document' for row in api.rows)
                await intake(update(fixture['text'] if modality=='text' else None,audio))
                if modality=='voice':
                    confirmation=json.loads((folder/'owner-confirmation.json').read_text('utf-8'))
                    await intake(update(confirmation['text'],reply=True))
                    await intake(update('да',reply=True,new_reply=True))
                await control.start()
                while state.queue_counts() != (0,0):
                    control.assert_healthy(); await asyncio.sleep(.15)
                if [x.projection.model_dump(mode='json') for x in runtime._store.list_tasks(TENANT)]!=original_tasks or outbox_projection(folder)!=original_outbox or sorted(p.name for p in folder.glob('asr-*.json'))!=original_asr:
                    raise RuntimeError('replay_repeated_task')
                if budget.snapshot()['turns_reserved']!=original_budget or sum(row['kind']=='document' for row in api.rows)!=original_documents:
                    raise RuntimeError('replay_repeated_model_or_artifact')
                replay_rows=api.rows[transport_before:]
                previous_messages={r['text'] for r in api.rows[:transport_before] if r['kind']=='message'}
                allowed_status={'Голосовая задача уже обрабатывается.','Эта голосовая запись больше не ожидает подтверждения. Отправьте новую задачу отдельным сообщением.'}
                if any(r['kind']=='message' and r['text'] in previous_messages and r['text'] not in allowed_status for r in replay_rows):
                    raise RuntimeError('replay_repeated_user_result_message')
            if args.phase in {'confirm','cancel','drain','replay'} and fixture['expected'] in {'unknown','cancel'}:
                assert_terminal_no_task(folder,fixture['expected'],runtime,state,budget,before)
            if args.phase in {'drain','replay'}:
                tasks = [row.projection for row in runtime._store.list_tasks(TENANT)]
                if fixture['expected']=='ready':
                    if len(tasks)!=1 or str(tasks[0].status) not in {'answered','TaskStatus.ANSWERED'} or tasks[0].verification_bundle is None or str(tasks[0].verification_bundle.status) not in {'APPROVED','approved','VerificationBundleStatus.APPROVED'}:
                        raise RuntimeError('authoritative_ready_artifact_missing')
                    assert_ready_delivery(folder,api,state)
                elif tasks:
                    raise RuntimeError('conditional_created_task')
            result='PHASE_COMPLETED'
    finally:
        cleanup=[]
        for name, closer in [('control',control.close),('asr',engine.close),('runtime',runtime.close)]:
            try:
                # Direct await runs control.close synchronously until it has set
                # _closing and cancelled newly created workers, before yielding.
                async with asyncio.timeout(20):
                    await closer()
                cleanup.append({'component':name,'closed':True})
            except BaseException:
                cleanup.append({'component':name,'closed':False})
        snapshots=[x.projection.model_dump(mode='json') for x in runtime._store.list_tasks(TENANT)]
        with sqlite3.connect(state.path) as db:
            jobs=[dict(zip(('kind','status','task_id'),row)) for row in db.execute('SELECT kind,status,task_id FROM telegram_jobs')]
        # Read-only projections, no decryption of retained recovery content here.
        write(folder/f'phase-{phase_id}-{args.phase}.json',{'phase':args.phase,'process_id':os.getpid(),'result':result,
            'scenario':args.scenario,'binding':binding,'budget_before':before,'budget_after':budget.snapshot(),
            'tasks':snapshots,'jobs':jobs,'outbox':outbox_projection(folder),'asr_outputs':sorted(p.name for p in folder.glob('asr-*.json')),'cleanup':cleanup,'restart_barrier':barrier,'transport_sha256':digest(api.log) if api.log.exists() else None,
            'overall_acceptance':'PENDING_INDEPENDENT_RUBRIC_AND_RESTART_COMPARISON'})
        if not all(row['closed'] for row in cleanup): raise RuntimeError('cleanup_not_verified')
    print(json.dumps({'phase':args.phase,'result':result,'scenario':args.scenario,'turns':budget.snapshot()['turns_reserved']}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--scenario',required=True,choices=[f'{name}_{mode}' for name in ('transform','transform_correction','cancel','negation','conditional','conditional_supported_unknown') for mode in ('text','voice')])
    parser.add_argument('--phase',choices=['inspect','assemble','admit','confirm','cancel','drain','replay'],default='inspect')
    parser.add_argument('--codex-home',type=Path,required=True)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--audio',type=Path)
    parser.add_argument('--correction',action='store_true')
    parser.add_argument('--authorized-run',action='store_true')
    trial = parser.add_mutually_exclusive_group()
    trial.add_argument('--unknown-authorized-trial',action='store_true')
    trial.add_argument('--closure-authorized-trial',action='store_true')
    args=parser.parse_args()
    try: asyncio.run(run(args))
    except BaseException as error:
        # Deliberately suppress untrusted provider exceptions and raw paths.
        code=str(error) if isinstance(error,RuntimeError) and re.fullmatch('[a-z_]{1,100}',str(error)) else None
        print(json.dumps({'status':'FAILED','error_type':type(error).__name__,'safe_code':code}))
        raise SystemExit(1)

if __name__=='__main__': main()
