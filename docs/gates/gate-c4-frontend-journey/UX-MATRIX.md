# Gate C4 — состояния и пользовательский путь

Это контракт проверок кандидата, не самостоятельный PASS. Источник проекции — `src/application/product_status.py`; C1/C2/C3 определяют состояние до отображения.

| Core / intake / delivery | Смысл для владельца | Telegram | Mini App | Следующее действие |
|---|---|---|---|---|
| Durable admitted / PENDING | Задача принята | Одна карточка очереди | Название, время, «В очереди» | Ждать |
| IN_PROGRESS / execution | Выполняется | Та же карточка с прошедшим временем | «В работе», безопасные события | Читать состояние |
| Voice received / recognizing | Сохранён голос, задача ещё не запущена | «Запись получена» / «Распознаю запись» | Task появляется после Core admission | Дождаться preview |
| C2 preview waiting | Нужно проверить распознанный ввод | Ответить исходному voice: да/нет/исправление | Подтверждённая voice task сопровождается как text | Подтвердить в Telegram |
| CoreDecision CLARIFY | Не хватает одного уточнения | Один вопрос и reply guidance | Один server-derived вопрос, кнопка «Ответить» | Ответ с новым request key и исходным token |
| APPROVAL / WAITING_HUMAN | Нужно разрешение эффекта | Только существующий Core challenge | CURRENT semantic capability такого шага не требует | Не создавать fake approval |
| ANSWERED / exact result | Ответ подготовлен | Полный неизменный ответ по частям | «Результат», копирование | Прочитать / копировать |
| Pending outbox | Результат готов, доставка не подтверждена | Повтор только неподтверждённых частей | Отдельная delivery label, bounded polling | Сверить доставку |
| OutboxArtifact | Тот же файл результата | Имя nobus-result.txt | Скачать, проверить фактические bytes/digest | Сохранить / открыть файл |
| UNAVAILABLE | Функция не реализована | Общий Core catalog | Запрос не принят, функция недоступна | Другое намерение |
| Core read unavailable | Последнее состояние может устареть | /status честно сообщает недоступность | Экран сохранён, «Повторить чтение» | Повторить только GET |
| FAILED / REJECTED | Задача не выполнена | Без служебного exception | «Не выполнено» | Сверить состояние |
| ESCALATE / UNKNOWN | Исход требует сверки | Не отправлять прежнюю задачу снова | Request readback / журнал | Без blind POST |
| Expired bearer | Нужна актуальная сессия | Путь в боте сохранён | Однократная recovery rotation; затем fresh Telegram launch | Переоткрыть |
| Offline | Нет сети | Уже принятый input durable | Последние данные остаются, новое чтение после reconnect | Проверить соединение |
| Empty / loading | Нет задач / идёт чтение | — | Разные состояния и действие «Новая» | Создать запрос |

## Изменения пути

| Путь | База C3 | Исправление C4 | Доказательство |
|---|---|---|---|
| Session reload | In-memory bearer утрачен, initData consumed | Core HMAC-bound one-use cookie; fresh signature после deadline | test_c4_miniapp_recovery |
| ACK loss | JS key только в памяти, кнопка повтора | Durable Core request journal, opaque marker, GET reconcile | test_c4_miniapp_recovery + frontend.test.cjs |
| Запрос не дошёл до Core | Неизвестный исход блокирует новую отправку | Явная отмена только отсутствующего запроса; Core запрещает его поздний приём | ADR0025, cancellation negatives, frontend.test.cjs |
| Clarification | HTTP409 question скрыт общей ошибкой | Core readback вопроса, restore после reload, answer binding | test_c4_product_journey + frontend.test.cjs |
| Transient read | Очищение выбранной task/list/bearer | Сохранение UI и явный bounded GET | frontend.test.cjs |
| Result labels | «Проверенный ответ» из одного digest | «Результат»; integrity claim только после download hash | frontend.test.cjs |
| Voice help/progress | Preview ошибочно не обещан; минута до60s | Явное подтверждение, elapsed вниз, safe stages | test_c4_product_journey |
| Task/file names | Сокращение UUID / UUID в filename | Core sequence / presentation-only file alias | test_miniapp + artifact parity |
| Mobile / keyboard | Нет light fallback; live detail spam | Light/dark tokens, 44px, focus, selective announcement | Static/JS проверены; browser matrix PENDING |
| Two tasks / stale responses | Selection protection частичная | Generation guard list/detail/result, result revision match | frontend.test.cjs |
| Live | Старый runtime не является кандидатом | Только exact отдельно разрешённое временное окно | PENDING, HTTPS502 / UI tool unavailable |
