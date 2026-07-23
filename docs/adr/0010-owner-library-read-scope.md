# ADR 0010. Read-only область библиотеки владельца

**Статус решения:** ACCEPTED

**Статус реализации:** PARTIAL — реализовано в `main`, live-активация ожидает L4

**Дата:** 2026-07-23

## Контекст

Owner-bound Telegram-оркестратор должен находить и читать проектные материалы не только в изолированном Git worktree, но и в библиотеке владельца `C:\Хранилище\АГЕНТ`. Предыдущий worker contract запрещал любой путь за пределами репозитория, поэтому корректно отказывался искать существующий HTML-файл.

Расширять write-scope нельзя: библиотека содержит несколько проектов, документы и служебные каталоги. Флаг Codex CLI `--add-dir` не используется, поскольку он добавляет директории с правом записи, а не узкие read-only inputs.

## Решение

1. Серверная конфигурация owner-bound runner задаёт один точный корень библиотеки: `C:\Хранилище\АГЕНТ`.
2. Контракт получает отдельное permission `owner.library.read`.
3. Permission принимается только если adapter сконфигурирован существующим корнем и контракт не содержит `repo.write`.
4. Codex CLI продолжает работать с `--sandbox read-only`; web, MCP и ambient secrets выключены.
5. Рабочей директорией остаётся изолированный Git worktree. Дополнительный корень не становится `allowed_path` для diff, apply, tests или commit.
6. Worker получает корень как server-owned policy, а не из текста Telegram. В ответах пути возвращаются относительно корня библиотеки.
7. Запрещено читать `.git`, `.codex`, `.cache`, `.venv`, `.runtime`, `.env`, каталоги credentials/secrets и иные данные аутентификации.
8. Startup sentinel не получает `owner.library.read` и по-прежнему не читает файлы.
9. Активация расширенного read-scope в работающем runner требует отдельного L4.

## Инварианты

- LLM не назначает себе permission и не меняет корень.
- `owner.library.read` несовместим с `repo.write`.
- Ни один путь библиотеки не передаётся в patch pipeline.
- Любой code effect остаётся exact diff внутри `agent/telegram-live` и требует owner-bound L4.
- Внешняя сеть, merge, rebase, push и remote отсутствуют.
- Секреты не включаются в prompt, ответ, audit или `.nobus-quality`.

## Остаточный риск

В CURRENT Windows desktop deployment read-only sandbox и server-owned prompt policy не являются отдельной OS ACL на каждый файл. Процесс технически может иметь право чтения других локальных путей, доступных Windows account. Поэтому решение допустимо только для локального owner-bound MVP.

До production требуется один из вариантов:

- отдельная Windows identity с ACL только на утверждённую проекцию;
- read-only projection/staging area с deterministic manifest;
- специализированный file adapter, который сам проверяет корень, denylist, размер, тип и digest и передаёт worker только разрешённое содержимое.

## Последствия

Положительные:

- оркестратор может находить проектные документы внутри библиотеки владельца;
- write boundary не расширяется;
- доступ проверяется отдельным permission и fail-closed конфигурацией;
- startup probe и обычный repository-only adapter остаются совместимыми.

Отрицательные:

- текущая изоляция чтения policy-based, а не OS-enforced;
- Telegram пока возвращает текст и относительный путь, но не отправляет локальный файл как document;
