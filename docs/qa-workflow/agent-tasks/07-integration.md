# Агент 07: сквозной API-прогон и пакет для TestOps

Выполни реальный API-пилот после готовности входов. Других агентов не запускай.

## Входы

Тестовый проект: `/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Приложение: `/Users/zenalark/PycharmProjects/Test-java/niffler-py-st3`.
Прочитай применимые AGENTS.md, `.agents/skills/run-tests/SKILL.md`, требование
и сценарии в `docs/qa-workflow/pilots/category-update-validation/`, отчёты
`docs/qa-workflow/handoffs/03-runtime-plan.md`, `05-baseline-and-fix.md`,
`06-python-api.md` и интегрированные команды harness.

## Условия запуска

Актуальная координация: `docs/qa-workflow/handoffs/coordination-wave-2.md`.
03 принят как статический runbook, 06 интегрирован (58 offline unit passed;
это не API-прогон). 05 дал фактический red/green: baseline
`artifacts/java/run-l0qw8660/` (2 passed / 4 failed), base + patch
`artifacts/java/run-36tzwapr/` (6 passed), неизменный тест.
Прочитай handoff 05 и проверь соответствие текущих файлов evidence.
Выбран Runbook A: disposable `catupdval`, Kafka
включена, отдельный пользователь. SQL cleanup — только ID и username
собственной категории; удаление пользователя — при завершении disposable
окружения. Обязательные API env сейчас не настроены: подготовь их локально,
секреты не печатай и не помещай в поручение/evidence.

Если продукт не закоммичен, идентичность сборки — base + SHA-256 patch,
а не новый head SHA. Образы base/fix не должны различаться только меткой
latest или одинаковым тегом base SHA: сохрани Docker image ID и соответствие
исходникам каждой сборки. Не переключай общий checkout с чужими правками.

Координатор должен выбрать изолированное окружение и подтвердить scope
его старта, авторизации, создания и очистки данных. Ранее разрешённые
операции повторно не согласовывай. Если нужный scope не определён, уточни
только недостающее; подготовку команд и входов продолжай независимо.
Не запускай глобальные Docker-cleanup скрипты и не используй общий аккаунт.

## Действия

1. Проверь соответствие сборки выбранной версии приложения, readiness и данные.
2. Перед каждым запуском base и fix зафиксируй привязку работающего
   gateway-контейнера к image ID: передай harness флаги
   `--app-base-sha <base SHA> --app-patch-sha256 <sha256 patch>`
   `--gateway-image-id <image ID> --gateway-container <ID или имя>`.
   Для чистого base флаг `--app-patch-sha256` не передавать; для base + patch
   передать хеш фактически применённого patch.
   Manifest прогона запишет декларацию оператора и фактический результат
   `docker container inspect`, выполненный до старта pytest. Если проверка
   не выполнена (`performed=false` с явной причиной), привязку считай
   только заявленной оператором и отрази это в отчёте.
3. Выполни шесть случаев через harness с отдельными evidence-каталогами.
   Для выбора, затрагивающего `tests/api`, manifest дополнительно сохраняет
   `source_identity` согласованного контракта (`api-contract-v1`): хеши
   и копии исходников до старта и `changed_during_run` после завершения.
4. Подтверди реальное повторное чтение данных и очистку при любом исходе.
5. Если доступна исходная сборка, повтори применимые негативные случаи на base
   с теми же тестами и изолированными свежими данными. Не заменяй API-проверку
   MockMvc-результатом агента 05.
6. Сохрани SHA либо base + patch hash, версии образов, exit codes, test counts,
   JUnit/Allure, очищенные HTTP-артефакты и результаты cleanup.
7. После `docker compose -p catupdval down` сохрани отдельный post-down
   evidence-файл (например, `artifacts/integration/catupdval/post-down.txt`)
   с выполненной командой, её exit code, UTC-временем и выводом проверок
   только ресурсов этого проекта:
   `docker ps -a --filter label=com.docker.compose.project=catupdval` и
   `docker network ls --filter label=com.docker.compose.project=catupdval`.
   Снимок состояния до down эту проверку не заменяет.
8. Подготовь соответствие scenario ID → test node ID → TestOps ID, если уже
   известен. При отсутствии TestOps ID оставь его незаполненным.

## Публикация и область изменений

Только отчёт `docs/qa-workflow/handoffs/07-integration.md`, отдельный mapping
рядом с материалами пилота и локальные evidence в artifacts/.
Продукт и тесты не исправляй внутри прогона: передавай дефект владельцу,
после изменения начинай новый execution ID.

Внешняя загрузка в TestOps и создание draft PR выполняются только при явном
поручении на эти действия и известных целевом проекте/репозитории. До этого
подготовь конкретный пакет: metadata кейсов, путь к Allure-результатам,
описание PR и список файлов. Не выдумывай endpoint или значения credentials.
При разрешённой загрузке используй поддерживаемый инструмент TestOps и
существующие case IDs; не создавай дубли при повторной отправке выполнения.

## Готовность

Отчёт разделяет выполненные API-сценарии, cleanup, загрузку TestOps и PR.
Недоступная интеграция остаётся незавершённой частью MVP. Передай пакет 08
для ревью; приложи ссылки на launch/PR только если они реально созданы.
