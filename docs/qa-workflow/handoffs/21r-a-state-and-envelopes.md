# 21R-A — исправления schema и envelopes (21A F1/F2/F5)

Дата: 2026-11-15. Исполнитель: 21R-A. **Статус: `ready`** — все три
назначенных findings исправлены, регрессии зелёные, integrity-сверки
чистые. Это не приёмка 21R и не разрешение Git/PR-этапа: общая проверка
объединённой версии A+B+C остаётся координатору.

## Область и SHA

Изменены только назначенные файлы:

| Файл | SHA-256 |
| --- | --- |
| `infrastructure/workflow/state.py` | `a7c85ee1…642486` → **`c52ab60c3a54f0648445b46a25700f9d0896c05a2acb4b757aec9cbe80389e43`** |
| `infrastructure/workflow/envelopes.py` | `8caf13c3…dc62c` → **`14696422934331cf15114f9303bcb79dc1e074fd9a0b0c7d2dc8418dc5073a69`** |
| `tests/unit/test_workflow_21r_a.py` (new) | `55cd207b671ba3e33d4f42e4007001c4985fbc5baa358687f09bac2987d5c066` |
| `test_data/consts/workflow_21r_a.py` (new) | `a60fc9299a7c4a2bc0186b84bb64c1aad240fe5267bdf76930013c2a57b082fc` |
| `docs/qa-workflow/handoffs/21r-a-state-and-envelopes.md` (new) | этот файл |
| `artifacts/workflow-corrections/21r-a-20261115T204107Z/` (new) | gitignored evidence |

Сверки до/после (`integrity-before.json` / `integrity-after.json`):

- 13/13 записей `reviewed-inputs.sha256.json`: изменились ровно два моих
  файла, остальные 11 совпадают с принятым baseline. **Peer drift отсутствует**
  на момент записи: `orchestrator.py` (область B) и оба документа 20R2
  (область C — каталог обновляет отдельно) не менялись.
- 19/19 protected SHA из `20r2-20261115T195559Z/protected-sha-after.txt`
  совпали до и после (index.json, wf-17431cddc9919d3d, три TestOps state,
  upload.log, manifest/junit трёх runs, пробы координатора).
- 15/15 файлов `api-contract-v1` совпадают с `source_identity` manifest
  `run-ni_5bvnc`.
- `git diff --check` по изменённым файлам — exit 0.

## Исправления (findings → код → тесты)

### F-21A-1: типы/домены структур, используемых gate'ами

- `state.py`, новый `_validate_execution_requirement`: каждый элемент
  `expected_executions` и непустой `strength_evidence` — объект с
  `variant` ∈ `{base,head}`, `required` — bool, `scope` == `"api"`
  (единственный scope, который gate реально проверяет), `expect` —
  null|object с ключами только из `JUNIT_SUMMARY_KEYS` и неотрицательными
  int-значениями (bool запрещён). `strength_evidence` допускает
  null/пустой dict («нет strength-gate»); непустой dict обязан быть
  полной requirement-записью.
- `state.py`, `_validate_execution`: `junit_summary` — null|object со
  всеми пятью счётчиками неотрицательных int (bool запрещён);
  `selection` — null|object, `targets` — list непустых строк, `scope` —
  строка; `bound_revision` — неотрицательный int без bool.
- Gate'ы усилены без catch-all и без ослабления: `execution_matches`,
  `executions_satisfy`, `publications_confirmed` возвращают `False` на
  неправильных типах вместо AttributeError/TypeError (включая
  `bound_revision: true`, который раньше совпадал с revision 1).
- Проверки выполняются в `validate_state` до вызова `implied_phase` —
  повреждённый state даёт `WorkflowSchemaError`/`WorkflowStateCorruptError`
  и CLI 69 без traceback и без изменения файла.

Repro: probes p3/p4/p5 — было `AttributeError`, стало
`WorkflowSchemaError` (`probes-after/probe_state_schema_results.json`).
Тесты: `TestGateDataSchema` (18 мутаций revision_data + 12 мутаций
executions[] + fail-closed + прямые вызовы gate'ов на malformed dict).

### F-21A-2: fixed-MVP состав publications

- `_validate_publications`: `testops.required is True`; `pr` содержит
  ровно роли `app` и `tests` (`PR_ROLES`), у каждой `required is True`
  и статус из домена; `spec` — null|object, `spec_sha256` — null|64-hex,
  `testops.execution_id` — null|str. Missing/extra role, `required`
  false/null/0/1/"true" → schema error.
- `publications_confirmed` повторяет ту же композицию напрямую
  (`isinstance`-проверки, точное множество ролей, `required is True`),
  поэтому ослабленный набор отклоняется и при вызове gate в обход
  `load_state`. Внутренне согласованный `published` по-прежнему
  загружается — schema проверяет структуру, а не аутентифицирует автора
  (контроль q1 задокументирован).

Repro: probes q2/q3 — было `loaded phase=published`, стало
`WorkflowSchemaError` (`probes-after/probe_forged_published_results.json`).
Тесты: `TestPublicationsContract` (11 tamper-кейсов + 18 weak-required +
прямой gate на всех tamper + positive load).

### F-21A-5: bool как TestOps ID

- `envelopes.py`, `_validate_bindings_payload`: `testops_id` требует
  `int`, `not bool`, `> 0`. `True`/`False` отклоняются; положительные
  int, включая 1, остаются валидными.

Repro: probe a2 — было `accepted mapping={'UNIT-VAL-001': True, ...}`,
стало `blocked: TestOps ID must be a positive int: True`
(`probes-after/probe_accept_import_results.json`).
Тесты: `TestBindingsTestOpsId` (6 bad id + bool на accept + positive).

## Выполненные проверки

| Команда | Exit | Результат |
| --- | --- | --- |
| probes-before (3 скрипта, новые копии) | 0 | findings воспроизведены: p3/p4/p5 crash, q2/q3 forged accepted, a2 bool accepted |
| probes-after (те же копии) | 0 | 7/9, 3/3, 7/8; единственные FAIL — вне области: p9 (F3→B), p6 (контроль несогласованной phase), a1 (F4→B) |
| `pytest tests/unit/test_workflow_21r_a.py` | 0 | **74 passed**, 0 failed/errors/skipped |
| `pytest test_workflow_state.py::TestStateSchema ::TestRevisionCascade test_workflow_20r2.py::TestR2GitHeadSeparation` | 0 | **26 passed** |
| `git diff --check` (мои файлы) | 0 | чисто |

JUnit: `pytest/junit-21r-a.xml` (74, sha `1b705f9c…`) и
`pytest/junit-targeted.xml` (26, sha `9074a0a5…`).
CLI-регрессия внутри файла: реальный subprocess
`tools/workflow.py --store-dir <tmp> status` на испорченной копии state —
exit 69, `BLOCKED`, без `Traceback`/`AttributeError`, bytes файла не
изменились (два вида порчи: revision_data и publications); на валидном
state — exit 0.

Evidence: `artifacts/workflow-corrections/21r-a-20261115T204107Z/` —
`inputs-sha256-{before,after}.json`, `integrity-{before,after}.json`,
`probes-before/`, `probes-after/` (скрипты + results), `pytest/`
(basetemp, cache, JUnit, allure).

## Новые константы

`test_data.consts.workflow_21r_a` — только данные моих тестов:
`WEAK_REQUIRED_VALUES`, `WEAK_REQUIRED_PATHS`, `CORRUPT_REVISION_DATA`
(18), `CORRUPT_EXECUTION_FIELDS` (12), `PUBLICATION_TAMPERS` (11, с флагом
ожидания прямого gate), `BAD_TESTOPS_IDS`, `GOOD_TESTOPS_IDS`.
Shared consts/fixtures не изменялись.

## Поведенческие заметки (границы решения)

- `expect` может отсутствовать/быть null (нет проверки счётчиков);
  `scope` и `variant` обязательны. Требование `scope == "api"` —
  сознательное решение: любое другое значение молча отключало
  проверку `tests/api`-targets, что эквивалентно ослаблению gate.
- `expected_executions`/`strength_evidence` отсутствуют в
  `bound_input_digests` артефактов: их замена не делает артефакты
  stale, а лишь сдвигает implied-фазу через executions-gate —
  существующее поведение, не менялось.
- `publications_confirmed` не сверяет `spec_sha256` (целостность spec —
  проверки PR-пути, область B); флаг в `PUBLICATION_TAMPERS`
  документирует, что gate видит только состав.
- Внутренне согласованный forged `published` загружается — schema не
  является аутентификацией (уточнение сводного решения п.5).
- 21A F3 (base rebind) и F4 (lookalike node ids) — область 21R-B, не
  исправлялись; probes p9/a1 остаются FAIL ожидаемо.

## Ограничения и непроверенное

- Общий `group unit`/collection не запускался — по заданию, объединённую
  версию проверяет координатор.
- Живые пути не трогались: сеть, SUT/API/UI, Docker/Gradle/CI, TestOps/PR
  writes, commit/push/checkout/reset — не выполнялись; приложение
  read-only; рабочий workflow и исторические evidence не изменялись
  (19/19 protected, 15/15 API).
- Peer drift: на момент handoff `orchestrator.py` и документы 20R2
  совпадают с принятым baseline; правки B/C после моей сверки —
  ожидаемые и проверяются координатором при слиянии.
- Публичный API: добавлены константы `PR_ROLES`, `JUNIT_SUMMARY_KEYS`,
  `REQUIRED_EXECUTION_SCOPE` и приватный `_validate_execution_requirement`
  в `state.py`; сигнатуры существующих функций не менялись —
  `execution_matches` стал строже только к невалидным типам (не примет
  больше, может отклонить `bound_revision: true` и null `junit_summary`,
  ранее проходившие по пустому expect).

## Заметки для 21R-C (каталог)

- `infrastructure.workflow.state`: новые `PR_ROLES`, `JUNIT_SUMMARY_KEYS`,
  `REQUIRED_EXECUTION_SCOPE`; `executions_satisfy`/`execution_matches`/
  `publications_confirmed` — теперь type-safe (False на malformed);
  schema валидирует `expected_executions[]`/`strength_evidence`/
  `junit_summary`/`selection`/`bound_revision` и строгий состав
  `publications` (testops + ровно app/tests, `required is True`).
- `envelopes`: TestOps ID в bindings — только положительный int, bool
  запрещён.
- Новый модуль констант `test_data.consts.workflow_21r_a` и регрессии
  `tests/unit/test_workflow_21r_a.py` (74 теста).

## Остановка

После этого handoff работа прекращена до общей приёмки координатором
всех частей 21R.
