# Передача результата: финальный API execution с закреплёнными TestOps ID (17C)

Агент: `17C`. Дата: 2026-11-15. Статус: `needs_decision`.

**Документированной приёмки 17A/17B координатором не найдено.** По условию
поручения выполнена вся доступная проверка входов; запуск SUT (стек, прогон,
bind-пакет) не выполнялся до появления приёмки. Внешних вызовов, записей,
изменений кода/приложения/общих файлов и исторических evidence не было.

## Отсутствующий вход

- Последний документ координации — `coordination-wave-13.md` (2026-11-15 14:55),
  который закрыл этап 16 и выдал поручение 17 целиком. Он предшествует
  обоим отчётам исполнителей: `17a-allure-ids.md` (15:06) и
  `17b-runtime-readiness.md` (15:05).
- Wave-14, акта приёмки 17A/17B или иного решения координатора по входам
  17C в репозитории нет (проверено `docs/`, `agent-tasks/`, `handoffs/`).
- По аналогии с этапом 16 (приёмка 16A/16B оформлялась отдельным документом
  до публикации) запуск SUT отложен до документированной приёмки.

## Проверка входов 17A (принятый код маркировки) — подтверждено

| Проверка | Результат |
| --- | --- |
| sha256 `tests/api/test_category_update.py` | `ebd9deaa18398c306cac5f9ecacc4c554423477c8e38889fd41847878fa7e359` — совпадает с `after.sha256` 17A |
| sha256 `test_data/consts/category_update.py` | `c66a9a9f94e6a53286e53105212111217e2113de51f78690790cb664c83d3933` — совпадает |
| sha256 `knowledge/components/consts.md` | `a1f203a3a61165e000f894aba4260ec05b57c0aabbbe158499482efadc9bc8f0` — совпадает |
| diff копий `before/` 17A ↔ текущие файлы | только маркировка: импорт `TESTOPS_ALLURE_ID_BY_NAME`, по одному шагу `allure.dynamic.label("ALLURE_ID", …)` на тест, блок констант `TESTOPS_ALLURE_IDS`/`…_BY_NAME`. Параметры, ids, assertions, fixtures, cleanup, HTTP-поведение не изменены |
| `pytest tests/api/test_category_update.py --collect-only -q` | exit 0, 6 node IDs прежние `[CAT-UPD-VAL-001]`–`[006]` |
| Маппинг в константах | совпадает с wave 12/13: 001→55376, 002→55374, 003→55375, 004→55377, 005→55373, 006→55378 |

Оба файла пилота остаются untracked, как записано у 17A. Прогон unit
`artifacts/harness/run-f6rmfrdj/` (233 passed, из отчёта 17A) существует.

## Проверка входов 17B (готовность окружения) — перепроверено сейчас

| Проверка | Результат |
| --- | --- |
| Docker / Compose / JDK | server 29.7.2, API 1.55, linux/arm64; compose v5.5.0; JDK 21.0.12.1 (`/opt/homebrew/opt/openjdk@21`) |
| Конфликты `catupdval` | контейнеров и сетей проекта нет; имён `niffler|selenoid|catupd` нет вообще |
| Порты 5432/2181/9092/9000/8090/8093 | свободны (`lsof -sTCP:LISTEN` → exit 1, совпадений нет) |
| Чужие ресурсы | работают `ai-first-student-workspace-*`; пилотные порты не заняты, не затрагивались |
| Образы (`docker image inspect`) | fix gateway `sha256:f496835fbad4dd72fa650f4b27d1b7c171d40e73d662da929aab1a8c4162614b`, spend `sha256:fb10c075a21edab38c3309a8f1b4f848afa29c71ae00b5c29d3205ba9a13905e`, auth `sha256:f18b5255ea61d8974b724dd079944192b0dd1a7139b1484982d8992910981af9` — все на месте; тег `:latest` каждого сейчас указывает на эти же ID |
| Приложение `niffler-py-st3` | HEAD `36674280b6878540a9e88f40aaeedf5dfdd2e6ce` (`main`); дерево = `M CategoriesController.java` + `?? src/test/`; `git diff` sha256 `04eb4c874139610869793f0c72843b1a9cb338832973697cf56e25b7ba87937e` = принятому patch SHA; хеши целевых файлов совпадают с handoff 10 (`32aec8fb…`, `d0e0fb63…`, `eea6de8d…`) |
| Compose render | `PREFIX=qaguru docker compose -p catupdval config` отдаёт сервисы пилота и `qaguru/niffler-{auth,gateway,spend}-docker:latest` (мутабельные теги → перепривязка к image ID в runbook 17B сохраняется обязательной) |
| `.env` | имена `API_BASE_URL`, `API_AUTH_URL`, `API_USERNAME`, `API_PASSWORD`, `API_SPEND_DB_DSN`, `API_USER_AUTOPROVISION` присутствуют; значения не печатались. Пользователь прогона должен быть задан новый (`catupd-f-<suffix>`) |
| TestOps state | только `run-5tsmzg1d` и `run-vzsatlfk`; `run-5tsmzg1d/state.json` sha256 `6da4472277dc42aa4e5136b9574d1521c38105f30c3ad1f944fdde2e7cae57e8` = записи wave 13 — не изменён; lock не захватывался |

## Команды (все read-only, без SUT/сети/TestOps)

| Команда | Exit |
| --- | --- |
| `shasum -a 256 <3 файла 17A>` | 0, совпадение с `after.sha256` |
| `diff -u before/<file> <current>` (2 файла) | 1, только ожидаемые добавления маркировки |
| `pytest tests/api/test_category_update.py --collect-only -q` | 0, 6 собрано |
| `docker version`, `docker compose version`, `java -version` | 0 |
| `docker ps -a` / `docker network ls` (фильтры catupdval, имён) | 0, пусто |
| `lsof -nP -iTCP:… -sTCP:LISTEN` | 1 (совпадений нет) |
| `docker image inspect sha256:<id>` ×3 | 0 |
| `git rev-parse HEAD`, `git status`, `git diff \| shasum` (app) | 0 |
| `PREFIX=qaguru docker compose -p catupdval config` | 0 |
| `git diff --check` (тестовый проект) | 0 |

## Что заблокировано до приёмки

1. Запуск disposable-стека `catupdval` и один fix-прогон шести сценариев
   через harness с `--app-base-sha`/`--app-patch-sha256`/`--gateway-image-id`/
   `--gateway-container` (команды готовы в runbook 17B).
2. Live binding до/после, cleanup, post-down evidence.
3. Проверка `ALLURE_ID` в новых исходных result JSON и подготовка локального
   `--mode bind` пакета для проекта 5444 (пары согласованы, отдельного
   разрешения на локальный assign не требуется — но сам пакет требует
   нового execution).

## Решение координатора

Нужен документированный акт приёмки 17A/17B (например, wave-14 или отдельная
запись): подтверждение принятых SHA маркировки выше и принятого плана 17B.
После этого 17C выполняет runbook из `17b-runtime-readiness.md` без
дополнительных согласований в пределах прежнего scope.

## Evidence

`artifacts/final-execution/17c-20261115T120805Z/` (gitignored):
`summary.txt`, `01-tools.txt`, `03-conflicts.txt`, `04-ports.txt`,
`06-image-ids.txt`, `07-app-source-identity.txt`, `08-compose-render.txt`,
`08b-compose-images.txt`, `09-env-and-state.txt`.

## Не выполнялось

- SUT/стек/контейнеры, API-прогон, регистрация пользователя — до приёмки.
- plan/assign/package нового execution, любые операции TestOps — не было
  нового execution и сети.
- Изменения кода, приложения, harness, исторических evidence и state —
  не выполнялись; чужие незакоммиченные изменения сохранены.
