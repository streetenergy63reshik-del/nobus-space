# ADR 0010. Read-only область библиотеки владельца

**Статус решения:** ACCEPTED

**Статус реализации:** CURRENT LIVE — safe index/content adapter и `/file` приняты L1/L2/L3 и owner L4

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
6. Только при явном запросе server-side index/content adapter сканирует корень без перехода по symlink/junction, передаёт worker bounded sanitized context либо отправляет разрешённый файл; абсолютный root в продуктовый ответ не включается.
7. Один запрос ограничен 50 000 directory entries и 8 совпадениями.
8. Запрещены hidden/control names, `.git`, `.codex`, `.cache`, `.venv`, `.runtime`, `.env`, а также sensitive names с markers auth, cookie, credential, login, password, secret, session, token и vpn.
9. Path index входит в общий deadline контракта и получает cooperative stop при timeout/cancel. До безопасного content adapter capability означает поиск пути, а не чтение содержимого.
10. Startup sentinel не получает `owner.library.read` и по-прежнему не читает owner-library.
11. Активация новой ревизии в работающем runner требует отдельного L4.

## Инварианты

- LLM не назначает себе permission и не меняет корень.
- `owner.library.read` несовместим с `repo.write`.
- Ни один путь библиотеки не передаётся в patch pipeline.
- Любой code effect остаётся exact diff внутри `agent/telegram-live` и требует owner-bound L4.
- Внешняя сеть, merge, rebase, push и remote отсутствуют.
- Секреты не включаются в prompt, ответ, audit или `.nobus-quality`.
- Codex CLI не получает filesystem authority на owner root и не получает абсолютный owner path в prompt.

## Остаточный риск

Path-only index устраняет передачу file content и зависимость от внешнего filesystem scope Codex CLI, но Python runner всё ещё работает под owner Windows account без отдельной OS identity. Ошибка denylist теоретически может раскрыть лишнее имя файла; без handle-level ACL остаётся минимальное race-window между повторной проверкой directory и `scandir`. Поэтому решение допустимо только для локального owner-bound MVP.

До production требуется один из вариантов:

- отдельная Windows identity с ACL только на утверждённую проекцию;
- read-only projection/staging area с deterministic manifest;
- усиление текущего path index: signed manifest, per-project allowlist и audit digest;
- отдельный content adapter с явным выбором файла, secret-scan и изоляцией untrusted content.

## Последствия

Положительные:

- оркестратор может находить проектные документы внутри библиотеки владельца;
- write boundary не расширяется;
- доступ проверяется отдельным permission и fail-closed конфигурацией;
- startup probe и обычный repository-only adapter остаются совместимыми.

Отрицательные:

- server-side reader не заменяет отдельную OS identity и per-project ACL;
- `sendDocument` имеет узкое at-least-once crash-window; Google Drive остаётся отдельным TARGET connector;
