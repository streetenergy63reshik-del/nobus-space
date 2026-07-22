# Gate 5A.3 — confirmed Telegram fake tasks

**Статус:** ACCEPTED — L1/L2/L3 PASS
**Дата:** 2026-07-22
**Implementation commit:** `70941d8 feat: add confirmed Telegram fake tasks`
**L4:** для кода/local fake не требовался; существующее разрешение владельца покрывает ответы уже связанному owner-чату. Live Codex, новые credentials/bindings/адресаты и deployment не выполнялись.

## Принятый scope

- `/task <instruction>` создаёт durable content-free Task в `PENDING`, не запуская worker;
- owner получает preview с opaque one-shot token и командами `/confirm` / `/cancel`;
- token связан с exact tenant, actor identity/role, auth context, user/chat и исходным contract;
- `/confirm` единожды запускает только локальный fake-worker, затем L1/L2/L3 и terminal status outbox;
- `/cancel` и expiry переводят exact `PENDING` в `REJECTED`;
- outer SQLite polling checkpoint владеет update replay; send failure может повторно показать тот же challenge, не создавая второй Task;
- raw instruction и raw token остаются в памяти процесса/owner-чате и не сохраняются в SQLite;
- active challenges и retained tombstones делят один global/per-tenant capacity budget;
- Telegram status sender доставляет только content-free task/status/revision/event metadata;
- новая зависимость, live subprocess, filesystem write worker, network worker и live Codex отсутствуют.

## Независимый REWORK

Первое L2/L3 нашло P1: tombstones не учитывались в capacity и позволяли memory churn. Исправление:

- global/per-tenant capacity считает `active + tombstones`;
- tombstone минимизирован и не содержит instruction, raw token или PreparedTask;
- добавлены churn/cross-tenant fairness tests;
- malformed non-string token стабильно возвращает `REJECTED`;
- удалены неиспользуемые result messages и request digest только из tombstone; `_Binding.request_digest` сохранён для conflict detection;
- strict UUID binding исправлен и воспроизведён.

Дополнительно зафиксированы regression-сценарии:

- Telegram send failure после успешного execution → replay не выполняет worker повторно, durable outbox доставляется один раз;
- cancellation сразу после consume → token остаётся one-shot, повторный execution запрещён;
- restart теряет capability fail-closed;
- outbox NACK повторяется без reexecution;
- instruction/token отсутствуют в SQLite bytes.

## Проверки

```text
Gate target:       36 passed
Full repository:   630 passed, 1 skipped, 1 warning
compileall:        PASS
pip check:         No broken requirements found.
git diff --check:  PASS (только Windows LF→CRLF notices)
L2/L3 review #1:  ACCEPTED; P0=0, P1=0, P2=0
L2/L3 review #2:  ACCEPTED; documented availability limitation only
```

Ожидаемое предупреждение — прежний `StarletteDeprecationWarning` о будущем `httpx2`.

## Принятое ограничение

Consume выполняется до execution. Поэтому crash/cancellation после consume может оставить stranded `PENDING/PARSING` без capability и без автоматического resume. Это намеренно fail-closed: повторный worker start запрещён. Durable confirmation/recovery является следующим отдельным улучшением availability, а не основанием ослаблять one-shot безопасность.

## Не входит в Gate

- реальный Codex CLI или любой другой live worker;
- voice download/transcription и сетевой voice confirmation;
- восстановление raw instruction после restart;
- OS service/autostart, monitoring, backup/restore drill;
- новые Telegram owner/chat bindings, credential rotation, remote/push/deployment.

## Локальная активация

Serve-runner с кодом Gate 5A.3 активирован в существующем owner-bound Telegram-контуре 2026-07-22 18:37 Europe/Moscow. Процесс использует Git-ignored `nobus-runtime.local.sqlite3`. Это подтверждает startup/identity/checkpoint composition, но не заменяет owner live-воспроизведение `/task` → `/confirm` → terminal status; оно остаётся следующим шагом. Live Codex не запускался.
