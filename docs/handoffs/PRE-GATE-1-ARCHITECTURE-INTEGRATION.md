# Pre-Gate-1 architecture integration

**Статус:** ACCEPTED
**Дата:** 1 августа 2026 года
**Предшественник:** Gate 0 immutable accepted, `22/22`
**Открывает:** отдельный implementation cycle Gate 1
**Решение:**
[`ADR 0021`](../adr/0021-post-gate0-agent-roles-and-downstream-integration.md)

## 1. Причина

После immutable acceptance Gate 0 независимая read-only сверка обнаружила два
документационных долга уровня P2:

1. ADR 0020 перечисляет пять specialist worker profiles, тогда как принятый
   Gate 0 normative catalog и closed `AgentRole` Gate 2A содержат шесть,
   включая `verification_specialist`.
2. Индивидуальные архитектуры Gate 5–8 не фиксируют все уже принятые в
   документах 12/13 и ADR 0020 integration boundaries: отдельные Windows
   identities Development Worker и Document Bridge, единый Gate 2A effect
   plane, closed specialist results и роль Gate 8 как финальной интеграции, а
   не первого server deployment.

Это не дефект принятого результата Gate 0 и не основание переписывать его
evidence. Gate 1 владеет specialist routing proposal, поэтому ambiguity была
закрыта отдельным forward-only overlay до начала Gate 1.

## 2. Стратегия без нарушения immutable acceptance

Файлы из digest-bound normative catalog Gate 0 сохранены на точных байтах
accepted result commit. Исправление выполнено вперёд:

- ADR 0021 делегирует closed role vocabulary принятому catalog и явно включает
  `verification_specialist`;
- тот же ADR содержит Gate 5–8 integration addendum и ограничивает clauses,
  которые он уточняет;
- текущие индексы и roadmap ссылаются на ADR 0021 как на post-seal overlay;
- один regression test проверяет шесть ролей, downstream boundaries и
  неизменность sealed Gate 0 acceptance binding.

Gate 0 acceptance, catalog, evidence, ADR 0020, документы 12/13 и individual
Gate 5–8 architectures не редактировались ради ретроактивного совпадения.

## 3. Принятые инварианты overlay

1. Один Nobus Core остаётся единственным orchestrator, policy/authority owner и
   владельцем effects/reconciliation.
2. Closed roles: `general_orchestrator_worker`,
   `google_workspace_specialist`, `research_analytics_specialist`,
   `content_studio_specialist`, `development_specialist`,
   `verification_specialist`.
3. Specialist model не получает provider credentials, не выполняет external
   effects и не создаёт peer-to-peer authority. Только Core создаёт typed
   dispatch, проверяет closed result и выбирает следующий шаг.
4. `verification_specialist` независим от проверяемого исполнителя и не может
   одобрять собственную работу.
5. Development Worker Gate 2A и Document Bridge Gate 5 — разные Windows service
   identities, queue namespaces и capability sets. Document Bridge не исполняет
   development jobs; Development Worker не получает document authority.
6. Gate 4 расширяет единственный generic task/job/effect plane Gate 2A. Gate 7
   его переиспользует; второй effect engine запрещён.
7. Gate 6 возвращает closed `AnalysisResult`; deterministic calculations и
   reconciliation остаются в Core. Gate 7 принимает verified analytical source
   и не пересчитывает факты.
8. Gate 8 интегрирует уже существующие Core/Mini App server release Gate 2A,
   Development Worker и Document Bridge и проводит 72-hour pilot; это не первый
   server deployment.
9. SSH, VPS, domain, DNS, TLS, BotFather, live runtime, remote, push и deploy не
   относятся к PRE-G1.

## 4. Acceptance result

PRE-G1 принят после выполнения следующих условий:

- ADR 0021 и ADR journal фиксируют все инварианты;
- navigation/status/roadmap называют PRE-G1 `ACCEPTED`, Gate 1
  `READY TO START`, Gate 2 `BLOCKED` до accepted Gate 1 и Gate 2A `BLOCKED` до
  accepted Gate 2;
- `tests/test_pre_gate1_architecture_integration.py` доказывает vocabulary,
  boundary matrix, overlay priority и неизменность acceptance/catalog binding;
- mutating Gate 0 prepare/bind/seal/generator modes не запускались на canonical
  repository;
- воспроизведённый `prepare_precapture()` defect закрыт отдельным TDD commit
  `9dd03e8abd85178cda503e457df202526589c597`; mutation-bearing tests работали
  только на temporary copied fixtures;
- focused PRE-G1 regression: `7 passed`; helper-focused profile:
  `42 passed, 1 skipped`;
- forward-only historical self-checks привязаны к capture base и accepted result
  tree без изменения sealed evidence; весь Gate 0 normative profile:
  `58 passed, 3 skipped`;
- официальный unfiltered `full_read_only` из `verification-profiles.json`:
  `1521 passed, 6 skipped, 1 warning`;
- exact acceptance binding и SHA-256 всех 20 `required_sources` проверены новым
  regression test и отдельным readback; Gate 0 evidence, catalog, fixtures и
  verification receipts остались byte-identical;
- независимые L1/L2/L3 проверили один exact base HEAD, diff digest и staged tree
  и дали `ACCEPT`;
- staged/committed manifest содержит только exact allowlist; push/deploy нет.

Conditional owner acceptance подтверждена тремя финальными `ACCEPT` одного
candidate и exact manifest readback. Gate 1 `READY TO START`; это не является
L4 на его implementation.
