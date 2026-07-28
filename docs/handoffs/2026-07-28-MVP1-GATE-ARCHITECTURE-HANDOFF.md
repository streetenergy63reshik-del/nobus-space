# Handoff — архитектурная подготовка Gate 0–8 MVP-1

**Дата:** 28 июля 2026 года

**База исследований:** `9d816b35d3f419b42e24ad09ae6aadc92c33db43`

**Статус:** ARCHITECTURE READY; IMPLEMENTATION NOT STARTED

## Результат

Для каждого Gate создана отдельная задача Nobus Space, выполнены:

1. глубокое исследование GitHub, официальных документов и готовых решений;
2. отдельная product/technical architecture;
3. L1/L2/L3 соответствующего design;
4. root-интеграция контрактов и разрешение межблочных конфликтов.

Полный индекс: [`../gates/README.md`](../gates/README.md).

Сквозная архитектура:
[`../13-Интегрированная-архитектура-MVP-1.md`](../13-Интегрированная-архитектура-MVP-1.md).

## Задачи Nobus Space

| Gate | Codex task ID | Итог |
|---:|---|---|
| 0 | `019fa747-1ae7-7ab1-90f0-19583bf65b70` | Research + Baseline architecture |
| 1 | `019fa747-877d-77f1-944d-e52f8ae5523d` | Natural Language/Voice architecture |
| 2 | `019fa747-df99-7800-8694-bcabd8e87b3a` | Scope/document contracts |
| 3 | `019fa748-370d-7753-9341-cdb9d9c561b6` | Google foundation |
| 4 | `019fa748-908b-7772-96af-3c23161088ca` | Notes/Calendar/Tasks/effect plane |
| 5 | `019fa749-01e2-79a1-9e96-203bf4856535` | Document gateway/Windows Bridge |
| 6 | `019fa749-5e0f-7732-b8e9-81abd44ab709` | Multi-document analytics |
| 7 | `019fa749-cdd3-70d3-8005-517c2edb27d8` | Artifact Factory/writeback |
| 8 | `019fa74a-44cb-70e1-87cf-59cc6ff1a905` | Hybrid release/pilot |

## Принятые root-решения

- не создавать нового бота или второго framework;
- один Gate 1 `IntentEnvelope`;
- один authoritative effect SQLite store и atomic effect/job admission;
- lifecycle отделён от provider outcome;
- provider unknown отделён от Telegram delivery unknown;
- local identity снаружи Bridge — только opaque `doc_id`;
- Bridge protocol v1 read-only; Gate 7 добавляет закрытое versioned write extension;
- Docs/Calendar используют реальные preconditions;
- Sheets/Drive не симулируют strict CAS: version/copy либо fail closed;
- registry/release и Windows device keys имеют разные профили;
- official Google REST — production executor, MCP/CLI — только read-only canary;
- SQLite single-node — MVP-default; PostgreSQL только по измеримому trigger;
- один server Core/poller и один device-fenced Bridge;
- code rollback не является rollback внешних эффектов.

## Что не произошло

- runtime не запускался и не перезапускался;
- Scheduler, server, Bridge, Google и Telegram не изменялись;
- миграции, backup, deployment и publication не выполнялись;
- remote и push не выполнялись;
- ни один Gate не получил implementation PASS.

## Следующий шаг

Начать отдельную implementation-задачу Gate 0 по L4-шаблону из
[`docs/12`](../12-Эталон-MVP-1-и-дорожная-карта.md). Gate 1 implementation не
начинается до accepted Gate 0 handoff. Архитектурные задачи можно продолжать
для уточнений, но изменения shared contracts выполняются только через root
integration review.
