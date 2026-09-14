# Nobus Space текущий статус

**14 сентября 2026, 14:02 МСК: опубликованный MVP1 ACCEPTED / PUBLISHED; прежний v1.0.2 READY на свежем срезе, но M1-S1 и 72-часовое наблюдение не завершены.**

Read-only срез 13:57–13:59 МСК: local/public PASS, Health LastTaskResult 0, один logical supervisor/Core/relay/listener и polling lease. Четыре БД здоровы; 86 задач и 84 ACK receipts сохранены, очередь пуста, delivery_unknown 0, reconciliation false, offset `375633467`, revision `43983`. Backup generation 14.09 прошла authentication/binding/ciphertext и моложе 24 часов. C6 не повторяется, MVP2 не запускался.

Опубликован [выпуск v1.0.2](https://github.com/streetenergy63reshik-del/nobus-space/releases/tag/v1.0.2). Вердикт опубликованного статуса относится к этому пакету в защищённой `main`; непринятые локальные копии остаются WIP.

| Объект | Фактическое состояние |
|---|---|
| Принятый продукт и исходник LIVE | `82003c03d8a36015703472b472640ab4021fb416`; сейчас запущен именно он, а не maintenance-candidate |
| Тег | Аннотированный `v1.0.2`, точный product commit; опубликован и прочитан обратно |
| Исходник в main | [PR №30](https://github.com/streetenergy63reshik-del/nobus-space/pull/30), merge `9a34b60ac883d00631a9b1138905671728c62426` |
| Опубликованная main | `88e58c8866db2384423f2b154df901a2e4af6c48`, protected; документы текущего аудита пока local WIP |
| Runtime | Один logical supervisor, два gated helper, один relay, одна Core chain/listener 8765 и polling lease; local/public READY. Это ещё не 72-часовая устойчивость |
| Данные | 86 задач, 84 ACK receipts, четыре БД health ok; очередь пуста, delivery_unknown 0, reconciliation false. Offset `375633467`, revision `43983`; счётчики задач/доставок не изменились |
| Scheduler | Main Running с 03:31:05 МСК, LastTaskResult 267009. Legacy `RestartCount=10/PT1M` сохранён; реальный старый fixture доказал отсутствие normal-exit retry, но не исчерпание production-бюджета. Health LastTaskResult 0 |
| Текущая копия | `daily-20260914T033039-58e82052c3f54d6da759caad4aaed41c`, LastTaskResult 0; manifest `575a2f…e84e`, authentication/binding/ciphertext/freshness PASS. Restore не выполнялся |
| Историческая приёмка | 09.09: реальные text/voice/Mini App/TXT; post-accept backup 127,016 с; та же Word-памятка, шесть страниц проверены |
| Следующий шаг | `19c9bf3` отклонён aggregate L2/L3. Новый WIP на его parent: source freeze → real three-case Scheduler fixture v3 → D01/security → L1/L2/L3. MVP2 заблокирован |

### M1-S1 — локальный checkpoint 14.09, 14:02 МСК

Preservation baseline: 86 tasks, 84 ACK receipts, пустая очередь, один polling lease, offset `375633467`, reconciliation false. Дублей и второй очереди нет. Принятый LIVE остаётся clean на `82003c03…`; legacy Scheduler retry `10/PT1M` ещё не заменён.

Отклонены `73ed1c9` и `19c9bf3`; их evidence не смешивается с новым candidate. Текущий WIP закрывает подтверждённые L2/L3-блокеры: early failure sequencing, post-probe child race, exact terminal matrix, DPAPI-authenticated history/checkpoint/reset, typed fallback CLI failures, полный activation binding и отдельный permanent fixture. RED `8 failed` → GREEN; M1-S1 matrix `87 passed in 15.72s`. Точный пакет: [M1-S1 HANDOFF](../gates/mvp1-maintenance/HANDOFF.md) и [EVIDENCE](../gates/mvp1-maintenance/EVIDENCE.json).

[Восемь критериев, ограничения и доказательства](../gates/gate-c6-release/OPERATIONAL-STATUS-14.md), [передача](../gates/gate-c6-release/HANDOFF.md), [эксплуатация](../08-Runbook-эксплуатации.md), [роли каталогов](WORKSPACE-INVENTORY.md).

Прежние FAIL и версии сохраняются. Документ 11 не изменён и теперь входит digest-ом в activation binding; его будущая правка создаёт новый candidate. Исторический trigger 10–13 сентября остаётся `UNKNOWN`; отсутствие старого Scheduler recovery воспроизведено отдельно. Подробнее: [аудит](../audits/MVP1-STABILITY-AUDIT.md), [промпт M1-S1](../gates/mvp1-maintenance/M1-S1-PROMPT.md).

MVP2 остаётся предложением вне Gate. Все необходимые действия M1-S1 разрешены, но source freeze, publication, deploy и изменение live Tasks на этом checkpoint ещё не выполнялись. Nobus Memory используется только в scope `project:nobus-space` и не заменяет exact Git revision/evidence.
