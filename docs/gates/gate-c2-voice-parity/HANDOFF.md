# Gate C2 — продолжение, C3 HOLD

**5 сентября 2026: C2 DRAFT / BLOCKED / NOT PUBLISHED / NOT DEPLOYED.**
Продуктовый checkpoint `28222923d2c2560504d1237c8e8da6df442c6150`, tree `b24ae81b91786aca942c89a8d54f50279de3cef8`.
Ветка `codex/mvp1-closure-c2-voice-parity`; работа продолжается в той же задаче.
Текущий HEAD после документационных commits определяется `git rev-parse HEAD`; точный
readback записывается отдельно в `.runtime/c2/closure/confirmed-checkpoint-evidence.json`.
Это позволяет различать актуальную документацию и неизменный product-source revision.


C1 остаётся принятым и опубликованным, default-off, NOT DEPLOYED. База C2:
`43e753c571e1ad8db5af5f453b5db0c0b417cac8`, tree
`a7c6328a42412a0bd269004aefa9c9d402c75564`. Его приёмка не повторялась.
Входной HEAD продолжения `3ef14b32c1c602739db3b4d32016f5182b10567b` сохранён в ancestry.
Канонический checkout с чужим WIP и telegram-live имеют отдельное владение.

## Что уже завершено

Владелец явно принял [протокол3](../../../tests/gate_c2/qualification/PROTOCOL.json):
подтверждаемый голосовой ввод, независимые смысловые факты, прежние WER/CER и
per-file `max(5s,0.5×duration)`. Только exact critical-token zero и дополнительный
aggregate raw RTF перестали быть самостоятельными hard gates. Старые FAIL остаются FAIL.

ASR qualification прошла:32 синтетических примера, включая впервые открытый после
выбора holdout16, три warm-прохода на CURRENT и small, cold, concurrency2,4CPU/4GiB.
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
28,125п.п.; ухудшения WER/CER нет. Small медленнее base; ошибки raw остаются видимыми.
Одна TTS voice не доказывает качество на произвольных человеческих голосах.
Все192 warm-измерения, legacy metrics, durations, long samples, cold/concurrency,
ошибки и hashes — [CONFIRMED-QUALIFICATION.json](CONFIRMED-QUALIFICATION.json).
Третий small dev был прерван PermissionError verifier после2/16; его14 пропусков,
14,923234s и FAIL сохранены. Bounded Windows receipt-read исправлен после настоящего
воспроизведения CRT EACCES; завершённый повтор не считается новым blind corpus.

Локальный product factory проверяет SHA256 пяти small assets перед native constructor;
нет плавающего download или fallback при missing/mismatch. Реальная последовательность
small→закреплённый base→small прошла, native processes после каждого close0. Deployment
provisioning не выполнялся. [Происхождение и лицензии](ASR-PROVENANCE.md) разделяют
локальную квалификацию и незакрытые условия распространения native runtime.

## B02: что произошло и что осталось

В первой реальной provider session выполнено8 compiler turns, downstream0, ready answers0.
Окно24turn/1200s истекло;16 неиспользованных turns больше не доступны. Старые SQLite ledger,
ответы, отказавшие сценарии и source binding сохранены в `closure/product-smoke/confirmed-01/`.

Исправлены четыре воспроизведённых дефекта: граница «следующего материала»;
маскирование supported UNKNOWN общим material guard; восстановление подтверждённого
no-effect контракта по уже удалённому prefix; изменение immutable timestamps при
восстановлении PENDING task. Известные material facts и Core authority не ослаблены.
Подтверждены324 целевые проверки и48 voice checks. Полная регрессия дала1887 PASS,
2 skips,1 прежний deselect и1 FAIL устаревшей startup fixture. Fixture обновлена;
весь runner subset22 PASS. Первый FAIL не переименован в PASS.

Новая подготовка использует фактический product factory и все src/scripts hashes.
Zero-provider preview/cancel/replay не используют истёкшую compiler квоту; ASR разрешён
только в admit и целиком учитывается старым small ledger. Любой provider turn требует
действующего собственного бюджета. Новый ledger пока не создан, additional manifest
имеет `PENDING_AUTHORIZATION`. [Точный план дополнительного trial](PRODUCT-TRIAL-PLAN.md):
17 обязательных turns +3 для повторов, максимум20 и1200s от первого вызова.

B03/native lifetime и B04/TTL/retention сохранены и прошли относящуюся регрессию нового
кода; собственная итоговая L1/L2/L3 по цельному C2 ещё не проводилась. Их нельзя переносить
с исторических candidates или объявлять завершёнными вместо недостающего B02.

## Продолжение после точного дополнительного разрешения

1. Прочесть актуальные Git HEAD/tree, EVIDENCE и оба расходных ledger. Не возвращаться к3ef14b.
2. Проверить hashes окончательных code/model/config/fixture bytes, готовность preview и TTL.
   При истёкшем preview создать новый обычным intake в оставшемся ASR бюджете; не менять SQLite вручную.
3. Выполнить одну подготовленную provider session, независимо проверить реальные ready artifacts,
   UNKNOWN, подтверждение/коррекцию, controlled restart и replay. Не переоценивать C1.
4. После B01/B02 собрать окончательный кандидат C2 и выполнить собственные L1/L2/L3.
5. После PASS подготовить точный publication manifest и получить недостающее разрешение
   push/PR/merge. Сейчас публикация не разрешена. Не менять live, не выпускать binaries/tag/release,
   не запускать C3. Никакого нового распознавателя или Cloud project для этого продолжения не нужно.
