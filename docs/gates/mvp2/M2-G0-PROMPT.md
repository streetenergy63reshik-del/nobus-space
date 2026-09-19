# M2-G0 — контракт фирменного мобильного продукта

Готовый промпт одной задачи; ещё не запущен. Текст ниже применяется после
явного запуска владельцем. Не создавай другие пользовательские Gate-задачи.

## Начало промпта

Выполни только M2-G0 Nobus Space: согласуй исполнимый контракт MVP2, основанный
на действующем MVP1. Один Gate = одна задача. Паузы и исправления продолжай здесь.

Проект: канонический checkout репозитория `streetenergy63reshik-del/nobus-space`.
Прочитай AGENTS → docs/README → docs/handoffs/CURRENT-STATUS.md →
docs/15-Продуктовая-дорожная-карта.md → docs/mvp2/DOCUMENTATION.md →
docs/gates/mvp2/REGISTRY.md. Используй Nobus Memory только project:nobus-space.
История v1.0.2/82003c03 и C6 принята; прежние approvals не дают текущих полномочий.

Entry: M1-S1 закрыт по точным evidence, известны accepted base SHA/tree и
фактический runtime; владелец разрешил начать MVP2. Если этого нет, выполни
независимую подготовку контракта, но не объявляй entry PASS и не начинай G1.
Прочитай Git status; сохрани чужой WIP. Зафиксируй собственную зону docs/mvp2,
docs15/16, REGISTRY и m2-g0. Статус плана PROPOSED не превращай в ACCEPTED молча.

Цель: владелец с телефона ставит существующие текстовые/подтверждённые голосовые
задачи, понимает статус и получает результат/TXT в узнаваемой системе PROстранства.
Никаких новых models, format ingress, agents, источников/эффектов, второго Core
или переноса runtime. Понимание задач уже входит в MVP1; не создавай C1/C2 заново.

Работа:
1. Сверь реализованные journeys, лимиты и архитектуру ADR0022–0027 с текущим кодом.
   Обнаруженные нарушения MVP1 отнеси к сопровождению, не прячь в редизайн.
2. Найди утверждённые референсы сайта/презентации PROстранства в разрешённом
   контуре; exact paths/versions/hashes, права на font/assets. Если нескольких
   действующих вариантов нет возможности различить, предъяви конкретный выбор
   владельцу. Архивное упоминание Helvetica Neue не разрешает распространять font.
3. Зафиксируй scope, экраны и все состояния: empty/loading/active/clarification,
   preview voice/confirm/re-record, result/TXT, failed/unavailable, expired session,
   request UNKNOWN/reconciliation, reconnect. Раздели native Telegram ограничения
   и Mini App. Не обещай сменить шрифт нативного чата.
4. Зафиксируй M2-01…M2-10 и измерения: устройства/версии Telegram, viewport,
   light/dark, клавиатура, 200% zoom, контраст, количество действий, asset/latency
   baseline и список owner smoke. Цифры roadmap являются предложением до принятия.
5. Подтверди unchanged invariants: server-derived owner/tenant/capability,
   one Core/state/queue, volatile bearer, no secret in UI, no blind mutation retry,
   task/result/digest parity, voice confirmation. Любую смену semantics вынеси
   отдельным решением до реализации; не добавляй text-confirm шаг случайно.
6. Прими docs workflow: Markdown15 primary, HTML16 generated, один REGISTRY,
   один handoff/evidence каждого Gate, CURRENT с раздельным release/runtime.
   Изменяй ADR только добавлением нового принятого решения, если оно реально нужно.

Приёмка G0: полный scope/in-out; verified brand references или явный нерешённый
блокер; измеримые criteria; journey/state matrix; согласованная структура
G1–G4 без дублирования; точная base и owner approval контракта. Не проводи
runtime smoke, модель/ASR, установку или публикацию ради документного Gate.

Разрешены локальные документы и чтение. Запуск G0 не разрешает production code
edits, live profile changes, deploy, push/merge/release, внешние сообщения или
создание автоматизаций. Подготовь reviewable результат до вопроса о согласовании.
Не спрашивай повторно, если точное разрешение уже дано в этой задаче.

На checkpoint выполни проверку ссылок/непротиворечивости/полноты и render --check.
На цельном frozen контракте проведи независимые L1/L2/L3 по проектным правилам,
проверяя scope/authority/UX gaps; это не повтор исторических code suites C0–C6.
Собери замечания перед пакетной правкой, сохрани bindings каждого результата.

Создай `docs/gates/mvp2/m2-g0/HANDOFF.md` и `EVIDENCE.json`. Обнови REGISTRY
реальным task id/title, base/result, status; не угадывай будущие SHA. Передай
один итог с scope acceptance, blocker list и G1 allowed/blocked. Не запускай G1.

## Конец промпта
