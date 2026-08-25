# Nobus Space MVP-1

Nobus Space развивается как owner-bound Telegram-оркестратор с обязательным
тонким Telegram Mini App поверх существующего локального Windows Core/Codex
runtime.

Активное архитектурное решение:
[ADR 0022](docs/adr/0022-thin-miniapp-orchestrator-mvp1-and-delivery-workflow.md).

## Publication binding — 25 августа 2026 года

- репозиторий `streetenergy63reshik-del/nobus-space` публичный;
- принятый опубликованный канон — exact revision, достижимая из защищённой
  GitHub `main` после live readback; этот файл не дублирует подвижный SHA;
- содержащая этот файл revision вне защищённой `main` является
  `GATE_CANDIDATE`; после разрешённого merge и проверки достижимости та же
  revision становится частью `ACCEPTED_PUBLISHED_BASELINE`;
- baseline `main` при заморозке архитектурного кандидата:
  `8b896fbca9b23c8751d651d14a122506338b5827`;
- исходный head PR [#1](https://github.com/streetenergy63reshik-del/nobus-space/pull/1)
  до post-publication refresh:
  `d3a235e4db2257826d5a5c5661a709c442be981e`; живой статус PR и head читать
  в GitHub, а не из постоянного документа;
- снимок защиты `main` на 25 августа 2026 года: требуется pull request и
  закрытие всех обсуждений, запрещены bypass, force-push и удаление ветки;
  обязательные status checks не настроены;
- локальный owner-bound Telegram/Core/Codex runtime существует; точное live
  состояние процессов в этой docs-задаче не проверялось;
- Gate 0 принят как исторический sealed snapshot @
  `f5086b2a71a9ae22be3c858ff69453287f6925da`; его 20 digest-bound sources
  не изменяются;
- Gate 1 implementation существует только как dirty
  `HOLD / NOT_ACCEPTED` WIP в отдельном worktree; его нельзя считать каноном;
- Telegram Mini App и Telegram-оркестратор обязательны в MVP-1 и используют
  один Core, одну queue/state model и одну effect authority;
- полный распределённый Gate 2A — **FROZEN / NOT CURRENT**.

Git-репозиторий — источник истины для code/tests/ADR/CURRENT/docs. Nobus Memory
хранит только pointer, короткий status, decisions и freshness и не
переопределяет exact Git revision.

Точный фактический статус:
[CURRENT-STATUS](docs/handoffs/CURRENT-STATUS.md). Иерархия источников и
навигация: [docs/README.md](docs/README.md).

## Обязательный MVP-путь

```text
Telegram Mini App -> owner authentication / Telegram initData
  -> existing Nobus Core -> local Codex/runtime
  -> authoritative state -> Telegram/Mini App status/result/artifact
```

Первый новый deployment unit — один `Mini App Web Boundary`: static UI,
Telegram auth/session и тонкий API adapter за публичным HTTPS ingress. У него
нет собственной БД, queue, policy/effect authority или Agent Registry.

## Что дальше

Следующий самостоятельный slice:
**thin Mini App owner authentication + read-only список/карточка задач**.
Он не создаёт задачи, не выполняет effects, не переносит Core/token/poller на
VPS и не вводит второй state store.

Критерии slice:

1. backend проверяет bounded Telegram `initData`, exact bot/owner, freshness и
   replay;
2. короткая opaque session не попадает в URL, `localStorage` или logs;
3. список/карточка читаются из существующего authoritative state;
4. cross-owner/task ref и client-selected authority отклоняются;
5. при недоступном локальном Core UI fail-closed и ничего не исполняет.

## Локальная проверка документационного кандидата

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  tests/test_pre_gate1_architecture_integration.py `
  tests/test_documentation.py
git diff --check
```

Product/runtime-код этим rebaseline и обновлением publication binding не
изменяется. Наличие commit или PR само по себе не разрешает push, merge,
deploy, recovery, удаление или запись в Nobus Memory: каждое внешнее действие
требует отдельной точной авторизации владельца.

Локальные правила разработки: [AGENTS.md](AGENTS.md).
