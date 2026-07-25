# ADR 0015 — Nobus Memory progressive retrieval

**Статус ADR:** ACCEPTED
**Статус реализации:** IMPLEMENTED
**Дата:** 2026-07-25

## Контекст

Telegram-оркестратор должен использовать ту же курируемую Obsidian-память,
что и локальный Codex, но прямой filesystem-доступ модели к vault нарушил бы
client isolation, DLP и принцип минимальных полномочий. Передача всего vault
также создаёт stale truth, лишний контекст и риск смешения клиентов.

## Решение

1. Источник памяти — `C:\Хранилище\АГЕНТ\Nobus memory`. Git, project files,
   Google API и клиентские источники остаются source of truth.
2. Trusted server-side `NobusMemory` читает только Markdown с валидным
   frontmatter и формирует progressive context pack из не более семи
   релевантных заметок и не более 14 000 символов.
3. `.git`, `.obsidian`, Sources, Archive и Templates не попадают в LLM
   context. Secret-like заметка пропускается целиком.
4. Клиентская карточка выбирается только при явном упоминании клиента.
   Неупомянутые клиентские контуры исключаются до scoring.
5. В prompt каждая заметка имеет `id`, `scope`, `status`, `updated` и
   относительный source. Блок явно объявлен reference data, а не инструкцией.
   Он не даёт модели дополнительных tools, сети или filesystem authority.
6. Точная owner-команда `Сохрани в Nobus Memory: <текст>` создаёт новый
   атомарный `pending_review` note в `01 Inbox`. Существующие notes не
   перезаписываются, секретоподобные значения отклоняются, provenance
   связывается с digest доверенного Telegram ingress.
7. Inbox note становится каноническим project/client/decision/lesson
   knowledge только после обычной курации, source-check и L1/L2/L3.
8. Calendar, Tasks и Drive продолжают получать свежие данные через Google API;
   сохранённый memory snapshot не подменяет live integration.

## Последствия

- Nobus отвечает с тем же долговременным проектным и клиентским контекстом,
  который доступен Codex через skill, без чтения всего vault.
- Новая запись владельца доступна последующим запросам, но не меняет политики
  и решения автоматически.
- Ошибка или отсутствие релевантной заметки не расширяет файловые права модели
  и не включает cross-client fallback.
- Исторические и большие источники читаются только отдельным доверенным
  adapter после явного запроса.

## Проверка

- выбор релевантных notes и лимит context pack;
- client isolation и отсутствие неявного cross-client retrieval;
- secret-bearing note/write rejection;
- exact owner save route без общей LLM-очереди;
- маркировка memory block как data, а не instructions;
- startup с реальным vault, полный pytest и независимые L2/L3.
