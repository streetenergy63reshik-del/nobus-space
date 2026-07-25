# Журнал архитектурных решений

**Статус документа:** CANONICAL

Журнал содержит короткие ссылки на решения. Полный контекст и последствия находятся в соответствующем ADR.

| ADR | Решение | Статус решения | Реализация |
|---|---|---|---|
| [0001](adr/0001-platforma-zamenyaet-menedzhera-marketpleisa.md) | Платформа автоматизирует координацию, но человек сохраняет контроль высокорисковых действий | ACCEPTED | TARGET |
| [0002](adr/0002-determinirovannoe-yadro-smennye-llm.md) | Детерминированное Core и сменные workers | ACCEPTED | PARTIAL |
| [0003](adr/0003-kanal-prodazh-abstraktsiya.md) | Канал продаж — изолированный адаптер | ACCEPTED | TARGET |
| [0004](adr/0004-uchet-rashodov-prezhde-limitov.md) | Сначала учёт расходов, затем лимиты и блокировки | ACCEPTED | TARGET |
| [0005](adr/0005-agent-prompt-inzhener.md) | Доверенный intake формирует контракт до необязательного LLM-обогащения | ACCEPTED | TARGET |
| [0006](adr/0006-rezidentskie-proksi.md) | Доступ без официального API: residential proxies и обход защит запрещены; browser adapter — только после правовой/security проверки | PROPOSED | DEFERRED |
| [0007](adr/0007-reglament-rezervnogo-kopirovaniya.md) | Проверяемое резервное копирование и восстановление | ACCEPTED | CURRENT LOCAL |
| [0008](adr/0008-pravila-vneshney-zapisi.md) | Любое внешнее изменение требует связанного L4-подтверждения | ACCEPTED | CURRENT LOCAL |
| [0009](adr/0009-telegram-queue-sol-fast-timeouts.md) | Telegram intake отделён от длительного Codex execution; два read-only workers, Sol/High/Fast и трёхчасовой deadline | ACCEPTED | CURRENT LIVE |
| [0010](adr/0010-owner-library-read-scope.md) | Owner-bound worker читает библиотеку владельца отдельным permission без расширения write boundary | ACCEPTED | CURRENT LIVE |
| [0011](adr/0011-durable-owner-effects-and-web-profiles.md) | Durable Telegram admission, explicit owner effects и закрытые web/network profiles | ACCEPTED | CURRENT LIVE |

## Правила статусов ADR

- `PROPOSED` — решение обсуждается и не является разрешением на реализацию или действие.
- `ACCEPTED` — решение обязательно для новой разработки.
- `SUPERSEDED` — заменено более новым ADR; старый файл сохраняется для истории.
- `REJECTED` — рассмотрено и не принято.

Статус реализации ведётся отдельно, потому что принятое решение может ещё не быть реализовано. Изменение статуса ADR требует даты, причины и независимого L2/L3 review. Высокорисковое решение дополнительно требует L4.
