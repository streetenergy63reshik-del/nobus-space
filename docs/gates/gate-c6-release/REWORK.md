# C6: исправление независимых замечаний

Кандидат 924576804ac33cc251d6e5316e69ce6d3460ee29, tree 46cf7c12cf414556563f0e9d1f3f543529063f20: L1 — 2330 passed, 25 subtests, 2 skipped, 2 исторических deselected, 263,70 с. L2 — REWORK: 44 целевых теста и 3 независимых воспроизведения, 47 passed за 61,81 с. L3 — FAIL по тому же пакету из трёх замечаний. Полный исходный результат сохранён; L1 PASS не отменяет независимые findings.

1. P1: отказ graceful stop мог оставить Running. Исправление: durable admission hold, exact-bound принудительная остановка задания, readback двух задач, порта и mutex Core/supervisor; отдельные признаки доказанного hold/cleanup. Подтверждённый отказ cleanup не маскируется.
2. P1: partial generation отравлял следующий recover. Исправление: зарегистрированный до data writes wrapper, exact cycle/identity DPAPI intent, ограниченный inventory и восстановимое перемещение собственной частичной попытки после точного failed digest. Временный pointer находится внутри wrapper. Неизвестные каталоги не принимаются автоматически.
3. P2: карантин не имел границы. Исправление: 64 поколения / 2 ГиБ со всеми вложенными bytes и квитанциями; общий preflight до первого move, без удаления.

Новые проверки покрывают отказ graceful/forced stop, отказ после записи snapshot, до certificate, перед pointer publish, replay, чужую попытку, посторонний файл, nested bytes и предел карантина. Целевой rework-набор: 36 passed за 38,93 с. Первоначальный вызов с неверным именем test_c5_runtime_supervisor.py не запустил тестов; исправленный запуск использовал test_live_supervisor.py, исходная ошибка сохранена.

Изменённые bytes требуют новой source freeze и независимой проверки. Статус здесь DRAFT, не приёмка релиза. Native licence decision, настоящий полный RTO, активация, реальные owner journeys и окончательное подтверждение владельца остаются отдельными необходимыми условиями.


## Проверка взаимодействия после первого исправления

6f5d26757ea40ba841049ea78e17a18c64b419b3: полный L1 — 2339 passed, 25 subtests, 2 skipped и 2 исторических deselected за 280,21 с. Независимые L2/L3 подтвердили закрытие прежних прямых STOP/retention сценариев, но нашли два связанных P1: плановый hold мог завершить Core с ошибкой через health/Telegram handler; повторно неудачный recovery терял исходный attempt_id. Их FAIL receipts и reproducer сохранены. L2: 53 целевых PASS и оба воспроизведения; один дефект собственных тестовых часов исправлен с сохранением исходного verifier FAIL.

Исправление сохраняет logical attempt_id во всех подтверждённых повторах того же цикла. RuntimeAdmissionPaused отделяет плановую паузу от неисправности: hold блокирует startup и новое admission, но не мешает operational health/drain. Freshness/disk продолжают проверяться в health. Typed pause проходит через Telegram polling boundary без ACK, с освобождением lease, и обрабатывается внешним циклом с паузой 1 секунда; cancellation штатного shutdown сохраняется. Настоящие handler/checkpoint ошибки не преобразуются в повтор. Mini App отвечает503 и не создаёт задачу.

Целевой integration набор: 130 passed за30,88 с. Включает настоящий polling/outer loop с MockTransport, actual Core health и synthetic SQLite, повторный partial recovery после временного отказа, Mini App503 без task/queue/compiler call. Это не реальные owner journeys, не native inference и не полный RTO.


## Последняя граница polling cleanup

89982cf25b1f2c26f9f159ee62fafb03462ed3ad: полный L1 — 2343 passed,25 subtests,2 skipped,2 исторических deselected за275,38 с. L2/L3 закрыли прежние Major. Остался один дефект: release=False/exception мог скрыться за recoverable RuntimeAdmissionPaused. L2 оценил P2 (потеря ACK/effects не выявлена), L3 P1 из-за подавления checkpoint failure; оба подтвердили один и тот же сценарий. Промежуточный L3 PASS отозван и сохранён как superseded.

Одноусловная поправка сохраняет telegram_checkpoint_failed при неподтверждённом освобождении lease и активной planned pause. Приоритет cancellation и прежних terminal exceptions не меняется. Новые negative tests проходят через настоящий outer polling: ни ACK, ни backoff при failed release. Целевой набор —132 passed за31,09 с. Final frozen readback требуется только для этой изменённой границы и evidence package; прошлые подтверждённые результаты сохраняют свой точный scope/revision.
