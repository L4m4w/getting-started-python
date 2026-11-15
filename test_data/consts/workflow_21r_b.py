"""Фиктивные входы для 21R-B unit-регрессий оркестратора (review 21B F1–F6
и 21A F3/F4). Только данные этих тестов: записанный номер PR, вторые
execution id для повторного доведения ревизии, ветки/заголовки спецификаций
и байты повреждённого state. Реальных SHA/ID и кредов нет — все проверки
offline в temp dirs.
"""

# Второй head/base execution для повторного доведения ревизии до executed.
EXECUTION_HEAD_2 = "run-unithead2"
EXECUTION_BASE_2 = "run-unitbase2"
EXECUTION_HEAD_3 = "run-unithead3"

# Записанный remote-эффект: `created` entry с сохранённым номером.
PR_CREATED_NUMBER = 100
PR_PARENT_NUMBER = 42
PR_URL_TEMPLATE = "https://git.invalid/pr/{number}"

HEAD_BRANCH = "wf/head"
BASE_BRANCH = "main"
SPEC_TITLE = "unit PR"
PARENT_SPEC_TITLE = "sent spec"
CHILD_SPEC_TITLE = "new lineage spec"

CORRUPT_STATE_BYTES = b"{not-json"
MUTATED_SOURCE_TEXT = "# mutated source copy\n"

# Маркеры противоречия provenance при повторном import записанного base.
PROVENANCE_A = {"schema_version": "test-prov", "marker": "a"}
PROVENANCE_B = {"schema_version": "test-prov", "marker": "b"}
