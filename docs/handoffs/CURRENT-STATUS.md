# Nobus Space текущий статус

**14 сентября 2026, 21:46 МСК:** MVP1 v1.0.2 принят и опубликован. M1-S1 продолжается в той же задаче; production в текущем продолжении не изменялся, 72-часовое наблюдение ещё не началось.

Published tag `v1.0.2` → `82003c03d8a36015703472b472640ab4021fb416`; main до M1-S1 — `88e58c8866db2384423f2b154df901a2e4af6c48`. Тег не перемещён. Исторические C6 receipts и sealed sources сохранены.

Пятый frozen candidate `5b74368` восстановлен по внешней квитанции и 218 PASS по совпадающим blobs. Шестой `4777a2e59d07c18c2a99f1f3ddf818b81061c60b` прошёл real Scheduler fixture: 2 transient, 3 budget и 1 permanent attempt, cleanup proven. Все L1/L2/L3 findings собраны; aggregate FAIL сохранён из-за двух code boundary cases и двух неточностей плана. Единый ремонт `fcf99fc0f3a93881bc681e69f1f6f56f3676e246` закрывает потерю pre-signal exit и latched current/.compact interruptions; 210 затронутых и зависимых PASS. Документы уточняют реальный порядок admission и обязательное сохранение backup XML Gate operator. Итоговая revision/tree связывается внешней freeze-квитанцией.

Следующий конкретный шаг — финальная проверка документов, freeze, реальный three-case Scheduler fixture через PowerShell 7 и существующие L1/L2/L3 этой revision. D01 и классификация security findings сохраняются по неизменным входам. После aggregate PASS: свежие LIVE inputs, backup/baseline, разрешённая публикация и безопасное переключение, реальная text-задача и TXT, сверка сохранности, heartbeat этой же задачи на 72 часа.

Последний production read-only срез — **14.09, 21:32 МСК**, его требуется актуализировать перед activation:

| Объект | Наблюдавшийся факт |
|---|---|
| LIVE | clean detached `82003c03…`; DOWN после `runtime_failed` в 14:39:09 МСК |
| Runtime | Нет exact supervisor/Core/relay/listener 8765 и active polling lease; local/public false/false |
| Scheduler | Main enabled/Ready/1, legacy RestartCount=10/PT1M; Backup Ready/0 |
| Данные | Четыре БД healthy; 86 tasks, 84 ACK receipts, 14/14 parts; queue пустая, delivery_unknown=0, reconciliation=false |
| Offset | 375633467, revision 44146 |
| Backup | generation `daily-20260914T033039-58e82052c3f54d6da759caad4aaed41c` проверена exact v1.0.2 в 21:33: authentication/binding/ciphertext PASS, возраст 64966 с; перед переключением новая prechange generation |

Исторический первичный trigger остановок остаётся UNKNOWN. Истории production retry-attempts нет, поэтому исчерпание старого бюджета не заявляется. Попытка fixture `4f4d9f130bbc4f21a800d754e5e0fd1b` сверена: task/process/result отсутствуют; успех ей не приписан.

Документ 11 неизменён и остаётся runtime input. Fresh LIVE input readback 21:30 PASS: config/doc11/assets/requirements/Python80/state/backup ownership совпали. ASR runtime digest `4b9a0e8e…`; старый `3bfe7656…` воспроизведён на тех же files с префиксами member hashes. Перед activation дельта сверяется вновь; candidate helper/config/launcher/task signatures связываются после staging. Все необходимые разрешения владельца сохраняются. При неизвестном effect выполняется сверка, а не повтор. БД поверх новых accepted tasks не откатываются.

Точный текущий пакет: [HANDOFF](../gates/mvp1-maintenance/HANDOFF.md), [EVIDENCE](../gates/mvp1-maintenance/EVIDENCE.json), [Runbook](../08-Runbook-эксплуатации.md). Историческая эксплуатация: [C6 OPERATIONS](../gates/gate-c6-release/OPERATIONS.md), [роли каталогов](WORKSPACE-INVENTORY.md).

Раздельный verdict: published release — v1.0.2 unchanged; repaired candidate — код проверен, freeze/review pending; deployed runtime — без изменений, последний срез DOWN; stability observation — NOT STARTED; M2-G0 — BLOCKED. C6 не переоткрыт, MVP2 не запущен. Nobus Memory — только scope project:nobus-space.
