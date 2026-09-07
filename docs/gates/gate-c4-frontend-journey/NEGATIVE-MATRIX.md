# Gate C4 — отрицательные сценарии

Каждая строка проверяет один Core truth. Таблица фиксирует ожидаемое поведение; итоговые receipts и пробелы — EVIDENCE.json. Существующие C3 проверки запускаются как регрессии кандидата C4, без повторной приёмки C3.

| Сценарий | Core | Telegram copy/action | Mini App copy/action | Recovery / проверка |
|---|---|---|---|---|
| 400 malformed / extra fields | До admission отказ | Некорректный запрос | Запрос не принят | test_miniapp, test_c3_multipart_input |
| 401 expired | Недействительная session | Task сохранена | Recovery один раз, затем переоткрыть | test_c4_miniapp_recovery |
| 403 wrong origin | Boundary отвергает | Не применяется | Нет нового intent | test_miniapp |
| Foreign/unknown task | Opaque404 | Не раскрывать объект | Обновить список | test_miniapp/result/artifact |
| 408 partial/slow body | Admission отсутствует | — | Исправить/прочитать исход | test_c3_multipart_input |
| 409 rebound key | Старое намерение неизменно | Не создавать дубль | Читать прежний key | test_c4_miniapp_recovery |
| 413 large text/material | Boundary limit | Лимит ввода | Сократить запрос | test_c3_multipart_input |
| Capacity state | Existing queue bound | Очередь заполнена | Без ложного принятия | test_c3_durable_concurrency; статус не переименован в429 |
| 500/503 worker/Core | UNKNOWN или unavailable по authoritative state | Сверить /status | Сохранить экран; GET | test_c3_queue_recovery + JS |
| Malformed JSON response | Не даёт UI success | Safe error | Не рисовать результат | JS revision/malformed checks |
| Offline/reconnect | Не меняет task | Durable intake | Последний экран + read | frontend.test.cjs |
| Late detail/result | Новая revision неизменна | Core receipt | Generation/revision guard | frontend.test.cjs |
| Late list | Последний запрос списка | — | List generation guard | frontend.test.cjs |
| Double submit | Один key/claim | Идемпотентный update | Submit disabled | frontend.test.cjs + test_miniapp |
| Reload after unknown POST | Journal pending/accepted | Прежняя task | Opaque marker → GET | frontend.test.cjs |
| InitData expired/replay | Reject | Fresh Telegram launch | Переоткрыть | test_miniapp |
| Old bearer after re-auth | Revoke old generation | — | 401 bounded recovery | test_c4_miniapp_recovery |
| Concurrent sessions | Core CAS/one active generation | — | Не расширять scope | test_c4_miniapp_recovery |
| Cookie replay/tamper | HMAC/deadline/digest fail | — | Fresh Telegram launch | test_c4_miniapp_recovery |
| Clarification stale/foreign | C1 owner/conversation/token TTL | Новый корректный ответ | Clarification invalid | test_c4_product_journey |
| Approval stale/replay | Immutable policy unchanged | Только Core challenge | Неприменимо CURRENT semantic scope | Registry + retained tests |
| Failure after progress | FAILED/attention durable | Честное завершение | «Не выполнено» | C3 worker/recovery regressions |
| Changed result revision | Exact binding reject | Не менять sealed answer | Не показывать stale | test_miniapp_result + JS |
| Artifact foreign/missing | Exact tenant/task/result/ref | Safe delivery failure | Файл не получен | test_miniapp_artifact |
| Artifact corrupt bytes | Digest/size mismatch | Fail closed | Нет download/object URL | test_miniapp_artifact + JS |
| Unsafe name/MIME/path/symlink | Existing OutboxArtifact bounds | Safe alias | Safe alias authenticated route | retained artifact tests; symlink platform limits reported |
| Long/multipart result | Part manifests/receipts | Полный ответ по порядку | Wrapped text/copy | test_c3_delivery_parts |
| HTML/script/control/Bidi | Untrusted content | Existing safe render | textContent + control filter | JS + transport regressions |
| Voice before confirmation | Нет task/compiler | Preview обязателен | Нет выдуманной task | test_durable_voice / C4 model smoke |
| Direct/transform parity | C1 INERT preserved | Один Core decision | Та же task/result | C4 actual local inference PASS; LOCAL-JOURNEYS.json |
| Unavailable capability | No TaskContract/effect | Shared catalog | Явная недоступность | test_c4_product_journey / local inference |
| Internal exception | Safe code, no private payload | Safe failure | Общий безопасный error | C3 guards + C4 negative |
| False READY / verified | Только exact result state | Без internal metadata | «Результат», не verified | shared mapper / JS |
| Actual browser320/390/768 | Exact candidate UI | — | Light/dark/keyboard/viewport | BLOCKED: штатный Browser runtime |
| Actual owner Telegram/Mini App | Exact temporary candidate | Text/voice/file | Fresh signed auth/result/file | AUTHORIZED; actual owner journeys PENDING; LIVE-SMOKE.json |
