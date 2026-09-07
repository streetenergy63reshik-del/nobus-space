# ADR 0025 — Восстановление сессии и принятого запроса Mini App

Статус решения: ACCEPTED FOR C4 IMPLEMENTATION по поручению владельца выполнить
Gate C4 целиком. Статус реализации: DRAFT, собственная приёмка C4 обязательна.
Дата: 7 сентября 2026 года. База: C3 `b9283b3419928042c80278b5088b526edebab6e7`,
tree `77062335b1dbccb3694721d357e484c856ac89c7`.

## Причина

Core одноразово потребляет digest Telegram initData, но bearer существует только
в памяти страницы. Reload теряет bearer, а повтор initData правильно отклоняется.
Fresh auth не отзывает прежние bearer. Request key существует только в памяти
страницы; поэтому потерянный ACK нельзя надёжно сопоставить с принятой задачей.
Существующий ingress claim уже связывает задачу с содержимым и стабильным
auth_context_ref, а C1 хранит уточнение с owner/tenant/conversation binding.

## Решение до кода

Core выпускает отдельный случайный recovery credential при успешной свежей
Telegram-подписи. HMAC Core связывает случайную часть, исходный deadline и exact
bot/owner/tenant context; изменение cookie или даты в SQLite не продлевает
подписанное окно. Boundary передаёт его исключительно как HttpOnly cookie
`nobus_miniapp_recovery`, SameSite=Strict, Path=/api/session, без Domain;
Secure обязателен для HTTPS, единственное локальное исключение — существующий
loopback HTTP. Credential не является bearer и не открывает task routes.
В существующей Core SQLite сохраняются только его digest, auth_context_ref и
предельный срок исходной подписи. `POST /api/session/recover` с пустым телом
атомарно заменяет digest и выпускает новый короткий bearer. Старые bearer и
cookie недействительны, в том числе при нескольких Core instances. Fresh auth
также заменяет поколение. Срок нового bearer и cookie не выходит за исходное
окно signature freshness; после окна нужен новый запуск из Telegram. Повтор
initData, расширение TTL и автоматические бесконечные re-auth запрещены.

Перед admission Core сохраняет журнал намерения в той же SQLite. Он содержит
валидированный trusted envelope с digest содержимого, стабильный request key
и outcome, без исходной инструкции. Уточняющий вопрос и opaque token при
необходимости защищены существующим DPAPI, связаны с exact envelope и не
являются второй clarification authority. Проверку ответа, срока и conversation
по-прежнему выполняет C1, включая readback перед показом сохранённого вопроса;
journal дополнительно ограничивает его срок 30 минутами. Новый ответ имеет
новый key и прежний server token.
Изменённые bytes с прежним key дают conflict до compiler/queue. Сохранённый
неизвестный исход не вызывает повтор admission. `GET /api/requests/{key}`
проверяет действующую session и auth_context_ref, читает journal и ingress claim,
возвращает существующую identity/уточнение либо честный pending. При отсутствии
доказательства admission pending не превращается в «не выполнялось».

На клиенте разрешены только opaque navigation/request markers. Они помогают
после reload найти Core state, но сами не дают authority. Bearer, initData,
инструкция и clarification token не сохраняются в browser storage/URL.

## Threat model и ограничения

Подпись, exact bot/owner, freshness и durable anti-replay остаются прежними.
Cookie защищён от чтения JavaScript и cross-site отправки, а mutation routes
по-прежнему требуют exact Origin/Host. Украденный recovery credential имеет
короткий исходный deadline и одноразовую rotation; XSS не получает более широкую
authority, но всё ещё опасен, поэтому text-only DOM/CSP остаются обязательными.
Параллельные вкладки конкурируют за одно поколение: проигравшая безопасно
обновляет сессию, без собственного повторного POST. Поздняя mutation, уже принятая
Core до rotation, сохраняет identity; старый bearer не разрешает новый admission.
Потеря ответа rotation может потребовать свежего открытия Telegram; старый
credential ради удобства не принимается повторно.

Journal не содержит отдельной queue, execution state machine, TaskContract или
effect policy. Неопределённость crash между admission steps восстанавливает C3;
Mini App только читает исход. Scope: ADR 0022 session/recovery projection;
смысловой контракт ADR 0023, ASR C2 и recovery/artifact authority ADR 0024
не изменяются. Approval engine не добавляется: CURRENT semantic capabilities
не требуют approval. Production activation, ingress и backup drill остаются C5/C6.

## Проверка

Обязательны targeted negative tests: old bearer/cookie; restart и свежая auth;
foreign owner/tenant/bot/request; signature replay/expiry; cookie Origin/body;
concurrent rotation; ACK loss/reload; rebound input; persisted clarification;
crash до journal outcome; отсутствие private text/token в plaintext SQLite;
task/result/artifact binding. Весь C4 остаётся DRAFT до собственного frozen
L1/L2/L3 и отдельно разрешённого настоящего Telegram/Mini App smoke.
