# Передача результата: новый API baseline/fix с проверяемым evidence

Агент: `10`. Дата: 2026-11-14. Статус: `ready`.

Новый CAT-UPD-VAL API-прогон после интеграции 09 выполнен на disposable
compose-проекте `catupdval`: четыре негативных случая на чистом base дали
ожидаемый red (exit 1), все шесть на base + patch — green (exit 0).
Manifest обоих прогонов соответствуют schema 2: source identity
`api-contract-v1` полная и совпадает между прогонами, привязка gateway к
полному image ID подтверждена фактическим `docker container inspect` до
старта pytest, post-down evidence сохранён отдельно. Исторические evidence
05/07 не изменялись и не переобозначались. Проверку закрытия F-1/F-2 ревью
08 по новым артефактам выполняет координатор; полный MVP завершённым не
объявляется.

## Версии входов

- Приложение `/Users/zenalark/PycharmProjects/Test-java/niffler-py-st3`,
  HEAD `36674280b6878540a9e88f40aaeedf5dfdd2e6ce` (`main`), незакоммиченный
  production patch на месте: `git diff` → sha256
  `04eb4c874139610869793f0c72843b1a9cb338832973697cf56e25b7ba87937e`
  (совпадает с handoff 05/07). Общий checkout не переключался и не сбрасывался.
- sha256 целевых файлов текущего checkout (`source-identity.txt`):
  `CategoriesController.java` `32aec8fbd7a7a4533327a3eabeaccb5ba917ae3c0de338dac621c9025830b8a9` (base+patch),
  `CategoryJson.java` `d0e0fb63fd34e6b239d0c25596ba106b712d7326aae1164bc5d7e06e5191d552`,
  `CategoriesControllerValidationTest.java` `eea6de8d14f8d5f1b7bb84dd2dd384b1d03e3056daad39dacc9568515604ca50`.
- Тестовый проект: Python 3.13.15, pytest 9.1.1, allure-pytest 2.16.2,
  psycopg(-binary) 3.2.13. JDK `/opt/homebrew/opt/openjdk@21`, Gradle
  wrapper 8.6, Docker 29.7.2.
- Прочитаны: AGENTS.md, `.agents/skills/run-tests/SKILL.md`, README
  qa-workflow и agent-tasks, поручение 10, requirement v1 / scenarios v2,
  handoffs 03/05/06/07/08/09, coordination-wave-4.md, обновлённый runbook 07,
  `knowledge/testing/run-tests.md` (schema 2). Отчёта 10 до старта не было.

## Сборки и идентичность образов

Старые образы 07 не переиспользовались: построены новые, с собственными
командами, временем, exit codes и image ID (jib-сборка не бит-в-бит
воспроизводима — новые ID отличаются от 07, это ожидаемо).

| Сборка | Команда / источник | Exit | Image ID (полный) |
| --- | --- | --- | --- |
| auth | `JAVA_HOME=/opt/homebrew/opt/openjdk@21 PROFILE=docker sh gradlew :niffler-auth:jibDockerBuild :niffler-spend:jibDockerBuild :niffler-gateway:jibDockerBuild` в основном checkout (base+patch) | 0, BUILD SUCCESSFUL, 22s | `sha256:f18b5255ea61d8974b724dd079944192b0dd1a7139b1484982d8992910981af9` |
| spend | та же команда | 0 | `sha256:fb10c075a21edab38c3309a8f1b4f848afa29c71ae00b5c29d3205ba9a13905e` |
| gateway fix | та же команда | 0 | `sha256:f496835fbad4dd72fa650f4b27d1b7c171d40e73d662da929aab1a8c4162614b` |
| gateway base | `JAVA_HOME=… PROFILE=docker sh gradlew :niffler-gateway:jibDockerBuild` в отдельном worktree `niffler-py-st3-catupdval-base-wt`, detached на base SHA (0 изменённых файлов, без patch/теста) | 0, 12s, 10/10 executed | `sha256:1a7afc4df66a7c900c513da9b5684106770cba31b41c609625bbb422e39933bd` |

Логи: `build-fix.log`, `build-base.log`, `image-ids-*.txt`, `image-tags.txt`,
`base-to-fix.patch` в `artifacts/integration/catupdval-rerun/`.
Worktree удалён после сборки (`git worktree remove`, exit 0); `git worktree
list` чист, `git status` приложения не изменился. Метки `latest`/`2.x`
мутабельны — идентичность только по полным image ID.

## Стек и readiness (Runbook A)

- Preflight: других niffler/selenoid-контейнеров нет, порты
  5432/2181/9092/9000/8090/8093 свободны (`preflight.txt`).
- `PREFIX=qaguru docker compose -p catupdval up -d auth.niffler.dc
  spend.niffler.dc gateway.niffler.dc` — exit 0 (`compose-up.txt`);
  подняты postgres, zookeeper, kafka, auth, spend, gateway.
- Readiness (`readiness.txt`): auth `/actuator/health` UP, OIDC issuer
  `http://auth.niffler.dc:9000`, spend `/internal/categories/all` → `[]`,
  gateway UP.

## Прогоны

| Прогон | Команда | Exit | Total/passed/failed/errors/skipped | Пользователь | Evidence |
| --- | --- | --- | --- | --- | --- |
| base | `sh tools/run-tests.sh --allow-sut one 'tests/api/test_category_update.py::test_update_category_rejects_invalid_name' --app-base-sha 36674280b6878540a9e88f40aaeedf5dfdd2e6ce --gateway-image-id sha256:1a7afc4df66a7c900c513da9b5684106770cba31b41c609625bbb422e39933bd --gateway-container gateway.niffler.dc` | 1 | 4/0/4/0/0 | `catupd-b-ff620cd8` | `artifacts/harness/run-vzsatlfk/` |
| fix | `sh tools/run-tests.sh --allow-sut group api --app-base-sha 36674280b6878540a9e88f40aaeedf5dfdd2e6ce --app-patch-sha256 04eb4c874139610869793f0c72843b1a9cb338832973697cf56e25b7ba87937e --gateway-image-id sha256:f496835fbad4dd72fa650f4b27d1b7c171d40e73d662da929aab1a8c4162614b --gateway-container gateway.niffler.dc` | 0 | 6/6/0/0/0 | `catupd-f-d9fa1684` | `artifacts/harness/run-5tsmzg1d/` |

Для чистого base флаг `--app-patch-sha256` не передавался
(`declared.app_patch_sha256=null`). Переключение на fix-образ:
`docker tag sha256:f496835f… qaguru/niffler-gateway-docker:latest` +
`docker compose -p catupdval up -d --no-deps --force-recreate
gateway.niffler.dc` — exit 0 (`gateway-switch-to-fix.txt`); прочие сервисы
не пересоздавались. На каждый прогон — новый выделенный пользователь через
`API_USER_AUTOPROVISION=true`, свежие данные и отдельный evidence-каталог;
тесты и контракт между прогонами не менялись. Реально прошли `POST
/register`, authorization code + PKCE с динамическими login/consent-формами,
JWT принят gateway — ошибок подготовки нет в обоих прогонах.

## Исходы случаев

Base (4 негативных — все FAIL, assertion, без setup errors):

| Case | Вход | PATCH | Повторный GET (Allure) |
| --- | --- | --- | --- |
| CAT-UPD-VAL-001 | `""` | 200 | невалидное имя сохранено (`name=""`) |
| CAT-UPD-VAL-002 | три пробела | 200 | сохранено (`name="   "`) |
| CAT-UPD-VAL-003 | `A×1` | 200 | сохранено (`name="A"`) |
| CAT-UPD-VAL-004 | `A×51` | 200 | сохранено (`name="A"×51`) |

Fix (6 — все PASS):

| Case | Вход | PATCH | Повторный GET (Allure) |
| --- | --- | --- | --- |
| CAT-UPD-VAL-001–004 | невалидные | 400 | snapshot не изменён |
| CAT-UPD-VAL-005 | `A×2` | 200 | `name="AA"`, остальные поля сохранены |
| CAT-UPD-VAL-006 | `A×50` | 200 | `name="A"×50`, остальные поля сохранены |

## Проверка manifest (schema 2)

| Критерий | base `run-vzsatlfk` | fix `run-5tsmzg1d` |
| --- | --- | --- |
| `schema_version` | 2 | 2 |
| `source_identity.contract_version` | `api-contract-v1` | `api-contract-v1` |
| файлов в контракте | 15 | 15 |
| `missing` / `changed_during_run` | `[]` / `[]` | `[]` / `[]` |
| `rechecked_at` | `2026-11-14T14:45:39Z` | `2026-11-14T14:46:41Z` |
| копии `sources/` = хеши `files[]` | 15/15 совпали | 15/15 совпали |
| хеши контракта base vs fix | — | идентичны всем 15 файлам |
| `container_check.performed/running/matches_declared_image` | true/true/true | true/true/true |
| фактический `image_id` контейнера | `sha256:1a7afc4d…` = ожидаемый base | `sha256:f496835f…` = ожидаемый fix |
| `declared.app_patch_sha256` | `null` (чистый base) | `04eb4c87…` |
| `junit_summary` | 4/0/4/0/0 | 6/6/0/0/0 |

Живой `docker container inspect` выполнен harness до старта pytest в обоих
прогонах; полный inspect и env контейнера не сохранялись. Декларация
оператора подтверждена фактической проверкой, а не только `declared`.

## Live image binding до/после и cleanup

- base: pre `gateway-binding-pre-base.txt` и post `gateway-binding-post-base.txt`
  — контейнер `d041a1d6f380…`, running, image `sha256:1a7afc4d…`, не менялся.
- fix: pre `gateway-binding-pre-fix.txt` и post `gateway-binding-post-fix.txt`
  — контейнер `43405055455f…`, running, image `sha256:f496835f…`, не менялся.
- Cleanup категорий: параметризованный `DELETE` по ID+username финализерами
  с контрольным GET; SQL-проверки (`cleanup-after-base.txt`,
  `cleanup-after-fix.txt`): `SELECT count(*) FROM category WHERE
  username='<пилотный>'` → 0 после каждого прогона; `username LIKE 'catupd-%'`
  → 0. Изменённые невалидные имена удалены вместе со строками.

## Post-down evidence

`post-down.txt`: `utc_down=2026-11-14T14:47:38Z`, команда
`PREFIX=qaguru docker compose -p catupdval down` → `down_exit=0`; затем
`docker ps -a --filter label=com.docker.compose.project=catupdval` →
`ps_exit=0`, выборка пуста; `docker network ls --filter
label=com.docker.compose.project=catupdval` → `network_exit=0`, выборка
пуста. Все 6 контейнеров и сеть проекта удалены; чужих ресурсов не было и
не затрагивалось.

## Изменённые файлы

- Новый отчёт: `docs/qa-workflow/handoffs/10-api-evidence-replay.md`.
- Новый каталог evidence: `artifacts/integration/catupdval-rerun/`
  (16 файлов: source-identity, patch, логи сборок, image IDs/теги,
  preflight, readiness, compose-up/switch, 4 binding, 2 cleanup, post-down).
- Новые прогоны: `artifacts/harness/run-vzsatlfk/` и `run-5tsmzg1d/`
  (manifest.json, junit.xml, allure-results/, sources/).
- `.env` обновлён локально (gitignored): `API_USERNAME` —
  `catupd-f-d9fa1684` последнего прогона; значения секретов в отчёте и
  evidence отсутствуют, `.env` валиден только с новым стеком.
- Код продукта/тестов/harness не менялся; старые evidence, handoff 07 и
  mapping не переписывались; работа с app-repo — только read + отдельный
  worktree, удалённый после сборки.

## Подтверждено / не проверялось

Подтверждено новыми прогонами: различие base↔fix по всем шести сценариям на
реальном стеке (PATCH/GET через gateway, БД spend), schema-2 manifest с
полной source identity и live image binding до/после каждого запуска,
fixture cleanup и post-down доказательство lifecycle окружения.

Не проверялось: позитивные случаи на base (вне поручения), bit-совпадение
образов со сборками 07 (новые image ID, provenance — мои записанные сборки),
доставка kafka-событий регистрации, повторная авторизация без consent,
`archived=true`, TestOps upload, commit/push, PR.

## Блокеры и следующий исполнитель

Блокеров нет. Следующий исполнитель — координатор: проверить закрытие
F-1/F-2 ревью 08 по артефактам `run-vzsatlfk`, `run-5tsmzg1d` и
`artifacts/integration/catupdval-rerun/post-down.txt`. Результаты относятся
только к этим двум прогонам; TestOps/PR — отдельное поручение.
