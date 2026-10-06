# Nobus Space — действующая передача оператору

6 октября 2026. Начать с [CURRENT](CURRENT-STATUS.md) и фактических аргументов трёх задач Планировщика. LIVE чистый на `207778aea06869735bef97d58651c0ac117c3ed5`; после утреннего STOP работает с 11:40. Последняя полная read-only проверка — 12:27: одна цепочка Core/relay, local/public 200, Health 0, четыре БД/effects PASS, backup complete/VERIFIED, hold=false.

Публикация именно этого кода оформлена в [PR №42](https://github.com/streetenergy63reshik-del/nobus-space/pull/42). Документация поверх него не меняет исполняемый source и activation binding. Проверять слияние по GitHub; старый тег v1.0.2 не является версией действующего бота.

## Сохранённые границы

- [MVP1/M1-S1 принят 19 сентября](../gates/mvp1-maintenance/REPAIR-ACCEPTANCE.md); NOT PASS прежнего 72-часового окна сохраняется.
- Desktop bridge установлен, владелец подтвердил отдельный рабочий путь; весь D02–D17/MVP2 не объявлен принятым. Старые M2-G0…G4 не запускать.
- [Артуры используют существующий `/codex`](../CODEX-AGENT-COMMANDS.md). Отдельный HTTPS/PC-channel кандидат `1b6af61` не опубликован и не активирован; исходная незавершённая работа сохранена.
- Два исторических Desktop unknown_dispatch и одна delivery_partial не повторялись. Нет новой status-команды и полного машинного request ID на каждом файле.
- Runtime, точный вложенный StateRoot, четыре БД, копии, history, .venv, закреплённый Python и ASR защищены. [Реестр каталогов](WORKSPACE-INVENTORY.md), [результат уборки](REPOSITORY-MAINTENANCE.md).

## Следующий шаг при отказе

Разрешено только штатное восстановление по действующему поручению владельца: сверить установленный source/config/binding, фазу текущего backup, подлинную свежую копию, history/digest, отсутствие старых процессов/lease и данные/effects; затем точный inspect/ack и один Main либо продолжение уже ожидающего цикла. Backup перед Main должен быть Enabled/Ready. Не удалять history, не обходить binding, не откатывать БД. При активном starting ничего не acknowledge. Telegram-тест требует отдельного разрешения на отправку.

Последние причины и неизвестные — [каталог инцидентов](../incidents/README.md). Историческая передача архитектору сохранена [в Git на 207778a](https://github.com/streetenergy63reshik-del/nobus-space/blob/207778aea06869735bef97d58651c0ac117c3ed5/docs/handoffs/ARCHITECT-HANDOFF.md); прежние команды из неё не являются текущим поручением.
