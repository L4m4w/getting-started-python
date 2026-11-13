# Агент 04: регрессионный MockMvc-тест gateway

Подготовь проверку гипотезы о валидации PATCH. Исправление продукта в эту
задачу не входит. Других агентов не запускай.

## Входы

Приложение: `/Users/zenalark/PycharmProjects/Test-java/niffler-py-st3`.
Тестовый проект: `/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Прочитай применимые AGENTS.md. В тестовом проекте прочитай требование и
сценарии из `docs/qa-workflow/pilots/category-update-validation/`,
`docs/qa-workflow/api-framework-assessment.md`, отчёты
`docs/qa-workflow/handoffs/00-scenario-review.md` и `01-build-readiness.md`.
До закрепления ожиданий координатор должен подтвердить решение ревью 00.

## Действия

Создай standalone MockMvc-тест реального gateway CategoriesController:
настоящая Bean Validation, mock SpendClient, валидный JWT principal через
тестовый argument resolver. Не поднимай auth/Kafka/БД и весь SpringBoot-контекст.

Проверь пустое имя, три пробела, 1 и 51 ASCII-символ: HTTP 400 и отсутствие
вызова обновления downstream. Для имён длиной 2 и 50 — HTTP 200 и точные
переданные данные. Настрой validator и downstream так, чтобы отсутствие
валидации не маскировалось случайным NPE/500. Следуй существующим Java-конвенциям.

## Область изменений

В приложении только
`niffler-gateway/src/test/java/guru/qa/niffler/controller/CategoriesControllerValidationTest.java`.
Дополнительные зависимости передай агенту 01 через координатора; сам не меняй
общую сборку. Не добавляй @Valid в production-контроллер и не меняй требования.
Отчёт в тестовом проекте: `docs/qa-workflow/handoffs/04-gateway-regression.md`.

## Проверка и передача

После готовности 01 и согласования очереди Gradle с координатором проверь
компиляцию/запуск. Если команда evidence из 02 готова, используй её.
Падение assertions на base ожидаемо, но сбой компиляции/setup не является
воспроизведением. Запиши по каждому случаю фактический результат.

Передай 05 неизменяемый набор тестов, его hash/patch, команды и результаты.
Укажи предел доказательств: mock downstream не подтверждает сохранность
реальной БД, OAuth и межсервисную интеграцию.
