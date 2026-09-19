# M2-G4 — приёмка и выпуск MVP2

Готовый промпт одной задачи; ещё не запущен. Это не заранее данное разрешение
на внешнюю публикацию или live-переключение.

## Начало промпта

Выполни только M2-G4 Nobus Space: прими, опубликуй и активируй проверенный MVP2
в пределах получаемых в этой задаче точных разрешений. Один Gate = одна задача;
ожидание владельца, release и продолжение наблюдения остаются здесь.

Проект: канонический checkout репозитория `streetenergy63reshik-del/nobus-space`.
Прочитай AGENTS → docs/README.md → docs/handoffs/CURRENT-STATUS.md →
docs/15-Продуктовая-дорожная-карта.md → docs/mvp2/DOCUMENTATION.md →
docs/gates/mvp2/REGISTRY.md → docs/gates/mvp2/m2-g3/HANDOFF.md
и EVIDENCE.json того же Gate. Используй Nobus Memory только project:nobus-space.
Прими за вход точный результат предыдущего Gate, критерии G0 и применимые ADR.
Entry: M1-S1 закрыт, G0–G3 приняты, G3
candidate не изменён. Проверь Git status, exact remote/base/code/assets/config/
runtime inputs, сохранность пользовательского WIP и полноту checks.

Не повторяй успешные L1–L3 без нового основания. Если bytes/inputs/criteria
изменились, укажи точную дельту, обнови bindings и затронутые проверки; при
необходимости верни цельный candidate на rework в эту же задачу. Старый C6
не открывай. G4 проверяет готовность и effects этого выпуска, не копирует ритуалы.

### До любых внешних изменений

Подготовь owner-reviewable план:
- repo/branch/non-force semantics и exact candidate SHA/tree/assets;
- выбранный новый tag по фактическим refs, не автоматически v2.0.0;
- состав release note и docs-only publication, sanitation private evidence;
- текущий LIVE, StateRoot, config/Actions/inputs, backup и state watermark;
- before/after profile/menu/avatar изменения только выбранного бота;
- границы start/stop, бюджет запуска/model/ASR, окно наблюдения;
- пользовательские text/voice/clarify/reopen/result/TXT сценарии и устройства;
- совместимый rollback кода/config/assets/profile с сохранением новых данных.

Получай точное разрешение на каждый согласуемый пакет effects: push/PR/merge,
tag/release, deploy/службы, Bot API profile/menu, model/ASR/внешние сообщения.
Не считай текущий промпт или исторический C6 blanket authorization. Когда
владелец уже разрешил точный пакет в этой задаче, не спрашивай его повторно.
Не делай публикацию до завершения локальной подготовки и проверок.

### После разрешения

1. Зафиксируй свежий backup и baseline accepted tasks/receipts/offset. Новый
   запрос после планирования обновляет baseline; его не удаляют для сверки.
2. Выполни согласованную последовательность публикации и переключения,
   проверяя фактическое состояние после каждой внешней записи. Unknown outcome
   сначала readback; никаких blind repeats.
3. Один Core/Job/poller, accepted state/schema/config, local/public/stock
   readiness. UI/assets fingerprint должен соответствовать candidate отдельно
   от Python code digest; cache-busting и web response проверяются.
4. Реальный owner на iOS/Android Telegram выполняет согласованные сценарии:
   текст, voice preview до confirm без task, confirm/уточнение, повторное открытие,
   прежняя и новая последовательные задачи, copy и открытие правильного TXT.
   Запиши фактические файлы/digest без payload; недоступный clipboard readback
   не выдавай за побайтовую проверку. Device gap остаётся явным.
5. Проверь сохранность и backup/recovery только затронутого пути. Минимальное
   ограниченное наблюдение G4 и наследуемый M1-S1 stability receipt согласуй:
   визуальная правка не повод повторять 72 ч, если runtime inputs неизменны и
   evidence актуально; новая операционная дельта требует своей проверки.
6. Получи принятие владельцем точной версии и ограничений. После разрешённого
   release и docs merge прочитай remote SHA/tag; product tag не перемещай на
   более поздний docs-only commit. Установленный avatar/menu проверь readback.

### Условия финального PASS

M2-01…M2-10 закрыты проверяемыми данными либо точным заранее принятым изменением
критерия; нет скрытых Critical/Major/UNKNOWN effects. Действуют один Core,
прежняя security authority и реальные backend+frontend journeys. Published,
deployed и observed stable фиксируются раздельно; один HTTP 200 не product PASS.
Работающий ПК/сессия остаются принятым ограничением; always-on инфраструктуру
не добавляй. При blocking failure сохрани доказательства и безопасный статус,
не делай безусловный restart/restore или откат новых accepted данных.

Обнови на месте CURRENT, docs15/16 через renderer, REGISTRY, одну Word-памятку
и `m2-g4/HANDOFF.md`/`EVIDENCE.json`. Memory — только разрешённый короткий
source-backed managed handoff после verified outcome; не дублируй roadmap.
Финал должен содержать точные product/docs/LIVE refs, owner acceptance,
проверки/ограничения, runtime observation time и понятный пользовательский путь.
MVP3 остаётся отдельным решением; не запускай его.

## Конец промпта
