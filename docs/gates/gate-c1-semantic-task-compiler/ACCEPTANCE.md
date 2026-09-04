# Gate C1 — acceptance record

**State:** `C1 ACCEPTED / PUBLISHED / NOT DEPLOYED`

**Boundary:** `NO TAG / NO DEPLOY / NO LIVE EFFECT`

Candidate `381a1e54e6c2281fe335b2835972cc27ee9d486d`, tree
`ab8fa02cc6d358ba998acc0cc3b4ecd8862c7bc4`, — **REJECTED / SUPERSEDED**.
L3 воспроизвёл conditional-tail reference gap; L2 независимо подтвердил
finding, но завершился platform error без final ACCEPT. При server TRUE
недействительные tail refs давали VERIFIED/EXECUTE/OWNER_CONDITIONAL.
Его результаты сохранены как история, не как приёмка текущего ремонта.

Candidate `9de145ccc1c456927623885212f8d5ac64ff8ef0`, tree
`f7db924f46a1b5ff10694b0c2bc3f2c17e3cdcb1`, — **REJECTED / SUPERSEDED**.
Его прежний PASS отменён воспроизводимым security-аудитом C1-B01/C1-B02.
Ни его L1, ни прежние L2/L3 не доказывают replacement candidate.

## Принятый результат и публикация — 4 сентября 2026

- Проверенный frozen candidate: `8e5e5fd3bf5680b5dbcf78a5f7de40da63ba93da`.
- Его tree: `6a8f968f2b447a7a20d88321d8610adcb76c9cb9`.
- Опубликованный product commit: `2732a11122179c4197a74594dd0c8ba3ed9ec52d`,
  [PR #11](https://github.com/streetenergy63reshik-del/nobus-space/pull/11), squash merge.
- GitHub readback: product tree точно совпал с проверенным tree;
  единственный parent — C0 `5feccfd7626d4382259c3488a9cfb3b3e6c48a0b`;
  `main` protected. У PR #11 нет status contexts и workflow runs;
  это отсутствие CI, а не дополнительный PASS.
- Итог C1: L1 PASS по применимому scope, independent L2 ACCEPT и L3 ACCEPT.
  Точные результаты, исключения и хеши — [EVIDENCE.json](EVIDENCE.json).

Эта документная синхронизация не меняет code/tests/config/schema/ADR и не
переиздаёт проверки C1. L1–L3 привязаны к frozen candidate выше, а не к
последующему docs-only commit. Исходные bytes доступны по указанному SHA.
Предварительные pending-статусы в product commit заменены этим record.
C1 опубликован, но default-off; deployment identity не доказана, MVP1 не READY.


## Exact основание

- C0 predecessor: `5feccfd7626d4382259c3488a9cfb3b3e6c48a0b`;
- C0 tree: `480b2f85978e94a8a5a470d09fe3f343a60849bc`;
- C0 handoff SHA-256:
  `8424a59ce00f5dfc3abc4d379207d35e91e9373e41ee074d8d90ab8b29569221`;
- ADR 0023 SHA-256:
  `809447612d992e0c5b2ea76a1cce37d4c9908bf6038bb18a9ac67c7648256f8f`;
- SemanticProposal schema 1.0.0 SHA-256:
  `f09457922593bb82bc200cddaa6c6602295df3462627a5b101f0cab5e9115e87`;
- Capability Registry 1.0.0 SHA-256:
  `cabd76d4804474af73373c51cc5a7d361ff5c6d368aee365ffe6cbaa992a4161`;
- gold corpus 1.0.0, 25 cases, SHA-256:
  `43f87170d24e24df196078f08fd06fe80123b75f64c6d5175312c7e20048bab3`.

Digests относятся к Git blob bytes. Windows checkout line endings не являются
изменением sealed Git content.

## Исправленные источники ошибок

**C1-B01.** Authority выдаётся только при полной occurrence-level биекции.
Multiset всех requested/conditional occurrences основного proposal должен
совпасть с multiset всех relevant direct-span proposals. Каждый direct proposal
understood, без ambiguities и clarification question. Для каждого occurrence
совпадают operation kind, role, predicate kind/arguments; использованный
occurrence удаляется из пула. Extra, missing, conflicting и excess duplicate
блокируют все active bindings, а не только несовпавшую часть. Порядок неважен;
точно совпавшая кратность дубликатов не схлопывается.

Ambiguous direct-span не создаёт authority. Он приводит к конкретному
безопасному CLARIFY с INERT provenance, без TaskContract/effect. Reference
verification и C0 decision order сохраняются; никакое clarification не
обходит forged/stale/cross-boundary checks.

Model-selected source/target/predicate refs не входят в authority signature и
отдельно проверяются по issuance, membership, owner, tenant, conversation,
intake revision и exact boundary. Это относится к main, всем direct-span и
conditional-tail proposals; их failure переносится в TrustedAdmissionContext
до AMBIGUITY и predicate gates. Tail проверяется до semantic matching; даже
ambiguous/mismatching tail не скрывает invalid ref. При failure issuer не
выдаёт active binding, TaskContract/approval/effect запрещены. Tail является
вспомогательным pass и не входит повторно в multiset прямых операций.
Proposal/intake/span digest binding сохранён.

**C1-B02.** Линейный bounded parser выделяет «…», “…” , "…", '…', ‘…’,
inline code, fenced code и вложенные delimiters. Blockquote и explicit material
bounds сохранены. Апостроф внутри слова — обычный символ. Незакрытый или
конфликтующий delimiter делает весь intake inert. Ограничение входа — 16 000
символов; новых зависимостей и regex для quote parsing нет.

## Сохранённый продуктовый путь

Telegram text / подтверждённый voice transcript / Mini App text используют
один canonical input, fresh tool-less compiler, закрытый SemanticProposal,
server-derived TrustedAdmissionContext и deterministic CoreDecision.
Существующие TaskContract, queue/state, idempotency, approval и effect boundary
не заменены. Compiler и downstream no-effect answer используют ephemeral,
deny-all, read-only профиль без tools, web, MCP, apps, browser, shell, code,
image и multi-agent.

Материал преобразуется в промт; перечисленные внутри него команды inert.
24 structural spans, максимум 8 direct/tail compilations и один admission-wide
deadline сохранены. Conditional tail подтверждает только одну unconditional
requested operation без predicate/ambiguity; иначе уточнение. Clarification
требует exact Telegram reply или opaque Mini App token с TTL/revision binding.

## Приёмка и ограничения

Команды, результаты и история отклонений находятся в [L1-REPORT.md](L1-REPORT.md)
и [EVIDENCE.json](EVIDENCE.json); corpus и security coverage —
[COVERAGE.json](COVERAGE.json). Независимые L2/L3 уже выполнены по frozen SHA/tree;
повторная проверка C1 для этой документной синхронизации не требуется.

Feature flag остаётся False. C0 sealed files и docs 15/16 не меняются.
C2 — READY TO START / NOT STARTED; C3–C6 и MVP2 — HOLD. MVP1 не READY.
Владелец разрешил публикацию C1 и отдельную актуализацию документации.
Push/PR/merge product C1 выполнены; tag/release/deploy/activation/live effects
не выполнялись и этим record не разрешаются.

Согласованная semantic kind substitution самим compiler остаётся ограниченным
риском качества no-effect capabilities. Она не отменяет server refs/policy и
downstream deny-all. Будущая effectful capability требует собственных
server-verifiable target/precondition/approval controls.
