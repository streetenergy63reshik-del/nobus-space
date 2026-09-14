# Nobus Space текущий статус

**14 сентября 2026, 18:47 МСК: MVP1 v1.0.2 остаётся принятым и опубликованным, его последний проверенный runtime-срез — DOWN; M1-S1 и 72-часовое наблюдение не завершены.**

Последний legacy-запуск начался `00:31:06Z` и завершился `runtime_failed` в `11:39:09Z` (14:39:09 МСК). В свежем read-only срезе main enabled/Ready/LastTaskResult `1`, exact LIVE supervisor/Core/relay/listener 8765 отсутствуют, polling lease отсутствует, local/public readiness — `false/false`. Исторический первичный trigger остаётся `UNKNOWN`: v1.0.2 не сохраняет достаточную типизированную причину этого завершения.

Опубликован [выпуск v1.0.2](https://github.com/streetenergy63reshik-del/nobus-space/releases/tag/v1.0.2). Его tag и product commit не перемещались; непринятые maintenance-ревизии остаются локальным WIP.

| Объект | Фактическое состояние |
|---|---|
| Принятый продукт и исходник LIVE | `82003c03d8a36015703472b472640ab4021fb416`; checkout clean, runtime сейчас DOWN |
| Тег | Аннотированный `v1.0.2`, точный product commit; опубликован и прочитан обратно |
| Исходник в main | [PR №30](https://github.com/streetenergy63reshik-del/nobus-space/pull/30), merge `9a34b60ac883d00631a9b1138905671728c62426` |
| Опубликованная main | `88e58c8866db2384423f2b154df901a2e4af6c48`, protected; документы текущего аудита пока local WIP |
| Runtime | Нет exact LIVE supervisor/Core/relay/listener 8765 и active lease; local/public FAIL. Второго Core и второй очереди не найдено |
| Данные | Четыре БД PASS; 86 tasks/ingress, 84 ACK messages/receipts, 14/14 delivery parts, queue `{}`, `delivery_unknown=0`, `reconciliation=false`; offset `375633467`, revision `44146` |
| Scheduler | Main enabled/Ready/1, legacy `RestartCount=10/PT1M`; Health и Backup enabled, Backup Ready/0. История production retry-attempts отсутствует, поэтому исчерпание бюджета не заявляется |
| Текущая копия | `daily-20260914T033039-58e82052c3f54d6da759caad4aaed41c`; exact LIVE v1.0.2 подтвердил authentication/binding/ciphertext PASS, возраст `43577.032` с. Restore не выполнялся |
| Историческая приёмка | 09.09: реальные text/voice/Mini App/TXT; post-accept backup 127,016 с; та же Word-памятка, шесть страниц проверены |
| Следующий шаг | `73ed1c9`, `19c9bf3`, `121a4df` и `e357629` отклонены. После завершения текущего WIP: один freeze → real fixture → D01/security → L1/L2/L3 той же ревизии |

### M1-S1 — незамороженный WIP 14.09, 18:47 МСК

Preservation baseline: 86 tasks, 84 ACK receipts, пустая очередь, lease отсутствует, offset `375633467`, reconciliation false. Дублей и второй очереди нет. Принятый LIVE остаётся clean на `82003c03…`, но остановлен; legacy Scheduler retry `10/PT1M` ещё не заменён.

Отклонены `73ed1c9`, `19c9bf3`, `121a4df` и `e357629`; их evidence не смешивается с новым candidate. У `e357629` были L1 PASS, L2/L3 FAIL, aggregate FAIL при 209 frozen PASS и успешном real fixture: проверка нашла реальные контрактные пробелы, поэтому ревизия не публикуется и не развёртывается.

Текущий WIP на parent `e357629` одним пакетом закрывает все собранные блокеры: relay/planned-stop races; поздний stop после доказанного readiness failure; durable owner-authenticated latch для pre-control write failure; согласование Core exit с санитизированным outcome; principal SID, trigger time и влияющие Scheduler settings в activation binding; ограниченный backup-start только из свежей candidate-bound journal-фазы; полный run-id process cleanup и executable digest fixture; явная безопасная замена остановленной disabled backup task. Целевой supervisor/rework/L3 набор — 118 PASS; полный affected/dependent набор под реальной Windows identity — 218 PASS. Новый freeze, real fixture и reviews ещё впереди. Точный пакет: [M1-S1 HANDOFF](../gates/mvp1-maintenance/HANDOFF.md) и [EVIDENCE](../gates/mvp1-maintenance/EVIDENCE.json).

[Восемь критериев, ограничения и доказательства](../gates/gate-c6-release/OPERATIONAL-STATUS-14.md), [передача](../gates/gate-c6-release/HANDOFF.md), [эксплуатация](../08-Runbook-эксплуатации.md), [роли каталогов](WORKSPACE-INVENTORY.md).

Прежние FAIL и версии сохраняются. Документ 11 не изменён и входит digest-ом в activation binding; его будущая правка создаёт новый candidate. Исторический trigger 10–14 сентября остаётся `UNKNOWN`; отсутствие старого Scheduler recovery воспроизведено отдельно. Разрешение владельца покрывает необходимые действия и число запусков, но production-переход начнётся только после aggregate PASS по единому точному плану. Подробнее: [аудит](../audits/MVP1-STABILITY-AUDIT.md), [промпт M1-S1](../gates/mvp1-maintenance/M1-S1-PROMPT.md).

MVP2 остаётся предложением вне Gate. Publication, deploy и изменение live Tasks не выполнялись. Nobus Memory используется только в scope `project:nobus-space` и не заменяет exact Git revision/evidence.
