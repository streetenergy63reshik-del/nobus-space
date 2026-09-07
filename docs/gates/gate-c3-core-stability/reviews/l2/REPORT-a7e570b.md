# Независимая L2: CODE REJECT

Exact `a7e570bb084ea0324f05b1ec80328c72372a6858`, tree `2189ba333ad686be8e5ad42f6ee4dc553eeadf19`. Код автора не изменялся.

**L2-04 закрыт:** две независимые пробы actual SDK с delayed Popen и blocked threaded initialize теперь проходят. Startup остаётся учтённым, закрытие не заявляет успех при неизвестном исходе, поздний процесс очищается автоматически. Прежние 2 FAIL на e619 сохранены. Startup/shutdown/SDK/retry/smoke/runtime_operations вместе с этими пробами: **96 PASS**; отдельные author physical-start tests: **4 PASS**.

**ISSUE-C3-L2-05, Major, IMPLEMENTATION_DEFECT:** `src/workers/codex_sdk.py:531` отменяет await SDK close на timeout; повторное закрытие на строках 443/468 способно ошибочно подтвердить успех. Установленный SDK выполняет close через `asyncio.to_thread` и присваивает `_proc=None` до stdin.close/terminate. Второй close видит None, возвращает success и снимает учёт клиента, хотя первый физический поток ещё не остановил процесс.

Независимая probe_sdk_physical_close использует настоящий код SDK и безопасную заглушку процесса. При блокировке stdin.close adapter.close вернул успех до terminate: **1 FAIL**. Нужен один сохранённый shielded close на поколение; повторный no-op не может доказывать завершение прежней операции.

Все проверки offline, 0 model/ASR/external effects; пропусков нет. Прежние Core/queue/C1/C2/result/outbox/artifact/effect доказательства переносятся только на неизменные области. Startup/shutdown verdict не переносится. Команды, counts, hashes и границы исправления — в JSON рядом. Исторические FAIL сохранены.
