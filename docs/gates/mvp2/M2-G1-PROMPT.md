# M2-G1 — визуальная система и прототип

Готовый промпт одной задачи; ещё не запущен.

## Начало промпта

Выполни M2-G1 Nobus Space: создай принятую визуальную систему PROстранства и
полный интерактивный прототип MVP2. Один Gate = одна задача; следующий не запускай.

Проект: канонический checkout репозитория `streetenergy63reshik-del/nobus-space`.
Прочитай AGENTS → docs/README.md → docs/handoffs/CURRENT-STATUS.md →
docs/15-Продуктовая-дорожная-карта.md → docs/mvp2/DOCUMENTATION.md →
docs/gates/mvp2/REGISTRY.md → docs/gates/mvp2/m2-g0/HANDOFF.md
и EVIDENCE.json того же Gate. Используй Nobus Memory только project:nobus-space.
Прими за вход точный результат предыдущего Gate, критерии G0 и применимые ADR.
Entry: M2-G0 ACCEPTED с точным
scope/brand/criteria/base; M1-S1 не имеет текущего blocking incident. При отсутствии
predecessor не придумывай контракт. Проверь Git status и сохрани чужой WIP.

Используй frontend-design и принятые в G0 brand references. nobus-color-direction
применяется только к незаданным цветам; действующий бренд приоритетнее. Не
покупай/не устанавливай шрифты и не загружай внешние assets без точного разрешения.

Результат:
1. Компактные дизайн-токены light/dark: font roles/fallback, spacing, surfaces,
   interactive/focus, success/warning/error. Все HEX с назначением и контрастом;
   цвет не единственный признак состояния. Законный локальный font либо system fallback.
2. Экранная система всех states из G0, включая сложные error/UNKNOWN/reopen paths.
   Голос передаётся текущим Telegram ingress и подтверждается до задачи; UI не
   изображает несуществующий mic/upload/agents feature. Текст не получает новый
   approval ritual без принятого решения.
3. Интерактивный прототип с синтетическими данными и явной отметкой «Прототип»:
   список → create/clarify → progress → result/copy/TXT; preview/re-record/confirm
   показывают будущую коммуникацию, не выполняя backend или effects.
4. Готовые размеры/варианты аватара/иконок/профиля и тексты бренда для G3. Не
   публикуй их в Telegram. Фиксируй hashes и происхождение; не выдавай набросок
   за утверждённый asset. При imagegen прочитай применимый skill.

Сверь прототип на 320/360/390/768/1280px, light/dark, focus/клавиатуре,
200% text zoom, safe area и reduced motion; no horizontal overflow. Основные
targets 44px, contrast 4.5:1 и 3:1 в соответствующих ролях либо принятые G0 пороги.
Измерь начальные bytes и не добавляй UI framework ради прототипа. Предпочитай
существующие HTML/CSS/ES modules. Запиши ограничения эмуляции vs реальные устройства.

Локальные docs/prototype/assets разрешены в назначенной зоне docs/mvp2 и
m2-g1. Production runtime, state, API semantics и deployed UI не менять.
Запуск модели/ASR, Bot API changes, установка, push/merge/deploy требуют отдельных
текущих разрешений. Исторические C6/G0 permissions не расширяй.

Приёмка: все экраны/состояния покрыты matrix; tokens/контраст проверены;
реальный владелец принял показанный прототип; assets воспроизводимы и права
понятны; G2 получает конкретные files/hashes и interaction contract. Прототип
с mocks не доказывает end-to-end MVP2 и не получает product READY.

Сначала L1 по текущему прототипу; один цельный freeze и независимые L2/L3 по
дизайну, accessibility, отсутствию ложных capabilities и trust boundaries.
Не гоняй старые backend suites ради визуального candidate. Замечания собери,
исправь пакетно; новые bytes получают новые bindings и затронутые проверки.

Веди один m2-g1/HANDOFF.md и EVIDENCE.json, обнови REGISTRY. Передай G2 точные
base/result, принятие дизайна, список assets, screen/state matrix и ограничения.
Остановись после G1 verdict; не создавай задачу G2 самостоятельно.

## Конец промпта
