# Узкая регрессия TTL handoff выполнена

## Текущий кандидат после исправления TTL — 6 сентября 2026

Product-source `f01e9f88b48d5dd094ea28b9150da84ddb5da3e3`, tree `896b9dbb3e7df35038a792696eadd3b5920ae27e`. C2 FINAL REVIEW PENDING / NOT PUBLISHED / NOT DEPLOYED. Кандидат82e76b9 отклонён: L2 и L3 независимо воспроизвели позднюю постановку задачи, когда кодирование PreparedTask пересекало часовой TTL; реальный restore создавал PENDING task. Его1911 PASS не отменяют этот дефект; REJECT и все выводы сохранены.

Исправление проверяет срок после кодирования/декодирования и связывает первый INSERT draft с живым исходным voice, tenant/task/binding и lease в одной транзакции после ожидания блокировки. Уже созданный точный draft восстанавливается идемпотентно. Целевые проверки:123 PASS. Новая узкая actual B02 дала два готовых ответа и рубрику10/10: transform без смысловой коррекции и explicit correction, с controlled restart/replay. Первичные отсутствующие final_response SDK и предварительный planning gap повторов сохранены; addendum разрешён до второй повторной подачи в прежнем общем9turn/600s окне. Эта сессия завершилась FAIL при8/9turn: transform ready получен, correction снова NULL. Отдельная заранее ограниченная завершающая correction-подача3turn/180s без retry прошла; исходная матрицаFAIL сохранена. Между ними изменены только selector диагностического trial и безопасные status/itemcounts в receipts, product-sourcef01e9f8 неизменен. Полная B02 с5ready/2UNKNOWN/cancel остаётся доказательством source4ed2; переносом PASS на другой tree не объявляется.

Compiler/Core, ASR/model/config, эталоны, scorer и критерии не менялись. Полная32-case квалификация и отдельный dev16 reproduction сохраняют свои точные bindings; новый цельный freeze получает собственные L1/L2/L3. Измерение concurrent small: service6,180850s и end-to-end9,682063s, включая очередь3,501213s; эти величины не смешиваются. Предел обслуживания данного файла9,480567s выполнен; ожидание в очереди показано отдельно по исходному PLAN.

Приёмка относится к новому durable/semantic path при semantic flag ON. Default-off и live не объявляются включённым C2; сохранённый C2 voice при отключении флага останавливается fail-closed. Решение REPLACE ограничено локальным использованием закреплённой small и публикацией собственного кода/документов. Условия распространения native runtime и rollout сохраняются в ASR-PROVENANCE.md. C3 не начат; весь MVP1 не READY до C3–C6.

---

# C2 B02 — выполненная проверка product-source4ed2cd2

Новая B02 на product-source 4ed2cd2418b58ba499ff5dfdf69605244ceb4916 / tree 8eee2901119bb3699477479ef810efae3608773f прошла:
пять реальных готовых ответов, независимая рубрика25/25 и обе фактические
MATERIAL_ITEM_STATE_V1/UNKNOWN → CLARIFY/PREDICATE_UNKNOWN. Основная пара text/voice
прошла без смысловой коррекции. Отдельный correction-path соответствует явной правке
пользователя. До подтверждения compiler/task/effect0. Cancel, сохранённый preview,
PreparedTask и controlled restart/replay проверены; второй задачи или результата нет.

Сессия использовала17/24 model turns за418.837421s в одном окне1200s.
Были заморожены code/model/profile/fixtures. Старые FAIL, включая предыдущую
сессию21/24 с четырьмя неудачными correction-подачами, сохранены. Явная коррекция
не засчитана как точность исходного ASR. Прежние окна закрыты, остатки не перенесены.

ASR qualification PASS по протоколу3. В C2 кандидат выбран pinned small beam8 с
прежними CPU/int8/ru/VAD/patience1.2/prompt/hotwords, без новых зависимостей.
B03/B04 реализованы; собственные полные L1/L2/L3 по цельному freeze ещё впереди.
Условия binary distribution и live rollout отдельно ограничены ASR-PROVENANCE.md.

Владелец6 сентября разрешил полное завершение C2, необходимые ограниченные проверки
и обычные push/PR/merge после PASS. Повторный вопрос о том же разрешении не нужен.
Перед публикацией — exact manifest и итоговые проверки, после — GitHub readback.
C3 ещё не начат. Весь MVP1 не READY до C3–C6.

MATERIAL-TRIAL.json:24turn/1200s,17planned+7reserve; ledger material-trial-20260906.
Тот же transport-only fake, synthetic fixtures, gpt-5.6-sol/high/fast и штатный ChatGPT
endpoint. Неизменны45s/schema/Core/ref/multiset guards; raw audio не передавалось.

---

## История прежних планов

Ниже pending означает состояние на дату подготовки; действующее разрешение описано выше.

# C2 B02 после уточнения инструкции compiler

**6 сентября2026: PREPARED / PENDING AUTHORIZATION. C2 остаётся BLOCKED.**
Локальный product commit `efa0ac7e1e313bf53255b47260fa991271986399`, tree `26ca0ab70f31701a6836a05efab63cf3e9329151`.
Результаты предыдущих сессий и все FAIL сохранены в [PRODUCT-RESULTS.json](PRODUCT-RESULTS.json).
Квалификация ASR завершена; общий compiler prompt изменён после завершения UNKNOWN trial.
Проверки Core/schema/полномочий и admission-wide deadline45s не менялись.

UNKNOWN trial8turn/600s был разрешён и выполнен на предыдущих bytes: text PASS,
voice primary и fresh retry FAIL,6 calls. Третья voice попытка тем grant не разрешалась.
Уточнение инструкции устраняет двусмысленное «сохрани один predicate», но улучшение
поведения ещё не доказано. Следующая проверка должна относиться к новым bytes.

## Точный объём нового запроса

Одна непрерывная сессия **1200 секунд от первого provider call**, максимум **24 model
turns вместе со всеми повторами**:17 плановых и7 резервных. Существующая подписка
ChatGPT/OpenAI Codex, `gpt-5.6-sol/high/fast`, стандартный endpoint
`https://chatgpt.com/backend-api/codex`. Имеющаяся квота расходуется; новых покупок и
API billing нет. Жёсткого token ceiling у production adapter нет; region/retention
аккаунта неизвестны. Native login и SDK account/provider/endpoint проверяются до
inference; API-key или нестандартный endpoint останавливают запуск.

Только прежние синтетические fixtures, уточнённый общий compiler prompt и прежний
downstream prompt. Audio upload, tools и реальные effects отсутствуют. Матрица
проверяет C2; принятую C1-кампанию заново не проводить.

| Сценарий | Compiler | Downstream | Всего |
|---|---:|---:|---:|
| transform text |2|1|3|
| transform actual voice без смысловой коррекции |2|1|3|
| явная voice correction с quoted/nested/negation материалом |2|1|3|
| supported UNKNOWN text |2|0|2|
| supported UNKNOWN voice с явной singular correction |2|0|2|
| negation text |1|1|2|
| negation voice |1|1|2|
| cancel, controlled restart, original/confirmation replay |0|0|0|
| Резерв в общем пределе | | |7|

## Подготовка и исполнение

1. Сверить source/model/config/fixture/audio hashes с
   `.runtime/c2/closure/compiler-clarification-20260906/freeze.json`. Новый manifest
   `product-plan/CLOSURE-TRIAL.json` содержит exact source binding и PENDING.
   Только после отдельного grant сохранить его точный текст, статус AUTHORIZED и
   создать ledger `product-plan/closure-trial-20260906/budget.sqlite3`. Старые три
   ledger не редактировать. Проверка отвергает pending, чужой scenario и изменение
   source binding до создания нового ledger/provider.
2. До первого provider turn выполнить штатный login/account/endpoint preflight;
   подготовить пять свежих voice preview обычным intake. Использовать только уже
   закреплённые `transform.wav` (также correction), `conditional.wav`, `negation.wav`,
   `direct.wav` (cancel). Native admit учитывается в прежнем small ledger1200s,
   под Windows Job4CPU/4GiB. TTL1h проверять по immutable created_at; состояния не
   оживлять вручную. Завершить cancel→нет→replay без compiler/task/effect.
3. Новый run: `.runtime/c2/closure/product-smoke/compiler-clarified-01`. Все phases
   запускаются отдельными процессами через `tests/gate_c2/product_smoke_runner.py`
   с `--closure-authorized-trial`. Text: admit→drain→replay. Voice:
   admit→confirm→drain→replay; `--correction` только для correction и UNKNOWN voice.
   Транспорт — единственная заглушка; compiler, Core, PreparedTask, SQLite,
   downstream, verification и delivery настоящие. Compiler input/output сохраняются
   локально отдельно, чтобы независимо проверить переданный хвост и model output.
4. Сначала все первичные сценарии в порядке таблицы. Затем максимум один свежий
   повтор каждого провалившегося сценария, только если он целиком помещается в
   оставшиеся24turn/1200s. При уже созданной задаче/ответе не создавать дубликат;
   delivery/replay failure сначала сохранить и разобрать. Истёкшее окно не продлевать.
   Не менять source, prompts, model, fixtures, deadline или состояния внутри trial.
5. Требуются пять фактических ANSWERED+APPROVED результатов, по одному outbox ACK,
   artifact и набору ready chunks; независимая рубрика5 критериев. UNKNOWN в обеих
   модальностях: MATERIAL_ITEM_STATE_V1/UNKNOWN, CLARIFY/PREDICATE_UNKNOWN,
   capability null/task0/effect0. Generic refusal или AMBIGUITY не подходят.
   До voice confirmation compiler/task/draft/effect0; replay не добавляет calls,
   ASR, задачу или результат. Restart контролируемый, не hard crash.
6. После фактического B02 PASS — собственные L1/L2/L3 цельного frozen C2. ASR bytes
   и протокол не менялись: закрытую32-case/3-pass кампанию не повторять. После
   итогового PASS подготовить точный publication manifest и запросить отдельное
   разрешение push/PR/merge. Live/config, tag/release/deploy и C3 не разрешены.

Команда одной фазы из корня C2 (Python — существующая canonical .venv):

```text
python tests/gate_c2/product_smoke_runner.py --run .runtime/c2/closure/product-smoke/compiler-clarified-01 --scenario transform_voice --phase confirm --model .runtime/asr-qualification/faster-whisper-small/models --audio .runtime/c2/synthetic-audio/transform.wav --closure-authorized-trial
```

Этот документ — конкретный план, а не внешний grant. До согласия provider calls0.
Успех при неизменном45s deadline не гарантирован; новые FAIL должны сохраняться.

---

## Исторические планы до уточнения compiler

Ниже сохранены исходные планы. Их PENDING-статусы уже исторические: обе сессии
получили разрешения и завершились; текущее недостающее разрешение описано выше.

# C2 B02: остаётся supported UNKNOWN

**6 сентября 2026: подготовлено, требуется отдельное разрешение.**
Основная text/voice-пара, отдельная voice correction и negation в обеих модальностях
дали пять реальных готовых ответов; независимая рубрика 25/25. Старые FAIL сохранены.
Подробности и hashes — [PRODUCT-RESULTS.json](PRODUCT-RESULTS.json).

В разрешённой дополнительной сессии выполнено 19 из 20 calls:14 compiler и 5 downstream.
Первая transform text попытка завершилась без второго ответа compiler; обычная
новая подача того же текста дала готовый результат. UNKNOWN text вернул внутренне
противоречивую proposal и был отвергнут. UNKNOWN voice не получил второй ответ в
штатные 45 s. В обоих случаях task 0/effect 0, но фактический Core UNKNOWN не доказан.
Один оставшийся turn не вмещал целый UNKNOWN-сценарий из двух calls; он не использован.
Исходные ledger 24/1200 s и дополнительный 20/1200 s сохраняются без обнуления.

## Точный оставшийся объём

Запрашивается одна отдельная сессия: максимум **8 model turns вместе с повторами**,
одна непрерывная **сессия 600 секунд от первого provider call**. План: UNKNOWN text2,
UNKNOWN voice2, резерв 4 на не более одной свежей повторной подачи каждой модальности.
Все резервные calls входят в 8. Никакого изменения fixtures, prompts, source, модели
или deadline по ответам compiler; failure остаётся failure.

Используется существующая подписка ChatGPT/OpenAI Codex, production
`gpt-5.6-sol/high/fast`, штатный `https://chatgpt.com/backend-api/codex`.
Перед первым turn — native login и SDK account/provider/endpoint guard.
API-key или иной endpoint останавливают проверку до inference. Только неизменный
синтетический conditional fixture и штатные C1 prompts; без audio upload, tools,
реальных действий, API billing и новых покупок. Расходуется имеющаяся квота;
жёсткого token ceiling нет, region/retention аккаунта неизвестны.

## Исправленная проверка и её границы

Код проверки теперь доступен в Git: [product_smoke.py](../../../tests/gate_c2/product_smoke.py),
[resource executor](../../../tests/gate_c2/product_smoke_runner.py),
[неизменные fixtures](../../../tests/gate_c2/PRODUCT-FIXTURES.json).
Исторический smoke опускал внешний polling checkpoint: text negation replay
сохранил task/result, но сделал ещё один compiler call. Это пробел verifier и оценки
бюджета; ошибка production polling этим не доказана. Новый smoke использует настоящие
TelegramPollingBoundary и SQLitePollingCheckpointStore, включая штатный lease 240 s.
Заглушка остаётся только транспортной: get_updates соблюдает сохранённый offset.
Для обеих модальностей replay требует неизменных model/task/artifact counts.

24 целевые проверки прошли: accepted offset переживает restart, старый update
не вызывает handler, отказ не продвигает offset, новый confirmation проходит;
pending authorization и чужой scenario блокируются до нового ledger/provider.
Независимый focused review закрыл scope и resource-helper binding замечания.
Это подготовка verifier, не итоговые L2/L3 C2. Product src/scripts, schema и
compiler deadline 45 s не менялись; product source остаётся 28222923d2c2560504d1237c8e8da6df442c6150.

## Порядок после точного разрешения

1. Сверить Git и freeze `.runtime/c2/closure/polling-verifier-20260906/freeze.json`,
   hashes source/model/config/fixtures/audio/verifier/resource helper. Выполнить
   штатный login/provider preflight без inference до начала 600 s.
2. В `.runtime/c2/closure/product-plan/UNKNOWN-TRIAL.json` сохранить точный grant;
   сейчас он PENDING_AUTHORIZATION. Новый ledger `unknown-trial-20260906/budget.sqlite3`
   ещё не создан. Старые ledger не редактировать.
3. Проверить TTL свежего waiting preview в `product-smoke/unknown-prepared-05`.
   При истечении создать обычный intake в прежнем small ledger до первого provider
   turn; не оживлять SQLite. Аудио — прежний conditional.wav; owner явно исправляет
   plural raw transcript на неизменный singular conditional fixture. ASR credit 0.
4. Text: admit→drain→replay. Voice: confirm с --correction→drain→replay. Требуются
   фактические MATERIAL_ITEM_STATE_V1/UNKNOWN, CLARIFY/PREDICATE_UNKNOWN,
   capability null/task 0/effect 0; generic safe refusal не подходит. До confirm
   compiler/task/draft/effect 0. Replay не добавляет calls или результат.
5. При failure сохранить попытку; один неизменный fresh retry для этой модальности
   допускается только внутри общего 8 turn/600 s. Затем завершить все процессы и
   независимо оценить фактические решения. Только после B02 — цельный C2 и свои L1–L3.

Пример разрешённой только после нового grant provider-фазы (из корня C2;
Python — существующая canonical .venv):

```text
python tests/gate_c2/product_smoke_runner.py --run .runtime/c2/closure/product-smoke/unknown-prepared-05 --scenario conditional_supported_unknown_voice --phase confirm --model .runtime/asr-qualification/faster-whisper-small/models --audio .runtime/c2/synthetic-audio/conditional.wav --correction --unknown-authorized-trial
```

Этот документ не разрешает provider calls, публикацию, live или C3. Успех при
неизменном compiler deadline не гарантирован; при новом FAIL результат сохраняется.

---

## Исторический план дополнительной сессии5 сентября — выполнен6 сентября

Ниже сохранён исходный текст. Его PENDING и инструкции ожидания больше не являются
текущим статусом; текущие результаты и новый узкий запрос описаны выше.

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
