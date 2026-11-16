# Маппинг пилота CAT-UPD-VAL: сценарий → тест → TestOps

## Актуальные bindings после этапа 16

2026-11-15: согласованы координатором в wave 12, назначены штатным assign
и подтверждены свежим REST verify 11:52:43 UTC, uploaded.
Приёмка: [wave 13](../../handoffs/coordination-wave-13.md).
Execution `run-5tsmzg1d`, [launch 57316](https://allure.qa.guru/launch/57316).
17A закрепил ID в API-коде; маркировка принята в
[wave 14](../../handoffs/coordination-wave-14.md).
Новый финальный execution `run-ni_5bvnc` выполнен: шесть passed,
в исходных result JSON ровно по одному согласованному ALLURE_ID.
[Приёмка wave 15](../../handoffs/coordination-wave-15.md).
Финальный bind execution опубликован:
[launch 57317](https://allure.qa.guru/launch/57317), uploaded/confirmed,
шесть прежних кейсов, новых ID не создано.
[Приёмка wave 17](../../handoffs/coordination-wave-17.md).

| Scenario ID | TestOps ID |
| --- | --- |
| CAT-UPD-VAL-001 | [55376](https://allure.qa.guru/project/5444/test-cases/55376) |
| CAT-UPD-VAL-002 | [55374](https://allure.qa.guru/project/5444/test-cases/55374) |
| CAT-UPD-VAL-003 | [55375](https://allure.qa.guru/project/5444/test-cases/55375) |
| CAT-UPD-VAL-004 | [55377](https://allure.qa.guru/project/5444/test-cases/55377) |
| CAT-UPD-VAL-005 | [55373](https://allure.qa.guru/project/5444/test-cases/55373) |
| CAT-UPD-VAL-006 | [55378](https://allure.qa.guru/project/5444/test-cases/55378) |

## Историческое состояние после 07

Дата: 2026-11-14. Исполнитель прогонов: агент 07
([handoff](../../handoffs/07-integration.md)).
TestOps ID не назначены: синхронизация и внешняя загрузка в эту волну не
входили; колонка оставлена пустой для заполнения при загрузке существующих
case IDs без создания дублей.

| Scenario ID | Требование | Test node ID | Результат base | Результат base+patch | TestOps ID |
| --- | --- | --- | --- | --- | --- |
| CAT-UPD-VAL-001 | R1, R3 | `tests/api/test_category_update.py::test_update_category_rejects_invalid_name[CAT-UPD-VAL-001]` | FAIL (HTTP 200, имя сохранено) | PASS | |
| CAT-UPD-VAL-002 | R1, R3 | `tests/api/test_category_update.py::test_update_category_rejects_invalid_name[CAT-UPD-VAL-002]` | FAIL (HTTP 200, имя сохранено) | PASS | |
| CAT-UPD-VAL-003 | R2, R3 | `tests/api/test_category_update.py::test_update_category_rejects_invalid_name[CAT-UPD-VAL-003]` | FAIL (HTTP 200, имя сохранено) | PASS | |
| CAT-UPD-VAL-004 | R2, R3 | `tests/api/test_category_update.py::test_update_category_rejects_invalid_name[CAT-UPD-VAL-004]` | FAIL (HTTP 200, имя сохранено) | PASS | |
| CAT-UPD-VAL-005 | R2, R4 | `tests/api/test_category_update.py::test_update_category_accepts_name_at_length_boundary[CAT-UPD-VAL-005]` | не выполнялся | PASS | |
| CAT-UPD-VAL-006 | R2, R4 | `tests/api/test_category_update.py::test_update_category_accepts_name_at_length_boundary[CAT-UPD-VAL-006]` | не выполнялся | PASS | |

Base-прогон: `artifacts/harness/run-3zbyks5d/` (негативные случаи 001–004,
exit 1 — ожидаемый red). Прогон base+patch: `artifacts/harness/run-ucu0gjly/`
(все шесть, exit 0). Идентичность сборок: base SHA
`36674280b6878540a9e88f40aaeedf5dfdd2e6ce`; исправление — незакоммиченный
patch sha256 `04eb4c874139610869793f0c72843b1a9cb338832973697cf56e25b7ba87937e`;
образы — `catupdval-base` / `catupdval-fix` в handoff 07.

## Метаданные кейсов для загрузки в TestOps

Для каждого случая: эпик «Категории», feature «Переименование категории»,
severity Critical, приоритет высокий, уровень — публичный REST API через
gateway. Шаги и ожидаемые результаты — [scenarios.md](scenarios.md);
Allure-результаты содержат шаги и вложения (snapshot до/после, ответ PATCH,
запись cleanup) и являются источником метаданных при синхронизации.

Allure-результаты прогонов:
`artifacts/harness/run-3zbyks5d/allure-results/` (base, негативные),
`artifacts/harness/run-ucu0gjly/allure-results/` (base+patch, все шесть).
JUnit: `junit.xml` в тех же каталогах.
