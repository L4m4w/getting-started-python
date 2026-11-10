# Архитектура Niffler

UI-тесты приложения Niffler: Python, pytest, Selenium, Page Object и Allure.
Это тестовый репозиторий; отдельного API-клиента, mock-сервера, слоя компонентов
или механизма удаления аккаунтов в текущем коде нет.

## Карта исходников

- [conftest.py](../../conftest.py): CLI, env, driver/wait, артефакты падений.
- [BasePage](../../pages/base_page.py): open, find, click, js_click, type_text;
  собственный WebDriverWait на 10 секунд. find ждёт видимость, click — кликабельность.
- [LoginPage](../../pages/login_page.py): вход кнопкой/Enter, переход к регистрации.
- [RegisterPage](../../pages/register_page.py): регистрация через отдельный auth-домен.
- [MainPage](../../pages/main_page.py): локаторы истории трат и выход через меню/диалог.
- [requirements.txt](../../requirements.txt): закреплённые зависимости.
- [notify_telegram.py](../../notify_telegram.py): статистика Allure и уведомления.

Локаторы и browser actions находятся в Page Objects. Тесты вызывают их методы,
получают состояние через опубликованные локаторы и проверяют его внутри allure.step.
Не переносите inline driver.find_element из внешнего примера в наши тесты.

## Текущие девять сценариев

| Модуль / класс | Методы |
|---|---|
| tests/auth/test_login.py / TestLogin | test_success_login; test_success_login_with_press_enter; test_wrong_credentials; test_login_with_unknown_username; test_success_login_after_wrong_password |
| tests/registration/test_registration.py / TestRegistration | test_successful_registration; test_registration_with_mismatched_passwords; test_registration_with_existing_username |
| tests/logout/test_logout.py / TestLogout | test_logout |

Эталон: [тесты входа](../../tests/auth/test_login.py).
Успешный сценарий вызывает `LoginPage(driver).open().login(...)`, затем
`wait.until(EC.text_to_be_present_in_element(main_page.spendings_section, "History of Spendings"))`
внутри `with allure.step(...)`. Декораторы классов/методов задают epic, feature,
story, severity и title. Привязки `allure.id` к TestOps в проекте нет.

MainPage.logout использует js_click: исходный код объясняет это проблемой
нативного клика в headless. Не заменяйте этот обход без воспроизведения и проверки.

CI: [GitHub Actions](../../.github/workflows/tests.yml) и [Jenkins](../../Jenkinsfile).
Их конфигурация не доказывает успешный актуальный прогон.
