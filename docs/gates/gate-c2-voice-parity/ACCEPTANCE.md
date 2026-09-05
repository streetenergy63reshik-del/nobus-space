# Gate C2 — уточнённая приёмка, WIP / NOT ACCEPTED

**5 сентября 2026:** владелец принял подтверждаемый голосовой ввод и конечную программу локальной квалификации. Entry checkpoint `3ef14b32c1c602739db3b4d32016f5182b10567b`, tree `e2432af5844955d4724eaedcfa97a6b77262a9fa`; product-source на входе был `96487d176cb3f09b543cadbc0e4b91c73308b8b4`, теперь `28222923d2c2560504d1237c8e8da6df442c6150`. ASR qualification завершена; B02 выявил исправленные дефекты, но ready answer пока не получен.

Действующий контракт — [PROTOCOL.json](../../../tests/gate_c2/qualification/PROTOCOL.json) и [PLAN](../../../tests/gate_c2/qualification/PLAN.md). Буквальные critical-token mismatches остаются диагностикой; дополнительный общий raw RTFp95≤0.5 перестаёт блокировать выполненный per-file интервал `max(5s,0.5×duration)`. Это явная смена двух task-level условий после открытых dev экспериментов, а не исправление старых FAIL. Нормализация, gold, ADR0023, WER/CER, подтверждение и полномочия Core сохранены.

До holdout зафиксировано `semantic_correction_required`: raw transcript требует смысловой правки для сохранения произнесённых цели, операции, объекта, роли, отрицания/отмены, условия, значения/сущности или ограничения. Косметика не считается такой правкой; утраченные факты не угадываются. Семь независимых измерений, абсолютные counts и ошибки публикуются раздельно от lexical diagnostics. Выбранный вариант не увеличивает correction burden относительно matched CURRENT на dev и отдельно holdout. WER≤15%/CER≤8% на all32 и отдельно holdout16 обязательны.

Перед compiler/task/effect каждый voice даёт сохранённый preview и требует подтверждения либо явной коррекции. После этого применяются общий C1 compiler/Core и production result pipeline. В проверенной матрице нужны100% accepted semantic parity,0 неверных принятых решений и хотя бы одна главная transform-пара text/voice до пригодного ответа без смысловой коррекции. Cold≤120s,4CPU/4GiB,concurrency2/один native slot,три warm passes,retention/recovery и правило substantial gain сохраняются. B02 проводится независимо от B01 в ранее разрешённых24turn/20min.

| Причина | Слой исправления | Проверка |
|---|---|---|
| IMPLEMENTATION_DEFECT: прежние native process escape/idle timer и TTL/late-write/backup | Уже исправлены в продуктовых bytes96487d; новая переработка без дефекта не нужна | Сохранённые focused14/27 и subset48; относящаяся финальная регрессия |
| VERIFIER_DEFECT / несоответствие критерия продукту: inflection как authority error, дополнительный RTF для коротких фраз | Явное решение владельца, протокол3; прежние FAIL неизменны | Независимые semantic facts, per-file latency и новый untouched holdout |
| MODEL_LIMITATION: утраченные цель, объект или имя | Измерение raw errors и correction burden; выбор одного dev-кандидата | Семь измерений, WER/CER, non-regression и B02 correction-path |
| ENVIRONMENT: прежний SDK sandbox OS5 и license/native provenance gaps | Штатный авторизованный provider preflight; проверка существующих installed bytes/notices | Реальные ChatGPT/endpoint, cleanup, ограничения бюджета; источники лицензий |
| STALE_CONTEXT: narrative96487d вместо latest3ef14b32, B02 ошибочно ожидал B01/Chirp3 | Текущие Git-указатели и независимая программа B02 | HEAD/tree, прежние receipts/ledger, актуальные индексы |

Текущее состояние: B01 quality/resource/integration PASS для локального кандидата; конечный REPLACE зависит от B02 и итоговой приёмки. B02 BLOCKED: первое окно истекло после8turn, ready0; B03/B04 LOCAL FIX / regression verified. C2 не PASS и не опубликован. Live/C1/C3 не затрагиваются. Публикационный manifest готовится после собственного итогового PASS; точное разрешение push/PR/merge ещё не дано.


Продуктовый checkpoint продолжения `28222923d2c2560504d1237c8e8da6df442c6150` / tree `b24ae81b91786aca942c89a8d54f50279de3cef8`.
Полная сводка, действующий расход и ограничения — [HANDOFF](HANDOFF.md),
[EVIDENCE](EVIDENCE.json), [квалификация](CONFIRMED-QUALIFICATION.json),
[дополнительный B02](PRODUCT-TRIAL-PLAN.md) и [лицензии](ASR-PROVENANCE.md).
Исторический source96487d и входной HEAD3ef14b ниже не являются текущим продуктовым кодом.

---

## История checkpoint4 сентября — старые критерии и FAIL сохранены

### Локальный кандидат4 сентября, BLOCKED

Дата: 4 сентября 2026. C2 не принят и не опубликован. C1 остаётся
ACCEPTED / PUBLISHED / NOT DEPLOYED; MVP1 не READY, C3–C6 и MVP2 HOLD.

Последний продуктовый checkpoint: `96487d176cb3f09b543cadbc0e4b91c73308b8b4`,
tree `7da1e466606dec9ef7ab7bf375a30ed002b9f728`. Точная привязка текущих
локальных проверок и отдельная история прежних кандидатов — [EVIDENCE.json](EVIDENCE.json).

## Результат и граница

В отдельном worktree реализован voice intake до download/ASR в существующей
зашифрованной SQLite queue. Подтверждённый transcript использует принятый C1
semantic path. Исправлена передача voice → draft: durable PreparedTask
записывается до Core admission, обе стадии одной задачи используют одно место
в лимите очереди. ASR не выбирает capability, route или authority.

Это кандидат для локальной проверки. Обязательные критерии ASR и полной
продуктовой квалификации ещё не доказаны, поэтому PASS не заявляется.

## Открытые блокеры

| ID | Доказательство и недостающее условие |
|---|---|
| C2-B01 | Отдельные gold/scorer, 16 dev + 16 holdout. CURRENT critical5, GigaAM4; raw semantics13/16 и15/16. Три FW config: critical4/4/5. Small beam8: WER6,64%, critical2, raw RTFp95 0,792. Отдельно разрешённый beam1: WER8,85%, CER2,16%, critical2, raw RTFp95 0,581>0,5. Все семь вариантов двух семейств hard FAIL. Holdout не распознавался; KEEP/REPLACE нет. |
| C2-B02 | Actual production voice path прошёл до persisted preview: task0/compiler0 до подтверждения. Реальный tool-less compiler и downstream harness подготовлены; ChatGPT/account/endpoint проверены, владелец разрешил24turn/20min, использовано0turn. Полный verified ready result и parity/restart smoke ещё впереди, после выбора ASR. |
| C2-B03 | LOCAL FIX, итоговая кандидатная проверка впереди. Native worker помещён в Windows Job до импорта модели; timeout/cancel/parent death/idle завершают процесс. Независимо воспроизведены и исправлены venv redirector escape и ранний idle timer. Focused14PASS; actual FW model runs завершились с Job active0. |
| C2-B04 | LOCAL FIX, итоговая кандидатная проверка впереди. TTL1h по immutable created_at применяется до decrypt для всех состояний; late-write/deadline guards, secure_delete/WAL cleanup, quiescent backup и expiry authenticated restore staging. Независимые27PASS, общий root native/state subset48PASS. Граница и ограничения — RETENTION.md. |

Пороги не ослаблялись после получения результатов. CURRENT Faster-Whisper
сохранён как исходный факт, а не как решение KEEP. GigaAM не интегрирован в
продукт. Внешний compiler уже отдельно разрешён, inference ещё не начинался.
Small скачан по отдельному разрешению: пять pinned assets проверены,
486217682 bytes с учётом redirect и первой неуспешной попытки.
Один dev занял78,520625s из1200s; RAM3040018432B, Job active0 при завершении.
Raw RTF не прошёл, хотя каждый файл уложился в allowance минимум5s; эти
критерии не взаимозаменяемы. После hard FAIL эксперимент остановлен.
Владелец отдельно разрешил одну пробу beam8→1; изменён только beam_size.
Она обработала16/16 за50,630924s, cold4,819s, RAM2922139648B, Job active0.
Latency p95 снизилась14,002→7,022s, но critical2 и raw RTFp95 0,581 снова
не прошли; появились ошибки в domain sample, поэтому это не допустимый REPLACE.
Small суммарно129,151549s из1200s; дальнейшие прогоны остановлены.
Следующая независимая гипотеза — Chirp3 на том же dev, только предложение.
Нужны решение о таком облачном сравнении и существующий Google Cloud project
для подготовки точного плана; передача аудио и расходы пока не разрешены.
Пределы и недостающие условия — EVIDENCE.json.
Результаты dev — [DEVELOPMENT-RESULTS.json](DEVELOPMENT-RESULTS.json).
Исходные frozen inputs и receipts продолжения находятся в
`.runtime/c2/closure/`; безопасные агрегаты, привязки и команды доступны в Git
через EVIDENCE.json и DEVELOPMENT-RESULTS.json. Старый
`.runtime/c2/final-evidence.json` не перезаписан и относится только к b090bc48.
B03/B04 остаются C2-owned до итоговых проверок, не переданы в C3.

Уточнение B04: исходные C2.7 и архитектурная модель не требуют forensic wipe
всех SSD/чужих backup или таймера при выключенном ПК. Эти гарантии не заявляются.
Реальные дефекты доступа после TTL и backup воспроизведены и исправлены;
это не снятие блока переименованием требования. См. [RETENTION.md](RETENTION.md).

## Проверки кандидата

Ниже — история замороженного b090bc48 и его предшественника. Она не является
приёмкой новых bytes продолжения; новый цельный C2 должен получить свои L1–L3.

Первый frozen C2 `5dca0524e7c80edb0ea971200b3ed89bbc9aa476`, tree
`c96302cbaae88e4d7e492791e7cb6a03125917ac` — REJECTED / SUPERSEDED.
Его L1: 1807 PASS / 2 skips / 1 historical deselect. Независимый L2 REJECT
(здоровый второй voice ошибочно требовал ручной retry); L3 REJECT
(reply replay подтверждал другую generation, flag-off recovery попадал в
legacy route, отказ по duration был без ответа, та же concurrency ошибка).
Это реальные findings, не аннулированные последующей доработкой.

Один consolidated rework добавил atomic encrypted reply watermark, сохранение
receipt при позднем worker checkpoint, fail-closed остановку voice при flag-off,
async сериализацию нормальных ASR запросов и allowlist-bound адрес безопасного
отказа ingress. Свои узкие проверки: 190 PASS / 1 Windows symlink skip.
Новый frozen candidate требует собственной финальной цепочки; результаты
первого SHA не объявляются проверками новых bytes.

До freeze: predecessor voice negatives 61 PASS; после WIP изменений широкий
impacted runtime 696 PASS; затем focused parity 30 PASS и объединённые
disk/cancel/capacity + state + service 112 PASS. Это разные последовательные
ревизии WIP, не суммарный результат frozen L1. Ошибки ранних WIP проверок
сохранены в локальных receipts и не заменены PASS задним числом.

Реальный CURRENT model через новый memory path: direct, transform, noise, long
обработаны, исходные audio hashes совпали, temp directory не создан.
Language probability в этих forced-ru samples = 1.0; это особенно наглядно
не означает точность transcript. Поле теперь `language_confidence`, quality
фиксировано как `unqualified_confirmation_required`; каждый transcript
требует подтверждения владельца.

После заморозки выполняются собственные C2 L1, независимый L2 и adversarial L3.
Их exact SHA/tree, команды, exit codes и хеши выводов сохраняются в
`.runtime/c2/final-evidence.json` и `.runtime/c2/reviews/` данного worktree.
Наличие этого плана не означает ACCEPT; итоговый verdict остаётся BLOCKED,
пока хотя бы одно обязательное условие не доказано. Нормативный пакет и код
после freeze не меняются без нового candidate binding.

L1 release command (в C2 worktree с existing Python):

```powershell
python -m pytest -q -ra --tb=short --ignore=tests/gate0 --ignore=tests/test_gate_c0_governance.py --deselect=tests/test_pre_gate1_architecture_integration.py::test_active_projections_and_authority_point_to_adr0022 --basetemp=.runtime/c2/pytest-frozen-release
```

Historical Gate 0/C0 campaigns исключены как predecessor evidence. Отдельная
проверка запрещённых diff, exact C1 bindings, secrets/private bytes и
`git diff --check` относится к текущему C2. Локальные тесты никогда не включают
live flags, реальные Telegram/filesystem/Google effects или cloud audio.

## Сохранённые ограничения predecessor

C1 default-off; production trusted item-state source отсутствует, conditional
без фактов остаётся UNKNOWN. C0 prebound corpus 25/25 не является измерением
production compiler. C1 semantic 316 / impacted 762 / release 1766 PASS,
2 skips, 1 historical deselect и 35 PASS/2 historical governance FAIL —
существующее evidence, не повторная приёмка C1. Его первый provider timeout
и один unchanged successful retry не скрываются.

См. [HANDOFF](HANDOFF.md), [ASR research](ASR-RESEARCH.md),
[первичный freeze](BENCHMARK-MANIFEST.json), [результаты](BENCHMARK-RESULTS.json)
и [индекс доказательств](EVIDENCE.json).
