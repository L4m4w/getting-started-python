# 22B — durable PR body payload и checkpoint читаемого create number

Дата: 2026-11-16 (UTC). Исполнитель: 22B. **Статус: `ready`** —
назначенная область реализована, все назначенные регрессии и
full-chain fake repeat зелёные, integrity-сверки чистые. Это не приёмка
22 целиком и не разрешение Git/PR-этапа: координатор принимает A/B,
затем назначает 22C. Другие агенты не запускались; все проверки
offline на fake runner / fake PR transport / FakeGit / isolated stores.

## Область и SHA

| Файл | SHA-256 |
| --- | --- |
| `infrastructure/workflow/adapters.py` | `9a9b23a5…` → **`10ac33420b94b39e9f98d7981e03c8fbfd82a52f47d945adefa9f864c815f35c`** |
| `infrastructure/workflow/orchestrator.py` | `f9e9d312…` (21R2 accepted) → **`bdd8196589b2aaafbb3410d24f387ebcf284304847a379dd0680a67652feb993`** |
| `tests/unit/test_workflow_pr_payload.py` (new) | `8a0a1d0a1ccf3526826e0bfa2d3a2b9f84092f1b052c3658f54beddcd79ffac8` |
| `test_data/consts/workflow_pr_payload.py` (new) | `cae77af1c0c581a7d99d85fb5d212c71f1e79f24ab522de8eb9d03b9a31cad4a` |
| `docs/qa-workflow/design/22b-pr-body-and-checkpoints.md` (new) | design |
| `docs/qa-workflow/handoffs/22b-pr-body-and-checkpoints.md` (new) | этот файл |
| `artifacts/workflow-github/22b-20261115T221149Z/` (new) | gitignored evidence |
| `tools/workflow.py` | `489bf41a…810` — **не менялся** (CLI — область 22C) |

**Peer 22A delta:** `infrastructure/workflow/github.py` существует в
worktree как работа 22A, sha256
`d4c06ec49034fc9c2e5b8202202a7229b7221220747e2347888cc0811471d8f1`
(`peer-22a-delta.txt`). Файл не редактировался; `PrSpec`/`PrRef`/
`PrTransport` сигнатуры сохранены — добавлено только поле
`PrSpec.body_text: str = None` (default, обратная совместимость).

State/envelopes/contracts/index/locks/CLI/github.py не трогались.
Старые tests/fixtures/consts не изменялись.

## Реализовано

- `PrSpec.body_text` + spec keys `body_text`/`body_source`/
  `body_snapshot`; канон absent/empty → `None`/`None`; digest —
  SHA-256 точных UTF-8 bytes без trim/CRLF-нормализации.
- Durable snapshot `payloads/pr-<role>-body-<sha16>.txt` внутри
  workflow dir, атомарная идемпотентная запись (`_write_payload`).
- `_body_payload_problems` — pre-POST gate: source/snapshot
  missing/drift, tampered `body_text`, legacy hash без текста →
  `blocked` (69) до любого remote read/POST. Legacy digest=None spec —
  допустимо.
- `_dispatch_pr_create`: читаемый `number`/`url` делается durable до
  verification GET; crash/lost save оставляет `dispatched`/`created`
  блокеры; re-prove — только targeted `get`. Границы и guards 21R2
  сохранены (design: `docs/qa-workflow/design/22b-pr-body-and-checkpoints.md`).

## Проверки

Python 3.13.15, pytest 9.1.1, все команды из корня репозитория,
`EV=artifacts/workflow-github/22b-20261115T221149Z`, JUnit внутри EV.

| Команда | Результат | Exit |
| --- | --- | --- |
| `pytest tests/unit/test_workflow_pr_payload.py --basetemp=$EV/basetemp/pr-payload -o cache_dir=$EV/pytest-cache --junitxml=$EV/unit-pr-payload.xml -q` | 36 passed | 0 |
| `pytest tests/unit/test_workflow_intents.py tests/unit/test_workflow_21r_b.py tests/unit/test_workflow_21r2.py tests/unit/test_workflow_20r2.py::TestR2GitHeadSeparation … --junitxml=$EV/unit-regression.xml -q` | 96 passed | 0 |
| `pytest tests/unit/test_workflow_orchestrator.py::TestEndToEnd --basetemp=$EV/basetemp/full-chain … --junitxml=$EV/unit-full-chain.xml -q` | 4 passed (fresh copy, цепочка до published) | 0 |
| `PYTHONPATH=. .venv/bin/python $EV/dispatch-probe.py` | counters в `dispatch-counters.txt` | 0 |

Покрытие нового файла (36 кейсов): body absent/empty/nonempty/CRLF/
Unicode/invalid-UTF-8/missing-file; snapshot+source missing/drift;
tampered `body_text`; legacy hash-без-текста → blocked → re-prepare;
legacy без body → allowed; mid-GET durable proof (номер записан до
verification GET); crash после POST до verify → targeted get; lost save
→ dispatched intent blocked → reconcile adopted; GET failure → created
сохранён; repeat create/reconcile/resume — 0 новых dispatch; unknown+[];
known+404/error; two-hop ancestry с body spec.

Dispatch counters (из probe + asserts): create с читаемым номером и
провалившимся verify → `created`, `{search:1, create:1, get:1}`;
created→repeat→reconcile→repeat `{search:1, create:1, get:3}` —
второго create нет ни в одной ветви.
Stores full-chain прогона скопированы в `$EV/stores/full-chain/`.

## Integrity

- Protected 19 файлов: до/после — `protected-sha.txt` vs
  `protected-sha-after.txt`, 19/19 unchanged.
- API sources (manifest `run-ni_5bvnc`): 15/15 matched после
  (`api-sources-check-after.txt`).
- Source SHA до/после: `source-sha-before.txt` /
  `source-sha-after.txt`.
- Сеть, SUT/API/UI/TestOps/Docker/Gradle/CI не использовались; Git
  commit/push/fetch/checkout/reset не выполнялись; `gh`, зависимости,
  токены, `.env` не затрагивались.

## Совместимость для 22C

- `Orchestrator.pr_prepare(..., body_path=None)` — новый опциональный
  аргумент; CLI `--body-path` wiring — область 22C.
- `transport.create(spec)` получает dict со всеми полями body;
  transport обязан вернуть `PrRef` с читаемым `number` сразу после
  POST. `transport.get(repo, number)` — targeted verification.
- Legacy state со spec без `body_text`: create с digest=None идёт как
  раньше; digest без текста — blocked до re-prepare (22C не обязан
  мигрировать исторические state).

## Ограничения и непроверенное

- Live GitHub transport (22A), реальные POST/GET, live идемпотентность
  и live PR-статусы **не проверялись** — только fake transport.
- `gh`/HTTP wiring и выбор `--pr-transport` — 22C, не реализовано.
- `pr_search` остаётся read-only и не проходит body-gate (dispatch-only
  по дизайну).
- Идентичный re-prepare — no-op даже для `blocked` entry: snapshot
  восстанавливается на диске, но снятие блока требует re-prepare с
  новым spec (зафиксировано в дизайне).
