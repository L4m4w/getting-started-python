import json

import allure
import pytest

from infrastructure.http.client import PreparationError
from test_data.consts.category_update import (
    INVALID_IDS, INVALID_NAMES, TESTOPS_ALLURE_ID_BY_NAME, VALID_IDS, VALID_NAMES)
from tests.api.conftest import category_snapshot


def attach_evidence(before, response, after=None, read_error=None):
    # Только поля категории и ответ PATCH; HTTP-заголовки/авторизация не пишутся.
    evidence = dict(before=before, patch_status=response.status,
                    patch_body=response.body.decode(errors="replace"), after=after,
                    read_error=read_error)
    allure.attach(json.dumps(evidence, ensure_ascii=False), "PATCH и повторный GET", allure.attachment_type.JSON)


@allure.epic("Категории")
@allure.feature("Переименование категории")
@allure.story("R1/R2/R3: невалидное имя не сохраняется")
@allure.severity(allure.severity_level.CRITICAL)
@allure.title("Невалидное имя отклоняется без изменения snapshot")
@pytest.mark.parametrize("name", INVALID_NAMES, ids=INVALID_IDS)
def test_update_category_rejects_invalid_name(name, own_category, categories_api):
    with allure.step("Привязать сценарий к кейсу TestOps"):
        allure.dynamic.label("ALLURE_ID", TESTOPS_ALLURE_ID_BY_NAME[name])
    with allure.step("Выполнить PATCH с невалидным именем"):
        before = own_category
        response = categories_api.update({**before, "name": name})
    with allure.step("Сохранить ответ PATCH и повторно прочитать категорию до assertions"):
        attach_evidence(before, response)
        try:
            after = category_snapshot(categories_api, before["id"])
        except PreparationError as error:
            attach_evidence(before, response, read_error=str(error))
            raise
        attach_evidence(before, response, after)
    with allure.step("Проверить HTTP 400 и неизменность сохранённых полей"):
        assert response.status == 400, f"Ожидался HTTP 400, получен {response.status}; snapshot в evidence"
        assert after == before, f"Категория изменилась: {before!r} → {after!r}"


@allure.epic("Категории")
@allure.feature("Переименование категории")
@allure.story("R2/R4: граничное допустимое имя сохраняется")
@allure.severity(allure.severity_level.CRITICAL)
@allure.title("Имя длиной 2 или 50 сохраняется для прежнего ID")
@pytest.mark.parametrize("name", VALID_NAMES, ids=VALID_IDS)
def test_update_category_accepts_name_at_length_boundary(name, own_category, categories_api):
    with allure.step("Привязать сценарий к кейсу TestOps"):
        allure.dynamic.label("ALLURE_ID", TESTOPS_ALLURE_ID_BY_NAME[name])
    with allure.step("Выполнить PATCH с допустимым граничным именем"):
        before = own_category
        response = categories_api.update({**before, "name": name})
        attach_evidence(before, response)
    with allure.step("Проверить HTTP 200 перед разбором успешного ответа"):
        assert response.status == 200, f"Ожидался HTTP 200, получен {response.status}"
    with allure.step("Повторным GET проверить сохранённое имя и остальные поля"):
        after = category_snapshot(categories_api, before["id"])
        attach_evidence(before, response, after)
        assert after == {**before, "name": name}, f"Неожиданный snapshot: {after!r}"
    with allure.step("Проверить вторичный контракт тела PATCH"):
        body = response.json()
        assert body.get("id") == before["id"] and body.get("name") == name, "Нарушен контракт тела PATCH"
