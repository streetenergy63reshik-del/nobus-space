# Независимый L3: локальный кандидат C4

Проверяющий: `/root/resume_l3`, новая независимая identity. Профиль: software-development, HIGH, GATE_CANDIDATE.

**ACCEPT в проверенной локальной кодовой области и в проверенной области локальных run/replay receipts. Полный Gate C4 НЕ ПРИНЯТ.**

Кандидат `a869a691293e45a1a3e65303be627d684acfa16e`, tree `9a7cab97fb9947ebdfedeb5baffa57f9627a4c98`; опубликованная база C3 `b9283b3419928042c80278b5088b526edebab6e7`. Все 40 изменённых файлов совпадают с before/after manifest прежнего независимого reviewer, tracked status чистый. Все 97 source hashes локальных product receipts совпадают с текущими файлами.

Исторические 3 исходных probes, 5 cancellation attacks, 129 targeted regressions и 17 Node checks принадлежат `/root/c4_l3_review`, а не текущему reviewer. Их команды, результаты и привязка проверены; исторический REJECT и PAUSE-VERDICT сохранены без изменения. Подробные пути и SHA-256 включены в `LOCAL-RECEIPT-AUDIT.json`.

Собственные новые проверки: **7 PASS**. Восемь одновременных recoveries потребляют один credential ровно один раз; подмена tenant/context/key/digest записи отмены отклоняется; три последовательных восстановления не снимают запрет позднего create; bearer, истёкший при ожидании mutation lock, не создаёт journal row. Проверено на синтетической disposable SQLite только в текущей review-зоне. `test_resume_attacks.py`, `attacks.xml`, `attacks.log`.

Локальные real-provider run receipts проверены для 7 сценариев; 6 завершённых задач имеют успешный отдельный restart/replay без дополнительного model/ASR расхода. Сверены exact source binding, authoritative task/result revision/digest, сохранённые UTF-8 artifact bytes и их размер/хэш, synthetic Telegram document digest, подтверждённый outbox, ожидаемые HTTP ответы и cleanup. Проверены конечные тексты: direct/clarification дают запрошенный список, transform-text/voice возвращают переработанный промпт, не заявляют выполнения вложенных календарных/почтовых действий. Исходный sandbox DPAPI replay failure не переименован в PASS; для direct_text принят последний отдельный успешный receipt того же кандидата.

Новых воспроизводимых P0/P1/P2 в этой области не найдено. Проверены ADR 0025/0026, Core-owned generation/rotation, durable request journal, cancellation tombstone, read-only reconciliation, tenant/task/result/artifact scope и сохранение одного Core. Nobus Memory использована только как устаревший указатель через явно обозначенный filesystem fallback после `OBSIDIAN_NOT_RUNNING`; точный Git остаётся источником истины.

Данная проверка не выполняла model, ASR, сетевые, UI или live действия. Самостоятельных фоновых процессов reviewer нет. Browser/mobile/keyboard/light/dark, реальный owner-facing Telegram + Mini App и фактический rollback/readback пока не подтверждены этой проверкой. Временный helper/launcher имеет отдельный verdict; этот локальный ACCEPT не является разрешением его запуска и не означает C4 PASS, публикацию или готовность C5.
