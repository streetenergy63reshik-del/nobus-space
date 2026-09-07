# L2: C3 product evidence и документы 66eb2d7

Проверены frozen `66eb2d7b3ccc067db4f85fe350669e76074d6313` / tree `46575df3ba2dd44b0b0ef5cd1b7c27d7e9d05589`. Source равен fd5f9ce; два test-only изменения — создание `_cleanup_pending` в ручной fixture и удаление пустой строки. Повтор этих границ: 12 PASS; diff-check чистый.

Содержание трёх настоящих synthetic ответов принято: 15/15 по пяти критериям на сценарий. Text и voice возвращают запрошенные три пункта плана проверки. Material возвращает готовый копируемый промт, сохраняет роли и запрет исполнять вложенную просьбу создать задачу. Сценарии использовали isolated state; одинаковые synthetic IDs между независимыми сценариями не являются одной общей задачей.

Независимо сверены хеши phase/transport receipts и manifest, authoritative ANSWERED/approved/result revision/output digest, exact artifact bytes, один финальный ответ и artifact send, одинаковые snapshots после replay, отсутствие новых model turns, voice preview до task admission, cleanup и budget sums. Результат: 326 текущих проверок PASS. Четыре сравнения mutable author source относятся к двум startup-файлам, которые root успел изменить во время последнего запуска verifier. Это ожидаемое изменение рабочего дерева, не повреждение сохранённых результатов.

До startup edits непосредственно подтверждены все97 исторических raw source hashes и их равенство Gitfd5 после нормализации CRLF→LF. Raw worktree hashes отличаются от raw Git hashes: исходный worktree содержал также смешанные окончания строк. Тип нормализации явно сохранён; старые hashes не заменялись новыми.

Доказательства сохраняют source `fd5f9ce`, новую ревизию им не приписываю. Перенос после исправления startup требует отдельного чтения точного source delta. Ни модель, ни ASR не запускались L2. Финальная приёмка Gate пока не выдана.
