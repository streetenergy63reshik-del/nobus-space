# M2-DESKTOP: убрать ложное предупреждение и служебные сообщения, 5 октября 2026

**Состояние на 19:54 МСК:** исправление работает в LIVE; техническая
готовность к ручной приёмке восстановлена. Полные D02–D17 и Gate/MVP2
остаются открытыми. GitHub `main` не обновлялся; кандидат опубликован в
[draft PR #41](https://github.com/streetenergy63reshik-del/nobus-space/pull/41).

| Область | Проверенный результат |
|---|---|
| Код | LIVE clean detached HEAD `207778aea06869735bef97d58651c0ac117c3ed5`, tree `7e62ed5ccde68163cecff01e59da1606b2da5c53`. От предыдущего LIVE `1765130` до кандидата нет удаления tracked-файлов. Новых зависимостей и схем БД нет. |
| Причина | После принятия поручения одна временная ошибка IPC переводила запрос в `waiting_pc` и сразу отправляла «Codex Desktop сейчас недоступен». Watchdog затем восстанавливал тот же запрос. Теперь такой переход не отправляет ложное предупреждение; проверка доступности до входа в меню и при выборе кнопок сохранена. |
| Очистка | Bridge сохраняет в зашифрованной записи точные ID своих временных карточек и квитанций. После `delivered`/`delivery_partial` удаляет их через существующий Telegram `deleteMessage`; неудачное удаление повторяется. Входное сообщение и итоговые delivery-квитанции исключены из набора удаления. Отказ и неизвестный исход оставляют диагностику. |
| L1 | На чистом clone точного commit: `2980 passed, 3 skipped, 5 deselected, 25 subtests` за 552,00 с. Пять deselection — известные исторические Gate C0/pre-Gate1 тесты другого среза. JUnit SHA-256 `084587b4afe1ee32fe2e8a1b06d9d0c995f57b3c5dfa244e78cc37985068391f`. |
| L2 | На другом чистом clone точного commit: `388 passed` за 107,55 с. Набор охватывает bridge, меню, IPC/UIA, Telegram API, output, supervisor, backup и no-delete границы. JUnit SHA-256 `e202f101a223197900dae0ba68d11330e63a0455d402424438c495f03f798364`. В обоих прогонах одно известное предупреждение Starlette/httpx. |
| L3 | Прочитан diff и проверены точная привязка временного ID к request/chat, запрет записи source/result ID, исключение внутреннего поля из ingress-idempotency, завершённое и частичное состояния, восстановление после сбоя удаления и отсутствие нового Telegram task/desktop turn во время выпуска. Блокирующих замечаний нет. |
| До переключения | Штатный prechange backup: signed journal `complete`, digest `sha256:4069268dcdb25f5e42f3b5b25bbfd4dc0bf9537d1ba54434c2986716bdd57d3c`, generation `daily-20261005T193208-b4c07546bf5249098f72ec846ee4999d` — `VERIFIED`. Старый LIVE clean, Main Running, local `/readyz` HTTP 200. |
| Rollback-снимок | В приватном `.runtime/m2-desktop-cleanup-release-20261005/` сохранены прежний backup config, Health launcher и XML трёх Task через создание новых файлов с readback SHA-256. Действующий после prechange backup Health XML имеет `sha256:9e3dd9488220d97af1ec7ca20e4ccc0eb75fc77ea38f062ec5610b3046969f11`; начальный снимок Health во время цикла отдельно сохранён как история. Main XML `sha256:fa89ad6c83b0a738f4debf655c0bc296aeafbabb004f05990a6d982a34cdf73c`, Backup XML `sha256:b8f4cecf8834ec03ad038482a6118e897f20843f3751dbe3c51f7f77508a3d5d`. |
| Переключение | Admission hold → штатный STOP → Main Ready/result 0 → три Disabled Task → exact production process/listener absent → clean checkout `207778a`. Новый O_EXCL config digest `sha256:06742c5b268c1dd892e570fabef743ceba921491afc2b28e05752ef885092969`; Backup Task поставлен в Disabled profile после успешного `-WhatIf`. Signed recovery rebind от `sha256:a627de8503801e8e57346750690f420f6e1dcd51c4b9d8645dee969ba1600ec8` к `sha256:f3e50942f9cfd1dcdaedf18264497f9d8779fe9a54219f5500c8962211cc2274`. |
| Новый цикл | Backup Task включён до запуска Main. Один `--reconcile-complete-digest` от прежнего `sha256:4069268...` завершился `PASS`, `quarantined=0`, `runtime_ready=true`; generation `daily-20261005T194843-301dcffd41544f3ba2d2e3be5d34778e` прошла проверку подписанного inventory, backup `VERIFIED`. Новый signed journal `complete`, digest `sha256:011518ce98ed4b5b8b009c5241a852196000ff166aa0332a969b653b353c7953`. |
| Работа служб | Main Running; Main/Health/Backup Enabled, Health last result 0. Локальный и публичный `/readyz`: HTTP 200 с точным `{"status":"ready"}`. LIVE checkout остаётся чистым на указанном SHA. |
| Старый диалог | Владелец подтвердил, что нужный файл **получен**; подпроверка отправки файла — **PASS**. Read-only bridge-запись request `3d3d3129-7f33-468c-9e8d-a1d2f18e385c` при этом остаётся `delivery_partial`: source 3049, текст 3052, технический manifest 3053; способ фактического получения файла этот ledger не устанавливает. Bot API под подтверждённой личностью `@Nobusspacebot` удалил только служебные 3047, 3048, 3050, 3051, 3053. Сообщение владельца 3049 и итоговый текст 3052 не удалялись. |

Нового поручения в Codex для проверки автоматической очистки не создавали:
эта функция проверена кодовыми сценариями и точечным вызовом Telegram API,
её поведение на следующем живом завершённом запросе остаётся ручным
наблюдением. Успешные подпроверки меню, продолжения задачи, текстового
ответа и **получения файла** внесены в
[инструкцию владельца](../M2-DESKTOP-MANUAL-ACCEPTANCE.md).
Полный D10 по двум заданным файлам, хэшам и replay ещё открыт; D02–D17
в целом не приняты. Старую завершённую D03 не запускали.
