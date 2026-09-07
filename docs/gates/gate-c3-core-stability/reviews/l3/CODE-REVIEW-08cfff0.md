# Независимая adversarial проверка C3

**CODE REJECT. Итоговая приёмка Gate не выполнена.** Автор кода и исправлений — root/назначенные writers; L3 проверял отдельный чистый detached checkout и изменял только собственные disposable probes и receipts.

Проверены commit `08cfff031803211334f6da9da377b18226c5a393`, tree `fa265fb5a0c792ba342db025e1ecf584614cf36f`. Base C2 `5fdc28ce66dbb072acd6676baf72fe58ae10b4b3`, tree `c8e756fb00874c5db2f6105c6d65154d0ed243e7`; base ancestor подтверждён. Git blob C2 HANDOFF — `6d0fee2bdb82af3ffdb92faac22dc0218572e0e6`. `git diff --check` проходит. Рабочее дерево L3 чистое до/после проверок; WIP root и canonical checkout не редактировались.

Профиль software-development, риск HIGH, стадия frozen product checkpoint. Прочитаны launch prompt, AGENTS, README/CURRENT, ADR0024, связанные ADR0018/0023 и runtime callers. Nobus Memory прочитана через штатный bridge READY как устаревший указатель; authoritative revision взята из Git. Reacceptance C0–C2, provider/ASR calls, live/Telegram/external effects не выполнялись.

## Подтверждённые находки

| ID | Класс / важность | Точная граница | Доказательство |
|---|---|---|---|
| C3-L3-01 | PRODUCT_OR_SECURITY_RISK / Major | `src/storage/sqlite_store.py:1648`, повтор условия `:1832` | У настоящего C3 sealed ANSWERED удаляется seal row; user_message подменяется и обычные outbox fingerprint/ID/digest пересчитываются. Task/result digest не меняется. `read_outbox_message` принимает чужие bytes: optional seal отключает проверку связи результата. |
| C3-L3-02 | PRODUCT_OR_SECURITY_RISK / Major | `src/application/product_effects.py:609`, `:646`, `:727`; vault transition `:221` | У effect job истекает lease и происходит reclaim. Coroutine сохраняет старый execution_lease context. ProductEffectService.resolve(NETWORK) всё равно вызывает synthetic runner один раз и фиксирует completed. Queue guard не охватывает effect begin/completion. |
| C3-L3-03 | IMPLEMENTATION_DEFECT / Major | `src/workers/codex_sdk.py:148`, `:161`; `src/application/durable_product.py:190`; caller `scripts/run_telegram_control.py:248` | Fresh SDK имеет `_client=None`; control.start запускает queue loops, но не готовит client. assert_healthy падает до первой model task. Production serve вызывает health_check до polling, поэтому пустой runtime не доходит до ленивого создания SDK generation. |
| C3-L3-04 | IMPLEMENTATION_DEFECT / Medium | `src/storage/sqlite_store.py:2243`, `:2251` | Caller now захвачен до `_transaction`; имитированное ожидание write lock переносит authoritative clock за expiry, но part receipt принимается с прежним now. Это нарушение expiry boundary без ABA reclaim; CAS против уже сменившегося lease проходит существующие тесты. Нужна классификация/решение owner с проверкой server time после lock, а не автоматический перенос старого PASS. |
| C3-L3-V01 | VERIFIER_DEFECT / gate validation blocker | `tests/test_queue12_crash_regressions.py:426`; voice/retention fixtures | 14 historical tests создают control через object.__new__ и не задают новый `_cleanup_pending`. Production constructor поле задаёт. Нужно исправить fixture initialization, сохранив содержательные assertions. |

Собственные probes: `adversarial_probes.py`; frozen final run `probes03.log/xml`, 3 PASS / 4 FAIL. Хеш именно исполнявшейся версии — `probes03-source-hash.json`. Подмена foreign tenant/manifest и missing seal до terminal были остановлены корректно. Ошибка первоначального foreign-manifest probe была VERIFIER_DEFECT: защита срабатывала раньше ожидаемого блока; probes01 сохранён, собственный тест исправлен до probes02/03.

Root отдельно обнаружил R01 — потеря Core PARSING recovery при direct-text smoke. Эта независимая проверка не приписывает себе его обнаружение; R01 также требует закрытия на новой ревизии.

## Допустимое направление исправлений

Для C3-L3-01 предложенная root проверка нормализованных `{answer: user_message}` bytes против authoritative snapshot.output_digest сохраняет legacy без seal только при доказуемом совпадении. DPAPI seal при наличии остаётся дополнительной проверкой. Исторические synthetic fixtures с произвольным output_digest требуют честной привязки к answer; не ослаблять проверку ради fixtures.

Для C3-L3-02 queue authority должна охватывать синхронный begin/completion под write lock; SQLite transaction нельзя держать через await внешнего adapter. После remote acceptance при потере lease нельзя писать success; executing должен вести к безопасному UNKNOWN/reconciliation без повторного effect. Самого guard у Task snapshot недостаточно.

Для C3-L3-03 проверка должна включать fresh empty control → readiness → первый intake, без предварительного model turn. Readiness не должна ложным образом заявлять online при неготовой generation.

## Выполненные regression runs

`targeted.xml`: 176 PASS / 1 FAIL, 23.69s. Проверялись C3 delivery/concurrency/effect/multipart/queue/result/shutdown/retry и historical queue/crash/effect/outbox. Fail относится к C3-L3-V01.

`preservation.xml`: 140 PASS / 13 FAIL, 45.74s. Проверялись SDK, Mini App artifact/result, voice retention/durable voice, product effects, voice effect restart. Все 13 FAIL относятся к тому же C3-L3-V01; новых voice/TTL implementation defects этот запуск не установил.

Все команды используют canonical pinned `.venv/Scripts/python.exe`, `DEBUG=false`, чистый L3 checkout и отдельный `--basetemp` под review evidence. XML/log artifacts перечислены с SHA256 в receipt. Полный root L1 или независимый L2 здесь не повторяются и не заявляются как собственный результат.

После rework требуется новая exact product SHA/tree, повтор провалившихся и зависимых границ, explicit closure этих findings. Финальный Gate verdict возможен только после отдельного freeze документации и проверки docs-only delta / явного переноса неизменных evidence. Никакого final Gate ACCEPT на этой ревизии нет.
