# Nobus Space — текущее состояние

**9 сентября 2026. C6: исправление запуска проверено; MVP1 NOT READY.** Source correction `b8e8ac41a401aa839710d7b11a72f76f02d97607` добавляет только `PROGRAMDATA` в ограниченное окружение supervisor. До исправления настоящий owned `ssh -V` завершался255; после —0. Затронутые startup/Job/cleanup/readiness/backup проверки:107PASS; независимые L2/L3 scoped PASS. [Точная привязка](../gates/gate-c6-release/SOURCE-CORRECTION-01.json).

Предыдущий C6 source опубликован обычным PR21, merge `7ea915790c382473378078065f0d7d3630fb56e6`. Владелец подтвердил C6-ACT-01 и локальное использование cuDNN. Совместимая миграция сохранила79 задач и прежние receipts; исходные базы сохранены, зашифрованный snapshot проверен. Live checkout переключён на7ea9157, три задания установлены и оставлены Disabled. Первая управляемая копия новых данных расшифрована и проверена.

Настоящий recovery drill остановился до readiness из-за указанной ошибки окружения SSH. После выхода supervisor все строки обеих копий и checkpoint неизменны, порт8765 и mutex свободны. Неудачная попытка и зарезервированный бюджет сохранены; полный RTO не засчитан. По отдельному точному разрешению два ожидавших групповых update сохранены в DPAPI-архив и подтверждены без исполнения, заметок или ответов в группу.

Остаются публикация исправления, подтверждение только точного изменения activation plan, полный recovery RTO≤30мин, работающие Bot/Mini App, настоящий scheduled backup и controlled restart, пользовательские text/voice/download сценарии, ≥15мин наблюдения и явная итоговая приёмка. Затем v1.0.2 и постоянная активация. Памятка пока DRAFT. Canonical20 WIP/held docs15/16/history сохранены; MVP2 HOLD. [C6 handoff](../gates/gate-c6-release/HANDOFF.md).

## Сохранённый итог C5

**8 сентября 2026. C5 ACCEPTED / PASS / PUBLISHED.** C0–C4 сохраняют принятую публикацию. MVP1 NOT READY; C6 не начат, постоянной активации нет.

Источник C5: `9efad0f2eb152ff71ec684786c07ad38c906db1b`, tree `2e31c2f2e6dd72585c9e3a794f7ee8ec7475d78c`. [Передача](../gates/gate-c5-mvp1-operations-security/HANDOFF.md) и [приёмка](../gates/gate-c5-mvp1-operations-security/ACCEPTANCE.md) связывают L1 2305 PASS +25 subtests, Node20, независимые L2/L3 и фактический drill. Пакет `e7efeaaadb2006e204ff3fea1b27b15128d39acf` опубликован обычным [PR19](https://github.com/streetenergy63reshik-del/nobus-space/pull/19); main merge `efff730b9caeceae0afdaff840c5082d818c84d5`. Все56 опубликованных файлов сверены с пакетом.

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
