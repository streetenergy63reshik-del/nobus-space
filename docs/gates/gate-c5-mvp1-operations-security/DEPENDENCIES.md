# C5: зависимости, происхождение и известные ограничения

Проверено 8 сентября 2026 года. Состав существующей среды установлен чтением,
получены актуальные ответы PyPI/OSV и первичные сведения поставщиков. Проверка
относится к публикации собственного исходного кода и работе с уже установленной
локальной средой. Она не разрешает распространение venv, wheels, DLL, моделей
или готового Windows runtime и не объявляет весь native stack безопасным либо
лицензионно закрытым. Итоговая приёмка C5 связывает этот отчёт с точной revision.

## Состав и воспроизводимость

[DEPENDENCY-EVIDENCE.json](DEPENDENCY-EVIDENCE.json) содержит все 80 установленных
Python distributions с точными версиями, зависимостями, заявленными лицензиями,
хешами metadata и результатами запросов. Из них 79 входят в транзитивное замыкание
15 строк requirements.txt, включая тестовые зависимости и uvicorn[standard];
единственный дополнительный пакет — pip 25.0.1. `pip check` завершился успешно.
Новых библиотек, моделей и инструментов проверки не установлено.

| Слой | Проверенная идентичность | Основание и граница |
|---|---|---|
| Python | CPython 3.12.14, Windows AMD64 | Версия существующего интерпретатора; 11 Python/native файлов захешированы. Это bundled build, не доказательство идентичности официальному installer |
| TLS / БД | OpenSSL 3.5.8; SQLite 3.53.1 | Версии получены через стандартную библиотеку; SQLite source ID и compile options проверены на новой in-memory БД |
| ASR | faster-whisper 1.2.1; CTranslate2 4.8.1; PyAV 18.0.0; NumPy 2.5.1 | 132 выбранных C2 runtime/notice файла заново совпали с retained C2 SHA256 |
| Model | Systran small, revision 536b0662742c02347bc0e980a01041f333bce120 | Пять asset hashes перенесены как retained C2 evidence. C5 не скачивал, не переоценивал модель и не выполнял inference |
| CT2 native | cuDNN 9.10.2.21; Intel OpenMP PE 20250910 / product 5.0 | PE metadata прочитана без LoadLibrary. Intel 2025.3 и oneDNN 3.1.1 — сведения точного upstream build recipe |
| PyAV native | FFmpeg 8.1.2 и 18 дополнительных codec/runtime DLL | Состав всех DLL закреплён hashes. Версии codec из прежнего C2 static review сохраняют свою исходную степень доказательства |
| Другие native consumers | ONNXRuntime 1.27.0; tokenizers 0.23.1; Codex CLI 0.144.4; NumPy/OpenBLAS и остальные расширения | Включены в native inventory из 174 уникальных файлов; весь статический состав каждой библиотеки не восстановлен |

Инвентарь сохраняет 175 строк RECORD для 174 уникальных native файлов и 400
строк metadata/notice для 395 уникальных файлов. Пути нормализованы с учётом
регистра Windows и разделителей; размеры и SHA256 повторных строк совпадают.
Все 174 уникальных native файла имеют совпадающий SHA256 в установленном RECORD.
Для `ormsgpack/ormsgpack.cp312-win_amd64.pyd` одна строка не содержит хеша,
а вторая строка того же файла содержит совпадающий хеш. Ранее число строк было
ошибочно названо числом файлов, а отсутствие хеша у первой строки — отсутствием
хеша у файла; исправление и исходные данные сохранены в JSON.
RECORD не является независимой подписью поставщика.
PyPI metadata содержит совпадающие с локальными WHEEL tags filenames и wheel
hashes; оригинальные wheel bytes не загружались и с installed bytes не сравнивались.

requirements.txt закрепляет верхние 15 версий, но не весь транзитивный состав.
Полный snapshot в JSON позволяет обнаружить расхождение текущей среды; он не
заменяет hash-locked installer, offline recovery media или воспроизведённую
установку на чистом ПК. C5 не обещает восстановление утраченной venv из одного
Git checkout. До пересоздания среды разработчик должен подготовить отдельно
разрешённый точный installation plan и повторить применимые проверки.

## Проверка известных уязвимостей

Метод: 80 GET запросов к PyPI `/pypi/{name}/{version}/json` и один POST к OSV
`/v1/querybatch` с теми же публичными name/version. Все ответы успешны; дата,
URL и SHA256 каждого ответа сохранены. PyPI использует OSV: это два API-чтения
с пересекающимся источником, а не две независимые базы. Для 79 пакетов замыкания
эти API не вернули advisory matches. Это ограниченный результат поиска известных
записей, без проверки всех vendored/native компонентов.
[PyPI JSON API](https://docs.pypi.org/api/json/),
[OSV querybatch](https://google.github.io/osv.dev/post-v1-querybatch/).

Для pip 25.0.1 найдены 12 записей, соответствующих шести CVE:

| CVE | Исправление upstream | Применимость к этой задаче |
|---|---|---|
| CVE-2025-8869 | pip 25.3 | Уязвим fallback tar extraction без PEP 706; используемый Python 3.12 имеет PEP 706 |
| CVE-2026-1703 | pip 26.0 | Path traversal при установке вредоносного wheel; установка в C5 запрещена |
| CVE-2026-3219 | pip 26.1 | Неоднозначный tar/ZIP archive; установка в C5 запрещена |
| CVE-2026-6357 | pip 26.1 | Импорт после установки при self-update check; C5 ничего не устанавливает, existing product runner отключает version check |
| CVE-2026-8643 | pip 26.1.2 | Выход entry-point script за scripts directory; установка в C5 запрещена |
| CVE-2026-13346 | pip 26.2 | Doubly encoded URL от вредоносного index; product runner использует фиксированный PyPI index и isolated config, но это не патч pip |

Подробности подтверждены exact-version PyPI/OSV и
[журналом pip](https://pip.pypa.io/en/stable/news/). `pip check` — чтение metadata,
не уязвимая установка. Существующий `NetworkCommandRunner` всё ещё содержит
owner-approved pip-install path с `--require-hashes`, `--only-binary`, fixed index
и выключенным version check. Эти ограничения не устраняют все wheel CVE.
В C5 этот effect не запускался; до следующей установки разработчик и владелец
должны отдельно согласовать обновление installer до проверенной версии не ниже
26.2 и проверить её advisories на дату установки. Не использовать этот отчёт как
разрешение установки текущим pip.

SQLite 3.53.1 попадает в version range CVE-2026-11822/11824 — две записи одного
heap-write дефекта, исправленного в 3.53.2. Официальное описание требует доступа
атакующего к произвольному SQL при включённом FTS5 и выключенном DEFENSIVE.
In-memory probe текущей сборки подтвердил FTS5=True, DEFENSIVE=False,
TRUSTED_SCHEMA=True по умолчанию. Поэтому отсутствие advisory у Python packages
не закрывает эту native границу. C5 должен отдельно доказать отсутствие
произвольного SQL и доверенное происхождение восстанавливаемой БД; проверка
manifest hashes сама по себе не делает присланный извне SQLite файл доверенным.
Рекомендуемая дополнительная защита в коде проверки restore — DEFENSIVE=True и
TRUSTED_SCHEMA=False до разбора БД. Статус фактической реализации и тестов относится
к C5 restore evidence, а не к этому снимку исходных default settings.
[SQLite CVE applicability](https://www.sqlite.org/cves.html),
[SQLite security guidance](https://www.sqlite.org/security.html).

Официальный Python 3.12.14 является security release; это не удостоверяет все
особенности bundled build. FFmpeg перечисляет CVE-2026-8461 и CVE-2026-30999 как
исправленные в 8.1.2. OpenSSL 3.5.8 включает исправления опубликованного 25 августа
2026 года списка для ветки 3.5. Найденный Intel CVE-2022-26345 относится к OpenMP
до 2022.1; recipe 2025.3 не попадает в этот диапазон. Наличие более старого CUDA
SDK в recipe CT2 не позволяет перенести advisory всего Toolkit на конкретную
CPU DLL без анализа включённых компонентов. Полный native CVE applicability
остаётся ограничением, отсутствие найденного vendor match не означает zero CVE.
[Python release](https://www.python.org/downloads/release/python-31214/),
[FFmpeg security](https://ffmpeg.org/security.html),
[OpenSSL 3.5 advisories](https://openssl-library.org/news/vulnerabilities-3.5/),
[Intel INTEL-SA-00674](https://www.intel.com/content/www/us/en/security-center/advisory/intel-sa-00674.html).

## Лицензии: что сохраняется открытым

[Принятый C2 provenance](../gate-c2-voice-parity/ASR-PROVENANCE.md) и его notice
bundle не переписывались. Текущий код не копирует исследованные бинарники в
публикуемый Git. Проверены source-only scope и точные existing bytes; это не
переоформление прав на среду.

| Компонент | Факт | Оставшееся действие и владелец |
|---|---|---|
| Модель | Systran card MIT; первоначальные OpenAI code/weights MIT; HF upstream card Apache-2.0. Нет закреплённого parent revision конверсии | Разработчик сохраняет оба notices и immutable hashes. Перед распространением весов владелец уточняет применимые условия; dual licence не заявлена |
| CT2 / cuDNN | CT2 MIT не покрывает proprietary cuDNN. Windows loader читает все package DLL, включая cuDNN, ещё до `_ext`, в том числе при device=cpu | Владелец должен закрыть применение GPU-only SDK scope к этому CPU runtime до расширения использования/поставки. Соглашение за владельца не принято; автозагрузка не объявлена освобождением от EULA |
| Intel OpenMP | Exact PE bytes известны; отдельного vendor licence/redist pack для этого binary в установленном CT2 нет | Разработчик получает точные условия/redist notices при отдельно разрешённой подготовке runtime. Общий EULA index не закрывает missing pack |
| PyAV / FFmpeg / x264 / x265 | BSD wrapper; FFmpeg DLL label LGPLv3, но exact PyAV patch перемещает x264/x265 из GPL списка в VERSION3. Original FFmpeg licence по-прежнему относит их к GPL | Перед binary distribution владелец и разработчик должны закрыть codec conditions и corresponding sources. Ни metadata, ни patch не меняют права codec authors; коммерческая лицензия не доказана |
| Остальная среда | Локальные notices и metadata охватывают также Apache/BSD/MIT/PSF/MPL, NumPy OpenBLAS/LAPACK и GCC runtime exception | JSON фиксирует declarations отдельно от grants. Полный notice/SBOM pack всех статических Codex/ORT/codec зависимостей нужен до их передачи третьим лицам |

Основания:
[CT2 Windows build v4.8.1](https://github.com/OpenNMT/CTranslate2/blob/v4.8.1/python/tools/prepare_build_environment_windows.sh),
[cuDNN 9.10.2 EULA](https://docs.nvidia.com/deeplearning/cudnn/backend/v9.10.2/reference/eula.html),
[Intel EULA index](https://www.intel.com/content/www/us/en/developer/articles/license/end-user-license-agreement.html),
[PyAV exact patch](https://github.com/PyAV-Org/pyav-ffmpeg/blob/8.1.2-1/patches/ffmpeg.patch),
[FFmpeg n8.1.2 licence](https://github.com/FFmpeg/FFmpeg/blob/n8.1.2/LICENSE.md),
[Codex exact source licence](https://github.com/openai/codex/blob/rust-v0.144.4/LICENSE).

Для принятой локальной работы и собственного source-only PR эти вопросы не
превращаются в разрешение binary release. C5 не осуществляет постоянную активацию;
C6 должен явно сохранить или закрыть относящиеся к реальному runtime ограничения.
Если будущая граница требует полного runtime licence/security clearance, эти
пробелы являются невыполненными условиями, а не рисками, закрытыми одной записью.

Raw ответы и локальные receipts оставлены только в `.runtime/c5/dependencies`;
в публикуемый JSON входят безопасные hashes, версии и ссылки. 13 vendor/API страниц
сохранены с hashes; два raw Intel fetch завершились URLError, это сохранено,
а соответствующие страницы успешно прочитаны через web tool. Secrets, raw tasks,
voice, transcript, credentials и частные идентификаторы в evidence не включены.
