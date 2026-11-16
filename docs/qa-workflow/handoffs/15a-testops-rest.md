# Передача результата: read-only REST probe снимка launch TestOps

Агент: `15A`. Дата: 2026-11-14. Статус: `ready` — получение и
нормализация снимка реализованы и покрыты offline-тестами; живой запрос,
непустой launch и подключение к CLI в область поручения не входили и не
выполнялись. Параллельно работал агент 15B (сравнение снимка с
execution); его файлы не изменялись, общий контракт
`read_snapshot(endpoint, launch_id) -> dict` соблюдён без изменений.

Область записи соблюдена: `infrastructure/reporting/testops/rest.py`,
`tests/unit/test_testops_rest.py`, `test_data/consts/testops_rest.py`,
этот handoff и evidence собственных проверок
(`artifacts/harness/run-ozfx_3mb/`). `client.py`, `state.py`,
`lifecycle.py`, `tools/testops.py`, `api-contract-v1`, существующие
state и исторические evidence не затрагивались. `.env`/токен не
читались; сетевых вызовов, create/upload/close/delete, Docker/Gradle,
commit/push не было.

## Что реализовано

`infrastructure/reporting/testops/rest.py`:

- `RestProbe(token, *, http=None, timeout_s=30, page_size=100,
  max_pages=100)` — без сети и файлового I/O при импорте и создании.
  `http` — инъецируемый слой `request(endpoint, method, path, *,
  headers=None, form=None) -> response(.status:int, .body:bytes)`;
  по умолчанию `UrllibHttp` — обёртка над существующим
  `infrastructure.http.client.HttpClient` (stdlib urllib, без новых
  зависимостей): валидация HTTP(S)-origin без credentials, отказ от
  любых redirect (чужой origin недостижим по построению), bounded
  timeout на запрос, автоматических повторов нет.
- `RestProbe.read_snapshot(endpoint, launch_id)` — один запуск = один
  обмен `POST /api/uaa/oauth/token` (`grant_type=apitoken`,
  `scope=openid`, `token` в теле формы, никогда в URL), затем
  последовательно: `GET /api/launch/{id}` → `GET .../progress` →
  `GET .../statistic` → строгий обход `GET /api/testresult` → повторный
  `GET /api/launch/{id}` (drift-контроль). Чтение останавливается на
  первой ошибке секции; уже собранные поля остаются в снимке.
  KeyboardInterrupt/SystemExit пробрасываются вызывающему.
- Модель ошибок возвращается контрактным dict, без сырых HTTP
  исключений: `reason` содержит только имя операции и HTTP status —
  payload, headers, токен и JWT в снимок не попадают (проверено
  unit-тестом гигиены секретов).

## Контракт снимка (без изменений)

```python
{"outcome": "complete" | "missing" | "unreachable" | "inconclusive",
 "reason": str,
 "launch": {"id": int, "project_id": int, "closed": bool} | None,
 "ready": bool | None,
 "stats": {status: nonnegative_int} | None,
 "results": [{"id", "name", "status", "test_case_id", "launch_id",
              "project_id", "hidden", "retried_by_id"}],
 "pagination": {"complete": bool, "pages": int,
                "total_elements": int | None}}
```

- `outcome=complete` — все ответы прочитаны, схемы валидны, обход
  доказал полноту набора. Это НЕ `uploaded`: `closed=false` или
  `ready=false` остаются допустимым полным снимком; вердикт выносит
  15B. Статусы `in_progress`/`unknown` сохраняются как есть
  (lowercase), статистика `{}` — легитимный полный снимок.
- `missing` — только прямой 404 на `GET /api/launch/{id}` (включая
  повторный GET: launch, исчезнувший во время чтения, тоже missing;
  при этом `launch` может хранить первое наблюдение — честный
  снимок прочитанного, outcome авторитетен).
- `unreachable` — не-200 на обмене токена и любых GET (включая 403 на
  results для существующего launch — не «launch отсутствует»),
  транспортные ошибки/timeout, малформированный ответ транспорта.
- `inconclusive` — невалидный JSON, нарушение схемы (в т.ч. отсутствие
  обязательных allowlist-полей), невозможность доказать полноту
  обхода, drift launch-метаданных, невалидный `launch_id`.
- При ошибке обязательные поля не подставляются: `launch/ready/stats`
  остаются `None`, `results` и `pagination` содержат только честно
  собранное.

## Проверки обхода Page (строгие, все → inconclusive при нарушении)

Запрашиваются только подтверждённые параметры `launchId`, `page`,
`size` (sort не выдумывается — применяется документированный
OpenAPI-дефолт `createdDate,DESC`; нестабильность ловится проверками,
а не обходится):

- `number` обязан равняться запрошенной странице (повтор/пропуск
  страницы);
- `totalElements`/`totalPages` фиксируются на первой странице и обязаны
  быть неизменными на всех следующих (изменение набора за чтение);
- пустая страница без `last` — обрыв, не конец обхода;
- `last` на странице, не совпадающей с `totalPages-1`, `last=false` при
  исчерпанном `totalPages`, элементы за пределами `totalPages`,
  `totalElements>0` при `totalPages=0` — противоречия;
- повтор `id` результата между/внутри страниц;
- на `last` — собранное число результатов обязано равняться
  `totalElements`;
- лимит `max_pages` (по умолчанию 100); изменение `id/projectId/closed`
  launch за время чтения обозначается неполнотой.

## Нормализация allowlist

Результат: `id`, `name`, `status`, `test_case_id` (`testCaseId`,
nullable), `launch_id` (обязан равняться запрошенному), `project_id`,
`hidden`, `retried_by_id` (`retriedBy.id`, nullable). `hidden`/
`retriedBy`-строки не отбрасываются — их оценивает 15B. Тела,
parameters, trace, attachments и прочие поля `TestResultDto` не
сохраняются. `statistic` `[{status,count}]` → `{status.lower(): count}`
с проверкой дубликатов и неотрицательности.

## Источники контрактов

- OpenAPI 3.1.0 allure-testops-service `527u01` (distill:
  `artifacts/testops-readonly/14b-155530/02-openapi-extract.json`) —
  `LaunchDto{id,projectId,closed}`, `LaunchProgressDto{ready}`,
  `TestStatusCount[]{status,count}`, `PageTestResultDto`.
- Live-наблюдения 14B: page-обёртка, 404 launch, 403 на
  results/progress для несуществующего launch.
- Непустые ответы results/progress/statistic подтверждены только
  OpenAPI — серверный probe **не объявляется проверенным живым
  непустым launch**.

## Проверки этого агента

| Команда | Результат |
| --- | --- |
| `sh tools/run-tests.sh group unit` | exit 0, **222 passed** (файл probe: 38 тестов) |
| `sh tools/git.sh check` | exit 0 |

Evidence: `artifacts/harness/run-ozfx_3mb/` (manifest, junit.xml,
allure-results). Покрытие offline: импорт/конструкция без сети,
успех/провал обмена без утечки credentials, 2 страницы, пустой набор,
ранняя пустая страница, повтор страницы/id, изменение totals,
`last`/`totalPages`-противоречия, лимит страниц, обязательные поля,
404 launch и 403 results, transport/5xx/invalid JSON/не-объект/
малформированный транспорт, `ready=false`+`closed=false`,
`in_progress`, `hidden`/`retriedBy`, drift launch (изменение,
исчезновение, стабильность).

## Ограничения

- Живого запроса не было; реальная непустая форма ответов не
  подтверждена. Первый боевой прогон должен вручную сверить
  `closed`/`ready` со статистикой (рекомендация 14B сохраняется).
- Тело ответа читается целиком (`HttpClient` без лимита размера);
  при page_size=100 и allowlist-нормализации риск ограничен, но
  жёсткой границы байт нет.
- Повторный `GET launch` после обхода — детекция drift по
  id/projectId/closed; `ready` и `stats` между чтениями не сверяются
  (их изменение при закрытии — легитимное событие обработки).
- `RestProbe` не реализует `get_launch`/`list_launch_results`
  интерфейс `perform_verify` напрямую: точка входа — `read_snapshot`,
  сравнение с ожиданием — модуль 15B `verification.py`
  (`evaluate_snapshot`/`perform_snapshot_verify`), совместимость
  подтверждена прохождением его unit-тестов контракта в этом же
  прогоне.
- Токен обязателен при создании (`ValueError`); невалидный
  `launch_id` → `inconclusive` без сети.

## Действия координатору для подключения CLI

1. В `tools/testops.py` (после объединения с 15B): для `verify
   --online` создать `rest.RestProbe(_token())`, вызвать
   `verification.perform_snapshot_verify(state_dir, probe, ...)`
   по интерфейсу handoff 15B; exit-code маппинг verdict'ов — как в
   `cmd_verify` (confirmed→0, missing/contradiction→69, прочее→75).
   Выбор транспорта явный (allurectl launch-get + REST probe),
   upload остаётся на `AllurectlTransport`.
2. `ALLURE_TOKEN` — только env, как сейчас (`_token()`); probe читает
   его из аргумента конструктора и нигде не сохраняет.
3. Сохранение снимка как evidence — ответственность вызывающего
   (probe ничего не пишет); в state — только дистиллят через
   `state_mod.record_confirmation`, как делает 15B.
4. Каталог компонентов (вне области записи 15A, предлагается к
   интеграции): `knowledge/components/infrastructure.md` — запись
   `infrastructure.reporting.testops.rest.RestProbe` (read-only
   snapshot launch: token-exchange, launch/progress/statistic,
   строгий обход testresult); `knowledge/components/consts.md` —
   `test_data.consts.testops_rest` (фиктивные fixtures OpenAPI
   527u01 для offline-тестов probe).
5. Полный `unit`/`compile` после объединения — по регламенту wave.
