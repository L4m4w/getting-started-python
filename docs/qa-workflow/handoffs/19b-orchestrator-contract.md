# 19B — handoff: контракт минимального оркестратора

Дата: 2026-11-15. **Статус: ready** — контракт подготовлен и ожидает
приёмки координатора. Код не реализован (это запрещено поручением 19B).

## Результат

- Дизайн-документ: [19-orchestrator-contract.md](../design/19-orchestrator-contract.md)
- Evidence: `artifacts/workflow-design/19b-20261115T124919Z/`
  (`state-valid.json`, `input-event.json`, `intent-record.json`,
  `invalid/*.json` ×5, `checks.txt`)

## Входы и версии

Прочитаны: AGENTS.md, `docs/plans/qa-workflow-mvp.md`,
`handoffs/coordination-wave-17.md`, `coordination-wave-18.md`,
`knowledge/integrations/testops.md`, `knowledge/testing/run-tests.md`,
`knowledge/components/README.md` + `infrastructure.md`,
`docs/qa-workflow/README.md`, `agent-tasks/README.md`,
`agent-tasks/19a-git-pr-preparation.md`, пилотные
`requirement.md`/`scenarios.md`/`context.json`/`testops-mapping.md`,
`tools/{harness,testops,java_evidence}.py`,
`infrastructure/reporting/testops/{state,lifecycle,results,rest,client,verification}.py`,
`tools/{git,gh,run-testops,_python}.sh`.

HEAD QA-репозитория: `c84483bf6647678d4052eb377e04a682cdaddd74`
(рабочее дерево с прежними незакоммиченными изменениями других работ —
не затрагивались). Приложение: `36674280b6878540a9e88f40aaeedf5dfdd2e6ce`.

SHA-256 ключевых входов зафиксированы в таблице совместимости §15
дизайн-документа.

## Содержание контракта (по пунктам поручения)

1. **Versioned state** (`workflow_schema_version: 1`): детерминированный
   `workflow_id` из стабильной идентичности (pilot+repo+base); head/patch/
   test digest — данные ревизии внутри workflow, новый head — ревизия,
   не новый workflow. `index.json` + `--supersede` блокируют обход
   журнала через новый ID. `kind: commit|patch|none` различает immutable
   head и dirty snapshot.
2. **Таблица переходов T1–T12** для цепочки `initialized → context_ready
   → scenarios_ready → awaiting_review → approved →
   implementation_ready → executed → published` с условиями приёмки,
   `stale`/`blocked`/`failed` и resume. Разделены TestOps published и
   PR pending (T11): launch 57317 не закрывает отсутствующий draft PR.
   Инвалидация по цепочке `depends_on` digest'ов — неизменившиеся входы
   сохраняют принятые результаты.
3. **CLI + adapters** (§6–§7): `sh tools/run-workflow.sh` с фиксированными
   действиями; адаптеры — тонкие обёртки над `run-tests.sh`,
   `run-java-test.sh`, `run-testops.sh`, git reads; `PrTransport` —
   только интерфейс + fake для тестов. Разделено: что исполняет
   оркестратор, что принимает как артефакты human/LLM, что блокируется
   без разрешения.
4. **Crash-safety**: `.tmp`+`replace`; `WorkflowLock` (тот же механизм
   `lifecycle.ExecutionLock`); порядок захвата workflow → execution;
   повреждённый state — жёсткая ошибка без перезаписи.
5. **Сквозная идемпотентность** (§9): intent на диск до внешнего вызова;
   read-only reconciliation после unknown; exactly-once не обещается —
   гарантия «не слепой повтор»; ключ поиска будущего PR (repo+branches+
   title_key+spec/head digest), неоднозначность → блок.
6. **Связь с TestOps** (§10): execution `state.json` — единственный
   источник жизненного цикла отправки; guards не обходятся;
   `import-execution` — read-only, `source: imported`.
7. **Матрица offline-проверок M1–M18** для задания 20 с fake transports
   и подсчётом вызовов; live PR criterion оставлен открытым.
8. **Файлы реализации** и порядок 20 → 21 → Git/PR → оценка; метрики —
   источники перечислены, `llm_cost: null` без реконструкции.

## Собственные проверки (offline)

- JSON-примеры: 8/8 валидны (включая намеренно невалидные по семантике
  схемы — они парсятся и отклоняются правилами).
- ```json блоки в дизайн-документе: 2/2 валидны.
- `git diff --check` по новому документу: exit 0.
- Относительные markdown-ссылки: 4/4 существуют.
- Скан на секреты: литералов токенов/паролей/DSN в новых файлах нет.

## Ограничения и открытые решения

- Контракт не проверен реализацией: все проверки статические, матрица
  §12 — план. Live PR и поведение поиска не проверялись.
- Решения, требующие координатора (с выбранным минимумом по умолчанию):
  состав `expected_executions` (нужен ли base-вариант обязательным),
  `require_pr` для фазы `published`, допустимый источник `actor`.
- Существующие executions/state/evidence не изменялись и не пересылались.
- Сеть, API/UI, Docker/Gradle, TestOps writes, commit/push/PR не
  выполнялись; секреты не читались.
- 19A работал параллельно; его файлы и общие индексы не редактировались.

## Критерии приёмки для координатора

- Схема §3 и пример `state-valid.json` покрывают требуемые поля поручения.
- Таблица §4 корректна для нового head (T8) и повтора входа (T9/T12).
- Разделение §5 и adapter-контракты §7 совместимы с текущими helpers (§15).
- Матрица §12 достаточна для meaningful offline tests задания 20.

## Следующий исполнитель

Поручение 20 (минимальная реализация + offline-тесты) — только после
документированной приёмки этого контракта координатором. Состав файлов —
§13 дизайн-документа.
