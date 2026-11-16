# Контракт минимального оркестратора QA workflow (19B)

Дата: 2026-11-15. Статус: предложение; реализация — только после приёмки
координатором (поручение 20). Код в этом документе не реализован.

Основание: [план MVP](../../plans/qa-workflow-mvp.md),
[wave 17](../handoffs/coordination-wave-17.md),
[wave 18](../handoffs/coordination-wave-18.md),
[runbook TestOps](../../../knowledge/integrations/testops.md).

## 1. Назначение и границы

Оркестратор — последовательный исполнитель фиксированного списка этапов
MVP с сохранением состояния, возобновлением и защитой от дублей. Он:

- исполняет программные шаги через существующие CLI (`tools/run-tests.sh`,
  `tools/run-testops.sh`, `tools/git.sh`, `tools/run-java-test.sh`) по
  явным контрактам §7 — не дублируя их логику;
- принимает результаты человеческих/LLM-этапов (контекст, сценарии,
  ревью, реализация тестов) как проверенные артефакты с зафиксированной
  идентичностью и происхождением (§5);
- блокирует внешние записи без явного разрешения (`--execute`/`--online`
  сохраняют семантику существующих CLI);
- не является универсальным scheduler или LLM-фреймворком: фазы,
  переходы и набор действий фиксированы этим контрактом.

Не входит: событийный обработчик реальных MR/PR (вход задаётся командой
`init`), автоматическое принятие ревью, слияние веток, автотономное
исправление падений. Реестр исторических Markdown-отчётов сам по себе
не является выполнением workflow: принятые артефакты регистрируются
явно через `accept` с digest-проверкой.

## 2. Идентичность: событие, вход, workflow ID

### 2.1 Стабильная идентичность lineage

`workflow_id` вычисляется детерминированно и никогда не принимается
извне:

```
workflow_id = "wf-" + sha256("wf-v1\0" + pilot_id + "\0" + repo_key + "\0" + base_sha)[..16]
```

- `pilot_id` — стабильный ключ линии изменения (`category-update-validation`;
  в будущем — MR/branch ref).
- `repo_key` — нормализованный репозиторий приложения (URL lowercase или
  абсолютный путь, без credentials).
- `base_sha` — базовый commit приложения (40–64 hex).

Head SHA, patch digest и тестовый SHA в `workflow_id` не входят: они —
данные ревизии внутри одного workflow. Новый head — новая ревизия того
же workflow с инвалидацией зависимых этапов, а не новый workflow.

### 2.2 Защита журнала от обхода

`artifacts/workflow/index.json` отображает `pilot_id → {workflow_id,
base_sha, latest_revision, updated_at}`. Повторный `init` с тем же
(pilot_id, repo_key, base_sha) возобновляет существующий workflow.
`init` с зарегистрированным pilot_id, но другим base_sha блокируется
(exit 69) без `--supersede`, который создаёт новый workflow с полем
`supersedes: <old_workflow_id>` и записью в журнале обоих workflow.
Случайный параллельный lineage без явной связи невозможен.

### 2.3 Событие и ревизия входа

Событие — экземпляр внешнего запуска (`init`): `{event_id, received_at,
payload_sha256}`, где `event_id` детерминирован от payload. Повторная
доставка того же события — идемпотентный resume.

Ревизия — версия изменяемых частей входа: `input.revision` начинается с 1
и увеличивается при несовпадении digest'ов ревизионных данных. История
ревизий сохраняется в `input.history` и журнале.

Различие immutable head и dirty snapshot фиксируется явно:

```json
{"app_head": {"kind": "patch", "sha256": "04eb4c87...", "git_sha": null}}
```

- `kind: "commit"` — immutable head; `git_sha` обязателен (40–64 hex).
- `kind: "patch"` — незакоммиченное изменение; `sha256` обязателен,
  `git_sha` обязан быть `null`. Dirty snapshot не выдаётся за immutable
  head: будущие commits не превращают старый прогон в новый.
- `kind: "none"` — head отсутствует (`proposed`); оба поля `null`.
  Текущее состояние пилота.

## 3. Схема состояния (`state.json`, `workflow_schema_version: 1`)

Один файл `artifacts/workflow/<workflow_id>/state.json` — единственное
версионируемое состояние (identity + progress). Атомарная запись:
`.tmp` + `replace`, как в `tools/harness.py:_write_manifest` и
`state.save_state`.

```json
{
  "workflow_schema_version": 1,
  "workflow_id": "wf-0123456789abcdef",
  "created_at": "<UTC ISO>",
  "updated_at": "<UTC ISO>",
  "phase": "implementation_ready",
  "phase_status": "active",
  "blocked_reason": null,
  "input": {
    "revision": 1,
    "identity": {
      "pilot_id": "category-update-validation",
      "app_repo": "https://github.com/L4m4w/niffler-py-st3",
      "app_base_sha": "36674280b6878540a9e88f40aaeedf5dfdd2e6ce"
    },
    "revision_data": {
      "app_head": {"kind": "patch", "sha256": "04eb4c87...", "git_sha": null},
      "tests_repo": {"commit": "c84483bf6647678d4052eb377e04a682cdaddd74",
                     "dirty": true, "snapshot_sha256": "..."},
      "requirements": {"path": "docs/qa-workflow/pilots/.../requirement.md",
                       "version": "1", "sha256": "...", "ids": ["R1","R2","R3","R4"]},
      "expected_executions": [{"variant": "head", "required": true}]
    },
    "history": [{"revision": 1, "recorded_at": "...", "revision_data_sha256": "..."}]
  },
  "artifacts": {
    "context": {"status": "accepted", "path": ".../context.json",
                "sha256": "59562d37...", "schema_version": 1,
                "actor": "human", "accepted_at": "...",
                "bound_revision": 1, "depends_on": ["app_head", "app_base_sha"]},
    "scenarios": {"status": "accepted", "path": ".../scenarios.md",
                  "sha256": "...", "version": "2", "actor": "llm",
                  "bound_revision": 1,
                  "depends_on": ["context", "requirements"],
                  "scenario_ids": ["CAT-UPD-VAL-001","...-006"]},
    "review": {"status": "accepted", "decision": "approved",
               "scenarios_sha256": "<digest accepted scenarios>",
               "artifact": {"path": ".../handoff", "sha256": "..."},
               "bound_revision": 1, "depends_on": ["scenarios"]},
    "implementation": {"status": "accepted",
                       "test_files_sha256": {"tests/api/test_category_update.py": "..."},
                       "checks": {"compile": {"run": "sh tools/compile-tests.sh", "exit_code": 0, "checked_at": "..."},
                                  "node_ids": ["tests/api/test_category_update.py::..."]},
                       "bound_revision": 1, "depends_on": ["review", "scenarios"]},
    "bindings": {"status": "accepted", "source": "assign|resolve|imported",
                 "mapping": {"CAT-UPD-VAL-001": 55376},
                 "bound_revision": 1, "depends_on": ["scenarios"]}
  },
  "executions": [
    {"execution_id": "run-ni_5bvnc", "variant": "head", "bound_revision": 1,
     "source": "orchestrated", "manifest_sha256": "32f1ec89...",
     "junit_summary": {"total": 6, "passed": 6, "failed": 0, "errors": 0, "skipped": 0},
     "exit_code": 0, "status": "completed", "recorded_at": "...",
     "testops_state_dir": "artifacts/testops/run-ni_5bvnc"}
  ],
  "publications": {
    "testops": {"execution_id": "run-ni_5bvnc", "required": true,
                "last_observation": {"upload_status": "uploaded",
                                     "checked_at": "...",
                                     "state_sha256": "7bec44e1..."}},
    "pr": {"status": "pending", "required": true, "repo": "tests|app",
           "title_key": null, "url": null, "number": null,
           "head_branch": null, "base_branch": null, "spec_sha256": null,
           "intent_id": null}
  },
  "intents": [
    {"intent_id": "i-1", "operation": "testops.upload",
     "target": {"execution": "run-ni_5bvnc"}, "argv_digest": "...",
     "declared_at": "...", "dispatched_at": "...",
     "status": "completed", "finished_at": "...",
     "evidence": {"exit_code": 0, "outcome": "sent"}}
  ],
  "errors": [{"at": "...", "stage": "run_execution", "kind": "exit_nonzero",
              "message": "<clipped>", "resolved": false}],
  "journal": [
    {"seq": 1, "at": "...", "actor": "orchestrator", "event": "init",
     "detail": "revision 1"},
    {"seq": 2, "at": "...", "actor": "orchestrator", "event": "accept",
     "detail": "context accepted sha256=59562d37..."}
  ]
}
```

Правила:

- `actor` в artifacts/intents — декларируемое поле (`human`, `llm`,
  `orchestrator`, `imported`), не проверяемая идентичность.
- `executions` append-only; запись не удаляется и не переписывается при
  смене ревизии — она перестаёт удовлетворять текущей ревизии, но остаётся
  в истории.
- `publications.testops` хранит только ссылку на execution и последнее
  наблюдение; источник истины — `state.json` самого execution (§10).
- `journal` — append-only аудит; ни одна операция не обходит его.

Невалидные примеры и граничные случаи — в
`artifacts/workflow-design/19b-*/invalid/`; неподдерживаемая
`workflow_schema_version`, head `"patch"` с заполненным `git_sha`,
статус вне перечня, пропуск фазы.

## 4. Фазы и переходы

Фазы MVP сохранены; добавлена стартовая `initialized` (до первого gate):

```
initialized → context_ready → scenarios_ready → awaiting_review
  → approved → implementation_ready → executed → published
```

`phase` = последний достигнутый gate. `phase_status`: `active`,
`blocked` (ждёт решения/разрешения, `blocked_reason` заполнен),
`failed` (ошибка этапа, есть нерешённый `errors[]`).

| # | Текущая фаза | Событие | Условие приёма | Результат |
| --- | --- | --- | --- | --- |
| T1 | initialized | `accept context` | digest+schema OK; git blob/sha256 файлов пересчитаны и совпали; `head.kind` валиден | → `context_ready` |
| T2 | context_ready | `accept scenarios` | schema OK; ID уникальны; покрыты все `requirements.ids`; digest зафиксирован | → `scenarios_ready` |
| T3 | scenarios_ready | авто | — | → `awaiting_review` (версия сценариев заморожена) |
| T4 | awaiting_review | `accept review` | `decision=approved`; `scenarios_sha256` совпадает с замороженным | → `approved` |
| T4b | awaiting_review | `accept review` | `decision` не approved | `phase_status=blocked`, остаётся awaiting_review; fix → новая версия сценариев через T2 |
| T5 | approved | `accept implementation` | файлы тестов существуют; `compile`/`list` exit 0; node IDs соответствуют сценариям | → `implementation_ready` |
| T5b | approved | `accept bindings` | все scenario→testops ID разрешены (`assign`/`resolve`/import); записано в execution state или artifacts.bindings | остаётся в approved; bindings — вход T5/T6 |
| T6 | implementation_ready | `run execution` | команда harness завершена; manifest+junit прочитаны; execution привязан к текущей ревизии; для `required` вариантов есть успешный прогон | → `executed` |
| T7 | executed | `publish` | все `required` публикации подтверждены: testops — execution state `uploaded`; pr — `verified` | → `published` |
| T8 | любая | `init`/`update-input` с новым head/patch/test-digest | — | `input.revision`+1; зависимые артефакты → `stale` по цепочке depends_on; фаза откатывается к первому затронутому gate; executions сохраняются как история |
| T9 | любая | повтор `init`/`accept` с неизменными digest | digest совпадает | no-op resume; фаза и принятые результаты сохранены |
| T10 | любая не-published | сбой шага | — | stage `failed`, `errors[]`, фаза не меняется; `resume` повторяет только этот шаг |
| T11 | executed | публикация частична (testops confirmed, pr pending) | — | фаза `executed`, `phase_status=blocked` по `pr`; launch не закрывает отсутствующий draft PR |
| T12 | published | любое событие кроме нового входа/чтения | — | терминально; повтор входа — no-op; новая ревизия → T8 |

`stale` — статус артефакта, не фазы: при T8 проверяется только цепочка
`depends_on` (digest-сравнение). Неизменившиеся digest сохраняют принятые
результаты: если новый head не меняет requirements и пересчитанный
context digest совпадает, сценарии/ревью остаются принятыми.

`resume` — общий механизм: каждая команда загружает state, вычисляет
текущий actionable шаг по таблице и выполняет ровно его. Пропуск фаз
запрещён: `accept implementation` до `approved` → exit 69.

## 5. Действия оркестратора vs принимаемые результаты

| Этап | Оркестратор выполняет | Принимает как артефакт человека/LLM | Сейчас блокирует без разрешения |
| --- | --- | --- | --- |
| context | Валидация схемы, пересчёт git blob/sha256 источников по репозиторию | Сам пакет контекста (состав источников) | — |
| scenarios | Проверка ID/покрытия требований, заморозка digest | scenarios.md, решение ревью | — |
| implementation | `compile-tests.sh`, `run-tests.sh list`, fingerprint файлов | Код тестов, patch, выбор компонентов | commit/push (нет) |
| bindings | `run-testops.sh assign/status` локально | Согласованные ID (ввод координатора) | `resolve --online` (сеть) |
| execution | Фиксированная команда `run-tests.sh`, чтение manifest/junit | Окружение (состав/health — артефакт preflight) | SUT-доступ: `--allow-sut`, env/creds |
| testops publish | `plan`/`package` локально; `upload`/`verify` через CLI с intent | — | `upload --execute`, `verify --online` |
| draft PR | Локальная сборка spec (title/body/files/digest) | Черновик title/body (пакет 19A) | push/create — нет разрешения и транспорта |

Оркестратор не производит контекст, сценарии, решение ревью и код тестов
сам — но и не считает Markdown-отчёт доказательством: каждый принятый
артефакт проходит digest/schema-проверку и привязку к ревизии.

## 6. CLI-контракт

Точка входа: `sh tools/run-workflow.sh <action>` → `tools/workflow.py`
(по образцу `run-testops.sh`/`_python.sh`).

```
init      --pilot-id P --app-repo R --app-base-sha SHA
          [--app-head-sha SHA | --app-patch-sha256 SHA | --proposed]
          --tests-commit SHA [--tests-snapshot-sha256 SHA]
          --requirements FILE [--requirements-version V] [--supersede]
status                                            # read-only, без lock
accept    context|scenarios|review|implementation|bindings FILE
          [--decision approved|needs_decision|rejected] [--actor human|llm]
check                                             # compile + node IDs + пересчёт digest контекста
run-execution --variant base|head [--app-base-sha ... --app-patch-sha256 ...
              --gateway-image-id ... --gateway-container ...]
              # требует --allow-sut у делегированной команды harness
import-execution EXECUTION_ID                     # read-only импорт (§10)
publish-testops --execution ID [--execute|--online ...]   # intent + делегирование
reconcile [--online]                              # read-only разбор intents unknown/declared
doctor                                            # целостность state, digest, журнала
pr prepare                                        # локальный spec; без записи
pr create --execute                               # заблокировано до разрешения+транспорта
pr search --online                                # read-only reconciliation ключа (§11)
```

Коды выхода согласованы с существующими CLI: `0` ok; `2` argparse;
`69` блокировка/противоречие/lock; `75` неопределённый внешний исход
или неполная проверка; `77` требуется разрешение/флаг; `127` процесс
не запустился; `130` прерывание.

## 7. Программные адаптеры

Все адаптеры — тонкие обёртки с внедряемым транспортом; внешние вызовы
не выполняются неявно (образец `lifecycle.py`).

| Адаптер | Контракт | Существующая основа |
| --- | --- | --- |
| `GitReadAdapter` | `repo_state(path) -> {commit, dirty}`, `hash_object`, `cat_file`, `bounded_diff` | `tools/harness.py:_git`, `_repository_state`, `_source_fingerprint` |
| `ContextValidator` | `verify(context_json, repo) -> problems` | пересчёт blob/sha256 из `context.json`; `API_SOURCE_FILES`-аналог |
| `HarnessAdapter` | `run(argv) -> {exit_code, evidence_dir, manifest_sha256, junit_summary}` | `sh tools/run-tests.sh`; manifest schema 2 (`tools/harness.py:run_with_evidence`) |
| `JavaEvidenceAdapter` | `run(options) -> {exit_code, evidence_dir, manifest_sha256}` | `sh tools/run-java-test.sh` → `tools/java_evidence.py` |
| `TestOpsAdapter` | `plan/status/assign/package/upload/verify` как subprocess; `read_execution_state(dir) -> state dict` | `tools/testops.py`; `state_mod.load_state`; `lifecycle.decide_upload` |
| `PrTransport` (протокол) | `search(key) -> list[PrRef]`, `create(spec) -> CommandResult`, `get(number) -> Pr` | новый интерфейс; live-реализация отсутствует и не требуется в 20 (offline fake); `tools/gh.sh` — только CI |
| `IndexStore` | `get/register/supersede` для `index.json` | новый, мелкий |

`TestOpsAdapter` никогда не вызывает `state_mod` для записи и не
обходит `decide_upload`/`_validate_upload_package`: внешние операции
идут только через `tools/testops.py` как процесс. Reconciliation —
`status` (чтение) + `verify --online` по разрешению.

## 8. Crash-safety, блокировки, повреждения

- **Запись**: `.tmp` + `os.replace` для `state.json` и `index.json`;
  частичная запись невозможна — при чтении либо валидный JSON, либо
  `WorkflowStateCorruptError` (аналог `state.StateCorruptError`,
  `load_state`), выход 69 без перезаписи.
- **WorkflowLock**: тот же механизм, что `lifecycle.ExecutionLock`
  (`O_CREAT|O_EXCL`, gate-файл, reclaim мёртвого pid), файл
  `workflow.lock` в каталоге workflow. Все мутирующие команды держат его
  на load → решение → действие → save. `status` — без lock (read-only;
  запись атомарна rename'ом). Reclaim мёртвого lock не обходит
  persisted `in_progress`/`unknown` intent — их разбирает `reconcile`.
- **Порядок блокировок**: workflow → execution. Оркестратор сам никогда
  не захватывает `ExecutionLock` для делегированных операций — его
  захватывает `tools/testops.py` внутри процесса. Для чтения execution
  state lock не нужен (rename-атомарность). Обратный порядок
  (execution → workflow) запрещён.
- **Конкурентный resume**: второй писатель получает `LockHeldError` →
  exit 69; журнал и state не смешиваются.
- **Повреждённый state/index**: жёсткая ошибка, не тихий новый state;
  восстановление — только оператором (аналог `resolve_in_progress`-
  философии: неизвестное внешнее состояние не переписывается автоматом).
- **Прерывание**: `KeyboardInterrupt` → intent помечается `unknown`,
  exit 130; внешняя запись могла состояться.

## 9. Сквозная идемпотентность

Intent фиксируется на диск **до** внешнего вызова; reconciliation после
неизвестного исхода — только read-only. Exactly-once без серверной
поддержки не обещается: гарантия — «не чаще одного подтверждённого
результата и никогда слепой повтор».

| Случай | Поведение |
| --- | --- |
| Повтор `init` (тот же вход) | Детерминированный `workflow_id` → resume; journal += `resumed`; ничего не сбрасывается |
| Повтор `accept` (тот же digest) | Идемпотентный no-op |
| `accept` конфликтующего артефакта на той же ревизии | Блок 69; замена только через новую ревизию (T8) |
| Новый head/patch digest | T8: revision+1, зависимые → stale, executions — история, журнал фиксирует причину |
| Сбой до TestOps write | intent `declared`/`dispatched` без записанного исхода; reconcile: state execution `pending` → повтор допустим |
| Сбой после TestOps write до local save | execution state сам фиксирует `in_progress`/`sent`/`unknown` до оркестратора; reconcile читает его → adopt результатов; повторный upload заблокирован guards (`decide_upload`) |
| `verify` inconclusive/partial/empty | status не `uploaded` → resend заблокирован; повторная verify/ручная сверка, не resend |
| Новый фактический прогон | новый `execution_id`; старый не перезаписывается; publish выбирает execution текущей ревизии |
| PR create: crash до вызова | intent `declared` → повтор разрешён после fresh `pr search` |
| PR create: crash после успеха до save | intent `unknown` → reconcile: `pr search` по ключу §11; 1 совпадение → adopt, ≥2/0-недоказуемо → blocked; повторный create без найденного/исключённого дубля запрещён |
| PR create: неизвестный исход сети | `unknown` → то же: search до любого retry |
| Обход execution guards | `publish-testops` проверяет `decide_upload` перед вызовом CLI; fake-transport тесты считают вызовы = 0 |
| `import-execution` | Регистрирует принятое evidence с `source: imported`; не является новой отправкой и не доказывает выполнение этапов оркестратором |

## 10. Связь с состояниями TestOps

`artifacts/testops/<execution>/state.json` (schema 2) остаётся
единственным источником жизненного цикла отправки:

- Оркестратор хранит в `publications.testops` лишь ссылку на execution и
  `last_observation` (кэш с `checked_at`/`state_sha256`). Gate
  «testops published» вычисляется чтением execution state:
  `upload.status == "uploaded"` (т.е. `confirmed` по runbook).
- `sent`, `unknown`, `in_progress`, `uploaded` запрещают resend — это
  гарантирует `decide_upload` внутри CLI; оркестратор дополнительно
  проверяет его перед постановкой intent и не выполняет повтор.
- Сбой TestOps не вызывает повтор API-прогона или перегенерацию тестов;
  новый прогон — только по явной команде как новый execution.
- `import-execution <id>` — read-only: читает manifest+junit и execution
  state, записывает execution в `executions[]` с `source: "imported"` и
  provenance. Для текущего пилота `run-ni_5bvnc` (`uploaded`, launch
  57317) удовлетворяет ветке testops publication при совпадении
  `bound_revision`/environment digest — но `published` фаза требует ещё
  PR (T11). Импорт не меняет и не пересылает исходный execution.

## 11. Будущий draft PR: ключ поиска и reconciliation

Записи `publications.pr` достаточно для моделирования до появления
транспорта. Ключ поиска (все условия обязательны):

- репозиторий (`app`/`tests`) — точное совпадение remote;
- `head_branch` и `base_branch` — согласованные ветки;
- `title_key` — детерминированная метка `[wf-<id>]` в заголовке;
- состав: `spec_sha256` (title/body/список файлов) и `head_sha`
  (если известен после push) сверяются у найденного PR.

Исходы поиска: `0` → create допустим только после повторного свежего
search непосредственно перед create; `1` с совпавшими полями → adopt;
`1` с расхождением или `≥2` → blocked 69. Устаревший локальный снимок
«PR нет» не доказывает безопасность create: проверка — live read-only
query в момент решения, доверенной локальной замены нет.

Статусы `pr`: `pending → intent → created → verified`; `unknown`
после нечитаемого/ненулевого исхода; `blocked` при неоднозначности.
`verified` требует `get(number)` с совпавшим ключом, а не exit 0
create. Текущий пилот: launch 57317 подтверждён, `pr.status=pending`,
поэтому workflow завершается не раньше `published` по T11 — launch не
закрывает отсутствующий draft PR.

## 12. Матрица offline-проверок реализации (задание 20)

Все проверки offline: fake transports с подсчётом вызовов; live PR
criterion остаётся открытым и mock его не закрывает.

| # | Проверка | Ожидание |
| --- | --- | --- |
| M1 | `init` ×2 одного входа | одинаковый `workflow_id`, один index, journal без дублей создания |
| M2 | `init` того же pilot_id с другим base | blocked 69; с `--supersede` — связанный новый workflow |
| M3 | `accept` повтор и конфликт digest | повтор no-op; конфликт 69 без перезаписи |
| M4 | Resume после сбоя/прерывания на каждом этапе | восстановление с последнего durable boundary; этапы не повторяются |
| M5 | Новый head: каскад stale | changed-only по depends_on; неизменные артефакты приняты |
| M6 | Corrupt state.json / index.json | `*CorruptError` → 69, файл не перезаписан |
| M7 | Неподдерживаемый `workflow_schema_version` | schema error → 69 |
| M8 | Конкуренция: два писателя | второй — `LockHeldError` 69; мёртвый lock — reclaim; in_progress intent не обойден |
| M9 | Crash после внешнего успеха до save (upload) | fake transport: 1 вызов; reconcile читает `sent`/`uploaded` из execution state; resend не вызван |
| M10 | Crash после PR create до save | fake transport create=1; search=1 совпадение → adopt; create повторно не вызван |
| M11 | PR search: 0/1-совпадение/1-расхождение/≥2 | create допустим/adopt/69/69 |
| M12 | Guards: execution `sent`/`unknown`/`in_progress`/`uploaded` | `publish-testops` блок до транспорта; счётчик вызовов upload = 0 |
| M13 | Сбой TestOps → повтор API/генерации | не вызываются; новый execution только явной командой |
| M14 | `import-execution` | исходный state байт-идентичен; запись `source: imported`; фаза не скачет в published без PR |
| M15 | Невалидные schema/JSON из `artifacts/workflow-design/19b-*/invalid/` | каждый отклонён с 69, без молчаливого восстановления |
| M16 | Пропуск фазы (`accept implementation` до `approved`) | 69 |
| M17 | Частичная запись state (kill в rename) | чтение даёт либо валидный прежний, либо corrupt → 69 |
| M18 | Повтор входа при `published` | no-op; intent/create/upload не вызываются |

## 13. Файлы реализации и порядок работ

Минимальный состав задания 20 (предложение; точные пути — по приёмке):

- `infrastructure/workflow/__init__.py`, `state.py` (schema/load/save/
  migrate/corrupt, journal, stale-каскад), `locks.py` (`WorkflowLock`,
  переиспользование `lifecycle.ExecutionLock`), `intents.py` (intent +
  reconciliation), `evaluate.py` (чистые gate-функции по §4),
  `adapters.py` (§7).
- `tools/workflow.py`, `tools/run-workflow.sh`.
- `tests/unit/test_workflow_state.py`, `test_workflow_gates.py`,
  `test_workflow_intents.py`, `test_workflow_orchestrator.py`
  (fake transports, M1–M18).
- `test_data/consts/workflow.py` — фиктивные входы/ожидания.
- Обновление каталога `knowledge/components/*` в том же изменении.

Порядок (по wave 18): **20** реализация+offline-тесты → **21**
независимое ревью и повтор того же входа с fake PR/TestOps (без новых
реальных прогонов) → актуализация Git/PR-пакета 19A новым кодом →
итоговая оценка MVP.

## 14. Метрики и источники затрат

| Метрика | Источник |
| --- | --- |
| Длительность этапов/ожидания ревью | timestamps `journal[]`, `accepted_at` |
| Число ручных правок/итераций ревью | количество `accept` с `actor`/`version` сценариев, `errors[]` |
| Попытки execution/upload | `executions[]`, `upload.history` execution state |
| Дубли кейсов/launch/PR | reconciliation + TestOps inventories (после live) |
| Токены/стоимость LLM | **нет локального источника** — поле `metrics.llm_cost: null`; не восстанавливается из предположений |

## 15. Совместимость с текущими helpers (SHA входов 2026-11-15)

| Контракт | Символ/файл | SHA-256 файла |
| --- | --- | --- |
| manifest запуска | `tools/harness.py` `run_with_evidence`, `API_SOURCE_FILES`, `_container_check` | `ed9058c7…` |
| TestOps CLI | `tools/testops.py` `cmd_*`, `_validate_upload_package`, `_guard` | `4111bf7e…` |
| execution state | `state.py` `load_state/save_state`, `SCHEMA_VERSION=2`, `expected_scenarios`, `decide` statuses | `55e132b2…` |
| lock + lifecycle | `lifecycle.py` `ExecutionLock`, `decide_upload`, `perform_upload`, `perform_verify`, `PHASE_*` | `a994e685…` |
| пакет/integrity | `results.py` `build_package_verified`, `verify_package`, `results_digest`, `scan_assignments` | `8a7e550f…` |
| REST verify | `verification.py` `perform_snapshot_verify`, `evaluate_snapshot`; `rest.py` `RestProbe.read_snapshot` | `4f175d4e…`, `82c08e5c…` |
| транспорт/парсинг | `client.py` `run`, `parse_launch*`, `*_args` | `07b38fdc…` |
| Java evidence | `tools/java_evidence.py` `run_with_evidence`, CLI flags | см. репозиторий |
| сценарные константы | `test_data/consts/category_update.py` | `c66a9a9f…` |

Изменение публичной семантики этих helpers при реализации запрещено;
расширения — только аддитивные.

## 16. Открытые решения (минимальный выбор сделан)

- **Формат артефактов**: scenarios/review — Markdown + digest;
  machine-readable `accept` берёт digest файла, JSON-схема обязательна
  только для context и intent.
- **`initialized` вместо пустого `context_ready`** — выбрано для
  однозначного старта; цепочка MVP не изменена.
- **ExecutionLock переиспользуется** для WorkflowLock (тот же каталоговый
  механизм), новых примитивов нет.
- **Resolve vs assign для bindings**: оркестратор принимает `assign`
  (согласованные ID) и `resolve --online`; выбор — координатора,
  оркестратор лишь фиксирует результат.
- Требуют решения координатора: состав `expected_executions` (нужен ли
  base-прогон в обязательном наборе), `require_pr` для `published`,
  допустимый источник `actor`.

## 17. Ограничения

Код не реализован; матрица §12 — план offline-проверок. Live PR и
поведение поиска/создания не проверены; серверной идемпотентности нет —
гарантия только «не слепой повтор». Существующие executions/state,
evidence и handoffs не изменялись. Секреты не читались; никаких сети,
API/UI, Docker/Gradle, TestOps writes, commit/push/PR не выполнялось.
