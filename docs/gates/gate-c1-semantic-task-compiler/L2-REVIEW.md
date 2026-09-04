# Gate C1 — independent L2 review record

**State:** `L2 ACCEPT`

## Принятый независимый verdict

- Reviewer: `/root/c1_tail_l2`.
- Frozen candidate: `8e5e5fd3bf5680b5dbcf78a5f7de40da63ba93da`.
- Tree: `6a8f968f2b447a7a20d88321d8610adcb76c9cb9`; clean before/after.
- 990 собственных проверок плюс указанные регрессии; findings: none.
- 842 собственных matrix checks + 148 boundary checks; semantic 316,
product/worker 17 и applicable C0 governance 31. Exact prebound corpus 25/25.
- Raw receipt: `.runtime/c1-tail-repair/l2-review.json` в исходном C1 worktree.
- SHA-256: `ecad3498207bf279bdb76a46b792123c417dde8664fbc5368a291fe7809e8b4e`.

Результат получен до публикации в задаче C1; здесь он документирован без
повторного запуска. Он относится к frozen candidate, а не к docs-only commit.
Подробная сводка и сохранённые ограничения — [EVIDENCE.json](EVIDENCE.json).

## Историческое задание проверяющему — выполнено на указанном candidate

Формулировки ниже сохранены для объяснения объёма проведённой проверки;
они не являются текущим PENDING или распоряжением повторить L2.


`381a1e54e6c2281fe335b2835972cc27ee9d486d` /
`ab8fa02cc6d358ba998acc0cc3b4ecd8862c7bc4` — REJECTED / SUPERSEDED:
conditional-tail reference gap. Прежний L2 независимо воспроизвёл invalid
tail target/source/boundary, но final receipt прерван platform error. ACCEPT
не получен и не переносится. Новый reviewer получает только новые frozen bytes.

Обязательно независимо воспроизвести source/target/predicate refs всех
compiler-output paths (main, direct-span, tail), а не только новые тесты:
9 видов нарушения при TRUE/FALSE/UNKNOWN; ambiguous/mismatch tail; двухвызовное
main reuse и отдельный direct pass; no active issuance/approval/TaskContract/
effect, TRUST_VIOLATION раньше всех semantic/predicate gates. Tail не должен
удваивать occurrence multiset. Сохранить компактный exact-SHA terminal receipt
в `.runtime/c1-tail-repair/l2-review.json`, без правок tracked bytes.

`9de145ccc1c456927623885212f8d5ac64ff8ef0` /
`f7db924f46a1b5ff10694b0c2bc3f2c17e3cdcb1` — REJECTED / SUPERSEDED:
C1-B01 ambiguous/partial corroboration и C1-B02 missing quote boundaries.
Прежний L2 ACCEPT отменён и не переиспользуется. История других кандидатов
находится в EVIDENCE.json; это не evidence replacement.

Ровно один новый независимый read-only L2 получает frozen exact commit/tree,
exact C0 predecessor и manifest. Автор изменений не засчитывает собственный L2.
Проверяющий обязан отдельно воспроизвести:

- C1-B01 ambiguous matching direct proposal без authority/TaskContract/effect;
- extra create_file без partial respond, полный multiset всех direct spans,
  missing/excess duplicate/conflicting и reordered occurrences;
- отсутствие повторного использования одного occurrence;
- C1-B02 ASCII/Unicode single/double quotes, guillemets, inline/fenced code,
  nested delimiters, word apostrophes и malformed boundaries;
- actual admission/product stop до TaskContract, text/voice/Mini App parity;
- original transform incident и 25/25 sealed C0 corpus;
- closed schema, exact Registry, forged/stale/cross-principal/cross-boundary refs;
- conditional tail, shared deadline, span bounds и clarification replay/TTL;
- default-off, clean worktree, exact manifest и C0 sealed diff=0/docs 15/16=0.

Authoritative verdict и команды возвращаются в текущий C1-чат с exact SHA/tree.
Этот файл — review contract, не предварительный ACCEPT. После review bytes не
меняются; любое изменение аннулирует candidate binding.
