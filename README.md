# Nobus Space MVP1

Nobus Space — Telegram Bot и обязательный тонкий Mini App над одним существующим
локальным Windows Core/Codex runtime.

**8 сентября 2026:** C0–C3 ACCEPTED / PUBLISHED. C4 ACCEPTED / PASS / PUBLISHED. C5 ACCEPTED / PASS / PUBLICATION_PENDING; C6 не запущен; MVP1 NOT READY; MVP2 HOLD.
Постоянное развёртывание в C5 не выполняется; его принимает отдельный C6.

[Текущий статус](docs/handoffs/CURRENT-STATUS.md) содержит точные ревизии,
проверки и следующий шаг. [Документация](docs/README.md) —
архитектуру, API, пользовательские состояния и эксплуатационные границы.
[Пакет C5](docs/gates/gate-c5-mvp1-operations-security/HANDOFF.md) связывает эксплуатацию, восстановление, проверки и условия отдельного C6.

Опубликованная база C5 после C4: `1b3cf67405c4523258dd8b400d17d09601f815ff`,
tree `c302123e6f3ae93668e4fca7580b24d424056f94`.
Код C4 проверен на `68f87f18da3de7c995f83b9cb08b391d0af5cdfb`,
tree `5ae168bf613b18fc2f14e24973b5167a2b4c7b74`.
Исторический READY и прежний live не доказывают приёмку этого кандидата.

Semantic path реализован и проверен в изолированном ON-кандидате C4. В штатном runner флаг _GATE_C1_SEMANTIC_ADMISSION_ENABLED остаётся False; постоянная активация не выполнена.

## Пользовательский путь

Владелец задаёт текстовую задачу или подтверждает распознанное голосовое сообщение.
Если смысла недостаточно, Core задаёт уточнение; неподдерживаемая возможность
получает явный отказ без задачи и эффекта. Telegram и Mini App показывают
состояние одной задачи, прогресс, результат и связанный файл.

C4 реализует восстановление сессии, уточнения и неизвестного исхода запроса после
reload/reconnect. Потеря ответа POST не запускает задачу повторно: интерфейс читает
durable request journal. Если запрос точно не принят, Core может закрыть его
отменой и запретить поздний приём того же ключа. Bearer живёт только в памяти;
localStorage хранит только непривилегированные opaque указатели.

Core проверяет свежую Telegram-подпись и exact owner/bot/tenant. Одноразовый
HttpOnly recovery credential сохраняет исходный срок подписи и вращает поколение
bearer; после срока нужна новая Telegram-сессия. Mini App получает только
owner-bound список, детали, события, результат и авторизованные bytes файла.
Имя скачивания `nobus-result.txt` — представление; C3 identity/digest/part receipts сохранены.

Сохранённые доказательства C4 (не новый C5 smoke): полный C4 L1: 2227 PASS и 25 subtests PASS, 2 Windows symlink SKIP,
2 явно объяснённых historical deselect; frontend Node20 PASS. Настоящий владелец
подтвердил голос кнопкой, получил результат и TXT в обоих интерфейсах. Отдельный
локальный браузер проверил 320/390/768, светлую/тёмную темы, клавиатуру, копирование,
скачивание, reload и reconnect. Точные доказательства и границы — в C4 HANDOFF.

## Архитектура

```text
Telegram Bot / Telegram Mini App
  -> один Core: authentication, semantic admission, policy, queue, recovery
  -> локальный Codex worker / подтверждаемый локальный ASR
  -> authoritative task/result/outbox
  -> состояние, результат и один файл в Telegram и Mini App
```

[ADR0022](docs/adr/0022-thin-miniapp-orchestrator-mvp1-and-delivery-workflow.md)
задаёт thin topology; full distributed Gate2A остаётся FROZEN / NOT CURRENT.
[ADR0023](docs/adr/0023-modality-neutral-semantic-admission-and-core-decision.md)
реализован в C1–C3: модель описывает намерение без authority, решение принимает Core.
[ADR0025](docs/adr/0025-miniapp-session-and-request-recovery.md) и
[ADR0026](docs/adr/0026-channel-neutral-product-projection.md) описывают C4.
Нового Core, очереди, ASR или frontend framework нет.

Git хранит code/tests/ADR/current docs и принятую историю. Nobus Memory — указатель,
не замена exact Git revision. Пакеты C0–C3 и исторические sealed sources сохранены.

## Локальный product composition

Код C5 подготовлен для явных параметров `--semantic-admission`, `--runtime-root` и `--voice-model-directory`; штатный semantic default остаётся False. Read-only описание команды:

~~~powershell
& $python scripts/run_telegram_mvp1.py --help
~~~

Точные условия будущего запуска и остановки, проверка единственного экземпляра, диагностика и backup/restore находятся в [Runbook](docs/08-Runbook-эксплуатации.md). Постоянный запуск требует отдельного C6. В C5 действующий scheduler и live checkout не меняются; тесты используют отдельные данные и loopback.

C5 ограничивает HTTP приём, проверяет readiness и завершает только собственное дерево процессов. Восстановление БД инвалидирует прежние сессии/подтверждения и закрывает новый приём до сверки возможных внешних действий. Snapshot не отменяет доставку сообщений и не разрешает повторить UNKNOWN.

Активная Telegram-поверхность MVP-1 ограничена обычными текстовыми и голосовыми
задачами и командами `/start`, `/status`, `/limit`, `/help`. Маршруты `/task`,
`/calendar`, `/research`, `/document`, `/download`, `/network`, `/file`, `/notes`
и команды подтверждения future-effects не подключаются production runner и
fail closed с явным сообщением. Наличие отдельных адаптеров или тестовых
заготовок в исходниках не считается готовой функцией продукта.

Публичная owner-composition запускается одной отслеживаемой командой:

```powershell
& '..\..\nobus-orchestrator-dev\.venv\Scripts\python.exe' `
  scripts\run_nobus_space_live.py
```

Она помещает reverse SSH и Core в один Windows Job Object, а его
закрытие убивает оба process tree. Публичный frontend:
`https://app.nobusspace.com/`.

Verified answer даёт один детерминированный UTF-8 artifact. Его identity,
revision, digest, MIME, размер и безопасное имя выводятся из существующего
tamper-evident outbox result; отдельная artifact DB/queue не создаётся.
Telegram `sendDocument` и Mini App download получают одинаковые bytes/digest,
а path, foreign-tenant existence и stale/tampered refs не раскрываются.
При Telegram delivery тот же immutable `.txt` сохраняется как восстанавливаемая
локальная проекция в
`C:\Хранилище\АГЕНТ\PROстранство\ОРКЕСТРАТОР\NOBUS SPACE BOT\Проекты Telegram`.
SQLite/outbox остаётся единственным authoritative state; совпадающий retry не
создаёт копию, а конфликтующее содержимое под тем же именем fail closed.

Для реализованного owner journey отдельный ApprovalRequest не требуется: create,
status, result и download являются Core admission/read-only delivery. Уже
существующие заготовки approval/effect для будущих срезов не входят в активную
MVP-1 composition.

## Локальная проверка документационного кандидата

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  tests/test_documentation.py
git diff --check
```

Полный C4 code freeze, исходные FAIL, независимые проверки и оставшиеся
условия приёмки собраны в [C4 HANDOFF](docs/gates/gate-c4-frontend-journey/HANDOFF.md).
Исторические Gate 0 verifier не являются повторной приёмкой текущего C4.

Публикация C4 разрешена владельцем после полного PASS, включая настоящий
Telegram/Mini App smoke. Действующие main protection/checks обязательны.
Постоянный deploy/tag/release и запуск C5/C6 не входят в текущую задачу.

Локальные правила разработки: [AGENTS.md](AGENTS.md).
