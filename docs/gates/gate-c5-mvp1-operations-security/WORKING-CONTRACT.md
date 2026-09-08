# C5 эксплуатация восстановление и безопасность

Стадия: WIP. База `1b3cf67405c4523258dd8b400d17d09601f815ff`, tree
`c302123e6f3ae93668e4fca7580b24d424056f94`. Remote main сверена 8 сентября2026.
Цель: надёжная локальная owner-bound композиция Telegram/Mini App над одним Core.
Приёмка: обязательства A–F, disposable drills, frozen L1 и независимые L2/L3,
обновлённая единая памятка, затем обычный PR/merge/readback. Риск высокий.
Постоянный deploy, C6, tag/release, live restore и удаление старых данных запрещены.

| Обязательство | Факт входа | Пробел | Действие | Доказательство |
|---|---|---|---|---|
| Exact entry и WIP | C4 objects/trees/blobs/lineage совпадают;20dirty canonical;live/C4 чистые | Нет | Изолированный worktree, до/после hashes | Внешний preflight-preservation.json |
| Запуск/остановка | Singleton/lease/Job есть; scheduler отключён, pollers0, port8765 свободен | Spawn до Job, нет steady readiness, Health обходит restart budget | Gated spawn, bounded graceful stop, hang checks, один restart budget | C5 runtime tests/drill |
| Ingress | Exact Origin, body/query/CSP, C4 recovery | Header/connection/rate/response/total limits неполны | Пределы на pinned HTTP/ASGI, fail-closed readiness | C5 ingress tests; retained C4 auth/recovery |
| Backup/restore |3 mandatory stores+optional legacy из composition; SQLite backup/schema/digests | Version/target/watermark/auth/journal binding | Encrypted bounded snapshot, staged restore и запрет rollback новых effects | C5 representative restore/drill |
| Cleanup/retention | C2 voice1h и tombstone24h приняты | Recovery paths/ownership, нет принятой общей retention policy | Exact ownership/reparse guards;live dry-run;owner decision после drill | C5 cleanup negatives |
| Security/dependencies | Собственные исходники, установленные native компоненты C2 | Closure/provenance и наследованные licence/CVE limits | Датированный read-only inventory и официальные источники | DEPENDENCIES.md |
| Инструкция | Единый DOCX описывает старый release/автостарт | Нет current UI/recovery/C5 границ | Тот же DOCX, CAS/hash/render всех страниц;Runbook/CURRENT/issues | Manual manifest+QA |

Memory pointer прочитан штатным bridge, READY; заметка от26августа устарела.
Источник истины — проверенная Git-база; Memory не менялась.
Внешняя публикация source не означает работающий runtime. Live test window пока NOT RUN.
