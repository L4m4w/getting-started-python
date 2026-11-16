# Приёмка этапа 17 — финальный execution с закреплёнными ID

Дата: 2026-11-15. **Этап 17 завершён и принят координатором.**
Это локальный финальный API execution и bind-пакет, без новой публикации.
Этап 16 остаётся завершённым; полный MVP не завершён.

## Результат исполнителя 17C

[Handoff](17c-final-execution-run.md): новый fix execution **run-ni_5bvnc**,
шесть passed без failed/errors/skipped, собственный пользователь,
pre/post live gateway binding, SQL cleanup и down собственного catupdval.
Исходные result JSON уже содержат закреплённые ALLURE_ID из кода 17A.
Подготовлен локальный bind-пакет; TestOps write/read-only вызовов не было.

Evidence исполнителя:

- `artifacts/harness/run-ni_5bvnc/` — manifest/JUnit/Allure/source copies;
- `artifacts/final-execution/17c-run-20261115T121140Z/` — окружение/cleanup;
- `artifacts/testops/run-ni_5bvnc/` — новый state и bind-пакет.

## Собственная проверка координатора

Без запуска SUT, Docker или сети проверены:

- manifest schema 2, completed, exit 0; JUnit действительно содержит
  шесть testcase без failure/error/skipped;
- все 15 текущих файлов и их copies совпали с manifest SHA;
  missing/changed_during_run пусты, rechecked_at заполнен;
- environment.container_check performed/running/matches_declared_image=true;
- pre/post evidence содержит тот же полный container ID и image ID,
  что manifest: gateway fix
  `sha256:f496835fbad4dd72fa650f4b27d1b7c171d40e73d662da929aab1a8c4162614b`;
- исходный Allure и пакет содержат по шесть passed с UUID из state;
  у каждого ровно один ALLURE_ID и правильная согласованная пара;
- `_validate_upload_package` — OK: source/mapping/package integrity;
- новый state schema 2, bind, pending, attempts=0, launch=null;
- старый uploaded state run-5tsmzg1d не изменён, SHA из wave 13 совпал;
- сохранённые SQL counts=0 и post-down down_exit=0, пустые выборки
  контейнеров/сетей прочитаны и приняты как evidence исполнителя.

Cleanup и Docker-картину координатор live не повторял. SQL-файл хранит
метки проверок и counts, а точный пользователь и команда описаны в handoff;
это не самостоятельное повторное измерение координатора после остановки БД.
Source→build→image provenance — ранее принятый набор 10, без новой сборки.

Собственная offline-проверка: exit 0,
`artifacts/final-execution/coordinator-17-acceptance-20261115T121550Z/review.json`.
`git diff --check` и локальные ссылки — OK. Unit/collection не повторялись:
код после приёмки 17A не менялся. Исторические evidence/state не изменялись.
Координатор агентов не запускал, commit/push/PR не выполнял.

## Конкретный пакет для следующей публикации

| Поле | Значение |
| --- | --- |
| execution | `run-ni_5bvnc` |
| endpoint / project | `https://allure.qa.guru` / `5444` |
| mode | bind |
| results / files | 6 passed / 40 |
| input SHA-256 | `ba0d179cde801aca38df322b3725b786e70d44f82b47cd7af617a5fe5f5afa21` |
| assignments SHA-256 | `ebaa8a296ee2968edd50329e6aa3dace661abe879250889a41e01024a89bfc55` |
| package SHA-256 | `1e1f643257c2289be3add60c47ab10e749b289e3d0f8920d3acf060f488d05a7` |
| state SHA-256 при приёмке | `1b3a7762d83a6abffb337e8a55d351db3372af6f47f0e8aee77847d99e6ae1d2` |
| предлагаемый launch name | `CAT-UPD-VAL run-ni_5bvnc final17-20261115` |

Пары остаются согласованными: 001→55376, 002→55374, 003→55375,
004→55377, 005→55373, 006→55378. Не создавать кейсы заново.

Следующее поручение — [18: публикация финального bind execution](../agent-tasks/18-bound-publication.md).
Требуется отдельное разрешение пользователя на **одну** публикацию этого
пакета в новый launch и его close. Разрешение первой публикации этапа 16
использовано и на новый execution не переносится. Пока разрешения нет,
не запускать внешние write-вызовы. Старый launch 57316 не переиспользовать.

После публикации остаются Git/PR (не разрешены), минимальный оркестратор
с возобновлением, сквозная идемпотентность и итоговая оценка MVP.
