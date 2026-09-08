# Nobus Space — текущий статус

**Обновление 8 сентября: C4 REWORK / NOT ACCEPTED / NOT PUBLISHED.** Повторный настоящий smoke подтвердил текст, TXT и восстановление Mini App. Владелец запросил две кнопки под расшифровкой и очистку промежуточного сообщения; новый кандидат проходит собственные проверки. [Точные факты и границы](../gates/gate-c4-frontend-journey/SMOKE-REWORK.md). Ниже сохранены результаты предыдущего локального checkpoint.

**7 сентября 2026: C4 LOCAL VERIFIED / LIVE E2E PENDING / NOT ACCEPTED / NOT PUBLISHED.**
C0–C3 приняты и опубликованы. C5–C6 HOLD; MVP1 NOT READY; MVP2 HOLD.
Точный комплект: [приёмка C4](../gates/gate-c4-frontend-journey/ACCEPTANCE.md),
[доказательства](../gates/gate-c4-frontend-journey/EVIDENCE.json),
[единая передача](../gates/gate-c4-frontend-journey/HANDOFF.md).

## Ревизии и сохранность

| Назначение | SHA | Tree |
|---|---|---|
| Принятый опубликованный C3; protected main, проверен по GitHub 7 сентября | b9283b3419928042c80278b5088b526edebab6e7 | 77062335b1dbccb3694721d357e484c856ac89c7 |
| Проверенный код C4 | a869a691293e45a1a3e65303be627d684acfa16e | 9a7cab97fb9947ebdfedeb5baffa57f9627a4c98 |
| Первый отклонённый C4 | ad02795c5457deb3909517efd1992cacb5ac9a73 | 229d7a4be82da7391ee339825fffb3538d34481d |

C4 branch: `codex/mvp1-closure-c4-frontend-journey`.
Worktree: `nobus-orchestrator-dev/.runtime/worktrees/mvp1-closure-c4-frontend-journey`.
Изменения документации после code freeze не меняют исходные привязки кодовых
проверок; их отдельная проверка и manifest находятся в пакете C4.
Dirty canonical checkout, C3/C2 и старый live сохранены; они не были базой C4.
Пакеты C0–C3 и sealed historical Gate не переаттестовывались и не переписывались.

## Реализовано и проверено локально

C1–C3 уже дают общий semantic compiler, Core policy, подтверждаемый voice input,
durable admission/recovery, sealed result и доставку по связанным частям.
C4 завершает их пользовательскую проекцию в существующем Telegram Bot и Mini App:

- общий каталог состояний, безопасных причин и следующих действий;
- Core-owned recovery credential с ротацией, исходным сроком Telegram-подписи
  и отзывом прежнего bearer; клиент не хранит bearer/initData в localStorage;
- durable request journal, чтение результата неизвестного POST и точная отмена
  только ещё не принятого запроса, запрещающая его поздний приём;
- восстановление уточнения, состояния и результата после reload/reconnect;
- получение результата, копирование и одного связанного UTF-8 файла;
- light/dark, mobile layout, keyboard/focus и безопасное отображение текста.

Собственный полный L1 на a869a69: **2132 PASS + 25 subtests PASS**;
2 Windows symlink SKIP, 1 historical deselect. Frontend Node: **17 PASS**.
Локальные actual-provider/ASR сценарии: direct text, Telegram text, transform text,
direct voice, transform voice, clarification, unavailable.
Шесть задач завершены с совпадающими artifact bytes/digest и 12 part receipts;
unavailable не создаёт задачу/эффект. Отдельный restart/replay всех шести не
создал дополнительного результата и не расходовал model/ASR.
Это loopback HTTP и synthetic Telegram transport, а не настоящий пользовательский smoke.

Независимые L2/L3 приняли проверенную локальную кодовую область и actual local
run/replay evidence; общий Gate ими не принят до реальных поверхностей.
Исходные REJECT и неудачные прогоны сохранены с исходными ревизиями.

## Что необходимо для завершения C4

Обязательны настоящий owner Telegram + Mini App на точном кандидате,
фактическое получение/копирование результата и файла, recovery/re-auth,
снимки 320/390/768 в обеих темах и проверка клавиатурой.
Штатные Browser/Windows инструменты возвращают trusted RPC startup error;
локальные тесты не доказывают поведение Telegram WebView.

Владелец разрешил необходимые ограниченные проверки и публикацию после полного
PASS. Дополнительное разрешение на каждый шаг не требуется. Точные временные
окна, ошибки, cleanup/readback и общий бюджет записываются в C4 EVIDENCE/HANDOFF.
Временный контур не означает постоянную активацию.

C4 push/PR/merge пока не выполнены. Protected main остаётся принятой базой C3;
branch API подтвердил protection, чтение подробной policy через connector
возвращает403. Отсутствующие CI checks не объявляются PASS.
После настоящего полного C4 PASS — ordinary PR/merge с действующими проверками,
readback exact main SHA/tree и передача C5. Tag/release/постоянный deploy запрещены.

## Дальнейшая граница

C5 начинает отдельная задача владельца только от принятого опубликованного C4:
operations, ingress/security, backup/restore, cleanup, rollback и существующая
единая инструкция по фактически проверенному UI.
C6 — frozen release, разрешённая активация, readback и owner acceptance целого MVP1.
Исторические READY и deployment-наблюдения не являются текущей приёмкой.
