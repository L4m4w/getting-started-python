# Агент 10: новый API baseline/fix с проверяемым evidence

Выполни новый CAT-UPD-VAL API-прогон после интеграции 09. Других агентов
не запускай. Исторические evidence 05/07 не изменяй и не переобозначай.

## Входы и разрешённая область

Тестовый проект: `/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Приложение: `/Users/zenalark/PycharmProjects/Test-java/niffler-py-st3`.
Прочитай AGENTS.md, локальный run-tests skill, requirement/scenarios,
handoffs 03/05/06/07/08/09, coordination-wave-4.md, обновлённый runbook 07
и `knowledge/testing/run-tests.md` (manifest schema 2).

Scope повторяет ранее выбранный disposable compose-проект `catupdval`:
сборка/запуск только сервисов пилота, readiness, выделенный пользователь
на прогон, OAuth/регистрация, категории POST/PATCH/GET, SQL cleanup по
ID+username, завершение только своих ресурсов. Учитывай ранее выданное
разрешение; sandbox escalation выполняй отдельно по правилам среды.
Не используй чужой аккаунт, глобальные cleanup-скрипты или reset checkout.
Секреты — только локальное окружение, без печати значений.

## Поручение

1. Сохрани точную версию app base и patch, хеши целевых файлов. Проверь
   имеющиеся образы: не считай старый тег доказательством исходников.
   Для каждой используемой сборки сохрани команды, время, exit codes,
   source identity/patch и полученный полный image ID. При необходимости
   изоляции используй подходящий checkout/worktree по правилам среды.
   Общий checkout с незакоммиченными файлами не переключай.
2. Запусти изолированный стек по runbook A, проверь конфликты/readiness.
   Сохрани отфильтрованную привязку live gateway к полному image ID до
   каждого запуска. Не сохраняй полный container inspect с env.
3. На чистом base выполни четыре негативных случая тем же API-кодом:
   `sh tools/run-tests.sh --allow-sut one 'tests/api/test_category_update.py::test_update_category_rejects_invalid_name'`
   с `--app-base-sha`, `--gateway-image-id`, `--gateway-container`.
   **Не передавай `--app-patch-sha256` для чистого base.** Ожидается
   exit 1, ровно четыре assertion failures по валидации, без setup errors.
4. На base + patch выполни `sh tools/run-tests.sh --allow-sut group api`
   с теми же metadata-флагами плюс `--app-patch-sha256` реального patch.
   Ожидается exit 0 и ровно шесть passed. Каждый запуск — свежие данные,
   отдельный пользователь и evidence-каталог; тесты не менять.
5. Проверь schema 2 обоих manifest: `source_identity.contract_version`
   равен `api-contract-v1`, все 15 файлов присутствуют, `missing=[]`,
   `changed_during_run=[]`, recheck завершён, копии совпадают с хешами.
   Хеши API-контракта должны совпасть между base/fix. Для окружения нужны
   `container_check.performed=true`, `container_running=true`,
   `matches_declared_image=true` и ожидаемый полный фактический image ID.
   Наличие `declared` без успешной проверки не завершает эту задачу.
6. После каждого прогона дополнительно сохрани минимальную live привязку
   контейнера к тому же image ID с временем/exit code, подтверждение
   PATCH/повторных GET и cleanup всех созданных категорий. Не скрывай
   ошибки подготовки/teardown и изменения среды во время прогона.
7. Заверши только ресурсы проекта пилота. Сохрани отдельный post-down
   evidence: команда down, exit code, UTC-время, команды и exit codes
   `docker ps -a --filter label=com.docker.compose.project=catupdval`
   и `docker network ls --filter label=com.docker.compose.project=catupdval`.
   Обе выборки должны быть пусты; не удаляй чужие ресурсы при конфликте.

## Результат и ограничения

Запись только в `docs/qa-workflow/handoffs/10-api-evidence-replay.md` и новые
локальные каталоги artifacts. Старый handoff 07 и mapping не переписывай.
Код продукта/тестов/harness не менять внутри execution. Если обнаружена
проблема 09, передай диагностику координатору; исправленный код требует
нового execution ID. TestOps, commit/push и PR не выполнять.

Отчёт: ready/blocked/needs_decision, версии, команды/exit codes, пути новых
manifest/JUnit/Allure, таблица четырёх base и шести fix исходов, проверка
source/image identity, результатов cleanup и post-down. Результаты относятся
только к новым прогонам. После передачи координатор отдельно проверит
закрытие F-1/F-2 ревью 08 по новым артефактам.
