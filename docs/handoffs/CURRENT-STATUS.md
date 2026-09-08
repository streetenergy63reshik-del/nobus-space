# Nobus Space — текущее состояние

**8 сентября 2026. C0–C3 ACCEPTED / PUBLISHED. C4 ACCEPTED / PASS / NOT PUBLISHED.**
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
сверены в Mini App и Telegram. Итоговая независимая проверка пакета принята; публикация выполняется обычным PR.

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
