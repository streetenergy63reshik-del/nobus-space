# Gate C6: выпуск MVP1

**9 сентября 2026: SCOPED SOURCE CORRECTION PASS / ACTIVATION REWORK / NOT READY.** Точный источник `1bb1d85b9f9d6c7f8c5ed1edbf5e69680a021921`, tree `5fa988d224199ffb92a1c041d4d9e16c86755ee8`. [SOURCE-CORRECTION-03.json](SOURCE-CORRECTION-03.json) связывает 201 затронутую проверку и независимые L2/L3.

## Текущее состояние

Рабочая версия — опубликованный обычным [PR23](https://github.com/streetenergy63reshik-del/nobus-space/pull/23) merge `4c6d400898a47c63a993171f57d8be4265b3eec8`. Это исправление stdin запроса Git; [SOURCE-CORRECTION-02.json](SOURCE-CORRECTION-02.json) сохраняет его 127 проверок и независимые verdict. Владелец прямо разрешил все необходимые действия для доведения MVP1 до готовности и полное L4. Применены D3 source/config и точный отключённый Backup Action, новая prechange-копия проверена расшифрованием. Все три задания Disabled; production ещё не запускался.

Миграция сохранила 79 задач, 77 подтверждённых доставок и прежний inventory. Старые базы и зашифрованные snapshots сохранены. Локальное использование cuDNN принято. Два прежних групповых update по отдельному разрешению архивированы и подтверждены без исполнения, заметок или ответов. Новых групповых действий не было.

## Последняя коррекция

Recovery-c6-03 остановился через 38,187с после начала измерения. Preflight установил точную причину: state расположен вне worktree, а временный каталог был выбран внутри state; существующий build_worker_env справедливо отклонил его до вызова модели и ASR.

Теперь temp расположен внутри проверенного worktree `.runtime/codex-tmp`; изолированные state получают разные подкаталоги по SHA256 нормализованного пути. checked_path выполняется перед mkdir, исходный containment guard не менялся. Данные, voice-temp и artifacts остаются в своих state. Старые временные каталоги не удаляются.

Четыре composition-сценария с настоящим build_worker_env воспроизвели отказ. После коррекции 176 проверок C5 operations, CLI/SDK и managed backup прошли за70,77с. L3 обнаружил одну устаревшую подмену private-константы в runner-тесте; она удалена, все25 runner-тестов прошли за3,65с. Продуктовые bytes между faed33d и финальным1bb1d85 неизменны. L2 независимо выполнил пять проверок и шесть проверок извлечённого runtime-фрагмента. Итоговые L2/L3 относятся к текущей revision; прежний HOLD сохранён в evidence.

После STOP все строки восстановленной и production базы, checkpoint и canonical20 WIP неизменны; порт8765 и mutex свободны. Supervisor завершился1: это доказанная остановка неудачного запуска, не успешная активация. Полный RTO сохраняет FAIL_STARTUP; бюджет не сброшен.

## До готовности

1. Опубликовать текущую коррекцию и связать последующее переключение с точными source/config/backup/temp targets в рамках прямого разрешения владельца.
2. Выполнить отдельный полный RTO≤30мин с настоящими worker/ASR и private owner result/TXT, затем production, scheduled backup и controlled restart.
3. Пройти реальные пользовательские text/voice/Mini App/download сценарии и ≥15мин наблюдения. Получить фактическую owner acceptance точного продукта.
4. Применить принятую постоянную Scheduler фазу, проверить обязательный последующий backup, выпустить v1.0.2 и обновить итоговые документы. Принятый продукт оставить работающим.

Прежние [SOURCE-ACCEPTANCE](SOURCE-ACCEPTANCE.json), [SOURCE-CORRECTION-01](SOURCE-CORRECTION-01.json) и [SOURCE-CORRECTION-02](SOURCE-CORRECTION-02.json) сохраняют исторические scopes. [OPERATIONS](OPERATIONS.md) и [WORKING-CONTRACT](WORKING-CONTRACT.md) сохраняют RPO≤24ч,7daily/4weekly, DPAPI и fail-closed rollback. Восстановление поверх live DB и ручное снятие hold не выполняются; защита от потери диска/Windows account не обещается.

Единая Word-памятка пока DRAFT, SHA256 `c52602089c6ca751101d4408f6f42de09a27e8b374b2d1d087da2901d8f3eeba`,44787байт,6 проверенных страниц; [MANUAL.json](MANUAL.json). Она будет обновлена по фактическому deployment. C0–C5, canonical20 WIP, held docs15/16 и история сохранены. MVP2 HOLD.
