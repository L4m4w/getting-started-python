# Передача результата: воспроизводимость API evidence

Агент: `09`. Дата: 2026-11-14. Статус: `ready` для интеграции координатором.
Устранены ограничения F-1/F-2 ревью 08 **для следующих прогонов**: harness
теперь сохраняет идентичность исходников API-контракта и проверяемую привязку
окружения. Исторические результаты 05/07 не переобозначались и не дополнялись;
новое сохранение provenance **не доказывает** идентичность прошлых прогонов.
Стенд, Docker/HTTP/SQL и TestOps/PR в этой задаче не выполнялись — подготовка
нового baseline/fix остаётся отдельным поручением.

## Изменённые файлы

- `tools/harness.py` — source identity API-контракта, метаданные окружения,
  новые флаги `run`, `schema_version` 2.
- `test_data/consts/harness.py` — фиксированные входы/ожидания новых проверок.
- `tests/unit/test_harness.py` — 21 новый offline-кейс.
- `docs/qa-workflow/agent-tasks/07-integration.md` — привязка контейнера
  к image ID перед каждым запуском и отдельный post-down evidence.
- `knowledge/testing/run-tests.md` — контракт новых полей manifest и флагов.
- `knowledge/components/infrastructure.md`, `knowledge/components/consts.md` —
  записи каталога.

## Новые metadata в manifest прогона

`schema_version` поднят до 2; старые поля неизменны.

`source_identity` — заполняется до старта pytest, когда выбор затрагивает
`tests/api` (группа `api`, node ID `tests/api/...` или `all`), иначе `null`:

- `contract_version`: `api-contract-v1` (`API_CONTRACT_VERSION` в
  `tools/harness.py`; набор — `API_SOURCE_FILES`, 15 файлов: тесты, fixtures,
  транспорт, OAuth, константы, helpers тестовых данных, requirements).
- `captured_at`, `files[]` (`path`, `sha256`, `git_blob`, `tracked`),
  `copies` (физические копии — `sources/` прогона), `missing`.
- `changed_during_run` и `rechecked_at` — после завершения: файлы, изменённые
  или появившиеся/исчезнувшие за время прогона; `null` — проверка не завершена.
- `.env` и имена из `NEVER_EVIDENCE_NAMES` не fingerprint'ятся и не копируются.

`environment` — при переданных флагах `--app-base-sha`, `--app-patch-sha256`,
`--gateway-image-id`, `--gateway-container`, иначе `null`:

- `declared` — декларация оператора: четыре значения, `source: "operator"`,
  `captured_at`.
- `container_check` — фактический `docker container inspect` до старта pytest:
  `performed`, `reason`, `checked_at`, `container_id`, `container_name`,
  `container_running`, `image_id`, `image_tag`, `matches_declared_image`
  (короткий ID сверяется по префиксу). Недоступный docker/отсутствующий
  контейнер/нечитаемый вывод → `performed=false` с явной причиной.
  Полный inspect, env контейнера и credentials не сохраняются.
- Невалидные значения флагов отклоняет argparse (exit 2) до создания evidence.

Пример блока без секретов (unit-прогон `run-sim8n07v`, образ сокращён):

```json
"environment": {
  "declared": {
    "app_base_sha": "aaaa…aaaa",
    "app_patch_sha256": null,
    "gateway_image_id": null,
    "gateway_container": null,
    "source": "operator",
    "captured_at": "2026-11-13T23:17:51.456360+00:00"
  },
  "container_check": {"performed": false,
                      "reason": "container not declared", "checked_at": null}
}
```

## Обновление runbook 07

`agent-tasks/07-integration.md`: перед каждым запуском base/fix исполнитель
передаёт harness `--app-base-sha`, `--app-patch-sha256`, `--gateway-image-id`,
`--gateway-container`; manifest пишет декларацию и результат проверки до
старта pytest. Добавлен отдельный post-down evidence: команда, exit code,
UTC-время и проверки `docker ps -a` / `docker network ls` только с фильтром
`label=com.docker.compose.project=catupdval`; снимок до down её не заменяет.

## Проверки и evidence

- `sh tools/compile-tests.sh`: exit 0, 94 collected (collection, не прогон).
- `sh tools/run-tests.sh group unit`: exit 0, **79 passed**, 0 failed/errors/
  skipped; evidence `artifacts/harness/run-j0qh47l0/`. Из них 21 новый кейс
  `tests/unit/test_harness.py`: идентичность контракта, копии, missing,
  изменение во время прогона, защита `.env`, декларация окружения, все исходы
  проверки контейнера, валидаторы метаданных.
- `sh tools/run-tests.sh group unit --app-base-sha <40 hex>`: exit 0,
  `environment.declared` записан: `artifacts/harness/run-sim8n07v/`.
- Невалидные `--app-base-sha`/`--gateway-image-id`: exit 2 до evidence.
- Офлайн-проверка идентичности на реальном дереве: 15 файлов контракта
  fingerprint'нуты, untracked-файлы пилота помечены `tracked=false`;
  `changed_during_run` пуст.
- `sh tools/git.sh check`: exit 0.
- Без флагов окружения и вне `tests/api`: `source_identity`/`environment` —
  `null` (`run-9qu1q5nc`, `run-j0qh47l0`).

## Незавершённые проверки

- Реальный API-прогон base/fix с новыми флагами и живым
  `docker container inspect` не выполнялся (запрещено поручением): поведение
  проверки подтверждено только подменами, не живым docker.
- `group api`/`all`/`one tests/api/...` с реальным стендом не запускались;
  ветка `_is_api_scope` проверена офлайн.
- Живой post-down evidence по обновлённому runbook 07 не существует — это
  требование для следующего исполнителя, не результат.
- UI-прогоны и Java harness не затрагивались; контракт `java_evidence`
  не изменялся и не перепроверялся в этой задаче.
- Публикация TestOps/PR по-прежнему вне scope.
