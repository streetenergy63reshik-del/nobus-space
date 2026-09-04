# Gate C2 — локальный кандидат, BLOCKED

Дата: 4 сентября 2026. C2 не принят и не опубликован. C1 остаётся
ACCEPTED / PUBLISHED / NOT DEPLOYED; MVP1 не READY, C3–C6 и MVP2 HOLD.

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
| C2-B01 | Замороженный pilot: CURRENT WER 19,15% выше порога 15%; critical-token mismatches 12, у GigaAM 10 при пороге 0. Часть mismatches — формат чисел; scorer не доказывает семантическую ошибку или эквивалентность. Полноценной независимой semantic exactness оценки для реальных ASR hypotheses нет. Ни KEEP, ни REPLACE не доказан. |
| C2-B02 | 16 записей одной Windows TTS voice — pilot. Нет принятого представительного корпуса русской речи, реального ASR→production compiler→готовый transform result owner smoke. Парные fixtures проверяют интеграцию C1, а не качество compiler/распознавания. |
| C2-B03 | Отмена async ASR прекращает ожидание и запрещает новый параллельный inference; native call в Python thread нельзя принудительно завершить. Тест доказывает отказ от позднего результата и bounded concurrency, но не жёсткий срок освобождения памяти при зависшем native decoder/model. Следовательно полный timeout/cleanup критерий не закрыт. |
| C2-B04 | Scrub проверяет отсутствие содержимого в актуальной логической строке SQLite; forensic удаление прошлых encrypted страниц/WAL/backup и offline downtime TTL не доказано. Raw filesystem audio в новом production path не создаётся. Полный retention criterion не закрыт. |

Пороги не ослаблялись после получения результатов. CURRENT Faster-Whisper
сохранён как исходный факт, а не как решение KEEP. GigaAM не интегрирован в
продукт. Cloud trials не выполнялись. Для закрытия B01/B02 требуется следующий
согласованный корпус/метод semantic scoring и при необходимости отдельная
точная авторизация внешнего compiler/provider smoke в этом же чате C2.
B03/B04 остаются C2-owned, не переданы в C3.

## Проверки кандидата

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
