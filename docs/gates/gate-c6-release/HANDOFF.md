# Gate C6: выпуск MVP1

**9 сентября 2026: SCOPED SOURCE CORRECTION PASS / ACTIVATION REWORK / NOT READY.** Исправление `b8e8ac41a401aa839710d7b11a72f76f02d97607`, tree `b715c699891d970bd1a0bb8a65d7d5fa85d54312`, прошло107 затронутых проверок и независимые L2/L3. [SOURCE-CORRECTION-01.json](SOURCE-CORRECTION-01.json) связывает точные bytes, отрицательный regression и границы verdict.

## Действующий результат

Исходный C6 source `3a5625898ce4f66ff39c85685e926ea1e0e8afa1` проверен2345PASS+25subtests, frontend20 и L2/L3; [SOURCE-ACCEPTANCE.json](SOURCE-ACCEPTANCE.json) сохраняет эту принятую историю. Package989417f опубликован обычным [PR21](https://github.com/streetenergy63reshik-del/nobus-space/pull/21), merge `7ea915790c382473378078065f0d7d3630fb56e6`. Это source publication, не финальный релиз продукта.

Владелец подтвердил точный C6-ACT-01 и локальное использование cuDNN9.10.2. Миграция сохранила79 задач,77 подтверждённых доставок и весь прежний inventory. Старые данные и зашифрованный snapshot сохранены; первая управляемая prechange копия мигрированного state прошла расшифрование/integrity. Live checkout сейчас7ea9157; main/health/backup установлены, все три задания Disabled.

## Обнаруженный отказ и исправление

Первый настоящий startup отдельного recovery drill завершился до readiness. Существующий Windows OpenSSH9.5p2 требует `PROGRAMDATA`: inherited environment даёт `ssh -V` exit0, принятый restricted environment —255 без вывода; добавление только этой переменной даёт0. Исправление сохраняет явный allowlist, точные SSH destination/flags, Job gating, cleanup и readiness.

Новый Windows integration test сначала воспроизвёл exit255, затем прошёл на изменённых bytes. Затронутый набор дал107PASS за67,50с; L2 независимо воспроизвёл actual offline owned SSH exit0/empty Job и исключение synthetic private env. L3 проверил границы и отсутствие ложного runtime PASS. Успешный `ssh -V` не является доказательством подключения relay, полного RTO или работающего продукта.

Failed drill сохранён. После STOP все строки восстановленной копии и production state, включая checkpoint, неизменны; порт/mutex свободны. Потраченный startup и консервативный model/ASR reserve не сброшены. Два ожидавших owner update из business_notes по отдельному разрешению архивированы DPAPI и подтверждены без исполнения/групповых ответов.

## Что требуется до READY

1. Опубликовать проверенное исправление обычным PR/merge; получить подтверждение только точного изменившегося deployment/config/drill target. Исходный activation plan и его receipts не переписывать.
2. Выполнить полный отдельный recovery RTO≤30мин с pinned worker/ASR и private owner result/TXT, сверкой после STOP; затем один production runtime, настоящий scheduled backup и controlled restart.
3. Пройти реальные owner text/voice/Mini App/download сценарии и ≥15мин наблюдения. Получить явную итоговую приёмку exact product release; до неё READY запрещён.
4. Перевести согласованные Scheduler определения в постоянную фазу, опубликовать v1.0.2 и необходимые final status-only docs, оставить продукт работающим.

[OPERATIONS](OPERATIONS.md) описывает миграцию/reconciliation/backup, [WORKING-CONTRACT](WORKING-CONTRACT.md) — границы. Политика: RPO≤24ч,7daily/4weekly, локальный DPAPI; защита от потери диска/Windows account не обещается. Hold не снимается ручным SQL, live DB restore не разрешён.

Единая Word-памятка на прежнем пути пока DRAFT: SHA256 `c52602089c6ca751101d4408f6f42de09a27e8b374b2d1d087da2901d8f3eeba`,44787B,6 страниц после render/visual QA; [MANUAL.json](MANUAL.json). Её команды и статус будут сверены с окончательным deployment до приёмки.

Неизменная C0–C5 приёмка сохраняется. [REWORK](REWORK.md) и прежние commits сохраняют историю исходных findings; новый failed startup не скрыт. Canonical20 WIP, held docs15/16 и history сохранены. Все работы остаются в одной задаче C6; MVP2 HOLD.
