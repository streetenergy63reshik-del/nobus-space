# Gate C2 — handoff, C3 HOLD

## Текущий checkpoint и продолжение, 4 сентября 2026

**Текущий статус: DRAFT / BLOCKED / NOT PUBLISHED.** Последний продуктовый
checkpoint — `96487d176cb3f09b543cadbc0e4b91c73308b8b4`, tree
`7da1e466606dec9ef7ab7bf375a30ed002b9f728`; его receipt
`.runtime/c2/closure/checkpoint-evidence.json` имеет SHA256
`aeb7833c205214c5b9ac0721fdeddc8f6990faa20304c587ddc3f03950cb3afd`.
Продолжение остаётся в том же worktree и задаче. Сверка с аудитом подтвердила
этот HEAD/tree, десять хешей receipts и отсутствие новых model turns.
Продолжение добавило документационную синхронизацию, отдельный бюджет small
в qualification runner и один разрешённый dev-эксперимент. Продуктовый код
checkpoint не менялся; это не приёмка продукта. Актуальные агрегаты и привязки
сохранены в Git: [EVIDENCE.json](EVIDENCE.json).

Предыдущий `b090bc48b8934fcc16e10a81cff12b56b30479c1`, tree
`10055957c7ba1f5c21577d7e58ea5e459e0c46bf`, остаётся историческим BLOCKED.
Старый `.runtime/c2/final-evidence.json` с SHA256
`baf960372d5dd9c189a2de9b0de317c6ad0c45d3adc31bac3012135528bdba6d`
сохранён; локальные исходные evidence продолжения находятся в
`.runtime/c2/closure/`. Они не переносят прежние L1–L3 на новый checkpoint.

Native inference переведён в управляемый Windows Job: direct base interpreter
`-I -S`, передача config после assignment, ограниченные anonymous pipes,
timeout/cancel/close/parentdeath/idle cleanup. Исходный venv redirector мог
оставить дочерний native вне Job; ранний Windows timer мог потерять idle cleanup.
Оба дефекта воспроизведены и исправлены. Независимые focused14PASS, actual
native handles и Job limits проверены. Возможен служебный conhost; native
interpreter один. Это WIP evidence, не формальный L3.

Retention: до decrypt применяется TTL1h по created_at, включая leased/flag-off;
длительный этап отменяется на deadline, поздние preview/draft запрещены.
Новый backup требует отсутствия непустого voice recovery, restore очищает
только authenticated staging. Независимые27PASS и root native/state subset48PASS.
[RETENTION.md](RETENTION.md) различает логическую очистку, DPAPI и пределы
физического стирания; forensic wipe SSD/чужих backup не заявляется.

ASR: frozen32 synthetic cases = старые16dev + новые16holdout, независимые gold,
числовая нормализация с positive/negative probes, реальные паузы и шум20dB.
В первом matched dev CURRENT WER14,16%/critical5, GigaAM7,52%/critical4;
независимая raw semantics13/16 и15/16. Три FW config дали critical4/4/5.
Ни один вариант не квалифицирован; holdout ещё не распознавался.
[DEVELOPMENT-RESULTS.json](DEVELOPMENT-RESULTS.json) сохраняет агрегаты и hashes.
По точному разрешению владельца скачан Systran small
revision536b0662742c02347bc0e980a01041f333bce120, пять assets с проверенными
digests. Общий download486217682B включает первую остановку на новом
официальном HF CDN; прежний расход1061B сохранён.
Один объявленный dev с прежним decoder дал WER6,64%, CER1,27%, critical2
и raw RTFp95 0,792>0,5. RAM3040018432B, cold7,651s, active processes0.
Эксперимент завершён с hard FAIL, новые конфигурации и holdout не запускались.
Small использовал78,520625s из1200s; остаток1121,479375s не разрешает
самостоятельный перебор. GigaAM по-прежнему194,916977s из1800s.

Владелец затем отдельно разрешил одну пробу beam8→1. До запуска подтверждено
единственное изменение beam_size; source/model/audio/gold/scorer закреплены
в beam1-freeze. Все16 samples обработаны за50,630924s. WER8,85%, CER2,16%,
critical2 (cancel/domain), raw RTFp95 0,581>0,5, latency p95 7,022s.
Cold4,819s, RAM2922139648B, Job active0. Скорость улучшилась, но hard FAIL
сохранён; новых config/holdout прогонов нет. Small суммарно129,151549s
из1200s, осталось1070,848451s. Это не разрешение на следующий перебор.

Следующая единственная гипотеза — независимый Google Chirp3 ru-RU в eu
на том же dev16 через synchronous Recognize. Предложены16 запросов без
автоповторов, до10 минут и0,10USD, только синтетические156,26s audio,
inline без GCS/resource creation. Это **не разрешённый trial**: нужен
существующий Google Cloud project, проверка штатного auth/billing/region,
logging и применимых V2 retention terms, затем конкретный frozen runner
и точное согласие владельца на передачу синтетического аудио и расходы.
Проект/credentials не выбирались, облачных вызовов не было.

B02: transport-only harness использует actual ASR, production C1 compiler/runtime
и downstream pipeline. Реальный transform_voice дошёл до durable preview:
task0/compiler0 до подтверждения. Account/endpoint и ephemeral thread startup
проверены; штатный ChatGPT, gpt-5.6-sol/high/fast. Владелец разрешил24modelturn
и20min, synthetic text only/no audio/tools/effects, без API billing; region/retention
UNKNOWN раскрыты. Бюджет пока0turn и не начат; полные ready result/parity/restart
запуски следуют после ASR выбора, чтобы не расходовать ограниченное разрешение
на неподходящий final engine. План/guard/receipts — `closure/product-plan/`.

Далее: разрешённая model-only проверка, dev-выбор, untouched holdout и3passes,
ASR decision/integration при необходимости, actual B02, один frozen кандидат
с новыми L1/L2/L3 и отдельным final receipt. Непройденный критерий остаётся
блокером C2. C1 acceptance не повторяется; canonical20dirtyhashes/live/HOLD
сверены и сохранены. Публикация, live и C3 не выполнялись и не разрешены.

## История предыдущего замороженного кандидата

Остальная часть ниже описывает b090bc48 и сохранена как его исторический
handoff; утверждения о прежних ограничениях не описывают новые WIP fixes.

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

Reply update watermark хранится в encrypted payload и обновляется в той же
транзакции, что confirmation/retry. Старый либо преждевременный ответ не
подтверждает последующий transcript. Worker checkpoint сохраняет актуальный
watermark, даже если native call начался до прихода ответа. При отключённом
C1 восстановленный voice получает явную остановку; legacy routing запрещён.
Нормальные concurrent voices ждут async lock, отдельный native guard
защищает от ещё работающего отменённого inference.

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
