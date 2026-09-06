# Gate C2 — продолжение, C3 HOLD

**6 сентября 2026: C2 DRAFT / BLOCKED / NOT PUBLISHED / NOT DEPLOYED.**
Продуктовый checkpoint `28222923d2c2560504d1237c8e8da6df442c6150`, tree `b24ae81b91786aca942c89a8d54f50279de3cef8`.
Ветка `codex/mvp1-closure-c2-voice-parity`; работа продолжается в той же задаче.
Текущий HEAD после документационных commits определяется `git rev-parse HEAD`; точный
readback записывается отдельно в `.runtime/c2/closure/product-checkpoint-20260906.json`.
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

## B02: пять готовых ответов, остаётся UNKNOWN

6 сентября владелец разрешил дополнительную сессию 20 turn/1200 s. Выполнено 19 calls
(14 compiler/5 downstream), все завершены; первое окно 24 turn с 8 calls не затрагивалось.
Основная text/voice-пара без смысловой коррекции голоса, отдельная correction и
negation text/voice дали пять ANSWERED+APPROVED ответов. Независимая рубрика 25/25,
один ACK/артефакт/результат на задачу, effects0. Voice controlled restart после
preview и PreparedTask, cancel и replay пройдены. Это не hard crash.

Первый transform text FAIL сохранён; обычная новая подача того же текста прошла.
UNKNOWN text был безопасно отвергнут за understood+непустые ambiguities; UNKNOWN voice
не получил второй compiler response в 45 s. Фактического Core UNKNOWN нет в обеих
модальностях. Поэтому B02/C2 остаются BLOCKED, несмотря на пять готовых ответов.
[Результаты и независимая проверка](PRODUCT-RESULTS.json).

Исторический direct-control smoke опускал внешний polling checkpoint: negation text
replay сделал один лишний compiler call, сохранив task/outbox/result. Ошибка production
не доказана. Verifier перенесён в tests/gate_c2 и использует настоящий polling/SQLite
checkpoint;24 focused tests PASS и независимый review. Старый harness сохранён.
Продуктовые src/scripts, модель, prompts и deadline не менялись.

Small суммарно 858.434166/1200 s; осталось 341.565834 s. GigaAM 194.916977/1800 s
не запускался повторно. Дополнительный provider budget завершён на 19/20: один
неиспользованный turn не покрывал полный UNKNOWN и не переносится в новое окно.

## Следующий шаг

[Подготовлен точный UNKNOWN trial](PRODUCT-TRIAL-PLAN.md):4 calls+4reserve,
максимум 8 turn/600 s. Нового разрешения пока нет, ledger не создан. Новые verifier
bytes и все ресурсные helpers зафиксированы; actual waiting voice preview сохранён
в unknown-prepared-05 без новых provider calls. Перед использованием проверить TTL1h;
истёкший preview восстанавливается только новой обычной подачей в прежнем ASR бюджете.

После успешных UNKNOWN text/voice нужны собственные итоговые L1/L2/L3 цельного C2.
Нынешние targeted/focused reviews не являются этой приёмкой. B01 qualification PASS;
B03/B04 имеют сохранённые локальные исправления и регрессию. Не возвращаться к старым
checkpoints и не повторять закрытые ASR/ready сценарии без изменения зависимых bytes.

После итогового PASS подготовить exact publication manifest и получить отдельное
разрешение push/PR/merge. Публикация пока не разрешена; C1 не переоткрывать, live и C3
не менять. Native binary distribution/rollout остаются за границей локального C2.
