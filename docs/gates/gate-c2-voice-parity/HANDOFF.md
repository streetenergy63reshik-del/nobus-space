# Gate C2 — handoff, C3 HOLD

**Verdict: BLOCKED / NOT PUBLISHED / NOT DEPLOYED.**
Это один связный пакет текущего C2. Он не разрешает начало C3.

## Привязка

База: `43e753c571e1ad8db5af5f453b5db0c0b417cac8`, tree
`a7c6328a42412a0bd269004aefa9c9d402c75564`. На входе remote main совпал с SHA.
13 документов после product C1 не меняли code/tests/config/ADR/contracts.

Product C1: `2732a11122179c4197a74594dd0c8ba3ed9ec52d`, tree
`6a8f968f2b447a7a20d88321d8610adcb76c9cb9`; reviewed C1
`8e5e5fd3bf5680b5dbcf78a5f7de40da63ba93da`, тот же tree.
[Опубликованный C1 handoff](../gate-c1-semantic-task-compiler/HANDOFF.md)
Git-blob SHA-256 `3cdc5585cc5d7199aaf13c27d3dfb2bc440bd8ed2447317665c99a52ad8c39a6`;
[acceptance](../gate-c1-semantic-task-compiler/ACCEPTANCE.md)
`e001097212d975c83be04ca1fdbd0946b537c998936bfb73564d4e15d514ac02`.
Exact ADR/schema/registry/corpus bindings сохранены в EVIDENCE.json.

C2 branch: `codex/mvp1-closure-c2-voice-parity`. Worktree относительно
канонического repo: `.runtime/worktrees/mvp1-closure-c2-voice-parity`.
Собственные result SHA/tree и changed-files фиксируются после commit в
`.runtime/c2/final-evidence.json`; этот внешний receipt связывает неподвижный
Git tree и последующие независимые проверки, не требует self-referential SHA
внутри этого же tree. До такого receipt проверки не считать завершёнными.

## Voice state machine

`received → downloading → downloaded → recognizing → transcribed → waiting →
confirmed → prepared draft → finished`. Admission и original trusted envelope
в SQLite предшествуют долгой стадии и Telegram ACK. Детерминированный task id
основан на tenant/actor/user/chat/topic/original message; transcript в identity
не участвует. Отдельный digest связывает update/file metadata, accepted C1
semantic schema, content SHA-256; DPAPI защищает payload.

Restart до download безопасно повторяет только download; сохранённые bytes
не скачиваются снова. Restart из `recognizing` переходит в `interrupted`:
результат мог быть утрачен при crash, поэтому ASR сам не повторяется.
Владелец отвечает на исходный voice «повторить», либо пишет исправленный текст.
Это новая явная generation, не скрытый retry. Из transcribed/waiting сохраняется
preview; из confirmed с PreparedTask повторяется только idempotent enqueue.
После enqueue и до finish повтор не создаёт второй Core task.

В C1 predecessor воспроизведён настоящий hard-crash дефект: после task
admission, до enqueue, replay оставлял task=1/job=0 и подтверждал polling offset.
Гипотеза немедленной потери pre-ASR из-за update claim не подтвердилась:
production polling offset продвигается после успешного handler.
Historical «Voice durable admission CLOSED» покрывал уже подготовленный draft,
а не весь audio intake. Историческое evidence сохранено; CURRENT уточнён.

## Локальная проверка и пользовательский путь

В изолированном harness C1 включён только для проверки. Отправить synthetic
voice; дождаться preview; в течение часа ответить на исходное голосовое
сообщение «да», «нет» или исправленным текстом. До подтверждения task/effect
не создаются. Подтверждённый текст передаётся `_start_owner_instruction` и
accepted C1 CoreDecision. Для проверки используются
`tests/test_durable_voice.py` и `tests/gate_c2/candidate_smoke.py`.
Парные direct/transform/quoted/nested/negated/cancel/conditional fixtures
сравнивают goal, operation roles, capability, decision, task/effect permission.
Это не реальный owner/production compiler smoke.

Публичные стадии: получение, распознавание на русском, проверка текста,
очередь, ошибка/явный повтор. Лимиты: 10 MiB encoded audio, 300 секунд,
Ogg/Opus или WAV, 2000 символов accepted text. Download timeout 60 секунд;
async ASR timeout 180 секунд. Media signature/decode duration проверяются,
metadata не заменяет проверку bytes. Raw temp files новый production path
не создаёт. Максимальная decoded память: 300 секунд mono16k float32,
один активный inference; native hard-timeout limitation остаётся B03.

## ASR и rollback

[BENCHMARK-RESULTS.json](BENCHMARK-RESULTS.json) связывает frozen16-case pilot,
3 warm passes и concurrency2. CURRENT FW WER19,15%, CER7,16%, p95 4,16s,
peak351MiB. GigaAM ONNX telemetry-off WER11,49%, CER5,81%, p95 5,74s, peak999MiB.
Scorer — lexical; цифры critical mismatches 12/10 не равны semantic error counts.
ASR DECISION BLOCKED; улучшение WER не закрывает frozen product decision rule.
Cloud candidates Google/Deepgram/Azure исследованы только по official sources.

Production зависимости/config/model не заменены. GigaAM используется только
в отдельно разрешённом isolated comparator. Provider rollback не требуется,
поскольку REPLACE не выполнялся. Rollback C2 candidate: не активировать его;
использовать неизменённую принятую базу. После реальной будущей активации новый
SQLite schema нельзя открывать старым runtime без отдельного backup/restore
плана; такой production rollback не выполнялся и не заявлен.

## Privacy и доказательства

Voice row хранит encrypted recovery audio до transcript, затем audio=null;
по finish payload={}. Content TTL1h, replay tombstone TTL24h, максимум2000
voice rows и40 активных задач. Sweep происходит при intake/worker activity;
при выключенном runtime фоновый TTL не выполняется. Это не forensic erase
прошлых encrypted pages/WAL/backups (B04). Записи и ASR hypotheses pilot
остались только в ignored `.runtime`, в Git — synthetic text/index/hashes/
агрегаты. Private audio не использовалось. Terminal receipts хранят safe
выводы; raw model results отсутствуют в public evidence.

Авторизация: только GigaAM ONNX pinned revision, 11 pinned wheels и Silero6.2
в named C2 path, ≤1GB network, ≤3GiB disk, ≤4GiB RAM,4CPU,1800s, offline
synthetic recognition. Владелец разрешил этот scope в текущем чате. Использовано
932563674B download, около1,13GB disk,165,765s smoke+два pilot runs, cost$0.
Остаток execution budget учитывается при независимом локальном subset.
Не было новых cloud ASR/compiler trials, покупок или private upload.

## Остаток и границы

Все C2-B01…B04 описаны в [ACCEPTANCE](ACCEPTANCE.md); C0-F03/F04 остаются
открытыми до принятого C2. C3 reliability, C4 UX, C5 ingress/ops/cleanup
release evidence и C6 acceptance не выполнялись. C1 default-off и UNKNOWN
без trusted conditional facts сохранены. Nobus Memory project note устарел;
прочитан read-only, exact Git имел приоритет. Записей в Memory не было.

Canonical dirty WIP и live worktree не редактировались; сверка с entry manifest
входит в final-evidence. Sealed Gate0/C0/C1 и owner PUBLICATION HOLD docs15/16
сохранены. Авторизация C2 не разрешает внешнюю публикацию.

**C2 PERFORMED NO PUSH / PR / MERGE / TAG / DEPLOY / UNAUTHORIZED CLOUD AUDIO**

Следующий шаг остаётся в этом чате C2: закрыть его доказанные блокеры, получить
собственный exact ACCEPT и отдельное разрешение на публикацию. Будущий чат C3
может стартовать только от принятого опубликованного exact C2 SHA/tree после
readback и актуального handoff. Этот локальный кандидат такой базой не является.
