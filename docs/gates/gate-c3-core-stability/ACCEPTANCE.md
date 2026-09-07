# Gate C3 — приёмка

**DRAFT / NOT ACCEPTED / NOT DEPLOYED.** Идёт проверка цельного кандидата.
Публикация разрешена владельцем только после итогового PASS. C0–C2 не
принимаются повторно, C4 не запускается. Весь MVP1 ещё не READY.

Цель: задача принимается durable, восстанавливает свою identity и результат,
не повторяет подтверждённые части доставки и сообщает правдивое состояние.
Переиспользуются существующие Core, SQLite, SDK, outbox и artifact contract.

Опубликованная база C2: `5fdc28ce66dbb072acd6676baf72fe58ae10b4b3`, tree
`c8e756fb00874c5db2f6105c6d65154d0ed243e7`.
Ветка: `codex/mvp1-closure-c3-core-stability`.

- [Контракт работы и reuse/gap](WORKING-CONTRACT.md).
- [34 negative/crash сценария](FAILURE-MATRIX.md).
- [Failure/retry/recovery и invariants](RECOVERY-CONTRACT.md).
- [Exact evidence, расходы и findings](EVIDENCE.json).
- [Manifest исходной продуктовой ревизии](MANIFEST.json), [настоящие synthetic ответы](PRODUCT-RESULTS.json).
- [Передача следующему Gate](HANDOFF.md).

Кандидат принимается только после полного применимого canonical `tests/`,
static/import/compile/data checks, реальных synthetic text/voice/material
ответов и replay, а также независимых L2/L3 на exact frozen SHA/tree.
Production/offline tests не объявляются live evidence. Публикация не означает
deploy: tag/release/live mutation запрещены этим поручением.
