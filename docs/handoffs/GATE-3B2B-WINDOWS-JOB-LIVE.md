# Gate 3B.2b — локальный Windows Job live probe

**Статус:** ACCEPTED — L1/L2/L3/L4 PASS в ограниченном probe scope
**Дата:** 2026-07-22
**Implementation commit:** `6b0f923 fix: verify live Windows Job process cleanup`

## Граница проверки

По явному L4 владельца запущен только локальный allowlisted probe-child:

- без Telegram token, credentials, сети и внешних записей;
- без запуска Codex CLI;
- без установки зависимостей;
- во временном Git-ignored каталоге репозитория с обязательной очисткой;
- с exact argv/cwd/env/pipes, которые проверяет production process boundary.

Probe компилируется встроенным Windows .NET Framework `csc.exe`, создаёт одного descendant и проверяет его через retained process HANDLE и точный executable path.

## Найденные live-дефекты и исправления

Первый запуск fail-closed обнаружил race startup gate: parent закрывал последний HANDLE именованного event сразу после `SetEvent`, поэтому helper мог не успеть выполнить `OpenEventW`. Gate HANDLE теперь хранится вместе с Job ownership и закрывается только при normal reaper, tree kill или failure cleanup.

Второй запуск обнаружил Windows Proactor cycle: helper уже завершился, но `asyncio Process.wait()` ожидал EOF pipe, удерживаемого descendant; Job закрывался только после этого `wait()`. Reaper теперь ждёт публичный `process.returncode`, закрывает Job после фактического завершения helper и тем самым освобождает pipe EOF.

Regression проверяет, что Job и gate закрываются после появления `returncode`, даже если имитация pipe EOF ещё не наступила.

## Воспроизводимые доказательства

```text
Offline target: 17 passed
Full repository: 534 passed, 1 warning
py_compile + csc: PASS
git diff --check: PASS

Main live run:
  normal exit:       rc=0, stdio PASS, descendant alive-before/dead-after
  explicit tree kill: rc=125, stdio PASS, descendant alive-before/dead-after
  adapter cancel:    cancellation propagated, descendant alive-before/dead-after

Independent live reproduction:
  exact runner exit code: 0
  status: PASS
  all three scenarios: PASS
  post-run probe/helper processes: 0
  post-run tmp directory: absent
```

Команда воспроизведения после отдельного L4:

```powershell
.\.venv\Scripts\python.exe scripts\live_windows_job_probe.py --json
```

Независимое ревью дважды отклоняло harness до live-запуска: были закрыты false-dead WinAPI semantics, PID reuse, unchecked HANDLE cleanup и отсутствие реального adapter cancellation scenario. Финальная ревизия и независимый live-run — `ACCEPTED`.

## Что не доказано

- реальный `codex` не запускался;
- эффективность или безопасность Codex sandbox не проверялась;
- Telegram Bot API, token, polling и status delivery не активировались;
- production deployment, monitoring и restore drill отсутствуют;
- этот probe подтверждает Windows Job inheritance/stdio/tree cleanup/cancellation, но не завершает весь live Gate 3B.2.

Следующий шаг требует отдельного L4 на один минимальный read-only Codex process и отдельного L4 на Telegram identity/network boundary.
