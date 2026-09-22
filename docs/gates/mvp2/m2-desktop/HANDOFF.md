# M2-DESKTOP — рабочая передача

**Gate:** M2-DESKTOP
**Стадия:** PAUSED FOR INDEPENDENT AUDIT / SAFE STOP

**Дата наблюдения:** 22 сентября 2026 года, 12:29 МСК
**Ветка:** `codex/m2-desktop`
**База:** `f3fdb2d22a41b6a5b84fec06544447014c7bb35c`, tree `b604fcb6591ae11c4280d3a7d41a7261c2383305`

## Снимок остановки для независимого аудита — 22 сентября

Разработка и live-проверки остановлены по прямому запросу владельца из-за
лимита. Не отправлять новые Telegram-сообщения, не запускать Desktop turn и не
возобновлять production до завершения независимого аудита и нового явного
продолжения владельца. Подробная хронология, баги, блокеры, тесты и решения
вынесены в [AUDIT-JOURNAL.md](AUDIT-JOURNAL.md). Нижележащие разделы этого
документа сохраняют checkpoint 21 сентября; их утверждения «не выполнялось» и
«ожидает разрешения» являются историческими и не переопределяют этот снимок.

Точный Git-снимок разработки:

- HEAD `3ea243893a2647dc631662c2a2030de7679ae0e1`, ветка
  `codex/m2-desktop`, рабочая копия была чистой перед документированием;
- локальные commits: `3d6514d` (единый Telegram↔Desktop bridge), `3ac1cac`
  (миграция bridge schema до backup admission), `3ea2438` (UIA scroll перед
  созданием задачи);
- код не опубликован и не слит в `main`; полный независимый L1/L2/L3 по
  замороженному кандидату не выполнялся, Gate не принят.

Фактическое состояние live-контура при остановке:

- production checkout `Code\worktrees\telegram-live` находится detached на
  `3ea243893a2647dc631662c2a2030de7679ae0e1`; связанная backup-конфигурация и
  действие Scheduled Task были переведены на этот revision;
- подписанный activation rebind на новый код прошёл; binding
  `sha256:fddb39bbdfb5d2cd6403a9a19f89ff8805154eb0d41967890e084d391913f3fb`;
- непосредственный запуск Core остановился fail-closed до Telegram-сессии:
  новая application binding не имела свежей совместимой backup generation;
- штатный recovery reset для точного terminal event прошёл, а проверка тем же
  `pythonw.exe` вернула `PASS`, state `new`, last digest
  `sha256:e911277e820fa2244266d9914e9562403be2cfc37383479ec4a1ce9adbc51885`;
- последующий backup cycle завершился Scheduler result `1`. Его post-failure
  inspection показал только прежний/непривязанный `phase=complete`, digest
  `sha256:924656486923cc0c4c72acb65ce8e893de72ba6af193a05792a741eb7a4c738c`,
  тогда как отдельная read-only `load_config` тем же production `pythonw.exe`
  прошла. Точная граница этого отказа пока не установлена; цикл не повторять;
- на 12:29 МСК все три задания `NobusSpaceBot`, `NobusSpaceBot-Health` и
  `NobusSpaceBot-Backup` остановлены и Disabled. Это намеренная безопасная
  пауза, а не рабочий production-статус.

Live Telegram-факт текущей итерации:

- в «Заметки бизнеса» → «Codex work» после подтверждения владельца отправлен
  ровно один тестовый запрос, Telegram message id `2150`; бот ответил
  «Задача принята и передаётся в Codex Desktop.»;
- bridge request `e18a5ca3-95d3-4be8-8453-630d88e97a50` завершён как
  `unknown_dispatch`, без `desktop_thread_id` и `turn_id`;
- read-only список задач Desktop подтвердил, что новая задача не появилась.
  Запрос не исполнился и не должен повторяться автоматически;
- причина локализована в UIA: точная кнопка создания была `offscreen=true`,
  хотя поддерживала `ScrollItemPattern`. Исправление вызывает
  `ScrollIntoView()` перед `Invoke`, fail-closed при отсутствии pattern; 29
  целевых тестов прошли за 2,04 с, read-only wrapper snapshot прошёл;
- после исправления новый Telegram-запрос не отправлялся. Следующая попытка —
  только как новый request после аудита, восстановления production и нового
  подтверждения действия.

Не завершено: реальный Desktop create/start через исправленный путь, IPC ACK и
turn id, двустороннее продолжение, полный финал, question/approval approve и
deny, файл, reconnect, голос, две темы, реальный Артур младший и полный D01–D17.
DOCX-памятка пользователя не изменялась. Исторический отдельный App Server
writer-блокер и положительные read/visibility-доказательства сохраняются без
повторения.

## Контракт результата

Цель — один сквозной Gate управления настоящими задачами Codex Desktop из
доверенной группы Telegram: создание и продолжение задачи в выбранном
сохранённом проекте, полный ответ, вопросы и штатные разрешения, артефакты,
восстановление и ровно один владелец каждой доставки.

Границы текущей стадии: локальная реализация, offline-проверки и read-only
обследование работающего Desktop. Историческое разрешение прежнего live-probe
не действует для новых изменяющих операций. Новые Desktop turn/approvals,
намеренные Telegram-действия, изменение notifier/BotFather, установка,
публикация и deploy не выполнялись. Два автоматических Telegram-уведомления
прежнего App Server probe сохранены как исторический внешний эффект.

## Что подтверждено

- В установленном Codex Desktop найден сохранённый проект этого репозитория и
  текущая реальная задача проекта. Встроенная поверхность Desktop поддерживает
  операции создания, продолжения, чтения полного ответа и ожидания вопросов,
  однако сама по себе она не является внешним API для Nobus Space.
- На Desktop `26.915.4065.0` реально прошли `initialize` версии 0 и
  `thread-owner-discovery` версии 1 через `\\.\pipe\codex-ipc`; для существующей
  задачи разработки найден owner, `supportsUntrustedAppInput=true`. Probe не
  отправлял turn и не отвечал на вопросы/approvals. Это положительное
  доказательство отдельного owner-follower маршрута внутри работающего Desktop,
  а не повтор прежнего отдельного App Server.
- Статическое чтение того же установленного bundle подтвердило версии follower-
  методов: start turn 2, полная история 1, ответы command/file/permissions,
  user input и MCP elicitation 1, stream-state broadcast 11; interrupt/update
  settings требуют точной привязки payload перед использованием. Наличие метода
  не засчитано как полный цикл события или паритет.
- Read-only Windows UI Automation в интерактивном пользовательском сеансе
  обнаружил окно `Chrome_WidgetWin_1`, 600 доступных элементов и 22 элемента с
  AutomationId. Точные кнопки проекта `nobus-orchestrator-dev`, создания новой
  задачи и открытия обеих существующих задач доступны через семантические
  `ExpandCollapse`/`Invoke`; composer предоставляет `Value`/`Text`. Фокус,
  Invoke, ввод и координатные действия не выполнялись.
- Добавлен минимальный async IPC adapter
  `src/integrations/codex_desktop_ipc.py`: bounded little-endian frames,
  version profile, owner targeting, timeouts, reconnect safe-read, ответы на
  вопросы/approvals и fail-closed `UNKNOWN` после lost ACK без слепого повтора.
  `src/integrations/codex_desktop_uia.py` фиксирует только точные selectors и
  запрещает неоднозначный/неподдерживаемый выбор; выполняющего UI backend до
  нового live-разрешения нет.
- 13 offline-тестов IPC/UIA прошли. Они подтверждают framing, routing, version
  mismatch, отсутствие fallback, reconnect, owner-targeted responses и
  readback-first recovery; fixtures не считаются реальным Desktop turn.
- Производный roadmap совпадает с источником, JSON evidence разбирается, все
  относительные ссылки внутри checkpoint scope M2-DESKTOP разрешаются. Общий
  `tests/test_documentation.py` дал 3/4 PASS: link-test видит сохранённые ранее
  ссылки на отсутствующий именно в этом worktree `ARCHITECT-HANDOFF.md` и на
  ignored исторические `.runtime/m1-s1-*` receipts. Эти чужие WIP/evidence не
  копировались и тест не ослаблялся; ограничение не связано с IPC adapter.
- Установлены Desktop `26.915.4065.0` и поставляемый с ним Codex App Server
  `0.155.0-alpha.9.2`. Статический разбор установленного Desktop bundle показал:
  наблюдаемый локальный Windows host запускает собственный дочерний App Server
  через `stdio`;
  ветка общего daemon/control socket разрешена только не на Windows и при
  отдельном feature-флаге. Это привязанное к версии наблюдение, а не публичный
  контракт OpenAI.
- Отдельный read-only stdio-пробник тем же бинарным файлом получил каталог
  проектов, нашёл существующую задачу Desktop по `cwd` и прочитал её по точному
  идентификатору. Совпали рабочая папка, originator и версия протокола. Ответ
  `thread/read` не содержал `projectId`, а фильтр по идентификатору из
  `project/list` эту задачу не вернул. Контракт не требует наличия либо равенства
  таких идентификаторов, поэтому несовместимость проекта из этого не следует.
  Положительно подтверждён путь чтения общей реальной задачи; создание и
  двустороннее продолжение проверены отдельным живым экспериментом ниже.
- Поставляемый App Server создал одну persistent-задачу `M2-DESKTOP live probe`
  с `cwd` существующего проекта. Desktop показал её в списке, прочитал по тому
  же thread ID и отобразил полный финальный ответ. Затем Desktop успешно
  выполнил второй turn в том же thread; raw `thread/read` отдельного App Server
  увидел оба завершённых turn и оба полных финальных сообщения.
- Эфемерный `remoteControl/enable` в том же foreground App Server без daemon-
  установки перешёл `disabled → connected`, получил environment ID и был явно
  возвращён в `disabled`. Это подтверждает доступность Remote Control у
  поставляемого бинарного файла, но не наличие документированного стороннего
  Remote-клиента для Telegram bridge и не подключение к приватному процессу
  Desktop.
- Схема установленной версии содержит проекты, start/resume/read задач,
  пагинацию turns/items, attachments, вопросы и семейства approvals. Наличие
  методов в схеме не засчитано как пользовательский паритет.
- Все восемь установленных файлов notifier и `nobus-send-results` совпали с
  SHA256 канонического manifest от 2 сентября 2026 года. Их установленная
  конфигурация не менялась.
- One-shot ledger существующего notifier содержит `sent` для обоих turn
  тестовой задачи. Следовательно, в «Заметки бизнеса» → «Codex work» ушло два
  автоматических уведомления — по одному на turn, без дубля. Bridge и
  `nobus-send-results` их не вызывали, но условие эксперимента «без Telegram»
  фактически не выполнено. Сообщения не удалялись, notifier/ledger/config не
  менялись.
- В текущем notifier нет per-task исключения. Настройки содержат только
  глобальный `enabled`; wrapper отправляет непустой финал каждой зарегистрированной
  основной задачи, включая fallback без marker, а reconciler сканирует весь
  реестр. Без изменения установленного notifier или точного разрешения на
  ожидаемое уведомление новый live-turn недопустим.
- Подтверждены существующие ограничения повторного использования: старый ключ
  отправки связывает только назначение и digest файла, а notifier хранит лишь
  краткий финальный summary. Для M2-DESKTOP нужен совместимый operation key v2
  и чтение полного результата по точному turn; второй Telegram sender запрещён.

## Что не подтверждено

Новый owner IPC ещё не выполнил изменяющий turn. Не подтверждены ACK и реальный
turn id, получение всех событий вопросов/approvals, approve/deny, полный
readback результата и артефактов, reconnect после настоящего разрыва, Desktop-
host tools и паритет settings/model/skills/MCP/plugins. Наличие обработчиков и
offline fixtures не заменяет эти проверки.

UIA доказал доступность точных semantic selectors, но не создание/открытие:
неизвестно, появляется ли conversation id/owner сразу после `Invoke` новой
задачи или первый prompt тоже потребуется передать через проверенный UIA
pattern. Нет доказательства безопасного поведения при закрытом/заблокированном
сеансе. CDP не запускался.

Штатные Remote Connections, managed daemon, отдельный App Server и Desktop
owner IPC остаются разными механизмами. Исторический writer-блокер относится
к отдельному App Server и сохраняется; он не блокирует автоматически follower-
делегирование существующему Desktop owner. Общая история с изолированным CLI
по-прежнему недостаточна. Gate не принят; D01/D03/D07/D09/D13/D17 требуют live.

## Критерий совместимости с Desktop

Совместимость подтверждается поведением реальных задач в выбранных существующих
проектах: задача видна в Desktop; один thread последовательно продолжается со
стороны Desktop и внешнего адаптера; `cwd`, проектный контекст и требуемые
функции Desktop корректны; вопросы и разрешения проходят через штатные
механизмы. Совпадение PID, транспортного процесса или идентификаторов разных
API не требуется без документированного контракта. Отдельный процесс адаптера
разрешён.

Официальные источники, проверенные 21 сентября 2026 года:

- [Remote connections](https://learn.chatgpt.com/docs/remote-connections) —
  setup начинается в Desktop; подключённый хост предоставляет те же проекты,
  чаты, credentials, plugins, skills, tools и approvals.
- [Codex App Server](https://learn.chatgpt.com/docs/app-server) — app-server
  предоставляет history, streaming и approvals, но отдельные app-server/WebSocket
  transport не являются доказательством связи с Desktop; WebSocket пока
  экспериментален и не поддерживается для production.
- [ChatGPT desktop app for Windows](https://learn.chatgpt.com/docs/windows/windows-app) —
  Desktop и native Windows Codex используют общий Codex home, поэтому одна
  история на диске сама по себе не доказывает общий исполняющий процесс.

## Ограничения источников

Nobus Memory 21 сентября снова подтвердил `READY`, официальный CLI-маршрут,
читаемость vault и единственный разрешённый scope `project:nobus-space`;
`write_mode=limited_auto`. Scoped search текущего M2-DESKTOP завершился
`MEMORY_OPERATION_FAILED`; неизменный запрос, bridge и fallback не повторялись.
Vibecoding требует `project:prostranstvo`, которого нет среди разрешённых scope,
поэтому новый контекст этой базы не выдумывался. Git, новое исследование,
локальное IPC/UIA-наблюдение и тесты остаются доказательствами текущего шага.

## Проверенный предел managed daemon

Владелец разрешил ограниченный интеграционный эксперимент без установки.
`remote-control start` был проверен сначала с Desktop plugin binary, затем с
перенесённым Desktop CLI. Оба завершились до запуска с
`no complete local package`. Попытка выполнить in-package `resources/codex.exe`
напрямую отклонена Windows AppX ACL. Проверка после отказов подтвердила:
standalone package отсутствует, control socket отсутствует, daemon не запущен;
созданы только два пустых lock-файла daemon lifecycle. Эти попытки задачу не
создали.

Ошибка `no complete local package` относится только к проверенному способу
запуска managed daemon. Она не доказывает, что daemon нужно устанавливать для
MVP2. Дополнительная проверка поставляемого Desktop bundle закрыла отдельный
вопрос: в наблюдаемой конфигурации Windows Desktop выбирает private stdio, а
встроенная daemon-ветка на Windows недоступна. Поэтому его установка в текущей
версии не создаст общий writer и не
является следующим шагом.

## Исторический App Server эксперимент и локализованный блокер

Разрешённый эксперимент создал ровно одну тестовую задачу через отдельный
штатный stdio App Server. После Desktop-turn попытка нового внешнего
`thread/resume` завершилась `thread ... already has an active writer`, хотя
turn был завершён. Проверка альтернативной семантики без `resume` дала
`thread not found`. Официальный `thread/unsubscribe` относится только к
текущему соединению; после последнего подписчика App Server сохраняет thread
загруженным до 30 минут. Внешнего метода освободить writer приватного процесса
Desktop в доступном контракте нет.

Это конкретный блокер отдельного короткоживущего stdio-адаптера: он создаёт
видимую задачу и читает Desktop-turn, но не может своевременно вернуть себе тот
же исполняемый thread после продолжения из Desktop. Общая история здесь
положительно доказана, однако она недостаточна для требуемого туннеля.

Дополнительно выявлена версия контракта: pinned SDK `0.144.4` не разбирает новый
item `functionCallOutput`, который Desktop `0.155.0-alpha.9.2` записал во второй
turn. Raw-схема установленной версии прочитала результат полностью. Это не
причина writer-конфликта, но обязательная совместимость будущего адаптера.

Штатные Remote Connections дают официальным клиентам ChatGPT проекты, задачи,
инструменты и approvals хоста. Foreground App Server подтвердил соединение с
Remote relay без установки daemon, однако публичный контракт для стороннего
Telegram-клиента не найден. Официальная документация App Server описывает
подключение клиента к выбранному процессу и отписку своего соединения, но не
handoff writer между private stdio-процессами. Локальный bundle дополнительно
показывает, что Desktop умеет распознавать конфликт active writer и имеет
внутренние роли owner/follower. Прежний вывод «внешнего метода получить эту роль
нет» заменён новым фактом: owner IPC обнаруживает владельца и маршрутизирует
follower-запросы. История отдельного App Server не удаляется и не переносится
на новый транспорт.

## Текущий IPC/UIA checkpoint

Основной технический вопрос сузился: принимает ли найденный Desktop owner через
IPC реальный start turn, выдаёт ли подтверждаемый turn id и все нужные события,
а UIA — создаёт/открывает ли задачу без неоднозначного ввода. Локальный adapter
и 13 тестов готовы к этому smoke. Установка daemon, патч Desktop, CLI fallback,
запись в БД, CDP и изменение ACL/PATH/config не нужны.

### Подготовленный ограниченный live-сценарий

- **Проект:** существующий `nobus-orchestrator-dev`; одна новая тестовая задача
  `M2-DESKTOP owner IPC smoke`. Существующая Gate-задача и прежний
  `M2-DESKTOP live probe` не заменяются и не удаляются.
- **UI:** только точные accessible names и `ExpandCollapse`/`ScrollItem`/`Invoke`/
  `Value` patterns найденного окна Codex. Сначала выбрать проект и вызвать
  создание задачи. Если owner ещё не появился, разрешён ровно один первый prompt
  через проверенный composer новой задачи; при неоднозначности немедленно STOP.
- **IPC:** initialize не повторять как отдельный research probe; adapter выполняет
  его как часть соединения, затем owner discovery, один start turn с уникальным
  `clientUserMessageId`, ACK, stream/history readback и контролируемый reconnect.
  После lost ACK — только history/readback, без автоматического второго turn.
- **Двусторонность:** один follow-up отправить со стороны видимого Desktop через
  точный semantic UIA control, затем один через owner IPC; подтвердить один
  thread, порядок turns, рабочую папку и полный текст. Пользовательский ручной
  ввод остаётся отдельным финальным доказательством D03, а не подменяется UIA.
- **Вопрос:** тестовый turn вызывает структурированный `requestUserInput` без
  внешнего эффекта; harness получает pending event и отвечает по точному
  request/thread/turn. Это проверяет транспорт, но ещё не Telegram-author policy.
- **Разрешения:** запросить один безвредный read-only network `HEAD` к
  `https://example.com/` и одобрить; отдельно запросить запуск Calculator и
  отклонить до запуска. Если Desktop/auto-review не создаёт pending event,
  зафиксировать конкретную границу и не имитировать PASS.
- **Файлы:** читать/создавать только
  `.runtime/m2-desktop-live-probe/source-v1.txt`,
  `desktop-owner-ipc-created.txt` и `owner-ipc-smoke.json`. Никаких файлов за
  пределами этого каталога, кроме обычной истории самой тестовой задачи.
  Подготовленный `source-v1.txt`: 159 bytes, SHA256
  `e8f15053821c09313dbcb61b6cae404cd64c931b28a87b2b2ed2d7b9ab332b88`.
- **Telegram:** product ingress, ASR, bot-to-bot и sender в этом smoke не
  запускаются. Установленный глобальный notifier может автоматически отправить
  до пяти completion-summary в доказанную тему «Заметки бизнеса» → «Codex work»
  — по одному на фактически завершённый turn. Сообщения не удалять, notifier и
  ledger не отключать/очищать. Не выдавать summary за полный результат.
- **STOP/восстановление:** несовпадение версии, несколько UIA matches, отсутствие
  owner, неизвестный event, потерянный ACK без однозначного readback, неожиданный
  путь/сеть или лишнее уведомление останавливают сценарий. Сначала читать history
  и notifier receipt; неизвестный эффект не повторять.

Для выполнения этого сценария требуется новое точное разрешение на: одну задачу,
до пяти turn, перечисленные semantic UIA/IPC mutations, один `HEAD`, один
заведомо отклоняемый Calculator request и ожидаемые notifier-summary. Оно не
разрешает явные Telegram-тесты продукта, изменение notifier, установку, CDP,
публикацию или deploy.

После успешного smoke продолжить локальную реализацию Core↔Desktop и единого
delivery operation; затем отдельно подготовить и разрешить реальные Telegram/
Артур/голос/две темы/D01–D17. Gate остаётся `WIP_ITERATION`, не BLOCKED и не
ACCEPTED. Публикация и активация не выполнялись.
