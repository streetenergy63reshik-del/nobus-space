# C2: происхождение ASR и граница распространения

Проверено5 сентября2026. Для уже разрешённой локальной квалификации и кандидата
собственного Git-кода выбран существующий pinned small на том же FW runtime, что base.
Новая зависимость или бинарная поставка не добавляется. Это не whole-stack licence/CVE
clearance; незакрытые вопросы binary distribution ниже остаются открытыми.

| Компонент | Доказанный факт | Ограничение |
|---|---|---|
| Systran small | Revision536b0662742c02347bc0e980a01041f333bce120,5assets486214370B, всеSHA проверены acquisition,review,product factory | Card заявляет CT2 FP16 conversion из openai/whisper-small, но не закрепляет parent revision/converter environment; численная эквивалентность повторной конверсией не доказана |
| Model licences | Pinned Systran card MIT; original OpenAI code и weights MIT; текущая HF upstream card Apache-2.0 | Сохранены оба notices и само расхождение. Это не объявление dual licensing и не изменение лицензии модели |
| Faster-Whisper1.2.1 | MIT | Лицензия Python package не покрывает все native зависимости |
| CTranslate2 4.8.1 | MIT, build provenance oneDNN/Intel/CUDA/cuDNN; hash132selected installed assets в review | Exact installed wheel не пересобирался; package version не является полным native SBOM |
| PyAV18.0.0 | BSD wrapper; bundled FFmpeg8.1.2 | FFmpeg/codec условия отдельные |
| NumPy2.5.1 | Локальные BSD и bundled third-party notices сохранены | Не заявляется полный аудит canonical venv |

Первичные источники модели: [точная Systran card](https://huggingface.co/Systran/faster-whisper-small/blob/536b0662742c02347bc0e980a01041f333bce120/README.md),
[OpenAI Whisper README](https://github.com/openai/whisper/blob/v20250625/README.md#license),
[OpenAI MIT](https://github.com/openai/whisper/blob/v20250625/LICENSE),
[HF upstream card](https://huggingface.co/openai/whisper-small/blob/973afd24965f72e36ca33b3055d56a652f456b4d/README.md).
Точные attribution texts — [manifest](third-party-notices/MANIFEST.json).

## Незакрытая binary distribution

CT2 Windows loader загружает все package DLL ещё до `_ext`, включая cuDNN9.10.2.21,
даже при CPU. `WITH_CUDNN=OFF` не отменяет loader. Применимость NVIDIA GPU SDK scope
к этой автозагрузке не удостоверена; соглашение за владельца не принималось.
Exact Intel OpenMP2025.3 redistribution/licence pack отсутствует. Общая Intel FAQ
не заменяет условия конкретного binary.
[CT2 build](https://github.com/OpenNMT/CTranslate2/blob/v4.8.1/python/tools/prepare_build_environment_windows.sh),
[cuDNN9.10.2 EULA](https://docs.nvidia.com/deeplearning/cudnn/backend/v9.10.2/reference/eula.html).

PyAV FFmpeg label LGPLv3 при включённых x264/x265 объяснён точным upstream patch:
он переносит codecs из GPL списка в VERSION3. Это меняет проверку configure,
но не права сторонних codec авторов. Original FFmpeg LICENSE относит оба codecs
к GPL; локальный x265 сообщает GPLv2/commercial. Доказанной коммерческой лицензии
нет. Перед binary distribution нужны применимые условия и corresponding sources;
metadata wheel недостаточно.
[Patch8.1.2-1](https://github.com/PyAV-Org/pyav-ffmpeg/blob/8.1.2-1/patches/ffmpeg.patch),
[FFmpeg n8.1.2 LICENSE](https://github.com/FFmpeg/FFmpeg/blob/n8.1.2/LICENSE.md).

Эти native вопросы общие для CURRENT base и small. Они не исчезают при откате
модели. Разрешённая локальная работа не расширяется на распространение runtime,
моделей, wheels или DLL. Этот C2 план готовит собственные исходники/документы;
binary publication, установка и live rollout не входят в разрешённый объём.
Если будущий release требует готовый бинарный Windows runtime, перечисленные
условия нужно закрыть по существу до такого release; документ не даёт исключения.

Security evidence остаётся versioned snapshot PyPI advisories и hashes selected
installed bytes. Полный native CVE applicability и вся dependency closure venv
не закрыты. Не заявляются отсутствие всех уязвимостей, forensic wipe или native
egress isolation. Модель работает local_files_only, через bounded IPC/Windows Job,
без новых загрузок, аудиопередачи и cloud ASR.

Независимый технический отчёт: `.runtime/c2/closure/license-closure-review/REPORT.md`,
SHA256 a645b0e2a55f30fd8e0896b43d0fc15b2aac1896378b43ff198f68d6b71dfc82;
manifest493eb8f6d73c7f3da0e368718319e5a3351919a72c50781fd574f862eaa00dfe.
Сохранённый notice bundle — evidence, а не полный redistribution pack.

35 notice files сохраняют исходные bytes, включая авторские пробелы и окончания строк. Scoped `.gitattributes` отключает Git newline conversion только в этом evidence bundle; SHA каждого файла проверяется и в Git blob. Собственный код и документы проходят обычную whitespace-проверку.
