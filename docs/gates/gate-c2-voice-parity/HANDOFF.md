# Gate C2 — продолжение, C3 HOLD

**6 сентября 2026: C2 GATE CANDIDATE / FINAL REVIEW PENDING / NOT PUBLISHED / NOT DEPLOYED.**
Продуктовый checkpoint `4ed2cd2418b58ba499ff5dfdf69605244ceb4916`, tree `8eee2901119bb3699477479ef810efae3608773f`.
Ветка `codex/mvp1-closure-c2-voice-parity`; работа продолжается в той же задаче.
Текущий HEAD после документационных commits определяется `git rev-parse HEAD`; точный
readback записывается отдельно в `.runtime/c2/closure/final-candidate-20260906/freeze.json`.
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

Новая B02 на product-source 4ed2cd2418b58ba499ff5dfdf69605244ceb4916 / tree 8eee2901119bb3699477479ef810efae3608773f прошла:
пять реальных готовых ответов, независимая рубрика25/25 и обе фактические
MATERIAL_ITEM_STATE_V1/UNKNOWN → CLARIFY/PREDICATE_UNKNOWN. Основная пара text/voice
прошла без смысловой коррекции. Отдельный correction-path соответствует явной правке
пользователя. До подтверждения compiler/task/effect0. Cancel, сохранённый preview,
PreparedTask и controlled restart/replay проверены; второй задачи или результата нет.

Сессия использовала17/24 model turns за418.837421s в одном окне1200s.
Были заморожены code/model/profile/fixtures. Старые FAIL, включая предыдущую
сессию21/24 с четырьмя неудачными correction-подачами, сохранены. Явная коррекция
не засчитана как точность исходного ASR. Прежние окна закрыты, остатки не перенесены.

ASR qualification PASS по протоколу3. В C2 кандидат выбран pinned small beam8 с
прежними CPU/int8/ru/VAD/patience1.2/prompt/hotwords, без новых зависимостей.
B03/B04 реализованы; собственные полные L1/L2/L3 по цельному freeze ещё впереди.
Условия binary distribution и live rollout отдельно ограничены ASR-PROVENANCE.md.

Владелец6 сентября разрешил полное завершение C2, необходимые ограниченные проверки
и обычные push/PR/merge после PASS. Повторный вопрос о том же разрешении не нужен.
Перед публикацией — exact manifest и итоговые проверки, после — GitHub readback.
C3 ещё не начат. Весь MVP1 не READY до C3–C6.

Выполненный план — [PRODUCT-TRIAL-PLAN.md](PRODUCT-TRIAL-PLAN.md). Реальные
результаты, hashes, независимая оценка и старые сессии — [PRODUCT-RESULTS.json](PRODUCT-RESULTS.json).
Новые offline tests проверяют изоляцию безусловного хвоста и отсутствие полномочий
при придуманном условии. Новая B02 прошла на изменённом prompt.

## Передача C3 после приёмки и публикации

После итогового PASS фиксируются exact принятая revision и main readback. C3 ведётся
отдельной задачей по запуску владельца: queue/state/retry/recovery/status, multipart
idempotency и authoritative recovery. C2 blockers туда не переносятся. Подтверждение
voice, server-owned authority и pinned ASR сохраняются. C1 повторно не принимать.
