# Передача Gate C3 → Gate C4

**C3 ACCEPTED / PASS / NOT DEPLOYED. Публикация ещё должна быть подтверждена. C4 не начат.**
Проверенный code candidate: `b1ed94c6ddfefe957a50f4d133537f74482910cc`, tree `9acb41b5bf6d2a91b8964f84f4c459d072d0c127`. База C2: `5fdc28ce66dbb072acd6676baf72fe58ae10b4b3`, tree `c8e756fb00874c5db2f6105c6d65154d0ed243e7`. Canonical repository — `streetenergy63reshik-del/nobus-space`, C3 branch — `codex/mvp1-closure-c3-core-stability`.

Перед запуском отдельной задачи C4 нужно прочитать published GitHub main, точный SHA/tree, [ACCEPTANCE](ACCEPTANCE.md), [EVIDENCE](EVIDENCE.json), [MANIFEST](MANIFEST.json) и сверить код с принятым кандидатом. Финальный main SHA/tree фиксируется в локальном publication receipt и итоговом ответе, без самоссылочного commit. C4 разрешён только от принятого опубликованного C3.

Backend сохраняет один Core и исходные SQLite queue/task/outbox. Durable admission предшествует ACK; lease/tenant/contract fences защищают запись и доставку. Sealed answer восстанавливается локально; part receipts пропускают подтверждённые части. Multipart input — ровно metadata+UTF-8 material в прежнем16KiB/5s; C1 INERT смысловая граница и pinned C2 ASR сохранены. Границы ошибок и неизбежное Telegram UNKNOWN окно — [RECOVERY-CONTRACT](RECOVERY-CONTRACT.md).

C4 должен завершить Telegram/Mini App user journey: session expiry→re-auth→та же задача, правдивые ready/result/effect labels, получение того же результата и artifact. C0-F09/F10/F11 остаются C4. Использовать существующие backend authority, idempotency и artifact contract; не вводить вторую очередь или модель файла.

C0-F05/F06/F08 закрыты в C3; C0-F07 закрыт только для backend recovery. Live operational proof, ingress, supervisor, backup/rollback и active-release cleanup остаются C5/C6. Весь MVP1 не READY. Ни C4, ни deploy/live/tag/release автоматически не запускать. Чужой WIP, C2 cache/evidence и прежние Git objects сохранены.
