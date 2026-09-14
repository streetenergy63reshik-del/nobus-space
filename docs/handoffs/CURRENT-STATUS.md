# Nobus Space текущий статус

**14 сентября 2026, 21:17 МСК:** MVP1 v1.0.2 принят и опубликован. M1-S1 продолжается в той же задаче; production в текущем продолжении не изменялся, 72-часовое наблюдение ещё не началось.

Published tag `v1.0.2` → `82003c03d8a36015703472b472640ab4021fb416`; main до M1-S1 — `88e58c8866db2384423f2b154df901a2e4af6c48`. Тег не перемещён. Исторические C6 receipts и sealed sources сохранены.

Пятый frozen candidate `5b743680eaee4b43fd4912f916c52ea1a8ed1080` восстановлен по внешней квитанции; прежние 218 PASS привязаны к его code/test/input blobs. По собранным L1/L2/L3 он отклонён. Проверяющий отказал до product attempt из-за PowerShell 5.1; поздние child exits, rotation/latch и безопасная замена Scheduler profiles исправлены одним пакетом. Текущий code checkpoint — `23e47414932e236824c0d48430addac3cb4e9f88`; 137 целевых и 56 зависимых PASS под Windows identity владельца с изолированными mutex. Итоговый commit/tree документов и кода будет связан одной внешней freeze-квитанцией.

Следующий конкретный шаг — финальная проверка документов, freeze, реальный three-case Scheduler fixture через PowerShell 7 и существующие L1/L2/L3 этой revision. D01 и классификация security findings сохраняются по неизменным входам. После aggregate PASS: свежие LIVE inputs, backup/baseline, разрешённая публикация и безопасное переключение, реальная text-задача и TXT, сверка сохранности, heartbeat этой же задачи на 72 часа.

Последний production read-only срез — **14.09, 15:34–15:37 МСК**, его требуется актуализировать перед activation:

| Объект | Наблюдавшийся факт |
|---|---|
| LIVE | clean detached `82003c03…`; DOWN после `runtime_failed` в 14:39:09 МСК |
| Runtime | Нет exact supervisor/Core/relay/listener 8765 и active polling lease; local/public false/false |
| Scheduler | Main enabled/Ready/1, legacy RestartCount=10/PT1M; Backup Ready/0 |
| Данные | Четыре БД healthy; 86 tasks, 84 ACK receipts, 14/14 parts; queue пустая, delivery_unknown=0, reconciliation=false |
| Offset | 375633467, revision 44146 |
| Backup | generation `daily-20260914T033039-58e82052c3f54d6da759caad4aaed41c` проверена exact v1.0.2; freshness сейчас не утверждается |

Исторический первичный trigger остановок остаётся UNKNOWN. Истории production retry-attempts нет, поэтому исчерпание старого бюджета не заявляется. Попытка fixture `4f4d9f130bbc4f21a800d754e5e0fd1b` сверена: task/process/result отсутствуют; успех ей не приписан.

Документ 11 неизменён и остаётся runtime input. Fresh LIVE input readback PENDING; ожидаемые старые hashes не являются свежей проверкой. Все необходимые разрешения владельца сохраняются. При неизвестном effect выполняется сверка, а не повтор. БД поверх новых accepted tasks не откатываются.

Точный текущий пакет: [HANDOFF](../gates/mvp1-maintenance/HANDOFF.md), [EVIDENCE](../gates/mvp1-maintenance/EVIDENCE.json), [Runbook](../08-Runbook-эксплуатации.md). Историческая эксплуатация: [C6 OPERATIONS](../gates/gate-c6-release/OPERATIONS.md), [роли каталогов](WORKSPACE-INVENTORY.md).

Раздельный verdict: published release — v1.0.2 unchanged; repaired candidate — код проверен, freeze/review pending; deployed runtime — без изменений, последний срез DOWN; stability observation — NOT STARTED; M2-G0 — BLOCKED. C6 не переоткрыт, MVP2 не запущен. Nobus Memory — только scope project:nobus-space.
