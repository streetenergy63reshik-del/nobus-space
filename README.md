# nobus-orchestrator-dev

Локальная песочница для разработки главного агента-оркестратора платформы **Space Nobus**.

Здесь создаётся ядро оркестратора и подчинённые агенты в изоляции от основного MVP (`space-nobus/`). После тестов код будет перенесён в основную платформу.

## Текущее состояние (сессия 2026-07-16)

Реализованы **Этап 1** и **Этап 2** общего плана:

- ✅ Ядро оркестратора (`NobusOrchestrator`, `Task`, `StateManager`).
- ✅ Правиловое распознавание намерений (`IntentParser`) с LLM-fallback под флагом.
- ✅ Маршрутизация задач (`TaskRouter`, `AgentRegistry`).
- ✅ LangGraph-граф (`src/orchestrator/graph.py`) — явные узлы и переходы.
- ✅ Ponytail-правила экономии токенов (`src/skills/ponytail_rules.py`).
- ✅ Память кодовой базы (`src/memory/codebase_memory.py`) — keyword/fuzzy поиск по `.py` файлам.
- ✅ Базовый `AuditAgent` (заглушка с рабочим интерфейсом).
- ✅ 25 юнит-тестов, все проходят.

## Структура

```
nobus-orchestrator-dev/
├── README.md
├── requirements.txt
├── src/
│   ├── config.py                # настройки (без секретов)
│   ├── models/
│   │   └── task.py              # модель задачи + статусы
│   ├── agents/
│   │   ├── base.py              # BaseAgent, AgentResult, AgentRegistry, PonytailMixin
│   │   └── audit_agent.py       # агент аудита маркетплейсов (заглушка)
│   ├── memory/
│   │   └── codebase_memory.py   # индексация и поиск по кодовой базе
│   ├── skills/
│   │   └── ponytail_rules.py    # правила экономии токенов
│   └── orchestrator/
│       ├── intent_parser.py     # распознавание намерений (rules + LLM fallback)
│       ├── router.py            # маршрутизация задач
│       ├── state_manager.py     # управление состоянием (in-memory)
│       ├── orchestrator.py      # главный агент
│       └── graph.py             # LangGraph-граф
└── tests/
    ├── test_orchestrator.py
    ├── test_graph.py
    ├── test_llm_fallback.py
    ├── test_ponytail_rules.py
    └── test_codebase_memory.py
```

## Установка и запуск тестов

```bash
cd nobus-orchestrator-dev
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest tests -v
```

Последний результат:

```text
25 passed in 0.50s
```

## Что работает сейчас

- `/audit ozon|wb` — создаёт задачу, маршрутизирует на `AuditAgent`, возвращает результат.
- `/help` — отвечает правилом Ponytail, без агентов и без LLM.
- `/status` — отвечает правилом Ponytail, без агентов и без LLM.
- Неизвестная команда — `FAILED` с пояснением.
- Распознанный интент без зарегистрированного агента — `FAILED`.
- LangGraph-граф проходит через узлы `parse → route → execute → respond` с условными ранними выходами.

## План на следующую сессию

1. **Этап 3: Human-in-the-loop**
   - Расширить `AgentResult` флагом `requires_input`.
   - Добавить узел `human_input_node` в граф.
   - Метод `NobusOrchestrator.provide_input(task_id, user_reply)`.
   - Тесты на диалог с уточнением.

2. **Этап 4: Zero-error layer / ensemble voting**
   - `EnsembleVoter`, `FactChecker`, `CircuitBreaker`.
   - Узел `verify_node` в графе.
   - Retry для внешних API.

3. **Этап 5: Voice адаптеры**
   - Абстракция `VoiceProvider`.
   - Stub-адаптеры LiveKit / Pipecat.

## Правила работы в папке

- Все секреты хранятся в `.env`, файл не коммитится.
- Код пишем на Python 3.12 с типизацией.
- Все асинхронные операции через `async`/`await`.
- Сначала тесты, потом перенос в основную платформу.
