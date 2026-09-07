# Независимая L2: CODE ACCEPT

Exact `b1ed94c6ddfefe957a50f4d133537f74482910cc`, tree `9acb41b5bf6d2a91b8964f84f4c459d072d0c127`. Чистый detached checkout; код автора не изменялся.

**L2-05 закрыт.** Физический SDK close сохраняется как одна операция; timeout не отменяет его underlying thread и не разрешает подменить неизвестный исход повторным пустым close. Ошибка/незавершённость сохраняется, новая генерация блокируется. Успешный close допускает отдельную последующую очистку позднего Popen.

Прежняя независимая проба actual SDK physical close теперь PASS с неизменными критериями. L2-04 повторно проверен двумя собственными delayed-Popen/blocked-initialize пробами и четырьмя author startup scenarios. Общий свежий набор: **103 PASS, 0 FAIL, 0 skips**. Ошибочный физический close также проверен; прежние false-success assertions не ослаблены. `git diff --check` чистый.

L2-01/L2-02/R01 и fixture finding остаются закрытыми. От fd5 изменены только lifecycle-методы двух source-файлов; все изменения перечислены через AST comparison в JSON. Semantic/C1/C2, queue/Core recovery, результат, outbox/artifact/effect и model prompt/permissions/turn processing неизменны. Их прежние проверки и три фактических result/replay переносятся только в этих границах; исходные SHA, raw hashes и исторические FAIL сохраняются.

Модель/ASR/внешние действия reviewer: 0. Это CODE ACCEPT; окончательный Gate пока PENDING. Нужны exact финальный docs/evidence freeze, текущий L1 и root zero-turn SDK startup receipt с проверкой совокупного бюджета. Неизвестный исход физической очистки не называется успешной остановкой; синтетический Telegram не доказывает exactly-once доставку.
