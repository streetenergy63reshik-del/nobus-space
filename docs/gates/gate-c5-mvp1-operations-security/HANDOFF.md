# Gate C5 — эксплуатация, восстановление и безопасность

**ACCEPTED / PASS / PUBLICATION_PENDING.** 8 сентября 2026. C4 принят и не переоткрыт. Постоянная активация, C6, tag/release не выполняются. MVP1 NOT READY.

Проверенный C5 source: `9efad0f2eb152ff71ec684786c07ad38c906db1b`, tree `2e31c2f2e6dd72585c9e3a794f7ee8ec7475d78c`. [Приёмка](ACCEPTANCE.md), [связанные доказательства](EVIDENCE.json). Памятка SHA-256 `36fe554b9b7b0f327fecc7c22fecb5cc5241528267880ffdb4f5dad92433e2fc`.

## Вход

Опубликованная база main: 1b3cf67405c4523258dd8b400d17d09601f815ff, tree c302123e6f3ae93668e4fca7580b24d424056f94.
C4 source: 68f87f18da3de7c995f83b9cb08b391d0af5cdfb, tree 5ae168bf613b18fc2f14e24973b5167a2b4c7b74.
C4 package: 2812390052573fb8846cd942cca7a9e5aed82a31, tree 4f307fb7b6c05c8ad4e39089c287b3733d442737.
PR17 и PR18 сохранены в lineage; HANDOFF/ACCEPTANCE C4 проверены по Git blobs и не меняются.

Отдельная ветка codex/mvp1-closure-c5-ops-security и worktree mvp1-closure-c5. Canonical с 20 незавершёнными файлами, telegram-live и принятый C4 worktree не используются для изменений. Nobus Memory дала устаревший указатель; точный Git победил. Память не менялась.

## Принятый результат

| Обязательство | Изменение и проверка | Доказательство |
|---|---|---|
| A: управление | Singleton, Job до старта потомков, graceful stop, readiness/ограниченные повторы, explicit semantic ON при default OFF | [Операции](OPERATIONS.md), [receipts](RUNTIME-RECEIPTS.json) |
| B: ingress | Exact Host/Origin, no trusted proxy, HTTP бюджеты, timeout UNKNOWN, loopback slow/burst/spoof | [Ingress](INGRESS.md) |
| C: восстановление | Полный inventory, DPAPI/WAL snapshot, code/schema/target binding, restore journal/rollback, admission hold до сверки | [Drill](STORAGE-DRILL.md), [receipts](STORAGE-RECEIPTS.json) |
| D: очистка | Точное владение/пути, рабочий dry-run, tombstones сохраняются | Storage drill и retained C2/C4 retention |
| E: безопасность | Изоляция/UNKNOWN не ослаблены, точный native/dependency inventory | [Зависимости](DEPENDENCIES.md), DEPENDENCY-EVIDENCE.json |
| F: инструкция | Runbook и тот же DOCX; текст и визуальная проверка всех 6 страниц | MANUAL.json в acceptance package |

Telegram/Mini App сохраняют один Core, compiler, durable state и sealed result/TXT. Голос выполняется только после owner-bound подтверждения. Recovery не продлевает Telegram signature; утраченный ACK сначала сверяется чтением. Provider UNKNOWN и delivery UNKNOWN различаются.

## Нормы и ограничения

Владелец явно принял в этой задаче целевые RPO ≤24 ч и RTO ≤30 мин; backup ежедневно и перед изменениями; 7 ежедневных и 4 еженедельных копии. Это политика и критерии C6: расписание не включается, рабочие копии не удаляются. Копии на том же ПК не защищают от потери диска; полный RTO с SDK/ASR ещё не измерен.

В изолированной среде выполнены backup, восстановление данных и recovery после прерывания. Точные измерения и их source/application binding перечислены в приёмке C5; ранние WIP-замеры сохранены только в исходных receipts. В проверенном наборе потерянных принятых задач и повторно доставленных подтверждённых частей — 0. Полный запуск с SDK/ASR не входит в измеренное время восстановления данных. После restore admission остаётся закрытым до сверки возможных внешних действий после снимка.

Предел DPAPI backup 48 МиБ на БД, предупреждение с 36 МиБ. При свободном месте менее 256 МиБ оператор останавливает новый приём. Автоматического масштабирования и независимого оповещения вне ПК нет.
Inherited native/license/pip/SQLite риски описаны по фактической достижимости в DEPENDENCIES. Git публикует исходники и безопасные evidence, а не wheels/models/FFmpeg/cuDNN; новое binary distribution или установка требует отдельной проверки.

## Фактический runtime

Live window **NOT RUN**: новых model/ASR inference, исходящих bot messages и изменений внешней конфигурации 0.
Preflight: оба Scheduler tasks Disabled, port 8765 свободен, pollers 0; local HTTP отсутствует, public /readyz 403. Это новое чтение, не повторная приёмка historical C4 stopped/502.
Конечный прямой readback дал HTTPS502 при тех же Disabled/0процессов/свободном порте; исходный403 сохранён как preflight. [Runtime receipt](RUNTIME-READBACK.json).
Новые защиты проверены на изолированном кандидате; старый live checkout, TLS/route/config не менялись. Source/merge не означает deploy.

## Следующая отдельная задача C6

Принять опубликованный C5 package; проверить фактические runtime/config/owner binding. Подготовить совместимые данные и reconciliation restored hold; не снимать fencing по одному факту restore. Принять activation profile с explicit semantic ON, pinned CLI/ASR, public HTTPS-ready и одним poller. Применить расписание/retention только по отдельному разрешению, измерить полный RTO, провести необходимые реальные owner journeys и принять постоянную активацию.
До C6 default semantic=False, MVP1 NOT READY; tag/release не создаются.
