# 22AR handoff — полнота и согласованность GitHub PR snapshot

Дата: 2026-11-16. Статус: **ready** — два findings из
[wave 29](coordination-wave-29.md) исправлены с отдельными
регрессиями и повтором координаторских probes из копий; это не приёмка
22A/22B целиком и не разрешение live-публикации. Live GitHub
repository/API вызовы, реальные credentials, Git writes **не
выполнялись** — все проверки offline. Принятая реализация 22B не
изменялась.

## Root cause и исправление

- **F-22A-1:** `get` не сверял состав `.../files` с `changed_files`
  из PR detail — усечённый ответ (1 файл при count=2 без `Link`)
  принимался как полный и доходил до `verified`. Теперь `get`
  требует `changed_files` (int ≥ 0, без bool) в detail-схеме,
  отвергает count > 3000 (документированный серверный лимит
  выдачи, docs.github.com 2026-11-16) до files-запроса и требует
  `len(unique files) == changed_files`.
- **F-22A-2:** `get` читал detail один раз и возвращал смешанный
  снимок при гонке. Теперь последовательность detail → files →
  detail: второй ответ нормализуется и сравнивается по всем
  используемым полям (`SNAPSHOT_FIELDS`, включая head/base SHA,
  branches, title, body digest, draft, state, merged, count,
  head/base repo). Drift, 404 или ошибочное второе чтение —
  controlled failure, без ложного verified. Граница: согласованный
  наблюдаемый снимок, не атомарность.
- **Сохранено:** `create` — ровно 1 POST и 0 verification GET;
  новые reads только в `get`; 404 первого чтения — единственный
  источник `None`; `search` не прячет конфликты; сигнатуры API и
  состав исключений неизменны.

## Файлы и SHA-256

| Файл | SHA-256 |
| --- | --- |
| `infrastructure/workflow/github.py` | `2d27e9978e5db215b780ad084271d0038b545e66b30b4cb1f867f5f759554019` |
| `tests/unit/test_workflow_github.py` | `79bdbf9651c70255ed3c19c796368cd40c84f101207007f67a71ba75efd63d1f` |
| `test_data/consts/workflow_github.py` | `588df128fe8196375de62dfda47c4b7f74e3147a056b2c5a7f52ec74a55e663d` |
| `tests/unit/test_workflow_github_snapshot.py` (new) | `8dbd4ca3af7e1f832e92ef12f563c2083c6d8d345eb9e6bf76bcaa7b5aafcc03` |
| `test_data/consts/workflow_github_snapshot.py` (new) | `066e19b8ef8c02ae56f7e4c227e1cca401ded8aea3966af167af9ddfb8ab2dd7` |
| `docs/qa-workflow/design/22ar-github-snapshot-corrections.md` (new) | `e04067437b059bf524fd47e5be1edb57f4fb90aed7c6d52815c729383b7b31ef` |

Изменённые fixtures: `pr_payload` получил `base_sha` и обязательный
`changed_files` (default `len(FILES)`); `test_full_get` ожидает
повторный detail GET; `test_fixed_endpoint` использует
`changed_files=0` для пустого PR. Старые негативные сценарии
сохранены.

## Команды и результаты

- Python 3.13.15, pytest 9.1.1, `.venv` проекта; `sh tools/versions.sh` — exit 0.
- A HTTP tests + новые snapshot regressions:
  `pytest tests/unit/test_workflow_github.py tests/unit/test_workflow_github_snapshot.py -q`
  → **exit 0, 125 passed** (86 + 39), JUnit `unit-snapshot.xml` в evidence.
- B payload tests (без изменений):
  `pytest tests/unit/test_workflow_pr_payload.py -q`
  → **exit 0, 36 passed**, JUnit `unit-pr-payload.xml`.
- `sh tools/git.sh check` — exit 0. Общий unit/collection и прежние
  96 regressions не повторялись (сужение scope по заданию; потребители
  `github.py`/`workflow_github` consts — только эти файлы и probes).

## Координаторские probes (свежие копии в evidence)

`github-probes.py` (transport): control → returned/exact,
calls `[GET pr, GET files, GET pr]`; **incomplete-files →
`GitHubResponseError`** после files-страницы; **head-race →
`GitHubResponseError`** после второго detail. Результаты:
`*.before.json` (дефект) / `*.after.json` (исправлено).

`github-integration-probes-v2.py` (transport A + orchestrator B,
роль app): control → `verified`, POST=1; **incomplete-files →
`created`** (не verified), POST=1; **head-race → `created`**,
POST=1. Номер 137 записан до verification во всех цепочках.

Регрессия `TestOrchestratorSnapshot` дополнительно гоняет те же три
режима через `pr_create` для ролей **app и tests** (tests — через
canonical repo key `github.com/Unit-Tests-Org/Unit-Tests-Repo`
в `tests_repo_path`): inconsistent snapshot никогда не даёт verified;
повторный `pr_create` после `created` — **0 новых POST**, номер
остаётся записанным. HTTP-счётчики проверяются по списку вызовов,
не только по outcomes.

## Baseline-integrity (after-check, `after-sha.json`)

- Reviewed inputs (manifest `coordinator-22ab-review-20261116`):
  **24/27** совпадают; 3 расхождения — ровно файлы write-scope
  22AR (github.py, test_workflow_github.py, workflow_github consts).
- Protected evidence: **19/19** совпадают.
- API sources `run-ni_5bvnc`: **15/15** совпадают.
- Adapters/orchestrator/CLI/state/contracts, B tests/consts, общий
  интерфейс, старые handoffs/design/evidence, пакеты 19A2 и каталоги
  не изменялись; чужие изменения сохранены.

## Evidence

`artifacts/workflow-github/22ar-20261115T223255Z/`:
`sha_check.py`, `before-sha.json`, `after-sha.json`,
`new-files-sha.txt`, копии probes + `*.before.json`/`*.after.json`,
`integration-v2-*` stores, `unit-snapshot.xml`, `unit-pr-payload.xml`,
`pytest-temp*/`, `pytest-cache*/`.

## Для 22C (новые snapshot semantics)

- `get(repo, number)` теперь делает 2 GET detail + files-страницы —
  это ожидаемые HTTP-счётчики, не аномалия. `GitHubResponseError`/
  `GitHubHttpError`/`GitHubPrStateError` на `get` означают
  недоказанный/несогласованный snapshot; orchestrator отображает их в
  `created`/`blocked`/`unknown`, не в `verified`.
- `MAX_LISTED_FILES = 3000` — documented cap; PR с `changed_files`
  выше лимита не поддаётся verification через этот endpoint.
- CLI wiring `--pr-transport`, общий каталог и итоговая сводка 22 —
  область 22C/координатора.

## Ограничения

- Live GitHub API не вызывался; поля/лимит — по docs.github.com
  2026-11-16; реальное поведение (rate limits, `Link` на границе,
  лимитированная выдача) не верифицировано.
- Снимок согласован по двум чтениям; скрытая гонка между файлами и
  вторым detail вне заявленной границы.

После отчёта 22AR останавливается: координатор принимает исправленную
A + совместимость с принятой B до запуска 22C; всё 22/MVP не принимать.
