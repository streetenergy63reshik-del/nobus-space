# Эксплуатационные инциденты Nobus Space Bot

## Последние события 6 октября 2026

- [Вечерний public timeout / завершение relay, восстановление ночью](2026-10-06-relay-stop.md).
- [Утренний перезапуск Windows / STOP, восстановление в 11:40](2026-10-06-reboot-stop.md).

Текущий бот на `207778a` работает; актуальный срез — [CURRENT](../handoffs/CURRENT-STATUS.md). Причины UNKNOWN не заменять предположениями.

Текущий статус — [CURRENT](../handoffs/CURRENT-STATUS.md), процедуры — [runbook](../08-Runbook-эксплуатации.md). Записи ниже сохраняют время, версию, подтверждённую причину, UNKNOWN и результат восстановления. Историческая приёмка MVP1 не переписывается.

| Период | Запись |
|---|---|
| 20 сентября | [Power transition, backup/recovery и отдельный ремонт](2026-09-20-production-stop.md) |
| 29–30 сентября | [Relay STOP, backup и binding-порядок](2026-09-30-relay-stop.md) |
| 1 октября | [Повторное завершение SSH relay](2026-10-01-relay-stop.md) |
| 2 октября | [Local readiness STOP](2026-10-02-local-readiness-stop.md) |
| 4 октября | [Local/public readiness STOP после ремонта](2026-10-04-readiness-stop.md) |
| 5 октября | [Readiness HTTP 503 и штатное восстановление](2026-10-05-readiness-503-stop.md) |
| 5 октября | [Совместимость с обновлённым Codex Desktop и доставка сохранённого запроса](2026-10-05-desktop-compatibility.md) |
| 20 сентября — 3 октября | [Сводный журнал 16 аварийных завершений и выполненные меры](2026-10-03-production-stability-14d.md) |

Доказательства: [подлинные типизированные исторические наблюдения](System/2026-10-03-stability-evidence.json), [квалификация и выпуск exact 4db5f0e](System/2026-10-03-stability-release.json), [read-only проверка 3 октября 17:35](System/2026-10-03-documentation-observation.json). Эти файлы содержат агрегаты и digests, без payload, содержимого БД, сырого stderr и credentials. Хэши связывают источник, но не заменяют локальную проверку DPAPI под владельцем.
