# Gate 2A Research — Telegram Mini App, ранний Control Plane и управление разработкой

**Статус документа:** RESEARCH

**Статус реализации:** TARGET; исследование не доказывает работающий runtime

**Дата среза:** 30 июля 2026 года

## 1. Исследовательский вопрос

Как после Gate 2, но до Google Gate 3, дать владельцу полноценный мобильный
Telegram Mini App и безопасный рабочий контур:

`естественная задача -> план -> подтверждение -> Codex -> isolated worktree ->
проверка -> local candidate commit`,

не создавая второй orchestrator, не давая модели ambient authority и не
разрешая работающему Nobus самостоятельно изменять или публиковать собственный
live release?

Второй вопрос: должны ли Google, глубокая аналитика, контент и разработка быть
функциями одного неограниченного LLM или специализированными агентами?

## 2. Зафиксированный CURRENT

На момент исследования:

- Gate 0 ещё не принят;
- Gate 1–8 не имеют implementation PASS;
- старые runtime-функции и исторические commits не доказывают новую Gate
  архитектуру;
- существующий репозиторий уже содержит FastAPI, durable Telegram/SQLite
  примитивы, Codex SDK/CLI boundary, exact patch parser и worktree-safe code
  workflow, но эти части требуют интеграции и принятия по новой дорожной карте;
- server hybrid runtime не развёрнут и не считается CURRENT.

## 3. Что подтверждает Telegram

Официальная документация Telegram Mini Apps подтверждает:

- Mini App является полноценным HTML5-интерфейсом внутри Telegram;
- приложение можно запускать из menu button, inline button, keyboard button
  или как Main Mini App;
- Mini App получает `initData` для server-side validation;
- `initDataUnsafe` не является доверенным;
- server должен проверить подпись и свежесть данных;
- Mini App может отправлять действие обратно в bot/control backend.

Источники:

- [Telegram Mini Apps](https://core.telegram.org/bots/webapps)
- [Validating data received via the Mini App](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app)

Вывод: Telegram не ограничивает реализацию owner-only task dashboard,
approvals, status, diff, evidence и artifact views. Ограничение находится не в
Telegram, а в необходимости иметь доступный HTTPS backend и корректную
server-side authority.

## 4. Почему полноценный Mini App требует ранний server foundation

Мобильный Telegram client не может надёжно обращаться к desktop localhost.
Полноценный Mini App требует:

- стабильный HTTPS origin;
- TLS certificate;
- owner authentication;
- API к authoritative task state;
- безопасную доставку событий;
- supervisor и readiness;
- один Telegram polling authority.

Если оставить authoritative Core на Windows, а Mini App API разместить на VPS,
появятся два state/control plane и сложная двусторонняя синхронизация. Поэтому
Gate 2A должен перенести минимальный Nobus Core и единственную custody bot token
на VPS. Windows становится ограниченным Development Worker, а не вторым Core.

## 5. Worktree как граница developer-задачи

Git официально поддерживает несколько linked worktree с отдельными working
trees, indexes и HEAD при общей object database:

- [git-worktree](https://git-scm.com/docs/git-worktree)

Worktree решает изоляцию файлов, но сам по себе не решает:

- разрешение репозитория;
- malicious hooks/config/filters;
- незакоммиченные пересечения;
- credentials/network;
- approval binding;
- test/evidence;
- изменение active branch;
- publication.

Поэтому Gate 2A использует Gate 2 repository registry и trusted exact-argv Git
profile. «Один task — один worktree» является execution boundary, а не
authority boundary.

## 6. Почему Forge нельзя переносить как второй стек

Исследованный Forge-подход полезен следующими идеями:

- mobile task control;
- plan gate;
- verify gate;
- isolated worktree;
- live progress;
- candidate/PR result.

Для Nobus отклонены:

- отдельный Node/Fastify/Telegraf orchestrator;
- Claude как единственный primary worker;
- tmux как authoritative task state;
- PM2 поверх целевого `systemd`;
- двусторонний Syncthing для active repositories;
- обязательный GitHub PR для каждого business task;
- direct agent push/merge/deploy.

Nobus уже использует Python/FastAPI/Pydantic/SQLite/Codex. Новый стек увеличил бы
число contracts, supervisors, credential boundaries и failure modes без
продуктовой пользы.

## 7. Минимальный web stack

В репозитории уже закреплены:

- `fastapi`;
- `uvicorn[standard]`;
- `pydantic`;
- `httpx`.

Для MVP не требуется отдельный frontend framework. Принят buildless профиль:

- статические HTML/CSS/ES modules внутри release artifact;
- FastAPI same-origin JSON API;
- SSE для server-to-client progress;
- bounded polling fallback;
- системный HTTPS edge;
- никаких npm/runtime CDN dependencies.

Это уменьшает supply-chain и deployment surface, но не урезает продуктовые
экраны.

Релевантные первичные источники:

- [FastAPI deployment concepts](https://fastapi.tiangolo.com/deployment/concepts/)
- [Starlette StreamingResponse](https://www.starlette.io/responses/#streamingresponse)
- [systemd.service](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)

## 8. HTTPS и сетевой контур

Gate 2A не фиксирует секретный hostname в Git. Он использует deployment binding
`<NOBUS_CONTROL_ORIGIN>`.

Read-only server inventory перед implementation должен выбрать:

1. уже установленный и поддерживаемый HTTPS edge; либо
2. один pinned Caddy/Nginx artifact по отдельному L4.

Инварианты одинаковы:

- public exposure только `443/tcp`;
- Uvicorn слушает loopback;
- HTTP перенаправляется на HTTPS;
- TLS renewal наблюдается;
- API и static app same-origin;
- admin/debug/docs endpoints не публикуются;
- no wildcard CORS;
- rate/size/time limits на edge и Core;
- sanitized access logs без query/body/initData.

## 9. Telegram authentication findings

Одной проверки подписи недостаточно. Нужны:

- exact configured bot identity;
- exact owner Telegram user binding;
- `auth_date` freshness;
- reject будущего/naive timestamp;
- replay-resistant login nonce;
- короткая server session;
- session generation fencing;
- one-shot approval challenge;
- task/revision/action/target/digest binding;
- server time;
- no client-supplied tenant/risk/capability.

Gate 2A использует:

1. `POST /v1/webapp/session` с raw `initData`;
2. server-side validation;
3. short-lived opaque bearer, хранимый только в памяти Mini App;
4. exact origin and session generation;
5. one-shot approval challenge для изменяющих действий.

Persistent token в `localStorage`, доверие `initDataUnsafe` и бессрочная cookie
отклонены.

## 10. Почему специализированные agents целесообразны

Google, web analytics, content и code имеют разные:

- источники;
- инструменты;
- credentials;
- типы ошибок;
- limits/cost;
- output contracts;
- verification;
- внешние effects.

Один worker с полным набором tools:

- расширяет prompt-injection blast radius;
- усложняет routing;
- смешивает provider failures;
- затрудняет бюджет и observability;
- делает L2/L3 менее независимыми.

Специализация полезна, но отдельные автономные боты/оркестраторы не нужны.
Принята модель «один Core — несколько закрытых worker profiles».

## 11. Роли MVP-1

### Nobus Core

Единственный orchestrator и authority. Принимает задачу, определяет scope,
компилирует contracts, dispatches workers, проверяет результат, исполняет
effects и доставляет итог.

### General Orchestrator Worker

- prompt enrichment;
- быстрые ответы;
- bounded public web research;
- простые внутренние задачи.

Не владеет policy и не является самим Core.

### Google Workspace Specialist

- предлагает Google query/operation plan;
- анализирует разрешённые normalized facts;
- формирует proposed effect.

Не получает OAuth и не выполняет writes напрямую.

### Research & Analytics Specialist

- глубокий web research;
- multi-document research;
- structured synthesis;
- `AnalysisResult`.

Не выполняет business calculations вместо deterministic engine.

### Content Studio Specialist

- сокращает проверенную аналитику;
- предлагает narrative/layout;
- готовит content blocks для JPEG/HTML.

Не читает произвольные источники заново и не пересчитывает значения.

### Development Specialist

- Codex primary;
- registered repository;
- isolated worktree;
- code/test/diff/candidate.

Не получает live, remote, deploy или policy authority.

## 12. Почему workers не общаются напрямую

Свободный agent-to-agent chat не даёт воспроизводимого:

- tenant binding;
- budget;
- contract revision;
- capability;
- sequence;
- cancellation;
- evidence;
- source lineage.

Вместо этого Core выполняет durable choreography:

```text
TaskContract
  -> AgentDispatch(role=A)
  -> WorkerResult(A)
  -> Core validation
  -> AgentDispatch(role=B, input=result_ref_A)
  -> WorkerResult(B)
  -> verification/effect/delivery
```

Agent result является данными, а не authority следующего agent.

## 13. Размещение компонентов

### Linux VPS

- HTTPS edge;
- FastAPI Nobus Core;
- Telegram polling;
- Mini App static files;
- Control API/SSE;
- authoritative SQLite;
- agent registry;
- server-side workers, Google adapters и analytics в последующих Gate.

### Windows PC

- отдельный Development Worker service;
- Codex SDK/CLI credentials;
- repository registry;
- isolated worktrees;
- exact tool runner;
- test sandbox;
- candidate commit adapter.

Gate 5 добавляет отдельный Document Bridge identity. Development Worker и
Document Bridge не объединяются, потому что code и owner-document authority
различаются.

## 14. Рассмотренные варианты

| Вариант | Скорость | Надёжность | Security | Решение |
|---|---:|---:|---:|---|
| Полный Forge/Node rewrite | низкая | средняя | средняя | отклонён |
| Mini App только в Gate 8 | высокая для backend, низкая продуктовая | высокая | высокая | отклонён владельцем |
| VPS Mini App + Windows остаётся вторым Core | средняя | низкая | низкая | отклонён |
| VPS Core + Windows Development Worker | средняя | высокая | высокая | принят |
| Раздельные автономные domain bots | низкая | низкая | средняя | отклонён |
| Один Core + specialist worker profiles | высокая | высокая | высокая | принят |
| Full Web IDE/terminal в Mini App | низкая | низкая | низкая | не входит MVP-1 |

## 15. Что потребуется от владельца при implementation

Gate 2A потребует action-bound решений:

- точный VPS и SSH target;
- `<NOBUS_CONTROL_ORIGIN>`;
- DNS/TLS способ;
- firewall/Tailscale changes;
- server service identity;
- перенос единственной Telegram token custody;
- BotFather menu/Main Mini App activation;
- Windows Development Worker identity/ACL;
- exact registered repository and target paths;
- exact live cutover/rollback window.

Эти значения не фиксируются в публичных docs и не являются разрешёнными одним
архитектурным документом.

## 16. Итоговый исследовательский вердикт

Гипотеза работоспособна.

- Управление разработкой через Telegram text/voice: высокая осуществимость.
- Полный owner-only Mini App в Gate 2A: осуществимо только вместе с ранним
  server/control-plane deployment.
- Разработка Gate 3–8 через принятый Gate 2A: осуществима.
- Полностью автономный self-deploy: исключён из MVP-1.
- Специализированные agents: целесообразны как worker profiles под единым Core,
  но не как отдельные authority-bearing оркестраторы.
