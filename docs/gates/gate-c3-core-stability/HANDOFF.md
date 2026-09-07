# Передача Gate C3 → Gate C4

**DRAFT: C3 ещё не принят. Gate C4 не начинать.**
Итоговый exact accepted/published SHA/tree будет привязан в
[EVIDENCE.json](EVIDENCE.json) и локальном publication receipt. Этот файл не
заменяет проверку опубликованного Git object.

База C3 — принятый C2 `5fdc28ce66dbb072acd6676baf72fe58ae10b4b3`, tree
`c8e756fb00874c5db2f6105c6d65154d0ed243e7`.
Контракт результата — [ACCEPTANCE](ACCEPTANCE.md), границы восстановления —
[RECOVERY-CONTRACT](RECOVERY-CONTRACT.md), доказательства —
[FAILURE-MATRIX](FAILURE-MATRIX.md).

C4 принадлежит завершённый Telegram/Mini App user journey: session expiry и
re-auth, truthful ready/result/effect labels, пользовательское получение того
же результата и artifact. Нужно использовать существующую backend authority,
immutable result/part receipts и idempotency C3, без второй очереди/модели файла.

C0-F09/F10/F11 остаются C4. C0-F07 operational/live часть, ingress, supervisor,
backup/rollback и cleanup active release остаются C5/C6. Никакой production
restart, deploy, tag/release или live DB не выполнен и здесь не разрешается.
MVP1 не READY; C4 запускается только отдельным поручением от exact принятого и
опубликованного C3. Прежние C0–C2 объекты и чужой WIP сохраняются.
