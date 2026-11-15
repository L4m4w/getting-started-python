"""Фиксированные входы и ожидания unit-тестов Java evidence."""
from types import MappingProxyType

APP_REPO_STATE = MappingProxyType({"commit": "b" * 40, "dirty": True})
WRAPPER_VERSION = "8.6"
JAVA_VERSION_LINE = 'openjdk version "21.0.12.1" 2026-07-15 LTS'
MODULE = "niffler-gateway"
TEST_CLASS = "guru.qa.niffler.controller.CategoriesControllerValidationTest"
TEST_SELECTOR_METHOD = f"{TEST_CLASS}.rejectsBlankName"
TEST_FILE_RELPATH = ("niffler-gateway/src/test/java/guru/qa/niffler/controller/"
                     "CategoriesControllerValidationTest.java")
TARGET_RELPATH = ("niffler-gateway/src/main/java/guru/qa/niffler/controller/"
                  "CategoriesController.java")
TARGET_SOURCE = "public class CategoriesController {}"
TEST_SOURCE = "class CategoriesControllerValidationTest {}"
PATCH_TEXT = "diff --git a/pom b/pom\n+change\n"
LABEL_BASELINE = "baseline"
LABEL_HEAD = "head"
EXPECTED_TASK = f":{MODULE}:test"
EXPECTED_COMMAND = ["sh", "gradlew", f":{MODULE}:cleanTest", EXPECTED_TASK,
                    "--tests", TEST_CLASS, "--no-build-cache", "--rerun-tasks", "--no-daemon"]
JUNIT_GRADLE = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="guru.qa.niffler.controller.CategoriesControllerValidationTest" tests="4" skipped="1" failures="1" errors="1">
<testcase name="valid" classname="x"/>
<testcase name="bad" classname="x"><failure message="expected 400">private-value</failure></testcase>
<testcase name="broken" classname="x"><error/></testcase>
<testcase name="missed" classname="x"><skipped/></testcase>
</testsuite>
"""
JUNIT_FILENAME = f"TEST-{TEST_CLASS}.xml"
SECOND_JUNIT_FILENAME = "TEST-AnotherClass.xml"
INVALID_JUNIT = "<testsuite"
PROCESS_PID = 123456
EXPECTED_SUMMARY = MappingProxyType(
    {"total": 4, "passed": 1, "failed": 1, "errors": 1, "skipped": 1}
)
UP_TO_DATE_LOG = "> Task :niffler-gateway:test UP-TO-DATE\n"
SUCCESS_EXIT_CODE = 0
FAILED_EXIT_CODE = 1
LAUNCH_EXIT_CODE = 127
INTERRUPT_EXIT_CODE = 130
LAUNCH_FAILURE_CASES = (
    (OSError(), LAUNCH_EXIT_CODE, "launch_error"),
    (KeyboardInterrupt(), INTERRUPT_EXIT_CODE, "interrupted"),
)
EXPECTED_RUN_COUNT = 2
BLOCKED_EXIT_CODE = 69
INVALID_MODULE = "niffler gateway;rm"
INVALID_SELECTOR = "guru qa;rm -rf"
ARGPARSE_EXIT_CODE = 2
