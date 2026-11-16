"""Фиктивные данные offline unit-проверок TestOps-интеграции; реальных ID нет."""
ENDPOINT = "https://testops.unit.invalid"
PROJECT_ID = 9999
EXECUTION_ID = "run-unit0testops"
LAUNCH_ID = 4242
LAUNCH_NAME = "unit launch"
LAUNCH_URL = f"{ENDPOINT}/launch/{LAUNCH_ID}"
# ID кейсов — фиктивные номера, не из реального проекта 5444.
BOUND_IDS = {f"CAT-UPD-VAL-{i:03d}": 9000 + i for i in range(1, 7)}
UNKNOWN_SCENARIO = "CAT-UPD-VAL-999"
ALLURECTL_PATH = "/opt/unit/bin/allurectl"
TOKEN_ENV = "unit-token"
AQL = 'name ~= "CAT-UPD-VAL"'
ARGPARSE_EXIT = 2
BLOCKED_EXIT = 69
UNKNOWN_EXIT = 75
INTERRUPTED_EXIT = 130
FAILED_CODE = 4
SUCCESS_CODE = 0
