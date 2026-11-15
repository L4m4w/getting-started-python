# Передача результата: план изолированного окружения CAT-UPD-VAL

Агент: `03` (окружение, авторизация, данные). Дата: 2026-11-14.
Статус: `needs_decision` — исполнимый способ определён и описан; запуск
стенда, сборка образов и любые операции с побочными эффектами **не
выполнялись**. Остались решения координатора (раздел «Решения и блокеры»):
выбор варианта стенда, допуск точечной SQL-очистки и credentials.

Анализ статический: по исходникам приложения на base SHA
`36674280b6878540a9e88f40aaeedf5dfdd2e6ce` (дерево `niffler-py-st3` чистое
на момент проверки), compose-файлам и handoff'ам 00–02. Docker daemon,
образы, OAuth-протокол и БД реально не запускались и не проверялись.

## Входы и версии

- Приложение `niffler-py-st3`, `main`, HEAD `36674280b6878540a9e88f40aaeedf5dfdd2e6ce`.
- JDK для сборки образов: `/opt/homebrew/opt/openjdk@21` (handoff 01).
- Прочитаны: AGENTS.md тестового проекта; `pilots/category-update-validation/
  {requirement,scenarios}.md`; `api-framework-assessment.md`;
  `handoffs/{00-scenario-review,01-build-readiness,02-java-harness,
  coordination-wave-1}.md`; исходники `niffler-gateway`, `niffler-auth`,
  `niffler-spend` (конфиги, security, контроллеры, сервисы, миграции),
  `docker-compose*.yml`, `docker-compose-{dev,e2e}.sh`, `localenv.sh`,
  `postgres/script/init-database.sh`, build.gradle модулей (jib),
  учебный `niffler-tests-python` на `origin/study_AL_14_kafka` (только чтение).

## Минимальный контур

Для `GET /api/categories/all`, `POST /api/categories/add`,
`PATCH /api/categories/update` через gateway и получения JWT достаточно:

| Сервис | Роль | Порт host→cont | Обязателен | Обоснование (статически) |
| --- | --- | --- | --- | --- |
| `postgres:15.1` | БД `niffler-auth`, `niffler-spend` | 5432 | да | Flyway-миграции auth/spend при старте; точечная очистка |
| `niffler-auth` | OAuth2 AS, выдача JWT, `/register` | 9000 | да | Единственный источник JWT; `issuer-uri` gateway указывает на него |
| `niffler-spend` | `/internal/categories/*` + БД | 8093 | да | Реальное состояние категорий; readiness через HTTP-пробу |
| `niffler-gateway` | Публичный API, проверка JWT | 8090 | да | Цель пилота |
| `zookeeper` + `kafka` | Шина событий `users` | 2181, 9092 | фактически да | `depends_on` auth в compose; без них auth стартует (KafkaAdmin `fail-fast=false`, `kafkaTemplate.send` асинхронный — статически), но регистрация логирует async-ошибки отправки — непроверенный риск |
| `niffler-userdata` | Профили пользователей | 8089 | нет | Категории keyed по `username` из JWT `sub`; userdata не вызывается |
| `niffler-currency` | gRPC/REST валюты | 8091/8092 | нет | Нужен только для spends/stat; gRPC-клиенты ленивые |
| `frontend` | SPA | 80 | нет | `redirect_uri` не требует живого фронта: код берётся из заголовка `Location` |
| `selenoid`, `allure`, `niffler-e-2-e` | UI/e2e | — | нет | Профиль `test`, не стартуют без `--profile` |

Зависимости запуска: gateway выполняет OIDC discovery по
`issuer-uri: http://auth.niffler.dc:9000` **на старте** и не поднимется без
доступного auth (подтверждается `depends_on: service_healthy` в compose).
Auth и spend требуют postgres на старте (Flyway). gRPC-клиенты currency и
SOAP-клиент userdata в gateway/spend подключаются лениво и на категории
не влияют.

## Сборка образов и привязка к SHA

Jib-конфиги: `to.image = qaguru/<module>-${PROFILE}` с тегами `latest` и
`${project.version}` (`auth 2.4.1`, `spend 2.1.0`, `gateway 2.2.0`);
профиль `docker` вшивается в образ через
`-Dspring.profiles.active=${PROFILE}` на этапе сборки.
`jibDockerBuild` зависит от `test` — unit-тесты модулей выполняются
перед сборкой образа (у gateway на base SHA `test` — NO-SOURCE).

Оба тега (`latest`, version) мутабельны и перезаписываются каждой сборкой —
идентичность версии только по ним недопустима. Порядок привязки:

```sh
cd /Users/zenalark/PycharmProjects/Test-java/niffler-py-st3
git rev-parse HEAD            # зафиксировать SHA; дерево должно быть чистым
export JAVA_HOME=/opt/homebrew/opt/openjdk@21
export PROFILE=docker
sh gradlew :niffler-auth:jibDockerBuild :niffler-spend:jibDockerBuild \
           :niffler-gateway:jibDockerBuild
SHA8=$(git rev-parse --short=8 HEAD)
for m in auth spend gateway; do
  docker tag qaguru/niffler-$m-docker:latest qaguru/niffler-$m-docker:$SHA8
done
# в evidence: docker image inspect по каждому образу (Id/RepoTags/RepoDigests)
```

Для head-прогона сборка повторяется на head SHA с теми же командами;
`$SHA8`-тег различает базовый и исправленный образы. Изменять compose
или build-файлы под дополнительные теги не требуется.

## Runbook A — compose-проект пилота (рекомендуемый)

Использует штатный `docker-compose.yml` без изменений. `-p catupdval`
ограничивает старт/остановку ресурсами проекта; `down` удаляет только их.

```sh
cd /Users/zenalark/PycharmProjects/Test-java/niffler-py-st3

# префлайт: конфликт фиксированных имён и занятых портов
docker ps -a --format '{{.Names}}' | grep -E 'niffler|selenoid' && echo CONFLICT
# ожидаемые host-порты должны быть свободны: 5432 2181 9092 9000 8090 8093
lsof -nP -iTCP:5432 -iTCP:9092 -iTCP:9000 -iTCP:8090 -iTCP:8093 -sTCP:LISTEN

# старт: depends_on подтянет niffler-all-db + zookeeper + kafka
PREFIX=qaguru docker compose -p catupdval up -d \
  auth.niffler.dc spend.niffler.dc gateway.niffler.dc

# readiness
PREFIX=qaguru docker compose -p catupdval ps     # niffler-all-db Healthy, auth Healthy
curl -fsS http://localhost:9000/actuator/health                    # {"status":"UP"}
curl -fsS http://localhost:9000/.well-known/openid-configuration   # issuer http://auth.niffler.dc:9000
curl -fsS 'http://localhost:8093/internal/categories/all?username=__probe__'  # [] (у spend нет actuator)
curl -fsS http://localhost:8090/actuator/health                    # {"status":"UP"}

# стоп/удаление только ресурсов пилота (БД ephemeral, volume не создаётся)
PREFIX=qaguru docker compose -p catupdval down
```

Ограничения: `container_name` в compose фиксированы — при любом другом
запущенном niffler-стеке `up` упадёт на конфликте имён (префлайт выше).
Параллельный запуск двух niffler-стеков этим способом невозможен.
`docker-compose-{dev,e2e}.sh` и `localenv.sh` **не использовать**: в них
глобальная остановка/удаление всех контейнеров и образов.

## Runbook B — `docker run` в выделенной сети (альтернатива)

Не требует compose и даёт уникальные имена контейнеров; подходит при
занятых `container_name` или необходимости параллельной изоляции
(host-порты при конфликте перепубликовать, порты внутри сети неизменны).
Network-alias'ы воспроизводят DNS-имена docker-профиля.

```sh
docker network create catupdval-net
docker run -d --name catupdval-db --network catupdval-net --network-alias niffler-all-db \
  -e CREATE_DATABASES=niffler-auth,niffler-spend \
  -e POSTGRES_PASSWORD='<см. docker-compose.yml>' -e TZ=GMT+3 -e PGTZ=GMT+3 \
  -v "$PWD/postgres/script:/docker-entrypoint-initdb.d" -p 5432:5432 \
  postgres:15.1 postgres -c max_prepared_transactions=100
docker run -d --name catupdval-zk --network catupdval-net --network-alias zookeeper \
  -e ZOOKEEPER_CLIENT_PORT=2181 -p 2181:2181 confluentinc/cp-zookeeper:7.3.2
docker run -d --name catupdval-kafka --network catupdval-net --network-alias kafka \
  -e KAFKA_BROKER_ID=1 -e KAFKA_ZOOKEEPER_CONNECT=zookeeper:2181 \
  -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka:9092 \
  -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 \
  -e KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1 \
  -e KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1 \
  -p 9092:9092 confluentinc/cp-kafka:7.3.2
docker run -d --name catupdval-auth  --network catupdval-net --network-alias auth.niffler.dc  -p 9000:9000 qaguru/niffler-auth-docker:$SHA8
docker run -d --name catupdval-spend --network catupdval-net --network-alias spend.niffler.dc -p 8093:8093 qaguru/niffler-spend-docker:$SHA8
docker run -d --name catupdval-gw    --network catupdval-net --network-alias gateway.niffler.dc -p 8090:8090 qaguru/niffler-gateway-docker:$SHA8
```

Readiness те же + `docker exec catupdval-db pg_isready -U postgres`.
Остановка строго по именам:

```sh
docker rm -f catupdval-gw catupdval-spend catupdval-auth catupdval-kafka catupdval-zk catupdval-db
docker network rm catupdval-net
```

Строгий минимум без kafka/zookeeper возможен (auth стартует — статически),
но не рекомендуется как непроверенный; при исключении kafka регистрация
должна логировать async-ошибку отправки в топик `users`, не влияющую на
категории — проверяется первым реальным прогоном.

## Авторизация: получение JWT (единственный путь)

В `niffler-auth` зарегистрированы только public-клиенты `authorization_code`
с PKCE (`requireProofKey(true)`): `client` (redirect
`http://frontend.niffler.dc/authorized` в docker-профиле) и `mobile-client`
(`app://ru.niffler_android/callback`). `requireAuthorizationConsent(true)`.
Client credentials / password grant отсутствуют — другого источника JWT нет.

Последовательность (все запросы на `http://localhost:9000`; cookie-сеанс):

1. `GET /oauth2/authorize?response_type=code&client_id=client&scope=openid
   &redirect_uri=http://frontend.niffler.dc/authorized
   &code_challenge=<S256>&code_challenge_method=S256` → 302 на `/login`;
   следовать только по относительным Location на том же origin
   (`localhost:9000`), храня `JSESSIONID` и `XSRF-TOKEN`.
2. `POST /login` (form): `username`, `password`, `_csrf=<XSRF-TOKEN>` →
   302 обратно на `/oauth2/authorize?...`.
3. Для свежего пользователя — страница consent (200): `POST /oauth2/authorize`
   (form) с `client_id`, `state` из страницы, `scope=openid`, `_csrf`.
   Повторные прогоны того же пользователя пропускают этот шаг (запись в
   `oauth2_authorization_consent`). Контракту 06: форму consent разбирать
   динамически — статический анализ, подтверждение при первом прогоне.
4. 302 на `http://frontend.niffler.dc/authorized?code=<code>` —
   **не резолвить и не запрашивать frontend**; `code` из `Location`.
   TTL кода 10 с — обмен немедленно.
5. `POST /oauth2/token` (form): `grant_type=authorization_code`, `code`,
   `redirect_uri` как в п.1, `client_id=client`, `code_verifier` —
   без `Authorization`-заголовка (метод аутентификации клиента `NONE`;
   Basic-заголовок с пустым секретом из учебного клиента не переносить —
   риск `invalid_client`, не проверено).
   Ответ: `access_token` (JWT, `iss=http://auth.niffler.dc:9000`, TTL 1 ч).
6. Использование: `Authorization: Bearer <token>` к gateway. `sub` клейма =
   username; gateway подставляет его в downstream вместо поля тела.

Учебный `OAuthClient` (`study_AL_14_kafka`) как рабочий не считается:
`redirect_uri=.../authorize` (у нас `/authorized`), в `code_challenge`
передаётся `self.session.code` (None), `code` читается списком, consent
не обрабатывается, шлётся Basic-заголовок с пустым секретом, helper
выполняет двойной запрос (всё — assessment + проверка по коду).

## Данные: пользователь, категории, лимиты, очистка

**Пользователь** — выделенный, один на прогон (например `catupd-<run>`):
`POST http://localhost:9000/register` (form): `username` (3–50),
`password`, `passwordSubmit` (**3–12 символов каждое**), `_csrf` → 201.
Публичный endpoint, авторизация не нужна. Создаёт `user`+`authority`
(read, write) в `niffler-auth`; kafka-событие для userdata не требуется.
Fallback, если /register не подтвердится: SQL-вставка в `"user"`/`"authority"`
с bcrypt-хешем (delegating encoder) — решение координатора, не применено.

**Категория** — по одной на параметр (итого ≤6 активных):
`POST /api/categories/add` с Bearer: `{"name": "<уникальное>",
"archived": false}` → 200; `username` берётся из JWT, `id` из ответа.
Имя: валидное (2–50, не `"Archived"` в любом регистре — иначе 500),
уникальное в рамках пользователя; перед созданием `GET all` — проверка
коллизий и счётчика.

**Лимиты**: активных категорий ≤8 на пользователя (`count > 7` → 406
Not Acceptable через gateway). Уникальность `(name, username)` в БД →
409 Conflict при дубле. Свежий выделенный пользователь исключает оба
случая штатно; коллизия/лимит — ошибка подготовки.

**Snapshot/повторное чтение**: `GET /api/categories/all?
excludeArchived=false`, поиск по `id`; поля `id,name,username,archived`.
PATCH-тело: `{"id","name","username","archived"}` со snapshot-`archived`
(`false`): пропуск `archived` даст `false` — для наших данных безопасно,
но по сценариям передаём исходное значение явно.

**Очистка** — только созданное, строго по `id` (публичного delete нет;
архивация ≠ удалению):

```sql
-- БД niffler-spend
DELETE FROM category WHERE id IN ('<uuid>', ...);
```

`spend.category_id → category.id` — FK: перед удалением категории не должно
быть расходов (пилот их не создаёт). Категории удалять всегда, включая
падение assertions (teardown фикстуры). Пользователь прогона: на disposable
стенде можно оставить до `down`; при переиспользовании стенда —
`DELETE FROM oauth2_authorization_consent WHERE principal_name='<u>';
DELETE FROM oauth2_authorization WHERE principal_name='<u>';
DELETE FROM authority WHERE user_id IN (SELECT id FROM "user" WHERE
username='<u>'); DELETE FROM "user" WHERE username='<u>';` — в этом
порядке (`"user"` — зарезервированное слово, кавычки обязательны).
Альтернатива любой точечной очистке — пересоздание контуров БД
(`compose down` + `up`, данные ephemeral) перед каждым прогоном.

## Контракт fixtures для агента 06

Входы окружения (только имена; значений секретов в коде/отчётах нет):

| Переменная | Пример значения | Назначение |
| --- | --- | --- |
| `API_BASE_URL` | `http://localhost:8090` | gateway пилотного стенда |
| `API_AUTH_URL` | `http://localhost:9000` | OAuth2 AS пилотного стенда |
| `API_USERNAME` / `API_PASSWORD` | из env | выделенный пользователь прогона |
| `API_SPEND_DB_DSN` | `postgresql://postgres:<pwd>@localhost:5432/niffler-spend` | точечная очистка категорий |
| `API_AUTH_DB_DSN` | `.../niffler-auth` | опционально: очистка пользователя |
| `API_USER_AUTOPROVISION` | `true` | разрешить fixtures `/register` |

Фиксированные данные — `test_data/consts/category_update.py`
(конвенция проекта): `OAUTH_CLIENT_ID="client"`,
`OAUTH_REDIRECT_URI="http://frontend.niffler.dc/authorized"`,
`OAUTH_SCOPE="openid"`, граничные имена `A×1/2/50/51`, `""`, `"   "`,
маска полей snapshot.

Fixtures (семантика, размещение определяет 06 в `tests/api/conftest.py`):

- `api_settings` (session): читает env выше; отсутствие обязательной
  переменной → ошибка подготовки с перечнем недостающего (как
  `MissingTestDataError` в `test_data`), не skip и не fake PASS.
- `api_token` (session): PKCE-flow раздела выше; любой сбой шага
  (статус, отсутствие `code`, невалидный JSON token-ответа) → ошибка
  подготовки с указанием шага. Токен, cookies, `_csrf`, `code_verifier`
  не попадают в логи/вложения; `Authorization` редактируется.
- `categories_api` : транспорт GET all / POST add / PATCH update; каждый
  метод — ровно один HTTP-запрос, возвращает `(status, body)` без
  `raise_for_status`; ожидаемые 4xx/5xx не исключение.
- `own_category` (function): генерирует уникальное валидное имя →
  GET all (коллизия/лимит → ошибка подготовки) → POST add (≠200 →
  ошибка подготовки с телом ответа) → snapshot `{id,name,username,
  archived}` → yield → teardown: `DELETE ... WHERE id=<id>` + контрольный
  GET. Ошибку очистки фиксировать в evidence, не маскировать результат
  теста. Teardown выполняется при любом исходе.
- При недоступности env/token/БД — тестовая сессия завершается ошибкой
  подготовки, прогон не маркируется выполненным (правило 06/harness).

## Операции с побочными эффектами (на согласование scope)

1. `git checkout`/verify SHA в `niffler-py-st3` (read-only по факту).
2. `gradlew jibDockerBuild` ×3 модуля: unit-тесты, pull базового образа
   `eclipse-temurin:21-jdk` (arm64v8 на этом хосте), создание локальных образов.
3. `docker pull` `postgres:15.1`, `confluentinc/cp-zookeeper:7.3.2`,
   `confluentinc/cp-kafka:7.3.2`.
4. `docker compose -p catupdval up/down` либо `docker network create` +
   `docker run/rm` — старт/остановка контейнеров, публикация host-портов.
5. HTTP-записи: `POST /register`, OAuth-flow (сессии/authorizations в БД),
   `POST /api/categories/add`, `PATCH /api/categories/update`.
6. SQL: `DELETE` на `category` (по id), опционально `user`/`authority`/
   `oauth2_*` (по username) — прямые изменения БД изолированного стенда.
7. Evidence: запись в `artifacts/` тестового проекта; в отчётах — URL без
   credentials, токены/пароли/куки редактируются.

## Решения и блокеры

- **Вариант стенда**: рекомендован Runbook A (`compose -p catupdval`) —
  меньше ручных команд, штатные healthcheck/depends_on; при конфликте имён
  или потребности в параллельности — Runbook B. Решение за координатором.
- **Точечная очистка**: единственный подтверждённый способ удаления
  категории — SQL `DELETE` по `id` в `niffler-spend` (публичного endpoint
  нет; archive не удаляет). Если прямой доступ к БД стенда не разрешён —
  **блокер реального прогона**: alternatives только пересоздание БД на
  прогон (допустимо, но меняет contract `own_category`) или накопление
  данных (нарушает сценарии). Нужно решение до 06/07.
- **Consent-страница OAuth**: форма и необходимость шага — статический
  вывод (`requireAuthorizationConsent(true)`); подтверждается первым
  реальным прогоном; контракт требует динамического разбора формы.
- **Kafka**: включена в оба runbook; исключение — непроверенная оптимизация.
- **Credentials**: пароль postgres и креды выделенного пользователя — только
  env/локально, не в отчётах и константах; DSN приходит из env целиком.
- **Доступность не подтверждена**: Docker daemon, реестр образов,
  скачивание базовых образов, реальное поведение consent/PKCE — всё
  проверяется при первом исполнении runbook агентом 07 после разрешения scope.
- **Образы под внешним тегом**: `qaguru/*-docker:latest` мутабельны —
  обязательная фиксация `$SHA8`-тега и `docker inspect` Id в evidence.

## Подтверждено / не проверялось

Подтверждено статически (исходники на base SHA, compose, миграции, jib):
состав минимального контура и зависимости старта; endpoint'ы и контракты
category API; единственность authorization_code+PKCE источника JWT;
параметры клиента `client` и redirect `/authorized`; TTL кода/токена;
лимит 8 и уникальный индекс `(name, username)`; отсутствие delete API;
формат `/register` и ограничения 3–50/3–12; eager OIDC discovery gateway;
асинхронность kafka-отправки при регистрации; отсутствие actuator у spend;
дефекты учебных клиентов.

Не проверялось (вне области задачи): запуск любых контейнеров/образов,
Docker daemon и реестры, реальный OAuth-flow и consent-форма, реальные
HTTP-ответы на base SHA, поведение auth без kafka, SQL-очистка на живой БД.

## Передача

- Агенту 06: контракт fixtures и env-входы выше; реализация может
  начинаться — все вводы определены, стенд для кода не требуется.
- Координатору до 07: выбрать Runbook A/B, разрешить/запретить точечную
  SQL-очистку и автопровижининг пользователя, подтвердить scope операций
  с побочными эффектами и источник credentials (env).
- Агенту 07: исполняемый runbook и readiness-пробы выше; фиксировать
  SHA, `$SHA8`-теги, `docker inspect` Id, команды и результаты cleanup.
