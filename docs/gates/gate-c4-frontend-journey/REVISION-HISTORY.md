# C4 — история кандидатов

`ad02795c5457deb3909517efd1992cacb5ac9a73`, tree `229d7a4be82da7391ee339825fffb3538d34481d`: **REJECT**. Frozen L1: 2116 PASS, 9 FAIL, 2 Windows symlink SKIP, 1 historical deselect, 25 subtests PASS. Девять отказов — устаревшие проверки copy/typed refusal/exact schema whitelist; исходный receipt `.runtime/c4/ad02795-l1.xml` сохранён. Их обновление сохраняет security/no-task assertions: 400 PASS, `.runtime/c4/ad02795-contract-rework-final.xml`.

Независимые L2/L3 подтвердили продуктовые дефекты: вечная блокировка после never-arrived POST или точного boundary408; некорректная форма после истёкшего восстановленного уточнения; сохранение старой ошибки после успешного неизменного чтения. Исходные REVIEW.json/md и failing probes сохранены в `.runtime/c4/reviews/l2/` и `l3/`. L2: 44 targeted PASS, 4 independent HTTP PASS, JS4 PASS/2 FAIL. L3: 122 targeted PASS, 11 штатных Node PASS; недоказанная искусственная overlap-проба не включена в findings.

Цельный rework: Core-only cancellation tombstone до admission, запрет позднего create того же key; точный request_timeout408 завершает непринятый intent, неопределённый gateway408 остаётся UNKNOWN; UI сбрасывает режим уточнения и очищает подтверждённо устаревшую ошибку. Новые targeted receipts: cancellation51 PASS, frontend17 PASS. Приёмка относится только к следующей замороженной revision и её собственным проверкам.

Первый реальный direct_text на ad02795 завершился через actual loopback HTTP/Core/provider и synthetic Telegram transport: 2 model turns, 59.157 s с учётом первого SDK startup failure до inference. Файл453bytes, SHA256449ef1a9cb8dd820e38460a6ef9a9066bc916ca01591c02fc6c8e082c4554f74; обе части доставки подтверждены. Этот результат исторический и не переносится на новую revision. Общий C4 ledger не сбрасывался.

Владелец повторно явно разрешил все необходимые временные действия и тесты для завершения/публикации C4. Отдельные повторные вопросы о разрешении не нужны; exact temporary smoke bindings, лимиты, readback и возврат настроек остаются обязательными. Постоянный deploy/tag/release/C5/C6 не разрешены.

## Проверенный a869a69 и временные попытки

Новый код a869a691293e45a1a3e65303be627d684acfa16e / tree9a7cab97fb9947ebdfedeb5baffa57f9627a4c98 получил собственный L1 2132PASS+25subtests,2WindowsSKIP,1historicaldeselect,Node17PASS. Независимые L2/L3 приняли локальную кодовую область и7actual local runs/6replay. Их identities, исходные hashes и ограничения — REVIEW-VERDICTS.json.

Первая actual temporary attempt завершилась до пользовательского input после трёх polling failures. Lease300s пересекала верхнюю границу из-за разницы часов; исправление только helper240s подтверждено независимой realSQLite пробой. Attempt2 имеет новое окно/marker, сохранённые старые FAIL/STOP/DB и общий прежний budget. Реальный HTTPS route exactbindingPASS; ownerjourney/visual acceptance ещё отсутствуют. Состояние и возврат исходного контура — LIVE-SMOKE.json.
