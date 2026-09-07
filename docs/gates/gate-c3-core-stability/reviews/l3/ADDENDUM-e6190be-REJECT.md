# Дополнение: e6190be отклонён после проверки физического startup

**Текущий verdict — CODE REJECT** для `e6190be47b1e880c87304774455e773c83470338`, tree `8264efbcf3e610b4d57c747b4e21a45f4d98e348`. Это дополнение заменяет прежний итог CODE ACCEPT в `CODE-REVIEW-e6190be.md` / `CODE-RECEIPT-e6190be.json`. Первоначальные отчёты и их 85 PASS сохранены без переписывания. Gate ACCEPT не выдавался.

L2 обнаружил Major ISSUE-C3-L2-04. L3 прочитал точную границу установленного SDK и независимо повторил копию его offline probe: `e619-thread-start.log/xml`, **1 FAIL**, 0.83s. Исходник probe — `sdk_thread_start_probe.py`; Popen заменён инертным stub, настоящего процесса, model turn или ASR не было.

В установленном `openai_codex/async_client.py:88` start ждёт sync method через фоновый thread; `client.py:259` публикует `_proc` лишь после возвращения Popen. При deadline отменяется asyncio await, но thread продолжает работать. Очистка `client.py:275` видит `_proc is None`, возвращает успех, и adapter.close также объявляет успех. После этого stub Popen возвращается и оставляет опубликованный незавершённый процесс без владельца. Assert проверяет именно эту последовательность после успешного close.

Owning boundary проекта: `src/workers/codex_sdk.py:169` (timeout around startup), `:548`, `:562` (discard/close starting client). Async deadline и ownership shared control task устраняют часть C3-L3-05, но не владение физическим запуском pinned SDK. Нужны сохранённый владелец позднего результата startup, запрет новой generation до завершения/надёжной изоляции и правдивый close outcome. Исправление делает root; reviewer source не меняет.

Содержательная product quality 15/15 трёх fd5 synthetic результатов и проверенные transport/replay receipts не аннулируются. Они не доказывают корректность физического startup e619. Повтор code review и explicit evidence transfer возможны после новой frozen revision.
