# Независимая L2 проверка C3 — CODE REJECT

Проверены commit `08cfff031803211334f6da9da377b18226c5a393` и tree `fa265fb5a0c792ba342db025e1ecf584614cf36f` в отдельном чистом detached worktree. Исходный код и документы не изменялись. Финальное заключение по Gate ещё не выдано: исправленный код и окончательная заморозка документов/доказательств потребуют отдельной точной привязки.

Результаты: 805 тестов прошли, 15 завершились ошибками тестовых fixtures; четыре независимые пробы выявили две ошибки исполнения. Пропусков платформы нет. 30 проверок входной базы C2, ancestry, product bytes, принятых C0/C1 контрактов и хешей прежних L1/L2/L3 receipts прошли. Повторная приёмка C0–C2 не проводилась.

## Блокирующие findings

- **ISSUE-C3-L2-01, Major, IMPLEMENTATION_DEFECT.** `src/storage/sqlite_store.py:2207`, `:2243`, `:2272`: время lease берётся до ожидания write lock. Реальная блокировка SQLite на 1,3 секунды при lease 1 секунда позволяет записать manifest, квитанцию части и whole ACK после expiry. Нужны проверка trusted effective time после lock и единая граница для claim/manifest/part/whole receipt. Доказательство: `expiry-output.txt`, три failed-пробы.
- **ISSUE-C3-L2-02, Major, IMPLEMENTATION_DEFECT.** `src/application/durable_telegram_state.py:86`, `:217` и `src/application/durable_runtime.py:546`: guard удерживает queue lock, но проверяет expiry до ожидания второго, Core lock. Production `_record_worker_result` сохраняет sealed answer/event после expiry. Проверка с lease 5 секунд, ожиданием 4,2 секунды и отдельной Core-блокировкой 1,3 секунды это воспроизводит. Нужна повторная проверка той же authority внутри actual Core transaction до commit с rollback. Доказательство: `core-lock-v2-output.txt`.
- **ISSUE-C3-L2-03, Major verification blocker, VERIFIER_DEFECT.** Пятнадцать старых fixtures используют `object.__new__` и не создают `_cleanup_pending`; ошибки закрывают прохождение C2 TTL/failure и queue/Mini App регрессий. Исправлять fixtures, сохранив исходные assertions. Доказательство: `target-output.txt` (452 passed / 15 failed).
- **ISSUE-C3-R01, Major, IMPLEMENTATION_DEFECT.** Подтверждено чтением source и root phase snapshot: после controlled restart Core остаётся PARSING без job/result/outbox. L2 не расходовал model budget и не выдаёт root smoke за свой запуск. Безопасный Core-owned FAILED/outbox для прерванного PARSING соответствует контракту actionable recovery; queue ACK должен требовать authoritative terminal result.

Дополнительные C1 semantic / C2 smoke guards / Mini App result regression: `semantic-v2-output.txt`, 353 passed. Полный manifest команд, хеши, точные counts и сохранённые ошибки самих проб — в `REPORT-08cfff0.json`. Проба `.runtime/l2/probe_expiry.py` остаётся в review worktree; её SHA-256 записан в JSON.

Ни одна модель или ASR не вызваны, внешние действия не выполнялись. Синтетическая доставка не доказывает exactly-once Telegram. После исправления нужен новый exact candidate; прежний REJECT сохраняется.
