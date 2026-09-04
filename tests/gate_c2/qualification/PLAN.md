# C2-B01: независимый дизайн квалификации до новых hypotheses

Дата: 4 сентября 2026. Основа прочитана и совпала: C2 commit `b090bc48b8934fcc16e10a81cff12b56b30479c1`, tree `10055957c7ba1f5c21577d7e58ea5e459e0c46bf`; final-evidence SHA256 `baf960372d5dd9c189a2de9b0de317c6ad0c45d3adc31bac3012135528bdba6d`. Tracked checkout на входе чист. Старый pilot/scorer/evidence не изменялись. Новые ASR hypotheses не читались. ASR, TTS, compiler, model import, download/install/network не выполнялись.

Это конкретный план и gold, а не готовая квалификация. Root должен превратить его в executable scorer/runner, записать audio/config/toolchain hashes и заморозить новый полный manifest до inference. Устаревшую запись первого manifest «trials не авторизованы» не переносить в новый: continuation сохраняет точное ранее данное разрешение GigaAM и невозобновляемый остаток его бюджета.

## Минимальный корпус и разделение

`CORPUS-GOLD.json`: прежние 16 текстов только **dev**, плюс 16 новых **holdout**. Старые тексты/аудио уже использовались и не могут стать holdout после переименования. Dev labels независимы от compiler; старые aggregate WER19,15%/CER7,16%/critical12 у FW и WER11,49%/CER5,81%/critical10 у GigaAM остаются историей старого метода/ресурсов. Новые значения записывать под новым qualification ID.

16 новых текстов покрывают direct, transform, quoted, nested, negation, cancel, supported conditional, date, quantities/decimal percent, names, English terms, correction, real silence pauses, quiet, deterministic noise, long transform. Это ровно одно новое содержание на speech family; дополнительные большие корпуса сейчас не нужны. Внутри holdout не выбирать удачные варианты и не менять transcript reference по тому, что услышал ASR.

Новая акустика использует только уже установленную Microsoft Irina Desktop: rate 0/−1/+1, volume100/25, реальные паузы750/1500ms, два deterministic white-noise20dB samples. Это проверяет указанные преобразования synthetic речи. Это **не** разные дикторы/акценты, микрофон, помещение, спонтанные оговорки, whispering человека или статистическая оценка всей русской речи. Живая/private запись не является обязательным способом закрыть этот локальный benchmark.

В текущем `synthesize.ps1` читается volume, но `noise_snr_db` не применяется; наличие такого поля или фразы «сделай паузу» само не доказывает noise/pause audio. Не менять старые dev bytes. Если первоначальное внесение noise было отдельным шагом, связать его старым receipt; неизвестное так и отметить. Для новых samples recipe и измеренные duration/RMS/peak/SNR/clipping записать явно. Audio SHA256 freeze нужен **после** render, но **до** первой ASR.

Технические media/lifetime негативы — отдельная matrix, а не способы увеличить lexical denominator:

| Требование launch prompt | Speech/gold или отдельное доказательство |
|---|---|
| Короткая/длинная задача, transform incident | direct/transform/long + h_direct/h_transform/h_long |
| Quoted/nested, отрицание, отмена, условие | Соответствующие dev/holdout; role/negation/condition gold отдельно от слов |
| Даты/числа/имена/English terms | dates/numbers/names/domain + holdout; 0.5% против5%, финальное число после исправления |
| Паузы/самокоррекция/тихая речь/шум | h_pause с фактической вставкой тишины, h_correction, h_quiet/h_negation, h_noise/h_long |
| Oversize/overduration/empty/corrupt/unsupported | Server-side fixtures на реальных границах10MiB/300s/format; no ASR/no task/effect при отказе. Empty/no-speech — отдельный outcome, не WER=0 sample. |
| Truncation/low confidence | Известный source с критическим хвостом + целевой лимит; truncation/ambiguity ведут в confirmation/clarification. Forced-ru language_probability=1 не используется как word confidence. |
| Timeout/error/malformed output | Controlled provider boundary fixtures; fail closed, безопасная причина, без guessed transcript. Native hang — B03, не lexical score. |
| Duplicate/concurrency/restart/cleanup/disk pressure | B03/B04 и durable tests собственного кандидата, включая реальные процессы; не считать stubs benchmark accuracy. |
| Одинаковый text/voice semantic result | Независимый raw transcript rubric + отдельный actual production C1/result smoke B02; подтверждённая ручная коррекция не считается правильным исходным ASR. |

Уточнение C1: старый dev `conditional` с «просроченные дела» имеет смысл условного преобразования, но actual C1 grammar классифицирует его UNSUPPORTED; допустим safe clarification/no task/effect, это не exercised UNKNOWN. Новый `h_conditional` использует supported exact phrase: «Если в предоставленном списке есть просроченный пункт, преобразуй список в краткий план.» Без trusted facts ожидается UNKNOWN/no task/effect. Gold смыслов не заменяет trusted facts и не является prebound proposal.

## Нормализация и независимый semantic scorer

Сохранить две lexical колонки:

1. `legacy_wer/cer/critical_mismatches` — прежний scorer на прежних правилах, только воспроизводимый diagnostic. Он не превращается в semantic error count.
2. `normalized_wer/cer/critical_token_errors` — новая симметричная **value-preserving** нормализация, версия/код/digest заморожены до inference. WER/CER Levenshtein и micro числители/знаменатели остаются прежними. На исходный текст и hypothesis применяется одна функция без чтения эталонных значений и engine identity.

Разрешены existing casefold/ё→е/punctuation whitespace normalization и консервативная числовая грамматика. Кардинальные/порядковые выражения, полная дата и десятичная доля приводятся к типизированным атомам **только если parse однозначен**: `двадцать третье сентября две тысячи двадцать шестого года` = `23 сентября 2026 года` = ISO `date:2026-09-23`; `сто двадцать пять` = `num:125`; `ноль целых пять десятых процента` = `percent:0.5`. Если семантика/тип неизвестны, оставить исходные слова и показать discrepancy для независимой оценки.

Не удалять `не`, `нет`, `без`, отмену, исправление, условные союзы, границы цитаты, единицу измерения, знак, разряд/десятичность. `0.5%` не равны `5%`, `0.5` без `%`, `05` как opaque identifier или `пять десятых строки`. Не переставлять operands/entities/сроки. Не добавлять отсутствующий год к «восьмое ноября». Не делать reference-aware substitution («в этом case любое число значит125»), fuzzy matching, sound-alike autocorrection или словарь исправлений по hypotheses.

Перед ASR root должен проверить normalizer на заранее заданных positive/negative pairs из `NORMALIZATION-GOLD.json`. Имена/бренды допускают только зафиксированные произносительные формы **в semantic rubric**; они остаются lexical errors, если новая lexical функция не содержит предварительно доказанного общего правила. «Нобус Спейс»/Nobus Space, «Кодекс»/Codex, «Телеграм»/Telegram, «идемпотенси ки»/idempotency key семантически допустимы при сохранении термина и отсутствия tool authority; не превращать их в новые команды. Новые aliases после открытия holdout запрещены.

Critical threshold остаётся0. Старый marker set у dev и marker set новых holdout не выбрасывать из-за ошибок. Числовой normalization должен переносить critical span на полный typed value atom, а не объявлять исчезнувшее слово «двадцать» автоматически сохранённым. Для количеств нужна также связь value→object; иначе перемена125 rows/3 sections местами останется замеченной semantic rubric. Старые surface mismatch counts всегда доступны рядом.

Semantic evaluation выполняется независимо от проверяемого compiler и lexical scorer. Для каждого case/iteration сохранить engine-blind ID, hash/reference, hash/hypothesis, набор gold facts, observations, решение по каждому применимому измерению и короткое объяснение каждого mismatch. Разрешённые synthetic hypotheses — только isolated evidence; Git получает hashes/index/агрегаты.

| Измерение | Exact=1 только если |
|---|---|
| Goal/deliverable | Сохранено, что требуется сейчас и какой текстовый результат нужен; стилистическая синонимия допустима. |
| Operation roles/source scope | Requested/conditional не перепутаны с quoted/future/mentioned/negated; не добавлена операция или authority. |
| Capability intent | Сохранён intended capability class; gold null/неполнота остаётся неполнотой, без придуманного CoreDecision. |
| Negation/cancel/correction | Сохранены объект и область запрета/отмены; финальное значение исправления и отвергнутое значение различаются. |
| Condition | Сохранены trigger, субъект, state и область условной операции; ASR не устанавливает TRUE. |
| Values/entities/terms | Сохранены точные значения, units, имя→объект, дата/неуказанный год и идентичность терминов. |
| Constraints/order | Сохранены число разделов/вопросов, порядок этапов и запрет ложного success. |

`semantic_exact_raw` = все применимые измерения1 для **исходного ASR**; иначе0. N/A не увеличивает score. `semantic_exact_accepted` и `correction_needed` — отдельные поля после явного user confirmation/correction. Изменение goal/roles/capability/negation/cancel/condition/value bindings — critical semantic failure, которое нельзя компенсировать хорошим WER. Отдельно считать transcript truncation, hallucinated operation, wrong value, false-unavailable implication, clarification needed. Если смысл неясен или reviewers спорят — `unresolved`, не PASS; повторная оценка должна сослаться на source/hypothesis без изменения gold по удобству.

На этом этапе raw hypotheses не оцениваются. Для следующего поручения reviewer получает engine-blind pairs; root сравнивает независимые labels с собственными и adjudicates только расхождения. Production compiler результат проверяется отдельно B02, а не используется как «истина» о правильности своего ASR.

## Честное сравнение и неизменённые thresholds

Числа из исходного BENCHMARK-MANIFEST1.0.0 сохраняются: normalized WER≤0.15, CER≤0.08, critical token errors=0, accepted transcript semantic parity=1.0, cold readiness≤120s, warm RTFp95≤0.5 с отдельно сохранённым минимумом5s, peak process RAM≤4294967296B, concurrency2, warm passes3. Substantial gain: semantic exactness **+2 процентных пункта** OR warm latency p95 **−30%**; no new critical errors, WER/CER regression≤1pp, все privacy/ops constraints выполнены. Никакой новый абсолютный порог raw semantic exactness не придумывается.

Не смешивать raw RTF и 5s allowance: записывать исходные seconds/RTF и оба derived flags. Практический per-file budget — `max(5s,0.5*duration)`; отдельно показать p95 raw RTF≤0.5. Не называть raw RTF PASS только потому, что короткая фраза уложилась в5s. Если исходная трактовка5s влияла бы на verdict, объяснить ambiguity до результата и сохранить более строгую проверку, а не подбирать знаменатель.

Основной qualification report содержит all32 и holdout16 отдельно; repeated passes не создают48 независимых языковых samples. Для lexical/semantic headline использовать iteration0, для воспроизводимости дать диапазон/различия остальных двух; любое новое critical failure в repeat сохраняется как failure. Latency p50/p95 nearest-rank по всем96 warm observations, отдельно dev/holdout и long samples. Scorer не исключает трудные samples; empty/error/truncation не исчезают из учёта.

Прежний16-case pilot не переименовывать в matched baseline. Выполнить новую **CURRENT decoding config under matched4CPU** series; сохранить exact FW1.2.1/base snapshot/int8/ru/beam8/patience1.2/VAD/previous-text/prompts/hotwords. Изменение decode config или модели — отдельный candidate ID, только после dev diagnosis, с собственными hashes. OS resource cap — общий measurement protocol, не скрытая подмена ASR config.

Оба engine: одна и та же OS affinity из4 logical CPUs, одинаковый4GiB memory limit, один engine/process tree активен за раз, одинаковые immutable audio bytes/order/входной PCM формат. Явно фиксировать intra/inter/BLAS limits; не допускать скрытого native pool > CPU allowance. Без GPU, download, cloud calls. ORT telemetry off до sessions, HF offline; socket hook не выдавать за OS isolation.

Единая cold граница: fresh interpreter spawn→imports→model/VAD/readiness→первый пригодный transcript одинакового dev direct audio. Разложить spawn/import/load/first recognition; не сравнивать FW warmup+imports против GigaAM только load. Три cold runs при достаточном remaining budget; кеш ОС не очищать, честно назвать process-cold/filesystem-cache-uncontrolled. warm проходы после readiness; измеряем bytes→decode/resample/ASR→готовый transcript, включая IPC своего production adapter. CPU time — process tree, не только parent `time.process_time`; RAM — native child/process tree, а не контроллер.

Concurrency2: две задачи поступают одновременно, один serial native slot у обоих, те же4CPU суммарно; записать wait time, service time, end-to-end, throughput, завершения и peak RAM. Не сравнивать serialized CURRENT со свободным ThreadPool GigaAM. AB/BA порядок engines для парных repeats уменьшает систематический cache/load bias. Помимо complete wall-time учитывать cumulative GigaAM budget; лимит1800s не возобновляется после restart. Перед каждым запуском root сверяет remaining execution и не начинает необоснованно большой run.

Decision: сначала проверить completeness/fairness/safety и hard thresholds выбранного engine на all32 и untouched holdout. KEEP требует положительно прошедшего CURRENT и отсутствия substantial допустимого выигрыша challenger. REPLACE требует прошедшего challenger, substantial gain по frozen rule, отсутствия новых critical ошибок, допустимой регрессии WER/CER и реальной integration/pins/security/license/rollback проверки. Если любой selected-engine обязательный критерий не выполнен — BLOCKED или обоснованная dev-доработка с отдельным candidate; отсутствие cloud authorization не превращается в KEEP.

Holdout открыть один раз после dev выбора. Если он не проходит, root сохраняет failure; исправление по его результату превращает этот holdout в development evidence. Новый непредвзятый confirmation corpus тогда нужно отдельно спроектировать/заморозить до нового run. Нельзя объявить reused tuned holdout независимым или уменьшить thresholds. Статистический вывод остаётся ограниченным32 synthetic samples; gain в3.125pp на all32 означает один case, поэтому всегда приводить конкретный mismatch и count, а не только процент.

## Передача root

Следующие разрешённые шаги root: принять/согласованно поправить этот дизайн **до hypotheses**, подготовить pure scorer/negative normalization probes, synthesize только новые16samples установленным TTS, заморозить qualification manifest с hashes всех inputs/gold/normalizer/runner/config/model/runtime/resources/decision rule и отдельным blind engine mapping, затем начать bounded dev/final runs. Эта design-папка не содержит fake audio hashes и не объявляется full benchmark freeze. Independently scoring — отдельное поручение после получения новых разрешённых synthetic hypotheses.
