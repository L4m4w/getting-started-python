"""Фиктивные фиксированные входы unit-проверок целостности TestOps-пакета.

Реальных uuID/результатов прогонов здесь нет; значения предназначены только
для offline-тестов. Ожидаемые sha256 зафиксированы для детерминированных
входов helpers из tests/unit/test_testops_package_integrity.py: изменение
формата записи пакета или digest-алгоритма обязано менять константу.
"""

BASE_FULL_NAME = ("tests.api.test_category_update"
                  "#test_update_category_rejects_invalid_name")
BOUNDARY_FULL_NAME = ("tests.api.test_category_update"
                      "#test_update_category_accepts_name_at_length_boundary")
FOREIGN_FULL_NAME = "tests.api.other#test_other"

UNIT_INDEX = {
    "CAT-UPD-VAL-001": {"full_name": BASE_FULL_NAME, "param": "name",
                        "value": ""},
    "CAT-UPD-VAL-002": {"full_name": BASE_FULL_NAME, "param": "name",
                        "value": "A"},
    "CAT-UPD-VAL-005": {"full_name": BOUNDARY_FULL_NAME, "param": "name",
                        "value": "AA"},
}
SCENARIO_IDS = tuple(UNIT_INDEX)
RESULT_UUIDS = {
    "CAT-UPD-VAL-001": "11111111-0000-4000-8000-000000000001",
    "CAT-UPD-VAL-002": "11111111-0000-4000-8000-000000000002",
    "CAT-UPD-VAL-005": "11111111-0000-4000-8000-000000000005",
}
EXTRA_UUID = "22222222-0000-4000-8000-000000000099"
BOUND_IDS = {"CAT-UPD-VAL-001": 9101, "CAT-UPD-VAL-002": 9102,
             "CAT-UPD-VAL-005": 9105}
RESULT_TITLE = "unit title"
ATTACHMENT_NAME = "aaaaaaaa-0000-4000-8000-00000000000a-attachment.txt"
ATTACHMENT_BODY = "unit attachment payload"
NESTED_ATTACHMENT = "dddddddd-0000-4000-8000-00000000000d-attachment.txt"
NESTED_ATTACHMENT_BODY = "nested attachment payload"
FIXTURE_ATTACHMENT = "cccccccc-0000-4000-8000-00000000000c-attachment.txt"
FIXTURE_ATTACHMENT_BODY = "fixture attachment payload"
CONTAINER_NAME = "bbbbbbbb-0000-4000-8000-00000000000b-container.json"
CORRUPT_JSON = "{not-json"
NON_OBJECT_JSON = "[1, 2, 3]"
ESCAPING_SOURCE = "../escape.txt"
ABSOLUTE_SOURCE = "/etc/hostname"
# Golden-идентичность детерминированных входов; см. docstring модуля.
EXPECTED_INPUT_SHA256 = (
    "63d4ca228df3dc52d54e7e7cbb7eed9f81d2145a17ebcf73a411788eb55e9456")
EXPECTED_BIND_ASSIGNMENTS_SHA256 = (
    "fea18a6cbfa2b59995ff0457b105e709b110d6e8d3320923d5f0ac4d0a4b11e1")
EXPECTED_ISOLATE_PACKAGE_SHA256 = (
    "050210de172b8d1bdec496db52f5788691e8a54b64f07d5eb01e4457172b03db")
EXPECTED_BIND_PACKAGE_SHA256 = (
    "a5ed941a36ba821d89f07c5965d0cb5c543c8c161018521fcd5a49b417813e72")
