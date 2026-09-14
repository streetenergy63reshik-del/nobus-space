# Nobus Space текущий статус

**14 сентября 2026: опубликованный MVP1 ACCEPTED / PUBLISHED; прежний v1.0.2 READY на срезе 12:20–12:26 МСК, но M1-S1 ещё не завершён.**

Последний цельный read-only срез: local/public PASS вне сетевого sandbox, Health LastTaskResult 0, один логический runtime/listener и polling lease. Четыре БД здоровы; 86 задач и 84 ACK receipts сохранены, очередь пуста, delivery_unknown 0, reconciliation false, offset `375633467`, revision `43607`. Backup 14.09 повторно прошёл authentication/binding/ciphertext и моложе 24 часов. Это локальная документная актуализация; C6 не повторяется, MVP2 не запускался.

Опубликован [выпуск v1.0.2](https://github.com/streetenergy63reshik-del/nobus-space/releases/tag/v1.0.2). Вердикт опубликованного статуса относится к этому пакету в защищённой `main`; непринятые локальные копии остаются WIP.

| Объект | Фактическое состояние |
|---|---|
| Принятый продукт и исходник LIVE | `82003c03d8a36015703472b472640ab4021fb416`; сейчас запущен именно он, а не maintenance-candidate |
| Тег | Аннотированный `v1.0.2`, точный product commit; опубликован и прочитан обратно |
| Исходник в main | [PR №30](https://github.com/streetenergy63reshik-del/nobus-space/pull/30), merge `9a34b60ac883d00631a9b1138905671728c62426` |
| Опубликованная main | `88e58c8866db2384423f2b154df901a2e4af6c48`, protected; документы текущего аудита пока local WIP |
| Runtime | Один logical supervisor, два gated helper, один relay/Core listener, один listener 8765 и polling lease; local/public READY. Это ещё не 72-часовая устойчивость |
| Данные | 86 задач, 84 ACK receipts, четыре БД health ok; очередь пуста, delivery_unknown 0, reconciliation false. Offset не уменьшился, revision вырос до `43607`, счётчики задач/доставок не изменились |
| Scheduler | Main Running с 03:31:05 МСК, LastTaskResult 267009. Legacy `RestartCount=10/PT1M` сохранён; реальный старый fixture доказал отсутствие normal-exit retry, но не исчерпание production-бюджета. Health LastTaskResult 0 |
| Текущая копия | Backup 14.09 LastTaskResult 0; latest ownership/generation/manifest authentication/binding/ciphertext/freshness PASS. Полный restore заново не выполнялся |
| Историческая приёмка | 09.09: реальные text/voice/Mini App/TXT; post-accept backup 127,016 с; та же Word-памятка, шесть страниц проверены |
| Следующий шаг | Implementation checkpoint `87dba94` GREEN; теперь один новый freeze, реальный product-chain Scheduler fixture v2 и L1/L2/L3 этой ревизии. MVP2 заблокирован |

### M1-S1 — локальный checkpoint 14.09, 12:28 МСК

Backup-цикл 14.09 создал свежую копию и после неё поднял прежний v1.0.2; поэтому тестовые mutex переведены на отдельные имена. Preservation baseline: 86 tasks, 84 ack receipts, пустая очередь, один polling lease, offset `375633467`, reconciliation false. Дублей и второй очереди нет.

Первая frozen revision `73ed1c9` отклонена L1/L2/L3 и не будет опубликована или развёрнута. Все замечания собраны и исправлены одним пакетом в implementation checkpoint `87dba94`: action-owned controller, protocol v3 с activation binding/hash transitions, fail-closed history, exact Core allowlist, независимые probes, durable control STOP, bounded logs и product-chain fixture. Локально: rework `24 passed`, affected `116 passed`, dependent host-context `34 passed`; установок нет. Реальный fixture v2, frozen D01 и L1/L2/L3 ещё не запускались. Точный пакет: [M1-S1 HANDOFF](../gates/mvp1-maintenance/HANDOFF.md) и [EVIDENCE](../gates/mvp1-maintenance/EVIDENCE.json).

[Восемь критериев, ограничения и доказательства](../gates/gate-c6-release/OPERATIONAL-STATUS-14.md), [передача](../gates/gate-c6-release/HANDOFF.md), [эксплуатация](../08-Runbook-эксплуатации.md), [роли каталогов](WORKSPACE-INVENTORY.md).

Прежние FAIL и версии сохраняются. Документ 11 остаётся неизменным input принятого продукта. Первичный trigger runtime_failed 10–13 сентября остаётся `UNKNOWN`; причина нерабочего Scheduler recovery теперь воспроизведена отдельно. Подробнее: [аудит и пакет правок](../audits/MVP1-STABILITY-AUDIT.md), [точный промпт M1-S1](../gates/mvp1-maintenance/M1-S1-PROMPT.md).

MVP2 остаётся предложением вне этого Gate; реализация и активация не начинались. Пользователь разрешил все необходимые действия M1-S1, но publication, deploy, restart и изменение live Tasks на этом checkpoint ещё не выполнялись. Краткий проверенный указатель в Nobus Memory не заменяет Git и текущие наблюдения.
