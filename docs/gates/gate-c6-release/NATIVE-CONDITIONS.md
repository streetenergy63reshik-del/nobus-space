# C6: условия закреплённой исполняемой среды

9 сентября 2026. DRAFT: документ не принимает соглашения за владельца и не разрешает переключение. Установки и замены среды не выполнялись. ASR inference в C6 ещё не запускался.

Фактическая среда проверена чтением 8 сентября в 20:53 UTC; независимый L2 повторно сверил CLI/model/дополнительные inputs. Python 3.12.14, SQLite 3.53.1, OpenSSL 3.5.8, pip 25.0.1, faster-whisper 1.2.1, CTranslate2 4.8.1, PyAV 18.0.0, NumPy 2.5.1. CLI 0.144.4: SHA256 51398051c2332b6afe08dc3b9dbb4056085c197f35ca57a307ee303d450cada5. Модель small revision 536b0662742c02347bc0e980a01041f333bce120: пять закреплённых файлов совпали. Эти проверки не являются запуском ASR или новым C2 qualification.

| Условие C5-R4 | Применимость и фактическая граница C6 | Что остаётся |
|---|---|---|
| pip25.0.1 installer advisories | В C6 нет установки; production сохраняет enable_extended_routes=False и product_effects=None. Source-only релиз не включает venv или installer. Сами advisory не объявляются исправленными. | Сверить exact активируемый профиль; любая будущая установка потребует отдельного плана. |
| SQLite3.53.1 | Сохраняются DEFENSIVE/TRUSTED_SCHEMA guards, закрытая схема и trusted authenticated restore. Произвольные SQL/SQLite от пользователя не являются входом продукта. | Финальный active profile и negative restore checks. |
| Bundled cuDNN9.10.2 | CT2 Windows CPU import загружает bundled DLL; CPU inference не устраняет условие EULA. На ПК подтверждена NVIDIA RTX3050Ti Laptop. | Явное решение владельца о принятии уже применимого соглашения; запрос остаётся без ответа. До него native inference не выполняется. |
| Intel OpenMP | CT2 v4.8.1 build recipe использует oneAPI2025.3.0.372. Установленный libiomp5md.dll: FileVersion20250910, Product5.0, 1614192B, SHA256982233366b0afcda1e0f55a0b134097e35b779613f54ddb69e685e6cd06b755f. Официальный Intel NuGet redist2025.3.0.640 содержит DLL с теми же bytes/hash, Intel Simplified Software License October2022 и third-party-programs.txt. Метаданные конкретного redist: requireLicenseAcceptance=false. | Локальное использование неизменной DLL и source-only публикация соответствуют рассмотренной границе. Точные notices сохранены; не модифицировать/не декомпилировать DLL и не распространять binary/model assets в релизе. |
| FFmpeg/x264/x265/model notices | Локальное owner-only использование; source Git release не содержит Python environment, DLL, кодеков или моделей. C5 binary-distribution вопросы не превращаются в разрешение распространять эти bytes. | Проверить состав final release/assets; не обещать перенос на иной ПК. |

Официальные основания:

- [cuDNN9.10.2 EULA и supplement](https://docs.nvidia.com/deeplearning/cudnn/backend/v9.10.2/reference/eula.html). Условие использования и принятия соглашения относится и к CPU-профилю с загрузкой bundled cuDNN.
- [Закреплённый CT2 Windows build recipe](https://raw.githubusercontent.com/OpenNMT/CTranslate2/v4.8.1/python/tools/prepare_build_environment_windows.sh). Строка upstream installer с --eula=accept — данные о сборке, не согласие владельца.
- [Официальная metadata intel-openmp2025.3.0](https://pypi.org/pypi/intel-openmp/2025.3.0/json) и [Intel EULA index](https://www.intel.com/content/www/us/en/developer/articles/license/end-user-license-agreement.html). Index различает соглашения; окончательная привязка требует конкретного комплекта.
- [Intel oneMKL2025 release notes](https://www.intel.com/content/www/us/en/developer/articles/release-notes/onemkl/2025.html) не дали прямого текста licence именно для установленной DLL; этот поиск не закрыл условие.

Для полного закрытия нужны действительные обязательные права локального использования, active-profile readback и настоящий recovery drill. Запись «риск принят» не заменяет EULA или устранение достижимого security риска.


## Точная привязка Intel, 8 сентября22:36UTC

[Intel OpenMP redist2025.3.0.640](https://www.nuget.org/packages/intelopenmp.redist.win/2025.3.0.640) опубликован Intel. Архив2155170B, SHA256a4212c4aec3e528864d56d8b0c87103cd5c21a888d1985124909a1f85624a449. DLL проверена только в памяти и совпала с установленной:1614192B, SHA256982233366b0afcda1e0f55a0b134097e35b779613f54ddb69e685e6cd06b755f. На диск сохранены только nuspec/license/notices и evidence; установка, LoadLibrary, EULA acceptance и изменение среды не выполнялись.

Exact license4090B SHA2566c00ae54b2a610ea009e0f5c5d3aa79023eb694c7fb72857654c53c6e99d7c97. Third-party-programs31578B SHA256f8ce918fe7311ce279e68380a2e233f8a42b1cd3dda8f4c48d6de97a0255c1d7: ITT/hwloc BSD3, SafeC MIT, Intel oneTBB simplified notice, LLVM Apache2 with LLVM exceptions и legacy notices. Отдельный Developer Tools EULA из общей PyPI metadata не подменяет лицензию byte-identical redist. Доказательства в [NATIVE-EVIDENCE.json](NATIVE-EVIDENCE.json); полные notices сохранены локально вместе с C6 рабочими материалами.

cuDNN EULA остаётся ожидающим решения владельца условием. Этот документ не является общим юридическим заключением, разрешением на передачу всей среды или подтверждением её runtime readiness.
