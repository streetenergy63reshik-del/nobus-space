# Gate C2 — продолжение, C3 HOLD

**6 сентября 2026: C2 DRAFT / BLOCKED / NOT PUBLISHED / NOT DEPLOYED.**
Продуктовый checkpoint `efa0ac7e1e313bf53255b47260fa991271986399`, tree `26ca0ab70f31701a6836a05efab63cf3e9329151`.
Ветка `codex/mvp1-closure-c2-voice-parity`; работа продолжается в той же задаче.
Текущий HEAD после документационных commits определяется `git rev-parse HEAD`; точный
readback записывается отдельно в `.runtime/c2/closure/compiler-clarification-checkpoint-20260906.json`.
Это позволяет различать актуальную документацию и неизменный product-source revision.


C1 остаётся принятым и опубликованным, default-off, NOT DEPLOYED. База C2:
`43e753c571e1ad8db5af5f453b5db0c0b417cac8`, tree
`a7c6328a42412a0bd269004aefa9c9d402c75564`. Его приёмка не повторялась.
Входной HEAD продолжения `3ef14b32c1c602739db3b4d32016f5182b10567b` сохранён в ancestry.
Канонический checkout с чужим WIP и telegram-live имеют отдельное владение.

## Что уже завершено

Владелец явно принял [протокол 3](../../../tests/gate_c2/qualification/PROTOCOL.json):
подтверждаемый голосовой ввод, независимые смысловые факты, прежние WER/CER и
per-file `max(5 s,0.5×duration)`. Только exact critical-token zero и дополнительный
aggregate raw RTF перестали быть самостоятельными hard gates. Старые FAIL остаются FAIL.

ASR qualification прошла:32 синтетических примера, включая впервые открытый после
выбора holdout16, три warm-прохода на CURRENT и small, cold, concurrency2,4 CPU/4 GiB.
Выбран Systran/faster-whisper-small revision `536b0662742c02347bc0e980a01041f333bce120`,
beam8,CPU/int8, прежние prompt/hotwords/VAD/patience1.2. Это смена модели внутри
Faster-Whisper, а GigaAM остаётся ранее измеренным независимым семейством.

| Метрика | CURRENT base | Small beam8 |
|---|---:|---:|
| WER / CER all32 | 13,75% / 3,02% | 5,71% / 1,11% |
| WER / CER holdout16 | 13,47% / 3,22% | 5,09% / 1,00% |
| Смысловые правки dev16 | 7 | 3 |
| Смысловые правки holdout16 | 10 | 5 |
| Raw semantic exact all32 | 15/32 | 24/32 |
| Warm p50 / p95, s | 1,374 / 4,969 | 3,920 / 15,418 |
| Raw RTF p95, диагностика | 0,260 | 0,732 |
| Cold max, s | 2,859 | 6,058 |
| Peak committed Job bytes | 1660211200 | 3064528896 |

Каждый завершённый warm-пример уложился в формулу ожидания. Выигрыш raw semantics
28,125 п.п.; ухудшения WER/CER нет. Small медленнее base; ошибки raw остаются видимыми.
Одна TTS voice не доказывает качество на произвольных человеческих голосах.
Все 192 warm-измерения, legacy metrics, durations, long samples, cold/concurrency,
ошибки и hashes — [CONFIRMED-QUALIFICATION.json](CONFIRMED-QUALIFICATION.json).
Третий small dev был прерван PermissionError verifier после 2/16; его 14 пропусков,
14,923234 s и FAIL сохранены. Bounded Windows receipt-read исправлен после настоящего
воспроизведения CRT EACCES; завершённый повтор не считается новым blind corpus.

Локальный product factory проверяет SHA256 пяти small assets перед native constructor;
нет плавающего download или fallback при missing/mismatch. Реальная последовательность
small→закреплённый base→small прошла, native processes после каждого close0. Deployment
provisioning не выполнялся. [Происхождение и лицензии](ASR-PROVENANCE.md) разделяют
локальную квалификацию и незакрытые условия распространения native runtime.

## B02 и следующий шаг

ASR qualification пройдена. На прежнем product source2822292 получены пять готовых
ответов с независимой оценкой25/25 и затем правильный supported UNKNOWN для текста.
Голосовой UNKNOWN не прошёл: первая попытка не получила второй compiler response,
единственный разрешённый свежий повтор получил придуманное условие в proposal
безусловного хвоста. Core правильно остановился на AMBIGUITY; task/outbox/effect0.
Это не ошибка ASR или подтверждения и не доказательство прохождения UNKNOWN.

UNKNOWN-сессия по явному «да разрешаю» выполнена:6 из8 calls,142,917883 s от первого
вызова до последнего ответа, одна voice retry. Все процессы завершены. Два оставшихся
turn не разрешали третью голосовую попытку; окно600 s истекло. Исторические ledgers
8/24,19/20,6/8 и все FAIL сохранены, остатки в новые окна не переносятся.

В новом кандидате уточнена только общая инструкция compiler: сохранять условие лишь
при его наличии в текущем owner_text и не придумывать его для безусловного запроса.
Модель gpt-5.6-sol/high/fast, deadline45 s, schema, Core и проверки происхождения
операций сохранены. Устранена двусмысленная инструкция; её влияние на ответы модели
пока не доказано. 385 целевых тестов PASS; последние11 guard-тестов также PASS.
Это локальный checkpoint, а не итоговые L1/L2/L3 C2.

Поскольку изменён общий compiler prompt, старые ready/UNKNOWN результаты остаются
доказательствами прежней версии. Для нового кандидата подготовлена вся матрица B02:
17 плановых calls и7 резервных, общий предел24turn/1200s. Отдельное разрешение пока
не дано; новый ledger не создан. Повторная приёмка C1 и повтор закрытой ASR-кампании
не требуются. Small869,810135/1200 s, осталось330,189865 s; GigaAM194,916977/1800 s.

Точный следующий trial — [PRODUCT-TRIAL-PLAN.md](PRODUCT-TRIAL-PLAN.md). Реальные
результаты, hashes, независимая оценка и старые сессии — [PRODUCT-RESULTS.json](PRODUCT-RESULTS.json).
Новые offline tests проверяют изоляцию безусловного хвоста и отсутствие полномочий
при придуманном условии. Inference с изменённым prompt ещё не было.

После B02 нужны свои итоговые L1/L2/L3 замороженного C2. После итогового PASS —
публикационный manifest и точное разрешение push/PR/merge. C1 принят; live и C3
не менялись. Native binary distribution остаётся отдельным незакрытым объёмом.
