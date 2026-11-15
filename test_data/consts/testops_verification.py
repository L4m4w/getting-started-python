"""Фиктивные snapshot-данные unit-проверок верификации TestOps.

Форма dict повторяет контракт ``read_snapshot`` (волна 15, handoff 14B);
все идентификаторы вымышленные и не относятся к проекту 5444.
"""
ENDPOINT = "https://testops.verify.invalid"
PROJECT_ID = 6666
OTHER_PROJECT_ID = 5555
EXECUTION_ID = "run-unitverify"
LAUNCH_ID = 4243
OTHER_LAUNCH_ID = 88888
LAUNCH_NAME = "verification unit launch"
LAUNCH_URL = f"{ENDPOINT}/launch/{LAUNCH_ID}"

# Три сценария с разными статусами — ожидаемая серверная сводка.
SCENARIO_IDS = ("CAT-UPD-VAL-001", "CAT-UPD-VAL-002", "CAT-UPD-VAL-003")
SCENARIO_STATUSES = {
    "CAT-UPD-VAL-001": "passed",
    "CAT-UPD-VAL-002": "failed",
    "CAT-UPD-VAL-003": "skipped",
}
BOUND_IDS = {scenario_id: 9200 + index
             for index, scenario_id in enumerate(SCENARIO_IDS, start=1)}
EXPECTED_STATS = {"passed": 1, "failed": 1, "skipped": 1}
# Сценарий с совпадающим префиксом: не должен считаться CAT-UPD-VAL-001.
SID_LOOKALIKE = "CAT-UPD-VAL-0010"
CANDIDATE_CASE_ID = 7100
RESULT_ID_BASE = 5000
RESULT_TITLE = "unit scenario title"


def result_row(index, scenario_id, *, status=None, case_id="bound",
               launch_id=LAUNCH_ID, project_id=PROJECT_ID, hidden=False,
               retried_by_id=None, name=None):
    """Строка results по контракту read_snapshot."""
    if case_id == "bound":
        case_id = BOUND_IDS[scenario_id]
    elif case_id == "candidate":
        case_id = CANDIDATE_CASE_ID + index
    return {
        "id": RESULT_ID_BASE + index,
        "name": name if name is not None
        else f"{scenario_id}: {RESULT_TITLE}",
        "status": status if status is not None
        else SCENARIO_STATUSES[scenario_id],
        "test_case_id": case_id,
        "launch_id": launch_id,
        "project_id": project_id,
        "hidden": hidden,
        "retried_by_id": retried_by_id,
    }


def rows(case_ids="bound"):
    """По одной строке на каждый ожидаемый сценарий."""
    return [result_row(index, scenario_id, case_id=case_ids)
            for index, scenario_id in enumerate(SCENARIO_IDS, start=1)]


def snapshot(rows_list="bound", *, outcome="complete",
             reason="probe ok", launch="auto", ready=True,
             stats="expected", closed=True, launch_id=LAUNCH_ID,
             project_id=PROJECT_ID, complete=True, pages=1,
             total="auto"):
    """Нормализованный dict по контракту read_snapshot."""
    if rows_list == "bound":
        rows_list = rows("bound")
    elif rows_list == "candidate":
        rows_list = rows("candidate")
    elif rows_list is None:
        rows_list = []
    if launch == "auto":
        launch = {"id": launch_id, "project_id": project_id,
                  "closed": closed}
    if stats == "expected":
        stats = dict(EXPECTED_STATS)
    if total == "auto":
        total = len(rows_list)
    return {
        "outcome": outcome,
        "reason": reason,
        "launch": launch,
        "ready": ready,
        "stats": stats,
        "results": [dict(row) for row in rows_list],
        "pagination": {"complete": complete, "pages": pages,
                       "total_elements": total},
    }


# Некорректное доказательство полноты: нет прочитанных страниц или total.
UNPROVEN_PAGINATION = (
    {"complete": True, "pages": 0, "total_elements": len(SCENARIO_IDS)},
    {"complete": True, "pages": 1, "total_elements": None},
)
