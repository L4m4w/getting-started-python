# 20 — handoff: минимальный оркестратор и offline-проверки

Дата: 2026-11-15. **Статус: ready** — реализация выполнена и проверена
только offline (fake runner/transports, tmp dirs). Live API/UI/SUT,
Docker/Gradle, CI, сеть, TestOps-публикации, commit/push/PR не
выполнялись. Полный MVP завершённым не объявляется: драфт PR,
live TestOps-цепочка и поручение 21 остаются впереди.

## Результат

- Реализация: `infrastructure/workflow/` (state/index/locks/envelopes/
  adapters/orchestrator), `tools/workflow.py`, `tools/run-workflow.sh`.
- Дизайн-документ: [20-orchestrator-implementation.md](../design/20-orchestrator-implementation.md)
  (актуальная schema-1, envelope-формат, решения по wave 19).
- Runbook: `knowledge/integrations/qa-workflow.md`; каталог:
  `knowledge/components/workflow.md` (+ обновлены README, infrastructure.md,
  consts.md).
- Evidence реализации: `artifacts/workflow-implementation/20-20261115T182635Z/`
  (`commands.txt` с exit codes, `historical-sha.txt`).
- Рабочий workflow state пилота: `artifacts/workflow/index.json` +
  `artifacts/workflow/wf-17431cddc9919d3d/state.json` — создан реальным
  `init` (только чтение git/файлов), фаза `initialized`, повторный init
  дал `resumed`.
- Unit evidence прогона harness: `artifacts/harness/run-1nfhtki7/`
  (314 passed), targeted pytest: 81 passed.

## Входы и версии

- QA HEAD на момент поручения: `c84483bf6647678d4052eb377e04a682cdaddd74`
  (рабочее дерево содержит прежние незакоммиченные изменения — сохранены).
- Приложение (read-only): `niffler-py-st3`,
  base `36674280b6878540a9e88f40aaeedf5dfdd2e6ce`,
  patch SHA-256 `04eb4c874139610869793f0c72843b1a9cb338832973697cf56e25b7ba87937e`.
- Принятые документы: wave 19 (`coordination-wave-19.md`), контракт 19
  (`design/19-orchestrator-contract.md`), handoffs 19A/19B, wave 17,
  `knowledge/integrations/testops.md`, `.agents/skills/run-tests/SKILL.md`.
- Историческое accepted evidence `run-ni_5bvnc` / launch 57317 —
  SHA-256 state/log до и после идентичны (см. evidence), не читалось как
  вход и не мутировалось.

## Что реализовано (по пунктам поручения)

1. **CLI**: `init/status/accept/check/run-execution/import-execution/
   publish-testops/reconcile/resume/doctor/pr prepare|create|search`.
   Exit codes: 0/2/69/75/77/127/130. `workflow_id` вычисляется, не
   принимается; повторный `init` — `resumed` без reset; иной `base_sha`
   под тем же repo+pilot — 69 без `--supersede`; supersede создаёт
   связанную линию (`supersedes` + `superseded` в index) без обхода
   журнала.
2. **Строгая валидация**: schema-1 с доменами и `phase == implied_phase`
   (записанная фаза выводится из артефактов/executions/publications);
   placeholder-SHA (`0000`), kind=patch+git_sha, пропуск фазы в state,
   ложный `published` отклоняются; corrupt/unsupported state — жёсткая
   ошибка, файл байт-в-байт неизменён. Envelope v1: document digest по
   файлу, actor ∈ {human,llm,orchestrator,imported}, `approved` — только
   явный `payload.decision`, `scenarios_sha256` ревью сверяется с frozen
   digest.
3. **Index/state**: `WorkflowLock`/`IndexLock` поверх `ExecutionLock`;
   порядок index → workflow → delegated; запись tmp+fsync+replace+
   dir-sync; crash между index и state восстанавливает ту же линию
   (creating + superseded), незавершённые intents superseded линии
   наследуются и блокируют соответствующий PR-entry.
4. **Делегирование**: compile/list/run через `tools/compile-tests.sh`,
   `tools/run-tests.sh`; TestOps через `tools/run-testops.sh`; argv —
   фиксированный allowlist `sh tools/*` без `shell=True`; runner
   инъецируется (SubprocessRunner в CLI, FakeRunner в тестах).
   `Run evidence:` фиксируется до завершения pytest; принятие — manifest
   schema-2 + независимый пересчёт junit; unit-прогон не удовлетворяет
   api-gate.
5. **TestOps**: execution `state.json` — источник истины;
   `decide_upload` перед любым transport; sent/unknown/in_progress/
   uploaded → 69 до dispatch; intent declared→dispatched сохраняется до
   вызова; reconcile read-only (uploaded/sent — adopt, pending —
   retryable, прочее — kept). Импорт — read-only: manifest/junit
   пересчёт, при uploaded — verify source/package digest;
   `source: imported`, bound_revision по app_base_sha/patch.
6. **PR**: `PrTransport` (search/create/get) + `FakePrTransport`;
   live-транспорта нет — `search`/`create` в CLI дают 77. Spec digest,
   search key = repo+branches+`[wf-<id>]`+head_sha; свежий поиск перед
   create; один точный match — adopt; unknown + zero → **blocked**
   (не retry-safe; retry — явный re-prepare со своим свежим поиском);
   incomplete/foreign/mismatch/multiple → block. `app` и `tests` —
   раздельные записи.
7. **Каталог/runbook/схема**: `knowledge/components/workflow.md`,
   `knowledge/integrations/qa-workflow.md`,
   `docs/qa-workflow/design/20-orchestrator-implementation.md`.

## Решения по уточнениям wave 19 (расхождения с 19B)

- Примеры 19B не использованы как accepted state: введена строгая
  schema-валидация + выводимая фаза.
- **Base-execution привязывается по `identity.app_base_sha`** — при
  kind=patch иначе strength-гейт недостижим (19B привязывал run только к
  head); head — по patch/head SHA манифеста.
- **Unknown + zero search → blocked**, не retry-safe (поручение п.6);
  retry только через явный re-prepare.
- `bound_revision` никогда не доверяется: свежесть — пересчёт bound
  digests; execution связывается с ревизией по declared environment
  manifest, а не по «последнему каталогу».
- Plan/assign/package остаются делегированными шагами `run-testops.sh`:
  `publish-testops` покрывает upload+verify поверх существующего
  execution state (гарды до транспорта); полная оркестровка plan→verify —
  будущая работа (см. «непроверенное»).
- `gates.py`/`intents.py` отдельными файлами не созданы: gate-логика —
  чистые функции `state.py` (`implied_phase`, `executions_satisfy`,
  `publications_confirmed`, `artifact_fresh`), intent-жизненный цикл —
  там же; разделение ответственности сохранено.

## Команды и exit codes

| Команда | Exit | Результат |
| --- | --- | --- |
| `sh tools/versions.sh` | 0 | Python 3.13.15, pins совпадают |
| `sh tools/compile-tests.sh` | 0 | 329 collected |
| targeted `pytest tests/unit/test_workflow*.py -x -q` | 0 | **81 passed** |
| `sh tools/run-tests.sh group unit` | 0 | **314 passed** (включая 81 workflow), evidence `run-1nfhtki7` |
| `git diff --check` | 0 | чисто |
| Markdown-link check новых документов | 0 | все ссылки валидны |
| `run-workflow.sh status` (до init) | 69 | `no workflow found` |
| `run-workflow.sh init ...` (пилот) | 0 | `wf-17431cddc9919d3d` created |
| `run-workflow.sh init` повтор | 0 | `resumed`, тот же ID |
| `run-workflow.sh doctor` | 0 | problems: [] |
| `run-workflow.sh resume` | 0 | next_step: accept context |

SHA-256 `run-ni_5bvnc`: state `7bec44e1…`, upload.log `0f40d658…` —
идентичны до и после (полные значения в evidence).

## Покрытие M-сценариев (78+3 теста, fake transports/runner, tmp dirs)

- M1/M2 повтор/конфликт/supersede без обхода журнала — gates.
- M3 conflict digest → 69; identical → no-op.
- M4 resume/crash на durable boundaries: evidence adopt, declared-intent
  reuse, e2e до published.
- M5/M8 T8: новый head/dirty snapshot/requirements/environment → каскад
  stale, execution bound_revision инвалидируется; concurrent writer
  (workflow и index) отклонён, мёртвый pid освобождён, битый lock
  отклонён.
- M9 crash после upload до save → reconcile adopt, resend запрещён,
  upload-вызовов ровно 1.
- M10 create→crash→reconcile adopt, creates = 1.
- M11 unknown+zero → blocked; incomplete/foreign/multiple → blocked без
  create; точный match → adopt.
- M12 undetermined run/upload никогда не повторяется (dispatch count 1).
- M13 TestOps failure не вызывает новый API-прогон (runner count
  неизменён).
- M14 read-only import uploaded execution: source SHA до/после равен,
  corrupt package отклонён до записи.
- M15/M16/M17 strict validation, skip-phase/review-digest/unit-scope
  блоки, corrupt/unsupported state байт-в-байт неизменён.
- M18 terminal repeat: published → init resumed, publish/pr — no-op,
  транспортов 0.

## Доказано offline

Идемпотентность и отсутствие дублей на fake-транспортах со счётчиками
вызовов; crash-safety на всех durable boundaries; конкурентный отказ
второму писателю; read-only импорт; e2e initialized→published полностью
offline. Все fake-данные помечены вымышленными
(`test_data.consts.workflow`, `unit-pilot`, `git.invalid`).

## Непроверенное и ограничения

- Live PR workflow: `PrTransport` имеет только fake; search/create/get
  реального GitHub API, head_sha из PR-ветки, права/лимиты — не
  проверены; `published` в live требует реального verified PR.
- `publish-testops` покрывает upload+verify; plan/assign/package
  оркестратор пока не вызывает — их делегированный запуск остаётся на
  `run-testops.sh` (будущее уточнение контракта).
- Реальный запуск `run-execution` (Docker/SUT) не выполнялся — argv
  построены, но dispatch проверен только на fake runner.
- PR для QA-репозитория (`tests` role) моделируется отдельной записью;
  реальный пакет 19A ещё не публикуется — 19A-артефакты (ветки/spec/
  материалы) могут быть напрямую введены через `pr prepare` в будущем
  live-этапе; оркестратор не менял и не зависел от них.
- `metrics.llm_cost` зарезервировано, не заполняется.

## Изменённые/новые файлы

- `infrastructure/workflow/{__init__,state,index,locks,envelopes,adapters,orchestrator}.py` (новые)
- `tools/workflow.py`, `tools/run-workflow.sh` (новые)
- `tests/unit/test_workflow_{state,gates,intents,orchestrator}.py` (новые)
- `test_data/consts/workflow.py`, `test_data/utils/workflow.py` (новые)
- `knowledge/components/{README,infrastructure,consts,workflow}.md`
- `knowledge/integrations/qa-workflow.md` (новый)
- `docs/qa-workflow/design/20-orchestrator-implementation.md` (новый)
- `artifacts/workflow/index.json`, `artifacts/workflow/wf-17431cddc9919d3d/state.json` (новый state пилота)
- `artifacts/workflow-implementation/20-20261115T182635Z/` (evidence)
- Исторические state/evidence, исходники приложения и API-контракт —
  без изменений; чужие незакоммиченные изменения сохранены.

Остановка по поручению: ожидаю приёмки координатора перед 21.
