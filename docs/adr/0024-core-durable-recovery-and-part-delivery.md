# ADR 0024 — Восстановление задачи и доставка по частям

**Статус решения:** ACCEPTED FOR C3 IMPLEMENTATION по поручению владельца выполнить Gate C3 целиком.
**Реализация:** TARGET до приёмки цельного C3.
**Дата:** 6 сентября 2026 года.

Основание: опубликованный C2 `5fdc28ce66dbb072acd6676baf72fe58ae10b4b3`,
tree `c8e756fb00874c5db2f6105c6d65154d0ed243e7`; ADR 0018, 0022 и 0023.
Один Core, существующие SQLite queue/task/outbox, исходный TaskContract и
Core-owned effect authority сохраняются. Этот ADR не меняет смысловой
контракт, capability set, ASR, frontend или live.

## Доказанные пробелы

Рабочая обёртка отключает повтор non-web вычисления. Между RESULT_READY и
outbox сохраняется digest без восстанавливаемых bytes ответа. После crash
DRAFT/L1/L2 не восстанавливаются. Квитанция сообщения не фиксирует отдельные
доставленные части. `/status` объявляет online без живого executor и считает
просроченный lease выполняющейся задачей. HTTP ingress принимает только JSON.

## Решение

1. Admission подтверждается после durable job; восстановление использует тот
   же task/contract и исходный envelope. HTTP multipart является только другим
   представлением bounded text/material input существующего task-create.
   Semantic digest связывает декодированные поля и материал, а не случайный
   boundary или порядок частей. Дубликаты частей, лишние поля, неполное тело,
   неверные MIME/size/digest отклоняются до admission. Другой смысл с тем же
   owner/session/request key даёт conflict; новый key означает новое намерение.
2. Non-web read-only model computation допускает не более двух последовательных
   попыток для `worker_start_failed`/`worker_failed`. Перед повтором неисправная
   generation выведена из работы; общий monotonic deadline не пополняется.
   Protocol/malformed/permission/configuration, timeout и cancellation не
   повторяются. Typed permanent SDK errors не маскируются как transient.
   Web остаётся в прежней границе: один SDK и один разрешённый CLI fallback.
   Mutation UNKNOWN не является model retry. Context cache разделён по tenant.
3. Каждая запись исполнения проверяет текущий queue lease, owner, expiry и
   task/contract binding после получения write lock. Queue lock удерживается
   на время синхронной authoritative записи, исключая reclaim между проверкой
   и commit. Никакого ожидания provider внутри такой транзакции нет. Stale
   generation не может записать result, terminal decision или receipt.
4. Нормализованный sealed answer сохраняется защищённым существующим codec
   вместе с RESULT_READY в существующей task SQLite. Immutable binding:
   tenant/task/contract/result revision и content digest. Это результат
   вычисления, ещё не verdict success. Restart восстанавливает эти bytes и
   повторяет только локальную проверку, затем atomic terminal/outbox CAS.
   Worker и effect заново не запускаются. Повреждение или невосстановимый
   nonterminal state даёт существующее actionable attention/ESCALATE.
   Terminal audit неизменяем; готовый результат не подменяется новым.
5. Existing OutboxArtifact остаётся единственным artifact contract: safe name,
   MIME, size, immutable bytes/digest/revision и exact task/result binding.
   Outbox получает immutable manifest частей (index/total/kind/content digest)
   и отдельные durable receipts. Whole-message ACK невозможен до подтверждения
   всех обязательных частей. Restart пропускает подтверждённые части.
   Неизвестная доставка сохраняется отдельно и допускает только bounded
   delivery recovery. Remote accept до local receipt оставляет узкое
   at-least-once окно; exactly-once Telegram не заявляется.
6. Runtime snapshot использует durable queue/task/outbox и фактическую
   готовность executor. Expired lease означает recovery, dead-letter видим,
   store/worker-down не объявляются online. Existing safe product status
   используется без второго публичного enum. Queue wait, ASR service и общее
   время различаются. Shutdown прекращает intake и ограничивает cleanup;
   незавершённые jobs остаются durable и fenced для того же recovery.

## Приёмка и границы

Матрица C3 содержит 34 negative/crash case, C1/C2 регрессии и реальные
синтетические text/voice/material ответы в отдельном общем бюджете C3.
Frozen candidate требует L1, независимые L2/L3. Старые FAIL/REJECT сохраняются.
C0-F07 закрывается только в backend/recovery части; live operational evidence
остаётся C5/C6. C4 отвечает за конечное получение в UI. MVP1 не READY до C4–C6.
Публикация только обычным PR/merge после PASS; tag/release/deploy/live запрещены.
