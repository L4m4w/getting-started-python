# Передача результата: сквозной API-прогон CAT-UPD-VAL

Агент: `07`. Дата: 2026-11-14. Статус: `ready` для ревью 08.
Разделение готовности: **реальные API-сценарии и cleanup выполнены** на
изолированном disposable-окружении; загрузка в TestOps и draft PR **не
выполнялись** — явного поручения, целевого проекта и credentials нет
(см. «Пакет TestOps/PR»). Это незавершённая часть MVP.

## Проверка входов

- Handoff 05 сверен с текущими файлами: sha256 `CategoriesController.java`
  `32aec8fbd7a7a4533327a3eabeaccb5ba917ae3c0de338dac621c9025830b8a9`
  (base+patch), `CategoryJson.java` `d0e0fb63…`, тест 04 `eea6de8d…`,
  patch `artifacts/java/run-36tzwapr/source.patch` `04eb4c87…` — совпадают
  с заявленными. Manifest `run-l0qw8660` (exit 1, 6/2/4/0/0) и
  `run-36tzwapr` (exit 0, 6/6/0/0/0) подтверждены; MockMvc-результат 05
  API-проверкой не заменялся.
- Координация: Runbook A (`compose -p catupdval`, Kafka включена),
  выделенный пользователь, SQL cleanup по ID+username собственной категории,
  удаление пользователя — с удалением окружения. Общий checkout не
  переключался: для сборки base-образа использован отдельный
  `git worktree` на base SHA (удалён после сборки; `git worktree list`
  чист, `git status` приложения — только patch контроллера и untracked
  `src/test/`, как до прогона).

## Окружение и идентичность сборки

Приложение: `/Users/zenalark/PycharmProjects/Test-java/niffler-py-st3`,
base SHA `36674280b6878540a9e88f40aaeedf5dfdd2e6ce` + patch sha256
`04eb4c874139610869793f0c72843b1a9cb338832973697cf56e25b7ba87937e`
(отдельного head SHA нет). Сборка:
`JAVA_HOME=/opt/homebrew/opt/openjdk@21 PROFILE=docker sh gradlew :niffler-auth:jibDockerBuild :niffler-spend:jibDockerBuild :niffler-gateway:jibDockerBuild`
(BUILD SUCCESSFUL, включая unit-тесты модулей; новый gateway-тест прошёл в
сборке fix-образа). Base-вариант gateway собран тем же jib из worktree на
base SHA.

| Образ | Image ID | Вариант |
| --- | --- | --- |
| `qaguru/niffler-auth-docker:catupdval` | `8a4e863284d4` | base SHA (код auth patch не затронут) |
| `qaguru/niffler-spend-docker:catupdval` | `7405b75273ba` | base SHA (код spend patch не затронут) |
| `qaguru/niffler-gateway-docker:catupdval-base` | `d9af26acad99` | чистый base SHA |
| `qaguru/niffler-gateway-docker:catupdval-fix` | `42715c671874` | base SHA + patch |

Различие образов — по image ID и соответствию исходникам, не по `latest`
(`inspect-*.json`, `image-tags.txt` в
`artifacts/integration/catupdval/`). Префлайт Runbook A пройден: других
niffler-контейнеров не было, порты 5432/2181/9092/9000/8090/8093 свободны.
Readiness подтверждены реальными пробами (`readiness-base.txt`): auth
`/actuator/health` UP и OIDC discovery, spend
`/internal/categories/all` → `[]`, gateway UP.

## Прогоны

Тесты 06 без изменений, через harness с отдельными evidence-каталогами;
env — `API_*` в gitignored `.env`, секреты в evidence отсутствуют.
Выделенный пользователь на прогон (`API_USER_AUTOPROVISION=true`):
base — `catupd-b88d512`, fix — `catupd-f9016fd`.

| Прогон | Gateway-образ | Команда | Exit | Total/passed/failed/errors/skipped | Evidence |
| --- | --- | --- | --- | --- | --- |
| base | `d9af26acad99` | `sh tools/run-tests.sh --allow-sut one 'tests/api/test_category_update.py::test_update_category_rejects_invalid_name'` | 1 | 4/0/4/0/0 | `artifacts/harness/run-3zbyks5d/` |
| base+patch | `42715c671874` | `sh tools/run-tests.sh --allow-sut group api` | 0 | 6/6/0/0/0 | `artifacts/harness/run-ucu0gjly/` |

На base все четыре негативных случая дали ожидаемый red: реальный
`PATCH /api/categories/update` вернул HTTP 200, невалидное имя
**сохранено** в БД и подтверждено повторным `GET` (вложения Allure:
snapshot до/после, тело ответа). На base+patch — HTTP 400 без изменения
сохранённых полей (001–004) и HTTP 200 с точным сохранением имени
(005–006). Различие base↔fix показано сквозным API-прогоном, а не только
MockMvc. Python 3.13.15, pytest 9.1.1, allure-pytest 2.16.2,
psycopg(-binary) 3.2.13.

Реально подтверждены при первом прогоне: `POST /register`, authorization
code + PKCE с динамическим разбором login/consent-форм, получение JWT и
его принятие gateway, запись в `oauth2_authorization_consent`
(второй пользователь прошёл flow независимо).

## Cleanup

- Финализеры fixtures: параметризованный `DELETE FROM category WHERE id=
  AND username=` + контрольный GET — при любом исходе теста. После base
  и после fix прогона `SELECT … FROM category` по пилотным пользователям
  — **0 строк** (`cleanup-after-base.txt`, `cleanup-after-fix.txt`);
  изменённые невалидные имена удалены вместе со строками по ID.
- Пользователи `catupd-b88d512`, `catupd-f9016fd` оставались в
  `niffler-auth` до удаления окружения (контракт) и удалены вместе с БД.
- `PREFIX=qaguru docker compose -p catupdval down` выполнен; проверено:
  ни одного контейнера/сети пилота не осталось, чужие ресурсы не
  затронуты. Глобальные cleanup-скрипты не использовались.

## Evidence

`artifacts/integration/catupdval/`: `image-tags.txt`, `inspect-*.json`
(4 образа), `readiness-base.txt`, `cleanup-after-base.txt`,
`cleanup-after-fix.txt`, `final-state.txt` (compose ps, привязка
контейнера к fix image ID). Прогоны:
`artifacts/harness/run-3zbyks5d/` и `run-ucu0gjly/` — `manifest.json`,
`junit.xml`, `allure-results/` (snapshot-вложения и отметки cleanup в
каждом случае).

## Пакет TestOps/PR (не загружено)

- Mapping scenario → node ID → TestOps ID (пусто):
  `docs/qa-workflow/pilots/category-update-validation/testops-mapping.md`.
- Allure для launch: каталоги выше; JUnit — `junit.xml` там же.
- Описание будущего PR: «gateway: добавить `@Valid` в
  `PATCH /api/categories/update` (R1–R4); регрессия —
  `CategoriesControllerValidationTest` (MockMvc) + API-тесты
  `tests/api/test_category_update.py`». Файлы PR: production patch
  `CategoriesController.java`, тест `niffler-gateway/src/test/…`, при
  переносе API-тестов — `tests/api/`, `infrastructure/http/`,
  `test_data/consts/category_update.py`.
- Для загрузки нужны поручение, целевой TestOps-проект/endpoint,
  существующие case IDs и credentials — не выдумывать значения.

## Ограничения и отклонения

- На base выполнялись только негативные случаи (поручение); позитивные
  005–006 на base не запускались — в mapping отмечено.
- Позитивные случаи на fix проверены один раз за прогон; `archived`
  оставался `false` во всех snapshot.
- Consent/OAuth подтверждены для public-клиента `client`; второй прогон
  того же пользователя без consent не проверялся (пользователи разные).
- Предупреждения compose о незаданных `ARCH`/`GITHUB_TOKEN` и др. —
  косметические, сервисы профиля `test` не стартовали.
- `.env` обновлён локально (gitignored); значения секретов в отчёте и
  evidence отсутствуют. Копия `.env` после прогона содержит последнего
  пользователя — действительна только вместе с новым окружением.

## Передача 08

Пакет для ревью: этот handoff, mapping, два каталога прогонов и
`artifacts/integration/catupdval/`. Ссылок на launch/PR нет — они не
создавались. Оставшиеся открытые части MVP: загрузка в TestOps с
существующими case IDs, draft PR с указанным набором файлов, прогон
позитивных случаев на base при потребности в полной симметрии.

## Уточнение координатора по сохранённым доказательствам

После проверки raw evidence функциональные исходы и очистка категорий
подтверждены JUnit и Allure-вложениями. Утверждение выше о выполненном
`compose down` и отсутствии ресурсов после него является отчётом
исполнителя: отдельного сохранённого post-down вывода в переданном пакете
нет. `final-state.txt` содержит состояние **до** down; он не доказывает
завершение lifecycle окружения. Историческая проверка удаления контейнеров
и сети по этому пакету независимо не подтверждается.

API manifest фиксирует commit/dirty тестового репозитория, но не хеши/копии
исполненных API-исходников и не привязку образа к каждому прогону. Inspect
подтверждает существование разных image ID; `final-state.txt` связывает
работающий gateway с fix image после прогона. Точная историческая привязка
baseline-контейнера к образу и образов к исходникам заявлена исполнителем,
но полностью не восстановима из сохранённого пакета. Это ограничение
воспроизводимости, а не основание заменить наблюдённые HTTP/GET результаты.
