"""Данные пилота CAT-UPD-VAL и его OAuth-клиента."""
OAUTH_CLIENT_ID = "client"
OAUTH_REDIRECT_URI = "http://frontend.niffler.dc/authorized"
OAUTH_SCOPE = "openid"
INVALID_NAMES = ("", "   ", "A", "A" * 51)
VALID_NAMES = ("AA", "A" * 50)
INVALID_IDS = tuple(f"CAT-UPD-VAL-{i:03d}" for i in range(1, 5))
VALID_IDS = tuple(f"CAT-UPD-VAL-{i:03d}" for i in range(5, 7))
# Согласованные ID кейсов TestOps project 5444 (coordination wave 12).
TESTOPS_ALLURE_IDS = {
    "CAT-UPD-VAL-001": "55376",
    "CAT-UPD-VAL-002": "55374",
    "CAT-UPD-VAL-003": "55375",
    "CAT-UPD-VAL-004": "55377",
    "CAT-UPD-VAL-005": "55373",
    "CAT-UPD-VAL-006": "55378",
}
# Значение параметра name → ALLURE_ID для runtime-разметки параметризованных
# кейсов; сценарий определяется значением name, как в testops-маппинге.
TESTOPS_ALLURE_ID_BY_NAME = {
    name: TESTOPS_ALLURE_IDS[scenario_id]
    for names, scenario_ids in ((INVALID_NAMES, INVALID_IDS), (VALID_NAMES, VALID_IDS))
    for name, scenario_id in zip(names, scenario_ids)}
SNAPSHOT_FIELDS = ("id", "name", "username", "archived")
CATEGORY_NAME_PREFIX = "catupd-"
MAX_ACTIVE_CATEGORIES = 8
# Фиктивные ответы только для офлайн unit-проверок.
UNIT_ORIGIN = "http://localhost:8090"
UNIT_JSON = b'{"name":"AA"}'
UNIT_ERROR_BODY = b'not-json'
UNIT_TOKEN = "offline-token"
UNIT_CATEGORY_ID = "06fe9c06-ae67-406e-a711-ba729e3d4775"
UNIT_CATEGORY = dict(id=UNIT_CATEGORY_ID, name="initial", username="pilot", archived=False)
UNIT_LOGIN_HTML = b'<form action="/login"><input name="username"><input name="password"><input type="hidden" name="_csrf" value="csrf"></form>'
UNIT_CONSENT_HTML = b'<form action="/oauth2/authorize"><input type="hidden" name="client_id" value="client"><input type="hidden" name="state" value="state"><input type="hidden" name="_csrf" value="csrf"><input type="checkbox" name="scope" value="openid"><input type="submit" name="cancel" value="cancel"></form>'
UNIT_PASSWORD = "offline"
UNIT_BAD_ORIGINS = ("http://localhost:8090/a", "http://localhost:8090?x=1", "http://localhost:wrong", "http://user:pass@localhost")
UNIT_FOREIGN_LOCATION = "http://foreign.invalid/login"
