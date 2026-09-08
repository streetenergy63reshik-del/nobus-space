# Gate C5 — приёмка

**ACCEPTED / PASS / PUBLISHED.** Проверен исходный код `9efad0f2eb152ff71ec684786c07ad38c906db1b`, tree `2e31c2f2e6dd72585c9e3a794f7ee8ec7475d78c`. Acceptance package `e7efeaaadb2006e204ff3fea1b27b15128d39acf`, tree `f44ea1d24726c7f1608da1da520b514bc1c7e2b3` опубликован обычным [PR19](https://github.com/streetenergy63reshik-del/nobus-space/pull/19). Merge `efff730b9caeceae0afdaff840c5082d818c84d5` имеет то же дерево; прочитанные56 файлов совпали с пакетом. [Publication readback](PUBLICATION-READBACK.json). MVP1 NOT READY; постоянная активация относится к отдельному C6.

## Связанные доказательства

[Единый manifest](EVIDENCE.json) связывает источник, application/schema, памятку и receipts. [L1](VERIFICATION.json): 2305 PASS и 25 subtests, 20 Node PASS, compile 97, pip check, PowerShell parse, пять CLI help, diff, ссылки и фиксированный secret-pattern scan PASS. Два Windows symlink SKIP, два прежних historical deselect и одно предупреждение Starlette сохранены; новых исключений нет. Отсутствие совпадений новых шаблонов не означает исчерпывающего поиска секретов.

Независимый [L2](L2.json): 82 теста, три настоящих disposable drill и четыре исхода generated Health PASS; все шесть страниц памятки просмотрены. Независимый [L3](L3.json): 22 проверки, включая реальные redirect, chunked/DNS/STOP, настоящий Sender в пустом runtime root, restore journal и ingress. Авторы не выдают решение по собственным файлам; scope и hashes перечислены в receipts. Открытых Critical/Major/Minor в проверенной области — 0.

Первый `29d09d6` остался REWORK: 2296 PASS / 1 устаревшее ожидание схемы, три Major runtime и два Minor документации. [История](REWORK.json) и авторские receipts сохраняют исходные FAIL и ошибки verifier. Исправленный источник проверен заново; старые измерения не переименованы.

## Результат A–F

- **A:** single-instance и lease fencing; дети входят в собственный Windows Job до запуска; graceful stop и Job0; конечные повторы; реальный isolated ON/OFF. Readiness без redirects, caller deadline2/5с, единственный daemon slot, STOP и отказ от позднего PASS.
- **B:** exact Host/Origin, подпись/replay/expiry, безопасные headers/cache; 16 connections, 8 requests, bounded headers/body/query/response, budgets и UNKNOWN после timeout. Проверки на loopback; действующая внешняя TLS/edge policy не изменена.
- **C:** три обязательные БД и существующая legacy-БД, WAL snapshot, authenticated DPAPI manifest, code/schema/target binding, staged restore и crash journal/rollback. Старые сессии/подтверждения инвалидируются; admission остаётся закрыт до reconciliation, новые effects не откатываются.
- **D:** точные ownership/path/reparse/hardlink проверки; видимая ошибка cleanup; tombstones сохраняются; рабочая retention только [dry-run](RETENTION-DRY-RUN.json).
- **E:** изоляция, redaction, UNKNOWN и запрет повторов не ослаблены. [Зависимости](DEPENDENCIES.md): фактические версии, 79 компонентов closure, 174 уникальных native файла, официальные источники и незакрытые ограничения.
- **F:** актуализированы README, CURRENT/index/issues и [Runbook](../../08-Runbook-эксплуатации.md); изменён тот же DOCX. SHA-256 `36fe554b9b7b0f327fecc7c22fecb5cc5241528267880ffdb4f5dad92433e2fc`, 44591 байт, 6 страниц. [Manifest памятки](MANUAL.json) сохраняет исходник, последовательные правки, Word render и QA.

## Измерения и принятые нормы

Final application digest: `sha256:d5b72e7fafedecb643a55892491813ed6746c57f0968d12a901f42afaa14f504`. Измерения source`9efad0f2eb152ff71ec684786c07ad38c906db1b`:

| Проверка | Секунды |
|---|---:|
| Backup | 0,537000 |
| Restore и проверка данных | 0,687975 |
| Возраст snapshot при имитированном отказе | 0,342264 |
| Исключение при установке и rollback | 0,807785 |
| Запуск и аварийная остановка процесса | 1,668171 |
| Recovery journal на следующем запуске | 0,067990 |

Потери принятых записей и повтор подтверждённых частей — 0; после аварийного сценария Job0. Это восстановление данных, полный запуск SDK/ASR не измерен. Владелец принял RPO ≤24 ч, полный RTO ≤30 мин, backup ежедневно и перед изменениями, хранение 7 ежедневных и 4 еженедельных копий. Расписание не включено, рабочие копии не удалены; потеря диска того же ПК не покрыта.

## Ограничения и C6

[EVIDENCE](EVIDENCE.json) задаёт влияние, временные меры и владельца для C5-R1–R5: полный RTO/расписание; копии на том же ПК; предел48МиБ на БД и disk pressure; native/pip/SQLite conditions; фактическая edge/runtime activation. Эти условия нельзя объявлять выполненными по source merge. Установки, binary distribution и новые модели в C5 отсутствуют.

Live window **NOT RUN**. [Конечное чтение](RUNTIME-READBACK.json): оба задания Disabled, процессов0, port8765 свободен, прямой HTTPS readyz502. Начальный preflight403 сохранён как более раннее наблюдение; памятка указывает именно этот preflight. Код и тесты не запускали production. [Сохранность](PRESERVATION.json): canonical20dirty paths, live/C4 checkout,19 прежних worktree identities и6 recovery refs сохранены.

Обычные push/PR/merge после PASS разрешены контрактом задачи. Protection не обходится; пустой список CI не является CI PASS. Публикация подтверждена [отдельным readback](PUBLICATION-READBACK.json) с package/merge SHA/tree; это единственное документальное уточнение после PR19. Для C6 нужны отдельное поручение, exact active profile и owner binding, совместимые данные и сверка restore hold, полный RTO и реальные пользовательские journeys. C6, постоянный deploy и tag/release здесь не выполняются.
