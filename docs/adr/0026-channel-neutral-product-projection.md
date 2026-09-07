# ADR 0026 — Общая продуктовая проекция Telegram и Mini App

Статус: ACCEPTED для реализации C4; приёмка кандидата остаётся отдельной.
Дата: 7 сентября 2026 года.

## Решение

Существующий `product_status.py` остаётся единственным каталогом безопасных
состояний и текстов обоих каналов. К прежним `status`, `label`, `terminal`
добавляются закрытые `reason`, `reason_label`, `action`. Имена прежних status
сохраняются. Действие является подсказкой интерфейсу, не разрешением операции.

Проекция получает только authoritative TaskStatus, CoreDecision, закрытые
voice stages, worker stages и delivery states. Она различает очередь, работу,
распознавание, уточнение, подтверждение ввода, результат, ожидание доставки,
недоступную возможность, временный сбой, неисполнение и необходимую сверку.
Неизвестное значение не отображается как текст провайдера и не означает успех.
Предварительные состояния ввода не создают Core task и не дают task identity.
События имеют закрытый русский label; enum остаётся транспортным значением.

Отказ semantic admission перед TaskContract передаётся как типизированная
продуктовая остановка с этой проекцией, отдельно от временной недоступности.
Mini App может прочитать актуальность своего C1 clarification через прежние
owner/tenant/conversation/token/TTL bindings без consume и compiler call.
Такой read не подтверждает ответ и не заменяет проверки последующего POST.

Telegram показывает одну редактируемую карточку прогресса принятой задачи.
Прошедшее время округляется вниз; до минуты отображается «меньше минуты».
Голосовая запись до подтверждения называется записью; обязательный C2 preview
не является approval внешнего действия. Уточнение явно просит ответить на
сообщение вопроса. Ошибка восстановления предлагает сверить прежнюю задачу,
а не повторить неизвестное исполнение новым запросом.

ANSWERED и COMPLETED сохраняют точный существующий смысл. UI использует слово
«Результат»; наличие digest не называется проверкой фактов или скачанных bytes.
OutboxArtifact, immutable result, multipart manifests и receipts не меняются.
Транспорт показывает alias `nobus-result.txt` без UUID: Telegram multipart
filename и Mini App metadata/Content-Disposition используют одно имя.
Backing OutboxArtifact сохраняет прежние filename/id/fingerprint/content/digest;
alias не участвует в authority и не становится новым artifact. Telegram part
manifest по-прежнему связывает kind и exact content bytes; answer не получает
нового заголовка внутри этих bytes. Локальная immutable копия сохраняет прежнее
внутреннее имя. Старые refs/part receipts остаются действительными.
CURRENT semantic capabilities не требуют effect approval; FROZEN/UNAVAILABLE
capabilities не получают кнопки, превращающей их в CURRENT.

## Сохранённые границы

ADR 0023/0024, C1 INERT material, C2 TTL1h/confirmation/один queue slot,
default-off, C3 lease fencing и physical cleanup сохраняются. Каталог не имеет
DB, queue, retry policy, capability authority или browser shadow state.
Изменения не разрешают deploy, новую capability или внешнюю доставку.

## Проверка

Полнота закрытого mapper; unknown input fail-closed; Telegram/Mini App parity;
help ON/OFF; elapsed boundaries; clarification bindings/expiry; отсутствие
служебных строк и ложной проверки результата; прежние C1–C3 targeted tests.
Полный C4 требует собственного frozen L1/L2/L3 и разрешённого live smoke.
