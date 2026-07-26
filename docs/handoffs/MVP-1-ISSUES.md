# Реестр проблем и исправлений Nobus Space MVP-1

**Статус:** CANONICAL HISTORY
**Период:** Gate 0 — product reliability, 17–25 июля 2026 года
**Назначение:** единый журнал root cause, исправлений, регрессий и остаточных рисков

Реестр не содержит токенов, пользовательских payload, transcript, абсолютных
секретных путей или необезличенных данных. Источники — Git history, gate-handoff,
регрессионные тесты и owner smoke.

## Сводка

| Область | Проблема и root cause | Решение | Регрессия / evidence | Статус |
|---|---|---|---|---|
| FastAPI lifecycle | `TestClient` создавался без context manager, lifespan не запускался и `app.state.orchestrator` отсутствовал | fixture переведена на context manager | полный baseline suite | CLOSED |
| Конфигурация | внешний `DEBUG=release` ломал Pydantic Settings до test collection | дочерняя среда очищается/нормализуется; тесты запускаются с `DEBUG=false` | full pytest во всех Gate | CLOSED |
| Codex app-server web transport | длительный web turn мог завершиться transient WebSocket/stream failure через несколько минут, хотя общий deadline 3 часа не исчерпан | persistent SDK остаётся primary; один pinned ephemeral CLI fallback только для web; evidence требует точной цитаты из TLS-соединения к заранее разрешённому public IP; максимум 1+1 model turns | exact production-profile, quote-provenance, SSRF, multicast, DNS-pinning, cancellation regressions; live owner-class smoke: 3 sources; full 1303 | CLOSED |
| Telegram parser | malformed dict, bool-as-int, whitespace IDs, неизвестные callback actions и неоднозначные text+voice могли пройти parser | strict type/shape checks, closed enum, ambiguous message reject, safe `REJECTED/IGNORED` | adversarial gateway tests | CLOSED |
| Core contracts | Task ID, executor, bundle и tenant/idempotency bindings допускали подмену или aliasing | UUID, tenant-scoped key, executor freeze, deep copies, immutable accepted records, store-boundary revalidation | contract/completion-policy tests | CLOSED |
| L1–L4 | partial bundle, evidence replacement и L4 record могли появиться не на том transition | один stage validator, cumulative levels, audit lock, atomic L4 transition, owner/executor separation, bounded server time | adversarial completion tests | CLOSED |
| Voice provider | sync Whisper мог блокировать event loop; cancellation/cleanup и temp-file failures теряли семантику | весь sync pipeline в worker thread, shield/drain, atomic temp lifecycle, strict result validation | voice service regression suite | CLOSED |
| Exception leakage | `raise ... from None` оставлял исходное исключение в `__context__`, где могли быть raw audio/temp/provider details | безопасное исключение создаётся и выбрасывается после выхода из active `except`; cause/context проверяются | exception-chain adversarial tests | CLOSED |
| Первая транскрибация | lazy load Whisper занимал десятки секунд | offline startup warmup из существующего cache до объявления ready | startup/warmup smoke | CLOSED |
| Callback latency | `answerCallbackQuery` мог ждать около 60 секунд и задерживал постановку задачи | optional ACK и message cleanup получили отдельный двухсекундный deadline; очередь не ждёт ACK | callback latency tests + owner smoke | CLOSED |
| Worker timeout | прежние 120 секунд обрывали нормальные задачи | task deadline 10 800 секунд, ceiling 14 400; polling lifecycle отделён | exact argv/timeout tests | CLOSED |
| Последовательный handler | Telegram polling ожидал Codex и блокировал следующие сообщения | два worker-слота, FIFO admission, handler возвращается после durable enqueue | 5 rapid updates / 2 active / 3 queued regression | CLOSED |
| Неверный online | бот мог объявить готовность при неработающем CLI/auth | startup sentinel использует production adapter/profile и fail-closed останавливает start | startup probe tests/live smoke | CLOSED |
| Process-memory queue | accepted raw instruction и confirmations терялись после restart | SQLite durable jobs, DPAPI payloads, generation leases, restart reconcile | Queue 1 crash/recovery suite | CLOSED |
| Voice recovery binding | callback envelope использовался вместо исходного voice envelope; recovered job мог стать failed/исчезнуть | сохранены отдельные `recovery_envelope` и `action_envelope`; instruction binding восстанавливается только из original envelope | `aa8a02e`, voice crash regressions | CLOSED |
| Poison FIFO | повторно падающая задача могла блокировать очередь | максимум три claims, затем dead letter; последующие FIFO items доступны | dead-letter/reclaim tests | CLOSED |
| Runtime DB split | старые runner-режимы создавали БД в корне и новый runtime не видел очередь | три канонические БД перенесены в `.runtime`; maintenance tools используют один manifest | `0856603`, health/backup/restore | CLOSED |
| Прогресс | пользователь не видел, работает ли длинная задача; отдельные сообщения засоряли чат | одна редактируемая карточка стадий + heartbeat, удаление после результата | progress-card crash regressions | CLOSED |
| Технический UX | UUID/event/revision, резервные команды и лишние acknowledgements попадали в продуктовый чат | product projection без technical IDs; text сразу выполняется; L4 UI только при эффекте | Telegram product tests + owner smoke | CLOSED |
| Callback UI | использованные кнопки оставались в чате | исходное callback-сообщение удаляется после commit действия; failure не маскируется | callback cleanup tests | CLOSED |
| Owner library | prompt с путём не давал CLI реального права безопасно читать библиотеку | отдельный server-owned `owner.library.read`, bounded no-link index/content adapter; write scope не расширен | ADR 0010 + owner file smoke | CLOSED, local owner scope |
| Отправка файлов | бот находил путь, но не возвращал файл на телефон | owner file service + `sendDocument`, type/size/secret/link checks | Bot API and product-route tests | CLOSED |
| Web research | обычный read-only профиль не имел сети, а полный browser authority был избыточен | explicit `/research` profile с live public web search; остальные network/write actions закрыты | profile/argv tests | CLOSED |
| Внешние эффекты | restart между L4 и эффектом мог потерять/повторить действие | durable effect state, exact proposal/digest, DPAPI capability, receipt/reconcile; unknown не повторяется | Queue 2 crash tests | CLOSED |
| Backup/restore | простое копирование SQLite не доказывало совместимость/целостность | exact schema/application digests, authenticated manifest, journaled restore и rollback | backup/restore drill | CLOSED for local runtime |
| Autostart | бот зависел от открытой desktop-сессии без supervisor | Task Scheduler, singleton mutex, bounded restart, local safe logs | task config + live start | CLOSED for current user |
| Profile publication | диагностический запуск без явного режима мог изменить Bot Menu | запись разрешена только с `configure_telegram_profile.py --apply`; missing/help не пишет | Queue 1/2 regression | CLOSED |
| Installer invocation | использование PowerShell `-?` для диагностики могло выполнить install path | эксплуатационное правило: читать help/source и применять только exact documented command; installer L4-bound | runbook checklist | MITIGATED; CLI help hardening desirable |
| `sendDocument` crash | Telegram Bot API не принимает idempotency key; crash после remote accept до local receipt может дать повтор | delivery receipt/reconcile с явным at-least-once остаточным окном | ADR 0011 + release evidence | ACCEPTED RESIDUAL |
| Windows path race | тот же Windows user может заменить каталог между проверкой и финальным path syscall | повторная identity/reparse проверка перед replace; owner-only workspace/quarantine | path adversarial tests | ACCEPTED LOCAL; production OS identity TARGET |
| Calendar OAuth scopes | клиент требовал только узкий scope и отклонял совместимый более широкий Calendar scope | accepted-scope family с fail-closed проверкой фактических grants | 104 target tests + read-only Google API health | CLOSED |
| Длительный web research | валидный JSONL с более чем восемью промежуточными `agent_message` ошибочно считался protocol failure | bounded allowance повышен до 64 сообщений / 128 KiB при неизменном общем stdout ceiling | parser regression + live five-source research | CLOSED |
| Естественный запрос файла | product route требовал `пришли/отправь`, обязательное расширение и не различал два похожих имени | server-side contextual resolver, четыре явных owner-глагола, exact/longest filename stem; voice использует тот же route | text/voice regressions + real metadata smoke | CLOSED |
| Natural research routing | формулировка «последние изменения правил» не совпадала с узким web-intent regex и уходила в offline answer profile | закрытый словарь расширен на последние изменения, официальные источники, новостные порталы и СМИ | реальные owner-фразы в regression suite | CLOSED |
| Длинный research answer | outbox разрешал только 3400 символов и sender отправлял один message; подробный валидный ответ не мог стать durable delivery | verified answer хранится до 128 KiB, product budget 12 000 символов, sender режет по строкам на сообщения до 3400 | long-answer outbox/sender tests + live 7964-char web result | CLOSED |
| Research runaway/transient | широкий запрос мог слишком долго добирать источники; отдельный transient turn failure выглядел как поломка функции | web-profile ограничен шестью поисковыми запросами и 12 страницами, обязан завершать best verified result; штатный worker сохраняет один retry | bounded live research: 4 completed searches, parser PASS | CLOSED |
| Research stream idle около 15 минут | общий Gate deadline уже составлял три часа, но внутренний provider stream idle и повторы завершали длительный web turn раньше с `worker_failed` | только SDK web-thread получает 9 000 000 мс; последние 1 800 секунд зарезервированы для CLI fallback, bounded оставшимся deadline; non-web не расширен | config-scope, deadline-reserve, argv parity, full suite и короткий live web smoke; буквальный 3h-run не выполняется | PUBLISHED / OWNER LONG-RUN SMOKE PENDING |
| Google Tasks all lists | `list_name=null` выбирал только первый список, а выдача обрезалась до 30 задач | пагинация всех tasklists и tasks, группировка по спискам, inclusive period filter, chunked delivery | 21 список; независимые и production counts совпали: 36 задач / 12 списков | CLOSED |
| Одноразовый Codex worker | `codex exec --json/ephemeral` терял диалоговый контекст, зависел от самописного JSONL parser и создавал новый процесс на turn | официальный persistent `openai-codex` SDK/app-server; stable non-ephemeral thread per chat/topic/profile | SDK contract tests, startup sentinel, clean-worktree suite | CLOSED IN RC |
| SDK control hang | interrupt/close и повреждённый повторяющийся thread-list cursor могли удерживать supervisor без границы | 15-second control deadline, forced task cancellation, cursor replay guard и 100-page ceiling | timeout/cursor regressions | CLOSED |
| Voice durable admission | `VoiceMessage` не входил в durable draft union и мог исчезнуть/упасть после ACK или restart | voice payload и исходный envelope сохраняются и восстанавливаются как отдельный тип | voice crash/restart regressions | CLOSED |
| Google retry ambiguity | общий requestBuilder повторял create/update/delete после timeout и мог дублировать уже принятый эффект | retries стали явным opt-in только для safe reads; mutations выполняются с `num_retries=0` | transport policy regressions | CLOSED |
| Worktree path arithmetic | runner вычислял owner/orchestrator roots фиксированным `parents[n]` и падал либо выбирал неверный каталог при другом checkout depth | named-ancestor layout discovery с безопасным local fallback | clean detached worktree reproduction | CLOSED |
| Persistent SDK answer mismatch | реальный read-only SDK turn мог вернуть plain text, минимальный answer JSON или закрытый planner JSON, а adapter требовал только полный пятиключевой envelope и завершал задачу `worker_protocol_error` | совместимый read-only normalization с жёсткой границей: write не получает fallback, partial known envelope и answer с patch/paths отклоняются | malformed/smuggling regressions, direct SDK web smoke, full suite 1116 | CLOSED |
| Google Tasks natural routing | общий LLM planner был лишней точкой отказа для частых list-запросов; короткие продолжения не доходили до parser либо перехватывали задачи проекта/Calendar | deterministic common-list parser + 10-minute tenant/chat/topic context + project/client/file/Nobus/Calendar domain-switch guards | natural-language matrix и end-to-end Google→follow-up→Calendar/project tests | CLOSED |
| Business Notes marker in private chat | owner отправлял group marker в личный чат; Telegram update не содержал отрицательный group chat_id/title, поэтому trust proof получить невозможно | private marker не enqueue; выдаётся точная инструкция отправить marker непосредственно в целевой группе | async product regression: one hint, zero draft/enqueue | CLOSED; OWNER GROUP MARKER REQUIRED |
| Research provenance и stale thread | persistent research-thread мог не дать новых web events, а строгая проверка отклоняла полезный ответ из-за одной неподтверждённой ссылки | fresh ephemeral thread на каждый research-turn; exact sanitizer; union evidence initial+repair; server-owned ссылка только из реально открытого public HTTPS source | live smoke: 2164 символа, 3 evidence events; focused L3 142; full 1158 | CLOSED |
| Google Drive contextual retrieval | последовательный ancestry walk терял глубокий target после множества посторонних цепочек; fuzzy brand совпадал по подстроке; batch callback можно было подменить | bounded batch BFS, exact response binding, token-bound brand/folder matching, deadline/cancellation и fail-closed partial batch | deep 39×7 foreign-chain regression; focused L2 257; full 1158 | CLOSED |

| Telegram task admission/session binding | transport source был перегружен хешем chat/topic, поэтому Core отклонял обычные Telegram-задачи до durable queue; последующее укрепление выявило forged ref, persistence и opaque callback gaps | разделены подписанный `source` и серверный `conversation_ref`; ref выводится только из trusted envelope, связан в policy, условно сохраняется и не меняет legacy digest; Google Sheets hint расширен | exact Gateway→prepare PASS; product phrases 14; full 1167; независимые L2/L3 ACCEPT | CLOSED |

| Google Tasks create/list selection | Natural owner create с формой «в списке пространства» мог уйти в общий SDK route; общий `httplib2` service делился между worker threads; fuzzy resolver мог выбрать соседний список | anchored text/direct-voice/Business-Notes route; per-thread transport reset; exact normalized tasklist + closed alias; zero mutation retry, marker reconciliation и same-key in-process lock | target 143; full regression; independent L2/L3; read-only 21-list reproduction | CLOSED |

## Устойчивые профилактические правила

1. Admission подтверждается только после durable write.
2. Callback acknowledgement и cleanup не входят в execution critical path.
3. Polling lease, queue lease и worker deadline — разные часы.
4. Recovery envelope не подменяется action/callback envelope.
5. Любой внешний эффект имеет exact proposal, action digest, L4 и receipt.
6. Неизвестный исход сетевой записи не повторяется автоматически.
7. Startup сообщает ready только после worker sentinel и Whisper warmup.
8. Все четыре runtime-БД обслуживаются одним health/backup/restore contract.
9. Product projection скрывает технический audit, но не удаляет его из durable store.
10. Новая capability считается CURRENT только после L1/L2/L3 и отдельного live L4,
    если меняет сеть, файлы, Telegram profile, credentials или host configuration.

## Открытые улучшения после MVP-1

- отдельная Windows service identity с минимальными ACL;
- внешний независимый monitoring и alert channel;
- утверждённые RPO/RTO и регулярный crash/reboot/restore drill;
- идемпотентный внешний file delivery adapter, если Telegram предоставит такую возможность;
- безопасный renderer длинных структурированных ответов;
- строгий `-Help`/dry-run contract для всех operational PowerShell scripts.

## Дополнение: SDK recovery и scoped Drive — 26 июля 2026

| Область | Проблема и root cause | Решение | Регрессия / evidence | Статус |
|---|---|---|---|---|
| Persistent SDK generation recovery | После временного сбоя повтор выполнялся на том же повреждённом app-server/client; отмена или параллельное закрытие могли оставить orphan либо оборвать соседнюю задачу | Generation leases/refcounts, client-bound thread cache, invalidation только повреждённого поколения, общий shielded close-task с bounded drain и повторной попыткой | SDK regressions 24; полный L1 1186; независимые L2/L3 ACCEPT; длительный web-smoke 496,11 с | CLOSED |
| Google Drive scoped natural lookup | Точное имя могло совпасть вне указанной папки; whole-path lookup мог быть затенён literal folder; `Home_edit` не совпадал с `HomeEdit`; fallback расходовал лишние страницы | Segment-first path resolution, hard folder boundary, exact adjacent-token brand alias, dynamic budget не более 4 list-запросов, ambiguity fail-closed | Drive regressions 49; exact product smoke PASS 9,36 с; независимые L2/L3 ACCEPT | CLOSED |
