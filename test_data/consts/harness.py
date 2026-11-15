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
API_SELECTION = ("tests/api",)
# Подменный набор контрактных исходников API и один отсутствующий файл.
API_CONTRACT_SOURCES = MappingProxyType({
    "tests/api/test_category_update.py": "def test_case():\n    pass\n",
    "tests/api/conftest.py": "import pytest\n",
    "infrastructure/http/client.py": "class HttpClient:\n    pass\n",
    "requirements.txt": "pytest==9.1.1\n",
})
MISSING_CONTRACT_SOURCE = "tests/api/test_missing.py"
ENV_FILENAME = ".env"
APP_BASE_SHA = "b" * 40
APP_PATCH_SHA256 = "d" * 64
GATEWAY_IMAGE_ID = "f" * 12
GATEWAY_IMAGE_MISMATCH = "0" * 12
GATEWAY_CONTAINER = "catupdval-gateway-1"
CONTAINER_ID = "e" * 64
IMAGE_ID_FULL = "sha256:" + "f" * 64
IMAGE_TAG = "qaguru/niffler-gateway-docker:catupdval-fix"
# Ответ `docker container inspect` с секретным полем Env: в evidence
# сохраняются только дистиллированные поля.
DOCKER_INSPECT = MappingProxyType({
    "Id": CONTAINER_ID,
    "Name": f"/{GATEWAY_CONTAINER}",
    "Image": IMAGE_ID_FULL,
    "State": MappingProxyType({"Running": True}),
    "Config": MappingProxyType({"Image": IMAGE_TAG,
                                "Env": (f"API_PASSWORD={PRIVATE_VALUE}",)}),
})
NO_SUCH_CONTAINER_STDERR = "Error: No such container: gateway"
DAEMON_DOWN_STDERR = "Cannot connect to the Docker daemon"
INVALID_SHA = "not-a-sha"
INVALID_CONTAINER_REF = "bad/name!"
