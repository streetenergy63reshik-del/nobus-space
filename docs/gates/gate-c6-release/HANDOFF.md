# Gate C6: выпуск MVP1

**9 сентября 2026: SCOPED SOURCE CORRECTION PASS / ACTIVATION REWORK / NOT READY.** Источник `bba7d21530bd467339d1982b46051e578408f66d`, tree `4da0de08fcf7563a42095ed07f1370f7038892c8`. [SOURCE-CORRECTION-02.json](SOURCE-CORRECTION-02.json) связывает новую регрессию,127 затронутых PASS и независимые L2/L3. Готовность работающего продукта ещё не подтверждена.

## Опубликованное и установленное

Первоначальный C6 source `3a5625898ce4f66ff39c85685e926ea1e0e8afa1` прошёл2345PASS+25subtests, frontend20 и L2/L3; [SOURCE-ACCEPTANCE.json](SOURCE-ACCEPTANCE.json) сохраняет точные границы этой проверки. Он опубликован обычным PR21, merge `7ea915790c382473378078065f0d7d3630fb56e6`.

Первое исправление запуска `b8e8ac41a401aa839710d7b11a72f76f02d97607` сохранило PROGRAMDATA в ограниченном окружении Windows OpenSSH:107 затронутых PASS и L2/L3, [SOURCE-CORRECTION-01.json](SOURCE-CORRECTION-01.json). Обычный [PR22](https://github.com/streetenergy63reshik-del/nobus-space/pull/22) принят с merge `0b6425fed9aa82417cba299352d058d55811109c`. После точного подтверждения C6-ACT-01-D2 LIVE и application-bound конфигурации переключены на эту revision. Все три задания Disabled.

Совместимая миграция сохранила79 задач,77 подтверждённых доставок и прежний inventory. Старые базы и зашифрованные snapshots сохранены. Первая управляемая копия и новая prechange-копия под0b6425 прошли расшифрование/integrity. Production не запускался. Локальное использование cuDNN9.10.2 принято владельцем. По отдельному разрешению два групповых update архивированы DPAPI и подтверждены без исполнения, заметок или ответов.

## Вторая причина остановки

Отдельный recovery-c6-02 восстановлен и сверён, но Core не достиг readiness. Синхронный запрос Git revision наследовал stdin, из которого daemon-поток ожидал команду остановки. Изолированный реальный Git без читателя завершился за0,078с; с активным читателем завис до команды родителя и дал TimeoutExpired; с DEVNULL завершился за0,101с. Это проверка Git, а не успешный запуск продукта.

В общем application_binding добавлен только stdin=DEVNULL. Windows regression вызывает настоящий application_binding при ожидающем потоке stdin и проверяет revision; до исправления он падал, после прошёл. Runtime operations, managed backups, voice retention и Windows regression дали108PASS за56,46с; backup recovery —19PASS за20,15с. Эти127 проверок относятся к новой дельте; полная историческая проверка не приписывается новым bytes.

После неудачной попытки все строки восстановленного и production state, включая checkpoint, неизменны; порт8765 и оба mutex свободны. Три задания Disabled, canonical20 WIP сохранены. Неудачный graceful cleanup и последующая доказанная остановка сохранены как отдельные факты; полный RTO имеет FAIL_STARTUP. Бюджет попыток и консервативный model/ASR reserve не сброшены.

## До завершения C6

1. Опубликовать проверенную дельту обычным PR/merge и получить подтверждение только нового deployment/config/restore target. Принятые планы и failed roots сохраняются.
2. Измерить полный отдельный RTO≤30мин с pinned worker/ASR, реальным результатом/TXT и сверкой после STOP; затем проверить production runtime, настоящий scheduled backup и controlled restart.
3. Пройти реальные owner text/voice/Mini App/download сценарии, ≥15мин наблюдения и получить явную итоговую приёмку exact release.
4. Применить согласованную постоянную Scheduler фазу, опубликовать v1.0.2 и итоговые документы; оставить принятый продукт работающим.

[OPERATIONS](OPERATIONS.md) и [WORKING-CONTRACT](WORKING-CONTRACT.md) сохраняют RPO≤24ч,7daily/4weekly, локальный DPAPI, bounded effects и fail-closed rollback. Восстановление поверх live DB и ручное снятие hold не разрешены. Защита от потери диска/Windows account не обещается.

Единая Word-памятка остаётся DRAFT на прежнем пути, SHA256 `c52602089c6ca751101d4408f6f42de09a27e8b374b2d1d087da2901d8f3eeba`,44787байт,6 страниц после визуальной проверки; [MANUAL.json](MANUAL.json). Команды и статус будут сверены с окончательным deployment. C0–C5 сохраняют прежнюю приёмку; canonical20 WIP, held docs15/16 и history сохранены. MVP2 HOLD.
