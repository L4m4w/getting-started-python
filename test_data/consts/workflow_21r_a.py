"""Фиксированные данные регрессий 21R-A (findings 21A F1/F2/F5).

Повреждённые структуры state.json (revision_data, executions,
publications), ослабленные значения required и границы домена TestOps ID
для envelope bindings. Реальных SHA/ID и секретов нет — только
структурные входы для unit-проверок.
"""

# required: любое значение, кроме JSON true, ослабляет fixed-MVP контракт
# публикаций и не должно давать published ни в schema, ни в прямом gate.
WEAK_REQUIRED_VALUES = (False, None, 0, 1, "true", "yes")

# Пути внутри publications, куда подставляются WEAK_REQUIRED_VALUES.
WEAK_REQUIRED_PATHS = (
    ("testops", "required"),
    ("pr", "app", "required"),
    ("pr", "tests", "required"),
)

# Мутации revision_data: (имя кейса, ключ, значение, фрагмент ошибки).
CORRUPT_REVISION_DATA = (
    ("expected_executions_scalar", "expected_executions", 42,
     "expected_executions must be a list"),
    ("expected_executions_item_non_dict", "expected_executions", [42],
     "must be an object"),
    ("expected_executions_item_string", "expected_executions", ["head"],
     "must be an object"),
    ("expected_executions_bad_variant", "expected_executions",
     [{"variant": "side", "required": True, "scope": "api",
       "expect": {"total": 1}}],
     "variant unsupported"),
    ("expected_executions_required_string", "expected_executions",
     [{"variant": "head", "required": "yes", "scope": "api",
       "expect": {"total": 1}}],
     "required must be a bool"),
    ("expected_executions_required_missing", "expected_executions",
     [{"variant": "head", "scope": "api", "expect": {"total": 1}}],
     "required must be a bool"),
    ("expected_executions_scope_other", "expected_executions",
     [{"variant": "head", "required": True, "scope": "unit",
       "expect": {"total": 1}}],
     "scope must be 'api'"),
    ("expected_executions_scope_missing", "expected_executions",
     [{"variant": "head", "required": True, "expect": {"total": 1}}],
     "scope must be 'api'"),
    ("expected_executions_expect_list", "expected_executions",
     [{"variant": "head", "required": True, "scope": "api",
       "expect": ["total"]}],
     "expect must be an object"),
    ("expected_executions_expect_text", "expected_executions",
     [{"variant": "head", "required": True, "scope": "api",
       "expect": {"total": "6"}}],
     "must be a non-negative int"),
    ("expected_executions_expect_bool", "expected_executions",
     [{"variant": "head", "required": True, "scope": "api",
       "expect": {"total": True}}],
     "must be a non-negative int"),
    ("expected_executions_expect_negative", "expected_executions",
     [{"variant": "head", "required": True, "scope": "api",
       "expect": {"total": -1}}],
     "must be a non-negative int"),
    ("expected_executions_expect_unknown_key", "expected_executions",
     [{"variant": "head", "required": True, "scope": "api",
       "expect": {"xfailed": 1}}],
     "expect key unsupported"),
    ("strength_evidence_list", "strength_evidence", [1, 2],
     "strength_evidence must be an object"),
    ("strength_evidence_string", "strength_evidence", "base",
     "strength_evidence must be an object"),
    ("strength_evidence_incomplete", "strength_evidence",
     {"required": False},
     "variant unsupported"),
    ("strength_evidence_bad_variant", "strength_evidence",
     {"variant": "side", "required": True, "scope": "api",
      "expect": {"total": 1}},
     "variant unsupported"),
    ("strength_evidence_expect_bool", "strength_evidence",
     {"variant": "base", "required": True, "scope": "api",
      "expect": {"failed": False}},
     "must be a non-negative int"),
)

# Мутации executions[0]: (имя кейса, поле, значение, фрагмент ошибки).
CORRUPT_EXECUTION_FIELDS = (
    ("junit_summary_string", "junit_summary", "not-a-dict",
     "junit_summary must be an object"),
    ("junit_summary_list", "junit_summary", [3, 3, 0, 0, 0],
     "junit_summary must be an object"),
    ("junit_summary_missing_key", "junit_summary", {"total": 6},
     "missing keys"),
    ("junit_summary_negative", "junit_summary",
     {"total": -1, "passed": 0, "failed": 0, "errors": 0, "skipped": 0},
     "must be a non-negative int"),
    ("junit_summary_bool", "junit_summary",
     {"total": True, "passed": 0, "failed": 0, "errors": 0,
      "skipped": 0},
     "must be a non-negative int"),
    ("junit_summary_text", "junit_summary",
     {"total": "6", "passed": 0, "failed": 0, "errors": 0,
      "skipped": 0},
     "must be a non-negative int"),
    ("selection_string", "selection", "tests/api",
     "selection must be an object"),
    ("selection_targets_string", "selection", {"targets": "tests/api"},
     "targets must be a list"),
    ("selection_targets_int", "selection", {"targets": [7]},
     "targets must be a list"),
    ("selection_scope_int", "selection", {"scope": 7, "targets": []},
     "scope must be a string"),
    ("bound_revision_bool", "bound_revision", True,
     "bound_revision must be a non-negative int"),
    ("bound_revision_negative", "bound_revision", -1,
     "bound_revision must be a non-negative int"),
)

# Ослабленный/повреждённый состав publications: (имя, путь внутри
# publications, операция, значение, прямой gate обязан отклонить).
# op: "delete" — удалить ключ; "set" — записать значение. Флаг gate
# отличает составные нарушения (False у прямого gate) от целостности
# отдельных digest-полей, которую gate не проверяет.
PUBLICATION_TAMPERS = (
    ("drop_tests_role", ("pr", "tests"), "delete", None, True),
    ("drop_app_role", ("pr", "app"), "delete", None, True),
    ("drop_testops", ("testops",), "delete", None, True),
    ("drop_pr", ("pr",), "delete", None, True),
    ("testops_required_false", ("testops", "required"), "set", False,
     True),
    ("extra_pr_role", ("pr", "ops"), "set",
     {"required": True, "status": "verified",
      "spec": {"head_sha": "b" * 40}, "spec_sha256": "a" * 64,
      "intent_id": None, "number": 1, "url": None}, True),
    ("pr_not_dict", ("pr",), "set", ["app", "tests"], True),
    ("pr_entry_not_dict", ("pr", "app"), "set", "verified", True),
    ("spec_not_dict", ("pr", "app", "spec"), "set", "x", True),
    ("spec_sha256_short", ("pr", "app", "spec_sha256"), "set", "abc",
     False),
    ("testops_execution_id_int", ("testops", "execution_id"), "set", 5,
     True),
)

# TestOps ID: bool запрещён явно, положительные int валидны.
BAD_TESTOPS_IDS = (True, False, 0, -7, "9101", 1.5)
GOOD_TESTOPS_IDS = (1, 9101)
