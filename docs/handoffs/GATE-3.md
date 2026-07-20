# Gate 3A — fake-only Codex CLI adapter

**Статус:** ACCEPTED — L1/L2/L3 PASS

**Дата:** 2026-07-20

## Scope

Добавлен изолированный adapter для будущего Codex CLI worker. В Gate 3A нет live `subprocess` implementation, запуска реального `codex`, сети, credentials, изменения runtime graph или внешних действий. Единственная точка запуска — обязательный injected async `ProcessSpawner`, поэтому тесты используют только fake process.

## Реализованный boundary

- executable задаётся абсолютным существующим файлом и передаётся spawner по точному resolved path; поиск через `PATH` отсутствует;
- argv выбирается только из двух фиксированных профилей: `read-only` и `workspace-write`; instruction не может добавить аргументы;
- все `allowed_paths` должны существовать и находиться внутри настроенного workspace; текущая попытка консервативно запускается в первом разрешённом каталоге;
- permission registry закрыт; `repo.read` и `process.run_allowlisted` обязательны, unknown, `artifact.write_allowlisted` до отдельного sandbox и любые `external.*` отклоняются;
- instruction и acceptance criteria передаются только как ограниченный UTF-8 JSON через stdin;
- environment строится с нуля из четырёх безопасных технических переменных; ambient secrets не наследуются;
- NUL и превышение prompt/output limits отклоняются до принятия результата;
- общий execution deadline ограничивает start + communicate; timeout и cancellation вызывают bounded cleanup (`kill` + ожидание `wait` в отдельном коротком grace period), после чего cancellation сохраняет семантику `CancelledError`;
- server-configured task timeout не может превышать 900 секунд; повторная cancellation не прерывает bounded cleanup drain;
- async spawner обязан иметь cancellation-safe `abort_start`, чтобы убрать частично созданный процесс до возврата handle;
- stdout принимается как закрытый JSONL: опциональные точные `{"type":"started"}` и ровно один terminal `agent_message` со `status="success"`;
- malformed/unknown/duplicate/missing terminal, non-zero exit и process errors дают стабильный безопасный код без stderr, exception text, secret или локального пути.
- публичные коды ограничены registry: `worker_configuration_invalid`, `worker_forbidden`, `worker_start_failed`, `worker_timeout`, `worker_failed`, `worker_protocol_error`, `worker_output_too_large`.

## Ограничения

- Это preview boundary, а не доказательство изоляции реального CLI. Live spawner должен отдельно обеспечить OS sandbox, bounded streaming и фактическое отсутствие сети.
- Дополнительные `allowed_paths` проверяются, но текущий профиль запускает worker только в первом каталоге. Поддержка нескольких writable roots откладывается до проверенного live sandbox adapter.
- Output protocol минимален и намеренно не совместим молча с неизвестными версиями Codex JSONL. Live интеграция потребует зафиксированной версии CLI, golden fixtures и compatibility tests.
- Adapter ещё не связан с Core attempt/lease/WorkerEvent и не создаёт verification evidence.

## Проверка

Проверки executor при `DEBUG=false`, bundled Python Codex и пакетах существующей `.venv`:

- target `tests/test_codex_cli.py`: `33 passed` после security rework;
- независимое воспроизведение target: `33 passed, 1 warning`; reviewer verdict `ACCEPTED — L2/L3 PASS`;
- полный suite: `152 passed, 1 warning`;
- ожидаемое предупреждение: `StarletteDeprecationWarning` от существующего FastAPI TestClient;
- real process, `codex`, сеть и credentials не запускались.

Acceptance относится только к fake-only boundary; live subprocess и OS sandbox не проверялись. Реальный process boundary остаётся отдельным Gate 3B и требует новой проверки; remote, сеть и `.nobus-quality` в Gate 3A не изменялись.
