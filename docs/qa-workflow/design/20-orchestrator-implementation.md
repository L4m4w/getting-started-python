# Реализация минимального оркестратора QA workflow (20)

Дата: 2026-11-15. Статус: реализовано и проверено offline (fake
transports/runner); live-операции не выполнялись. Основание:
[19B](../design/19-orchestrator-contract.md) с обязательными уточнениями
[wave 19](../handoffs/coordination-wave-19.md); поручение —
[20](../agent-tasks/20-orchestrator-implementation.md). Отличия от
иллюстративных примеров 19B документированы в §6.

## 1. Состав

| Модуль | Ответственность |
| --- | --- |
| `infrastructure/workflow/state.py` | schema-1 state, canonical digests, атомарные save/load, implied_phase, T8-каскад, intents, исключения |
| `infrastructure/workflow/index.py` | `artifacts/workflow/index.json`: lineage repo+pilot → workflow, register/mark_active, IndexLock-обёртка |
| `infrastructure/workflow/locks.py` | `WorkflowLock`, `IndexLock` поверх `ExecutionLock` (O_EXCL + мёртвый pid) |
| `infrastructure/workflow/envelopes.py` | Строгий envelope v1 + предметная валидация payload |
| `infrastructure/workflow/adapters.py` | Runner-протокол, `GitReadAdapter`, `HarnessAdapter`, `TestOpsAdapter`, `PrTransport`/`FakePrTransport`, evidence helpers |
| `infrastructure/workflow/orchestrator.py` | Фазы, accept, run/import/publish/reconcile/resume, PR spec/search/create |
| `tools/workflow.py`, `tools/run-workflow.sh` | CLI surface и shell-обёртка |
| `test_data/consts/workflow.py`, `test_data/utils/workflow.py` | Фиктивные входы и tmp-проект/FakeRunner для unit-тестов |

Отдельных модулей `gates.py`/`intents.py` нет: gate-логика — чистые функции
`implied_phase`/`executions_satisfy`/`publications_confirmed`/`artifact_fresh`
в `state.py`, жизненный цикл intent — там же; разделение по
ответственности сохранено без лишних файлов.

## 2. Схема `state.json` (workflow_schema_version: 1)

```jsonc
{
  "workflow_schema_version": 1,
  "workflow_id": "wf-<16hex>",          // вычисляется, не принимается
  "supersedes": null,                  // wf-id вытесненной линии
  "inherited_intents": [],             // unfinished intents superseded
  "created_at": "...", "updated_at": "...",
  "phase": "initialized",              // только выводимая фаза
  "phase_status": "active",            // active|blocked|failed
  "blocked_reason": null,
  "input": {
    "revision": 1,
    "identity": {"pilot_id": "...", "app_repo": "host/Path",
                 "app_base_sha": "<40hex>"},
    "locals": {"app_repo_path": "...", "tests_repo_path": "..."},
    "revision_data": {
      "app_head": {"kind": "patch", "sha256": "<64hex>", "git_sha": null},
      "tests_repo": {"commit": "<40hex>", "dirty": false,
                     "snapshot_sha256": null},
      "requirements": {"path": "...", "version": "1",
                       "sha256": "<64hex>", "ids": ["R1"]},
      "expected_executions": [{"variant": "head", "required": true,
        "scope": "api", "expect": {"total": 6, "passed": 6,
        "failed": 0, "errors": 0}}],
      "strength_evidence": {"variant": "base", "required": true,
        "scope": "api", "expect": {"total": 4, "failed": 4}}
    },
    "history": [{"revision": 1, "recorded_at": "...",
                 "revision_data_sha256": "<64hex>"}]
  },
  "artifacts": {"context|scenarios|review|implementation|bindings": {
    "status": "pending|accepted|stale", "artifact_digest": "<64hex>",
    "document": {"path": "...", "sha256": "<64hex>"},
    "actor": "human|llm|orchestrator|imported",
    "bound_revision": 1,
    "bound_input_digests": {"identity": "...", "app_head": "..."},
    "bound_artifact_digests": {"context": "..."},
    "depends_on": [...], "payload": {...}, "...": "kind-specific"}},
  "executions": [{"execution_id": "run-...", "variant": "base|head",
    "bound_revision": 1, "source": "orchestrated|imported",
    "evidence_dir": "...", "manifest_sha256": "...",
    "junit_summary": {...}, "exit_code": 0, "status": "completed",
    "selection": {...}, "testops_state_dir": "..."}],
  "publications": {
    "testops": {"required": true, "execution_id": null,
                "last_observation": null},
    "pr": {"app": {"required": true, "status": "pending|intent|created|
                   verified|unknown|blocked", "spec_sha256": null,
                   "spec": null, "intent_id": null, "number": null,
                   "url": null},
           "tests": { "...": "same shape" }}},
  "intents": [{"intent_id": "i-1", "operation": "run.execution|
    testops.upload|testops.verify|pr.create|pr.search",
    "target": {...}, "argv_digest": "<64hex>", "bound_revision": 1,
    "declared_at": "...", "dispatched_at": "...",
    "status": "declared|dispatched|completed|failed|unknown",
    "finished_at": null, "evidence": null}],
  "errors": [], "journal": [{"seq": 1, "at": "...", "actor": "...",
    "event": "...", "detail": "..."}],
  "metrics": {"llm_cost": null}
}
```

`validate_state` проверяет версию, домены, журнал seq без пропусков и —
ключевое — `phase == implied_phase(state)`: записанная фаза обязана быть
выводимой из артефактов/executions/publications. Заглушки вида
`state-valid.json` из 19B accepted-state не являются.

## 3. Фаза как функция состояния

```
context fresh → context_ready
scenarios fresh → awaiting_review
review fresh + decision==approved → approved
implementation fresh → implementation_ready
executions_satisfy (expected + strength по bound_revision/scope) → executed
publications_confirmed (testops uploaded на execution текущей ревизии +
verified PR при required) → published
```

Свежесть пересчитывается из `bound_input_digests`/`bound_artifact_digests`,
никогда не доверяется `bound_revision`. T8 (`apply_revision`) повышает
revision по diff digest входов, помечает несвежие артефакты `stale` и
блокирует PR-публикации прошлой ревизии.

## 4. Envelope v1 (валидный пример)

```jsonc
{"envelope_version": 1, "artifact": "review", "actor": "human",
 "version": "1",
 "document": {"path": "docs/qa-workflow/.../review.md",
              "sha256": "<64hex реального файла>"},
 "payload": {"decision": "approved",
             "scenarios_sha256": "<artifact_digest принятых scenarios>"}}
```

Невалидно (любое): `envelope_version` ≠ 1; `actor` вне домена; `document`
без `sha256` или digest не совпадает с файлом; payload без обязательных
ключей или с лишними; `sources[].path` абсолютный/`..`; `git_blob` не
40-hex; `decision` вне {approved,needs_decision,rejected};
`scenarios_sha256` ≠ frozen digest; `test_files` вне `tests/`;
`mapping` не биекция scenario_id → int. `approved` из `actor` не
выводится — только явный `payload.decision`.

## 5. Исполнение, публикация, PR

- **Run intent**: `declared → dispatched` сохраняется до subprocess;
  `Run evidence:` из stdout фиксирует evidence_dir до завершения pytest;
  принятие — только по manifest schema-2 + пересчёту junit; undetermined
  intent запрещает новый запуск до reconcile.
- **Upload intent**: перед dispatch — `decide_upload` по execution
  `state.json` (единственный источник статуса); после — verify и
  `last_observation`; crash после write даёт `unknown` + reconcile adopt.
- **PR**: без live-транспорта; spec + свежий поиск перед create;
  adopt при одном точном совпадении; unknown + zero search → blocked
  (не retry-safe; retry — явный re-prepare со своим поиском); неполные/
  чужие/множественные → blocked. `app` и `tests` — раздельные записи.

## 6. Решения по уточнениям wave 19

1. Примеры 19B — не accepted state: schema + implied_phase +
   строгие домены; placeholder-SHA (`0000`) отклоняются.
2. Index lock отдельный; index → workflow → delegated порядок; TestOps
   `ExecutionLock` не берётся; crash index↔state восстанавливает ту же
   линию (status creating + superseded).
3. `base` execution связывается по неизменному `identity.app_base_sha`
   (иначе strength-гейт недостижим при kind=patch) — уточнение привязки
   19B к базовому варианту.
4. `published` требует `uploaded` наблюдения execution текущей ревизии
   и verified PR — fake transport/один launch `published` не дают.
5. Unknown + zero search — blocked (не retry-safe), см. §5.
6. Импорт — read-only: digest источника/пакета проверяются, состояние
   принятого execution не мутируется (`source: imported`).
7. Произвольные argv из входов не исполняются: allowlist `sh tools/*`,
   без `shell=True`; runner инъецируется для offline-фейков.
