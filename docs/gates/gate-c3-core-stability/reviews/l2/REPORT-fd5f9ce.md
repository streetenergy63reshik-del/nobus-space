# C3: независимая L2 — CODE ACCEPT

Проверены `fd5f9cefb64a192f0de02db314b469915bc4e6f6` / tree `65c3230bceeca7cae7fd3d9e902eae1887f0fb3f` в чистом detached checkout. Код автора не изменялся. Итоговый Gate пока не принят: остаётся точная проверка окончательных документов, доказательств и двух небольших test-only изменений.

- **L2-01 CLOSED:** прежние независимые пробы с реальной SQLite-блокировкой теперь отклоняют запись manifest, part receipt и whole ACK после expiry. Проверка использует trusted server timestamp плюс фактически прошедшее monotonic время после получения lock и перед commit.
- **L2-02 CLOSED:** прежняя проба второго Core lock проходит; result/event/seal transaction повторно проверяет authority через уже удерживаемое queue connection и откатывается при expiry.
- **R01 CLOSED:** независимая probe_completion подтверждает отказ completion guard для PARSING; восстановление даёт FAILED, result0, outbox1 без worker replay, второй restart ничего не меняет.
- **Прежние 15 ошибок fixtures закрыты.** Расширенная регрессия: 838 PASS / 1 FAIL. Единственный FAIL — ещё не вошедшая в fd5 и уже исправленная у root fixture `tests/test_runtime_operations.py:87`, где отсутствует `_cleanup_pending`. На финальном freeze нужна её повторная проверка.

Проверка исправлений и защищённых result/effect bindings: 23 PASS. Дополнительная независимая completion-проба: 1 PASS. Это отдельные запуски с частичным пересечением, не число уникальных тестов. Пропусков нет; настоящая модель и ASR не вызывались.

`git diff --check` отмечает лишнюю пустую строку `tests/test_c3_outbox_clock.py:82`; root сообщил о её нормализации для final freeze. Это форматирование, не ошибка product source.

30 прежних exact C2 entry проверок остаются валидны: C2 — ancestor, C0/C1/C2 документы и evidence bytes между08cfff иfd5 не менялись. Старые reports/FAIL не переписаны. Команды, counts, SHA-256 и точные ограничения — `REPORT-fd5f9ce.json`.

Окончательный L2 verdict будет привязан к final candidate после проверки source equality, fixture, документов и фактических smoke receipts. Синтетический транспорт не доказывает exactly-once Telegram; deploy/live/C4 не выполнялись.
