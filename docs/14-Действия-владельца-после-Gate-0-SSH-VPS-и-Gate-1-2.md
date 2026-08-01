# Действия владельца после Gate 0: Gate 1, Gate 2, SSH и VPS

**Статус документа:** CANONICAL OWNER RUNBOOK
**Дата:** 1 августа 2026 года

## 1. Текущая точка

Gate 0 завершён и immutable accepted:

- result commit: `f5086b2a71a9ae22be3c858ff69453287f6925da`;
- result tree: `2e3248eb295b1627d36f196c26dfc21c6ebd90fd`;
- acceptance: [`gate-00-product-contract-baseline/GATE-0-ACCEPTANCE.json`](gates/gate-00-product-contract-baseline/GATE-0-ACCEPTANCE.json).

Следующий разрешённый этап — Gate 1. Gate 2 ожидает accepted handoff Gate 1.
Gate 2A ожидает accepted Gate 2. Точный CURRENT ведётся в
[`CURRENT-STATUS`](handoffs/CURRENT-STATUS.md).


### Известная post-seal validation note

Focused повторный запуск Gate 0 после acceptance даёт `6 passed, 2 failed`;
оба FAIL относятся к helper/test-harness: `prepare_precapture()` удаляет уже tracked независимые submissions, а
следующий tracked-topology scan ожидает эти файлы на месте. Это не меняет exact
Gate 0 acceptance и не связано с содержанием этого runbook, но повторное
использование precapture generator из sealed checkout требует отдельного
TDD maintenance cycle. Следующая разработка не должна скрывать эти FAIL или
«лечить» их перезаписью immutable Gate 0 evidence.
## 2. Не смешивать три разных контура

| Контур | Когда нужен | Для чего | Не является |
|---|---|---|---|
| Локальная разработка Gate 1/2 | сейчас | код, тесты, evidence и локальные commits | VPS deployment |
| Git SSH | опционально после выбора private Git hosting | remote backup/collaboration и будущий push | доступом к VPS |
| VPS SSH | подготовка к Gate 2A live | администрирование конкретного Linux VPS | Git credential или Telegram credential |

Для Git hosting и VPS используются разные SSH-ключи. Приватные ключи, bot
token, credentials и raw connection strings не передаются в чат, Markdown,
Git, logs или evidence. Допустимо фиксировать только public key, SHA-256
fingerprint и opaque resource identifier.

## 3. Что делать сейчас: Gate 1

VPS, domain, DNS, TLS, BotFather и Git remote для Gate 1 не требуются.

1. Оставить Gate 0 acceptance неизменным.
2. Передать разработке следующий L4:

```text
Разрешаю Gate 1 MVP-1 Nobus Space.

Разрешаю локальные изменения Natural Intent Kernel, IntentEnvelope, voice/text
parity, scoped conversation context, clarification flow и safe error taxonomy.
Разрешаю unit/integration/fault/full tests, L1/L2/L3, один локальный commit и
GATE-1-HANDOFF.

Запрещаю live bot/Bridge start, реальные Google/Telegram effects, чтение owner
documents, server deployment, remote и push. Slash-команды оставить только
compatibility fallback. При ослаблении tenant/effect boundary остановиться.
```

3. Принять Gate 1 только после точного result commit/tree, локальных проверок,
   независимых L1/L2/L3 и immutable `GATE-1-HANDOFF`.
4. Не переходить к Gate 2 по одному сообщению о passing tests без accepted
   handoff.

## 4. После принятия Gate 1: Gate 2

Gate 2 также выполняется локально и не требует VPS/SSH.

1. Подтвердить owner root только для metadata-only scan:
   `C:\Хранилище\АГЕНТ`.
2. Подтвердить единственную тестовую область записи:
   `C:\Хранилище\АГЕНТ\PROстранство\ОРКЕСТРАТОР\TestTemp\Gate2`.
3. Убедиться, что `VPN данные`, ambient `Системные`, backups, VCS internals,
   runtime/cache/temp, secret-like, hard-link и reparse paths остаются закрыты.
4. Передать разработке следующий L4:

```text
Разрешаю Gate 2 MVP-1 Nobus Space.

Разрешаю реализовать Intent/Document/Analysis/Artifact/Write contracts,
source/output/deny registries, metadata-only scan C:\Хранилище\АГЕНТ и
тестовые операции только в
C:\Хранилище\АГЕНТ\PROстранство\ОРКЕСТРАТОР\TestTemp\Gate2. Разрешаю
L1/L2/L3, один локальный commit и GATE-2-HANDOFF.

Всегда исключить VPN данные, ambient/нерегистрированное чтение Системные,
Nobus memory backups, VCS internals/runtime/cache/temp/secret-like paths,
multiple-link files/hard-link aliases и reparse points. Allowlisted ordinary
code/tool resources внутри Системные доступны только через registry. Nobus
memory читать только отдельным adapter. Запрещаю реальные document
contents/writes, Google writes, live runtime, remote и push.
```

5. Принять Gate 2 только по тем же правилам exact binding и независимых review.

## 5. Gate 2A делится на offline и live

### 5.1. Offline candidate

Сначала без VPS-действий разрабатываются contracts, Core/Control API, Mini App,
server packaging, Windows Development Worker и synthetic tests. Offline L4 из
[`Gate 2A ARCHITECTURE`](gates/gate-02a-miniapp-development-control/ARCHITECTURE.md#221-implementation-l4)
прямо запрещает SSH, deployment, BotFather, Telegram cutover, remote и push.

### 5.2. Owner inputs для будущего live L4

После offline PASS подготовить и передать только обезличенные значения:

- `[VPS_PROVIDER]`, `[VPS_REGION]`, `[LINUX_DISTRO_VERSION]`, размер VPS и
  opaque server ID;
- `[VPS_HOST_FINGERPRINT]` и fingerprint отдельного admin public key;
- `[DOMAIN]`, `[NOBUS_CONTROL_ORIGIN]`, управляемые DNS record IDs;
- `[TLS_EDGE]` после read-only inventory существующего Nginx/Caddy/managed edge;
- `[BACKUP_PATHS]`, off-host backup destination, retention и restore owner;
- server service identity, Windows Development Worker identity и allowed
  repository ID;
- подтверждение доступа к BotFather и Telegram token custody без передачи
  самого token;
- способ non-interactive Codex authentication для VPS shadow benchmark без
  записи session material в Git или чат.

Live activation разрешается только отдельным exact action-bound L4 из
[`Gate 2A ARCHITECTURE`](gates/gate-02a-miniapp-development-control/ARCHITECTURE.md#222-live-activation-l4).

Любое выполняемое агентом создание VPS, public network, DNS record, firewall
rule, платного ресурса или иное изменение provider state требует отдельного
exact resource-bound L4 до первой мутации. Такое L4 связывает opaque
provider account/project, region/zone, image+version, plan, disk, network,
public IP, backups и exact resource ID/label; фиксирует currency, one-time и
recurring ceiling, renewal/termination condition, одну mutation без retry и
обязательный post-readback. Mismatch, unknown state или ошибка означают stop
без второй mutation. Выбор параметров в этом runbook не является разрешением
на provisioning или расходы.

## 6. Если нужен private Git remote

Сейчас `git remote` в repository не настроен. Это не блокирует Gate 1/2.

1. Выбрать private Git hosting и создать пустой private repository.
2. На рабочем ПК создать отдельный Ed25519-ключ с понятным именем, например
   `id_ed25519_nobus_git`. Для interactive admin key задать непустую passphrase,
   ограничить ACL private key только владельцем и использовать локальный agent.
3. Добавить hosting-провайдеру только `.pub` key и сверить его SHA-256
   fingerprint. Ed25519 является штатным типом в актуальном OpenSSH
   [`ssh-keygen`](https://man.openbsd.org/ssh-keygen).
4. Проверить host key провайдера по официальному каналу и записать exact
   fingerprint в pinned `known_hosts`; слепой TOFU запрещён.
5. Выполнить authentication smoke без push. Заранее определить owner,
   процедуру revoke/rotation и срок пересмотра ключа.
6. Отдельным L4 разрешить exact `remote add` и первый push exact branch/commit.
   До такого L4 не добавлять remote и не публиковать repository.

## 7. Подготовка VPS SSH перед Gate 2A live

1. Выбрать provider, region, поддерживаемый Linux LTS, ресурсы, public network,
   backup и recovery console. До выбора distro не копировать случайный набор
   shell-команд из Интернета.
2. Создать отдельный Ed25519-ключ, например `id_ed25519_nobus_vps`. Не
   переиспользовать Git key; для interactive admin key обязательны непустая
   passphrase, restrictive local ACL и agent.
3. Установить на VPS только public key. Fingerprint server host key получить
   через provider console или другой независимый канал, сравнить до trust и
   закрепить в `known_hosts`; TOFU не является достаточным evidence.
4. Первый вход выполнить по exact IP/hostname и отдельному ключу. Создать
   non-root admin с минимальным `sudo` только по distro-specific runbook.
5. Держать provider recovery console и bootstrap session открытыми. В рамках
   отдельного hardening L4 сначала подготовить candidate config с требуемыми
   `PasswordAuthentication` и `PermitRootLogin`, затем проверить уже
   отредактированные bytes через `sshd -t` до применения.
6. Только после успешного syntax check выполнить reload, а не необратимый
   restart; открыть новую IPv4/IPv6 SSH-сессию, доказать key login + `sudo` и
   readback применённой password/root policy. Лишь после этого закрывать
   bootstrap session. При любой ошибке выполнить заранее определённый rollback
   через ещё открытую session/provider console. Значения этих параметров
   определяются `sshd_config`. См. официальный
   [`sshd_config`](https://man.openbsd.org/sshd_config).
7. Firewall менять staged: сначала добавить exact SSH allow rule, затем deny,
   не закрывая console/bootstrap session; после применения доказать свежую
   IPv4/IPv6 SSH-сессию и при failure откатить правило. Публичные `80/443` —
   только для проверенного HTTPS edge. Uvicorn остаётся на loopback; публичный
   Uvicorn, self-signed mobile TLS, debug/admin/docs endpoints запрещены.
8. Снять sanitized inventory ОС, storage, time sync, firewall, DNS/TLS edge и
   backup readiness. Не устанавливать Nobus Core до accepted offline Gate 2A и
   exact live L4. Для VPS key заранее зафиксировать revoke/rotation plan.

## 8. Порядок live cutover Gate 2A

1. Freeze нового admission и reconciliation незавершённых effects.
2. Backup точного набора runtime DB и проверка restore path.
3. Action-bound disable/fence прежнего Windows Scheduler/poller, исключить его
   автоматический restart и доказать zero old runner.
4. Если exclusive custody доказана, передать действующий token в server
   boundary и удалить старую копию с Windows host. Если custody неизвестна или
   могла сохраниться, отдельным BotFather-bound L4 выполнить rotation, доказать
   invalidation старого token и поместить новый secret только в
   root/service-readable credential channel. Rollback не восстанавливает
   invalid token или недоказанную custody. Token запрещён в argv, shell history,
   unit text, logs и backups.
5. Установить exact immutable release под `systemd`. Polling должен оставаться
   gated, пока новый Core не получит единственную singleton lease/generation.
6. После lease acquisition доказать readiness, dedupe и fencing и только затем
   разрешить polling ровно одному server worker.
7. Подключить один Windows Development Worker с отдельной identity.
8. Активировать Mini App menu только после HTTPS и server-side Telegram auth.
   Приём raw `initData` имеет exact body/size/time bounds и exact bot binding;
   проверка использует официальный HMAC-SHA-256 algorithm с constant-time
   comparison, а официальный Ed25519 flow — только как documented third-party
   validation. Обязательны `auth_date` max-age/future-skew, replay/session
   binding и отдельная owner authorization после authentication.
   `initDataUnsafe` не является authority. До menu activation также доказаны
   exact HTTPS Origin/Host и same-origin API, CSP, rate/body-size limits и
   short-lived opaque bearer, который хранится только в памяти и не попадает в
   URL, `localStorage`, logs или evidence. См. официальную документацию
   [Telegram Mini Apps](https://core.telegram.org/bots/webapps).
9. Выполнить один bounded synthetic developer-task smoke и сохранить только
   local candidate commit. Remote/push/deploy candidate запрещены без нового L4.
10. При любой ошибке mutation прекратить admission/dispatch, сохранить old
    runner fenced и не повторять, не возвращать token custody и не включать
    poller без нового exact rollback/recovery L4.

## 9. Что пока не делать

- Не покупать и не настраивать VPS ради Gate 1 или Gate 2.
- Не переносить текущего Telegram bot runner до Gate 2A live cutover.
- Не настраивать Tailscale: он относится к Gate 5 и не заменяет application
  authentication/authorization.
- Не начинать Google OAuth: это Gate 3 после accepted Gate 2A.
- Не публиковать Git repository и не выполнять deploy «заодно» с SSH setup.

## 10. Короткая последовательность владельца

```text
Gate 0 accepted
  -> выдать локальный L4 Gate 1
  -> принять Gate 1 handoff
  -> подтвердить metadata-only root/TestTemp и выдать L4 Gate 2
  -> принять Gate 2 handoff
  -> выдать offline L4 Gate 2A
  -> принять offline candidate
  -> подготовить отдельный VPS SSH + domain/DNS/TLS/backup/identity inputs
  -> выдать exact live L4 Gate 2A
  -> один fenced cutover и acceptance
  -> Gate 3 Google Foundation
```
