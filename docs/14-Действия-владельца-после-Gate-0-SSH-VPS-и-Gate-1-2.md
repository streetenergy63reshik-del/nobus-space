# 14. Решения владельца и завершение Gate C2

**Статус документа:** CANONICAL OWNER INPUTS
**Актуально на:** 4 сентября 2026 года
**CURRENT:** `C1 ACCEPTED / PUBLISHED / NOT DEPLOYED`
**Локальная разработка:** `C2 BLOCKED / NOT PUBLISHED / NOT DEPLOYED`
**Deployment identity:** `DEPLOYMENT REVISION UNVERIFIED`
**Program boundary:** `MVP-2 HOLD`

Этот файл не выдаёт разрешение на push, PR, merge, tag/release, deploy,
provider/VPS/DNS/TLS/BotFather, credentials, live effect, Nobus Memory write,
HTML publication или Telegram delivery.

Активная thin topology остаётся привязана к
[ADR 0022](adr/0022-thin-miniapp-orchestrator-mvp1-and-delivery-workflow.md),
а C1 semantic boundary — к [ADR 0023](adr/0023-modality-neutral-semantic-admission-and-core-decision.md).
Telegram Mini App остаётся тонким MVP-1 ingress; полный Gate 2A —
`FROZEN / NOT CURRENT`.

## 1. Что требуется сейчас

Владелец принял exact local Gate C0 candidate
`0d6fec08dc95e252e0d9491e7bb11b78e60adcec` / tree
`e1ae77eba2f2b50a45b82883e4ac20071e145dfd`. Publication-safe projection
опубликована через [PR #9](https://github.com/streetenergy63reshik-del/nobus-space/pull/9);
точный predecessor для C1 зафиксирован в едином
[handoff](gates/gate-c0-mvp1-truth-contract/HANDOFF.md).

C0 восстановил фактическую границу:

- C0 contract publication через PR #9 дала merge `70085f8...`, tree
  `3a31914a...`; final protected-main binding после status-only sync
  фиксируется exact readback в итоговом C0-сообщении; annotated tag `v1.0.1`
  остался на `f5a9119...`;
- live runtime наблюдался 2 сентября, но текущий процесс/health и loaded
  revision не подтверждены;
- previous owner acceptance переоткрыта из-за false semantic reject одинаковой
  transform-задачи в text и после успешного voice transcript;
- forward [ADR 0023](adr/0023-modality-neutral-semantic-admission-and-core-decision.md)
  реализован и опубликован в default-off C1 через
  [PR #11](https://github.com/streetenergy63reshik-del/nobus-space/pull/11);
  product commit `2732a11122179c4197a74594dd0c8ba3ed9ec52d`;
- historical READY claim остаётся только в ancestry и superseded текущими
  active docs на protected `main`.

## 2. C1 завершён; C2 выполняется

Gate C1 выполнен в отдельном пользовательском чате от exact protected-main
predecessor `5feccfd...`, tree `480b2f85...`, а не от floating
`origin/main`, dirty local `main` или непринятого checkpoint.

Продуктовый результат C1: text и voice-transcript после нормализации проходят
один tool-less semantic compiler; strict SemanticProposal описывает смысл без
authority; Core детерминированно выбирает capability/policy и решение. C1
использует corpus C0 как acceptance и не меняет Faster-Whisper.

**Один Gate = одна Codex-задача = один пользовательский чат.** Все Txx/Cxx,
исправления, проверки и разрешённая публикация C2 продолжаются в существующей
задаче C2. Принятый C1 повторно не принимается; C3 самостоятельно не начинается.

Локальный checkpoint C2 — `96487d176cb3f09b543cadbc0e4b91c73308b8b4`,
tree `7da1e466606dec9ef7ab7bf375a30ed002b9f728`. Исправления native lifetime и
retention проверены целевыми наборами; ASR и полный готовый результат ещё
не прошли обязательные критерии. Это не разрешение включить их в live.

Владелец отдельно разрешил один ограниченный эксперимент
`Systran/faster-whisper-small@536b0662742c02347bc0e980a01041f333bce120`:
пять файлов 486214370 bytes, до 600 MB загрузки, 1,5 GiB диска, 4 GiB RAM,
четыре логических CPU и 1200 секунд суммарного локального исполнения.
Существующий стек, только синтетический корпус, без передачи аудио и pip.
Файлы скачаны и проверены: общий payload486217682B. Один dev с неизменным
decoder дал WER6,64%, critical2, raw RTFp95 0,792>0,5 — hard FAIL.
Эксперимент остановлен, holdout не открыт. Лицензионное расхождение MIT/Apache
сохранено; включение модели в продукт не принято.
Точные pins и границы — [ASR research](gates/gate-c2-voice-parity/ASR-RESEARCH.md).

Дополнительная проба small с единственным изменением beam_size8→1 отдельно
разрешена и выполнена. Dev16: WER8,85%, critical2, raw RTFp95 0,581>0,5;
50,630924s, hard FAIL. Small суммарно129,151549s из1200s, остаток1070,848451s.
Новые конфигурации после этого не запускаются.

Текущее недостающее решение: продолжать ли подготовку одного независимого
сравнения с Google Chirp3 и какой существующий Google Cloud project использовать.
Предложение: eu/ru-RU, synchronous Recognize,16 запросов без автоповторов,
синтетические156,26s audio, до10 минут и0,10USD, без GCS/resource creation.
Перед exact trial authorization нужны проверенные штатные auth/billing/region,
logging/retention, executable runner и freeze. Google Workspace-доступ не
считается разрешением Google Cloud Speech-to-Text. Облачная передача аудио
и расходы пока не разрешены; project/login/billing/IAM не изменялись.

Ранее разрешённые GigaAM и compiler не требуют повторного согласия в прежних
пределах. GigaAM использовал 194,916977 из 1800 секунд; compiler — 0 из 24
model turns, таймер 20 минут от первого turn не начат. Журналы суммарные,
новый запуск не обнуляет расход.

После закрытия B01/B02 и собственной приёмки C2 потребуется отдельное точное
разрешение на публикацию принятого SHA/tree: обычный push, PR, проверки и merge
в protected main. План должен также явно назвать возможный PR синхронизации
статуса после merge. До этого текущий BLOCKED checkpoint не публикуется.

## 3. Active closure-roadmap

| Gate | Результат | Статус |
|---|---|---|
| C0 — единая истина и контракт | published contract и exact readback | PUBLISHED / ACCEPTED |
| C1 — универсальное семантическое понимание | compiler/proposal/Core decision + corpus PASS | ACCEPTED / PUBLISHED / NOT DEPLOYED |
| C2 — voice parity и ASR qualification | общий route и русский bake-off | LOCAL CANDIDATE BLOCKED / NOT PUBLISHED |
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

- не повторять завершённую code publication C1; документация синхронизируется
  по отдельному прямому разрешению владельца;
- не начинать C3–C6 или MVP-2 раньше соответствующего handoff;
- не загружать новую ASR-модель без точного разрешения и не выбирать её для продукта до квалификации;
- не переносить Core/token/poller на VPS;
- не создавать universal Agent Registry/Development Control platform;
- не считать C0 разрешением на code publication или deploy;
- не выполнять provider/DNS/TLS/BotFather/live smoke без точной авторизации;
- не удалять dirty WIP, live checkout, Gate 1 worktree, safety refs, bundles,
  stash или recovery files;
- не обновлять Nobus Memory и не публиковать docs 15/16.

Точный current status: [CURRENT-STATUS](handoffs/CURRENT-STATUS.md).

**C1 ACCEPTED / PUBLISHED / NOT DEPLOYED. NO TAG / NO DEPLOY / NO LIVE EFFECT.**
