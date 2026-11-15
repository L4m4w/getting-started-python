"""Фиктивные входы unit-проверок оркестратора; реальных SHA/ID нет.

Все идентификаторы, хеши и пути вымышленные и не относятся к проекту
Niffler или TestOps 5444. Используются только в temp dirs unit-тестов.
"""
PILOT_ID = "unit-pilot"
OTHER_PILOT_ID = "unit-pilot-2"
APP_REPO = "https://git.invalid/Org/Unit-App.git"
APP_REPO_SSH = "git@git.invalid:Org/Unit-App.git"
APP_REPO_KEY = "git.invalid/Org/Unit-App"
APP_BASE_SHA = "a" * 40
APP_BASE_SHA_2 = "b" * 40
APP_HEAD_COMMIT_SHA = "1" * 40
APP_HEAD_COMMIT_SHA_2 = "2" * 40
NON_COMMIT_OBJECT_SHA = "3" * 40
MISSING_COMMIT_SHA = "4" * 40
WRONG_TREE_COMMIT_SHA = "5" * 40
APP_PATCH_SHA256 = "c" * 64
APP_PATCH_SHA256_2 = "d" * 64
TESTS_COMMIT = "e" * 40
TESTS_COMMIT_2 = "f" * 40
REQUIREMENTS_REL = "docs/unit-requirement.md"
REQUIREMENT_IDS = ["R1", "R2"]
REQUIREMENTS_TEXT = (
    "Таблица требований\n| R1 | имя непустое |\n| R2 | длина 2-50 |\n"
)
SCENARIO_IDS = ["UNIT-VAL-001", "UNIT-VAL-002", "UNIT-VAL-003"]
BASE_SCENARIO_IDS = ["UNIT-VAL-001", "UNIT-VAL-002"]
SCENARIO_COVERAGE = {
    "R1": ["UNIT-VAL-001", "UNIT-VAL-002"],
    "R2": ["UNIT-VAL-003"],
}
BINDINGS = {
    "UNIT-VAL-001": 9101,
    "UNIT-VAL-002": 9102,
    "UNIT-VAL-003": 9103,
}
CONTEXT_SOURCE_PATHS = ("src/main/Controller.java", "src/main/Dto.java")
CHANGED_APP_FILE = "src/main/Controller.java"
TEST_FILES = ["tests/api/test_unit_val.py"]
TEST_FILE_CONTENT = "# unit test placeholder\n"
NODE_ID = "tests/api/test_unit_val.py::TestUnitVal::test_case[{sid}]"
EXECUTION_HEAD = "run-unithead1"
EXECUTION_BASE = "run-unitbase1"
EXECUTION_OTHER = "run-unitother"
TESTOPS_ENDPOINT = "https://testops.unit.invalid"
TESTOPS_PROJECT_ID = 7777
PACKAGE_DIR_NAME = "upload-results"

UNIT_SCENARIO_CONTRACT_VERSION = "unit-val-scenarios-v1"
UNIT_SCENARIO_INDEX = {
    "UNIT-VAL-001": {
        "full_name": "tests.api.test_unit_val#test_rejects_invalid",
        "param": "value",
        "value": "",
    },
    "UNIT-VAL-002": {
        "full_name": "tests.api.test_unit_val#test_rejects_invalid",
        "param": "value",
        "value": "A",
    },
    "UNIT-VAL-003": {
        "full_name": "tests.api.test_unit_val#test_accepts_boundary",
        "param": "value",
        "value": "AA",
    },
}
# Русские display titles без scenario ID — как у реального пилота Niffler.
UNIT_DISPLAY_TITLES = {
    "UNIT-VAL-001": "Невалидное значение отклоняется без изменения состояния",
    "UNIT-VAL-002": "Невалидное значение отклоняется без изменения состояния",
    "UNIT-VAL-003": "Допустимое граничное значение сохраняется",
}

EXPECTED_EXECUTIONS = [
    {"variant": "head", "required": True, "scope": "api",
     "expect": {"total": 3, "passed": 3, "failed": 0, "errors": 0}},
]
STRENGTH_EVIDENCE = {
    "variant": "base", "required": True, "scope": "api",
    "expect": {"total": 2, "failed": 2},
}
HEAD_JUNIT = {"total": 3, "passed": 3, "failed": 0, "errors": 0,
              "skipped": 0}
BASE_JUNIT = {"total": 2, "passed": 0, "failed": 2, "errors": 0,
              "skipped": 0}
UNIT_JUNIT_SAME_COUNTS = {"total": 3, "passed": 3, "failed": 0,
                          "errors": 0, "skipped": 0}

# Фиксированные константы для 20R2 regression tests (санитизированы, без кредов).
PILOT_INVALID_TITLE = "Невалидное имя отклоняется без изменения snapshot"
PILOT_VALID_TITLE = "Имя длиной 2 или 50 сохраняется для прежнего ID"
LOOKALIKE_SCENARIO_ID = "UNIT-VAL-0010"
FOREIGN_SCENARIO_ID = "FOREIGN-VAL-999"
FALSE_BINDING_ID = 99999
REVIEW_WAVE_REL = "docs/review-wave-baseline.md"
REVIEW_WAVE_TEXT = "# Baseline review acceptance\nStatus: accepted.\n"
HISTORICAL_TEST_CONTENT = "# pre-allure-id historical test content\n"

