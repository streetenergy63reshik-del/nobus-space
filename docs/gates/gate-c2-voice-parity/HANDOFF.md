# Gate C2 → C3

<!-- C2_CURRENT_START -->
**C2 принят: PASS / PUBLISHED / NOT DEPLOYED.**

Проверенный кандидат: `98aa8dc545eaf3c80a820cec4c8ab0601e4fdfc6`, дерево `c81539fdad74ec3f296c7926aeb77c8e78b5c656`. Продуктовый код: `f01e9f88b48d5dd094ea28b9150da84ddb5da3e3`, дерево `896b9dbb3e7df35038a792696eadd3b5920ae27e`. L1: 1937 тестов и 25 subtests пройдены, два Windows symlink сценария пропущены, одно историческое исключение сохранено. Независимые L2 code/recovery и L3: 118 и 146 тестов пройдены; L2 verifier/ASR: 1154 проверки данных и привязок пройдены. Все три независимых заключения — ACCEPT. B01–B04 закрыты; точные команды и SHA отчётов находятся в EVIDENCE.json.

Выбран **REPLACE: Systran/faster-whisper-small**, revision `536b0662742c02347bc0e980a01041f333bce120`, CPU/int8/ru, beam 8, patience 1.2, VAD и прежние prompt/hotwords. По принятому владельцем протоколу 3 WER/CER на всех 32 записях — 5,71%/1,11%, на holdout из 16 записей — 5,09%/1,00%. Исходный смысл совпал в 24 из 32 случаев против 15 у CURRENT. Смысловые правки dev/holdout: 3/5 против 7/10. Каждая транскрипция требует подтверждения пользователя; явные исправления не засчитываются как точность ASR.

Полная B02 на source `4ed2cd2` дала пять готовых ответов, 25/25 по рубрике и два typed UNKNOWN; проверены отмена, перезапуск и повторная доставка. После изменения только TTL-передачи на source `f01e9f8` дополнительно получены два настоящих voice→ready ответа, 10/10 по рубрике и успешный replay без дублей. Основной transform подтверждён без смысловой правки. Compiler/Core/model/config/scorer/gold не менялись; каждое доказательство сохраняет свою исходную привязку. Неуспешная промежуточная TTL-матрица и NULL-попытки сохранены.

Кандидат `82e76b9` был отклонён L2/L3: кодирование PreparedTask могло пересечь срок хранения и создать позднюю задачу. Исправление атомарно связывает первую запись draft с ещё действующими voice, tenant, task, binding и lease после кодирования и ожидания блокировки. Независимые пробы нового кандидата подтвердили отсутствие позднего draft/task и сохранение своевременной передачи и идемпотентного восстановления. Прежние FAIL/REJECT и отдельные бюджеты сохранены.

Приёмка охватывает локальный durable/semantic path при включённом semantic flag и публикацию собственного кода и документов. Флаг остаётся выключенным по умолчанию; live и deployment не менялись. ASR проверен на 32 синтетических записях одной TTS voice; точность произвольной человеческой речи не заявляется. Native runtime и веса не распространяются; ограничения лицензий, CVE и дальнейшего развёртывания сохранены в ASR-PROVENANCE.md. Время обработки и ожидание в очереди показаны раздельно; aggregate raw RTF остаётся диагностикой по протоколу 3.

C2 опубликован через [PR #13](https://github.com/streetenergy63reshik-del/nobus-space/pull/13): merge `d888e6bb78b275c7669971710c2a82309d98a621`, tree `b6815bd848f401d376b0de006da464fe90da17b5`. GitHub и полученное дерево сверены с manifest. **C3 READY TO START / NOT STARTED**; весь MVP1 ещё требует C3–C6.
<!-- C2_CURRENT_END -->

## Откуда продолжать C3

Принятая база C1: 43e753c571e1ad8db5af5f453b5db0c0b417cac8, tree a7c6328a42412a0bd269004aefa9c9d402c75564. C1 повторно не принимался. C3 готов к началу и запускается только отдельной задачей владельца. Продуктовая база — опубликованный merge C2 ниже. После чисто документального слияния использовать окончательную protected main из GitHub; её дерево отличается от этой базы только фиксацией публикации. Точный commit самого HANDOFF определяется через Git: документ не содержит собственный будущий SHA.

## Граница следующего Gate

C3 владеет C0-F05–F08: общей retry/recovery матрицей Core/backend/worker, authoritative status, restart/reclaim/dead-letter/outbox reconciliation и multipart idempotency. Различать неисполненную задачу и неизвестный исход; не повторять внешний effect вслепую. Закрытые C2-B01–B04 не переносятся в C3 как незавершённые работы.

Сохранить server-owned authority, общий C1 compiler/Core, подтверждение каждого C2 voice, pinned ASR, durable intake до ASR, PreparedTask до admission, одно место очереди для передачи voice→draft, CAS/update watermark, TTL 1h, Windows Job cleanup и ограничения ASR-PROVENANCE.md. При отключении semantic flag сохранённый C2 voice останавливается fail-closed. Live/activation и распространение native runtime требуют соответствующего будущего этапа; C2 их не принимает.

## Доказательства для следующего разработчика

- [Приёмка](ACCEPTANCE.md), [машиночитаемые привязки](EVIDENCE.json), [фактические результаты B02](PRODUCT-RESULTS.json).
- [Квалификация ASR](CONFIRMED-QUALIFICATION.json), [протокол](../../../tests/gate_c2/qualification/PROTOCOL.json), [хранение и очистка](RETENTION.md), [происхождение и лицензии](ASR-PROVENANCE.md).
- [Текущий статус](../../handoffs/CURRENT-STATUS.md) и [owning Gate проблем](../../handoffs/MVP-1-ISSUES.md).

Старые 7 hard ASR FAIL, первые неподходящие C2 freeze, 82e76 TTL REJECT и все неуспешные provider подматрицы сохранены в том же пакете. Принятый критерий не делает их PASS задним числом. Суммарный small ledger 1173,568207 / 1200 s; Giga 194,916977 / 1800 s. Новые модели, настройки и прогоны в этом Gate не нужны.

## Публикация и база C3

Продукт C2 опубликован обычным merge [PR #13](https://github.com/streetenergy63reshik-del/nobus-space/pull/13):

```text
merge d888e6bb78b275c7669971710c2a82309d98a621
tree  b6815bd848f401d376b0de006da464fe90da17b5
head  a9ed3c3380d59d3b306036c6de81c814e4922b62
```

GitHub readback подтвердил merged=true и опубликованный HANDOFF; fetch подтвердил exact main/tree и совпадение с publication manifest. GitHub checks/workflows отсутствовали: это не объявляется CI PASS. Основание приёмки — собственные точные L1/L2/L3 и независимая проверка документальной синхронизации. Protection/force bypass не применялись.

Этот документ фиксирует уже состоявшуюся публикацию. Его отдельный PR меняет только статусы, ссылки и привязки; код, тесты, model/config и критерии остаются принятыми. Окончательный SHA/tree protected main проверяется после такого merge и указывается в итоговом сообщении задачи C2. В следующей задаче прочитать данный HANDOFF по этой точной ревизии и сверить Git.

**C2 ACCEPTED / PUBLISHED / NOT DEPLOYED. C3 READY TO START / NOT STARTED.** Никаких открытых C2-B01–B04 не остаётся. C3–C6 и готовность всего MVP1 не приняты этим Gate. Live, tag/release/deploy, runtime/weights distribution и редакционные документы 15/16 не затронуты.
