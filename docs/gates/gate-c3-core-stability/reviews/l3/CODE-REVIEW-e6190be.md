# Независимый L3 recheck C3

**CODE ACCEPT** для `e6190be47b1e880c87304774455e773c83470338`, tree `8264efbcf3e610b4d57c747b4e21a45f4d98e348`. Итоговый Gate verdict пока не выставлен: требуется отдельный final freeze и проверка документации/переноса evidence.

Проверка выполнена в чистом detached L3 worktree. Код автора не менялся; reviewer записывал только свои probes и отчёты. Canonical dirty checkout не редактировался. Provider/model/ASR/external calls reviewer: 0. Исправления принадлежат root.

## Закрытие находок

| Находка | Независимое доказательство закрытия |
|---|---|
| C3-L3-01, Major, missing seal fail-open | `sqlite_store.py:1654` проверяет authoritative output_digest даже без seal; аналогичная проверка enqueue `:1836`. Нормализованный JSON answer входит в канонический message digest. Подмена bytes при удалённом seal отвергается; legacy без seal допустим только с тем же связанным answer. Собственный отрицательный probe проходит. |
| C3-L3-02, Major, stale effect authority | `durable_telegram_state.py:1000`, `:1037`, `:1054`: tenant/token/job kind и текущий lease проверяются на том же SQLite connection до/после CAS. Собственный probe содержит валидный capability_token, поэтому проверяет именно stale lease; NETWORK stub вызван 0 раз. После remote acceptance потеря authority не разрешает completion; UNKNOWN/reconciliation сохраняются. Транзакция не удерживается через await adapter. |
| C3-L3-03, Major, cold startup readiness | Исправленный probe с валидной конфигурацией независимо провален на 08cfff, проходит на fd5/e619. `CodexSdkAdapter.start` и Resilient.start готовят локальную protocol generation без model turn; control разделяет owned startup task. Исправление исходной неверной классификации приложено отдельно. |
| C3-L3-04, Medium, expiry while waiting SQLite lock | Реальные lock probes независимо провалены на 08cfff, проходят на fd5/e619 для part/whole/manifest. Проверка Core commit после ожидания lock также проходит; `sqlite_store.py:422`, `:424` вызывают guarded lease validation внутри commit boundary. Искусственный Clock.advance probe не засчитан. |
| C3-L3-05, Major, startup/shutdown ownership | На fd5 собственные extended probes: 2 FAIL / 2 PASS. На e619 все 4 PASS: pending initialization принадлежит close; public startup имеет deadline; отмена одного concurrent caller не отменяет shared start; late readiness не создаёт workers после close. `codex_sdk.py:169`, `:562` и `durable_product.py:419`. Дополнительно проходят resistant-startup, failed physical cleanup, repeated close и cancelled caller проверки автора. |
| Root R01, PARSING recovery | `gate5a4.py:1048`, `durable_product.py:543`, `:767`: interrupted PARSING получает durable FAILED без provider replay; ACK требует terminal state либо точную durable patch continuation. Регрессии recovery проходят. Обнаружение принадлежит root. |

## Выполненные проверки

- На fd5: собственные adversarial/real-lock probes **10 PASS**, 1 явно исключённый недостоверный Clock.advance probe; 20.87s.
- На fd5: целевые C3, queue/crash/effect/outbox, SDK, Mini App binding, voice retention и durable voice regressions **341 PASS**, 68.34s.
- На e619: собственные adversarial/startup/real-lock probes плюс repo startup/shutdown/SDK/worker-retry tests **85 PASS**, 1 исключённый Clock.advance probe; 33.92s. Единственный warning — deprecation Starlette/httpx, на исход тестов не влияет.
- Git HEAD/tree, чистота checkout и diff --check проверены. У source delta fd5→e619 только два файла: durable_product.py и codex_sdk.py; содержимое правки прочитано полностью. Тестовые/документальные изменения отдельно видимы в Git delta.

Проверки использовали pinned `.venv/Scripts/python.exe`, DEBUG=false, PYTHONPATH clean review checkout и отдельный basetemp. Точные воспроизводимые команды, SHA256 probes/logs/XML и counts находятся в `CODE-RECEIPT-e6190be.json`.

## Product quality и перенос evidence

Три настоящих synthetic ответа независимо оценены **15/15**, по 5/5 каждый: исходная цель, материал/ограничения, готовность результата, отсутствие неразрешённых действий, replay без дубля. Проверены исходные phase/transport/model receipts и artifact bytes: один ANSWERED result revision, один ACKed outbox, одна отправка answer/document, неизменный replay snapshot и 0 дополнительных model turns. Для voice подтверждены preview и отсутствие task/result/model turn до confirm; finished tombstone не является active job.

`PRODUCT-QUALITY-fd5f9ce.json` содержит 194 проверки квитанций и точные hashes. Исторические smoke относятся к fd5. Для 95 файлов source bytes сверены непосредственно; два startup файла связываются с fd5 через contemporaneous L2 receipt до их изменения. Смешанные line endings явно учтены; не заявляется raw-byte равенство LF review checkout и mixed-ending author checkout.

Перенос содержательной product quality с fd5 на e619 допустим: прочитанная source delta ограничена deadline, ownership и cleanup локальной protocol initialization. Prompts, model profile, permissions, tools policy, semantic compiler, effect capability и result generation не изменены. E619 не повторяет старый live smoke и не объявляется его исходной ревизией. Zero-turn real SDK startup/close выполняет и учитывает root; reviewer этого вызова не делал.

Ограничения сохранены: три synthetic случая; controlled separate-process restart, не hard kill; synthetic transport не доказывает exactly-once Telegram; indefinite cancellation-resistant third-party operation не объявляется успешно закрытой. Полный final gate требует exact docs/evidence freeze.
