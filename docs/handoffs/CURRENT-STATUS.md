# Nobus Space — текущее состояние

**8 сентября 2026. C5 ACCEPTED / PASS / PUBLICATION_PENDING.** C0–C4 сохраняют принятую публикацию. MVP1 NOT READY; C6 не начат, постоянной активации нет.

Источник C5: `9efad0f2eb152ff71ec684786c07ad38c906db1b`, tree `2e31c2f2e6dd72585c9e3a794f7ee8ec7475d78c`. [Передача](../gates/gate-c5-mvp1-operations-security/HANDOFF.md) и [приёмка](../gates/gate-c5-mvp1-operations-security/ACCEPTANCE.md) связывают L1 2305 PASS +25 subtests, Node20, независимые L2/L3 и фактический drill. Документальный package будет опубликован обычным PR/merge.

Live window NOT RUN. В конечном чтении оба задания Disabled, процессов бота0, порт8765 свободен, прямой HTTPS readyz502; preflight403 остаётся прежним наблюдением. Semantic default=False. Canonical20dirty paths и остальные checkout/history сохранены.

## Сохранённый итог C4 (историческая проекция)


**8 сентября 2026. C0–C3 ACCEPTED / PUBLISHED. C4 ACCEPTED / PASS / PUBLISHED.**
C5–C6 не запущены; MVP1 NOT READY; MVP2 HOLD. Постоянного deploy нет.

Проверенный код C4: `68f87f18da3de7c995f83b9cb08b391d0af5cdfb`,
tree `5ae168bf613b18fc2f14e24973b5167a2b4c7b74`. Ветка `codex/mvp1-closure-c4-frontend-journey`,
worktree `.runtime/worktrees/mvp1-closure-c4-frontend-journey`, от опубликованного
C3 `b9283b3419928042c80278b5088b526edebab6e7` /
`77062335b1dbccb3694721d357e484c856ac89c7`.

Telegram и Mini App над одним Core дают текстовую/подтверждаемую голосовую
задачу, уточнение, честный статус, восстановление и результат с одним файлом.
Голос подтверждается кнопкой под расшифровкой; временное сообщение бота
обновляется на месте и удаляется после подтверждённой итоговой доставки.

Frontend68f87f1 прошёл20Node checks, полный L1 —2227PASS+25subtests.
Независимые L2/L3 приняли исходники и перенос неизменных доказательств. Прежние exact66 actual browser2tasks и
b89 voice/model scopes сохраняются с исходными SHA. Owner66 подтвердил новую
текстовую задачу и результат; найден initial404 UI defect, теперь исправлен.
Exact owner окно attempt8 успешно завершено: результат, копирование и TXT446байт
сверены в Mini App и Telegram. Итоговая независимая проверка пакета принята; публикация подтверждена обычным merge PR17.

Attempt8 остановлен: Job0, wrappers closed, HTTPS502, прежние bot/menu/webhook.
Штатный semantic flag остаётся defaultFalse. Завершение C4 не означает
постоянную доступность бота или всего MVP1.

[Единый handoff C5](../gates/gate-c4-frontend-journey/HANDOFF.md) содержит
продукт, ревизии, границы, отрицательные проверки, сохранённые FAIL и следующий
объём. [Публикация/readback](../gates/gate-c4-frontend-journey/PUBLICATION-READBACK.json)
фиксирует PR, main SHA/tree и фактические проверки GitHub. Отсутствующие CI
не объявляются PASS; защита main не обходится.

Canonical checkout и его20 dirty paths сохранены. C5/C6 запускает владелец
отдельными Gate-задачами после принятой публикации C4; эта задача их не начинает.

Первая принятая публикация C4: [PR17](https://github.com/streetenergy63reshik-del/nobus-space/pull/17),
main `ded561b8b3c32bcd807d7c5ed0cf37b05ec4650d`, tree `4f307fb7b6c05c8ad4e39089c287b3733d442737`.
Разрешённый status-only follow-up меняет только факт публикации и доказательства readback;
окончательная identity проверяется после его merge. C5 готов к отдельному запуску владельцем.
