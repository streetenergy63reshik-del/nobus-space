# C2 B02: дополнительная сессия после исправлений

Статус5 сентября2026: **PREPARED / PENDING AUTHORIZATION**. Это план, не разрешение.
Исходное окно24turn/1200s завершилось после8compiler turns; downstream0, готовых
ответов0. Старый ledger `product-plan/budget.sqlite3` и все FAIL сохранены. Остаток
16turn не переносится в новое окно. Новых provider calls после истечения не было.

Product source28222923d2c2560504d1237c8e8da6df442c6150/tree
b24ae81b91786aca942c89a8d54f50279de3cef8. Production model/compiler/downstream:
gpt-5.6-sol/high/fast, существующая подписка ChatGPT, штатный OpenAI endpoint
https://chatgpt.com/backend-api/codex. Перед inference — native login status,
SDK account/provider/endpoint guard. API-key или нестандартный endpoint блокируют вызов.
Только frozen synthetic text и существующие C1/downstream prompts; audio upload,
tools, реальные effects, API billing и новые покупки0. Расходуется текущая квота;
жёсткого token ceiling у production adapter нет, region/retention аккаунта неизвестны.

## Конечная матрица и предел

Запрашиваемый дополнительный объём — максимум20 model turns, включая все повторы,
и одна непрерывная сессия1200s от первого provider turn. План17turn, резерв3.
Не расширять окно из-за ожидания ASR, чтения отчётов или неудачи отдельного сценария.

| Сценарий | Compiler | Downstream | Итог |
|---|---:|---:|---:|
| Основной transform text | 2 | 1 | 3 |
| Тот же transform actual voice, без смысловой коррекции | 2 | 1 | 3 |
| Отдельный voice correction с quoted/nested/negation material | 2 | 1 | 3 |
| Supported UNKNOWN text | 2 | 0 | 2 |
| Supported UNKNOWN voice с явной корректировкой singular fixture | 2 | 0 | 2 |
| Negation text | 1 | 1 | 2 |
| Negation voice | 1 | 1 | 2 |
| Cancel/restart/replay | 0 | 0 | 0 |

Два compiler turns основной пары нужны после правильного выделения отдельного
DIRECT_OWNER_COMMAND перед инертным материалом. Первоначальная оценка15 относилась
к дефектной границе материала и теперь историческая. Сложный corrected transform
добавляет явно написанный владельцем синтетический материал; эти слова не выдаются
за исходное аудио и не улучшают ASR accuracy.

## Уже подготовлено

Пять real ASR preview нового product source сохранены в `closure/product-smoke/confirmed-02/`;
во всех before/after provider count8, новых calls0, tasks/drafts/effects0. Cancel→нет→
original/confirmation/new-да replay завершён, model count прежний, повторов ASR0.
Остальные preview имеют штатный TTL1h: перед сессией проверить пригодность, не оживлять
истёкший SQLite payload вручную. При необходимости обновить через обычный intake в
оставшемся прежнем small budget. Сейчас small775.020787199901/1200s, осталось424.979212800099s.
GigaAM194.916977/1800s не менялся. Новые downloads/deps/cloud ASR не нужны.

Pinned small factory проверяет5asset SHA; decoding совпадает с квалифицированным.
В source binding входят все tracked src/scripts Python bytes, product-source revision,
harness/executor/fixtures/protocol и model hashes. Doc-only HEAD не заменяет product revision.
Все phases — отдельные процессы, transport-only fake; production admission/Core,
PreparedTask, SQLite, worker, verification и delivery остаются настоящими.
ObservedVoice запрещает native ASR до вызова, если phase не admit; run_phase целиком
начисляет admit в старый small ledger под Job4CPU/4GiB. Replay не обходит бюджет.

Дополнительный manifest `.runtime/c2/closure/product-plan/ADDITIONAL-TRIAL.json`
имеет PENDING_AUTHORIZATION. Новый ledger `additional-trial-20260905/budget.sqlite3`
не создан. Только после точного согласия владельца статус станет AUTHORIZED и
появится отдельный ledger; исходный счётчик/FAIL не редактируются и не обнуляются.

## Порядок исполнения после разрешения

1. Проверить source/model/config/fixture hashes, preflight17turn и пригодность preview.
   Freeze сохраняет текущий Git HEAD/tree отдельно от product-source2822292.
2. Последовательно пройти основную text/voice пару, corrected voice, UNKNOWN и negation.
   Text: admit→drain→replay. Voice: confirm→drain→replay из persisted preview.
   Correction-path и UNKNOWNvoice используют явный --correction.
3. При готовом ответе обязательны actual ANSWERED+APPROVED, ровно1ANSWERED outbox ACK,
  1artifact и1набор ready chunks. После replay тот же task identity, без второго
   ответа, ASR или model turn. UNKNOWN: фактические MATERIAL_ITEM_STATE_V1/UNKNOWN,
   CLARIFY/PREDICATE_UNKNOWN, task0/effect0; plural UNSUPPORTED не заменяет эту проверку.
4. Независимо оценить5 готовых artifacts по цели/ролям/constraints и пригодности
   для копирования; compiler не является oracle. После принятого текста нужны
  100%semantic parity и0неверных решений. Preview и PreparedTask restart — controlled,
   не hard crash. Никаких ручных lease/state edits или подложенных proposals.
5. При локальном дефекте остановить зависимую часть, сохранить FAIL и завершить
   независимые допустимые cases в том же бюджете. Не тратить окно на исправления
   исходников с последующим смешиванием разных bytes в одном trial.

Команды из корня C2 (Python — прежний canonical .venv):

```text
python .runtime/c2/closure/product-plan/preflight.py
python .runtime/c2/closure/product-plan/run_phase.py --run .runtime/c2/closure/product-smoke/confirmed-02 --scenario transform_voice --phase confirm --model .runtime/asr-qualification/faster-whisper-small/models --audio .runtime/c2/synthetic-audio/transform.wav --additional-authorized-trial
```

Вторую команду до отдельного согласия не выполнять: pending manifest отвергается.
Для следующих phases меняется только scenario/phase/audio/явная correction согласно
таблице; preexisting fixture, prompt или state не подстраивается под provider result.
Итоговый PASS C2 требует B02 и затем собственных L1/L2/L3 окончательного кандидата.
Публикация, merge, live и C3 этим планом не разрешаются.
