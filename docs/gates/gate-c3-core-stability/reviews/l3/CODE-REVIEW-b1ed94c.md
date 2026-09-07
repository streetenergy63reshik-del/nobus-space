# Независимый L3 recheck b1ed94c

**CODE ACCEPT** для `b1ed94c6ddfefe957a50f4d133537f74482910cc`, tree `9acb41b5bf6d2a91b8964f84f4c459d072d0c127`. Финальный Gate verdict требует отдельного docs/evidence freeze; он здесь не выставлен.

Чистый detached L3 worktree, `git diff --check` проходит. Source автора не изменялся; reviewer работал только со своими probes/reports. Canonical dirty checkout не редактировался. Reviewer real model/ASR/process/external calls: 0.

Независимый запуск `b1e-own.log/xml`: **89 PASS**, 1 исключённый недостоверный Clock.advance probe, 34.38s. Проверены собственные start-timeout/caller-cancel ownership probes, копия L2 actual-SDK physical close timeout, собственный physical close exception, четыре repo late-Popen/hung-initialize варианта, startup/shutdown/SDK/retry и прежние missing-seal/stale-valid-token/SQLite-Core-lock probes. Единственный warning относится к прежней deprecation Starlette/httpx.

**L2-05 закрыт.** В `src/workers/codex_sdk.py:531` сохраняется один pending/failed physical close task на generation. `asyncio.wait` не отменяет фоновую операцию; timeout и exception не превращаются в success через последующий no-op. Generation блокируется, retired outcome остаётся false. Успешный завершённый close удаляется из cache, поэтому reaper сохраняет возможность закрыть late Popen следующим проходом. Собственные проверки на a7 давали два FAIL; на b1e оба PASS.

**L2-04 остаётся закрыт.** Запуск в thread сохраняет владельца после отмены/таймаута. Поздний process очищается даже при зависшем initialize, replacement не разрешён до cleanup. Исходная недостоверность async-only startup tests не скрыта: подтверждённый e619 physical-start FAIL и a7 physical-close FAIL сохранены отдельно.

**Прежние L3-01/02/03/04/05 закрыты в проверенном объёме.** Missing seal не отключает authoritative answer digest; stale effect probe использует правильный capability_token; реальные SQLite/Core lock expiry guards проходят. Valid-config cold startup и его lifecycle проходят. Неверная первоначальная классификация startup/Clock probe исправлена отдельным `CORRECTIONS-08cfff0.md`, без переписывания первоначальных FAIL/отчётов. Historical fixtures исправлены без ослабления содержательных assertions.

Весь source delta a7→b1e прочитан; менялся только SDK physical close. Изменение трёх test assertions с двух попыток на одну усиливает требование: failed close сохраняется, blind no-op retry не засчитывается как доказательство. Суммарный source delta fd5→b1e — только `durable_product.py` и `codex_sdk.py`, локальные startup/deadline/ownership/cleanup. Prompts, model profile, permission policy, capabilities и answer semantics не менялись.

**Explicit evidence transfer принят:** product quality fd5 остаётся 15/15 и переносится на b1e для неизменной содержательной части. Сам smoke остаётся привязан к `fd5f9cefb64a192f0de02db314b469915bc4e6f6`, tree `65c3230bceeca7cae7fd3d9e902eae1887f0fb3f`; он не объявляется запуском b1e. `PRODUCT-QUALITY-fd5f9ce.json` hash `b293a25a5b35de8b9c80d125c1da77ba83cfea10709207987957774a4afac026`: 194 receipt checks, 95 собственных raw-source readbacks и явная атрибуция contemporaneous L2 readback для двух изменённых startup файлов. Смешанные окончания строк не подменены заявлением raw-byte равенства.

Ограничения: три synthetic продукта, controlled restart вместо hard crash, synthetic transport вместо exactly-once Telegram. Незавершённая/неудачная physical cleanup остаётся явным failure с сохранённым владельцем; не обещается успешное закрытие произвольно зависшего стороннего кода. Full L1 и zero-turn native SDK readback выполняет root; L3 не приписывает себе эти вызовы.

Прежние verdict e619/a7 отозваны отдельными дополнениями и сохранены как история. Новый CODE ACCEPT основан на b1e; final gate возможен только после exact docs delta review.
