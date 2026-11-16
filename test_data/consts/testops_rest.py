"""Фиктивные данные unit-проверок REST probe TestOps; реальных ID нет.

Payload'ы повторяют форму OpenAPI allure-testops-service 527u01
(LaunchDto, LaunchProgressDto, TestStatusCount[], Spring Page of
TestResultDto), но все идентификаторы, токены и JWT вымышленные и не
относятся к проекту 5444.
"""
ENDPOINT = "https://testops.rest.invalid"
API_TOKEN = "unit-api-token"
JWT = "unit-jwt-value"
LAUNCH_ID = 31337
OTHER_LAUNCH_ID = 99999
PROJECT_ID = 7777
PAGE_SIZE = 2
MAX_PAGES = 4

TOKEN_PATH = "/api/uaa/oauth/token"
LAUNCH_PATH = f"/api/launch/{LAUNCH_ID}"
PROGRESS_PATH = f"/api/launch/{LAUNCH_ID}/progress"
STATISTIC_PATH = f"/api/launch/{LAUNCH_ID}/statistic"


def results_path(page, launch_id=LAUNCH_ID, size=PAGE_SIZE):
    """Подтверждённые параметры GET /api/testresult; sort не выдумывается."""
    return (f"/api/testresult?launchId={launch_id}&page={page}"
            f"&size={size}")


TOKEN_OK = {"access_token": JWT, "token_type": "Bearer", "expires_in": 3600,
            "scope": "openid", "jti": "unit-jti"}
TOKEN_WRONG_TYPE = {"access_token": JWT, "token_type": "mac"}
TOKEN_NO_ACCESS = {"token_type": "Bearer", "expires_in": 3600}

LAUNCH = {"id": LAUNCH_ID, "name": "unit launch", "projectId": PROJECT_ID,
          "closed": True, "createdDate": 1760000000000,
          "lastModifiedDate": 1760000000001, "tags": []}
LAUNCH_OPEN = dict(LAUNCH, closed=False)
LAUNCH_WRONG_ID = dict(LAUNCH, id=OTHER_LAUNCH_ID)
LAUNCH_NO_CLOSED = {key: value for key, value in LAUNCH.items()
                    if key != "closed"}
LAUNCH_NO_PROJECT = {key: value for key, value in LAUNCH.items()
                     if key != "projectId"}

PROGRESS_READY = {"ready": True}
PROGRESS_NOT_READY = {"ready": False}
PROGRESS_NO_READY = {"phase": "processing"}
PROGRESS_STRING_READY = {"ready": "true"}

# TestStatusCount[] → {"passed": 2, "failed": 1, "in_progress": 1}.
STATISTIC = [{"status": "passed", "count": 2},
             {"status": "failed", "count": 1},
             {"status": "in_progress", "count": 1}]
STATISTIC_EMPTY = []
STATISTIC_DUP = [{"status": "passed", "count": 1},
                 {"status": "passed", "count": 2}]
STATISTIC_NEGATIVE = [{"status": "passed", "count": -1}]
STATISTIC_NOT_LIST = {"passed": 2}
EXPECTED_STATS = {"passed": 2, "failed": 1, "in_progress": 1}


def result_item(result_id, name="CAT-UPD-VAL-001: unit", status="passed",
                test_case_id=9101, launch_id=LAUNCH_ID,
                project_id=PROJECT_ID, hidden=False, retried_by=None):
    """Минимальный TestResultDto allowlist-набора плюс лишние поля."""
    item = {"id": result_id, "name": name, "status": status,
            "testCaseId": test_case_id, "launchId": launch_id,
            "projectId": project_id, "hidden": hidden,
            "fullName": "should#not survive", "message": "dropped",
            "trace": "dropped", "parameters": [{"name": "p"}],
            "duration": 12}
    if retried_by is not None:
        item["retriedBy"] = retried_by
    else:
        item["retriedBy"] = None
    return item


def page(number, content, total_elements, total_pages, last,
         size=PAGE_SIZE):
    """Spring Page wrapper в форме PageTestResultDto."""
    return {"content": content, "number": number, "size": size,
            "numberOfElements": len(content), "totalElements": total_elements,
            "totalPages": total_pages, "first": number == 0, "last": last,
            "empty": not content, "sort": {"sorted": True},
            "pageable": {"pageNumber": number, "pageSize": size}}


RESULT_A = result_item(101, name="CAT-UPD-VAL-001: ok", status="passed")
RESULT_B = result_item(102, name="CAT-UPD-VAL-002: bad", status="failed",
                       test_case_id=9102)
RESULT_C = result_item(103, name="CAT-UPD-VAL-003: wip",
                       status="in_progress", test_case_id=None,
                       hidden=True, retried_by={"id": 55, "name": "r"})
RESULT_FOREIGN_LAUNCH = result_item(105, launch_id=OTHER_LAUNCH_ID)

# Две полные страницы: 3 результата при size=2.
PAGE0_FULL = page(0, [RESULT_A, RESULT_B], 3, 2, last=False)
PAGE1_LAST = page(1, [RESULT_C], 3, 2, last=True)
PAGES_TWO = [PAGE0_FULL, PAGE1_LAST]

# Пустая страница до конца обхода — обход неполон.
PAGE0_EMPTY_EARLY = page(0, [], 3, 2, last=False)
# Легитимный пустой набор: totalElements=0, last=true.
PAGE0_EMPTY_DONE = page(0, [], 0, 0, last=True)
# Повтор запрошенной страницы: сервер вернул number != page.
PAGE1_ECHO_0 = page(0, [RESULT_C], 3, 2, last=True)
# Повтор ID результата на следующей странице.
PAGE1_DUP_ID = page(1, [result_item(101, name="CAT-UPD-VAL-009: again")],
                    3, 2, last=True)
# Изменение totals между страницами.
PAGE1_SHIFTED = page(1, [RESULT_C], 4, 2, last=True)
# last=true не на последней по totalPages странице.
PAGE0_LAST_EARLY = page(0, [RESULT_A, RESULT_B], 3, 2, last=True)
# last=false там, где totalPages не оставляет следующей страницы.
PAGE0_NOT_LAST_END = page(0, [RESULT_A, RESULT_B], 2, 1, last=False)
# Обход без last-страницы: сервер всегда обещает продолжение — проверка
# ограничения MAX_PAGES.
PAGES_NO_END = [page(index, [result_item(200 + index)], 10, 10,
                     last=False)
                for index in range(MAX_PAGES)]
# Второй элемент страницы без обязательного поля: первый уже нормализован.
PAGE0_BAD_FIELD = page(
    0, [RESULT_A,
        {key: value for key, value in RESULT_B.items() if key != "hidden"}],
    3, 2, last=False)
# Результат с чужим launchId.
PAGE0_FOREIGN = page(0, [RESULT_FOREIGN_LAUNCH], 1, 1, last=True)
