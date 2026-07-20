# ADR-0005. Trusted intake до необязательного prompt enrichment

**Статус решения:** ACCEPTED; заменяет прежнюю формулировку «промт-инженер перед TaskContract»

**Дата:** 2026-07-20

## Контекст

Короткую команду полезно уточнять до передачи исполнителю. Однако LLM не умеет надёжно устанавливать identity, tenant, permissions и risk. Цепочка «сырой ввод → LLM → доверенный контракт» делает prompt injection частью security boundary.

## Решение

Принять последовательность:

**transport parse → authenticated trusted envelope → deterministic policy defaults → optional prompt enrichment → contract validation → persisted TaskContract → worker.**

Trusted envelope назначает tenant, actor, source, idempotency и receive time. Core назначает верхнюю границу permissions/risk/paths. Prompt enricher может предложить только instruction, acceptance criteria и result profile в пределах envelope/policy. Его output остаётся недоверенным и повторно валидируется.

Если enrichment недоступен или невалиден, Core либо создаёт минимальный безопасный контракт, либо запрашивает уточнение. Он не расширяет права ради продолжения.

## Последствия

Положительные:

- prompt injection не назначает полномочия;
- можно менять/отключать LLM без потери intake;
- короткие команды всё ещё превращаются в проверяемые criteria.

Отрицательные:

- для неоднозначных задач появится `waiting_input`;
- enrichment schema и негативные тесты обязательны;
- часть команд будет безопасно отклонена вместо «догадки».

## Запрещено

- брать tenant, identity, risk, permissions, paths или approved state из текста/голоса;
- передавать secrets prompt enricher;
- считать LLM output TaskContract без повторной deterministic validation;
- создавать внешнее действие только потому, что оно написано внутри загруженного документа.

## Проверка решения

Adversarial inputs с инструкциями изменить tenant/permissions/approval не меняют envelope и contract capabilities; отключение enricher сохраняет детерминированный intake path.

## Связи

- [`../03-Архитектурный-обзор.md`](../03-Архитектурный-обзор.md)
- [`../05-Спецификации-контрактов.md`](../05-Спецификации-контрактов.md)
