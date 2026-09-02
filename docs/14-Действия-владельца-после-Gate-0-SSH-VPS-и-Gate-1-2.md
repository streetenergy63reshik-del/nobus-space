# 14. Реальные owner inputs для тонкого MVP-1

**Статус документа:** CANONICAL OWNER INPUTS
**Актуально на:** 2 сентября 2026 года

Активное решение:
[ADR 0022](adr/0022-thin-miniapp-orchestrator-mvp1-and-delivery-workflow.md).
Полный распределённый Gate 2A — **FROZEN / NOT CURRENT**.

Этот файл не выдаёт разрешение на push, deploy, provider/VPS/BotFather,
publication, credentials или live effect.

## 1. Что требуется сейчас

ADR 0022 и базовый Telegram Mini App auth/list/detail/create уже опубликованы.
G2–G6 собраны и проверены: status/events/result, реальный artifact,
Telegram/Mini App parity, same-process composition, recovery и frozen
assurance. Candidate развёрнут за public HTTPS и ожидает визуальный owner smoke,
но всё ещё `NOT PUBLISHED`; общий verdict —
`MVP-1 IN PROGRESS / NOT PRODUCT READY`.

Exact revision, checks и blockers ведутся только в
[CURRENT-STATUS](handoffs/CURRENT-STATUS.md). Оставшееся решение владельца —
визуальное принятие обновлённой карточки и разрешение публикации exact release,
а не повторное принятие архитектуры.

Наличие настроенного `origin` не означает, что GitHub `main` содержит эту
историю. Опубликованный канон появляется только после разрешённых push/PR/merge
и readback exact remote SHA.

## 2. Следующий product gate — G7

**Продуктовый результат:** owner открывает Nobus Space из Telegram по public
HTTPS и проходит живой путь `create -> status/events -> verified result -> real
artifact` через один backend+frontend release.

Критерии:

1. exact HTTPS ingress/hostname и provider-bound transport выбраны и проверены;
2. Telegram BotFather/menu открывает exact deployed Mini App;
3. backend и frontend соответствуют одному frozen candidate;
4. signed live `initData` проходит exact-owner auth, а replay/foreign owner/
   stale session fail closed;
5. одна задача имеет одну identity в Telegram и Mini App, возвращает verified
   result и скачиваемый artifact с совпадающими bytes/digest;
6. unavailable/restart/recovery проверены без orphan task, дубля или утечки;
7. owner фиксирует `ACCEPT` либо один объединённый rework list.

Не входят: перенос Core/token/poller на VPS, universal Agent Registry, Web IDE,
shell, self-deploy, multi-user SaaS и Gate 3–8 platform scope.

## 3. Точные inputs и авторизации G7

Первый путь использует один `Mini App Web Boundary`: static UI + bounded
Telegram auth/session + thin API adapter за public HTTPS ingress, без своей
DB/queue/policy/effect authority.

До live activation владелец отдельно определяет или разрешает:

1. exact HTTPS ingress, hostname, provider и допустимую стоимость;
2. exact code candidate для deployment; docs-only merge не разрешает его
   публикацию или deploy;
3. provider/DNS/TLS изменения и public endpoint;
4. exact BotFather/menu mutation;
5. bounded owner smoke и допустимые live test data;
6. после G7 — публикацию принятого code candidate и G8 release tag/readback.

Выбор ingress не разрешает перенос Core, Telegram token или poller на VPS.

## 4. Когда нужен отдельный вопрос владельцу

Владелец принимает решение только если источники не разрешают один из конфликтов:

- какой exact public HTTPS ingress/hostname использовать;
- допустим ли конкретный внешний provider/cost;
- какой exact live branch/commit публиковать;
- какой bounded owner smoke выполнить с реальным Telegram effect;
- принимать ли риск, который меняет trust/authority/recovery invariant.

Обычные local docs/code/tests/checkpoint commit не требуют formal quality-L4.
Push, PR, merge, deploy, provider/DNS/TLS/BotFather mutations и live effects
требуют отдельной явной авторизации по общей безопасности.

## 5. Runtime approvals не изменены

Sealed docs
[06](06-Регламент-качества-L1-L4.md) и
[07](07-Правила-внешней-записи.md) продолжают определять product/runtime
`ApprovalRequest/ApprovalDecision`. Если будущий reachable effect потребует
подтверждения, Mini App может принять только решение по immutable server
challenge. Принятый journey create/status/result/artifact отдельного
`ApprovalRequest` не требует. Client не получает authority назначать action
details, target или risk.

Formal quality-L4 рабочего пространства добавляется только перед удалением
данных с ПК или критическим изменением кабинета маркетплейса. Это не отменяет
более строгую runtime policy конкретного пользовательского effect.

## 6. Что пока не делать

- не продолжать Gate 1/2/2A ceremony как active roadmap;
- не переносить Core/token/poller на VPS;
- не создавать universal Agent Registry или Development Control platform;
- не покупать/настраивать provider «заодно»;
- не считать эту docs-публикацию разрешением на code push/PR/merge/deploy;
- не выполнять provider/DNS/TLS/BotFather или live smoke без точной
  авторизации;
- не удалять Gate 1 worktree, safety refs, bundles, stash или recovery files;
- не обновлять Nobus Memory до принятия Git-кандидата.

После принятого merge Nobus Memory получает только короткий pointer/status sync,
а не копию ADR, roadmap или backlog.
