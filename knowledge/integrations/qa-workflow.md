# QA workflow: локальный оркестратор этапов

GitHub transport и CLI wiring приняты как offline-реализация этапа 22:
[wave 31](../../docs/qa-workflow/handoffs/coordination-wave-31.md).
Реальные Git heads/PR и live repeat требуют отдельных разрешений.

Точка входа — `sh tools/run-workflow.sh <action> ...` → `tools/workflow.py`
+ `infrastructure.workflow`. Оркестратор — минимальный последовательный
исполнитель фиксированной цепочки MVP:

`initialized → context_ready → scenarios_ready → awaiting_review →
approved → implementation_ready → executed → published`

Это не планировщик и не LLM-фреймворк: каждый переход фиксируется в
versioned state, повтор любой операции идемпотентен или блокируется, а
все внешние эффекты проходят через intents + существующие CLI harness
и TestOps с их собственными `--execute`/`--online`/`--allow-sut` гейтами.

## Запуск: интерпретатор и глобальные флаги

`tools/run-workflow.sh` делегирует `tools/_python.sh`: интерпретатор
выбирается как `PYTHON` из окружения → `.venv/bin/python` → `python3`.
Голый `python3` без зависимостей падает с неочищенным ImportError, а не
с кодом 69 — для скриптов 19A закрепляй `PYTHON=.venv/bin/python` явно.

`--store-dir`, `--workflow-id` и `--pr-transport` — глобальные
аргументы, они стоят **до** subcommand:

```sh
sh tools/run-workflow.sh --store-dir artifacts/workflow \
  --workflow-id wf-17431cddc9919d3d status
```

- `--store-dir` — корень workflow-хранилища (default
  `artifacts/workflow`); все линии всех пилотов лежат в общем store.
- `--workflow-id` — целевая линия. Обязателен, когда в store больше
  одного `wf-*/state.json`: автоматического выбора «active» линии нет —
  разрешение сканирует директории store, а не `index.json`. Без флага
  любые `status`, `doctor`, `check`, `accept`, `resume`, `reconcile`,
  executions, TestOps и `pr` команды отвечают `BLOCKED: multiple
  workflows present; pass --workflow-id: […]` (exit 69).
- `--pr-transport {none,github}` — wiring PR-транспорта (default
  `none`; без транспорта `pr search`/`pr create` дают 77). `github`
  лениво подключает принятый stdlib GitHub REST transport
  (`infrastructure.workflow.github.GitHubPrTransport`) в обе PR-роли
  (`app`, `tests`) и только на командах, способных дойти до
  transport-вызова (`pr create`, `pr search`, `pr verify`,
  `reconcile`, `resume`):
  на `status`/`init`/`doctor`/`pr prepare` модуль даже не импортируется.
  Выбор транспорта сам по себе сеть не разрешает — HTTP выполняется
  только при `--online`, а POST — только при `--execute` + `--online` +
  действующие guard'ы; конструктор не делает I/O, а `GITHUB_TOKEN`
  читается провайдером только внутри авторизованного запроса.

Store с несколькими линиями возникает уже после первого `init
--supersede` (старая линия остаётся на диске) и при нескольких пилотах
в общем store. Примеры команд для такого store:

```sh
WF=wf-<new-lineage-id>
sh tools/run-workflow.sh --workflow-id $WF status
sh tools/run-workflow.sh --workflow-id $WF doctor
sh tools/run-workflow.sh --workflow-id $WF resume --online
sh tools/run-workflow.sh --workflow-id $WF accept context env/context.json
sh tools/run-workflow.sh --pr-transport github --workflow-id $WF pr search --repo app --online
sh tools/run-workflow.sh --pr-transport github --workflow-id $WF pr create --repo app --execute --online
```

`init` флаг `--workflow-id` не использует: линия выбирается записью
`repo_key + pilot_id` в `index.json` (active-запись после supersede
указывает на новую линию). Скрипты 19A в общем store обязаны передавать
`--workflow-id` явно — дословный runbook без него после supersede
блокируется на каждом шаге.

## Хранилище

- `artifacts/workflow/index.json` — единый журнал lineage
  `repo_key + pilot_id → workflow_id`; повторный `init` резюмит ту же
  линию, иной `app_base_sha` требует `--supersede` (связанная линия,
  `superseded` в index и `supersedes` в state). Superseded-линии не
  удаляются: после первого supersede в store уже несколько `wf-*`
  директорий и `--workflow-id` становится обязательным.
- `artifacts/workflow/<wf-id>/state.json` — schema-1 state: identity,
  revision_data + история ревизий, артефакты с bound-digest, executions
  (включая checkpoints подготовки TestOps), publications, intents, журнал
  аудита.
- `wf-id = wf-<sha256("wf-v1\0"+pilot+"\0"+repo_key+"\0"+base_sha)[:16]>` —
  вычисляется, произвольный ID задать нельзя.
- Lock'и: `workflow.lock` на директорию workflow, `index.lock` на
  `index.json` (оба поверх `ExecutionLock`: мёртвый pid освобождается,
  битый lock отклоняется). Порядок: index → workflow → делегированный
  execution; TestOps `ExecutionLock` оркестратор не берёт.

## Коды выхода

`0` ok/accepted/no-op; `2` usage-ошибка argparse; `69` blocked/validation/
corrupt/lock; `75` неопределённый внешний исход; `77` нужен явный флаг
разрешения; `127` делегированная команда не стартовала; `130` прерывание.

## Init и ревизии (T8/T9)

```sh
sh tools/run-workflow.sh init \
  --pilot-id category-update-validation \
  --app-repo https://github.com/L4m4w/niffler-py-st3 \
  --app-base-sha 36674280b6878540a9e88f40aaeedf5dfdd2e6ce \
  --app-patch-sha256 04eb4c87... \
  --tests-repo https://github.com/L4m4w/getting-started-python \
  --tests-commit <sha> --tests-clean \
  --requirements docs/qa-workflow/pilots/category-update-validation/requirement.md \
  --app-repo-path ../niffler-py-st3
```

Head формы: `--app-head-sha <sha>` (`kind=commit`), `--app-patch-sha256`
(`kind=patch`, dirty-снимок, не Git commit), `--proposed` (`kind=none`).
Новый head/patch/требования/tests snapshot при том же base — `revision+1`
и каскад stale зависимых артефактов; иной base — только через `--supersede`.
`--expect-head-passed N` / `--expect-base-failed N` переопределяют
execution-гейты ревизии (дефолты пилота: head — 6 passed, base — 4 ожидаемых
негативных failures).

`--tests-repo` — обязательный canonical remote тестового репозитория,
сохраняемый в `identity.tests_repo` **отдельно** от
`locals.tests_repo_path` (локальный checkout продолжает обслуживать
commit/dirty/tree gates). Значение нормализуется `normalize_repo_key`
(https/ssh/scp/`.git` spellings приняты, case owner/repo сохраняется) и
проверяется чистым строгим owner/repo-контрактом без HTTP/транспорта/
token reads: пустые segments, traversal, userinfo/query/fragment,
local/bare path и лишние segments отклоняются. Identity immutable: resume
с другим remote блокируется **до** записей state/index; `workflow_id` и
index key не зависят от `--tests-repo` (same repo + pilot + app base
сохраняют линию). State schema остаётся v1: `identity.tests_repo` —
опциональный ключ для чтения старых store, но если присутствует —
обязан быть валидным canonical remote (`None` не считается валидным
legacy key). Старый store без `identity.tests_repo` читается
status/doctor без миграции; новый init и `pr prepare --repo tests` на
нём дают 69 — backfill remote и fallback на local path отсутствуют.

## Accept артефактов через envelope

Артефакт принимается только как строгий JSON-envelope:

```json
{"envelope_version": 1, "artifact": "scenarios", "actor": "human",
 "version": "1", "document": {"path": "docs/.../scenarios.md",
 "sha256": "<64hex>"}, "payload": {"scenario_ids": ["CAT-UPD-VAL-001"],
 "requirement_coverage": {"R1": ["CAT-UPD-VAL-001"]}}}
```

`actor ∈ {human,llm,orchestrator,imported}`; `approved` — только явная
`payload.decision`, из actor не выводится. Payload по видам:

- `context`: `sources[] = {path, sha256, git_blob?}` — пересчитываются по
  app checkout (`--app-repo-path` при init).
- `scenarios`: `scenario_ids` + `requirement_coverage` — каждое требование
  покрыто, каждый сценарий привязан.
- `review`: `decision` + `scenarios_sha256` — обязан совпадать с frozen
  digest принятых сценариев.
- `implementation`: `test_files` под `tests/` — реальные compile + list
  через harness, node IDs должны покрывать сценарии.
- `bindings`: `mapping` scenario_id → TestOps ID (bijection), `source ∈
  {assign,resolve,imported}`; сверяется также с `ALLURE_ID` уже записанных
  executions текущей ревизии.

```sh
sh tools/run-workflow.sh accept context envelopes/context.json
sh tools/run-workflow.sh status
sh tools/run-workflow.sh check    # doctor + пересчёт digest + реальный compile/list
sh tools/run-workflow.sh doctor   # только чтение: index/state/preflight digest
```

`check` — не «лёгкая» проверка: кроме `doctor` и пересчёта digest он
делает реальный делегированный dispatch `sh tools/compile-tests.sh` и
`sh tools/run-tests.sh list`. State не записывается, но команда требует
живой venv/tools — это единственная операция на ранних фазах,
запускающая harness. `doctor` только читает и отчитывает проблемы
(index entry, state, preflight digest по документам/checkout); он не
выполняет dispatch и **не является полным реальным прохождением
цепочки** — целостность записей не доказывает live-выполнение этапов.

Повтор identical-envelope — `no-op` в любой фазе (без повторных
compile/list); конфликтный digest на той же ревизии — 69; пропуск фазы —
69.

## Preflight (единый, перед gate'ами/мутациями/эффектами)

Перед `accept`, `run-execution`, `import-execution`, `prepare-testops`,
`publish-testops`, `verify-testops` и `pr prepare/create` оркестратор
пересчитывает записанные digest: requirements doc, tests commit/dirty/
snapshot, документы принятых артефактов, context sources против app
checkout и `test_files_sha256` implementation. Дрейф — 69 до любого
эффекта; `doctor` показывает тот же список проблем read-only.

## Executions и контракты evidence (R1 + R3)

```sh
sh tools/run-workflow.sh run-execution --variant head [--allow-sut] [--rerun]
sh tools/run-workflow.sh import-execution run-XXXX [--provenance record.json]
```

`run-execution` делегирует `sh tools/run-tests.sh group api` через
зарегистрированный intent: evidence dir фиксируется до завершения pytest,
manifest schema-2 + пересчёт junit обязательны; satisfying execution той
же ревизии — `no-op` без `--rerun`; undetermined intent — повторный запуск
запрещён до reconcile. Run-args сверяются с записанной ревизией до
dispatch: head с patch требует base+patch, head с commit — точный head
SHA, противоречие — 69.

`import-execution` и adoption прогона проверяют точный контракт R1:

- `selection.targets` покрывает `tests/api`; `repository.commit`/`dirty`
  совпадают с ревизией (или принятым baseline acceptance record);
- `source_identity`: обязательная `contract_version = "api-contract-v1"`,
  полный уникальный набор `API_SOURCE_FILES` + принятые
  `implementation.test_files` без пропусков и посторонних путей, пустые
  списки `missing` и `changed_during_run`, заполненный `rechecked_at`,
  совпадение sha256 каждого файла с checkout и 1:1 копиями в `sources/`
  без незаписанных файлов;
- `environment`: соответствие ревизии (base+patch или commit head) и
  обязательный `container_check` при объявленном image/container;
- сценарии и результаты: точная 1:1 биекция JUnit и raw Allure
  (`infrastructure.reporting.testops.results`: `load_results`,
  `validate_attachments`, `scan_assignments` по `fullName` + `parameters`
  без зависимости от русского display `name`), соответствие варианту
  (`head` — 6 passed, `base` — 4 ожидаемых негативных `failed` у пилота,
  не `errors`/`broken`), совпадение статусов JUnit↔Allure и `ALLURE_ID`
  привязок.

Исторический baseline принимается через `--provenance <record.json>`
**только** для `variant = "base"` (никогда для `head`; `source_identity_missing`
запрещён). Запись обязана соответствовать `schema_version = 1`
(`kind = "historical_baseline_acceptance"`), входить в принятый
координатором реестр (`DEFAULT_ACCEPTED_HISTORICAL_BASELINES`), ссылаться
на существующие на диске документы ревью с совпадающими sha256 и точно
связывать `execution_id`, `manifest_sha256`, `junit_sha256`,
`allure_results_sha256` и `allowed_changed_files` (с одновременной
проверкой исторического sha256 в manifest и текущего sha256 в checkout).
Самостоятельно составленный payload по отклонённому manifest не проходит.

`import-execution` дополнительно принимает `--evidence-root <absolute
project root>`: evidence читается из `<root>/artifacts/harness/<id>` и
`<root>/artifacts/testops/<id>` внешнего исторического root. Флаг
разрешён только вместе с `--provenance` и фактически только для
accepted baseline (`variant = "base"`: head evidence по внешнему root
отклоняется до общих проверок). Resolved root обязан существовать,
находиться вне store dir и быть отделён от нового store — locks/tmp/
state/package writes в исторический root не выполняются. Containment:
resolved harness/testops директории и все используемые subpaths
(manifest/JUnit/Allure/copies, `results.path`, `package.dir`) обязаны
остаться внутри выбранного root; symlink escape и произвольные external
пути из записанного state отклоняются. Location сохраняется
типизированной записью per execution (`evidence_root`,
`testops_state_dir`) и используется restart/reimport/base-rebind
чтениями — директории выводятся из root + ID, а не принимаются от
caller. Reimport того же ID с иной location/provenance — контролируемый
конфликт **до** same-revision no-op; прежний безопасный no-op без
конфликтного входа сохраняется. Execution с external root read-only
навсегда: `prepare-testops`, `publish-testops`, `verify-testops` и
reconcile upload отказывают **до** делегированного subprocess даже если
его TestOps state неожиданно `sent`/`uploaded` (запрет не опирается на
pending status); observation/import/rebind читают state, а
head-публикация TestOps от base не перезаписывается.
Missing/corrupt/mismatch — отказ.

## Публикация и checkpoints TestOps (R4)

```sh
sh tools/run-workflow.sh prepare-testops --execution run-XXXX
sh tools/run-workflow.sh publish-testops --execution run-XXXX --execute
sh tools/run-workflow.sh verify-testops --execution run-XXXX --online
```

`prepare-testops` — локальная цепочка `plan → assign → package` с durable
checkpoints (`testops_prepare` на записи execution), привязанными к
`source_sha256`, `assignments_sha256` и `package_sha256`:

- повтор `prepare-testops` на уже подготовленном и целостном пакете
  возвращает `no-op` с **нулём** вызовов `run-testops.sh`;
- после сбоя повторяется только первый неподтверждённый шаг (`plan` и
  `assign` пропускаются, если их результаты в `state.json` валидны);
- потерянный save `workflow/state.json` после успешного делегированного
  шага восстанавливается чтением и верификацией `artifacts/testops/<id>/`
  (`verify_source_digest` + `verify_package`), без пересборки готового
  пакета;
- изменение локальных входов инвалидирует только невыполненную/устаревшую
  границу `pending` (`attempts = 0`, `launch = null`) подготовки; любой
  execution с начатой попыткой или публикацией (`in_progress`, `sent`,
  `uploaded`, `unknown`, `failed` с `attempts > 0` или записанным `launch`)
  строго неизменяем.

Перед dispatch upload выполняются `decide_upload` и полная верификация
собранного пакета. `verify-testops --online` возобновляет подтверждение
из durable `sent` без повторного upload; `uploaded` — `no-op`. Учитывай:
даже `no-op`-verify обновляет `last_observation.checked_at`/
`state_sha256` в `state.json` — повтор не бит-в-бит по файлу при
стабильных identity-digests (workflow id, revision_data, executions,
package/spec/state sha256).

## PR: разделение patch/dirty и immutable Git commit head (R2)

```sh
sh tools/run-workflow.sh pr prepare --repo app --title "..." \
  --head-branch wf/... --base-branch main [--files a,b] [--body file] \
  [--head-sha <commit_sha>]
sh tools/run-workflow.sh --pr-transport github pr search --repo app --online
sh tools/run-workflow.sh --pr-transport github pr create --repo app \
  --execute --online
sh tools/run-workflow.sh --pr-transport github pr verify --repo app --online
```

`spec.repo` роли `tests` — canonical `identity.tests_repo` из init
(локальный checkout path в spec не попадает); при отсутствии записанной
identity `pr prepare --repo tests` блокируется 69 до сборки spec.
Без `--pr-transport` (default `none`) `search`/`create` дают `77` —
транспорт не поставляется по умолчанию. `--pr-transport github` подключает
принятый в wave 30 `GitHubPrTransport` (22A+22AR) без изменений: repo
key строго канонический `github.com/owner/repo`, HTTP только на
`https://api.github.com`, `create` — ровно один POST без внутреннего
verification GET, `get` — строгий snapshot `detail → все страницы
files → повторный detail` (второй read обязан совпасть по всем полям,
а уникальных файлов — ровно `changed_files`). `--body <file>` остаётся
публичным флагом тела PR и передаётся в `body_path`: точные UTF-8 байты
фиксируются в durable snapshot внутри workflow dir и редоказываются
перед dispatch (digest без воспроизводимого текста блокирует create).
Идентичность PR head строго отделена от patch/dirty digest:

- при `app_head.kind = "patch"` (или `none`) и при `tests_repo.dirty = true`
  в `spec.head_sha` записывается `null` — это только локальный черновик
  (`status = "pending"`, `draft = true`); `pr create`, `verified` и фаза
  `published` заблокированы (`69`), даже если транспорт эхом вернёт
  patch digest;
- ни кандидат из ревизии, ни явный `--head-sha` не принимаются на веру:
  read-only `GitReadAdapter` проверяет, что SHA является существующим Git
  объектом типа `"commit"`, не равен `app_base_sha`, согласован с ревизией
  (`app_head.kind = "commit"` / `tests_repo.dirty = false`) и его дерево
  совпадает с принятыми файлами (`context.sources`, `API_SOURCE_FILES`,
  `implementation.test_files`, документы и diff `base..head`); иначе
  возвращается блокировка `69`;
- при unknown-диспатче `pr.create` пустой поиск никогда не переводит
  intent в retry-safe: intent со снимком spec остаётся unresolved и
  блокирует re-prepare/create в текущей и superseded линиях.

`pr verify --repo {app,tests} --online` — remote READ-ONLY
re-verification записанного PR на месте (39C/40): после revision bump
записанная публикация становится `blocked` с ревизионным маркером, и
ни `reconcile`, ни `pr create`, ни `pr prepare` не могут подтвердить
существующий remote-эффект без смены spec или ручной правки state.
`pr verify` проверяет freshness, текущую ревизию и фазу `executed`,
целостность записанной identity (`number`, `url`, `spec`/`spec_sha256`),
отсутствие unresolved own/inherited `pr.create` intents (единственная
допустимая причина `blocked` — ревизионный маркер) и только затем делает
единственный внешний вызов — targeted `get` по записанному номеру с
теми же commit/tree + body-integrity + exact-spec проверками против
текущей ревизии, что и при create. Полное совпадение → `verified` и
journal `pr-verify` текущей ревизии; доказанный 404, mismatch или
неполный snapshot → `blocked` (ложного `verified` после свежей
отрицательной проверки не остаётся); ошибка `get` → `unknown` (75):
`verified`-запись деградирует в `unknown`, а не остаётся подтверждённой,
и повторный verify может её редоказать. Нарушение локальной
целостности recorded identity/head/body на `verified`-записи снимает
claim до remote-вызова (`blocked` с причиной находки). При смене
статуса `refresh_phase` выполняется до сохранения: `published`
опускается до `executed`, когда обязательная публикация больше не
подтверждена. Отказ без `--online` или transport — не результат
проверки и записанное состояние не меняет.
`transport.create` и `search` не вызываются никогда — подменный номер
после 404 не ищется, resend невозможен; повторный verify выполняет
свежий targeted get.

## Восстановление

```sh
sh tools/run-workflow.sh reconcile [--online]
sh tools/run-workflow.sh resume [--online]
```

`reconcile` — разрешение незавершённых intents без повторных внешних
отправок: «read-only» относится к внешнему remote-эффекту (повторный
upload/create не выполняется), а не к собственному хранилищу — итог
разрешения сохраняется в `state.json` (adopted outcomes, обновлённый
`last_observation`, refresh фазы). Run с целым manifest усваивается
после полных проверок R1/R3, upload сверяется с execution state
(`uploaded`/`sent` — adopt, `pending` — retryable, прочее — kept),
`pr.create` — свежий поиск при `--online` по снимку spec из intent с
проверкой Git commit head + `pr_ref_exact` (точный match —
adopt+verified, ноль — unresolved/blocked, прочее — block); без
`--online` или без подключённого `--pr-transport` intent остаётся
`kept`. `resume` = `reconcile` + следующий шаг (тоже пишет state: фаза и
запись в журнал).
Повреждённый/чужой state не перезаписывается и не пересоздаётся —
только `69`.

## Контракт 21R и результат проверки

Раздел фиксирует обязательные решения
[независимого ревью 21](../../docs/qa-workflow/handoffs/21-independent-workflow-review.md).
Handoff 21R-A/B/C проверены координатором:
[wave 25](../../docs/qa-workflow/handoffs/coordination-wave-25.md).
A и документационная часть C приняты. Остальные пункты ниже подтверждены
на проверенных offline-путях; inherited guard закрыт 21R2
([handoff](../../docs/qa-workflow/handoffs/21r2-pr-lineage-deduplication.md)):
parent adopted → snapshot resolved → child больше не повторяет create —
записанный номер редоказывается targeted get до любого dispatch.
Общая offline-приёмка 21/21R/21R2 оформлена в
[wave 26](../../docs/qa-workflow/handoffs/coordination-wave-26.md).
Следующий этап — локальная актуализация Git/PR-пакетов, без разрешения
commit/push/PR. GitHub REST transport (22A/22AR) принят и подключается
только явным `--pr-transport github`; live-проверка против реального
GitHub по-прежнему не выполнялась.

- Обе PR-роли (`app`, `tests`) и публикация TestOps обязательны для
  `published`; `required` строго `true`, пустой/ослабленный набор ролей
  не допускает фазу `published` (21A F2 → 21R-A).
- `created`/неизвестный исход `pr.create` не разрешает повтор по пустому
  search или 404: при известном номере — targeted get + exact
  verification, иначе intent остаётся unresolved и блокирует create
  (21B F1 → 21R-B).
- Разрешение inherited intents из superseded-линии требует проверяемого
  parent evidence (identity/intent/spec/result старой линии); conflict —
  blocked, точный PR — adoption только после commit/tree/exact-spec
  проверок, без дублирования remote-эффекта. 21R2 реализовал durable
  guard: записанный в ancestry номер (`resolved_in_parent` и terminal
  `pr.create` с номером, наследуемые при supersede, включая two-hop
  цепочку `supersedes`) редоказывается targeted get к текущему spec до
  любого нового dispatch — пустой search, 404, несовместимый ref и
  ошибка get сохраняют blocked/unknown без автоматического recreate
  (21B F2 → 21R2).
- Base rebind после T8 — только после полной повторной source/scenario/
  provenance/environment проверки; re-import того же evidence не является
  no-op-привязкой к новой ревизии, head-execution не переиспользуется
  (21A F3 → 21R-B).
- Типы `expected_executions`/`strength_evidence`/`junit_summary`
  валидируются явно с чистым 69 вместо crash; `true`/`false` не является
  TestOps ID, допустимы только положительные int (21A F1/F5 → 21R-A).
- Lookalike node IDs не считаются покрытием сценариев — boundary-token
  matching вместо substring (21A F4 → 21R-B).
- Отсутствующий PR spec, исключения `search` и повреждённый TestOps
  state — контролируемые исходы без внешнего dispatch и без перезаписи
  чужого state. WorkflowBlockedError даёт 69; reconcile/resume могут
  вернуть exit 0 с report action=blocked/error — проверять report,
  а не только код процесса (21B F3–F5 → 21R-B).
- Наблюдение base-execution не перезаписывает подтверждённую
  head-публикацию TestOps (21B F6 → 21R-B).

Re-import записанного base после T8 возвращает `rebound` с
`bound_revision` текущей ревизии и audit-событием `base-rebind` после
полной проверки. Повтор в той же ревизии — `no-op`; head прежней
ревизии — `blocked`, без переиспользования старого head execution.


### Routing 33R: граница local checkout и external evidence

`--tests-repo` — обязательный remote identity input нового init; это не путь
локального checkout. Immutable conflict той же линии проверяется до index/
state writes, в том числе при concurrent init; gates/locks могут создаваться
в новом store. Старый store остаётся читаемым без миграции/backfill.

External baseline import использует `--evidence-root /abs/HIST` вместе с
`--provenance /abs/accepted-baseline-record.json`. Manifest containment
проверяется до JSON read, default/member paths — до чтения contents;
recorded root повторно проверяется при rebind/observe. External prepare/
publish/verify и upload reconcile не допускаются даже при sent/uploaded.
Исторический root должен оставаться без внешних writers во время операции:
check/read не является атомарным filesystem snapshot.

Для clean-head этапа не принимать старый run-ni_5bvnc как прогон новых commits.
Новый actual API run выполняется после final clean QA freeze по отдельному
разрешению; uploaded текущего head требуется для полного published.
Routing unit regressions не заменяют этот API/TestOps/live GitHub этап.
