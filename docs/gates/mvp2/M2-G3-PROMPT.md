# M2-G3 — Telegram, единый пользовательский путь и документация

Готовый промпт одной задачи; ещё не запущен.

## Начало промпта

Выполни M2-G3 Nobus Space: согласуй Telegram-коммуникацию и Mini App в одном
законченном MVP2 и подготовь цельный release-кандидат. Один Gate = одна задача.

Проект: канонический checkout репозитория `streetenergy63reshik-del/nobus-space`.
Прочитай AGENTS → docs/README.md → docs/handoffs/CURRENT-STATUS.md →
docs/15-Продуктовая-дорожная-карта.md → docs/mvp2/DOCUMENTATION.md →
docs/gates/mvp2/REGISTRY.md → docs/gates/mvp2/m2-g2/HANDOFF.md
и EVIDENCE.json того же Gate. Используй Nobus Memory только project:nobus-space.
Прими за вход точный результат предыдущего Gate, критерии G0 и применимые ADR.
Entry: G2 принят
на exact SHA/tree/assets, нет blocking M1-S1 regression. Проверь Git status,
назначь зону файлов и сохрани несвязанный WIP.

Работа:
1. Инвентаризируй фактические /start/help, menu, voice preview/re-record/confirm,
   clarification, progress, result/TXT, unavailable и error тексты. Основные
   владельцы — существующие telegram_product/durable_product/status renderer;
   найди точные файлы. Не создавай второй каталог product state.
2. Приведи коммуникацию к принятому дизайну и русскому стилю. Объясняй действие
   пользователя и проверяемый исход; не выводи внутренние codes/paths/credentials.
   Сохрани distinctions UNKNOWN, «принято», «выполняется», «доставлено».
3. Подготовь точный пакет profile assets/описания/menu с before/after и целевым
   ботом, считанным из безопасной конфигурации. Не публикуй его без нового
   точного разрешения. Нативный чат не поддерживает произвольные шрифты/CSS.
4. Проверь единый путь Telegram↔Mini App: одна task identity, voice confirm
   одноразовый, response после уточнения связан с запросом, повтор сообщения
   не создаёт duplicate, результат/TXT совпадают. Нельзя менять смысл ради копирайта.
5. Обнови активные docs и существующую Word-памятку на месте. Используй documents
   skill: hash/mtime до, извлечение текста и render всех страниц после. До
   activation инструкция явно помечает candidate; будущие функции не обещает.
   Не трогай docs11 без explicit inclusion как runtime input кандидата.
6. Собери один candidate manifest: code/tree, HTML/CSS/JS/assets/fonts,
   runtime input hashes, schema/config, prepared Telegram profile effects,
   регрессии, owner smoke matrix, rollback и plan публикации G4.

Разрешены локальные правки code/tests/docs/assets и синтетические проверки.
Не разрешены live profile/menu changes, сообщения владельцу от бота, paid/model/ASR
вызовы, restart, deploy, публикация/push/merge/tag, установки и изменения секретов.
Сначала подготовь конкретные документы/пакет, затем запроси только необходимые
новые effects, если они нужны до G4. Исторические permissions не переноси.

Приёмка: согласованные texts/assets готовы; все existing paths сохранены;
UX states соответствуют Core; инструкция проверена; цельный candidate не имеет
известных Critical/Major в scope; G4 получает конкретный безопасный release plan.

WIP получает целевой L1. На frozen coherent G3 candidate — обязательные
независимые L1/L2/L3, объединяющие UI, Telegram, trust boundaries и changed risks.
Подтверждённые незатронутые checks G2 переиспользуй с точной binding-гранью;
не утверждай, что результаты другой ревизии проверяют новый asset. Никакого
повторного C6. Собери замечания до пакетного rework.

Веди `m2-g3/HANDOFF.md` и `EVIDENCE.json`, обнови REGISTRY/CURRENT раздельно
для candidate/published/runtime. Финал: exact frozen package, что принято,
что не активировано, owner approvals для G4 и оставшиеся device checks.
Следующий Gate не создавай и не запускай автоматически.

## Конец промпта
