# ADR 0010. Server-mediated доступ к библиотеке владельца

**Статус решения:** ACCEPTED

**Статус реализации:** IMPLEMENTED — безопасный path index и file-transfer; анализ содержимого внешней моделью отложен

**Дата:** 2026-07-24

## Контекст

Nobus должен находить и возвращать владельцу материалы из
`C:\Хранилище\АГЕНТ`, не читать и не изменять `C:\Хранилище\WORK` и не
расширять write boundary рабочего Git worktree.

Первый вариант передавал Codex CLI дополнительный каталог через `--add-dir`.
Второй вариант использовал custom permission profile с точными `read` и
`deny`. Синтетический native-Windows probe показал: запись блокируется, но
shell-подпроцесс способен читать соседний каталог и deny-файл. Поэтому ни один
из этих вариантов не считается доказанной read-изоляцией на текущем runtime.

## Решение

1. Локальный trusted service владеет одним exact resolved owner root.
2. Root и directory identity фиксируются при startup и перепроверяются перед
   каждой проекцией и перед запуском worker.
3. `owner.library.read` означает server-mediated доступ, а не прямой
   filesystem-доступ LLM-процесса.
4. Сервер строит bounded path index: максимум 50 000 entries и 8 совпадений,
   без symlink/junction, hidden/runtime/VCS-каталогов и чувствительных имён.
5. В prompt попадают только относительные пути. Абсолютный root и содержимое
   файлов не передаются.
6. Обычный ответ, owner path-index и startup probe используют tool-less
   `model.inference`: shell, shell snapshot, apps, MCP и local file tools
   выключены. `--add-dir`, custom owner profile и иной root отсутствуют в argv.
7. `owner.library.read` несовместим с `repo.write` и `web.search`.
8. Файл владельцу отправляет отдельный `OwnerFileService` после server-side
   проверки root, размера, типа и owner binding; модель файл не открывает.
9. `C:\Хранилище\WORK` находится вне owner root и не сканируется.
10. Анализ содержимого локальных бизнес-документов внешней моделью не
    разрешается этим ADR. Для него нужен отдельный data-handling gate:
    локальное извлечение, явная per-request авторизация данных, DLP/secret
    scan, bounded excerpts и независимый review.

## Проверяемые инварианты

- owner root не добавляется в Codex CLI argv или prompt;
- owner path-index попадает только в tool-less model session; public research использует отдельный web-search-only profile без local-file scope;
- внешний worker не может открыть путь из server-projected index;
- `owner.library.read + repo.write` запрещено;
- `owner.library.read + web.search` запрещено;
- подмена root/reparse point/identity отклоняется до spawn;
- path index не читает и не пересылает содержимое;
- `C:\Хранилище\WORK` не является потомком owner root;
- секреты и бизнес-данные не попадают в Git, документацию, логи и
  `.nobus-quality`.

## Доказательства

- Реальный синтетический probe зафиксировал неприемлемость прямого Windows
  shell read: разрешённый sentinel читался, запись блокировалась, но соседний и
  deny-файл оставались читаемыми. Этот дизайн отвергнут.
- Adversarial tests проверяют отсутствие `--add-dir`, отсутствие owner root в
  prompt, выключенные shell/apps/MCP для answer/owner/web, запрет web/write
  сочетаний, identity check, bounded scan, cancellation и исключение
  чувствительных путей.

## Последствия

Положительные:

- сервер может безопасно находить и отправлять файлы владельцу;
- `C:\Хранилище\WORK` и произвольные каталоги не становятся областью worker;
- внешний Codex не получает ambient filesystem authority;
- write pipeline остаётся ограничен worktree.

Ограничение:

- текущий worker может сообщить найденный относительный путь или вернуть файл
  через Telegram, но не анализирует содержимое произвольного локального
  документа. Это честное ограничение до отдельного безопасного content gate.
