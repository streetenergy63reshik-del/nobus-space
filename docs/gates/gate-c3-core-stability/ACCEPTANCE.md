# Gate C3 — приёмка

**ACCEPTED / PASS / PUBLISHED / NOT DEPLOYED.**
Код принят на `b1ed94c6ddfefe957a50f4d133537f74482910cc`, tree `9acb41b5bf6d2a91b8964f84f4c459d072d0c127`. Итоговый пакет `e45a4d42bfac8b813b8e1d6e07d0df38baace8c2` принят отдельными L2/L3. Опубликовано обычным merge [PR #15](https://github.com/streetenergy63reshik-del/nobus-space/pull/15): `331f3566f03ae9ae5ede8cdc6b411f4102cc2e95`, tree `baedf0da25ab6e6599829684961b9f3c7dcf7570`. Код совпадает с принятым кандидатом; C4 READY TO START / NOT STARTED. Итоговый main после служебного PR фиксируется в локальном publication receipt и ответе задачи. Весь MVP1 ещё не READY; C4 не запущен.

Принятая задача сохраняет durable identity и контракт, восстанавливает sealed результат и отправляет только неподтверждённые части. Просроченные полномочия не позволяют записать результат или ACK; неизвестный effect не повторяется. Зависшие состояния становятся восстанавливаемыми либо честно требуют внимания. Локальный SDK имеет ограниченный запуск и сохраняет владение физическим запуском/закрытием при отмене.

База C2: `5fdc28ce66dbb072acd6676baf72fe58ae10b4b3`, tree `c8e756fb00874c5db2f6105c6d65154d0ed243e7`; branch `codex/mvp1-closure-c3-core-stability`. Повторной приёмки C0–C2 не было.

- [Exact проверки, расходы, история FAIL и независимые заключения](EVIDENCE.json), [L1](L1-VERIFICATION.json).
- [Manifest проверенного кандидата](MANIFEST.json) и [34 сценария отказов](FAILURE-MATRIX.md).
- [Настоящие text/voice/material ответы](PRODUCT-RESULTS.json): 3/3, независимая оценка15/15, replay без нового результата или model turn.
- [Reuse/gap](WORKING-CONTRACT.md), [failure/retry/recovery и invariants](RECOVERY-CONTRACT.md), [ADR0024](../../adr/0024-core-durable-recovery-and-part-delivery.md).
- [Единая передача C4](HANDOFF.md).

C0-F05/F06/F08 закрыты; у C0-F07 закрыта backend/recovery часть, live incident остаётся C5/C6. Окно Telegram accept до local receipt остаётся at-least-once. При неизвестной физической очистке SDK статус не считается успешным, новая generation запрещена. Проверки использовали синтетические данные; live DB, Telegram, deploy, tag/release и C4 не затрагивались. 19 посторонних WIP файлов и C2 worktree сохранены.
