# Единая передача Gate C4 → C5

**8 сентября 2026. C4 ACCEPTED / PASS / PUBLISHED.**
Этот документ объединяет код, проверки и публикацию C4. C5–C6 не запущены;
MVP1 NOT READY; MVP2 HOLD. Постоянного production deploy нет.

## Результат для владельца

Telegram Bot и Mini App используют один существующий Core. Текстовая задача
принимается через любой из двух интерфейсов. Голосовое сообщение сначала
распознаётся локальным ASR; бот показывает расшифровку и две кнопки:
«Подтверждаю» и «Записать заново». До подтверждения задача не выполняется.
Ответ с исправленным текстом также поддерживается. Автоматический запуск
голоса без подтверждения остаётся будущим изменением за пределами C4.

Бот сразу сообщает о получении сообщения до долгого разбора запроса. Один
промежуточный ответ обновляется по ходу выполнения и удаляется после
подтверждённой доставки результата и файла. В чате остаются итог и TXT.
Старые сообщения, созданные предыдущими test runtime, задним числом не удаляются.

Если запрос непонятен, Core задаёт уточнение; продолжение связано с исходным
запросом и владельцем. Неподдерживаемая операция получает понятный отказ без
задачи и эффекта. Статус, прогресс и ошибки берутся из Core; процентов или
обещаний успешного выполнения интерфейс не придумывает.

Mini App восстанавливает выбранную задачу, сессию и исход запроса после reload,
reconnect и истечения короткого bearer. При неизвестном результате POST клиент
читает существующий request journal. Новый POST автоматически не отправляется.
Отмена разрешена только для точно ещё не принятого key; tombstone закрывает
поздний create. После исходного срока Telegram-подписи требуется снова открыть
Mini App из Telegram.

Результат можно прочитать и скопировать; один связанный `nobus-result.txt`
получается через оба канала. Mini App проверяет фактически скачанные bytes,
размер и digest до передачи файла браузеру. Имя файла — представление;
C3 artifact identity, result revision, digest и receipts сохраняются.

## Ревизии и доказательства

Ветка: `codex/mvp1-closure-c4-frontend-journey` в изолированном C4 worktree.
Repository: `streetenergy63reshik-del/nobus-space`.

| Роль | SHA | Tree |
|---|---|---|
| Принятая опубликованная C3 база | b9283b3419928042c80278b5088b526edebab6e7 | 77062335b1dbccb3694721d357e484c856ac89c7 |
| Первая принятая публикация C4, PR17 | ded561b8b3c32bcd807d7c5ed0cf37b05ec4650d | 4f307fb7b6c05c8ad4e39089c287b3733d442737 |
| Итоговый код C4 | 68f87f18da3de7c995f83b9cb08b391d0af5cdfb | 5ae168bf613b18fc2f14e24973b5167a2b4c7b74 |

[CODE-MANIFEST](CODE-MANIFEST.json) связывает все product/test bytes относительно C3.
[DOCS-MANIFEST](DOCS-MANIFEST.json) отдельно связывает активную документацию;
[MANIFEST](MANIFEST.json) — весь пакет без собственного файла. Документационный
commit не переименовывает source checks. PR и опубликованная main находятся в
[PUBLICATION-READBACK](PUBLICATION-READBACK.json).

На66cff24 полный собственный L1 дал2227PASS+25subtests,2Windows symlink SKIP,
2объяснённых historical deselect. На68f87f1 собственный полный L1 дал2227PASS+25subtests за187.03с;
Node frontend20PASS. Команды, counts и исходные receipts —
[TEST-RECEIPTS](TEST-RECEIPTS.json). C0–C3 повторно не принимались.
Независимые scoped L2/L3 и окончательная проверка пакета связаны отдельно в
[REVIEW-VERDICTS](REVIEW-VERDICTS.json).

Последняя правка касается первого чтения карточки: при404 действие «К списку
задач» закрывает недоступную карточку; после ошибки исчезает «Загружаем…».
Сохранённый pending request не отменяется, новый POST не появляется. При
временной ошибке уже полученные данные сохраняются. Новые URL статических
файлов исключают загрузку старого cached script после обновления HTML.

[LOCAL-JOURNEYS](LOCAL-JOURNEYS.json) сохраняет b89b651 direct/transform
text/voice, clarification/unavailable, шесть restart/replay и шесть отдельных
чтений прежних sealed результатов через новый66cff24 Core/HTTP. Первоначальные
model/ASR вызовы остаются привязанными к b89b651. Provider timeout и failed
attempts сохранены; подтверждённый voice input продолжен до Core admission
без нового ASR, а replay не повторял model/ASR или доставку.

[RETAINED-66-TWO-TASKS](RETAINED-66-TWO-TASKS.json) подтверждает две реальные
задачи через браузер, Core и provider: очередь→«В работе», reload/reconnect,
потерю настоящего202 без второго POST, отдельные результаты/TXT и защиту от
запоздалого ответа первой задачи. Четыре model turns, ASR0. У локального
синтетического Telegram sender обнаружилось ограничение одинакового имени
файла; доставлена только оставшаяся часть из существующего outbox. L3 отдельно
подтвердил2ACK/4partACK без повторного выполнения. Старый FAIL не переписан.

[SCREENSHOTS](SCREENSHOTS.json) связывает текущую матрицу320/390/768px,
light/dark, клавиатуру/focus, копирование, download, expiry/recovery и negative
initial404. Локальный браузер работает над настоящим MiniAppCore и копией
sealed synthetic task store; user profile, raw Telegram initData и продуктовые
моки не используются. Реальная Telegram-проверка выделена отдельно.

## Настоящий Telegram и Mini App

На b89b651 владелец подтвердил голос кнопкой, получил результат/TXT и проверил
копирование. Исходные523байта и SHA256
`069eca0c5dbb084c9e906e20dabcc5e0f6b6843aa1f87aac5db54bc44f9b985d`
связаны в [RETAINED-B89-LIVE-SMOKE](RETAINED-B89-LIVE-SMOKE.json).

На66cff24 владелец создал текстовую задачу из Mini App, наблюдал «В работе» и
результат; Telegram подтвердил answer/document356байт. До её создания UI
пытался восстановить старую выбранную карточку и показал ошибочный loader.
Этот defect исправлен в68f87f1. Владелец сообщил об успешном скачивании,
но artifactHTTPGET/физический файл этого окна не наблюдались; этот шаг не
объявлен доказанным. Точная область —
[RETAINED-66-OWNER-SMOKE](RETAINED-66-OWNER-SMOKE.json).

Ограниченное окно attempt8 exact68f87f1 на `@Nobusspacebot`, в проверенном
личном чате и `https://app.nobusspace.com` завершено успешно.
[LIVE-SMOKE](LIVE-SMOKE.json) связывает подписанную Telegram-сессию, одну
задачу, результат, скачивание446байт из Mini App и тот же digest в Telegram.
Владелец подтвердил проверку. После штатного STOP JobActiveProcesses=0,
все компоненты закрыты; HTTPS вернулся к исходному502, bot/menu/webhook прежние.
Полные owner screenshots не публикуются из-за посторонней переписки/фона;
сохраняются hashes и связанный readback.

Неизменные доказательства прежних SHA сохраняются только в явно названной
области с независимой проверкой применимости. Ни b89 неверный running status,
ни66 ошибочный initial404 не переносятся как PASS новой версии.

## Границы и сохранность

Semantic path проверен в изолированном ON-кандидате. Штатный runner сохраняет
`_GATE_C1_SEMANTIC_ADMISSION_ENABLED=False`; постоянная активация не выполнена.
Local/live fixtures используют `project_context=None`. Новый docs11 имеет
отдельный digest и не объявляется проверенным прежними model inputs.

C1 tenant/meaning/policy, C2 qualified small ASR/confirmation и C3 durable
queue/recovery/part delivery остаются действующими. Новых Core, очереди, ASR,
frontend framework или dependency не добавлено.

Callback голоса связан с owner/tenant/chat, exact preview message, generation,
transcript digest и одноразовым token со сроком до15мин. «Записать заново»
отменяет данный ввод. Очистка прогресса подтверждается Core/outbox; для
отменённого голоса без задачи используется существующий finished-voice
24-часовой tombstone. После его удаления неизвестная progress reference
автоматически не удаляется. Неизвестный исход не разрешает повтор задачи.

[Сохранность](PRESERVATION.json): все20 dirty canonical paths совпадают с C4 entry;
C0–C3 sealed packages и защищённые документы сохранены. Исторический C3 manifest
имел19 hashes и один явный пробел; отсутствующий hash не придуман.
[История исправлений](SMOKE-REWORK.md) сохраняет прежние FAIL и временные окна.
Общий сохраняемый журнал расходов всех попыток приведён в [EVIDENCE](EVIDENCE.json):
лимиты64 фактических model turns/5400с и20 ASR/1200с не сбрасываются. C4 accounting считает фактические model turns перед SDK;
старты без inference не расходуют turns, но всё их время остаётся в5400с.
Все прежние строки сохранены; принятый код учёта C3 не изменён.

## Передача C5

C4 принят и опубликован. C5 готов к отдельному запуску по поручению владельца.
Первая принятая публикация — PR17; этот status-only follow-up не меняет код.
Окончательные main SHA/tree после последнего merge записываются во внешний
publication receipt и итоговый ответ, без самоссылочного commit в этом файле.
Его точная база — опубликованная main из PUBLICATION-READBACK, а не dirty
canonical checkout и не старый live. C5 должен завершить эксплуатационные
health/ingress/security, backup/restore, очистку, rollback и существующую единую
инструкцию по фактически принятому UI. В неё входят голосовые кнопки,
восстановление сессии/UNKNOWN и получение файла.

C6 принимает frozen release, разрешённую активацию и весь MVP1.
C4 не запускает C5/C6/MVP2, не делает постоянный deploy, tag/release или
публикацию редакционной roadmap/HTML. Полного MVP1 READY пока нет.
