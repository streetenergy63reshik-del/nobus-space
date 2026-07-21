# Gate 4D — actor-bound voice confirmation

**Статус:** ACCEPTED — L1/L2/L3 PASS
**Дата:** 2026-07-21
**Implementation commit:** `438233c feat: add actor-bound voice confirmation`
**L4:** не требуется: только локальные файлы и тесты, без сети, credentials и внешней записи

## Принятый scope

- in-memory store выдаёт ограниченный TTL opaque callback token для точного `VoiceMessage` + `TrustedIngressEnvelope` + `VoicePreview`;
- raw token возвращается только как masked `SecretStr`, в состоянии хранится SHA-256 digest;
- gateway `claim()` и application `confirm()` используют одну state machine;
- подтверждение связано с tenant, actor identity/role, auth context, user/chat, ingress revision/content ref, audio и transcript digest;
- подтверждение single-use: active binding атомарно заменяется минимальным replay tombstone без transcript/raw token;
- global и per-tenant limits учитывают active bindings и зарезервированное tombstone retention;
- clock rollback, token collision, expiry, duplicate/replay, concurrent confirm, cross-tenant/actor/chat и mutated models отклоняются fail-closed;
- публичные ошибки не содержат raw audio, temp path, provider details или exception chain.

## Не входит в Gate

- Telegram downloader, polling/webhook, bot credentials и внешняя сеть;
- live transcription provider;
- runtime wiring с Core/SQLite/outbox;
- durable confirmation across restart: незавершённые in-memory challenge после restart безопасно теряются.

## Evidence

```text
Gate 4D target:                  46 passed
Telegram + voice relevant:     192 passed
Full repository:               460 passed, 1 warning
pip check:                     No broken requirements found.
compileall:                    PASS
git diff --check:              PASS (только Windows LF→CRLF notice)
```

Независимый reviewer повторил replay/ABA, tenant capacity, concurrent duplicate, active expiry и tombstone expiry сценарии. Финальный verdict: `ACCEPT`; P0/P1/P2 не обнаружены.

Единственное предупреждение полного pytest — прежний `StarletteDeprecationWarning` о будущем переходе `starlette.testclient` на `httpx2`; зависимости Gate 4D не менял.

## Изменённые implementation-файлы

- `src/voice/confirmation.py`
- `src/voice/__init__.py`
- `tests/test_voice_confirmation.py`

## Следующий gate

Gate 4F: локальное runtime wiring и restart/recovery E2E. До отдельного L4 нельзя подключать реальные Telegram credentials, polling/webhook, сеть, live subprocess, deploy или внешнюю отправку.
