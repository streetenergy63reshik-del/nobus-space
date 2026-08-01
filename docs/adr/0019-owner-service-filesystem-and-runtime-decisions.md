# ADR 0019 — Решения владельца по сервисам, filesystem authority и runtime

**Статус ADR:** ACCEPTED

**Статус реализации:** TARGET

**Дата:** 28 июля 2026 года

## Контекст

После архитектурного исследования Gate 0–8 владелец Nobus Space закрыл
продуктовые и конфигурационные вопросы по Google, Codex, Windows Bridge,
локальной библиотеке, платным fallback, monitoring, backup и пилоту.

Это решение параметризует уже принятые ADR 0017 и ADR 0018. Оно не разрешает
регистрацию сервиса, оплату, OAuth-подключение, установку, миграцию, публикацию
или иной внешний эффект без отдельного action-bound L4 соответствующего Gate.

## Решение

### 1. Владелец и approvals

- Только владелец Nobus Space выдаёт L4, расширяет права и повышает бюджеты.
- Raw owner/client content не передаётся в eval/trace service.
- Неавторитетная sanitized telemetry по умолчанию хранится 30 дней. Этот срок
  не применяется к technical logs, TaskContract, verification, approvals,
  audit/external receipts и incidents: для них действует канонический retention
  из [политики памяти](../10-Политика-памяти.md).
- Clientless owner work сохраняет `client_ref=null` только для явно
  clientless registry entry; `null` никогда не является wildcard или обходом
  project/client binding.
- Gitleaks остаётся release/test reinforcement и не получает runtime-доступ к
  содержимому owner documents; обязательный runtime classifier остаётся
  отдельным закрытым компонентом.
- Неоднозначный внешний outcome переводится в manual review; blind retry
  запрещён.

### 2. Google identity и environments

- Основной аккаунт — личный Gmail владельца; домен и возможность разместить
  privacy policy доступны.
- Development, canary/test и production получают отдельные Google Cloud
  environments и OAuth clients.
- Drive discovery охватывает My Drive и обычные файлы/папки, которыми поделились
  с владельцем. Google Workspace Shared Drives не заявляются как обязательный
  MVP-1 scope.
- Целевой read scope — Drive-wide metadata/content read через
  `drive.readonly`; write остаётся узким и выполняется только через официальные
  adapters, разрешённые destinations и отдельные write scopes.
- OAuth verification, публикация consent screen и фактическая доступность scopes
  проверяются заново по официальной документации в Gate 3.

### 3. Google effects и Gemini

- Calendar: create/update; delete/cancel — только с отдельным подтверждением.
- Tasks: create/update/complete; delete — только с отдельным подтверждением.
- Drive/Docs/Sheets: create и new-version semantics разрешены; произвольная
  молчаливая перезапись запрещена.
- In-place update разрешается только для доказанного provider precondition либо
  утверждённого шаблона с preview, revision/digest binding, readback и owner
  confirmation.
- Для non-public model calls предпочтителен EU/EEA route при фактической
  доступности нужной модели. Если допустимый route отсутствует, Core
  останавливается и запрашивает владельца.
- В Google provider boundary `CONFIDENTIAL` допускается только в отдельно
  управляемый strict Vertex route с выключенными request/response logging,
  Files и cache и только когда source registry явно разрешает
  `vertex_strict`. Это максимально допустимый route, а не blanket
  authorization.
- Domain/source deny policy имеет приоритет: raw Business Notes остаются
  local-only; `RESTRICTED` и `SECRET` не передаются никакой модели. Secret
  material не передаётся модели никогда.
- Gemini Developer API может быть opt-in fallback только для `PUBLIC` и
  `INTERNAL`; для `CONFIDENTIAL` он запрещён.
- Google Document AI и Cloud Speech-to-Text подключаются только после benchmark,
  оценки стоимости и отдельного L4.
- До утверждения benchmark и денежных ceilings платные production-вызовы
  запрещены.

### 4. Codex production route

- Основной worker не использует OpenAI API по умолчанию.
- Целевой путь — persistent официальный Codex app-server/SDK из поставки Codex
  CLI через существующий Codex-доступ владельца.
- Одноразовый `codex exec` допускается только как bounded fallback, а не основной
  worker.
- До server promotion путь проходит VPS shadow benchmark без внешних эффектов:
  non-interactive authentication, service restart, session continuity,
  structured output, timeout/cancel, concurrency, длительный research,
  subscription limits и наблюдаемое потребление.
- Если CLI-путь не проходит benchmark либо не допускает устойчивый server
  runtime, система останавливается. OpenAI API не включается автоматически:
  владельцу сначала представляются три сценария стоимости и сравнительная
  надёжность.

### 5. Owner library и локальная authority

- Максимальная локальная граница — `C:\Хранилище\АГЕНТ`.
- Внутри неё Nobus может читать, создавать и изменять обычные бизнес-документы,
  исходный код и материалы будущих project/agent контуров, но только через
  versioned registry, tenant/project binding и закрытые Bridge operations.
- Модель не получает ambient filesystem, shell, абсолютный root или credentials.
- Выход за owner root запрещён.
- Всегда защищены:
  - `C:\Хранилище\АГЕНТ\VPN данные`;
  - credentials, tokens, cookies, private keys, browser/OAuth profiles и secret
    stores;
  - ambient/model-доступ к внутренним `.git` objects/config/refs; рабочее
    дерево исходного кода остаётся доступным через code workflow;
  - runtime databases, backup sets, caches, temp и logs вне специальных
    migration/backup/restore процедур;
  - files with `NumberOfLinks > 1` и доказанные hard-link aliases без
    исключений; обычный NTFS-файл с `NumberOfLinks = 1` допустим; reparse
    points, symlinks и junction запрещены;
  - канонический Nobus Memory вне curated adapter.
- Обычные allowlisted code/tool resources внутри каталога `Системные` могут
  входить в точный registry scope. Ambient или нерегистрированное чтение всего
  каталога запрещено; secret-like resources остаются always-deny.
- Данные project/client контуров не смешиваются автоматически. В MVP-1 agent
  является execution role внутри exact project/client scope, а не отдельной
  authority boundary. Явный cross-project запрос владельца создаёт отдельный
  scoped contract и не снимает tenant/client checks.

### 6. Versioning и code changes

- Поддерживаемые MVP-1 форматы: DOCX, XLSX, CSV, PDF, TXT, MD, HTML, JPEG и PNG.
- PPTX, legacy XLS, arbitrary ZIP ingestion, password-protected documents и
  формальный PDF/UA не входят в обязательный MVP-1.
- Для бизнес-документов default — новая версия с понятным номером/маркером.
- Изменение существующего бизнес-документа требует snapshot, diff/preview,
  digest/revision binding, atomic/CAS semantics где применимо, confirmation и
  readback.
- Исходный owner request «исправь/реализуй/доработай» разрешает подготовить
  code patch. Кандидат применяется к exact base HEAD в disposable OS sandbox с
  read-only source snapshot, без credentials/network и с bounded output; там
  выполняются L1/L2/L3.
- Pre-state manifest связывает HEAD, expected branch ref, index-tree digest,
  worktree-status digest и digests затронутых paths. Чужие staged/uncommitted
  изменения не включаются: пересечение с target paths вызывает fail-closed;
  `stash/reset/checkout` для их удаления запрещены.
- L4 связывает pre-state manifest, exact patch, file/delete manifest и test
  evidence. Trusted adapter использует закрытый exact-argv Git plumbing profile:
  hooks, signing, pager, fsmonitor, external diff и clean/smudge filters не
  исполняются; system/global/repository executable config не доверяется.
  Inherited `GIT_*` scrubbed; explicit Git paths проходят containment. External
  object/index/worktree redirection, alternates, grafts и replace refs запрещены.
- Adapter создаёт commit и candidate ref через expected-old-value CAS, не меняя
  caller worktree/index. Обновление active branch/working tree допускается тем
  же L4 только при точном clean precondition; иначе остаётся candidate ref либо
  требуется новое решение владельца. Post-commit tree/diff/readback должны
  совпасть с L4.
- Изменение config, hooks, remotes, credentials и submodules, а также
  fetch/pull/push и любой Git network запрещены. Копии каждого исходного файла
  не создаются.
- Удаление, publication, deployment, remote, push и access changes всегда
  требуют отдельного action-bound L4.

### 7. Windows Bridge и сеть

- Tailscale account пока отсутствует; его подключение на Gate 5 разрешено.
- VPS и Windows PC могут быть добавлены в один tailnet; платный тариф требует
  отдельного согласования после проверки необходимости.
- Bridge работает как WinSW service под отдельной service identity с
  минимальными ACL, без паролей и токенов в config/env/argv/logs.
- Tailscale предоставляет reachability, но не application authority; остаются
  mTLS, device binding, signed jobs, nonce/sequence и generation fencing.
- При выключенном ПК local operations переходят в `DEGRADED` и ожидают
  восстановления Bridge; обходной runner не запускается.

### 8. Test resources, recovery и monitoring

- Разрешено подготовить изолированные test Calendar, Task list, Drive folder,
  Docs/Sheets, Telegram topic и local input/output roots, но их фактическое
  создание остаётся отдельным Gate-bound действием.
- Конкретный off-host backup provider выбирается в Gate 8 после сравнения.
- Начальные design SLO:
  - Core DB `RPO <= 15 min`, `RTO <= 60 min`;
  - полная потеря VPS `RTO <= 2 h`;
  - Windows Bridge `RTO <= 30 min`.
- Финальные SLO принимаются только после portable restore drill.
- Внешний heartbeat monitor — Healthchecks.io; owner alert destination — Gmail.
  Healthchecks.io не является единственным evidence source: локальные signed
  health evidence, logs и portable recovery evidence сохраняются.
- Telegram token ротируется при неопределённой старой custody.
- Autostart и bounded restart разрешаются только отдельным L4 после успешного
  72-hour pilot; бесконечный restart loop запрещён.

## Решения, отложенные до измерений

Отложенное решение не считается разрешением расхода:

- точные per-task, daily и monthly Google AI ceilings;
- точные OpenAI/API cost scenarios, только если CLI benchmark не пройден;
- включение Document AI или Cloud Speech-to-Text;
- Tailscale paid tier;
- конкретный backup provider, account boundary и фактическая retention;
- окончательные RPO/RTO после restore drill.

До отдельного решения действует budget `0` для нового платного production
маршрута.

## Последствия

Положительные:

- продукт получает широкий функциональный доступ к owner workspace без
  передачи модели секретов или ambient filesystem authority;
- код не размножается копиями, а версионируется Git;
- CLI-first решение проверяется на реальном VPS до возможного API billing;
- Drive-wide owner UX отделён от узкой authority на запись;
- monitoring и owner alert находятся вне Core failure domain.

Ограничения:

- OAuth verification для personal Gmail и `drive.readonly` может потребовать
  ручной регистрации и проверки Google;
- Shared Drives не являются принятым scope;
- локальные функции недоступны при offline Windows Bridge;
- Healthchecks.io не заменяет signed composite health;
- TARGET design не доказывает регистрацию, implementation, runtime или Gate
  PASS.

## Проверка и реализация

ADR реализован только когда соответствующие Gate завершили свои contract tests,
negative security tests, provider/readback tests, cost evidence, portable
restore drill, независимые L1/L2/L3 и exact L4. Любое подключение, billing,
OAuth, installation, migration или publication получает отдельный action-bound
manifest.
