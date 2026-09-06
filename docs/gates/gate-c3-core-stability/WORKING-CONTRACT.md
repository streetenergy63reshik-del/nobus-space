# Gate C3 — контракт работы

Цель: принятая задача сохраняет одну identity, восстанавливается после отказа
и не повторяет результат либо внешний effect; пользователь видит честный статус.
Риск HIGH; WIP_ITERATION → CHECKPOINT → GATE_CANDIDATE. PASS пока не заявлен.

Exact base: `5fdc28ce66dbb072acd6676baf72fe58ae10b4b3`, tree
`c8e756fb00874c5db2f6105c6d65154d0ed243e7`. HANDOFF blob
`6d0fee2bdb82af3ffdb92faac22dc0218572e0e6`. GitHub main/protected/readback совпали.
C2 frozen ancestor; delta до base только docs. Четыре final report hashes и
четыре вложенных L1 receipts совпали. C2 manifest 118/118. C1 squash tree
совпадает с reviewed tree; принятые C0 contracts сохранены. Это entry check,
не повторная приёмка C0–C2.

Исходная регрессия C3: 422 PASS, одна upstream deprecation warning.
Первая попытка сохранилась как ENVIRONMENT_FAILURE: отсутствовал parent
каталог для pytest basetemp; после его создания исходные bytes прошли.
Основной checkout: 19 dirty/untracked paths сохранены с hashes вне Git.
C2 worktree не изменяется. Новая ветка `codex/mvp1-closure-c3-core-stability`.

| Requirement | CURRENT reuse | Доказанный gap | Owning code | Regression |
|---|---|---|---|---|
| admission/lease/recovery | SQLiteTelegramState, PreparedTask, CAS, 3 claims | stale clock/commit fence, hung state, truthful status | root: durable_product, durable_telegram_state, telegram_product, runtime_maintenance | test_c3_queue_recovery |
| bounded worker retry | SDK retirement/deadline | production non-web bypass, tenant context cache | worker executor: codex_sdk, codex_cli | test_c3_worker_retry |
| sealed result/outbox/artifact | exact SQLite projection/outbox/OutboxArtifact | missing pre-outbox answer bytes; no part receipts | result executor: durable_runtime, gate5a4, sqlite_store, outbox, state_manager, telegram/bot_api | test_c3_result_recovery, test_c3_delivery_parts |
| multipart input | existing JSON ingress, semantic compiler, request binding | multipart unsupported | ingress executor: transport/miniapp, application/miniapp | test_c3_multipart_input |

Каждый executor пишет только назначенную зону. Root интегрирует и ведёт docs,
общий ledger, настоящие model/ASR smoke. Независимые L2/L3 будут read-only на
frozen bytes. Решение границ — [ADR 0024](../../adr/0024-core-durable-recovery-and-part-delivery.md).

Обязательная приёмка: все 34 negative/crash case, C1 semantic/C2 voice parity,
полный применимый canonical tests/, static/import/compile, diff и data scans,
реальные конечные ответы; затем exact freeze L1/L2/L3, normal publication и
readback. No live/deploy/tag/release/C4. C0-F07 live residual остаётся C5/C6.
