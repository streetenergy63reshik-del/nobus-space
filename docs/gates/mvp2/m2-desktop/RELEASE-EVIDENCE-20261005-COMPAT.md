# M2-DESKTOP: восстановление связи с Codex Desktop, 5 октября 2026

**Статус к 17:15 МСК:** `READY_FOR_MANUAL_ACCEPTANCE` для владельца.
Ручные D02–D17 и показ плиток на его устройстве остаются `NOT_RUN`;
Gate/MVP2 `NOT_ACCEPTED`. Это новый выпуск после
[реального отказа](../../../incidents/2026-10-05-desktop-compatibility.md),
а не переименование доказательств прежней ревизии.

| Проверка | Связанное доказательство |
|---|---|
| Код | LIVE clean detached HEAD `17651308ce8a9d6a1f27199955b13f42de019978`, tree `f3d56b51d3e7abd554098b43a6a5d24d395b8521`; исходный кандидат — тот же commit. Числовой UIA pin удалён, точный Store package family и фактический InstallLocation проверяются при каждом действии. |
| L1 | Чистый короткий Git clone commit: `2975 passed, 3 skipped, 5 deselected, 25 subtests` за 514,10 с; JUnit SHA-256 `56f80c24c0ea9989defbb4f58143e2928ca720bbdb3f9a55efa52950ff0a7319`. Пять deselection — прежние исторические Gate C0/pre-Gate1 проверки другого среза; тесты production mutex выполнены с изолированным pytest namespace. |
| L2 | Другой чистый clone того же commit: `174 passed` за 59,55 с; JUnit SHA-256 `e548b9b297cc31f8196bb2f8bc157f84812acdbef8447f6ed3d4225a2b44ac58`. Набор охватывает IPC, UIA, bridge, меню, supervisor, runner, backup и документацию. Оба прогона дали одну известную Starlette/httpx deprecation warning. |
| L3 | Проверены ограничения package family/процесса, отсутствие координатного fallback, точный owner/thread/cwd до мутации, старый ход без `clientUserMessageId`, строгий отказ при явно некорректном поле и правило lost ACK без слепого повтора. Живой read-only UIA `Snapshot` вернул `26.930.4958.0`, `mutations=[]`; IPC прочитал полную историю. Нового блокирующего дефекта нет. |
| Перед сменой кода | Проверенный prechange backup `daily-20261005T164359-cd98c9e8f77f4c6d86cb270b118e7519`, четыре зашифрованные БД VERIFIED. Прежний signed journal `complete`, digest `sha256:58983d69294cd148a4a916fc77912e59ab894d901f674c8c0aa75d75dce75542`. XML трёх Task, config и launcher сохранены в новом приватном rollback-каталоге с SHA-256; source LIVE был чистым на `9aeff52`. |
| Переключение | Admission hold → штатный STOP → отсутствие точных процессов, listener и mutex → три Disabled Task → clean LIVE checkout нового commit → новый backup config digest `sha256:ad3f5fdb8a88f67c809dd9ccb5f33b8b6aa61db505d587ebfbabca64e009f2ec` → signed activation rebind head `sha256:183c51fb6cf26d0d43eaf592bb1813ab4d412676207201c95de09c47ba0f6202`. Старые файлы и БД не удалялись. |
| Коррекция запуска | Первый Main завершился 75 до запуска runtime: Backup Task оставался Disabled. Signed journal был в `starting`, recovery head не менялся, listener и дочерние процессы отсутствовали. Точный Backup Task включён, binding вновь проверен `PASS/new`, затем Main запущен **один раз**; тот же backup cycle завершился `PASS`, `quarantined=0`. |
| Новый backup и службы | Generation `daily-20261005T165917-40954f964ca04e1d8415639ad7e9b22f`, четыре зашифрованные БД VERIFIED, source commit `1765130`. Signed journal `complete` digest `sha256:1509924a4c50f935215cd52a0f207fae2f464d435ef7c79b184908ea7271610a`. Admission hold снят, Main Running; Main/Health/Backup Enabled; плановый Health result 0 в 17:15 МСК; local/public `/readyz` PASS. |
| Сохранённый запрос | Telegram source message 3029, request `e2864d25-51a9-4b2b-897c-e99ec2090416`, проект `HomeEdit`, точная задача `01a0848d-9432-74c1-800e-13a35882b26f`. До восстановления запись `failed`, Desktop turn пуст; owner/cwd совпали, в четырёх старых ходах нет его `nobus:` ID. Прежний отказ произошёл в парсере до `start_turn`. CAS перевёл **одну** запись в `waiting_pc`; watchdog создал единственный turn `01a10c69-55cb-7d02-869c-0a98e0cb4e19`, после чего запись `delivered`. |
| Telegram | Для этого request единственная delivery-строка: `kind=text`, `ordinal=0`, `status=sent`, Telegram message **3043** в исходную тему. Текст промта и результата в доказательства не копировались. Старую D03 и два исторических `unknown_dispatch` не запускали. |

Будущее обновление числа сборки Codex Desktop само по себе не требует выпуска
бота. Если изменятся смысловые UI-контролы или приватный IPC-контракт,
маршрут останавливается до адресного исправления. Ежедневная проверка
стабильности может сообщить о таком отказе; менять константу версии ей не
нужно. Для ручной проверки владельца действует
[инструкция D02–D17](../M2-DESKTOP-MANUAL-ACCEPTANCE.md) с меткой
`UAT-20261005-02`.
