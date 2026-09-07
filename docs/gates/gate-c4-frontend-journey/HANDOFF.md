# Единая передача Gate C4 → C5

**DRAFT / C4 NOT ACCEPTED / C5 HOLD.** Этот документ сохраняет состояние C4, но не разрешает начало C5.

Repository: `streetenergy63reshik-del/nobus-space`. Ветка: `codex/mvp1-closure-c4-frontend-journey`.
Worktree: `nobus-orchestrator-dev/.runtime/worktrees/mvp1-closure-c4-frontend-journey`.
Принятая база: `b9283b3419928042c80278b5088b526edebab6e7`, tree `77062335b1dbccb3694721d357e484c856ac89c7`. Identity кандидата и checks записываются в [EVIDENCE](EVIDENCE.json) и отдельный exact receipt; файл не содержит самоссылочного SHA своего commit.

Реализованы общий безопасный каталог состояний, session rotation и request journal Core, clarification readback, восстановление UI, text-only результат/копирование/download и mobile/theme/focus tokens. Underlying result/artifact bytes, id, digest и part receipts C3 сохранены; файл имеет presentation alias nobus-result.txt. Bearer только в памяти; storage хранит лишь непривилегированные opaque markers.

Условия завершения C4: собственный frozen L1, независимые L2/L3, actual local inference paths, browser320/390/768 light/dark + keyboard, одно точное разрешение и настоящий Telegram/Mini App smoke, затем ordinary protected-main PR/merge/readback. Локальные doubles не подменяют реальные поверхности.

Внешняя зависимость: Telegram-клиент запущен, но tools возвращают trusted RPC package error; HTTPS `https://app.nobusspace.com` возвращает502, порт8765 не слушает. Bot identity проверена. Накопленные Telegram updates не забирались и не удалялись. Временный runtime/route и безопасное обращение с накопленными updates требуют точного smoke-плана после freeze. Ни live DB, ни Scheduler/VPS/BotFather/menu/profile не изменялись.

C5 стартует только от accepted/published C4 SHA/tree. В C5 остаются operations/ingress/security/recovery и итоговая инструкция по доказанному UI; C6 — release/owner acceptance. **NO TAG / RELEASE / PERMANENT PRODUCTION DEPLOY; MVP1 NOT READY.**
