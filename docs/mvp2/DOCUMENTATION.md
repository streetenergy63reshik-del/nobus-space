# Документация MVP2: единый источник и выпуск

21 сентября 2026. MVP2 состоит из одного функционального Gate M2-DESKTOP.
Цель задана владельцем; техническая архитектура DRAFT, Gate находится в
WIP / DESKTOP IPC ADAPTER CHECKPOINT: owner IPC работающего Desktop подтвердил
initialize и discovery владельца; локальный adapter готов, но изменяющий smoke
и D01–D17 ещё не выполнены. Блокер отдельного App Server сохранён как
route-specific, а не как невозможность всего MVP2.
Старые M2-G0…G4 заменены. Эта редакция подготовлена локально; разрешения
на публикацию или активацию из старых документов не наследуются.

## Файлы и роли

Основной продуктовый план — `docs/15-Продуктовая-дорожная-карта.md`.
Технический контракт — `docs/gates/mvp2/M2-DESKTOP-ARCHITECTURE.md`;
отдельный запуск — `docs/gates/mvp2/M2-DESKTOP-PROMPT.md`.
Версионное транспортное исследование —
`docs/gates/mvp2/M2-DESKTOP-TRANSPORT-RESEARCH.md`.
`docs/16-Управленческая-карта-разработки.html` генерируется из него и содержит
SHA256 исходника (UTF-8, переносы строк LF; проверка также нормализует CRLF).
HTML не читает сеть, не изменяет систему и не является
источником статуса. Не копировать backlog в Obsidian: только указатель/короткий
результат с датой и exact revision через разрешённый managed handoff.

`docs/gates/mvp2/REGISTRY.md` хранит исполнение Gate; план не содержит вторую
независимую таблицу процентов или придуманных дат. В каждом Gate-пакете ровно
один HANDOFF.md и один EVIDENCE.json; для нового Gate — `m2-desktop/`.
Папка создаётся при запуске этого Gate,
не заранее ради пустых документов. Промпты уже подготовлены отдельно.

## Обновление без дрейфа

1. Перед правкой прочитать status/diff и определить владельца файлов.
2. В WIP менять относящийся раздел и короткий resume внутри одного handoff;
   не переписывать весь комплект после каждой команды.
3. На checkpoint сверить scope, state, requirements и evidence; обновить
   REGISTRY и CURRENT только по подтверждённым фактам.
4. На принятом Gate занести exact base/result SHA/tree, test receipts/digests,
   blockers/ограничения и следующий незавершённый шаг того же Gate. Если commit ещё не существует,
   фиксировать content digest и NOT COMMITTED; никогда не угадывать SHA.
5. После изменения docs15 выполнить из корня проекта:

   `python -B docs/mvp2/System/render_roadmap.py`

   Скрипт использует стандартную библиотеку, пишет только docs16 и не запускает
   tests/provider/браузер. Он намеренно поддерживает используемый поднабор Markdown.
6. Проверить generated consistency без записи:

   `python -B docs/mvp2/System/render_roadmap.py --check`

   Дополнительно проверить относительные ссылки, архитектуру и промпт M2-DESKTOP, реальные
   статусы, отсутствие секретов и визуальный desktop/mobile/print при изменении
   структуры/стиля. Смена даты сама по себе не требует повторять browser matrix.
7. Перед freeze зафиксировать coherent source и bindings; после новых bytes
   повторить изменённые и зависимые проверки. Старые успешные C0–C6 не повторять.

В EVIDENCE.json минимально: schema_version, gate_id, stage, observed_at_utc,
base_commit/tree, candidate_commit/tree либо content_digest, checks с status,
tool/version, subject digest, evidence ref/hash; findings с owner/class/status;
publication, deployment и next_step. UNKNOWN/null объясняется; PASS не возникает
из отсутствия результата. Не включать raw logs, credentials или личные задачи.

## Публикация

Формат: Markdown, санитизированные JSON receipts и производная standalone HTML
в том же Git-репозитории. Для владельца достаточно открыть HTML локально; новый
хостинг или GitHub Pages не нужен. Размещение на app.nobusspace.com не входит в
план документации: этот адрес остаётся продуктовым ingress.

1. Сначала завершить локальный coherent docs package, проверки и review.
2. Получить точное разрешение на branch/push/PR/merge с нужным repo/ref. Обычная
   публикация docs не разрешает deploy и не создаёт отдельный формальный L4.
3. В PR указать scope, что является TARGET, какие проверки выполнены, product
   SHA и отсутствие runtime effect; после merge прочитать remote SHA/tree.
4. Сам roadmap может быть опубликован как **PROPOSED** только с явным разрешением
   такой публикации. Merge не заменяет утверждение scope. ACCEPTED писать лишь
   после прямого принятия владельцем и соответствующего Gate verdict.
5. Release product tag указывает на принятый product candidate. Последующий
   docs-only commit фиксирует факт выпуска; product tag не перемещается.
   Название будущего тега выбирается при выпуске M2-DESKTOP по реальному состоянию refs:
   номер MVP2 не означает автоматически SemVer v2.0.0.
6. Startup/deploy/Telegram profile changes выполняются отдельно по точным
   разрешениям и receipts. Docs-only publication не активирует новый UI.

До публикации исключить внутренние абсолютные пути, task IDs, системные account
имена и сырой JUnit/Windows output из публичной проекции, когда они не нужны
для воспроизводимости. Закрытые оригиналы evidence остаются в private System;
публичные относительные refs/digests не маскируют фактически пропущенные проверки.

## Канон после релиза

CURRENT всегда различает четыре вещи: принятый product SHA, опубликованную docs
revision, активный runtime SHA/config/assets и время последней проверки. Инцидент
не переписывает приёмку; исправление не получает прежний PASS автоматически.

Единственная пользовательская инструкция:
«Памятка — управление Nobus Space Bot.docx» в существующей папке владельца Nobus Space Bot.
Обновлять на месте с hash/mtime до правки, извлечением текста и визуальной
проверкой всех страниц после неё. Не создавать dated/final/v2 копий и не
заявлять будущие capabilities как работающие.

## Контроль перехода

Архитектор проверяет coherent handoff и фактические bindings. Разработчик ведёт
изменения в назначенной зоне. Владелец принимает scope/дизайн/пользовательский
результат и даёт точные внешние разрешения. Независимые проверки выполняются по
одной замороженной ревизии; автоматического запуска следующего Gate нет.
