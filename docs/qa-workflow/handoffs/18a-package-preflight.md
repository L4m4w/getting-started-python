# 18A — локальная проверка финального bind-пакета run-ni_5bvnc

Агент: `18A`. Дата: 2026-11-15. Статус: `ready`.

Локальная перепроверка входов задания 18 перед возможной публикацией.
`ready` означает готовность локальных входов, **не разрешение публикации**:
внешних вызовов, попыток upload и изменений state/пакета не выполнялось.
Execution lock не захватывался; state читались напрямую и через read-only
`state.load_state` без `save_state`.

Основание: [coordination-wave-15.md](coordination-wave-15.md),
[17c-final-execution-run.md](17c-final-execution-run.md),
[задание 18](../agent-tasks/18-bound-publication.md).

## Следы предыдущих попыток (отсутствуют)

- Handoff 18* отсутствует; `artifacts/testops-live/` содержит только каталоги
  16c/coordinator-16, новых `18-*` нет.
- В `artifacts/testops/run-ni_5bvnc/` только `state.json`, `upload-results/`,
  `execution.lock-gate` (gate-файл остаётся на диске и не означает занятый
  lock); `upload.log` нет, временных `.upload-results.tmp-*` каталогов нет.
- `upload.attempts=0`, `history=[]`, `launch=null` — попыток не было.

## Identity пакета и state (зафиксировано для перепроверки 18C)

| Поле | Значение |
| --- | --- |
| execution | `run-ni_5bvnc` |
| endpoint / project | `https://allure.qa.guru` / `5444` |
| state.json SHA-256 | `1b3a7762d83a6abffb337e8a55d351db3372af6f47f0e8aee77847d99e6ae1d2` (= записи wave 15 при приёмке, не изменён) |
| package SHA-256 | `1e1f643257c2289be3add60c47ab10e749b289e3d0f8920d3acf060f488d05a7` |
| input SHA-256 | `ba0d179cde801aca38df322b3725b786e70d44f82b47cd7af617a5fe5f5afa21` |
| assignments SHA-256 | `ebaa8a296ee2968edd50329e6aa3dace661abe879250889a41e01024a89bfc55` |
| results / files | 6 passed / 40 |
| предполагаемый launch | `CAT-UPD-VAL run-ni_5bvnc final17-20261115` |
| manifest SHA-256 | `32f1ec8950462d96f220326bfa6665fa55c44195eaab39ec76e57733418970ad` |
| junit.xml SHA-256 | `0d2e10c2e3c608c32a020fd56308d9a0424de98d16254d8e4cd25a20f20cdf08` |

## Проверенное состояние state run-ni_5bvnc

- `schema_version=2`, `endpoint`/`project_id` согласованы, `package.mode=bind`.
- `upload.status=pending`, `attempts=0`, `phase=null`, `launch=null`,
  `history=[]`, `confirmation=null`, `package_sha256=null`.
- `unmapped=[]`, `unresolved_ids=[]`; все шесть сценариев `bound`
  (`binding_source=assign`, status `passed`):
  001→55376, 002→55374, 003→55375, 004→55377, 005→55373, 006→55378 —
  совпадают с согласованными парами.

## Integrity-проверки (чистые функции `results.py`, без CLI)

- `verify_source_digest(results.path, package.input_sha256)` — PASS;
  `results.sha256 == input_sha256` — исходные результаты не менялись.
- `scan_assignments(src, index)` — строгое 1:1 соответствие шести
  результатов сценариям; UUID совпали с записанными в state.
- `assignments_digest(state)` == записанный `assignments_sha256` — PASS.
- `verify_package(upload-results, package.sha256)` — PASS: пакет
  байт-идентичен записанному.
- `validate_attachments` на пакете — PASS (все attachment source внутри
  каталога, существуют).
- Исходные result JSON: у каждого из шести сценариев **ровно один**
  `ALLURE_ID` с согласованным значением, status `passed`.
- Пакет: 6 `*-result.json`; у каждого префикс `CAT-UPD-VAL-00X:` в `name`,
  суффикс `[CAT-UPD-VAL-00X]` в `fullName`, сохранённый UUID, ровно один
  правильный `ALLURE_ID`, status `passed`; лишних результатов нет.

## Manifest/JUnit/source copies run-ni_5bvnc

- Manifest schema 2, `status=completed`, `exit_code=0`,
  `junit_summary` 6/6/0/0/0; junit.xml — 6 testcase без failure/error/skipped.
- `source_identity.contract_version=api-contract-v1`: 15/15 файлов,
  `missing=[]`, `changed_during_run=[]`, `rechecked_at` заполнен;
  все 15 копий `sources/` и текущие файлы побайтово совпадают с manifest SHA.
- `environment.declared`: base SHA `36674280…`, patch
  `04eb4c87…`, gateway image `sha256:f496835f…`, контейнер
  `gateway.niffler.dc`; `container_check`: performed/running/
  `matches_declared_image=true`, container `c6c7cb4d…`.

## Неизменность старых executions

- `run-5tsmzg1d/state.json` sha256
  `6da4472277dc42aa4e5136b9574d1521c38105f30c3ad1f944fdde2e7cae57e8` —
  совпадает с записью wave 13/17C; `upload.status=uploaded`,
  `launch.id=57316`, confirmation сохранена. `upload.log` sha256
  `221898892a4b59e595ec16f4e2533404d143599fda904f3f5cd35ad704d0c21a`.
- `run-vzsatlfk/state.json` sha256
  `001c99ba2f582f628a7559d9c79145f1d6798cfc921a3cf035fd599a11695bee`.

## Команды и exit codes

| Шаг | Способ | Exit |
| --- | --- | --- |
| Инвентаризация | `ls` handoffs/testops/testops-live/preflight | 0 |
| Чтение state | `state.load_state` (read-only, без lock) | 0 |
| Integrity | `verify_source_digest`, `scan_assignments`, `assignments_digest`, `verify_package`, `validate_attachments` | PASS |
| ALLURE_ID/rewrite | `load_results` по source и пакету | PASS, 21/21 проверок |
| Manifest/JUnit | разбор manifest.json и junit.xml | 0 |
| Копии state/log | `cp` + `shasum -a 256` в evidence | 0 |
| Гигиена | `git diff --check` | 0 |

CLI `plan/status/assign/package/resolve/verify/upload` не вызывался.

## Evidence

`artifacts/testops-preflight/18a-20261115T122532Z/`:

- `state-run-ni_5bvnc.json` — копия state (sha `1b3a7762…`);
- `state-run-5tsmzg1d.json` — копия state (sha `6da44722…`);
- `upload-run-5tsmzg1d.log` — копия upload.log (sha `2218988…`);
- `SHA256SUMS.txt` — sha копий; `originals.sha256` — sha файлов на месте,
  включая manifest/junit run-ni_5bvnc;
- `verification.txt` — вывод 21 проверки, `ALL PASS`.

Секретов в сохранённых копиях нет: state содержит только ID/метаданные,
upload.log — только UTC/операцию/exit/error.

## Ограничения

- Проверка исключительно локальная: сеть, TestOps, Docker, Gradle,
  тестовые прогоны не выполнялись. Live-состояние проекта 5444 (кейсы,
  launches) по этому поручению не перепроверялось — остаётся по handoff
  16B/wave 15.
- Байт-идентичность пакета подтверждает совпадение с записанным SHA; это
  не проверка серверной применимости.
- `execution.lock-gate` на диске — артефакт механизма, не признак занятого
  lock; признаков активного писателя нет.
- Публикация требует отдельной явной авторизации пользователя (задание 18);
  18A её не запрашивает и не предоставляет.
