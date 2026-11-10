# Браузер и артефакты

Источник: [conftest.py](../../conftest.py).

- dotenv загружается при импорте conftest; значения задаются через env / локальную .env.
- browser_name, browser_version, base_url и headless — session fixtures.
- driver и wait — function fixtures: отдельный браузер на тест, quit после yield.
- SELENIUM_REMOTE_URL выбирает webdriver.Remote; иначе Chrome или Firefox локально.
  SELENIUM_REMOTE=true без URL завершает setup ошибкой, без fallback на локальный браузер.
- Chromium — alias Chrome. --browser и --bversion имеют приоритет над env defaults.
- Размер окна 1920×1080, headless по умолчанию, wait — 10 секунд.
- В отличие от внешнего примера implicitly_wait не настраивается.

При падении фазы call hook сохраняет PNG и HTML в artifacts/ и прикладывает к Allure.
Он не собирает их при setup/teardown-падениях; ошибки сбора перехватываются.
Наличие hook не гарантирует, что артефакт записался: проверяйте реальные файлы.
Имена основаны на item.name, поэтому повторные прогоны могут перезаписывать файлы.
Сохраняйте свидетельства исходного падения перед повтором. Видео и traces не настроены.
