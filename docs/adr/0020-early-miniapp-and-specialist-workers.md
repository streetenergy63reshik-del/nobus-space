# ADR 0020 — Ранний Mini App Control Plane и специализированные workers

**Статус ADR:** ACCEPTED

**Статус реализации:** TARGET

**Дата:** 30 июля 2026 года

## Контекст

Каноническая дорожная карта MVP-1 описывала Natural Language, Google,
документы, аналитику, артефакты и итоговый hybrid release, но не содержала
раннего сквозного продукта для управления разработкой самого Nobus через
Telegram. Полноценный Telegram Mini App был отложен до финального release Gate,
поэтому владелец не мог использовать Nobus как мобильную станцию разработки
Gate 3–8.

Одновременно продуктовые функции Google, глубокой аналитики, визуального
контента и разработки не должны превращать Nobus Core в одного
неограниченного «суперагента». Уже принятый ADR 0002 требует
детерминированное Core и сменные workers с минимальными capabilities.

## Решение

### 1. Gate 2A является обязательным Gate MVP-1

После принятия Gate 2 и до Gate 3 вводится Gate 2A:

`Telegram Mini App, Server Control Plane and Development Worker`.

Gate 2A включает всё необходимое для реально доступного owner-only Mini App:

- ранний Linux Server Core foundation под `systemd`;
- один server-held Telegram token и один fenced polling consumer;
- HTTPS origin и same-origin Control API;
- Telegram Mini App с task, plan, approval, event, diff, evidence, artifact,
  agent и health views;
- server-side validation Telegram `initData`, exact owner binding,
  short-lived session и one-shot action-bound approvals;
- durable task/job/approval/effect/outbox authority;
- Windows Development Worker под отдельной service identity;
- outbound authenticated worker transport;
- Codex primary development worker;
- один code task — один зарегистрированный isolated Git worktree;
- local candidate commit/ref без remote, push, deploy или self-update.

Gate 8 больше не является первым server deployment. Он выполняет финальную
интеграцию всех доменов, hardening, recovery drill и 72-часовой pilot.

### 2. Mini App и Telegram chat используют одно Core

Mini App не создаёт второй orchestrator, queue, policy engine или state store.
Telegram text/voice остаётся основным способом постановки задачи. Mini App
даёт мобильные task views, approvals, progress, evidence, artifacts и agent
status поверх тех же durable IDs и transitions.

Клиентская часть не является authority. `initDataUnsafe`, client timestamps,
tenant, actor, risk, route, capabilities, approval payload и task state
повторно не принимаются от браузера как доверенные.

### 3. Nobus остаётся единственным оркестратором

Nobus Core:

- аутентифицирует владельца;
- нормализует intent;
- компилирует закрытый Task/Agent contract;
- выбирает worker profile;
- назначает scope, policy, budget и deadlines;
- владеет durable state, approvals, effects, reconciliation и delivery;
- принимает или отклоняет WorkerEvent/WorkerResult;
- собирает проверенный итог.

Модели и специализированные workers не выбирают себе полномочия и не
выполняют внешние действия напрямую.

### 4. Специализация реализуется worker-профилями

MVP-1 использует закрытый `AgentRole` registry:

- `general_orchestrator_worker` — prompt enrichment, быстрые ответы и
  ограниченный public web research;
- `google_workspace_specialist` — планирование Workspace-запросов и анализ
  нормализованных Google facts;
- `research_analytics_specialist` — глубокий web/multi-document research и
  один `AnalysisResult`;
- `content_studio_specialist` — narrative/layout proposal из проверенного
  `AnalysisResult`, без пересчёта метрик;
- `development_specialist` — Codex в зарегистрированном isolated worktree.

Это логические execution roles, а не отдельные Telegram-боты и не отдельные
authority domains. Для MVP они могут работать как профили модульного монолита
или отдельный device worker там, где этого требует host boundary.

### 5. Нет свободного agent-to-agent чата

Workers не вызывают друг друга напрямую. Составная задача проходит через
Core:

`TaskContract -> AgentDispatch -> WorkerResult -> Core validation ->
next AgentDispatch`.

Каждый переход durable, tenant-bound, version/digest-bound и наблюдаем в
Mini App. Worker output остаётся недоверенным input следующего шага.

### 6. Google authority остаётся у application adapters

`google_workspace_specialist` не получает OAuth token и не вызывает write API
как модельный tool. Core-owned Google adapters выполняют metadata/read
операции и внешние effects. Worker получает только разрешённые
нормализованные данные либо закрытый read result. Calendar/Tasks/Drive writes
исполняются только через единый effect plane.

### 7. Self-development не является self-deployment

Стабильный release `N` может разработать candidate `N+1`, но не изменяет
собственные live bytes, active service, policy, prompts, skills или approval
rules.

Допустимы только:

- registered repository;
- exact base commit;
- isolated worktree;
- allowed target paths;
- bounded exact-argv tools;
- tests без production credentials и незапрошенной сети;
- exact patch/evidence;
- local candidate commit/ref после action-bound owner approval.

Integration, push, deployment, service restart и публикация остаются
отдельными owner-authorized actions.

## Последствия

Положительные:

- владелец получает полноценный мобильный Control Center до Gate 3;
- Gate 3–8 можно разрабатывать через принятый Gate 2A;
- глубокие домены изолируются по worker profiles без второго orchestrator;
- Google OAuth, filesystem и external effects не попадают в model authority;
- интерфейс approvals становится проще без ослабления trust boundaries.

Цена:

- server foundation, HTTPS, Telegram WebApp auth, generic durable control/effect
  primitives и Windows Development Worker переходят в ранний Gate;
- Gate 2A становится крупнее и требует отдельного deployment/acceptance L4;
- Gate 4 специализирует уже существующий effect plane для Notes/Calendar/Tasks,
  а не создаёт второй;
- Gate 5 расширяет общий device-worker transport документными capabilities,
  не переопределяя его;
- Gate 8 должен различать ранний development release и финальный MVP-1 release.

## Отклонённые альтернативы

1. **Отложить Mini App до Gate 8.** Отклонено: владелец не сможет использовать
   Nobus для мобильного управления разработкой последующих Gate.
2. **Создать отдельный Forge/Node orchestrator.** Отклонено: появляется второй
   Core, state store, policy и Telegram control path.
3. **Разрешить модели прямые Google/filesystem/Git tools.** Отклонено:
   authority становится неаудируемой и prompt injection получает эффект.
4. **Свободный peer-to-peer multi-agent chat.** Отклонено: теряются durable
   ownership, бюджет, tenant binding и воспроизводимость.
5. **Автономный self-deploy.** Отклонено для MVP-1: один дефект может уничтожить
   управляющий и восстанавливающий контур одновременно.

## Проверка

Решение считается реализованным только после принятия Gate 0, 1, 2 и 2A,
включая:

- owner-only Mini App auth/replay/expiry/CSRF tests;
- same-origin API и sanitized event stream;
- one-poller/token-custody proof;
- durable restart and approval recovery;
- agent registry/capability/tenant tests;
- isolated worktree and exact patch tests;
- no-live-self-write, no-remote and no-secret tests;
- local candidate commit readback;
- independent L1/L2/L3;
- bounded live Telegram/Mini App smoke по отдельному L4.
