# Gate C6 Подготовка выпуска MVP1

**9 сентября 2026: CANDIDATE WIP / NOT READY.** C6 выполняется в одной задаче владельца. Source publication, activation, реальные owner journeys, окончательная приёмка и v1.0.2 release пока не выполнены. MVP2 HOLD.

Entry: опубликованная main `14d95b2001a4f49fb96a84e767cf62bbcf5dffdb`, tree `fdcc3537268df303a31faca1bd8499a126e87d09`. C5 source/package, PR19/20, blobs передачи/приёмки и исходный Word hash совпали. Неизменная приёмка C0–C5 сохраняется.

Рабочая зона — `codex/mvp1-closure-c6-release`, отдельный `Code/worktrees/mvp1-closure-c6`. Canonical WIP содержит 20 сохранённых paths; held docs15/16 не импортируются. Live v1.0.1, соседние worktrees, refs, credentials, Bot/menu/webhook и внешняя инфраструктура не менялись.

## Проверяемый результат

- Совместимая миграция всего inventory, зашифрованные исходные bytes, новый auth cutoff и точное восстановление старого формата в новый каталог.
- Owner-confirmed reopening после restore только при доказанном отсутствии post-snapshot delta; atomic hold/audit и replay protection.
- Quiescent daily backup, authenticated latest, 7daily/4weekly retention через обратимый карантин, bounded Scheduler cycle и явный повтор после ошибки.
- Запрет нового admission при старой/непроверяемой копии и нехватке места; профиль передаёт backup root/ownership явно.

Подробности и команды — [OPERATIONS](OPERATIONS.md). Границы результата — [рабочий контракт](WORKING-CONTRACT.md).

## Фактические проверки WIP

Целевые наборы: 84 PASS после первого checkpoint; затем 82 PASS обновлённых backup/recovery/operations; 63 PASS затронутых Mini App/queue после исправления fixtures. Это пересекающиеся наборы, их не складывают. Frontend — 20 PASS, bytes интерфейса не изменены.

Продукционный migration CLI на защищённой копии фактического live сохранил все 79 задач и прежние receipts/legacy. Из оригинального encrypted snapshot восстановлены точные bytes; исходный v1.0.1 storage прочитал 79 задач. Live source unchanged. 10,047 секунды не являются полным RTO.

Первый широкий regression остановлен после массовых FAIL; отдельно воспроизведён 503 в `test_c3_multipart_input`. Причина — fixtures создавали control plane через `object.__new__`, минуя новый optional callback конструктора. Обновлены 22 тестовых объекта; проверка production не ослаблена. Исходные FAIL сохранены. Повтор дал2227PASS/101FAIL: оставались fixtures с `__class__` и alias-конструктором и ожидаемый список SQLite tables без новой таблицы. Они исправлены; scoped source/recovery набор дал135PASS/1 fixtureFAIL, последний shared lifecycle fixture исправлен. Ни один failed тест не исключён. Полный прогон 9245768 дал 2330 PASS, 25 subtests, 2 skipped и 2 исторических deselected за 263,70 с. Независимые L2/L3 выявили два P1 и один P2 в backup cycle; исправления описаны в [REWORK](REWORK.md). После исправлений целевые наборы дали 36 PASS и затем 58 PASS; это пересекающиеся проверки. Новая ревизия требует собственного полного L1 и независимого readback.

Historical исключения сохранены из C5: `tests/gate0`, `test_gate_c0_governance.py` и два sealed/held-document assertion в `test_pre_gate1_architecture_integration.py`. Они не проверяют новые C6 возможности и не служат обходом нового FAIL.

## Открытые обязательные условия

1. Полный релевантный regression, compile/PowerShell/security/manifest/links и независимые L2/L3 по замороженному кандидату.
2. Решение владельца по локальному использованию cuDNN 9.10.2 EULA. NVIDIA RTX3050Ti на ПК подтверждена, но соглашение за владельца не принимается; реальные ASR пробы не запускаются до ответа.
3. Полный recovery RTO с настоящими pinned worker/ASR и результатом; точные runtime/native conditions.
4. Word обновлён на том же пути; все6 страниц последней редакции прошли visual QA. Hash `c52602089c6ca751101d4408f6f42de09a27e8b374b2d1d087da2901d8f3eeba`,44787B. Зависание экспорта локализовано во вложенном Windows PowerShell5; тот же helper через PowerShell7.6.5 STA успешно отрисовал документ. [MANUAL.json](MANUAL.json) сохраняет исходные FAIL и итоговые hashes. Содержимое остаётся DRAFT до активации и owner acceptance.
5. После candidate PASS — разрешённые push/PR/normal merge/readback, один точный activation plan и подтверждение владельца. Затем действующий backup task, постоянный runtime, public ingress/readiness и controlled restart.
6. Реальные owner text/voice/Mini App/download journeys, ≥15 минут наблюдения и явная итоговая owner acceptance. Только после неё tag/release v1.0.2 и final status-only docs/readback.

Последний live preflight: main/health Disabled, poller0, порт8765 свободен, прямой публичный `/readyz`502. Source merge сам по себе не изменит это состояние. Финальный READY пока запрещён.
