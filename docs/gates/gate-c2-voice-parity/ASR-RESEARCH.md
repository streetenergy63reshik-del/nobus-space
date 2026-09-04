# C2: исследование ASR

Дата чтения официальных источников: 4 сентября 2026. Cloud ASR не вызывался.
После отдельного разрешения владельца выполнен локальный GigaAM pilot;
результат отделён от discovery в BENCHMARK-RESULTS.json.
CURRENT — Faster-Whisper 1.2.1/base.

## Текущее решение и ограниченный следующий эксперимент

**ASR DECISION BLOCKED.** Исторический pilot ниже не заменяет последующее
сравнение при одинаковых лимитах. На 16 dev samples CURRENT получил
WER 14,16%, critical token errors 5 и raw semantic exactness 13/16;
GigaAM — 7,52%, 4 и 15/16. Ещё три настройки FW дали 4/4/5 critical errors.
Эти пять вариантов двух семейств не прошли обязательные критерии.
16 holdout samples заморожены и ещё не распознавались. Результаты с hashes —
[DEVELOPMENT-RESULTS.json](DEVELOPMENT-RESULTS.json); неизменный контракт —
[qualification PLAN](../../../tests/gate_c2/qualification/PLAN.md).

GigaAM разрешён ранее; текущий суммарный расход 194,916977 из 1800 секунд
включает все прошлые вызовы и дополнительный matched dev. Значения 165,765
секунды ниже описывают только исторический pilot, не остаток разрешения.

После отдельного точного разрешения выполнен один новый эксперимент:
`Systran/faster-whisper-small@536b0662742c02347bc0e980a01041f333bce120`.
Все пять файлов скачаны и проверены. Суммарный HTTP payload486217682B включает
перенаправления и первую неуспешную попытку; ASR выполнен только локально.
Это новая модель того же Faster-Whisper, не независимый движок. Пять pinned
файлов составляют 486214370 bytes; лимиты 600 MB загрузки, 1,5 GiB диска,
4 GiB RAM, четыре логических CPU, один native slot и 1200 секунд суммарного
локального исполнения, включая будущие проверки и B02. Используется прежний
стек без pip, conversion и загрузки удалённого кода.
Точные assets/digests и план сохранены в [EVIDENCE.json](EVIDENCE.json).

С прежней конфигурацией decoder один dev дал WER6,64%, CER1,27%, critical2
и raw RTFp95 0,792 при пороге0,5. Latency p95 14,002s, cold7,651s,
RAM3040018432B; все16 samples обработаны, после завершения Job active0.
Израсходовано78,520625s, осталось1121,479375s из исходных1200.
Модель лучше по WER, но **hard FAIL** одновременно по critical tokens и raw RTF.
Теперь не прошли шесть вариантов двух семейств; KEEP/REPLACE нет.
Per-file allowance минимум5s пройден, что не заменяет отдельный raw RTF threshold.
Новые конфигурации и holdout не запускались.

Первая загрузка остановилась до получения model bytes на `us.aws.cdn.hf.co`.
Этот конкретный CDN подтверждён [официальной документацией HF](https://huggingface.co/docs/hub/models-downloading)
и добавлен в allowlist downloader. Ранее полученные1061B оставлены в счётчике,
пустой partial и failed ledger сохранены. Source/revision/assets/лимиты не менялись.

Следующая единственная гипотеза для отдельного решения: снизить только
beam_size8→1, чтобы проверить raw RTF≤0,5 при неизменных остальных настройках
и обязательном critical0. Один dev16 до150s из прежнего остатка, без новых
файлов модели/установок. Возможность исправить critical errors не доказана.
Пока это предложение, а не продолжение разрешённого эксперимента.

В плане сохранено лицензионное расхождение: pinned Systran card и original
OpenAI repository указывают MIT, а прочитанная 4 сентября HF-карточка
openai/whisper-small — Apache-2.0. Замечания о PyAV/FFmpeg/CT2 также остаются
открытыми до проверки выбранного варианта. Эти сведения не являются
заключением о допустимости распространения модели.
[Закреплённая карточка](https://huggingface.co/Systran/faster-whisper-small/blob/536b0662742c02347bc0e980a01041f333bce120/README.md),
[original repository](https://github.com/openai/whisper#license),
[HF upstream card](https://huggingface.co/openai/whisper-small).

## Историческое исследование и первый pilot

| Решение | Русский / статус / регион | Цена USD и privacy | Пробелы |
|---|---|---|---|
| Google STT V2 `chirp_3` | ru-RU GA, EU/US multi-region | standard $0.016/мин; dynamic batch $0.003/мин; data logging opt-in | immutable backend build не открыт; V2 batch/GCS retention требует точной проверки |
| Deepgram `nova-3`, `language=ru` | GA, русский обновлён 17.08.2026; EU endpoint | prerecorded mono $0.0043/мин; `mip_opt_out=true` в каждом запросе, content только на время обработки | exact backend UUID/версия и account quotas не проверены |
| Azure Fast Transcription REST `2025-10-15` | GA, explicit ru-RU, westeurope; <500 MB / <5h | цена страницы `$-`, UNKNOWN; fast content не сохраняется; logging default-off | цена/договор training/backend snapshot не подтверждены |
| GigaAM v3 `e2e_rnnt` | независимый local Russian ASR, MIT | offline после получения компонентов; нет платы API | native longform добавляет зависимости; ONNX-конверсия третьей стороны требует отдельной квалификации |

Google Chirp 3 отдельно предупреждает, что возвращаемые word confidence
не являются настоящей confidence score. Ни они, ни Faster-Whisper
`language_probability` не разрешают выполнение задачи.

Официальные источники:

- [Google model](https://docs.cloud.google.com/speech-to-text/docs/models/chirp-3), [limits](https://docs.cloud.google.com/speech-to-text/docs/quotas), [pricing](https://cloud.google.com/speech-to-text/pricing), [data FAQ (v1; не переносить автоматически на V2 batch)](https://docs.cloud.google.com/speech-to-text/docs/v1/data-usage-faq).
- [Deepgram languages](https://developers.deepgram.com/docs/models-languages-overview/), [RU update](https://developers.deepgram.com/changelog/2026/8/17), [pricing](https://deepgram.com/pricing), [opt-out/retention](https://developers.deepgram.com/docs/the-deepgram-model-improvement-partnership-program), [opt-out pricing change](https://developers.deepgram.com/changelog/2026/3/5), [EU/privacy](https://developers.deepgram.com/trust-security/data-privacy-compliance), [limits](https://developers.deepgram.com/reference/api-rate-limits).
- [Azure API](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/fast-transcription-create), [languages](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=stt), [regions](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/regions), [pricing](https://azure.microsoft.com/en-us/pricing/details/speech/), [privacy](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/speech-service/speech-to-text/data-privacy-security), [logging](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/logging-audio-transcription).
- [Faster-Whisper 1.2.1](https://github.com/SYSTRAN/faster-whisper/releases/tag/v1.2.1), [runtime/MIT](https://github.com/SYSTRAN/faster-whisper).
- [GigaAM upstream](https://github.com/salute-developers/GigaAM/commit/7447938d791c4f3e643386ee22c33777004293a5), [official model](https://huggingface.co/ai-sage/GigaAM-v3), [ONNX conversion](https://huggingface.co/istupakov/gigaam-v3-onnx), [ONNX runtime wrapper](https://github.com/istupakov/onnx-asr/tree/b9e0ce0ae3223b3d24ce5a22a5e701a726ca35fc).

Discovery coverage: Google + один независимый local + два независимых managed.
Для платных/cloud trials нет авторизации; они не включены в выполнение.
Без честного сравнения verdict ASR остаётся BLOCKED. Тарифы не являются
benchmark evidence; права аккаунта и региональная доступность не проверены.

## Подготовленная отдельная авторизация comparator

Статус: AUTHORIZED / LOCAL PILOT PERFORMED. Ответ владельца в этом чате:
«Разрешаю в указанных пределах». Точная цель — `GigaAM-v3 E2E RNN-T`
через `onnx-asr==0.12.0`, `onnxruntime==1.23.2`, CPU FP32. Это сторонняя
конверсия `istupakov/gigaam-v3-onnx` revision
`322c3b29492673eb7d0b434bfa9dfb8653e34d02`, не исходные upstream bytes.
Эквивалентность исходной upstream модели отдельно не доказана; измерена
именно эта ONNX-конверсия.

Только C2 `.runtime/asr-qualification/gigaam-onnx/{venv,wheelhouse,models,results}`.
Установленный Python фактически 3.12.14; значение 3.12.13 в старом pyvenv.cfg
не подменяет runtime readback. Скачать не более 1 GB из PyPI и pinned HF;
проверить SHA-256 до загрузки. Не более 3 GiB диска, 4 GiB RAM, 4 CPU threads
и 30 минут на проверку. Только текущий синтетический корпус, без сети при
распознавании; API cost $0. Без global install, изменения CURRENT или live.

Пакеты из exact wheels, `--no-deps --require-hashes`: onnx-asr 0.12.0,
onnxruntime 1.23.2, numpy 2.3.3, coloredlogs 15.0.1, flatbuffers 25.9.23,
packaging 25.0, protobuf 6.33.5, sympy 1.14.0, mpmath 1.3.0,
humanfriendly 10.0, pyreadline3 3.5.4. Wheel lock закреплён до download в
`tests/gate_c2/comparator-requirements.txt`.
Суммарные wheels 37,823,146 B; model FP32 892,411,899 B.
Опциональный ungated Silero 6.2 VAD ~2.33 MB только из snapshot
`b3e3ee3cce4c11ceb63b1a0b229d916069c1ddf6`; его использование и параметры
закреплены до comparator run в `.runtime/c2/comparator-freeze.json`:
threshold 0.5, negative 0.35, segment максимум 20 секунд, batch 1,
min speech 250 ms, min silence 100 ms, padding 30 ms.

Фактически скачано 932 563 674 B (<1 GB); каталог после установки 1 129 922 032 B
(<3 GiB). Smoke, первый pilot и исправленный telemetry-off pilot заняли
165,765 секунды из разрешённых 1800.
`pip check`: No broken requirements found. Native Windows Job Object ограничил
память процесса 4 GiB; CPU affinity mask 15, ORT intra-op 4 / inter-op 1;
только CPUExecutionProvider. Offline resolver и Python socket audit deny
действовали до model import. Последний pilot явно вызвал
`onnxruntime.disable_telemetry_events()` до создания sessions.
Первый запуск без этого вызова сохранён как ограниченное evidence.
Python audit не доказывает native/OS egress isolation; Windows ETW сам по себе
не доказывает передачу audio. Это следует из
[ORT1.23.2 Privacy](https://raw.githubusercontent.com/microsoft/onnxruntime/v1.23.2/docs/Privacy.md)
и [Python API](https://onnxruntime.ai/docs/api/python/api_summary.html#onnxruntime.disable_telemetry_events).
Native network traces не наблюдались. API cost $0. Установка не меняла основной venv.
Первичный BENCHMARK-MANIFEST.json сохранён как исторический freeze до
авторизации: его `NOT AUTHORIZED` описывает тот момент, а не текущий статус.

Model hashes: encoder `cd60b3764a832e8560ae6d3ad0b10adc1a42ffae412b9476f25620aae4f4a508`;
decoder `7b0a16d67fd2cb37061decc93c69e364a9ab27afee3c57495d55b1c974cf7231`;
joint `602ff7017a93311aad34df1437c8d7f49911353c13d6eae7a6ee7b041339465c`;
vocab `39abae20e692998290c574e606f11a9edef2902a1995463fcff63d1490cf22b7`.

PyPI advisory metadata перечисленных pins не содержит записей на дату
проверки; это не гарантия отсутствия уязвимостей. MIT/BSD/Apache/dual-license
notices нужно сохранить и проверить внутри wheels после разрешённой загрузки.
Torch/Transformers/card stack и gated pyannote не включены. Синтетический
comparator не закрывает представительность человеческой речи.
