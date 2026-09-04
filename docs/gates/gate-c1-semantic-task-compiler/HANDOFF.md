# Gate C1 → Gate C2 handoff

**State:** `C1 ACCEPTED / PUBLISHED / NOT DEPLOYED`

**Boundary:** `NO TAG / NO DEPLOY / NO LIVE EFFECT`

`381a1e54e6c2281fe335b2835972cc27ee9d486d` /
`ab8fa02cc6d358ba998acc0cc3b4ecd8862c7bc4` — REJECTED / SUPERSEDED:
conditional-tail refs не проверялись. L3 REJECT, L2 reproduced finding без
final ACCEPT из-за platform error. Этот handoff относится к последующему
ремонту, а не возвращает отклонённому SHA статус pending или PASS.

`9de145ccc1c456927623885212f8d5ac64ff8ef0` /
`f7db924f46a1b5ff10694b0c2bc3f2c17e3cdcb1` — REJECTED / SUPERSEDED по
C1-B01/C1-B02. Его прежний PASS и reviews не переиспользуются.
Последующий frozen candidate принят по собственным L1/L2/L3.

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


C2 — READY TO START / NOT STARTED. База C2 — точный protected-main SHA/tree
после этой docs-only синхронизации. Их readback и SHA-256 актуальных HANDOFF /
ACCEPTANCE передаются в стартовом промте C2 после merge; документ не содержит
собственный будущий SHA. Не использовать floating origin/main вместо binding.
Fetch/readback допустимы. На входе C2 product code должен быть byte-identical к
`2732a11122179c4197a74594dd0c8ba3ed9ec52d`; исходные L1–L3 C1 не повторять.

## Exact основание

- repository: `streetenergy63reshik-del/nobus-space`;
- branch: `codex/mvp1-closure-c1-semantic-compiler`;
- C0 commit: `5feccfd7626d4382259c3488a9cfb3b3e6c48a0b`;
- C0 tree: `480b2f85978e94a8a5a470d09fe3f343a60849bc`;
- C0 handoff SHA-256:
  `8424a59ce00f5dfc3abc4d379207d35e91e9373e41ee074d8d90ab8b29569221`;
- schema/registry/corpus 1.0.0 digests — [ACCEPTANCE.md](ACCEPTANCE.md);
- exact changed paths — [MANIFEST.json](MANIFEST.json).

Frozen replacement — один C1 commit относительно exact C0. Его SHA/tree и
принятая публикация указаны выше. Документный follow-up не меняет этот объект.
Итоговый candidate receipt SHA-256:
`26f38a6cc371130715b6a2bd2e7849cfebdaacfc89dfc5ef5b5e9a8afc1463a5`.
Локальные raw receipts остаются в исходном C1 worktree под
`.runtime/c1-tail-repair/`; опубликованная обезличенная сводка — EVIDENCE.json.

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

Выполненные проверки — [L1-REPORT.md](L1-REPORT.md),
[L2-REVIEW.md](L2-REVIEW.md) и [L3-ADVERSARIAL.md](L3-ADVERSARIAL.md).
Semantic 316 PASS; impacted 762 PASS; release 1766 PASS / 2 skips / 1 deselect.
L2: 990 собственных checks и регрессии; L3: 1477 собственных checks и
135 регрессий. Полные C0 docs/governance: 35 PASS / 2 исторических FAIL,
не объявлены зелёными. Первый provider smoke — безопасный timeout;
один неизменённый повтор — 5/5. Причина первого timeout не установлена.
25/25 prebound C0 corpus доказывает совместимость evaluator, не качество
реального ASR/модели. Production trusted item-state source отсутствует:
легитимные условные задачи остаются UNKNOWN. Эти ограничения передаются C2–C6.

C2 владеет ASR bake-off и реальной voice qualification; C3–C6 — общей
стабильностью, полным journey, operations/security и release/owner acceptance.
C3–C6 остаются HOLD до своих predecessors. C1 не меняет ASR, runtime config, live databases или
activation. Для будущих effectful capabilities нужны отдельные проверяемые
targets/preconditions/approvals.

## Publication manifest boundary

Владелец разрешил публикацию C1: non-force push, PR #11 и squash merge
выполнены; product SHA/tree подтверждены readback. Отдельно разрешён этот
docs-only follow-up. Повторять code push/PR/merge не требуется.
Tag/release/deploy/activation/live effect не выполнялись. C2 работает в новом
изолированном worktree/чате; публикацию C2 выполняет этот же C2-чат только
после отдельного точного разрешения владельца.
