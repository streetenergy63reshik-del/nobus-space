# Gate C3 — границы восстановления

Техническое решение — [ADR 0024](../../adr/0024-core-durable-recovery-and-part-delivery.md).
Исходные механизмы и обнаруженные пробелы — [WORKING-CONTRACT](WORKING-CONTRACT.md).
Проверки каждого отказа — [FAILURE-MATRIX](FAILURE-MATRIX.md).
Итоговая приёмка и точные revisions ведутся в [EVIDENCE](EVIDENCE.json).

| Отказ | Состояние и допустимое продолжение | Что не повторяется |
|---|---|---|
| Store недоступен до admission | Запрос не принят; исходный запрос можно повторить после восстановления | ACK/task/worker до durable job |
| ACK потерян после admission | Тот же key и digest возвращают прежнюю identity; rebound даёт conflict | Logical task, исходный материал, контракт |
| Процесс потерян после claim | Истёкшая lease возвращается в bounded очередь; после трёх claims — attention | Запись старой lease/owner после expiry/reclaim |
| Corrupt/poison job | Payload сохраняется; row переводится в failed; следующий FIFO item доступен | Неограниченное исполнение повреждённого input |
| Non-web transient compute | Одна новая попытка того же read-only контракта через новую SDK generation; общий deadline | Capability expansion, effect, web/CLI fallback |
| Protocol/malformed/permission/configuration/timeout/cancel | Без автоматического non-web retry; безопасное завершение и bounded cleanup | Принятие позднего результата; повтор неизвестного effect |
| Результат sealed, verdict ещё не принят | Восстанавливаются те же зашифрованные bytes; локальные проверки и terminal/outbox CAS | Model/provider и новая result revision |
| Прерванный PARSING без sealed результата | Durable failure/attention; provider автоматически не переисполняется | Illegal PARSING→PENDING, memory-only recovery и ACK без завершения |
| Nonterminal Core task без допустимого job | Из собственной валидированной Core projection создаётся failure/attention и outbox; следующий restart идемпотентен | Догадки из повреждённого queue payload; новое вычисление |
| Delivery transient | Immutable manifest; повтор только неподтверждённых частей, до существующего outbox limit | Worker и подтверждённые части |
| Delivery UNKNOWN | TIMEOUT receipt сохраняет неопределённость; только ограниченное recovery доставки | Ложный whole-message ACK |
| Effect UNKNOWN | Существующий effect vault сохраняет UNKNOWN, marker reconciliation только у поддерживающего adapter | Слепой повтор внешнего изменения |
| Shutdown | Intake закрывается сразу; shared cleanup защищён от отмены caller; workers ждутся до30s, effects до5s | Удаление незавершённой durable задачи, late Core commit после release |

Queue lock удерживается через синхронный Core write. Порядок блокировок:
queue → Core; provider/transport не ожидаются под этим lock. Проверка owner,
lease, attempt, срока и payload выполняется после его получения. Part receipts
имеют собственную outbox lease, не заимствуют lease другой исполняемой задачи.

Sealed answer связывает tenant, task, contract, result revision/digest и
нормализованные bytes. Outbox связывает дополнительно task revision/projection
и destination. OutboxArtifact остаётся единственным контрактом файла: safe
name, MIME, size и immutable digest. Локальный путь не служит публичной ссылкой.

Multipart INPUT — ровно metadata JSON и UTF-8 text/plain material в пределах
существующего16KiB body/5s. Material digest, size, safe filename и media type
проверяются до admission. Boundary/порядок частей не создают новое намерение;
дубли частей и изменённое смысловое содержимое с тем же key отклоняются.
Исходный material проходит прежнюю C1 INERT-границу без изменения parser/routing.

`/status` использует tenant-scoped queue/Core/outbox и готовность локального
исполнителя. Просроченные leases не считаются работой; attention, очередь,
ожидание подтверждения и доставка показаны отдельно. Наличие SDK generation
означает готовность локального runtime, а не гарантию доступности провайдера.

Узкое окно remote accept до local receipt остаётся at-least-once для Telegram:
неподтверждённая часть может повториться. Реальная сеть Telegram здесь не
используется. Backend recovery C0-F07 проверяется в C3; incident/live health,
supervisor, ingress и восстановление production остаются C5/C6. Queue wait,
ASR service и E2E latency учитываются отдельно; C3 не повторяет ASR benchmark.

Классы findings: IMPLEMENTATION_DEFECT — исправляется owning layer;
VERIFIER_DEFECT — исправляется проверка при неизменных критериях;
ENVIRONMENT_FAILURE — сохраняется причина/повтор; STALE_CONTEXT — обновляется
источник; SPECIFICATION_CONFLICT и PRODUCT_OR_SECURITY_RISK требуют точного
разрешения границы. Старые FAIL/REJECT не превращаются в PASS новой ревизии.

SDK initialization ограничена15s плюс bounded cleanup. Async cancellation не считается остановкой физического SDK thread: startup остаётся owned и quarantined, late process очищается даже при зависшем initialize. Одна pending/failed physical close сохраняется; повторный no-op не стирает UNKNOWN/failure. Foreground close ограничен, незавершённая очистка запрещает новую generation и успешный статус.
