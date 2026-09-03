# Gate C1 → Gate C2 handoff

**State:** `C1 CONDITIONAL-TAIL REPAIR CANDIDATE / EXACT REVIEW PENDING`

**Boundary:** `NO TAG / NO DEPLOY / NO LIVE EFFECT`

`381a1e54e6c2281fe335b2835972cc27ee9d486d` /
`ab8fa02cc6d358ba998acc0cc3b4ecd8862c7bc4` — REJECTED / SUPERSEDED:
conditional-tail refs не проверялись. L3 REJECT, L2 reproduced finding без
final ACCEPT из-за platform error. Этот handoff относится к последующему
ремонту, а не возвращает отклонённому SHA статус pending или PASS.

`9de145ccc1c456927623885212f8d5ac64ff8ef0` /
`f7db924f46a1b5ff10694b0c2bc3f2c17e3cdcb1` — REJECTED / SUPERSEDED по
C1-B01/C1-B02. Его прежний PASS и reviews не переиспользуются. После новых
exact L1 PASS / L2 ACCEPT / L3 ACCEPT итог в текущем C1-чате должен быть:
`C1 GATE CANDIDATE PASS / PUBLICATION AUTHORIZATION REQUIRED`.

Gate C2 не запускается от локального candidate. Его predecessor — только
принятый опубликованный protected-main C1 SHA/tree после отдельно разрешённых
push/PR/merge/readback. Floating origin/main не является handoff binding.

## Exact основание

- repository: `streetenergy63reshik-del/nobus-space`;
- branch: `codex/mvp1-closure-c1-semantic-compiler`;
- C0 commit: `5feccfd7626d4382259c3488a9cfb3b3e6c48a0b`;
- C0 tree: `480b2f85978e94a8a5a470d09fe3f343a60849bc`;
- C0 handoff SHA-256:
  `8424a59ce00f5dfc3abc4d379207d35e91e9373e41ee074d8d90ab8b29569221`;
- schema/registry/corpus 1.0.0 digests — [ACCEPTANCE.md](ACCEPTANCE.md);
- exact changed paths — [MANIFEST.json](MANIFEST.json).

Replacement остаётся одним C1 commit относительно exact C0. Commit не содержит
собственный SHA; authoritative frozen readback и итоговые review receipts
передаются в этом же чате без последующей правки bytes.

## Что передаётся

1. Один modality-neutral semantic path для Telegram text, prepared voice
   transcript и Mini App.
2. Fresh tool-less compiler, closed schema и intake-specific generation schema,
   не заменяющая sealed C0 contract.
3. All-or-nothing occurrence-level corroboration: все direct proposals
   understood и без ambiguity; multiset signatures совпадает целиком;
   occurrence не используется повторно. Extra/missing/excess duplicate —
   вся authority INERT; reordered/exact multiplicity корректно сопоставляются.
4. Линейные ASCII/Unicode quote и inline/fenced-code boundaries, nested quotes,
   сохранённый blockquote; word apostrophe не quote, malformed boundary —
   весь intake inert.
5. Независимая issuance/membership/principal/revision/exact-boundary проверка
   всех model-selected refs: main, direct-span и conditional-tail proposals.
   Любой failure сохраняет TRUST_VIOLATION раньше AMBIGUITY и TRUE/FALSE/UNKNOWN
   predicate gates, без нового active binding. Tail не удваивает multiset.
6. Existing Core, TaskContract, queue/state/idempotency/effect boundaries;
   durable clarification с exact reply/token/TTL binding; default-off wiring.
7. Original transform incident и quoted injection regressions, включая
   admission parity text/voice/Mini App и product stop до TaskContract.

## Проверки и остаточный scope

Новые команды/результаты — [L1-REPORT.md](L1-REPORT.md).
Новые independent requirements — [L2-REVIEW.md](L2-REVIEW.md) и
[L3-ADVERSARIAL.md](L3-ADVERSARIAL.md). Исторические PASS/REJECT не заменяют
проверку replacement SHA/tree.

C2 владеет ASR bake-off и реальной voice qualification; C3–C6 — общей
стабильностью, полным journey, operations/security и release/owner acceptance.
Все остаются HOLD. C1 не меняет ASR, runtime config, live databases или
activation. Для будущих effectful capabilities нужны отдельные проверяемые
targets/preconditions/approvals.

## Publication manifest boundary

После candidate PASS владелец отдельно разрешает non-force push exact branch,
один PR в main, merge и protected-main readback. До этого push/PR/merge
запрещены. Tag/release/deploy/activation/live effect запрещены во всём C1.
