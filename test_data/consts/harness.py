"""Фиксированные входы и ожидания unit-тестов локального harness."""
from types import MappingProxyType

REPOSITORY_STATE = MappingProxyType({"commit": "a" * 40, "dirty": True})
UNIT_SELECTION = ("tests/unit",)
PRIVATE_PARAMETER_SELECTION = ("tests/unit/test_example.py::test_case[private-value]",)
PRIVATE_VALUE = "private-value"
PRIVATE_ENV_KEY = "HARNESS_TEST_PRIVATE"
UNSAFE_BROWSER_VERSION = "https://user:private-value@example.org/wd/hub"
JUNIT_MIXED = """<testsuites><testsuite>
<testcase name="ok"/>
<testcase name="bad"><failure>private-value</failure></testcase>
<testcase name="setup"><error/></testcase>
<testcase name="skip"><skipped/></testcase>
</testsuite></testsuites>"""
JUNIT_INVALID = "<testsuites>"
EXPECTED_SUMMARY = MappingProxyType(
    {"total": 4, "passed": 1, "failed": 1, "errors": 1, "skipped": 1}
)
FAILED_EXIT_CODE = 1
SUCCESS_EXIT_CODE = 0
LAUNCH_EXIT_CODE = 127
INTERRUPT_EXIT_CODE = 130
LAUNCH_FAILURE_CASES = (
    (OSError(), LAUNCH_EXIT_CODE, "launch_error"),
    (KeyboardInterrupt(), INTERRUPT_EXIT_CODE, "interrupted"),
)
EXPECTED_RUN_COUNT = 2
