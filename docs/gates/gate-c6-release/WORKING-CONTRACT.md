# Gate C6 — рабочий контракт выпуска MVP1

Статус: DRAFT / WIP. Владелец запустил C6 8 сентября 2026 года и принял полный GATE-C6-LAUNCH-PROMPT.md. Цель — постоянно работающие Telegram, Mini App и один локальный Core, сохранённые данные, проверенное восстановление и единая памятка.

База: published main `14d95b2001a4f49fb96a84e767cf62bbcf5dffdb`, tree `fdcc3537268df303a31faca1bd8499a126e87d09`. Неизменная приёмка C0–C5 сохраняется. Изменения только в `codex/mvp1-closure-c6-release`.

Риск высокий: схема, recovery authority и постоянный запуск. Приёмка: candidate-bound L1/L2/L3, migration/recovery/backup, реальные owner text/voice/Mini App/download journeys,15 минут наблюдения и явная owner acceptance. Source publication разрешена после PASS; переключение — после подтверждения единого точного activation plan; tag v1.0.2/release — после owner acceptance. MVP2, новые зависимости/инфраструктура, EULA от имени владельца, удаление прежних данных, запись памяти и публикация held docs15/16 исключены.

| Условие READY | Принятое доказательство | Текущий факт | Действие C6 | Проверка |
|---|---|---|---|---|
| Entry и WIP | C5 main/blobs/DOCX | Совпали;20 dirty paths сохранены | Отдельный worktree | CAS hashes и refs |
| Production | C5 explicit semantic ON, pinned CLI, C2 ASR | Live v1.0.1, tasks Disabled,poller0 | Activation plan | Exact roots/digests,local/public ready |
| Данные | C5 schema и DPAPI |79tasks,77receipts,15legacy,0jobs,884736B | Snapshot и миграция копии | Все прежние строки/связи |
| Recovery | C5 hold/data drill | Нет полного RTO/operator closure | Reconciliation и полный drill | ≤30мин,worker/ASR/result |
| Backup | RPO24ч,daily+pre-change,7daily/4weekly | Расписание выключено | Quiescent backup,managed retention | Реальный запуск и next run |
| Native | C5-R4 inventory | Production extended routes OFF;NVIDIA GPU есть | Достижимость и licence decision | Exact environment,официальные условия |
| UI | Retained C4 smoke | C6 journeys ещё нет | Матрица после активации | Text/voice/UI/download/acceptance |
| Памятка | C5 DOCX44591B/6стр | Hash совпал | Тот же документ,render | Manual QA и GitHub readback |

Первое чтение:4SQLite integrity OK,WAL0,свободно139.5GB. Репетиция на private ACL-копии:11 прежних таблиц сохранили все строки, новые schema/content проверки PASS,live bytes неизменны.2с не являются полным RTO. Локальные receipts находятся в ignored `.runtime`; публикуются только безопасные агрегаты и hashes.
