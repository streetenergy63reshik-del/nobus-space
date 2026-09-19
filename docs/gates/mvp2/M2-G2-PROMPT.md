# M2-G2 — фирменный Mini App на существующем Core

Готовый промпт одной задачи; ещё не запущен.

## Начало промпта

Выполни M2-G2 Nobus Space: внедри принятый дизайн в Mini App и сохрани рабочие
пользовательские пути через существующий Core. Один Gate = одна задача.

Проект: канонический checkout репозитория `streetenergy63reshik-del/nobus-space`.
Прочитай AGENTS → docs/README.md → docs/handoffs/CURRENT-STATUS.md →
docs/15-Продуктовая-дорожная-карта.md → docs/mvp2/DOCUMENTATION.md →
docs/gates/mvp2/REGISTRY.md → docs/gates/mvp2/m2-g1/HANDOFF.md
и EVIDENCE.json того же Gate. Используй Nobus Memory только project:nobus-space.
Прими за вход точный результат предыдущего Gate, критерии G0 и применимые ADR.
Entry: G1 принят, M1-S1 stable baseline подтверждён; зафиксируй фактический
predecessor SHA/tree и Git status. Чужие файлы/WIP не изменяй.

Основная зона: `src/transport/miniapp_static/` и соответствующие frontend tests.
Точное имя test entrypoint найди в репозитории. `src/transport/miniapp.py` и
`src/application/miniapp.py` меняй лишь при доказанной необходимости согласованного
UI contract; сначала зафиксируй изменение границы. Не меняй auth/state/schema,
семантику admission или polling ради внешнего вида.

Реализуй G1 tokens/assets и все G0 screen states: list/detail/create/clarification,
progress/result/copy/TXT, empty/loading/failure/unavailable/expired/UNKNOWN/reopen.
Сохрани DOM behavior или обнови связанные селекторы/tests в одном пакете.
Нет fake success, выдуманных процентов, данных другого task или кнопок будущих
агентов/файлов. UI читает authoritative Core projection, не хранит вторую очередь.

Сохрани:
- server-derived identity/capability; volatile bearer, отсутствие secrets/initData
  в URL/log/storage и отсутствие permissive CORS/CSP;
- idempotency key и reconciled UNKNOWN: потерянный ACK не порождает новую task;
- task/revision/result/artifact binding и совпадающий TXT;
- текущие лимиты, клавиатурную навигацию и accessible announcements;
- голосовой вход в Telegram и confirm до создания, без скрытого изменения route.

Theme changes/viewport/safe area проверяй по актуальной официальной Telegram
документации; поддержка старого клиента даёт явный fallback. Холодный запуск
при недоступном origin отличается от сетевой ошибки уже загруженной оболочки:
не обещай offline UI там, где HTML не получен; второй hosting/cache с личными
данными не добавляй автоматически.

Разрешены локальные code/tests/docs изменения в изолированном checkout, local
fixture backend и browser tests с синтетическими данными. Это не разрешение
изменять LIVE, main/health tasks, production БД/backup, запускать модель/ASR,
публиковать Telegram профиль, push/merge/deploy. Реальный owner smoke готовь
как конкретный сценарий G4; если нужен раньше, получи точное разрешение.

Проверки: screen matrix и реальная интеграция с локальным Core fixture,
lost ACK/reconciliation, expired/recovered session, stale response/order races,
result/TXT identity, 320–1280px, light/dark, клавиатура/200% zoom/reduced motion,
assets budget из G0. Моки только для отдельных визуальных состояний; не называй
ими backend E2E. Целевой backend regression добавляй по реальным изменениям.

Перед freeze заверши весь связный diff, docs и cache-busting/assets hashes.
Пройди один независимый L1/L2/L3 по exact code+assets+inputs кандидату. Старые
проверки незатронутых C0–C6 не повторяй; при changed bytes обнови только
затронутые/зависимые проверки с честными bindings. Не выдавай один code_digest
Python за fingerprint CSS/JS/fonts — asset digest нужен отдельно.

Приёмка G2: принятый дизайн реализован и проверен на всех состояниях;
пользовательский путь работает с настоящим локальным Core; нет регрессий
auth/idempotency/UNKNOWN/artifact; frontend budget выполнен. Реальный deployment
ещё NOT DEPLOYED. Веди один m2-g2/HANDOFF.md/EVIDENCE.json, REGISTRY и один
next Gate G3; не запускай его самостоятельно.

## Конец промпта
