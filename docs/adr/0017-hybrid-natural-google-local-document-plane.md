# ADR 0017 — Natural Language First и гибридный Google/local document plane

**Статус ADR:** ACCEPTED

**Статус реализации:** TARGET

**Дата:** 28 июля 2026

**Одобрено:** владельцем продукта в интеграционной задаче Nobus Space

## Контекст

Владелец управляет Nobus Space из Telegram и не должен запоминать slash-команды,
ключевые слова или точный служебный синтаксис. Все продуктовые функции должны
начинаться обычным текстовым или голосовым запросом.

Nobus должен работать с двумя равноправными источниками документов:

1. Google Drive, Google Docs и Google Sheets;
2. owner library `C:\Хранилище\АГЕНТ`.

Для обоих источников нужен один продуктовый lifecycle:

- найти;
- выбрать точный документ;
- прочитать нужный фрагмент;
- проанализировать один или несколько документов;
- создать новый результат;
- контролируемо обновить существующий документ;
- доставить результат владельцу.

Основной runtime планируется размещать на сервере. Сервер не имеет нативного
доступа к Windows-пути `C:\Хранилище\АГЕНТ`. Прямой shell/filesystem-доступ
LLM к этому корню ранее был отвергнут ADR 0010: Windows sandbox не доказал
достаточно узкую read-boundary.

## Решение

### 1. Natural Language First

Обычный текст и подтверждённая локальная voice-транскрипция являются основным
продуктовым интерфейсом. Slash-команды остаются только совместимым
операционным fallback и не входят в критерий пользовательской готовности.

Все входы нормализуются в один закрытый `IntentEnvelope`. Он содержит domain,
action, entities, period, source scope, output format, proposed effects,
confidence и ambiguities. Неоднозначность ведёт к одному понятному уточнению,
а не к угадыванию либо общему `worker_failed`.

### 2. Детерминированное Core и application-owned effects

Codex и Gemini могут понимать запрос, планировать анализ и готовить содержание,
но не владеют OAuth, shell или ambient filesystem authority.

Реальные чтения и записи выполняют доверенные application adapters:

- Calendar Executor;
- Tasks Executor;
- Google Document Executor;
- Local Library Bridge;
- Telegram Result Delivery.

Модель возвращает закрытый plan. Core повторно валидирует owner, tenant,
project/client scope, target, revision/digest, risk и idempotency.

### 3. Гибридный runtime

Server Nobus Core владеет Telegram polling, durable queue/outbox, Codex/Gemini,
Google Workspace adapters, policy, audit и orchestration.

На Windows-ПК работает один тонкий `Local Library Bridge`. Он не является
Telegram runner и не получает Telegram/Google credentials. Bridge принимает
только подписанные device-bound jobs с закрытыми операциями:

- metadata search;
- bounded selected read;
- create new artifact;
- prepare diff;
- snapshot + digest CAS + atomic update;
- readback;
- restore тестового/разрешённого snapshot.

Bridge не публикует arbitrary filesystem API, shell, PowerShell или открытый
сетевой share. При выключенном ПК локальные задачи становятся `DEGRADED` или
ожидают восстановления Bridge; Google, Calendar, Tasks и Telegram продолжают
работать.

### 4. Единый document plane

Оба backend используют общие смысловые контракты:

- `DocumentRef`;
- `DocumentQuery`;
- `DocumentReadPlan`;
- `AnalysisRequest`;
- `ArtifactPlan`;
- `DocumentWritePlan`.

`DocumentRef` связывает backend, tenant, project/client, opaque source identity,
revision/digest, media type, classification и provenance. Для local backend
наружу Bridge передаётся только Bridge-minted opaque `doc_id`; путь остаётся
внутри device boundary. Google IDs разрешает Core adapter и не передаёт модели
как authority. Специализация закреплена ADR 0018.

Поиск всегда metadata-first. Содержимое читается только после exact selection.
При нескольких кандидатах Core спрашивает владельца до чтения содержимого.

### 5. Границы owner library

Owner root: `C:\Хранилище\АГЕНТ`.

Разрешённые project/client roots и output roots задаёт versioned registry.
Абсолютный root, deny paths и credentials не передаются модели.

Всегда исключаются:

- `C:\Хранилище\АГЕНТ\VPN данные`;
- произвольное чтение `C:\Хранилище\АГЕНТ\Системные`;
- `Nobus memory backups`;
- VCS, runtime, caches, temp и secret-like paths;
- symlink, junction и другие reparse points.

`Nobus memory` читается только через отдельный curated Nobus Memory adapter.
Данные разных клиентов не объединяются без явного cross-client запроса и
санитизированного контракта.

### 6. Чтение и анализ

Разрешённые owner-bound чтение, поиск, анализ и расчёты не требуют отдельного
L4. Доверенный adapter извлекает только необходимые ranges/pages/excerpts,
выполняет secret/DLP classification и повторно связывает контент с digest или
revision.

Секреты и credentials никогда не передаются модели. Конфиденциальные
business/client данные обрабатываются по provider policy: локальные
детерминированные вычисления предпочтительны; внешней модели передаётся только
минимальный разрешённый context.

Prompt injection внутри документа остаётся недоверенными данными и не получает
tools или полномочий.

### 7. Создание и обновление документов

Точная owner-команда разрешает создать новый документ в заранее разрешённом
output root или Google folder. Поддерживаемые целевые формы MVP-1:

- Telegram text;
- JPEG;
- self-contained HTML;
- XLSX;
- DOCX;
- PDF;
- Google Docs;
- Google Sheets;
- Drive upload разрешённого нового артефакта.

Если имя, тип и destination явно указаны в исходном запросе и planner их не
изменил, вторая кнопка не требуется.

Если payload или destination определились только после анализа, Core показывает
точный preview и принимает естественное текстовое/голосовое подтверждение либо
кнопку.

Новый файл никогда не перезаписывает существующий молча. Collision создаёт
новую версию либо требует уточнения.

Обновление существующего локального документа требует snapshot, current digest,
diff preview, CAS, atomic replace и readback. Google Docs update требует
`requiredRevisionId`, preview, idempotency и readback. Если Google Sheets или
Drive blob не предоставляет доказанный strict precondition, MVP создаёт новую
version/copy либо fail closed; CAS не симулируется.

Удаление, sharing/access changes, отправка третьей стороне, деньги, deployment,
remote и push всегда требуют отдельного action-bound L4.

### 8. Аналитика и выдача

`AnalysisRequest` фиксирует client, SKU/article, period, sources, metrics,
grouping, requested outputs и calculation rules. Сначала строится bounded query
plan, затем извлекаются факты. Формулы и агрегации отделены от текстового
объяснения.

Многодокументный анализ сохраняет provenance до файла, листа/range либо
страницы. Конфликт источников показывается явно. Отсутствующее значение не
подменяется нулём или догадкой.

Один self-contained HTML является базовым renderer source для HTML, JPEG и PDF.
Это исключает три независимые системы форматирования. Telegram по умолчанию
получает короткий ответ; сложный результат может дополнительно содержать JPEG
и HTML.

## Последствия

Положительные:

- продукт управляется речью, а не служебным синтаксисом;
- Google и локальные документы имеют один понятный lifecycle;
- широкая функциональность не требует прямого доступа модели к OAuth или диску;
- сервер остаётся always-on, а Windows-доступ изолирован тонким Bridge;
- существующие Calendar/Tasks/Drive/OwnerFile/OwnerWorkspace components
  переиспользуются;
- unknown write outcome не приводит к слепому повтору.

Ограничения:

- локальные документы недоступны, когда ПК/Bridge выключен;
- local и Google Docs update требуют digest/revision binding; Sheets/Drive
  используют new-version/fail-closed до доказанного strict precondition;
- scanned PDF может потребовать отдельный OCR fallback;
- удаление, sharing, массовые операции и third-party delivery не входят в
  обычные полномочия MVP-1;
- статус `ACCEPTED/TARGET` не означает реализацию.

## Проверка

Реализация принимается только при:

- natural text/voice golden corpus;
- tenant/project/client isolation;
- path escape, reparse point и secret-path tests;
- Bridge device authentication, offline/reconnect и job replay tests;
- Google revision/idempotency/reconciliation tests;
- local snapshot/CAS/atomic rollback tests;
- single- и multi-document analytics с calculation evidence;
- одинаковых значениях Telegram/JPEG/HTML/XLSX;
- одном Telegram polling runner;
- composite health, fresh readiness и отсутствии orphan PENDING;
- полном L1/L2/L3 и точном release L4.

Полная последовательность Gate, acceptance matrix и самостоятельные
L4-сообщения закреплены в
[`12-Эталон-MVP-1-и-дорожная-карта.md`](../12-Эталон-MVP-1-и-дорожная-карта.md).
