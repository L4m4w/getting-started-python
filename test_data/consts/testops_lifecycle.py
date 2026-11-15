"""Фиктивные данные unit-проверок TestOps upload lifecycle; реальных ID нет.

Сценарии и payload'ы повторяют форму state.json и вывода allurectl, но все
идентификаторы вымышленные и не относятся к проекту 5444.
"""
ENDPOINT = "https://testops.lifecycle.invalid"
PROJECT_ID = 7777
OTHER_PROJECT_ID = 8888
EXECUTION_ID = "run-unitlifecycle"
LAUNCH_ID = 31337
OTHER_LAUNCH_ID = 99999
LAUNCH_NAME = "lifecycle unit launch"
LAUNCH_URL = f"{ENDPOINT}/launch/{LAUNCH_ID}"
ALLURECTL_PATH = "/opt/unit/bin/allurectl"

# Три сценария: два passed и один failed — ожидаемая серверная сводка.
SCENARIO_IDS = ("CAT-UPD-VAL-001", "CAT-UPD-VAL-002", "CAT-UPD-VAL-003")
SCENARIO_STATUSES = {
    "CAT-UPD-VAL-001": "passed",
    "CAT-UPD-VAL-002": "passed",
    "CAT-UPD-VAL-003": "failed",
}
BOUND_IDS = {scenario_id: 9100 + index
             for index, scenario_id in enumerate(SCENARIO_IDS, start=1)}
EXPECTED_STATS = {"passed": 2, "failed": 1}

PACKAGE_SHA256 = "f" * 64


def launch_payload(stats=None, launch_id=LAUNCH_ID, project_id=PROJECT_ID,
                   include_project=True):
    """Словарь ответа `launch get -o json` для подмены транспорта."""
    payload = {"id": launch_id, "name": LAUNCH_NAME}
    if include_project:
        payload["projectId"] = project_id
    if stats is not None:
        payload["statistic"] = dict(stats)
    return payload


LAUNCH_MATCHING = launch_payload(stats=EXPECTED_STATS)
LAUNCH_EMPTY = launch_payload(
    stats={"passed": 0, "failed": 0, "broken": 0, "skipped": 0})
LAUNCH_PARTIAL = launch_payload(stats={"passed": 1, "failed": 0})
LAUNCH_OVERDELIVERED = launch_payload(stats={"passed": 3, "failed": 1})
LAUNCH_NO_STATS = launch_payload()
LAUNCH_WRONG_ID = launch_payload(stats=EXPECTED_STATS,
                                 launch_id=OTHER_LAUNCH_ID)
LAUNCH_WRONG_PROJECT = launch_payload(stats=EXPECTED_STATS,
                                      project_id=OTHER_PROJECT_ID)
LAUNCH_NO_PROJECT = launch_payload(stats=EXPECTED_STATS,
                                   include_project=False)


def result_entries(bound=True):
    """Per-result наблюдения, совпадающие с ожидаемым набором сценариев."""
    entries = []
    for scenario_id in SCENARIO_IDS:
        entries.append({
            "name": f"{scenario_id}: unit title",
            "status": SCENARIO_STATUSES[scenario_id],
            "test_case_id": BOUND_IDS[scenario_id] if bound else 7000 + 1,
        })
    return entries


RESULTS_MATCHING_BIND = result_entries(bound=True)
RESULTS_WRONG_CASE = [
    {**entry, "test_case_id": entry["test_case_id"] + 5000}
    for entry in result_entries(bound=True)]

DEAD_PID = 999999
BLOCKED_EXIT = 69
FAILED_CODE = 4
INTERRUPTED_EXIT = 130
SUCCESS_CODE = 0
