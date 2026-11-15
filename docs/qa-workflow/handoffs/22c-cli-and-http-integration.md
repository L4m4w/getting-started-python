# 22C handoff — CLI wiring `--pr-transport {none,github}` и offline-интеграция

Дата: 2026-11-16. Статус: **ready** — production CLI подключён к
принятым 22A/22AR (`GitHubPrTransport`) и 22B (durable body/checkpoint
orchestration) через глобальный `--pr-transport {none,github}`
(default `none`); offline-интеграционные проверки выполнены на
настоящем `tools/workflow.py` в subprocess с fake HTTP/git bootstrap и
программно. Live GitHub repository/API вызовы, реальные credentials,
публикация и Git writes **не выполнялись** — все проверки offline.
Это не приёмка 22A/22B целиком и не разрешение live-публикации;
принятые A/B исходники не изменялись.

## Изменение (единственный production-файл — `tools/workflow.py`)

- Глобальный `--pr-transport {none,github}` на top-level parser до
  subcommand, default `none`.
- `_needs_pr_transport` ограничивает wiring dispatch-командами
  (`pr create`, `pr search`, `reconcile`, `resume`); на
  `status`/`init`/`doctor`/`accept`/`check`/executions/TestOps/
  `pr prepare` модуль не импортируется и транспорт не строится.
- `github`: lazy `from infrastructure.workflow.github import
  GitHubPrTransport` + чистый конструктор без I/O; один объект в
  `pr_transports={"app": t, "tests": t}`.
- `--body` остаётся публичным флагом → `body_path` (механика 22B не
  тронута); сеть только `--online`, POST только `--execute`+`--online`
  + действующие guards; выбранный транспорт не делает healthcheck.

## Файлы и SHA-256

| Файл | SHA-256 |
| --- | --- |
| `tools/workflow.py` (изменён) | `f9ed251bba6ea5ba428ad17027be2abe94f366455c978a9bbbbf06cf33039e88` |
| `tests/unit/test_workflow_github_cli.py` (new) | `8534b275dd93cd964a745a432c1c5699d5cb52e598b584ffe6228804da0877bb` |
| `test_data/consts/workflow_github_cli.py` (new) | `5395969efa7059545ea7386fdc9bcc833bda1dad0a7fed3a6232a5e64b63146e` |
| `knowledge/components/workflow.md` (изменён) | `2b15fe35ecd002312bb9c7cabd83d8842c44a468a9ccca2e679c8f26edd4620b` |
| `knowledge/components/consts.md` (изменён) | `e0166aff2f126c6bab1768b833ae8fe601edb241b237f279acd567cc02163613` |
| `knowledge/integrations/qa-workflow.md` (изменён) | `94fe1311873900015156a209e3f41035d9b51553cc40abcd3ee9a84a881e3048` |
| `docs/qa-workflow/design/22c-cli-and-http-integration.md` (new) | `461bba5f968e95016728facd017390dadae03bddbebce2c3ba9486f8b63f7139` |

## Команды и результаты

- Python 3.13.15 (`.venv`), pytest 9.1.1; `sh tools/versions.sh` — exit 0;
  `sh tools/compile-tests.sh` — exit 0 (726 collected, collection only).
- Новый CLI regression-файл (subprocess + программный):
  `pytest tests/unit/test_workflow_github_cli.py` → **exit 0,
  15 passed**, JUnit `unit-github-cli.xml`.
- A HTTP tests (принятые, без изменений):
  `pytest tests/unit/test_workflow_github.py` → **exit 0, 86 passed**,
  `unit-github-http.xml`; 22AR snapshot:
  `pytest tests/unit/test_workflow_github_snapshot.py` → **exit 0,
  39 passed**, `unit-github-snapshot.xml`.
- B payload tests (без изменений):
  `pytest tests/unit/test_workflow_pr_payload.py` → **exit 0,
  36 passed**, `unit-pr-payload.xml`.
- Смежный CLI-subprocess regression:
  `pytest tests/unit/test_workflow_21r_a.py -q` → **exit 0, 74 passed**.
- `git diff --check` — exit 0. Общие unit-прогоны и остальные workflow
  regressions не повторялись: потребителей изменённого CLI-кода кроме
  нового файла нет; A/B regressions уже выполнены волной 30.

Изолированные `--basetemp`/`-o cache_dir`/`--junitxml` под evidence dir.

## Offline-интеграция: subprocess (настоящий `tools/workflow.py`)

Bootstrap: `sitecustomize.py` из
`test_data/consts/workflow_github_cli.SITECUSTOMIZE` через `PYTHONPATH`;
JSON-сценарий `WF_GH_FAKE_SCENARIO` (git-деревья commit'ов + regex
HTTP-правила) и лог `WF_GH_FAKE_LOG`. Подменяются только `UrllibHttp`
(счётчик request'ов) и `GitReadAdapter` по зарегистрированным repo_path;
endpoint остаётся `https://api.github.com`, новых endpoint/флагов
отключения guards в production нет. `EnvGitHubToken` обёрнут счётчиком
credential-чтений. Fixture: `Project.drive_commit_to_executed()`
(commit head + clean tests) с canonical `github.com/Unit-*` repo keys;
записанные repo-relative пути переведены в абсолютные tmp-пути с
перепривязкой `bound_input_digests`/`history` digests (входные данные
не изменены).

| Проверка | Результат | HTTP | Credentials |
| --- | --- | --- | --- |
| `--pr-transport` до action / после action / `bogus` | parse / exit 2 / exit 2 | 0 | 0 |
| `status`, `doctor`, `pr prepare`, `reconcile`, `resume` (без `--online`) с `github` | exit 0; prepare → `prepared` | 0 | 0 |
| `pr create` без флагов / `--online` / `--execute`; `pr search` без `--online` | exit 77 | 0 | 0 |
| `pr create --online --execute` без `--pr-transport` (default none) | exit 77 «no PR transport» | 0 | 0 |
| `pr create --online --execute` без `GITHUB_TOKEN` | exit 69 controlled (`GitHubAuthError` до первого запроса) | 0 | 1 |
| app: `pr prepare --body` → `pr create --online --execute` | `verified`, exit 0; повтор — `no-op` | 4 GET (list+files+2×detail), 1 POST | 3 |
| tests: `pr prepare` → `pr create --online --execute` | `verified`, exit 0 | 4 GET, 1 POST | ≥1 |
| POST transport error → `unknown` (75); `reconcile --online` + `[]` | `blocked`, intent unresolved | +1 GET | — |
| повторный `pr create` после unknown | 69 | POST остаётся 1 | — |
| `get` 404 по созданному номеру → `created`; повтор `create` | `created` exit 0 → 69 blocked | POST=1, GET=3 | — |
| minimal ref (только number/url) → `created`; `get` ошибка при повторе | `created` → 75 `unknown` | POST=1, ноль новых POST | — |

Durable-поведение 22B подтверждено через CLI: номер записан в
`state.json` до verification GET во всех цепочках; второй POST ни в
одной ветке не диспатчится.

## Программный уровень (внутри pytest, без subprocess)

- `_orchestrator`: `github` на dispatch-командах →
  `GitHubPrTransport` в ролях `app` и `tests` (один объект); на
  `status`/`doctor`/`init`/`pr prepare` и при `none` —
  `pr_transports == {}`; provider/HTTP-счётчики конструктора — 0.
- Полная цепочка `Orchestrator` (настоящий, B) + `GitHubPrTransport`
  (настоящий, A/22AR) + `FakeHttp`: `verified` одним POST; порядок
  GET — list → detail → files → detail; token provider вызван 3 раза
  (search, create, get) — только внутри authorized запросов.

## API-каталог подключённой поверхности

`GitHubPrTransport(token_provider=None, http=None)` → `search(key)` —
свежий list `GET /repos/{owner}/{name}/pulls?...`; `create(spec)` —
ровно один `POST /repos/{o}/{n}/pulls` (минимальный readable ref при
частично читаемом ответе); `get(repo, number)` — `GET .../pulls/{n}` →
`GET .../pulls/{n}/files?...` (все страницы) → повторный `GET
.../pulls/{n}` со сверкой `SNAPSHOT_FIELDS` и `changed_files`.
CLI отображает `WorkflowError`-наследников (`GitHub*Error`) в exit 69,
`WorkflowPermissionError` — в 77.

## Baseline-integrity

- Before (`before-sha.json`): accepted inputs **35/35**, protected
  **19/19**, API sources `run-ni_5bvnc` **15/15**.
- After (`after-sha.json`): accepted inputs **31/35** — 4 расхождения
  ровно по файлам write-scope 22C (`tools/workflow.py` + 3 knowledge
  docs); `github.py` `2d27e997…`, `adapters.py` `10ac3342…`,
  `orchestrator.py` `bdd81965…` и прочие принятые входы неизменны.
  Protected **19/19**, API sources **15/15**.
- Новые файлы и их SHA: `new-files-sha.txt`.

## Evidence

`artifacts/workflow-github/22c-20261115T224726Z/`:
`before-sha.json`, `after-sha.json`, `new-files-sha.txt`,
`unit-github-cli.xml`, `unit-github-http.xml`,
`unit-github-snapshot.xml`, `unit-pr-payload.xml`,
`pytest-cache-*`, `pytest-temp-*`.

## Ограничения

- Live GitHub API не вызывался: поведение реального сервера
  (пагинация на границе, rate limits, реальные PR) не верифицировано —
  offline-ready ≠ live-verified и не завершение MVP.
- `get`-семантика счётчиков учитывает принятый 22AR порядок
  detail → files → detail (2 detail GET на один `get`).
- Fake git подменяет read-only identity по зарегистрированным
  checkout'ам; незарегистрированные repo получают реальный
  `GitReadAdapter` с записью события — в прогонах fallback не
  использовался.
- Исторические evidence, index/state файлов репозитория и чужие
  незакоммиченные изменения не затрагивались; коммитов/пушей нет.

После отчёта 22C останавливается: координатор принимает CLI wiring и
offline-интеграцию до любого разрешения live-публикации.
