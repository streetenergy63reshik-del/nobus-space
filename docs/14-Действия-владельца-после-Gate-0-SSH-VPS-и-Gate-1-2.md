# 14. Реальные owner inputs для тонкого MVP-1

**Статус документа:** CANONICAL OWNER INPUTS
**Актуально на:** 25 августа 2026 года

Активное решение:
[ADR 0022](adr/0022-thin-miniapp-orchestrator-mvp1-and-delivery-workflow.md).
Полный распределённый Gate 2A — **FROZEN / NOT CURRENT**.

Этот файл не выдаёт разрешение на push, deploy, provider/VPS/BotFather,
publication, credentials или live effect.

## 1. Что требуется сейчас

1. Проверить локальный архитектурно-документационный candidate на ветке
   `docs/mvp1-thin-architecture`.
2. Принять ADR 0022 либо вернуть один объединённый rework list.
3. После принятия отдельно разрешить точные branch/commit для push и PR.

Наличие настроенного `origin` не означает, что GitHub `main` содержит эту
историю. Опубликованный канон появляется только после разрешённых push/PR/merge
и readback exact remote SHA.

## 2. Следующий vertical slice

**Результат:** owner открывает Telegram Mini App, backend аутентифицирует его и
показывает read-only список/карточку задач из существующего authoritative state.

Критерии:

1. bounded `initData` проверен server-side для exact bot/owner, freshness и
   replay;
2. short-lived opaque session не записывается в URL, `localStorage` или logs;
3. список и карточка читаются через существующий Core/state, без второй БД;
4. cross-owner/task ref, stale session и client-selected authority fail closed;
5. при недоступном local Core UI безопасно сообщает unavailable и не создаёт
   task/effect.

Не входят: task create, approvals, effects, VPS Core migration, token/poller
cutover, Agent Registry, Web IDE, shell и self-deploy.

## 3. Один будущий deployment input

Первый путь использует один `Mini App Web Boundary`: static UI + bounded
Telegram auth/session + thin API adapter за public HTTPS ingress, без своей
DB/queue/policy/effect authority.

Перед implementation нужен read-only выбор совместимого HTTPS ingress и
hostname. Если его создание/настройка меняет provider, DNS, TLS, стоимость или
публикует endpoint, владелец отдельно авторизует exact target и действие.
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
`ApprovalRequest/ApprovalDecision`. Mini App может принять только решение по
immutable server challenge. Он не получает action details, target, risk или
effect authority от клиента.

Formal quality-L4 рабочего пространства добавляется только перед удалением
данных с ПК или критическим изменением кабинета маркетплейса. Это не отменяет
более строгую runtime policy конкретного пользовательского effect.

## 6. Что пока не делать

- не продолжать Gate 1/2/2A ceremony как active roadmap;
- не переносить Core/token/poller на VPS;
- не создавать universal Agent Registry или Development Control platform;
- не покупать/настраивать provider «заодно»;
- не выполнять push/PR/merge/deploy без точной авторизации;
- не удалять Gate 1 worktree, safety refs, bundles, stash или recovery files;
- не обновлять Nobus Memory до принятия Git-кандидата.

После принятого merge Nobus Memory получает только короткий pointer/status sync,
а не копию ADR, roadmap или backlog.
