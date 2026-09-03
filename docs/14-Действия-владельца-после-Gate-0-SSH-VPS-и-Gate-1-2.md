# 14. Реальные owner inputs после Gate C0

**Статус документа:** CANONICAL OWNER INPUTS
**Актуально на:** 2 сентября 2026 года
**CURRENT:** `MVP-1 PUBLISHED / LIVE RUNTIME OBSERVED / ACCEPTANCE REOPENED / PATCH REQUIRED`
**Deployment identity:** `DEPLOYMENT REVISION UNVERIFIED`
**Program boundary:** `MVP-2 HOLD`

Этот файл не выдаёт разрешение на push, PR, merge, tag/release, deploy,
provider/VPS/DNS/TLS/BotFather, credentials, live effect, Nobus Memory write,
HTML publication или Telegram delivery.

## 1. Что требуется сейчас

Владелец принимает или отклоняет exact local Gate C0 candidate по его
result SHA/tree и единому
[handoff](gates/gate-c0-mvp1-truth-contract/HANDOFF.md).

C0 восстановил фактическую границу:

- protected `main` и annotated tag `v1.0.1` указывают на `f5a9119...`;
- live runtime наблюдался 2 сентября, но текущий процесс/health и loaded
  revision не подтверждены;
- previous owner acceptance переоткрыта из-за false semantic reject одинаковой
  transform-задачи в text и после успешного voice transcript;
- forward [ADR 0023](adr/0023-modality-neutral-semantic-admission-and-core-decision.md)
  принят как TARGET, но не реализован;
- published remote READY — `STALE PUBLISHED CLAIM / PUBLICATION PENDING AUTHORIZATION`.

## 2. Следующий Gate — C1

Gate C1 можно открыть только в новом пользовательском чате от принятого exact
C0 result SHA/tree. Нельзя начинать C1 автоматически от `origin/main`, dirty
local `main` или непринятого checkpoint.

Продуктовый результат C1: text и voice-transcript после нормализации проходят
один tool-less semantic compiler; strict SemanticProposal описывает смысл без
authority; Core детерминированно выбирает capability/policy и решение. C1
использует corpus C0 как acceptance и не меняет Faster-Whisper.

**Один Gate = одна Codex-задача = один пользовательский чат.** Все Txx/Cxx,
исправления, повторные проверки и внутренние reviewers C1 остаются в этом
одном чате. Новый чат создаётся только для C2 после принятого C1 handoff.

## 3. Active closure-roadmap

| Gate | Результат | Статус |
|---|---|---|
| C0 — единая истина и контракт | local verified candidate и owner decision | CURRENT candidate |
| C1 — универсальное семантическое понимание | compiler/proposal/Core decision + corpus PASS | HOLD до принятого C0 |
| C2 — voice parity и ASR qualification | общий route и русский bake-off | HOLD до C1 |
| C3 — стабильность Core/backend/worker | retry/state/status/recovery stability | HOLD до C2 |
| C4 — завершённый frontend/user journey | Telegram/Mini App complete E2E | HOLD до C3 |
| C5 — operations/recovery/security | health, ingress, backup/restore, cleanup, rollback | HOLD до C4 |
| C6 — frozen release и owner acceptance | exact publish/activate/readback и owner smoke | HOLD до C5 |

R01–R47 — internal release checkpoints, не отдельные пользовательские чаты.

## 4. Когда нужен точный вопрос владельцу

Внутри C1–C5 отдельное решение владельца нужно только если отсутствующий выбор
меняет product scope, trust/authority/recovery invariant или требует внешней
записи. Пауза и ответ продолжают тот же Gate-чат.

Перед C6 отдельно фиксируются и авторизуются только точные действия:

1. какой frozen SHA/tree публиковать;
2. какой PR/merge/tag/release выполнять;
3. какой exact release/config активировать и какой rollback target сохранять;
4. какие provider/DNS/TLS/BotFather mutations нужны;
5. какой bounded owner smoke допустим с реальными данными/effects;
6. принимается ли итоговый exact active release как целый MVP-1.

Одна авторизация не подразумевает следующую.

## 5. Runtime approvals

Sealed документы [06](06-Регламент-качества-L1-L4.md) и
[07](07-Правила-внешней-записи.md) продолжают определять runtime
`ApprovalRequest/ApprovalDecision`. Semantic model не назначает permissions,
risk, route, approval или право на effect. Client может ответить только на
immutable server-derived challenge. Authoritative success внешнего действия
подтверждает effect receipt, а не текст модели.

Formal workspace quality-L4 нужен только перед удалением данных с ПК или
критическим изменением кабинета маркетплейса. Это не ослабляет более строгую
runtime policy конкретного effect.

## 6. Что пока не делать

- не реализовывать C1 до принятия exact C0 result;
- не начинать C2–C6 или MVP-2 раньше соответствующего handoff;
- не заменять и не устанавливать ASR до C2 bake-off/privacy decision;
- не переносить Core/token/poller на VPS;
- не создавать universal Agent Registry/Development Control platform;
- не считать C0 разрешением на code publication или deploy;
- не выполнять provider/DNS/TLS/BotFather/live smoke без точной авторизации;
- не удалять dirty WIP, live checkout, Gate 1 worktree, safety refs, bundles,
  stash или recovery files;
- не обновлять Nobus Memory и не публиковать docs 15/16.

Точный current status: [CURRENT-STATUS](handoffs/CURRENT-STATUS.md).

**C0 PERFORMED NO PUSH / PR / MERGE / TAG / DEPLOY.**
