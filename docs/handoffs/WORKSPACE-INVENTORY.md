# Nobus Space — рабочие каталоги

**Актуально на 9 сентября 2026.** Канон принятой истории — защищённая GitHub main; точный опубликованный код и состояние runtime разделены в [CURRENT](CURRENT-STATUS.md).

| Каталог относительно Code | Назначение |
|---|---|
| nobus-orchestrator-dev | Основной чистый checkout main; Python-окружение и закрытые служебные архивы сохраняются. |
| worktrees/mvp1-closure-c6 | Рабочая ветка завершения и документации C6. |
| worktrees/telegram-live | Штатный runtime checkout принятой 82003c03; постоянный процесс работает. Состояние и резервные копии сохраняются отдельно. |
| nobus-orchestrator-dev/.runtime/worktrees/mvp1-closure-c2-voice-parity | Сохранён из-за ASR-модели, указанной в действующем профиле. Удалять его как промежуточную копию нельзя. |

Восемь устаревших рабочих копий удалены после проверки полных архивов: c1-publication-status, c0-publication, c0-publication-readback, c0-truth-contract, release-docs, closure-c5, docs-product-readiness и docs-status-g7-ready.

Девять исходных деревьев перенесены в закрытый `private-cleanup-10/retained-originals`: c1-semantic-compiler, c3-core-stability с двумя отдельными review-worktrees, c4-frontend-journey, command-surface, owner-ui, runtime-recovery и gate-01-acceptance. Они остаются зарегистрированными worktree ради восстановления. Часть тестовых каталогов недоступна для полного чтения; оригиналы сохранены целиком с проверкой NTFS ID, HEAD и статуса. Полная проверка хэшей недоступных байтов не заявляется.

Прежняя локальная main f18a664 сохранена веткой `codex/archive-main-before-mvp1-20260909`. Её 20 незавершённых файлов сохранены в проверенном ZIP, бинарных патчах, stash ref и Git bundle. Два уникальных документа 15/16 находятся в этом архиве и не объявлены опубликованной продуктовой документацией. Для всех 21 исходных HEAD сохранены refs и проверенный bundle. Никакие прежние stash или refs не удалены.

Восстановимые материалы находятся в основном checkout, в `.runtime/c6-entry/closure-20260909/private-cleanup-10`. Точные исходные и архивные пути доступны в локальных манифестах; частные архивы в Git не попадают. [Итог очистки и хэши доказательств](../gates/gate-c6-release/CLEANUP-10.md).

Каталоги интеграций, результаты и загрузки Telegram, production state/backups, credentials и TaskArtifacts с данными других проектов не относятся к устаревшим копиям. Их удаление не выполнялось. Старые схемы расположения сохранены в истории Git и не служат командами для текущей очистки.
