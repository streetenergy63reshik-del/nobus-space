# Исправления после ручной проверки 8 сентября 2026 года

**REWORK / NOT ACCEPTED / NOT PUBLISHED.** C5–C6 HOLD; MVP1 NOT READY.

Владелец проверил временный e9bf22aee1187c06b6846a6debb865014c205f86
(tree 35684f40e5f99ed83d436fe1068bcdf891f96bf2) в настоящем Telegram.
Бот выполнил текстовую задачу; владелец получил и открыл TXT с тем же ответом.
Полного PASS нет: около 20 секунд не было подтверждения получения запроса;
Mini App показывал ошибку загрузки. [Исходные доказательства](LIVE-ATTEMPT3.json)
и два обезличенных снимка сохранены. История чата с посторонними запросами
не включена в пакет.

Причина задержки: первый ответ находился после await semantic admission.
Исправление отправляет честное подтверждение получения перед разбором, без
утверждения, что Core уже создал задачу. Admission и idempotency не меняются.

Mini App: шесть настоящих POST /api/session/recover вернули400; первичного
POST /api/session не было. Контроль без credentials: loopback Content-Length:0
вернул401, loopback chunked и оба HTTPS-варианта вернули400. Пустое тело
отклонялось по Transfer-Encoding до проверки cookie. Исправление допускает
единственный chunked без Content-Length, затем проверяет декодированное тело
с прежним нулевым лимитом и timeout. Непустое тело, неоднозначное framing,
чужой Origin, отсутствующая/прежняя cookie и старый bearer остаются запрещены.
Соответствие исправления фактическому HTTPS ещё требует повторного smoke.

Окно attempt3 остановлено до правок: graceful cleanup всех компонентов,
Windows Job0, wrappers exited, listener8765 отсутствует; HTTPS502, прежние
меню/webhook. Общий ledger сохранён:26 model reservations,20 actual turns,
358.124s; ASR2/14.11s, active0. Новое окно получит отдельные SHA/tree/state.

Предыдущие manifests, L1/L2/L3 и actual local runs относятся к своим исходным
ревизиям. Для нового цельного кандидата нужны собственные L1/L2/L3 и настоящий
owner-run. Опубликованная main остаётся принятой C3. Публикация C4 только после
полного PASS; permanent deploy/tag/release/C5/C6 не выполняются.
