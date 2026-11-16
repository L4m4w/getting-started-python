# 21A — независимое ревью: state schema, envelopes, evidence contracts

Дата: 2026-11-15. Исполнитель: независимый ревьюер 21A (не автор 20/20R/20R2).
**Статус: `ready`** — ревью завершено; зафиксировано 5 findings (ни одного
ложного принятия evidence на проверенных путях; проблемы — устойчивость
schema-валидации и два пробела в инвариантах/гейтах). Код не изменялся;
другие агенты не запускались; все операции offline.

Параллельные области: эффекты/recovery — 21B; index/locks/concurrency,
CLI и повтор цепочки — 21C. Этот отчёт покрывает только назначенную часть
и **не** является приёмкой задачи 21 или MVP.

---

## 1. Проверенная версия (SHA)

Все 13 записей
`artifacts/workflow-implementation/coordinator-20r2-review-20261115/reviewed-inputs.sha256.json`
пересчитаны на текущем дереве и **совпали** (infrastructure/workflow/*,
tools/workflow.py, tools/run-workflow.sh, handoff/design 20R2,
tests/unit/test_workflow_20r2.py). Drift принятого кода отсутствует.

Ключевые SHA-256 проверенной версии:

| Файл | SHA-256 (первые 16) |
| --- | --- |
| `infrastructure/workflow/state.py` | `a7c85ee1df724881` |
| `infrastructure/workflow/contracts.py` | `e1caf5c78c3bee51` |
| `infrastructure/workflow/envelopes.py` | `8caf13c304186729` |
| `infrastructure/workflow/orchestrator.py` | `19e506b9e88a5c7a` |
| `infrastructure/workflow/adapters.py` | `9a9b23a51227d1d3` |

Protected state: `shasum -a 256 -c` по списку
`20r2-20261115T195559Z/protected-sha-after.txt` — **19/19 OK** до и после
ревью (index.json, wf-17431cddc9919d3d/state.json, три TestOps state,
два upload.log, шесть manifest/junit, четыре файла проб координатора).
15/15 файлов `api-contract-v1` побайтово совпадают с `source_identity`
manifest `run-ni_5bvnc` (`missing=[]`, `changed_during_run=[]`).

## 2. Что проверено

### Статическое ревью
- `state.py` (708 строк): schema-1 строгая валидация, атомарная запись,
  `artifact_fresh`/bound-digest freshness, каскад stale при T8,
  `executions_satisfy`/`execution_matches`, `publications_confirmed`,
  `implied_phase` как единственный источник фазы, журнал/intents.
- `envelopes.py` (253 строки): строгий разбор envelope v1, allowlist
  ключей, actor/domain, repo-relative пути, `verify_document` с защитой
  от выхода за root, digest артефакта по content.
- `contracts.py` (777 строк): `validate_source_identity` (точный
  allowlist `api-contract-v1` + `implementation.test_files`, пустые
  `missing`/`changed_during_run`, `rechecked_at`, уникальность, точное
  равенство множеств files/copies, live- или R3-эквивалентные sha256,
  1:1 копии `sources/` + запрет неучтённых файлов);
  `validate_scenario_composition` (точная биекция JUnit↔raw Allure через
  `testops.results`, boundary-token SID без lookalike `0010↔001`,
  статусы по варианту, `ALLURE_ID`, сверка с TestOps state);
  `verify_historical_baseline_acceptance` (канонический digest против
  реестра координатора, review-файлы на диске, exact SHA evidence,
  ограниченный `allowed_changed_files`).
- `orchestrator.py` accept/import (строки 323–605, 914–1239): preflight
  digest-пересчёты перед gate'ами, фазные границы accept, no-op
  идентичного конверта, связывание review→frozen scenarios digest,
  проверки bindings против записанных executions, строгий
  `_manifest_problems`/`_manifest_variant`/`_manifest_matches_revision`.
- `adapters.py` (части identity): read-only `GitReadAdapter` (тип
  объекта `commit`, дерево, diff base..head), `read_manifest` (schema-2),
  `junit_summary` (независимый пересчёт), `snapshot_allowlist`.

### Выполненные проверки (команды → exit → результат)

| Команда | Exit | Результат |
| --- | --- | --- |
| `shasum -a 256` по 13 файлам reviewed-inputs | 0 | 13/13 совпали, drift нет |
| `shasum -a 256 -c protected-sha-before.txt` | 0 | 19/19 OK |
| сверка 15 `source_identity.files` manifest `run-ni_5bvnc` с checkout | 0 | 15/15 совпали |
| `pytest tests/unit/test_workflow_state.py::TestStateSchema ::TestRevisionCascade tests/unit/test_workflow_gates.py tests/unit/test_workflow_20r2.py::TestR1SourceAndScenarioContract ::TestR3HistoricalProvenance -q --basetemp=<EV> -o cache_dir=<EV> --junitxml=<EV>/targeted.xml` | 0 | **70 passed**, 0 failed |
| `probe_state_schema.py` (собственный) | 0 | 9 проб: 4 OK, **3 crash-findings**, 1 baseline dead-end, 1 контрольная (см. probe 2) |
| `probe_forged_published.py` (собственный) | 0 | 3 пробы: **2 schema-findings**, 1 контрольная демонстрация |
| `probe_accept_import.py` (собственный) | 0 | 8 проб: 6 OK, **2 findings** |
| `real_pilot_compat_probe.py` (побайтовая копия пробы координатора) | 0 | head 6/6 mapped, problems `[]`; base blocked без provenance (2 файла 17A), `[]` с принятой записью; деревья неизменны |
| `probe_real_evidence.py` (собственный, read-only + мутации на копиях) | 0 | **11/11 PASS** |
| `git diff --check` (оба репозитория) | 0 | чисто |
| `sh tools/versions.sh` | 0 | Python 3.13.15, все pins совпали |

Evidence: `artifacts/workflow-review/21a-20261115T201127Z/`
(probe_*.py, probe_*_results.json, real_pilot_compat_probe.py +
real-pilot-compatibility-results.json, targeted.xml, protected-sha-*.txt,
pytest-basetemp/, pytest-cache/).

## 3. Findings

### F-21A-1 [medium] Невалидируемые типы в state.json приводят к crash вместо clean `69`

- **Файлы:** `infrastructure/workflow/state.py:352-370`
  (`executions_satisfy`), `:340` (`execution_matches`,
  `entry.get("junit_summary")`), `:359` (`strength_evidence`),
  `:514` (`validate_state` → `implied_phase`).
- **Суть:** `validate_state` проверяет форму `artifacts`, `executions`,
  `publications`, `intents`, `journal`, но **не** типы
  `revision_data.expected_executions[]`, `strength_evidence` и
  `executions[].junit_summary`. При этом `implied_phase` вызывается внутри
  `validate_state` и обращается к ним через `.get` без защиты.
- **Trigger/repro:** `artifacts/workflow-review/21a-20261115T201127Z/probe_state_schema.py`
  — валидный executed state с `expected_executions=[42]` →
  `AttributeError: 'int' object has no attribute 'get'` (p3);
  `strength_evidence=[1,2]` → `AttributeError` (p4);
  `executions[0].junit_summary="not-a-dict"` → `AttributeError` (p5).
- **Последствия:** повреждённый/искажённый state падает необработанным
  исключением: CLI `status`/`doctor`/любая команда дадут traceback с
  exit 1 вместо задокументированного `69`; `reconcile`/`doctor` не смогут
  показать состояние. Ложного принятия нет — fail-stop, но нарушен
  контракт «corrupt state — чистый WorkflowStateCorruptError» и затруднена
  диагностика.
- **Рекомендация:** в `validate_state` добавить `_require_type` для
  `expected_executions` (list[dict] с `variant`/`required`/`expect`/dict),
  `strength_evidence` (dict), `executions[].junit_summary` (dict|null),
  `selection` (dict|null); либо обернуть вызов `implied_phase` в
  `validate_state` перехватом `AttributeError/TypeError → WorkflowSchemaError`.

### F-21A-2 [medium] `publications.required`/состав ролей не валидируется — forged `published` без ни одной реальной публикации

- **Файлы:** `infrastructure/workflow/state.py:300-313`
  (`_validate_publications`), `:373-413` (`publications_confirmed`),
  `:199-206` (`new_state` — единственное место, где `required=True`).
- **Суть:** `_validate_publications` проверяет только домен `status`,
  но не требует наличия обеих ролей `pr.app`/`pr.tests` и не требует
  `required=True`. `publications_confirmed` перебирает только
  присутствующие записи и пропускает `required=False`.
- **Trigger/repro:** `probe_forged_published.py` —
  q2: удаление `publications.pr.tests` из state.json (с phase=published)
  → `load_state` принимает `published` без какой-либо записи о PR тестового
  репозитория; q3: `required=false` на testops и обоих PR → `published`
  при нуле подтверждённых публикаций.
- **Последствия:** заявленный в 20R2 инвариант («`load_state` отказывает
  поддельному `published`, пока head не является проверенным immutable
  commit») обходится не подменой head_sha, а удалением/ослаблением
  обязательных элементов. Требуется локальная запись в state.json —
  это не удалённая атака, но defence-in-depth, на который опирается R2,
  здесь не работает.
- **Рекомендация:** в `_validate_publications` требовать наличие обеих
  ролей `app`/`tests` с `required: true` и `testops.required: true`
  (или зафиксировать домен допустимых значений `required` явно).

### F-21A-3 [medium-low] Re-import того же baseline после T8 — `no-op` без перепривязки: тупик для strength evidence

- **Файлы:** `infrastructure/workflow/orchestrator.py:1116-1119`
  (`import_execution` → `no-op` на записанном execution_id),
  `state.py:335-349` (`execution_matches` требует
  `bound_revision == текущей ревизии`), противоречие с docstring
  `orchestrator.py:941-967` (`_manifest_matches_revision`: «base —
  evidence для каждой ревизии с тем же base»).
- **Trigger/repro:** `probe_state_schema.py` p9: после `drive_to_executed`
  + init с новым patch sha (revision=2) повторный
  `import_execution(run-unitbase1)` возвращает `no-op` («already
  recorded»), `bound_revision` остаётся 1 → `executions_satisfy=False`,
  фаза `implementation_ready`.
- **Последствия:** для того же неизменного base workflow требует нового
  baseline-прогона под новым execution id после каждой смены ревизии —
  иначе strength evidence невосполнимо. Поведение fail-closed (ложного
  принятия нет), но противоречит документированной семантике base и
  сообщает оператору «уже записано» там, где evidence фактически не
  удовлетворяет текущей ревизии. Выход есть: `run_execution --variant base`
  создаст новый execution.
- **Рекомендация:** либо ослабить `execution_matches` для `variant=="base"`
  (bound к `identity.app_base_sha`, а не к revision), либо при re-import
  перепривязывать `bound_revision` после полного `_manifest_problems`,
  либо явно документировать требование нового baseline-прогона и честный
  ответ `blocked`/`needs_rerun` вместо `no-op`.

### F-21A-4 [low-medium] `accept implementation` принимает lookalike node id (подстрока вместо boundary-token)

- **Файл:** `infrastructure/workflow/orchestrator.py:591-596`
  (`_check_implementation`: `not any(sid in node for node in node_ids)`).
- **Суть:** проверка покрытия сценариев собранными node id использует
  подстроку: `UNIT-VAL-0010` удовлетворяет `UNIT-VAL-001` — та же
  lookalike-проблема, которую R1 исправил для JUnit (`contracts.py:300-318`),
  осталась на гейте implementation.
- **Trigger/repro:** `probe_accept_import.py` a1: `list` возвращает только
  `test_case[UNIT-VAL-0010/0020/0030]` → `accept implementation` =
  `accepted`, фаза `implementation_ready`.
- **Последствия:** артефакт implementation принят при фактическом
  отсутствии сценариев; фаза продвигается. Дальше всё равно fail-closed
  (R1 composition на evidence не пройдёт), но gate слабее заявленного и
  ошибка всплывёт только на execution.
- **Рекомендация:** использовать тот же boundary-token regex
  `(?<![A-Za-z0-9_-])<sid>(?![A-Za-z0-9_-])` для node ids.

### F-21A-5 [low] `testops_id: true` в bindings проходит envelope и accept

- **Файл:** `infrastructure/workflow/envelopes.py:180-181`
  (`isinstance(testops_id, int) and testops_id > 0` — `True` проходит).
- **Trigger/repro:** `probe_accept_import.py` a2: mapping
  `{"UNIT-VAL-001": true}` → envelope валиден, `accept bindings` =
  `accepted`, записано `True` (=`int(True)` = 1).
- **Последствия:** ложная привязка к TestOps id 1; внутренне консистентно
  (метка `"1"` совпадёт), но семантически неверно и маскирует ошибку входа.
- **Рекомендация:** `isinstance(testops_id, int)
  and not isinstance(testops_id, bool) and testops_id > 0`.

## 4. Подтверждённые свойства (без findings)

- **Strict state:** corrupt JSON → `WorkflowStateCorruptError` (p2);
  gapless journal, доменные проверки всех перечислений, фаза строго равна
  `implied_phase`, атомарная запись tmp+fsync+replace+dir-sync.
- **Freshness/revision:** bound-digest freshness пересчитывается, а не
  доверяется `bound_revision`; T8 каскадит stale артефакты и блокирует
  PR-публикации; идентичный accept — `no-op` в любой фазе (a6), конфликтный
  digest на той же ревизии → `69`, пропуск фазы → `69` (a7).
- **Envelopes:** строгий ключевой контракт, actor ∈ {human,llm,
  orchestrator,imported}, document обязателен кроме bindings, защита от
  выхода за root, bijection mapping, git_blob 40-hex.
- **Source contract R1:** полный allowlist, точное равенство множеств
  files/copies, live/current+historical sha256, 1:1 копии и запрет
  посторонних файлов подтверждены на реальном `run-ni_5bvnc` и мутациях
  его копий (удаление результата → missing scenario; посторонний файл в
  `sources/` → unrecorded; лишний testcase → count+foreign; flip статуса
  → junit+J/A mismatch).
- **Scenario contract:** реальные raw Allure `run-ni_5bvnc` имеют
  `uuid`/`fullName`/`parameters`/одну `ALLURE_ID`; русские display titles
  в identity не участвуют; `scan_assignments` отклоняет unmapped/duplicate
  до индексации (KeyError в `contracts.py:518` недостижим — каждый
  scanned uuid гарантированно мапится).
- **Provenance R3:** head provenance → blocked (a3); self-signed запись →
  «no coordinator-accepted record» (a4); реестровая запись для чужого
  execution → та же блокировка (a5); поле-дрейф и поддельный
  review-decision → canonical-digest mismatch (r6/r7); `run-vzsatlfk` без
  provenance блокируется двумя файлами 17A, с принятой записью — `[]`.
- **Чужой head/base:** `_manifest_variant`/`_manifest_matches_revision`
  связывают base только с `identity.app_base_sha`, head — с exact
  patch/commit; commit-head требует `git cat-file` тип `commit` и
  совпадение дерева (R2, см. ниже про PR — сам PR-путь в области 21B).
- **Read-only совместимость:** tree digests `run-ni_5bvnc`,
  `run-vzsatlfk`, их TestOps-директорий и `artifacts/workflow` до/после
  всех проб **идентичны** (`ed699418…`, `89eea129…`, `28b0af8d…`,
  `5e461a31…`, `1bce1def…`); оригиналы не модифицировались, мутации —
  только на копиях в temp dirs.

## 5. Замечания (не findings)

- `implied_phase` никогда не возвращает `scenarios_ready` (state.py:417-432):
  после accept scenarios фаза сразу `awaiting_review` — документированный
  шаг цепочки недостижим; косметика.
- `contracts.py:699` — неиспользуемая переменная `key`.
- `_match_junit_scenario` сверяет `classname` только при `[` в имени —
  непараметризованный кейс с чужим классом не проверяется (edge).
- `load_results` и `scan_assignments` читают директорию дважды —
  теоретический TOCTOU при одновременной записи в evidence dir.
- `validate_scenario_composition` берёт `scenario_ids` без проверки
  статуса артефакта — фаза выше всё равно fail-closed.
- `publications_confirmed` не требует bindings — но `prepare-testops`
  требует `artifact_fresh("bindings")`, цепочка до `uploaded` без
  bindings невозможна.

## 6. Непроверенное (вне области 21A)

- Эффекты/recovery: intent journal до/после dispatch, upload
  unknown/inconclusive, crash-границы prepare/upload, PR transport —
  **21B**.
- Index/locks/concurrency, production CLI на реальном subprocess,
  повтор полной цепочки — **21C**.
- Live пути (настоящий SUT, TestOps `--online`, Git/PR writes) — не
  выполнялись никем.

## 7. Рекомендации координатору / для Git-PR пакета 19A

1. Все 5 findings — локальные правки `state.py`, `orchestrator.py`,
   `envelopes.py`; фикс небольшой и должен сопровождаться регрессионными
   тестами уровня probe (входы уже есть в моём evidence).
2. F-21A-1 и F-21A-2 стоит закрыть до приёмки 21: они дешёвые и прямо
   укрепляют заявленные инварианты «corrupt → 69» и «поддельный published
   не проходит load».
3. F-21A-3 требует решения по семантике: revision-agnostic base binding
   или явное требование нового baseline. Это влияет на документированный
   workflow — решение за координатором.
4. F-21A-4/F-21A-5 — мелкие правки валидации, можно в том же пакете.
5. При включении workflow-кода в PR-пакет: мои probe-скрипты
   (`artifacts/workflow-review/21a-*/`) — кандидаты для адаптации в
   unit-тесты; сами evidence в Git не включаются (artifacts/ gitignored).

## 8. Границы выполнения

Не выполнялись: сеть, SUT/API/UI, Docker/Gradle, CI, TestOps writes,
commit/push/PR, запуск других агентов, переключение/сброс checkout,
правка исходников/тестов/общих документов. Исторические evidence,
рабочий workflow и принятый код — только чтение; tree digests и
protected SHA подтверждены неизменными до/после.
