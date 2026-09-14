# Nobus Space текущий статус

**14 сентября 2026: опубликованный MVP1 ACCEPTED / PUBLISHED; прежний v1.0.2 сейчас READY, но M1-S1 ещё не завершён.**

Последний цельный read-only срез 14.09.2026, 08:28–08:31 МСК: local/public readiness PASS, Health LastTaskResult 0, один логический runtime и один polling lease. Это локальная документная актуализация, ещё не опубликованная в GitHub. C6 не повторяется; MVP2 не запускался.

Опубликован [выпуск v1.0.2](https://github.com/streetenergy63reshik-del/nobus-space/releases/tag/v1.0.2). Вердикт опубликованного статуса относится к этому пакету в защищённой `main`; непринятые локальные копии остаются WIP.

| Объект | Фактическое состояние |
|---|---|
| Принятый продукт и исходник LIVE | `82003c03d8a36015703472b472640ab4021fb416`; сейчас запущен именно он, а не maintenance-candidate |
| Тег | Аннотированный `v1.0.2`, точный product commit; опубликован и прочитан обратно |
| Исходник в main | [PR №30](https://github.com/streetenergy63reshik-del/nobus-space/pull/30), merge `9a34b60ac883d00631a9b1138905671728c62426` |
| Опубликованная main | `88e58c8866db2384423f2b154df901a2e4af6c48`, protected; документы текущего аудита пока local WIP |
| Runtime | Один логический supervisor/Core/relay, один listener 8765 и polling lease; local/public READY. Это ещё не 72-часовая устойчивость |
| Данные | 86 задач, 84 ack receipts, четыре БД health ok; очередь пуста, delivery_unknown 0, reconciliation false. Offset монотонно вырос на 2, счётчики задач/доставок не изменились |
| Scheduler | Main Running с 03:31:05 МСК, LastTaskResult 267009. Legacy `RestartCount=10/PT1M` сохранён, но реальный fixture доказал, что normal action exit 23 не был повторён. Health LastTaskResult 0 |
| Текущая копия | Backup 14.09 LastTaskResult 0; latest ownership/generation/manifest authentication/binding/ciphertext/freshness PASS. Полный restore заново не выполнялся |
| Историческая приёмка | 09.09: реальные text/voice/Mini App/TXT; post-accept backup 127,016 с; та же Word-памятка, шесть страниц проверены |
| Следующий шаг | Исправленный Scheduler-hosted F03 fixture PASS; теперь один freeze и L1/L2/L3 этой ревизии. MVP2 заблокирован |

### M1-S1 — локальный checkpoint 14.09, 08:31 МСК

Backup-цикл 14.09 создал свежую копию и после неё поднял прежний v1.0.2; поэтому тестовые mutex переведены на отдельные имена. Preservation baseline: 86 tasks, 84 ack receipts, пустая очередь, один polling lease, offset `375633467`, reconciliation false. Дублей и второй очереди нет.

F02/F03 repair локально GREEN: один action-owned controller, budget 10/60 с, exact attempt/history, allowlisted retry и типизированный STOP. Старый `RestartOnFailure` mechanism реально опровергнут; исправленный Scheduler-hosted fixture восстановил transient на attempt 2 и завершил permanent понятным budget STOP на attempt 3 без лишнего запуска. D01 — `REVIEW_TOOLING`: OSV matches только для `pip 25.0.1`, не в runtime path; установок не было. Candidate готов к freeze; L1/L2/L3, публикация, deploy, controlled production start и 72-часовое наблюдение ещё не начинались. Точный пакет: [M1-S1 HANDOFF](../gates/mvp1-maintenance/HANDOFF.md) и [EVIDENCE](../gates/mvp1-maintenance/EVIDENCE.json).

[Восемь критериев, ограничения и доказательства](../gates/gate-c6-release/OPERATIONAL-STATUS-14.md), [передача](../gates/gate-c6-release/HANDOFF.md), [эксплуатация](../08-Runbook-эксплуатации.md), [роли каталогов](WORKSPACE-INVENTORY.md).

Прежние FAIL и версии сохраняются. Документ 11 остаётся неизменным input принятого продукта. Первичный trigger runtime_failed 10–13 сентября остаётся `UNKNOWN`; причина нерабочего Scheduler recovery теперь воспроизведена отдельно. Подробнее: [аудит и пакет правок](../audits/MVP1-STABILITY-AUDIT.md), [точный промпт M1-S1](../gates/mvp1-maintenance/M1-S1-PROMPT.md).

MVP2 остаётся предложением вне этого Gate; реализация и активация не начинались. Публикация, deploy, restart и изменение продуктового кода этой задачей не выполнялись и не разрешаются этим документом. Краткий проверенный указатель в Nobus Memory не заменяет Git и текущие наблюдения.
