# Gate C1 — L1 report

**State:** `TARGETED REPAIR L1 PASS / FROZEN EXACT L1-L3 PENDING`

## Conditional-tail repair — 4 сентября 2026

`381a1e54e6c2281fe335b2835972cc27ee9d486d` /
`ab8fa02cc6d358ba998acc0cc3b4ecd8862c7bc4` — REJECTED / SUPERSEDED.
L3 REJECT: refs conditional-tail не проходили verifier. L2 независимо
воспроизвёл finding, но final receipt прерван platform error; ACCEPT нет.
Ни один прежний verdict или большой прогон не засчитывается новому SHA.

Resume preflight: exact rejected HEAD/tree, clean, один C1 commit поверх
exact C0, remote main=5feccfd… и remote C1 ref отсутствует. Nobus Memory bridge
4 сентября READY; project pointer устарел относительно Git, не изменялся.

Минимальный ремонт: reference-only helper применяет существующий builder к
main/direct/tail. Tail проверяется до semantic matching. Invalid refs остаются
в итоговом context, TRUST_VIOLATION предшествует ambiguity и predicate gates;
новая active authority не выдаётся. Tail не включён повторно в multiset.

WIP terminal receipts в исключённом из Git `.runtime/c1-tail-repair/`:

| Receipt | Exit | Результат |
|---|---:|---|
| red-tail.json | 1 | 1 failed, 152 deselected: VERIFIED вместо FORGED_REF |
| green-tail.json | 0 | 190 passed, 124 deselected in 2.73s |
| wip-semantic.json | 1 | 1 failed, 313 passed: излишнее изменение exact historical C0 prebound context |
| wip-semantic-corrected.json | 0 | 316 passed in 6.86s; unrelated context rewrite удалён, sealed corpus не менялся |

Новые 191 cases покрывают 162 tail-ref negatives, 12 ambiguous/mismatch,
6 valid TRUE/FALSE/UNKNOWN controls, 9 product guards и 2 invalid-main guards.
Двухвызовное main reuse и отдельный direct-span path проверены отдельно.

### Сохранение frozen результатов

Runtime runner `python .runtime/c1-tail-repair/run_check.py LABEL ARGS…`
записывает точный argv, cwd, before/after SHA/tree/status, terminal exit code,
длительность и SHA-256 output в `LABEL.json`; полный synthetic output —
`LABEL.log`. Secrets/env/private payload не сохраняются. Повтор существующего
LABEL запрещён: при потере сообщения сначала читается готовый receipt/log.
Без terminal exit результат не засчитывается. Runtime не входит в manifest.

Frozen labels: `frozen-semantic`, `frozen-impacted`, `frozen-release`,
`frozen-docs-governance`, `frozen-applicable-governance`, `frozen-smoke`,
`frozen-integrity`. Их результаты не объявляются до выполнения на новом SHA.
Команды ниже сохраняются; для pytest дополнительно применяются `-ra` и
уникальный `--basetemp=.runtime/c1-tail-repair/LABEL-tmp`.
Applicable governance использует точные deselect:
`tests/test_gate_c0_governance.py::test_active_status_and_roadmap_are_consistent`
и `tests/test_gate_c0_governance.py::test_candidate_changes_no_production_code`.

## Историческая проверка 381a1e54 — НЕ evidence текущего ремонта

## История и preflight

Candidate `9de145ccc1c456927623885212f8d5ac64ff8ef0`, tree
`f7db924f46a1b5ff10694b0c2bc3f2c17e3cdcb1`, REJECTED / SUPERSEDED.
C1-B01: ambiguous direct-span и частичное signature matching выдавали
authority. C1-B02: single quotes и inline code не отделяли material.
Его прежние PASS/L2/L3 аннулированы. Более ранние отклонения сохранены в
[EVIDENCE.json](EVIDENCE.json), но не переиспользуются.

Перед правками повторно подтверждены exact rejected HEAD/tree, clean worktree,
C0 parent/main `5feccfd7626d4382259c3488a9cfb3b3e6c48a0b` /
`480b2f85978e94a8a5a470d09fe3f343a60849bc`, отсутствие remote C1 ref,
C0 sealed diff=0 и docs 15/16=0. C0 Git-byte digests совпали с launch prompt.
Nobus Memory bridge вернул IPC_UNAVAILABLE; скрытый filesystem fallback не
применялся, exact Git остаётся достаточным source of truth по launch prompt.

## Воспроизведение и owning-layer correction

Новые focused tests на старом production source дали:
`32 failed, 5 passed, 44 deselected`. Воспроизведены EXECUTE для ambiguous
matching proposal, partial authority при extra/missing, неправильная кратность
duplicates, missing single/inline boundaries и незакрытые quotes.

Исправлены issuer, существующий bounded structural parser и безопасный
ambiguity path; C0 schema/registry/corpus/ADR не менялись. Новые ambiguous
claims остаются INERT, но могут дойти только до no-effect CLARIFY; ранее
серверно подтверждённый C0 ambiguity fixture сохраняет опубликованный результат.
Reference checks и decision order не ослаблены.

Первый полный semantic прогон обнаружил один C0 ambiguity compatibility
failure; он исправлен в owning Core check, без изменения corpus. После этого:
`110 passed` semantic и `10 passed, 167 deselected` targeted Telegram/voice.
Последующее усиление malformed-boundary и финальные результаты учитываются
только в новом полном прогоне ниже.

## Точные команды

Все Python-команды используют canonical
`C:\Хранилище\АГЕНТ\PROстранство\ОРКЕСТРАТОР\Code\nobus-orchestrator-dev\.venv\Scripts\python.exe`,
cwd — isolated C1 worktree; `PYTHONDONTWRITEBYTECODE=1`. Каждый pytest run
использует отдельный `--basetemp=.runtime/...`. Сокращение `python` ниже
обозначает только этот executable.

```text
python -m pytest tests/test_semantic_admission.py -q --tb=short -k "c1_b01 or c1_b02"
python -m pytest tests/test_semantic_admission.py -q --tb=short
python -m pytest tests/test_semantic_admission.py tests/test_codex_cli.py tests/test_codex_sdk.py tests/test_durable_runtime.py tests/test_durable_telegram_state.py tests/test_gate5a4.py tests/test_miniapp.py tests/test_miniapp_artifact.py tests/test_miniapp_result.py tests/test_telegram_gateway.py tests/test_telegram_product.py tests/test_telegram_mvp1_runner.py -q --tb=short
python -m pytest -q --tb=short --ignore=tests/gate0 --ignore=tests/test_gate_c0_governance.py --deselect=tests/test_pre_gate1_architecture_integration.py::test_active_projections_and_authority_point_to_adr0022
python -m pytest tests/test_documentation.py tests/test_gate_c0_governance.py -q --tb=short
python tests/gate_c1/run_real_provider_smoke.py --workspace . --codex-home C:\Users\CGC1ub\.codex --temp-root .runtime\c1-provider-temp
git diff --check
git diff --quiet 5feccfd7626d4382259c3488a9cfb3b3e6c48a0b -- docs/gates/gate-c0-mvp1-truth-contract docs/adr/0023-modality-neutral-semantic-admission-and-core-decision.md
```

## Исторические результаты 381a1e54 до freeze

- focused B01/B02: `74 passed, 51 deselected in 2.12s`;
- full semantic: `125 passed in 5.11s`;
- exact impacted suite: `571 passed, 1 warning in 76.61s`;
- release-relevant: `1575 passed, 2 skipped, 1 deselected, 1 warning in 99.71s`;
- docs only: `4 passed in 0.19s`;
- full docs + C0 governance: `35 passed, 2 failed in 0.93s`.
  Failures: `test_active_status_and_roadmap_are_consistent` требует старый C0
  verdict; `test_candidate_changes_no_production_code` запрещает src/scripts
  diff относительно release. Оба являются historical snapshot checks,
  не новыми C1 regressions;
- тот же docs/governance с двумя явно названными deselect:
  `35 passed, 2 deselected in 0.67s`;
- manifest: exact 32 paths; C0/Gate0 sealed diff=0; docs 15/16=0;
  credential-pattern scan=0; manual changed-content review — только
  обезличенные fixtures, без private payload/transcript/credentials;
- feature flag=False; `git diff --check` exit 0.

Последние basetemp: `c1-security-focused-final-wip-resume`,
`c1-security-semantic-final-wip`, `c1-security-impacted-final-wip-resume`,
`c1-security-release-final-wip-resume`,
`c1-security-governance-applicable-resume` внутри `.runtime`.
Прерванный до результата запуск не засчитан. Более ранний impacted argv
случайно повторял один filename; pytest дедуплицировал его, но итоговая
evidence-команда выше повторена с правильным единственным filename.

Direct-span source/target/predicate refs теперь отдельно проходят тот же
существующий server verifier. Первый их failure переносится в существующий
TrustedAdmissionContext, поэтому TRUST_VIOLATION остаётся раньше AMBIGUITY.
Новые 14 negative cases покрывают forged/boundary/stale/owner/tenant/
conversation/membership для understood и ambiguous direct proposals.

Единственное предупреждение — StarletteDeprecationWarning о существующем
httpx TestClient; зависимость не менялась.

WIP real-provider smoke: 5/5 expected decisions; direct/incident/quoted/injection
EXECUTE in no-effect capabilities, ambiguity CLARIFY with INERT provenance;
TaskContract created=false и effect observed=false во всех пяти случаях.
Этот WIP smoke не заменяет повторный frozen candidate-bound smoke.

## Явные ограничения suite

Historical `tests/gate0` проверяет sealed Gate-0 snapshot, а не C1 code release.
C0 governance содержит snapshot assertions старого CURRENT и запрет любых
production code changes относительно release `f5a9119…`; эти проверки
несовместимы с code Gate C1 и выполняются отдельно с точным failure report.
Единственный release-suite deselect требует obsolete exact ADR 0022 cell
`ACCEPTED`, тогда как exact C0 predecessor уже содержит
`ACCEPTED; semantic/process scope by 0023`. Ничего не скрывается как новый PASS.

После freeze exact SHA/tree должны получить новый L1, ровно один independent
L2 и ровно один independent L3. До их ACCEPT verdict остаётся pending.
