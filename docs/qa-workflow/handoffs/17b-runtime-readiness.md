# Передача результата: подготовка окружения финального API-прогона

Агент: `17B`. Дата: 2026-11-15. Статус: `ready` — готов проверяемый
план запуска одного нового fix execution. **API-прогон, сборка, запуск
стека и любые внешние записи не выполнялись.** `ready` означает готовность
плана, а не выполненный прогон.

Проверки только read-only: состояние Docker, образы, файлы, git.
Параллельно работающий 17A (маркировка `tests/api/test_category_update.py`,
`test_data/consts/category_update.py`) не затрагивался. Общий execution
state `artifacts/testops/` только читался пассивно, lock не захватывался.
Чужие незакоммиченные изменения сохранены.

Evidence: `artifacts/final-execution/17b-20261115T120337Z/`
(13 файлов проверок + `summary.txt`).

## Версии инструментов (проверено сейчас)

| Инструмент | Версия / состояние | Источник |
| --- | --- | --- |
| Docker engine | 29.7.2, API 1.55, Docker Desktop 4.89.0, linux/arm64 | `01-docker-env.txt` |
| docker compose | v5.5.0 | `01-docker-env.txt` |
| JDK | OpenJDK 21.0.12.1, `/opt/homebrew/opt/openjdk@21` | `02-tools.txt` |
| `/usr/bin/java` | системный stub — **не использовать**, задавать `JAVA_HOME` явно | `02-tools.txt` |
| Gradle wrapper | 8.6 (`distributionUrl`), `gradlew` на месте | `12-app-build-inputs.txt` |
| psql CLI | **отсутствует** → SQL-проверки через psycopg-фикстуры и `docker exec niffler-all-db psql` | `02-tools.txt` |
| git, curl, sh | присутствуют | `02-tools.txt` |

## Конфликты ресурсов (проверено сейчас)

Конфликтов проекта `catupdval` нет (`03-conflicts.txt`, `04-ports.txt`):

- `docker ps -a --filter label=com.docker.compose.project=catupdval` → пусто;
- `docker network ls --filter label=com.docker.compose.project=catupdval` → пусто;
- контейнеров с именами `niffler|selenoid|catupd` нет вообще — фиксированные
  `container_name` из `docker-compose.yml` свободны;
- host-порты 5432/2181/9092/9000/8090/8093 свободны
  (`lsof -sTCP:LISTEN` → exit 1, совпадений нет);
- работают чужие контейнеры `ai-first-student-workspace-*` (postgres:16-alpine
  и др.) — пилотные порты ими не заняты, конфликта нет. Их не останавливать;
  если к моменту прогона появится сторонний niffler-стек — это конфликт для
  17C (фиксировать, не останавливать чужое).

## Образы пилота (image ID проверены `docker image inspect`)

| Назначение | Полный image ID | Теги (мутабельны, не доказательство) |
| --- | --- | --- |
| gateway **fix** | `sha256:f496835fbad4dd72fa650f4b27d1b7c171d40e73d662da929aab1a8c4162614b` | `qaguru/niffler-gateway-docker:catupd10-fix`, `:latest` |
| gateway base | `sha256:1a7afc4df66a7c900c513da9b5684106770cba31b41c609625bbb422e39933bd` | `:catupd10-base`, `:2.2.0` |
| spend | `sha256:fb10c075a21edab38c3309a8f1b4f848afa29c71ae00b5c29d3205ba9a13905e` | `:catupd10`, `:2.1.0`, `:latest` |
| auth | `sha256:f18b5255ea61d8974b724dd079944192b0dd1a7139b1484982d8992910981af9` | `:catupd10`, `:2.4.1`, `:latest` |
| postgres | `02547253a07e` (`postgres:15.1`) | — |
| zookeeper / kafka | `5971e800825c` / `724faab73e5a` (`confluentinc/cp-*:7.3.2`) | — |

Дополнительно присутствует набор образов агента 07 (`d9af26acad99`,
`42715c671874`, `7405b75273ba`, `8a4e863284d4`, теги `catupdval*`) —
для 17C **не использовать**: provenance набора агента 10 сильнее
(записанные команды/время/логи сборки). Полный файл: `06-image-ids.txt`,
инвентарь тегов: `05-image-list.txt`.

## Сопоставление source ↔ build ↔ image

**Подтверждено сейчас** (`07-app-source-identity.txt`, `08-historical-evidence.txt`):

- Приложение `niffler-py-st3`: HEAD `36674280b6878540a9e88f40aaeedf5dfdd2e6ce`
  (`main`), `git worktree list` — только основной checkout;
- рабочее дерево = `M CategoriesController.java` + `?? niffler-gateway/src/test/`;
- `git diff` → sha256 `04eb4c874139610869793f0c72843b1a9cb338832973697cf56e25b7ba87937e`
  — **байт-идентичен принятому patch SHA и сохранённому `base-to-fix.patch`**;
- хеши целевых файлов совпадают со snapshot времени сборки 10:
  controller `32aec8fb…`, `CategoryJson` `d0e0fb63…`, тест `eea6de8d…`;
- четыре image ID выше совпадают с `image-ids-*.txt` handoff 10;
- compose рендерится (`config --services`, exit 0): `PREFIX=qaguru` →
  `qaguru/niffler-*-docker:latest`; предупреждения о `ARCH`/`GITHUB_TOKEN` —
  косметические.

**Известно только из исторического evidence** (нельзя перепроверить без
пересборки): сам факт «образ `f496835f…` собран из base+patch» доказан
записями handoff 10 (build-логи, `source-identity.txt`, снятый за ~1 минуту
до `Created` образа, записанные команды). Сейчас это усилено совпадением
текущего дерева с тем snapshot побайтно, но биты образа не проверяемы.
Для fix-прогона риск приемлем: source identity времени сборки и сейчас
идентичны; live привязка контейнера к полному image ID обязательна и
выполняется harness до старта pytest.

**Вывод: пересборка не требуется.** Запасные команды сборки на случай,
если координатор/17C не примет историческую привязку (выполнять только 17C
после отдельного разрешения, сейчас не выполнялись):

```sh
cd /Users/zenalark/PycharmProjects/Test-java/niffler-py-st3
git rev-parse HEAD   # ожидание 36674280…; дерево = base+patch (уже так)
git diff | shasum -a 256   # ожидание 04eb4c87…
JAVA_HOME=/opt/homebrew/opt/openjdk@21 PROFILE=docker sh gradlew \
  :niffler-auth:jibDockerBuild :niffler-spend:jibDockerBuild :niffler-gateway:jibDockerBuild
# зафиксировать новые полные image IDs; :latest укажет на новую сборку
# base-образ (только если потребуется симметричный baseline): отдельный
# git worktree на base SHA, та же команда только для :niffler-gateway:jibDockerBuild
```

## Runbook для 17C — один fix execution

Последовательность (Runbook A, scope задания 10; baseline не повторять):

```sh
cd /Users/zenalark/PycharmProjects/Test-java/niffler-py-st3

# 1. Конфликты (повторить перед стартом; чужие ресурсы не трогать)
docker ps -a --format '{{.Names}}' | grep -E 'niffler|selenoid|catupd' && echo CONFLICT
lsof -nP -iTCP:5432 -iTCP:2181 -iTCP:9092 -iTCP:9000 -iTCP:8090 -iTCP:8093 -sTCP:LISTEN
docker ps -a --filter label=com.docker.compose.project=catupdval

# 2. Перепривязать мутабельные :latest к зафиксированным image ID
docker tag sha256:f496835fbad4dd72fa650f4b27d1b7c171d40e73d662da929aab1a8c4162614b \
  qaguru/niffler-gateway-docker:latest
docker tag sha256:fb10c075a21edab38c3309a8f1b4f848afa29c71ae00b5c29d3205ba9a13905e \
  qaguru/niffler-spend-docker:latest
docker tag sha256:f18b5255ea61d8974b724dd079944192b0dd1a7139b1484982d8992910981af9 \
  qaguru/niffler-auth-docker:latest

# 3. Старт только сервисов пилота (depends_on поднимет db/zookeeper/kafka)
PREFIX=qaguru docker compose -p catupdval up -d \
  auth.niffler.dc spend.niffler.dc gateway.niffler.dc

# 4. Readiness
PREFIX=qaguru docker compose -p catupdval ps
curl -fsS http://localhost:9000/actuator/health                     # UP
curl -fsS http://localhost:9000/.well-known/openid-configuration    # issuer http://auth.niffler.dc:9000
curl -fsS 'http://localhost:8093/internal/categories/all?username=__probe__'  # []
curl -fsS http://localhost:8090/actuator/health                     # UP
```

```sh
cd /Users/zenalark/PycharmProjects/Test-java/getting-started-python

# 5. Live binding контейнера до прогона (дистиллированные поля, без env)
docker container inspect gateway.niffler.dc --format \
  'id={{.Id}} running={{.State.Running}} image={{.Image}}'
#   ожидание image= sha256:f496835f…; harness повторит проверку перед pytest

# 6. Один fix-прогон шести сценариев (env: свежий API_USERNAME, см. ниже)
sh tools/run-tests.sh --allow-sut group api \
  --app-base-sha 36674280b6878540a9e88f40aaeedf5dfdd2e6ce \
  --app-patch-sha256 04eb4c874139610869793f0c72843b1a9cb338832973697cf56e25b7ba87937e \
  --gateway-image-id sha256:f496835fbad4dd72fa650f4b27d1b7c171d40e73d662da929aab1a8c4162614b \
  --gateway-container gateway.niffler.dc
#   ожидание: exit 0, junit 6/6/0/0/0; manifest environment.container_check
#   performed=true, running=true, matches_declared_image=true

# 7. Binding после прогона — той же командой inspect; образ не должен измениться
# 8. Cleanup-проверка по пользователю прогона (psql CLI нет — через контейнер)
docker exec niffler-all-db psql -U postgres -d niffler-spend -tAc \
  "SELECT count(*) FROM category WHERE username='<API_USERNAME прогона>'"     # 0
docker exec niffler-all-db psql -U postgres -d niffler-spend -tAc \
  "SELECT count(*) FROM category WHERE username LIKE 'catupd-%'"              # 0

# 9. Down только ресурсов пилота + post-down evidence
cd /Users/zenalark/PycharmProjects/Test-java/niffler-py-st3
PREFIX=qaguru docker compose -p catupdval down
docker ps -a --filter label=com.docker.compose.project=catupdval     # пусто
docker network ls --filter label=com.docker.compose.project=catupdval # пусто
```

Запрещённые в прогоне действия: `docker-compose-{dev,e2e}.sh`, `localenv.sh`
(глобальная остановка/удаление), любые глобальные cleanup-скрипты,
остановка чужих контейнеров, TestOps-обращения, публикация.

## Переменные окружения (только имена)

В `.env` тестового проекта уже есть имена; **значения нигде не фиксировать**:

- `API_BASE_URL` — `http://localhost:8090` (gateway стенда);
- `API_AUTH_URL` — `http://localhost:9000` (OAuth2 AS);
- `API_USERNAME` / `API_PASSWORD` — выделенный пользователь прогона
  (сейчас в `.env` пользователь предыдущего прогона — 17C задаёт **новое**
  уникальное имя, напр. `catupd-f-<новый суффикс>`, пароль 3–12 символов);
- `API_SPEND_DB_DSN` — DSN `niffler-spend` для cleanup-фикстур;
- `API_USER_AUTOPROVISION=true` — разрешение `/register` в фикстурах;
- `API_AUTH_DB_DSN` — опционально (очистка пользователя; сейчас отсутствует,
  не требуется — БД ephemeral);
- `PREFIX=qaguru` — только для compose-команд; `JAVA_HOME`/`PROFILE=docker` —
  только для запасной сборки. `EXISTING_*`, `ALLURE_TOKEN` прогону не нужны.

Полный `docker container inspect` с env не сохранять; токены/пароли/DSN —
не в evidence.

## Пользователь и очистка

- Один выделенный пользователь на прогон через `POST /register`
  (`API_USER_AUTOPROVISION=true`), OAuth authorization code + PKCE,
  consent-форма разбирается динамически — подтверждено прогонами 07/10.
- Категории создаются фикстурой по одной на параметр; teardown —
  параметризованный `DELETE FROM category WHERE id=%s AND username=%s`
  по каждой созданной категории + контрольный GET, при любом исходе теста.
  Глобальные cleanup-скрипты не запускать; узкое условие — строго
  собственные `id`+`username` прогона.
- Контрольные SQL-запросы после прогона — в п.8 runbook (0 строк).
- Пользователь прогона остаётся в `niffler-auth` до `compose down`
  (ephemeral БД удаляет его вместе со стеком); при аварийном броске стека —
  точечное удаление по username из задания 03.

## Входы, которые 17C должен получить от 17A

1. Принятый diff/SHA маркировки: содержимое и sha256 изменённых
   `tests/api/test_category_update.py` и `test_data/consts/category_update.py`
   (ожидаемо отличаются от исторического `api-contract-v1` — версию контракта
   не менять, manifest не подгонять).
2. Mapping шести `ALLURE_ID`, фактически сериализованных в новых result JSON:
   CAT-UPD-VAL-001→55376, 002→55374, 003→55375, 004→55377, 005→55373,
   006→55378 (wave 12; по одному ID на параметризованный случай, не один на
   функцию).
3. Подтверждение неизменности API-поведения: те же параметры, node ID,
   PATCH/GET assertions, fixtures/cleanup — прогон 17C должен отличаться
   от `run-5tsmzg1d` только добавленными `ALLURE_ID`-лейблами.

## Ограничения

- Стек, образы, БД, регистрация, API и TestOps не трогались; план
  не проверен исполнением.
- Привязка образа к исходникам — историческая (см. раздел выше); полная
  перепроверка требует пересборки по запасным командам — решение координатора.
- `.env` содержит пользователя прошлого прогона — валиден только с новым
  стеком и только после установки свежего `API_USERNAME`/`API_PASSWORD`.
- compose `container_name` фиксированы: появление стороннего niffler-стека
  до прогона — конфликт для 17C, его ресурсы не останавливать.
- `psql` CLI отсутствует — SQL-проверки через `docker exec niffler-all-db psql`
  либо psycopg-фикстуры.
- Маркировка 17A в работе: хеши двух файлов контракта изменятся — это
  ожидаемо, не дефект.
