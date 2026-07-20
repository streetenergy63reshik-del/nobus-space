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
| [0007](adr/0007-reglament-rezervnogo-kopirovaniya.md) | Проверяемое резервное копирование и восстановление | ACCEPTED | TARGET |
| [0008](adr/0008-pravila-vneshney-zapisi.md) | Любое внешнее изменение требует связанного L4-подтверждения | ACCEPTED | PARTIAL |

## Правила статусов ADR

- `PROPOSED` — решение обсуждается и не является разрешением на реализацию или действие.
- `ACCEPTED` — решение обязательно для новой разработки.
- `SUPERSEDED` — заменено более новым ADR; старый файл сохраняется для истории.
- `REJECTED` — рассмотрено и не принято.

Статус реализации ведётся отдельно, потому что принятое решение может ещё не быть реализовано. Изменение статуса ADR требует даты, причины и независимого L2/L3 review. Высокорисковое решение дополнительно требует L4.
