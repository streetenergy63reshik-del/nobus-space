# M2-DESKTOP: технический выпуск плиточного меню, 5 октября 2026

**Статус:** `READY_FOR_MANUAL_ACCEPTANCE`, D02–D17 и живой сценарий плиток
владельцем `NOT_RUN`; Gate/MVP2 `NOT_ACCEPTED`. Данные получены к 14:38 МСК.
Это запись выпуска к ручной проверке, а не свидетельство её прохождения.

| Связка | Точный результат |
|---|---|
| Кодовый кандидат и LIVE | `9aeff52c3d11e895e048bb496cdaa6c17845b057`, tree `5c9ba94fd72fbf7e6e655eddc7b8329346f8df92`; LIVE checkout чистый на том же commit |
| L1 | Отдельный короткий чистый Git clone этого commit: `2969 passed, 3 skipped, 5 deselected, 25 subtests`, 547.04 с, одна известная Starlette/httpx warning. JUnit SHA-256 `1371e36ba864a3134a4b32ea4c81f79e53454845be87f64f19d5753f7fffe757`. Пять исключений — исторические Gate C0/pre-Gate1 про другой статус/манифест, их имена сохранены в [журнале](AUDIT-JOURNAL.md). Mutex-тесты прошли в этом прогоне при остановленном боте |
| L2 | Другой чистый Git clone тех же commit/tree: `332 passed, 3 deselected`, 105.32 с, та же warning. Три deselection касаются глобального production mutex и были включены в L1. JUnit SHA-256 `92293c98728935a21dcf886866b8f6371ba167c78849d0cee509dfa2fcae30d` |
| L3 | Адресная неблагоприятная проверка callback `user_id`/`chat_id`/topic, привязки выбранного проекта по ID и корню, точной SQLite-миграции, backup и сохранения launcher при ошибке staging: нового блокирующего дефекта не найдено. Не является живым D02–D17 |
| Application binding | Новый config digest `sha256:b13a0e1797d6a67cc96becd90a9f6bf9fff89c2dddcba1a25bb11da60ca923de`; signed rebind head `sha256:7f9aa3f43f177b4bc0fd192ae382d47824c57e488039cae074ccae899db55162`, inspect `PASS/new` |
| Backup | Один exact reconcile прежнего complete digest; PASS, `quarantined=0`; generation `daily-20261005T142552-830340671ad3415581725e9209636bcb`; новый complete journal digest `sha256:31fa08560d03de81b4a9dc6c5cce11d51331445346905611df1f730fc2e9d2a5`; четыре зашифрованные БД VERIFIED, новая SQLite-схема 18 объектов, hold=false |
| Службы и сеть | `NobusSpaceBot` Running/Enabled; `NobusSpaceBot-Health` Ready/Enabled, последний result 0 в 14:35 МСК; `NobusSpaceBot-Backup` Ready/Enabled. Локальный `/readyz` с точным Host и публичный `https://app.nobusspace.com/readyz`: HTTP 200, тело `{"status":"ready"}` |
| Codex Desktop | Работающий процесс владельца; IPC `connected=True`; свежий read-only каталог: 11 локальных проектов и 3 задачи `nobus-orchestrator-dev`. Никакой Desktop turn не отправлялся для этой технической проверки |
| Telegram | `configure_telegram_profile.py --apply`: PASS; последующий read-only `getMyCommands`: `start,codex,status,limit,help`. Это проверка профиля и доступности API, не живая приёмка маршрута |
| Видимая кнопка | 05.10, 15:12 МСК: один `sendMessage` с постоянной `ReplyKeyboardMarkup` и кнопкой `/codex@Nobusspacebot` принят Bot API как message `3024` в chat `-1004417194376`, topic `91` («Codex work»); текст и target сверены по ответу. Реальное отображение и нажатие клиентом ещё `NOT_RUN` |
| Состояние очередей | Runtime-set PASS; desktop requests: 3 delivered, 2 исторических `unknown_dispatch` без повтора; 0 новых меню и 0 Telegram jobs на момент readback |
| Возврат | Прежний рабочий commit `4db5f0e9266637feca408a57aa0c8e8ac580dbc0` сохранён в `codex/nobus-before-m2-menu-20261005`; старые Task XML, launcher, backup config и signed journal скопированы в игнорируемый release-каталог. Основные БД и резервные копии не удалялись. При штатной остановке SQLite убрал только отдельно разрешённые `-wal`/`-shm` sidecar |

Профиль зависимостей, CVE и ограничения задокументированы в
[SECURITY-TRIAGE-20260924](SECURITY-TRIAGE-20260924.md). `pip check` PASS;
в окружении остаются известные advisories для `pip 25.0.1` и
`urllib3 2.7.0`; обновление пакетов не выполнялось из-за запрета на
удаление старых файлов вне временных тестовых каталогов. Возможность
кратковременной недоступности и точная причина прежнего STOP не устранены
одной успешной проверкой.

При закрытом Codex Desktop работающий бот должен отвергать каждое действие
меню с сообщением «Codex не активен на ПК». При полном выключении этого ПК
сам бот также не работает и немедленно ответить в Telegram не может; для
такого ответа нужен отдельный постоянно работающий внешний контур. Это
явное архитектурное ограничение для оценки владельцем.

`main` и релизный тег не обновлялись. Код опубликован в ветке
`codex/m2-desktop`, [draft PR #41](https://github.com/streetenergy63reshik-del/nobus-space/pull/41).
Документы после `9aeff52` могут получить отдельный docs-only commit; L1/L2
относятся к точным bytes `9aeff52` и не переносятся на другой code tree.
Следующий шаг — результаты владельца по
[инструкции D02–D17](../M2-DESKTOP-MANUAL-ACCEPTANCE.md) и меню, затем
исправление подтверждённых дефектов с затронутыми повторными проверками.
