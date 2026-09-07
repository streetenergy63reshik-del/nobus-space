# Единая передача Gate C4 → C5

**C4 LOCAL VERIFIED / LIVE E2E PENDING / NOT ACCEPTED / NOT PUBLISHED.**
Передача сохраняет весь результат C4, но не разрешает старт C5.
C5–C6 HOLD; MVP1 NOT READY; MVP2 HOLD. Актуально на 7 сентября 2026 года.

## Продуктовый результат

Существующие Telegram Bot и Mini App работают над одним Core.
Текстовая и подтверждённая голосовая задача проходят общий semantic admission.
Уточнение продолжается с проверкой владельца, контекста и срока.
Оба канала используют единый каталог состояния, причины и следующего действия.

Mini App восстанавливает сессию, уточнение и исход запроса после reload/reconnect.
Потерянный ответ POST не повторяет выполнение: клиент читает Core journal.
Core отменяет только точно ещё не принятый key и закрывает его для позднего create.
Результат можно прочитать/скопировать, а один связанный файл — получить в обоих каналах.
Light/dark, mobile и keyboard/focus реализованы; фактическая визуальная приёмка остаётся открытой.

## Точные привязки

Repository: `streetenergy63reshik-del/nobus-space`.
Branch: `codex/mvp1-closure-c4-frontend-journey`.
Worktree относительно каталога Code:
`nobus-orchestrator-dev/.runtime/worktrees/mvp1-closure-c4-frontend-journey`.

| Роль | SHA | Tree |
|---|---|---|
| Принятая опубликованная база C3 / последнее readback main | b9283b3419928042c80278b5088b526edebab6e7 | 77062335b1dbccb3694721d357e484c856ac89c7 |
| Проверенный код C4 | a869a691293e45a1a3e65303be627d684acfa16e | 9a7cab97fb9947ebdfedeb5baffa57f9627a4c98 |
| Сохранённый первый REJECT | ad02795c5457deb3909517efd1992cacb5ac9a73 | 229d7a4be82da7391ee339825fffb3538d34481d |

[CODE-MANIFEST](CODE-MANIFEST.json) фиксирует 40 изменённых файлов замороженного
кандидата. [MANIFEST](MANIFEST.json) и [DOCS-MANIFEST](DOCS-MANIFEST.json) отдельно
связывают итоговые документы и evidence. Они не содержат SHA собственного commit.
Последняя local docs revision записывается в отдельный локальный checkpoint receipt.

Semantic path проверялся в изолированном ON-кандидате; штатный runner по-прежнему
имеет default-off flag. Временные тесты используют project_context=None.
Обновлённый docs11 читается обычным runner и имеет новый явно записанный digest;
старые model runs не объявляются проверкой этих новых context bytes.
Изменение фактической проекции docs не меняет Core policy/capabilities или pinned prompts.

## Контракты и матрицы

[UX-MATRIX](UX-MATRIX.md) сопоставляет Telegram ↔ Mini App, состояния и gaps до/после;
[NEGATIVE-MATRIX](NEGATIVE-MATRIX.md) связывает негативные проверки с Core truth.

[ADR0025](../../adr/0025-miniapp-session-and-request-recovery.md): fresh raw initData
сохраняет durable anti-replay. HttpOnly SameSite=Strict recovery credential вращается
однократно, сохраняет исходный deadline, отзывает прежнее поколение bearer и не
расширяет owner/tenant scope. После deadline нужна новая Telegram-подпись.
Bearer только в памяти; localStorage содержит лишь opaque navigation/request markers.
Unknown POST читается, а не повторяется; cancellation tombstone закрывает late create.

[ADR0026](../../adr/0026-channel-neutral-product-projection.md): только Core даёт
состояние/причину. «Результат» не обещает истинность модели или готовность MVP1.
Неизменные C3 result revision/digest, artifact identity/bytes и part receipts
сохраняются. `nobus-result.txt` — только имя представления.
Mini App проверяет реально полученные size/hash/MIME перед Blob download;
Telegram получает те же bytes. [LOCAL-JOURNEYS](LOCAL-JOURNEYS.json) содержит
точные result/artifact digests и размеры шести результатов.

## Проверки и оставшийся пробел

Собственный frozen L1: **2132 PASS + 25 subtests PASS**; 2 Windows symlink SKIP,
1 historical deselect; frontend Node17 PASS. [TEST-RECEIPTS](TEST-RECEIPTS.json)
сохраняет команды, исходные хэши receipts и исторический failed L1.

Локальные actual-provider/ASR пути: direct_text, telegram_text, transform_text,
direct_voice, transform_voice, clarification, unavailable. Шесть задач завершены
и имеют 12 подтверждённых частей доставки; unavailable имеет task/job/outbox0.
Все шесть отдельных restart/replay сохранили результат без новых model/ASR calls.
Транспорт Telegram и initData в этих локальных проверках синтетические.

Независимый L2: 634 evidence checks и 7 собственных Node checks PASS; семь реальных
синтетических ответов оценены по intent/scope/honesty/delivery/usefulness, каждый15/15.
Независимый L3: 7 новых adversarial PASS; проверены source/result/artifact/replay bindings.
[REVIEW-VERDICTS](REVIEW-VERDICTS.json) различает identities, исходные REJECT,
прежние paused evidence и текущий ограниченный ACCEPT.
Доказательства прежнего автора не названы собственными проверками нового reviewer.

[SCREENSHOTS](SCREENSHOTS.json): снимков нет. Viewports320/390/768, light/dark,
keyboard-only и реальный Telegram WebView не проверены.
Причина — повторяемый startup error штатных Browser/Windows tools.
Минимальный недостающий шаг: восстановить штатную UI-поверхность либо пройти
точный owner-run сценарий настоящим владельцем с проверяемыми результатами
и снимками без credentials/initData/private data. Разрешение на C4 уже выдано.

## Временный smoke, сохранность и бюджет

[Сводный live receipt](LIVE-SMOKE.json) содержит точные бот/чат, origin,
helper manifest, лимиты, фактические результаты и stop/readback.
Первая попытка завершилась до пользовательского input: lease300s пересёк строгую
границу из-за разницы часов; причина воспроизведена офлайн и исправлена на240s.
Исходные FAIL, STOP, DB, manifest и reviewer verdict сохранены.
Изменение Telegram pending count3→1 до контрольного запуска не имеет установленного
происхождения; локальный offsetNULL не позволяет приписать его ACK помощника.

Контрольная attempt2 использует отдельную папку/окно, тот же exact code/bot/owner/origin,
существующий relay и общий C4 ledger. Exact HTTPS instance и три static hashes
совпали. Это route check, не завершённый owner smoke.
Никакие production DB, Scheduler, VPS/network config, menu/profile или credentials
не изменялись. Останавливаются только процессы собственного Windows Job;
Оба окна закрыты. Root readback подтвердил JobActiveProcesses0, отсутствие
слушателя8765 и consumer/relay, baseline health/readiness502, прежние bot/menu/webhook.
Настоящих ownerinputs и botoutputs во второй попытке0.

Единый бюджет C4:64 model reservations/turns,5400s active;20localASR,1200s native.
Фактический накопленный расход:23 model reservations /18actual turns /280.359s;
ASR2runs /14.11s; active reservations0. Остаток41model reservations /5119.641s,
18ASR /1185.89s. [EVIDENCE](EVIDENCE.json) и LIVE-SMOKE сохраняют точные значения;
старые ошибки/retries/bootstrap включены, ledger не обнулялся.
Новых моделей, зависимостей, API billing или покупок нет.

[PRESERVATION](PRESERVATION.json):20 текущих canonical dirty hashes/status
совпали с C4 entry. Все19 исторически записанных C3 hashes совпали;
отсутствующий старый hash runtime_maintenance.py не выдуман.
Docs06/07/12/13, C0–C3 и sealed Gate0 сохранены; соседние worktrees не редактировались.

## Публикация и C5

C4 push/PR/merge не выполнены; C4 PR отсутствует. GitHub main прочитана обратно:
`b9283b3419928042c80278b5088b526edebab6e7`,
tree `77062335b1dbccb3694721d357e484c856ac89c7`, protected=true.
Подробная protection policy через connector вернула403; её детали не считаются
доказанными. Отсутствующие CI checks не названы PASS.

После настоящего полного C4 PASS необходимо в этой же C4 задаче завершить ordinary
push/PR/merge с обязательными checks/reviews, exact head/base/manifest check,
fetch/readback final main SHA/tree и при необходимости один разрешённый
status-only follow-up. Нельзя обходить protection или публиковать незавершённый Gate.

C5 может начаться только отдельной задачей владельца от exact ACCEPTED/PUBLISHED
C4 SHA/tree. Его объём: operations/ingress/security, backup/restore, cleanup,
rollback и актуализация существующей единой инструкции по доказанному UI.
C6 завершит frozen release/activation/readback и owner acceptance целого MVP1.

**NO TAG / RELEASE / PERMANENT PRODUCTION DEPLOY. C5/C6 НЕ ЗАПУЩЕНЫ. MVP1 NOT READY.**
