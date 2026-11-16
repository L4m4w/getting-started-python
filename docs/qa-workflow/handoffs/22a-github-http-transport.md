# 22A handoff — GitHub HTTP transport

Дата: 2026-11-16. Статус: **ready** — реализация, регрессии и design
готовы к приёмке координатором параллельно с 22B; это не приёмка
всего 22 и не разрешение live-публикации. Live GitHub repository/API
вызовы, live PR creation и реальные credentials **не выполнялись** —
все проверки offline через injectable fake-HTTP; синтетические
ответы не выдавались за live fixtures.

## Результат

`infrastructure/workflow/github.py` — stdlib `GitHubPrTransport`
по закреплённому интерфейсу
`docs/qa-workflow/design/22-pr-transport-interface.md`:

```python
from infrastructure.workflow.github import GitHubPrTransport

transport = GitHubPrTransport(token_provider=None, http=None)
transport.search(key)        # list[PrRef] или controlled error
transport.create(spec)       # PrRef с читаемым number сразу после 1 POST
transport.get(repo, number)  # полный PrRef; None только на 404
```

Конструктор pure/lazy: zero HTTP, zero provider-вызовов, zero env/file.
Детали контракта, endpoints, используемые поля и границы —
`docs/qa-workflow/design/22a-github-http-transport.md` (URL/date
официальной docs.github.com документации 2026-11-16 зафиксированы там).

## API/exception contract для 22B/22C и каталогов (пишет 22C)

- HTTP-слой: `request(endpoint, method, path, *, headers=None,
  payload=None)` → объект с int `status`, `body` (bytes|str),
  `headers` (case-insensitive). Default `UrllibHttp` поверх
  `infrastructure.http.client.HttpClient` (no-redirect, timeout 30 s).
- Token provider: zero-arg callable → str; вызывается только при
  разрешённом HTTP-вызове; default `EnvGitHubToken()` → `GITHUB_TOKEN`
  в момент вызова.
- Исключения (наследуют `WorkflowError`, сообщения без токенов/сырых
  тел): `GitHubTransportError` база; `GitHubSpecError` (key/spec до
  HTTP), `GitHubAuthError` (нет токена, до HTTP), `GitHubHttpError`
  (transport/status; POST-failure = unknown outcome без retry),
  `GitHubResponseError` (malformed/foreign/incomplete),
  `GitHubPrStateError` (PR не open unmerged same-repo draft).

## HTTP counters / границы (assert'ятся регрессиями)

- constructor: 0 HTTP, 0 provider.
- search: по одному GET на страницу; обрыв/неполнота — error, не `[]`;
  max_pages bound; title_key не отправляется.
- create: ровно 1 POST, 0 GET (verification GET внутри create нет);
  retries нет ни на статус, ни на transport raise.
- get: 1 GET PR + paginated GET files; 404 → None за один GET;
  state/merged/draft/head отказы до чтения files.
- Все запросы только `api.github.com`; Authorization только Bearer
  header; 3xx не dereference'ится; `Link` URL не dereference'ится
  (foreign-host rel="next" доказанно не уводит запрос); repo-формы
  вне canonical `github.com/owner/repo` отклонены до HTTP; пустой
  токен → `GitHubAuthError` до HTTP.

## Файлы и SHA-256

| Файл | SHA-256 |
| --- | --- |
| `infrastructure/workflow/github.py` | `96f1c3f85761c05abcdb139ab1a1ea3cf72856cd7ec2f87acbb385ba76aabffd` |
| `tests/unit/test_workflow_github.py` | `2d3c0e265bf6adbd83249fcff8a75237d7a415703e26d7718bf35b33df09463a` |
| `test_data/consts/workflow_github.py` | `3e61c135d8c5ccdbf963c120728448ea8f4101e77642c13fddd9d0cd51127a5e` |
| `docs/qa-workflow/design/22a-github-http-transport.md` | см. `new-files-sha.txt` в evidence |

## Команды и результаты

- Python `3.13.15`, pytest `9.1.1`, venv проекта.
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest
  tests/unit/test_workflow_github.py -q
  --basetemp=artifacts/workflow-github/22a-20261115T221334Z/pytest-temp
  -o cache_dir=artifacts/workflow-github/22a-20261115T221334Z/pytest-cache
  --junitxml=artifacts/workflow-github/22a-20261115T221334Z/unit-github.xml`
  → **exit 0, 86 passed / 0 failed / 0 errors / 0 skipped**.
- Собственные basetemp/cache/JUnit только в 22A evidence; чужие
  stores/тесты не запускались (сужение scope по заданию).

## Baseline-integrity после работы (after-check)

`after-sha.json` в evidence: accepted-inputs **20/22** совпадают с
baseline wave 26 — оба расхождения ожидаемые peer-22B правки:

- `infrastructure/workflow/adapters.py` — peer spec (`body_text`
  и пр.), actual `10ac33420b94b39e9f98d7981e03c8fbfd82a52f47d945adefa9f864c815f35c`,
  без изменений за время 22A;
- `infrastructure/workflow/orchestrator.py` — peer checkpoints,
  actual изменён в ходе работы `f9e9d312…` → `bdd8196589b2aaafbb3410d24f387ebcf284304847a379dd0680a67652feb993`;
- `tools/workflow.py` без изменений (`489bf41a…`).

Protected evidence **19/19** совпадают; API source manifest
`run-ni_5bvnc` **15/15** совпадают. Защищённые и чужие файлы 22A
не изменял; новые файлы — только явный write scope (6 путей).

## Evidence

`artifacts/workflow-github/22a-20261115T221334Z/`:
`before-sha.json`, `after-sha.json`, `new-files-sha.txt`,
`unit-github.xml`, `pytest-temp/`, `pytest-cache/`.

## Ограничения для координатора/22C

- Live-поведение GitHub API не верифицировано: endpoints/схемы —
  по docs.github.com 2026-11-16; реальные статусы, rate limits и
  draft-flag в list-ответе могут отличаться — потребуется отдельное
  разрешение на live проверку перед боевым wiring.
- `search` не фильтрует closed/merged/non-draft/fork-head — кандидаты
  возвращаются; конфликт решает orchestrator.
- `files` в list-схеме отсутствует: search-refs несут `files=[]`,
  полный состав — только через `get`.
- Реальные credentials/env secrets не читались; default provider
  (`GITHUB_TOKEN`) покрыт только fake-env регрессией под вымышленной
  переменной.

После этого отчёта 22A останавливается: 22C не начинать до
координаторской приёмки A/B; всё 22/MVP не принимать.
