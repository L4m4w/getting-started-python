from uuid import uuid4

import allure
from selenium.webdriver.support import expected_conditions as EC

from pages.login_page import LoginPage

USERNAME = "stas"
PASSWORD = "12345"


@allure.epic("Niffler")
@allure.feature("Авторизация")
class TestLogin:

    @allure.story("Успешный логин")
    @allure.severity(allure.severity_level.BLOCKER)
    @allure.title("Логин с валидными кредами")
    def test_success_login(self, driver, wait):
        main_page = LoginPage(driver).open().login(USERNAME, PASSWORD)

        with allure.step("Проверить заголовок истории трат"):
            wait.until(EC.text_to_be_present_in_element(
                main_page.spendings_section, "History of Spendings"
            ))

    @allure.story("Успешный логин")
    @allure.severity(allure.severity_level.CRITICAL)
    @allure.title("Логин с отправкой формы клавишей Enter")
    def test_success_login_with_press_enter(self, driver, wait):
        main_page = LoginPage(driver).open().login_with_enter(USERNAME, PASSWORD)

        with allure.step("Проверить заголовок истории трат"):
            wait.until(EC.text_to_be_present_in_element(
                main_page.spendings_section, "History of Spendings"
            ))

    @allure.story("Невалидные креды")
    @allure.severity(allure.severity_level.NORMAL)
    @allure.title("Логин с неверным паролем показывает ошибку")
    def test_wrong_credentials(self, driver, wait):
        login_page = LoginPage(driver).open()
        login_page.fill_username(USERNAME).fill_password("12345sgsrgwr").submit_with_enter()

        with allure.step("Проверить текст ошибки"):
            # текст ошибки зависит от локали браузера (ru/en)
            error = wait.until(EC.visibility_of_element_located(login_page.error_message))
            wait.until(lambda _: error.text.strip() != "")
            assert error.text in ("Bad credentials", "Неверные учетные данные пользователя"), \
                f"Unexpected error text: {error.text!r}"

    @allure.story("Невалидные креды")
    @allure.severity(allure.severity_level.NORMAL)
    @allure.title("Логин с несуществующим пользователем показывает ошибку")
    def test_login_with_unknown_username(self, driver, wait):
        login_page = LoginPage(driver).open()
        username = f"unknown_{uuid4().hex}"
        login_page.fill_username(username).fill_password(PASSWORD).submit()

        with allure.step("Проверить текст ошибки"):
            error = wait.until(EC.visibility_of_element_located(login_page.error_message))
            wait.until(lambda _: error.text.strip() != "")
            assert error.text in ("Bad credentials", "Неверные учетные данные пользователя"), \
                f"Unexpected error text: {error.text!r}"

    @allure.story("Успешный логин")
    @allure.severity(allure.severity_level.CRITICAL)
    @allure.title("Успешный логин после исправления неверного пароля")
    def test_success_login_after_wrong_password(self, driver, wait):
        login_page = LoginPage(driver).open()
        login_page.fill_username(USERNAME).fill_password(f"{PASSWORD}_wrong").submit()

        with allure.step("Проверить отклонение неверного пароля"):
            error = wait.until(EC.visibility_of_element_located(login_page.error_message))
            wait.until(lambda _: error.text.strip() != "")
            assert error.text in ("Bad credentials", "Неверные учетные данные пользователя"), \
                f"Unexpected error text: {error.text!r}"

        main_page = login_page.login(USERNAME, PASSWORD)

        with allure.step("Проверить заголовок истории трат после повторного входа"):
            wait.until(EC.text_to_be_present_in_element(
                main_page.spendings_section, "History of Spendings"
            ))
