# Независимый L3 recheck a7e570b

**CODE REJECT** для `a7e570bb084ea0324f05b1ec80328c72372a6858`, tree `2189ba333ad686be8e5ad42f6ee4dc553eeadf19`. Предварительный CODE ACCEPT, сообщённый root после целевого запуска, отозван после дополнительного физического close probe. Gate ACCEPT не выдавался.

Независимый чистый detached checkout: **87 PASS**, 1 исключённый недостоверный Clock.advance probe, 33.95s (`a7e-own.log/xml`). Прочитан весь source delta e619→a7: только SDK ownership initialization. L2-04 закрыт: собственные timeout/caller_cancel probes теперь проходят, вторая physical generation не начинается до завершения старого startup, late Popen очищается. Четыре repo варианта настоящего installed SDK с инертным Popen, включая hung initialize, также проходят. Все прежние missing seal, valid-token stale effect, реальные SQLite/Core lock probes проходят.

**Открыт Major ISSUE-C3-L2-05 — physical close теряет незавершённый outcome.** Обнаружение принадлежит L2; L3 независимо повторил его probe и добавил исключение до terminate:

- `sdk_physical_close_probe.py`: 1 FAIL, 0.91s. Настоящий installed SDK убирает `_proc` перед заблокированным stdin.close; asyncio timeout не останавливает фоновый поток. Второй close не видит процесс, возвращает no-op success; adapter.close ошибочно успешен до terminate.
- `sdk_close_exception_probe.py`: 1 FAIL, 0.83s. При исключении из stdin.close после `_proc=None` второй no-op точно так же превращает failed physical close в success.

Owning project boundary: `src/workers/codex_sdk.py:529` `_close_client`, вызываемый повторно из `_close_once` и reaper. Installed SDK `client.py:278` очищает `_proc` раньше stdin.close/terminate. Нужен сохранённый pending и failed physical close outcome на generation; второй no-op не доказывает прекращение прежнего процесса. Reviewer источник не меняет. Все process/model/ASR эффекты в этих probes инертны; reviewer real calls 0.

Полезные 87 PASS сохраняются как доказательства именно проверенных границ. Product quality 15/15 и fd5 receipt provenance неизменны; они не доказывают physical close. Explicit transfer может быть принят после новой frozen source и final docs delta.
