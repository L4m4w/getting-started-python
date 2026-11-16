# Передача результата: финальный API execution с закреплёнными TestOps ID (прогон 17C)

Агент: `17C`. Дата: 2026-11-15. Статус: `ready`.

Выполнен один новый фактический fix-прогон шести сценариев CAT-UPD-VAL на
disposable-стеке `catupdval` с закреплёнными `ALLURE_ID`; локальный bind-пакет
для проекта 5444 подготовлен и проверен. **Публикация TestOps, upload/
create/close, commit/push/PR не выполнялись.** `ready` означает завершённый
локальный execution и готовый bind-пакет, не серверную публикацию и не
завершение MVP.

Основание: приёмка [coordination-wave-14.md](coordination-wave-14.md).
Прежний handoff остановки `17c-final-execution.md` и его evidence сохранены
неизменными.

## Принятые входы (перепроверены перед стартом)

- Код 17A: `tests/api/test_category_update.py` `ebd9deaa…`,
  `test_data/consts/category_update.py` `c66a9a9f…`,
  `knowledge/components/consts.md` `a1f203a3…` — совпадают с принятыми SHA;
  отличие от before-копий — только маркировка (проверено ранее, зафиксировано
  в `17c-final-execution.md`).
- Приложение `niffler-py-st3`: HEAD `36674280b6878540a9e88f40aaeedf5dfdd2e6ce`
  (`main`), `git diff` sha256 `04eb4c874139610869793f0c72843b1a9cb338832973697cf56e25b7ba87937e`.
- Образы (`docker image inspect`, `:latest` уже разрешался в принятые ID —
  повторная смена тега не выполнялась по wave 14):
  gateway fix `sha256:f496835fbad4dd72fa650f4b27d1b7c171d40e73d662da929aab1a8c4162614b`,
  spend `sha256:fb10c075a21edab38c3309a8f1b4f848afa29c71ae00b5c29d3205ba9a13905e`,
  auth `sha256:f18b5255ea61d8974b724dd079944192b0dd1a7139b1484982d8992910981af9`.
- Docker 29.7.2, compose v5.5.0, JDK 21.0.12.1; конфликтов `catupdval` нет,
  порты 5432/2181/9092/9000/8090/8093 свободны; чужие
  `ai-first-student-workspace-*` не затрагивались.

## Стек и прогон

- `PREFIX=qaguru docker compose -p catupdval up -d auth.niffler.dc
  spend.niffler.dc gateway.niffler.dc` — exit 0; подняты db/zookeeper/kafka/
  auth/spend/gateway. Readiness: auth `/actuator/health` UP, OIDC issuer
  `http://auth.niffler.dc:9000`, spend `/internal/categories/all` → `[]`,
  gateway UP (`04-readiness.txt`).
- Свежий выделенный пользователь `catupd-f-2f5bc45b` (`.env`, gitignored;
  пароль 10 символов, `API_USER_AUTOPROVISION=true`; значения не печатались).
- Binding до прогона (`05-gateway-binding-pre.txt`): контейнер
  `c6c7cb4d39f457e8220924ffd303dd7679a797fa9c430c3cfffbb95b40fb876f`,
  running, image `sha256:f496835f…`.
- Прогон (exit 0, `artifacts/harness/run-ni_5bvnc/`):
  ```sh
  sh tools/run-tests.sh --allow-sut group api \
    --app-base-sha 36674280b6878540a9e88f40aaeedf5dfdd2e6ce \
    --app-patch-sha256 04eb4c874139610869793f0c72843b1a9cb338832973697cf56e25b7ba87937e \
    --gateway-image-id sha256:f496835fbad4dd72fa650f4b27d1b7c171d40e73d662da929aab1a8c4162614b \
    --gateway-container gateway.niffler.dc
  ```
  Реально прошли регистрация `/register`, OAuth authorization code + PKCE
  с динамическими формами, POST/PATCH/GET категорий, SQL-cleanup —
  setup/teardown errors нет.

## Исходы шести сценариев (JUnit 6/6/0/0/0)

| Scenario | Параметр name | Ожидание | Исход | ALLURE_ID в исходном result JSON |
| --- | --- | --- | --- | --- |
| CAT-UPD-VAL-001 | `""` | PATCH 400, snapshot неизменён | passed | `55376` (ровно один) |
| CAT-UPD-VAL-002 | `"   "` | PATCH 400, snapshot неизменён | passed | `55374` |
| CAT-UPD-VAL-003 | `"A"` | PATCH 400, snapshot неизменён | passed | `55375` |
| CAT-UPD-VAL-004 | `"A"×51` | PATCH 400, snapshot неизменён | passed | `55377` |
| CAT-UPD-VAL-005 | `"AA"` | PATCH 200, имя сохранено | passed | `55373` |
| CAT-UPD-VAL-006 | `"A"×50` | PATCH 200, имя сохранено | passed | `55378` |

Проверка исходных result JSON (`10-allure-id-check.txt`): 6 файлов, у каждого
ровно один label `ALLURE_ID` со значением из согласованного маппинга
(сценарий определён по параметру `name` — то же правило, что в mapper
`results.py`). Ручной дописки ID не было — метки сериализованы тестом.

## Manifest `run-ni_5bvnc` (schema 2, `09-manifest-check.txt`)

- `exit_code=0`, `junit_summary` 6/6/0/0/0.
- `source_identity.contract_version=api-contract-v1`: 15 файлов, 15 копий,
  `missing=[]`, `changed_during_run=[]`, `rechecked_at` заполнен; хеши обоих
  файлов маркировки в manifest = текущим файлам (новые SHA ожидаемо отличаются
  от исторического прогона `run-5tsmzg1d`, контракт не менялся).
- `environment.declared`: base SHA, patch sha256, gateway image ID и контейнер
  как в команде; `container_check.performed=true`, `container_running=true`,
  `image_id=sha256:f496835f…`, `matches_declared_image=true`.

## Cleanup и post-down

- Binding после прогона (`07-gateway-binding-post.txt`): тот же контейнер,
  тот же образ, running — идентичность не менялась за прогон.
- SQL до остановки (`08-cleanup-sql.txt`, `docker exec niffler-all-db psql`):
  `count(*) FROM category WHERE username='catupd-f-2f5bc45b'` → 0;
  `username LIKE 'catupd-%'` → 0. Удаление выполнено fixture-финализаторами
  по `id`+`username`; проверено до `down`, а не выведено из ephemeral БД.
- `PREFIX=qaguru docker compose -p catupdval down` → exit 0
  (`11-post-down.txt`): контейнеры и сеть проекта удалены, выборки пусты,
  name-sweep чист.

## Bind-пакет (локальный, без внешних вызовов)

- `plan` → все шесть сценариев mapped/passed (`12-testops-plan.txt`);
  `assign` — согласованные пары wave 12 (`13-testops-assign.txt`);
  `package --mode bind` → exit 0 (`14-testops-package.txt`).
- Execution: `run-ni_5bvnc`, state schema 2, endpoint
  `https://allure.qa.guru`, project `5444`.
- Пакет `artifacts/testops/run-ni_5bvnc/upload-results`: 40 файлов,
  6 результатов, 18 attachments; sha256
  `1e1f643257c2289be3add60c47ab10e749b289e3d0f8920d3acf060f488d05a7`,
  `input_sha256=ba0d179cde801aca38df322b3725b786e70d44f82b47cd7af617a5fe5f5afa21`
  (= sha исходных результатов), `assignments_sha256=ebaa8a29…`.
- Каждый переписанный результат: имя с префиксом `CAT-UPD-VAL-00X:`,
  `fullName` с суффиксом `[CAT-UPD-VAL-00X]`, ровно один правильный
  `ALLURE_ID`, status passed; полный набор из шести, лишних нет
  (`15-package-verify.txt`).
- Upload: `pending`, attempts=0, launch=null. Исходные `allure-results`
  прогона не изменялись; старый uploaded execution `run-5tsmzg1d` не тронут
  (state sha256 по-прежнему `6da44722…`, проверено на входе).

## Гигиена секретов

Пароль прогона не найден ни в одном файле новых evidence (`run`,
`harness run-ni_5bvnc`, `testops/run-ni_5bvnc`); generic JWT/Bearer-скан —
единственное совпадение в копии исходника `sources/.../client.py`
(строка кода `Bearer {token}`, не реальный токен). Полный `docker inspect`
с env не сохранялся.

## Команды и exit codes

| Шаг | Команда | Exit |
| --- | --- | --- |
| Preflight | `docker ps/network ls`, `lsof` | 0 / 1 (нет совпадений) |
| Up | `compose -p catupdval up -d auth spend gateway` | 0 |
| Readiness | `curl` health/oidc/internal | 0 |
| Прогон | `run-tests.sh --allow-sut group api --app-*/--gateway-*` | 0, 6 passed |
| Cleanup | `docker exec niffler-all-db psql` | 0, count=0 |
| Down | `compose -p catupdval down` | 0, post-down пусто |
| TestOps | `plan` / `assign` / `package --mode bind` / `status` | 0 / 0 / 0 / 0 |
| Проверка | `git diff --check` | 0 |

## Evidence

- Окружение и проверки: `artifacts/final-execution/17c-run-20261115T121140Z/`
  (16 файлов: preflight, images, compose-up, readiness, pre/post binding,
  вывод прогона, cleanup SQL, post-down, manifest/ALLURE_ID/package checks,
  testops-выводы).
- Прогон: `artifacts/harness/run-ni_5bvnc/` (manifest.json, junit.xml,
  allure-results/, sources/).
- Execution state и пакет: `artifacts/testops/run-ni_5bvnc/`.

## Не выполнялось / ограничения

- Любые внешние обращения TestOps (upload/create/close/verify/resolve) —
  запрещены; пакет собран и проверен только локально.
- Baseline не повторялся (сила тестов доказана ранее).
- Позитивные случаи на base, `archived=true`, доставка kafka-событий,
  повторная авторизация без consent — вне scope.
- Образ не пересобирался: source→build→image основано на принятом evidence
  прогона 10 и совпадении текущих source/patch (wave 14).
- `.env` содержит пользователя этого прогона — валиден только с новым стеком.
- Полный MVP не завершён: решение о публикации этого execution и Git/PR —
  за координатором.
