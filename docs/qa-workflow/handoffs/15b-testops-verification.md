# Передача результата: сверка REST-снимка launch с ожидаемым execution

Агент: `15B`. Дата: 2026-11-14. Статус: `ready` — оценка снимка и
переходы состояния реализованы и проверены offline; подключение probe
15A и интеграцию в `tools/testops.py` выполняет координатор.

Область записи соблюдена: новые `infrastructure/reporting/testops/
verification.py`, `tests/unit/test_testops_verification.py`,
`test_data/consts/testops_verification.py`, этот handoff. Существующие
`lifecycle.py`/`state.py`/`client.py`, CLI, модули и тесты агента 15A
не менялись. Живых запросов, чтения токена/.env, upload, Docker/Gradle,
commit/push не было; probe — только инъецируемый fake по контракту.

## Публичные интерфейсы

- `verification.evaluate_snapshot(snapshot, expected, *, launch_id,
  project_id) -> Assessment` — чистая оценка одного dict по контракту
  `read_snapshot` против `state_mod.expected_scenarios(state)`.
  Контракт перепроверяется до сравнения: malformed snapshot всегда даёт
  `inconclusive`, исключений по форме не бросает.
- `verification.perform_snapshot_verify(state_dir, probe, *,
  launch_id=None, persist=None, lock=None) -> lifecycle.VerifyRun` —
  оркестрация для CLI: `load -> probe -> verdict -> persist` целиком
  под ExecutionLock. `probe` — любой объект с `read_snapshot(endpoint,
  launch_id)`; `lock` — любой context manager. Уже захваченный
  `ExecutionLock` (`_held`) используется без повторного захвата и без
  release — владение остаётся у вызвавшего; `contextlib.nullcontext()`
  (текущий паттерн `cmd_verify` под `_guard`) работает.
- `Assessment(verdict, confirmed, checks, detail)` — `checks`
  дистиллированы (booleans/verdicts/counts/ID списки, строки ≤200,
  списки ≤20) и сохраняются в `upload.confirmation` как есть: без
  raw HTTP, имён результатов, attachments и credentials.
- Вердикты — те же семь из `state.CONFIRMATION_VERDICTS`; outcome
  `missing`/`unreachable`/`inconclusive` probe передаётся честно.
  `METHOD="rest-snapshot"` в `confirmation.method`.

## Модель проверок и вердиктов

При `outcome="complete"` сверяются все слои одновременно:

| Слой | Проверка | При нарушении |
| --- | --- | --- |
| contract | обязательные поля и типы snapshot | `inconclusive` (malformed) |
| expected set | непустой набор сценариев в state | `inconclusive` |
| launch | `id` == записанному, `project_id` == state | `contradiction` |
| launch | `closed=true`, `ready=true` | `inconclusive` (неполнота) |
| pagination | `complete=true`, `total_elements` == числу строк | `inconclusive` |
| rows | `launch_id`/`project_id` каждой строки | `contradiction` |
| rows | точное имя `SID:`/`SID` (0010 ≠ 001) — иначе foreign | `contradiction` |
| rows | ровно одна строка на сценарий; дубли result ID | аномалия → `inconclusive` |
| rows | `hidden`/`retried_by_id` — «последний» не выбирается | аномалия → `inconclusive` |
| status | точное совпадение; `in_progress`/`unknown` — обработка | `contradiction` / `inconclusive` |
| stats | == expected (нулевые ключи ≡ отсутствующие) и == rows | overdelivered/inconsistency → `contradiction`, недобор → `partial`, нули+нет строк → `empty`, `stats=None` → `inconclusive` |
| bindings | bind: `test_case_id` == `testops_id`; isolate: найденные ID → `checks["candidates"]`, автоматический `uploaded` не объявляется | `contradiction` / `inconclusive` |

Приоритет вердиктов: `contradiction` > `inconclusive` (контракт,
неполнота, аномалии, нечитаемая статистика, bindings не согласованы) >
`empty` > `partial` > `confirmed`. Несовпадение stats↔rows считается
противоречием только без аномалий/незавершённой обработки — иначе оно
объяснимо и остаётся `inconclusive`.

## Переходы состояния (не-terminal статусы sent/unknown/failed)

| Вердикт | upload.status | Допуск повтора |
| --- | --- | --- |
| `confirmed` | → `uploaded` (через `mark_upload_confirmed`, method=`rest-snapshot`) | никогда |
| `empty` | → `failed`: launch доказанно закрыт, готов и пуст — guarded retry в **тот же** launch | только явный `--retry` |
| `partial`, `missing`, `contradiction` | → `unknown` + detail | заблокирован даже с `--retry` |
| `inconclusive`, `unreachable` | без изменений + `confirmation` записан | без изменений |

Особые входы оркестрации: `uploaded` — терминал, probe не вызывается,
state не меняется; `in_progress` — inconclusive без probe и без записи
(требуется отдельное `resolve_in_progress`); `--launch-id` ≠ записанному —
`contradiction` без probe; повреждённый state — `StateCorruptError`,
файл не перезаписывается.

**Отличия от `lifecycle.perform_verify` (allurectl-путь), осознанные:**
`empty` здесь уже переводит в `failed` (модель handoff 13; требует
`closed+ready`, поэтому безопаснее, чем «sent навсегда»), а `partial`
понижает до `unknown` (частичная серверная запись доказана — слепой
retry опасен). Решить, унифицировать ли старый verify с этими
правилами, — координатору.

## Проверки и evidence

| Команда | Exit | Итог |
| --- | --- | --- |
| `pytest tests/unit/test_testops_verification.py -q` | 0 | **30 passed** |
| `sh tools/run-tests.sh one 'tests/unit/test_testops_verification.py::TestSnapshotContract'` | 0 | 2 passed, `artifacts/harness/run-8udmfmq6/` |
| `…::TestConfirmedAndContradictions` | 0 | 8 passed, `run-vwci5yk0` |
| `…::TestIncompleteAndAnomalies` | 0 | 8 passed, `run-ozivtjwr` |
| `…::TestBindingModes` | 0 | 3 passed, `run-27bqhyg3` |
| `…::TestVerifyOrchestration` | 0 | 9 passed, `run-hxz0ig3s` |
| `sh tools/compile-tests.sh` | 0 | 237 collected (включая файлы 15A) |
| `git diff --check` + trailing-whitespace scan новых файлов | 0 | чисто |

`sh tools/run-tests.sh group unit` в этой сессии: **192 passed, 30
failed — все падения в `tests/unit/test_testops_rest.py` агента 15A**
(`TypeError: keywords must be strings`, строки 126–220 их файла) —
их рабочий процесс, файлы не трогал; новый файл 15B полностью зелёный.

Покрытие порученных сценариев: полный bind → uploaded; неверный
launch/project/case/status; отсутствующий сценарий → partial;
лишний результат и `CAT-UPD-VAL-0010` → foreign/contradiction; дубли
result ID и строк сценария → аномалии; неполная/несогласованная
пагинация и malformed snapshot → inconclusive; closed/ready false;
нулевая статистика → empty→failed; in_progress/unknown статусы;
hidden/retry; isolate-кандидаты без автоподтверждения; lock вокруг
probe+persist (включая внешний захваченный ExecutionLock);
повреждённый state; терминальный uploaded и блок повторной отправки;
проверка дистиллированного evidence.

## Подключение для координатора (точный пример)

```python
# tools/testops.py, cmd_verify — внутри _guard (ExecutionLock уже держится)
from infrastructure.reporting.testops import rest, verification  # rest — файл 15A

probe = rest.RestProbe(endpoint=..., token=_token(), ...)  # конструктор 15A
run = verification.perform_snapshot_verify(
    state_dir, probe, launch_id=options.launch_id,
    lock=nullcontext())
_write_calls(state_dir, run.calls)   # calls хранит только outcome, без снимка
print(f"Verify verdict={run.verdict} launch={run.launch_id}: {run.message}")
if run.confirmed:
    return 0
if run.verdict in (verification.VERDICT_MISSING,
                   verification.VERDICT_CONTRADICTION):
    return EXIT_BLOCKED        # 69 — ручное разрешение
if run.verdict == verification.VERDICT_EMPTY:
    return 0                   # решено к retry (--retry в тот же launch)
return EXIT_UNKNOWN            # 75 — inconclusive/partial/unreachable
```

1. Перед verify повторно сверить пакет и источник как в `cmd_upload`:
   `results.verify_package(state["package"]["dir"],
   state["package"]["sha256"])` и `results.verify_source_digest`
   для `state["results"]["path"/"sha256"]` — подтверждение должно
   относиться к тому пакету, который реально ушёл; расхождение → 69
   до вызова probe.
2. Lock: `perform_snapshot_verify` сам держит ExecutionLock; при вызове
   из-под `_guard` передавать `lock=nullcontext()` (как сейчас) либо
   уже захваченный `ExecutionLock` — повторного захвата/release не будет.
3. Ошибки state: `StateCorruptError`/`StateSchemaError` — печать и 69,
   никогда не `new_state` поверх (как в интеграции handoff 13).
4. Выбор транспорта: `verify --online` → REST-probe 15A; без probe
   (`allurectl` без per-result чтения) модуль честно возвращает
   inconclusive «no read_snapshot path». Старый слабый verify
   (`launch get` + существование) заменить этим вызовом.
5. `record_confirmation` хранит только `checks` выше — raw snapshot
   никуда не пишется; `calls` фиксирует лишь `outcome`.
6. Миграция существующих `artifacts/testops/*/state.json` не нужна:
   schema 2 уже содержит `confirmation`/`history`; новых полей
   модуль не вводит.

## Ограничения

- Проверено только offline с fake probe по контракту волны 15; живой
  `read_snapshot` 15A, реальная форма `TestResultDto` и поведение
  сервера (hidden/retriedBy, семантика `ready`) остаются неподтверждёнными
  до разрешённого live-прогона.
- `empty → failed` и `partial → unknown` — усиление относительно
  `lifecycle._apply_verdict` (там статус сохранялся); координатор решает,
  приводить ли старый путь к этой модели.
- Семантика `hidden` в OpenAPI не описана: строка hidden трактуется как
  аномалия (inconclusive), а не исключается из набора — консервативно.
- Оценка имени — только точный `SID:`/`SID` по state.scenarios; иные
  схемы именования (суффикс `[SID]` в `fullName`) snapshot-уровнем не
  разбираются — это ответственность нормализации probe.
- `tools/testops.py` не изменён и по-прежнему содержит старый verify —
  до интеграции им пользоваться нельзя.
- Изменения state schema не требуются; изменения вне области
  (`testops.py`, унификация старого verify, каталог компонентов)
  предложены координатору, не выполнены.
