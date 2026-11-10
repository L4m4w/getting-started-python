# Данные и окружение

Источники: [conftest.py](../../conftest.py), [RegisterPage](../../pages/register_page.py),
[env example](../../.env.example) и [тесты регистрации](../../tests/registration/test_registration.py).

BASE_URL по умолчанию https://niffler.qa.guru; AUTH_URL — https://auth.niffler.qa.guru.
LoginPage открывает BASE_URL /, RegisterPage.open — AUTH_URL /register.
Это два отдельных параметра: смена BASE_URL не меняет AUTH_URL.

BROWSER=chrome, HEADLESS=true; BROWSER_VERSION опционален.
SELENIUM_REMOTE_URL включает remote-драйвер; SELENIUM_REMOTE=true требует URL.
Не выводите URL с basic-auth или содержимое .env в отчёты.

Текущие login/logout и проверка занятого имени используют фиксированный
демо-аккаунт в исходниках: это существующее допущение, а не env-конфигурация.
Не копируйте его значения в новую документацию и не меняйте способ хранения без задачи.
Для нового имени используется user_ + первые 10 hex-символов UUID4; Faker не нужен.
Успешная регистрация создаёт постоянный аккаунт. quit закрывает браузер,
но не удаляет серверные данные. Cleanup API, сброс БД и гарантия parallel isolation отсутствуют.

Ошибка входа допускает ru/en тексты, закреплённые в тесте. Не заменяйте их
произвольным «любым непустым сообщением» ради успешного результата.
Telegram включается только при наличии TELEGRAM_TOKEN и TELEGRAM_CHAT_ID.
