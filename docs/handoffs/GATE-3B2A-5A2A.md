# Gate 3B.2a / 5A.2a — PRE-LIVE durable polling и Windows Job substrate

**Статус:** ACCEPTED — L1/L2/L3 PASS только в offline PRE-LIVE scope
**Дата:** 2026-07-22
**Implementation commit:** `1d4029f feat: add pre-live polling and Windows job substrate`
**L4:** не требовался: реальные child processes, Telegram credentials, сеть и внешняя отправка не запускались

## Принятый scope

### Durable polling checkpoint

- `SQLitePollingCheckpointStore` реализует существующий `PollingCheckpointStore` без новой зависимости;
- одна SQLite-запись на валидированный `consumer_id` хранит offset, generation UUID, owner UUID, expiry, revision и checksum состояния;
- `BEGIN IMMEDIATE` сериализует acquire/reclaim/CAS на одном локальном SQLite-файле;
- lease time берётся только из store-owned clock; caller timestamp не может досрочно reclaim или отравить состояние;
- активный lease блокирует второго consumer, истёкший lease reclaim-ится новой generation без потери offset;
- `load` и `advance` отклоняют истёкший lease; stale generation не может advance/release новый lease;
- offset изменяется только монотонным exact-expected CAS;
- restart, concurrent acquire, expiry, clock rollback, tamper и polling resume воспроизведены локально;
- public persistence error не содержит путь, raw SQLite exception или exception chain.

`state_digest` является checksum для обнаружения повреждения. Это не MAC и не доказательство подлинности против субъекта, который может переписать SQLite и пересчитать digest.

### Windows Job Object substrate

- `WindowsJobLauncher` повторно проверяет exact executable, workspace-contained cwd, фиксированный argv, закрытый env, pipes и creation flags;
- launcher создаёт Job Object с `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` и gated helper до запуска target;
- helper запускается фиксированным Python через `-I`, ждёт startup gate не более 30 секунд и принимает только два allowlisted argv-профиля;
- helper назначается в Job до сигнала gate; target наследует stdin/stdout/stderr, cwd, env и Job membership;
- parent crash до assignment оставляет helper не более чем на bounded wait; crash после assignment закрывает Job handle и активирует kill-on-close;
- ownership Job handle связан с identity process object, а не PID, поэтому PID reuse не создаёт ABA;
- normal exit, tree kill, assignment failure и cancellation reaper закрывают gate/job handles;
- WinAPI signatures явно заданы для 64-bit HANDLE; проверенные x64 размеры структур: 64/48/144 bytes.

## Проверки

```text
Target SQLite/Windows/process/Telegram: 59 passed
Full repository:                      534 passed, 1 warning
compileall:                           PASS
pip check:                            No broken requirements found.
git diff --cached --check:            PASS after EOF normalization
Independent L2/L3:                    ACCEPTED; P0=0, P1=0
```

Независимое ревью нашло и потребовало закрыть:

- caller-controlled future-time lease reclaim;
- load/advance после expiry;
- orphan helper с бесконечным ожиданием gate;
- PID-reuse ABA между Job handles;
- потерю background reaper и cancellation leak до `CloseHandle`;
- неявную передачу stdio helper → target;
- неполный cleanup на failure paths.

## Что не объявлено готовым

- реальный Windows child tree, Job inheritance и kill-on-close не воспроизводились;
- реальный Codex CLI не запускался;
- Telegram token, `getMe`, authenticated allowlist и сеть не подключались;
- live polling, status delivery, kill switch и end-to-end user flow не выполнялись;
- SQLite checksum не заменяет OS access control, секретный MAC или защищённое хранилище;
- deployment, monitoring, restore drill, remote и push отсутствуют.

Следовательно, это **3B.2a/5A.2a PRE-LIVE substrate**, а не завершённые live Gate 3B.2/5A.2.

## Следующая граница и L4

Перед следующим шагом требуется отдельное L4 на точно ограниченный live-сценарий:

1. создать Job Object и запустить allowlisted probe-child, затем независимо доказать descendant kill/stdio/cancellation;
2. подключить реальный Codex только после успешного probe и с минимальным read-only заданием;
3. передать bot token только через secret boundary, выполнить `getMe` и сверить ожидаемый bot identity;
4. активировать один allowlisted user/chat/tenant polling consumer с kill switch;
5. провести один ограниченный text E2E, затем отдельно voice E2E;
6. подтвердить отсутствие token, raw update, audio, prompt и stderr в Git, SQLite, logs и exception chain.

До такого L4 live Gate 3B.2/5A.2 остаются **BLOCKED BY DESIGN**.
