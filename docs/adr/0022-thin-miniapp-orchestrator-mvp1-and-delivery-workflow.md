# ADR 0022 — Тонкий Mini App, один orchestrator MVP-1 и процесс поставки

**Статус ADR:** ACCEPTED

**Статус реализации:** CURRENT для процесса разработки; TARGET для Mini App

**Дата:** 25 августа 2026 года

**Тип решения:** forward-only owner decision

## 1. Контекст и binding

Решение вводится поверх локального Git-состояния
`agent/mobile-codex-runtime` @
`8b896fbca9b23c8751d651d14a122506338b5827`. Оно не переписывает историю и
не превращает документацию в доказательство реализации.

На момент решения воспроизводимо подтверждено:

- локальный owner-bound Telegram/Core/Codex runtime уже существует в Git;
- `main` @ `420c9a6d4fcdb8f73fc71e23257fa319dafb6354` является предком
  исходного HEAD;
- `origin` настроен, но remote-tracking refs и upstream отсутствуют;
- наличие `origin` не доказывает опубликованный GitHub-канон;
- Gate 0 принят как исторический sealed snapshot по
  [`GATE-0-ACCEPTANCE.json`](../gates/gate-00-product-contract-baseline/GATE-0-ACCEPTANCE.json):
  `result_commit = f5086b2a71a9ae22be3c858ff69453287f6925da`,
  `result_tree = 2e3248eb295b1627d36f196c26dfc21c6ebd90fd`;
- все 20 `required_sources` из
  [`normative-catalog.json`](../gates/gate-00-product-contract-baseline/product/normative-catalog.json)
  совпадают по SHA-256 и остаются byte-identical;
- `agent/gate-01-acceptance` @
  `db0a24e8d7be8b1d1f1ddcd701d424c49164784e` содержит 86-path dirty
  WIP и не является принятым Gate 1;
- safety refs, bundles, stash и recovery worktrees существуют и не должны
  изменяться этим решением;
- активные README/CURRENT документы ошибочно утверждали, что remote отсутствует,
  Gate 1 не начинался, полный Gate 2A обязателен сейчас, а обычная локальная
  разработка требует отдельного formal L4 и полного L1/L2/L3 на каждом WIP.

Главное продуктовое противоречие: Telegram Mini App обязателен в MVP-1, но
прежний путь делал его частью крупной распределённой платформы с ранним Linux
Core, универсальным Agent Registry, Development Worker и Gate 3–8. Такой путь
не даёт короткого коммерчески полезного результата поверх уже работающего
локального runtime.

## 2. Решение

### 2.1. Прямой вердикт

Telegram Mini App и Telegram-оркестратор — **REQUIRED in MVP-1**. Они используют
**one Core / one queue / one authoritative state / one effect authority**.

MVP-1 развивается поверх существующего локального Windows runtime. Core
остаётся единственным владельцем identity, маршрута, state transitions,
idempotency, approvals, effects, recovery и delivery. LLM/Codex/worker остаётся
заменяемым недоверенным исполнителем без credentials и effect authority.

Полный распределённый Gate 2A имеет статус **FROZEN / NOT CURRENT**.

### 2.2. Обязательный вертикальный путь

<!-- mvp1-vertical-path:start -->
`Telegram Mini App -> owner authentication / Telegram initData ->
existing Nobus Core -> local Codex/runtime -> authoritative state ->
Telegram/Mini App status/result/artifact`
<!-- mvp1-vertical-path:end -->

В пользовательских терминах:

```text
владелец открывает Mini App из Telegram
  -> backend проверяет Telegram identity/initData
  -> владелец создаёт и видит одну задачу
  -> Telegram и Mini App передают её в один существующий Core
  -> существующий локальный Codex/runtime выполняет задачу
  -> один authoritative state хранит статус
  -> статус, результат и артефакт видны в Telegram и Mini App
```

### 2.3. Минимальная topology

```text
Telegram chat ------------------------------+
                                             |
Telegram Mini App -> Mini App Web Boundary --+-> existing local Nobus Core
                                                    |-> current queue/state
                                                    |-> local Codex/runtime
                                                    `-> current effect/outbox
```

`Mini App Web Boundary` — единственный новый deployment unit первого пути:

- static HTML/CSS/ES modules;
- публичный HTTPS ingress и exact Host/Origin boundary;
- bounded pass-through endpoint для raw Telegram `initData`;
- pass-through для короткой owner-bound opaque session Core;
- тонкий API adapter к существующему Core;
- безопасная task/result/artifact projection.

Boundary не имеет собственной БД, очереди, policy engine, effect engine,
Agent Registry, scheduler или model authority. Durable login replay/session
generation и task state хранятся в существующем authoritative state Core.
Boundary не хранит bot token/secret и не принимает auth decision: он ограничивает
размер/время запроса и без изменения передаёт raw `initData` по
аутентифицированному transport в Core. Только Core проверяет signature,
freshness/future skew, exact owner и replay, затем выпускает и валидирует opaque
session. Boundary не кэширует raw `initData`, bearer или auth verdict.
Публичный ingress может использовать один outbound-authenticated reverse
transport к owner PC, но не хранит task payload и не становится Core. При
недоступном локальном runtime Mini App fail-closed показывает недоступность; он
не выполняет задачу отдельно.

Для каждого будущего mutating request (`task create` или approval resolve)
один owner/session-bound idempotency key проходит неизменным от browser через
Boundary до Core. Core связывает его с owner, session, operation и request
digest. Boundary не является очередью и не делает blind retry. Если Core мог
зафиксировать mutation, но ACK потерян, клиент/Boundary выполняет только
readback/reconciliation по тому же request id; повторная task или approval не
создаётся. Idempotency key не даёт effect authority: approval по-прежнему
разрешается только immutable server challenge.

Точный HTTPS provider/hostname выбирается внутри отдельного implementation
slice после read-only preflight и отдельной авторизации внешнего изменения.
Это обратимая deployment-деталь, а не разрешение переносить Core на VPS.

### 2.4. Поверхность первого MVP

В Mini App входят только:

- server-side owner authentication;
- список и карточка задачи;
- создание задачи обычным текстом;
- статус и журнал существенных безопасных событий;
- результат и tenant/task-bound получение артефакта;
- accept/reject immutable server challenge только когда runtime effect policy
  действительно требует `ApprovalRequest/ApprovalDecision`.

Не входят:

- второй orchestrator, queue, state store, policy или effect plane;
- ранний перенос Core, Telegram token или poller на VPS;
- universal Agent Registry, peer-to-peer agents или отдельные agent services;
- Web IDE, terminal, arbitrary shell, self-update и self-deployment;
- multi-user SaaS, billing, RBAC и tenant administration;
- Gate 3–8, Google/document/analytics platform без прямой нужды пути;
- framework, service или repository «на будущее».

## 3. Сохранённые границы безопасности

Из прежней архитектуры обязательны:

1. Boundary ограничивает raw `initData` и передаёт его неизменным; только Core,
   владеющий bot secret, проверяет подпись для exact bot, freshness/future skew,
   exact owner и replay/session generation.
2. `initDataUnsafe` никогда не является authority.
3. Только Core выпускает и валидирует короткоживущий opaque session bearer.
   Boundary его не кэширует; клиент хранит bearer только в памяти, не в URL,
   `localStorage`, logs или evidence.
4. Host/Origin и same-origin API точны; wildcard CORS запрещён; обязательны CSP,
   bounded body/query/header/time, rate limits и sanitized errors.
5. Client не назначает tenant, actor, route, risk, role, capability, state или
   approval payload. Core выводит их повторно.
6. Approval принимает только ссылку на immutable server challenge; stale,
   replayed, expired или revision-mismatched challenge отклоняется.
7. Task/event/artifact projection связана с owner, tenant, task, revision и
   session; неизвестные поля и cross-tenant refs отклоняются.
8. Provider unknown и delivery unknown различаются; доставка может быть
   повторена только без повтора provider/effect.
9. Idempotency, one-poller fencing, atomic state/outbox, audit и recovery
   сохраняются. Mutating request id проходит до Core end-to-end; неизвестный
   mutation/effect не повторяется вслепую, а reconciles по authoritative state.
10. Credentials, raw prompt/payload, local path, argv/env, audio и данные
    другого tenant не появляются в UI, API errors, logs или evidence.

Sealed документы
[`06-Регламент-качества-L1-L4.md`](../06-Регламент-качества-L1-L4.md) и
[`07-Правила-внешней-записи.md`](../07-Правила-внешней-записи.md) остаются
авторитетными для **product/runtime approval semantics**. Этот ADR меняет
только локальный процесс разработки Codex и активную roadmap.

## 4. Gate 1 WIP: reuse, freeze, discard later

### Reuse

Из принятого runtime и проверенных идей Gate 1 переиспользуются:

- trusted Telegram ingress, exact owner binding и replay protection;
- локальная voice boundary;
- deterministic Core и model proposal without authority;
- durable queue, authoritative state, outbox и safe delivery;
- application-owned effects, idempotency, receipts и reconciliation;
- scoped context/TTL, safe errors и negative tenant/effect tests;
- существующий local Codex/runtime.

### Freeze

Весь dirty Gate 1 worktree и recovery-контур сохраняются как
`HOLD / NOT_ACCEPTED`. Широкая миграция всех доменов на новый
`IntentEnvelope`, 80-case Gate ceremony, provider qualification, cloud
expansion и legacy deprecation не являются prerequisite тонкого Mini App.

### Discard later

Дублирующие parser/router/agent maps, speculative framework remnants и
Gate-specific ceremony artifacts могут быть удалены только после отдельного
recovery/cleanup-аудита, точного manifest и применимой авторизации. Этот ADR
ничего не удаляет, не вливает и не объявляет принятым.

## 5. Точная граница supersession

Старые документы и ADR не переписываются. Действует следующая forward-only
матрица:

| Источник | Остаётся действующим | Superseded / deferred новым ADR |
|---|---|---|
| docs 06/07 | product/runtime approvals, effect binding, human decision и audit | ничего; локальный Codex workflow просто отделён от runtime policy |
| docs 12/13 | sealed historical product/security snapshot; tenant, effect, evidence и recovery invariants | topology Gate 0–8, обязательный full hybrid rollout и последовательность поставки |
| ADR 0017 | Natural Language First, deterministic Core, application-owned effects, model without OAuth/shell/filesystem authority | ранний Server Core и document-platform sequence |
| ADR 0018 | existing Core reuse, atomic admission/outbox, idempotency, provider/delivery unknown, SQLite default, one-poller fencing | Gate 0–8 integration sequence как active MVP roadmap |
| ADR 0019 | owner/secret/filesystem boundaries, no blind mutation и recovery discipline | обязательные server/Bridge steps, не нужные текущему vertical slice |
| ADR 0020 | Mini App обязателен; один Core/state/effect authority; client not authority; no peer-to-peer/self-deploy | full Server Control Plane, universal Agent Registry, Windows Development Worker и Gate 2A-before-Gate-3 sequence |
| ADR 0021 | historical Gate 0 binding, один Core, workers без credentials/effect authority, maker/reviewer independence для frozen candidate | six-role registry как active MVP requirement, Gate 1->2->2A->3–8 order, Development Worker/Document Bridge platform и Gate 6–8 handoffs |
| full Gate 2A | security test ideas, перечисленные в разделе 3 | **FROZEN / NOT CURRENT** topology, deployment, contracts, acceptance matrix и owner runbook |

ADR 0021 остаётся byte-identical, но его forward verification mapping к
`tests/test_pre_gate1_architecture_integration.py` superseded: файл с прежним
именем теперь проверяет ADR 0022 overlay и неизменность Gate 0 catalog. Closed
roles остаются историческим catalog fact, а не создаваемыми здесь runtime
`AgentRole`.

Security, tenant isolation, effect authority, idempotency, evidence binding,
audit trail и recovery invariants не superseded.

## 6. Authority Git, GitHub и Nobus Memory

- Git-репозиторий — источник истины для code, tests, ADR, CURRENT и постоянной
  документации.
- Локальная ветка и commit — проверяемый WIP/candidate, но не опубликованный
  канон.
- GitHub `main` и release tags становятся каноном принятой опубликованной
  истории только после явно разрешённых push/PR/merge и проверки exact remote
  SHA.
- Наличие `origin` само по себе ничего не публикует и не доказывает remote SHA.
- Nobus Memory хранит только pointer, короткий status, decisions и freshness.
  Она не дублирует code, architecture или backlog и не переопределяет exact Git
  revision.
- Gate 0 acceptance/evidence остаётся историческим digest-bound фактом старой
  revision; новые bytes не переиспользуют его L1/L2/L3.

## 7. Процесс дальнейшей разработки

### 7.1. Task contract

Одна задача содержит:

- бизнес-результат и один вертикальный slice;
- 3–7 критериев приёмки;
- затрагиваемые файлы/модули;
- неизменяемые contracts и boundaries;
- явное out of scope;
- требуемые проверки и docs;
- разрешённые и запрещённые внешние действия;
- риск и lifecycle stage.

Контекст ограничивается ближайшими `AGENTS.md`, docs index, CURRENT, одним
релевантным ADR/contract, затрагиваемыми code/tests и текущим Git diff.

### 7.2. Process roles

- **Архитектор** принимает долговечное нормативное решение и impact analysis
  только при изменении contract, schema, trust boundary, authority, storage,
  migration, deployment или необратимого effect.
- **Диспетчер** формирует task contract, выбирает контекст/зоны, управляет stage
  и собирает цельный candidate.
- **Исполнитель** меняет code/tests/docs назначенной непересекающейся зоны,
  выполняет target L1 и не принимает собственный результат.
- **L2 reviewer** независимо воспроизводит главный claim frozen candidate.
- **L3 reviewer** adversarially проверяет продуктовую цель, отказы,
  безопасность, tenant isolation, idempotency и recovery.
- Reviewer не расширяет scope; необязательные улучшения идут в backlog.

Архитектор/диспетчер не является независимым reviewer собранного им candidate.
Эти роли — роли процесса Codex, а не новые runtime `AgentRole` Nobus Core.

### 7.3. Lifecycle

<!-- delivery-workflow:start -->
`TASK -> WIP_ITERATION -> CHECKPOINT -> GATE_CANDIDATE -> MERGE ->
RELEASE_PRODUCTION`
<!-- delivery-workflow:end -->

**WIP_ITERATION**

- одна задача — одна branch; один executor — непересекающаяся file zone;
- минимальная реализация, target L1 и negative test изменённой boundary;
- reviewer не запускается после каждой команды; WIP не объявляется принятым.

**CHECKPOINT**

- готов один связный slice и выполнены его критерии;
- target checks и реально изменённые trust/data/effect boundaries проверены;
- diff не содержит secrets, мусора или чужих изменений;
- создаётся local checkpoint commit; полный L2/L3 не требуется.

**GATE_CANDIDATE**

- scope завершён, revision frozen, L1 связан с exact SHA/digest;
- один независимый L2 воспроизводит важный результат;
- один adversarial L3 проверяет цель, failure paths, security, tenant isolation,
  idempotency и recovery;
- findings объединяются в один список и один пакет rework;
- полный цикл повторяется только после новой freeze изменённых normative/code
  bytes.

**MERGE**

- один PR содержит code, tests и affected docs одного slice;
- push/merge явно разрешены, exact remote revision проверена;
- защищённая `main` становится опубликованным Git-каноном после merge readback;
- Nobus Memory после принятия получает только короткий pointer/status sync.

**RELEASE_PRODUCTION**

- используется уже проверенный release candidate;
- выполняются release regression, backup, rollback, smoke, effect verification
  и post-state check;
- live effect имеет отдельную явную авторизацию;
- formal quality-L4 добавляется только для удаления данных с ПК или критического
  изменения в кабинете маркетплейса;
- release tag становится опубликованным каноном после проверки remote SHA.

Локальные docs/code/tests/commit не требуют formal quality-L4. Push, deploy,
публикация и внешняя запись всё равно требуют явной авторизации по общей
безопасности. Это development workflow; runtime
`ApprovalRequest/ApprovalDecision` может быть строже для конкретного
пользовательского effect и этим ADR не ослабляется.

## 8. Ближайшие вертикальные slices

1. Архитектурный rebaseline и единый Git-контур — этот ADR/candidate.
2. Thin Mini App owner authentication + read-only список/карточка задач.
3. Создание одной задачи из Mini App в существующем Core.
4. Единый статус и получение результата/артефакта через Telegram и Mini App.
5. Минимальные runtime approvals и recovery только для реально нужных effects.
6. Ограниченный owner smoke и release после отдельной авторизации.

Каждый slice обязан работать самостоятельно. Google/document/analytics,
multi-user и platform идеи остаются backlog до прямой нужды пути.

## 9. Последствия, риски и recovery

Положительные последствия:

- первый результат использует уже существующий runtime;
- Mini App не выпадает из MVP-1;
- нет второго Core/queue/effect authority и ранней платформенной миграции;
- development assurance платится один раз за frozen candidate, а не за каждый
  WIP шаг;
- исторический Gate 0 и recovery WIP остаются воспроизводимыми.

Риски и меры:

| Риск | Мера |
|---|---|
| публичный HTTPS расширяет attack surface | один узкий boundary, exact Telegram auth/Origin/CSP/rates, no authority/state duplication |
| локальный Core недоступен | Mini App fail-closed; task не исполняется на edge |
| два ingress создадут дубли | единый Core idempotency/state и один task identity |
| client попытается назначить authority | client fields недоверенны; Core повторно выводит route/risk/effect |
| старый Gate 1 WIP случайно вольют | отдельные worktree/refs остаются frozen; reuse только точным будущим diff |
| sealed snapshot начнут читать как roadmap | docs index и Gate index маркируют historical binding и ADR 0022 overlay |
| origin примут за публикацию | remote SHA проверяется только после разрешённого push/merge |

Recovery этого решения — forward ADR, а не переписывание ADR 0017–0021 или
Gate 0 bytes. При провале Mini App slice отключается только новый web boundary;
существующий Telegram/Core runtime и authoritative state остаются исходным
контуром. Dirty Gate 1 WIP/recovery сохраняется до отдельного решения.

## 10. Критерии пересмотра

Topology пересматривается новым ADR только если измеримо доказано хотя бы одно:

- owner PC не обеспечивает нужную доступность обязательного пути;
- публичный transport нельзя безопасно связать с локальным Core;
- единый SQLite/state writer упирается в измеренную concurrency/availability;
- появляется реальный второй пользователь с RBAC/tenant requirements;
- external effect требует отдельной host/credential boundary;
- коммерческий slice невозможно поставить без server Core migration.

Наличие framework, VPS или старого Gate-плана само по себе не является trigger.

## 11. Проверка решения

Governance regression:
[`tests/test_pre_gate1_architecture_integration.py`](../../tests/test_pre_gate1_architecture_integration.py).
Он проверяет ADR 0022 overlay, активные projections, workflow, authority и
byte-identical SHA-256 всех 20 sealed `required_sources`.

Этот ADR не разрешает product/runtime-code changes, provider/VPS/BotFather
операции, push, PR, merge, deploy, публикацию, удаление, recovery cleanup или
изменение Nobus Memory.
