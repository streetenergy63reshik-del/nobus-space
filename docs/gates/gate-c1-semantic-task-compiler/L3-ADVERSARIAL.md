# Gate C1 — independent adversarial L3 record

**State:** `PENDING NEW EXACT-CANDIDATE REVIEW`

`381a1e54e6c2281fe335b2835972cc27ee9d486d` /
`ab8fa02cc6d358ba998acc0cc3b4ecd8862c7bc4` — REJECTED / SUPERSEDED.
Прежний L3 REJECT выявил nine invalid conditional-tail ref variants с
VERIFIED/EXECUTE/OWNER_CONDITIONAL при trusted TRUE и потерей trust failure
при FALSE/UNKNOWN. Это server-verifier omission, не model-quality residual.
Он исправляется в последующих bytes; старые verdict не переиспользуются.

Новая adversarial проверка отдельно атакует все compiler-output paths:
main/direct/tail source/target/predicate refs, nine violation classes,
TRUE/FALSE/UNKNOWN, ambiguous/mismatching tail, main reuse и отдельный direct
pass. Проверить отсутствие новой authority/approval/TaskContract/effect и
double-count tail, общий deadline/call bounds и product guard. Собственные
probes обязательны; новый тест не заменяет аудит. Exact-SHA terminal receipt
сохранить в `.runtime/c1-tail-repair/l3-review.json`, tracked bytes не менять.

`9de145ccc1c456927623885212f8d5ac64ff8ef0` /
`f7db924f46a1b5ff10694b0c2bc3f2c17e3cdcb1` — REJECTED / SUPERSEDED:
C1-B01/C1-B02. Прежний L3 ACCEPT отменён. Более ранняя история сохранена в
EVIDENCE.json и не является evidence replacement.

Ровно один новый независимый read-only L3 атакует frozen exact SHA/tree:

- ambiguous matching proposal и попытку получить authority до clarification;
- extra/missing/duplicate/heterogeneous operations, partial TaskContract,
  повторное использование occurrences и различия role/predicate signature;
- quoted/nested/inline-code prompt injection с ASCII/Unicode delimiters,
  незакрытые/конфликтующие quotes, backtick runs и apostrophes внутри слов;
- forged/stale/cross-boundary/source/target/predicate refs и tampered span ledger;
- proposal-digest/principal/intake-revision substitution;
- text/confirmed-voice/Mini App parity и отсутствие TaskContract/effect во всех
  fail-closed случаях;
- conditional FALSE/UNKNOWN/second condition, malformed/timeout/cancellation,
  model capability/route/permission/approval smuggling и keyword fallback;
- default-off и отсутствие нового Core, queue, policy plane или dependencies.

Проверяющий возвращает exact commands, observed outcomes, findings и ACCEPT
либо REJECT в этом же чате. Этот документ не объявляет заранее ACCEPT.
После freeze любые изменённые bytes требуют новой candidate binding.

Согласованная semantic kind substitution в no-effect capabilities остаётся
модельным quality residual; она не разрешает обход refs/policy/downstream
deny-all. Для любой будущей effectful capability нужны собственные проверяемые
target/precondition/approval controls.
