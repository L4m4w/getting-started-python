# 21R-C — runbook и каталог workflow

Дата: 2026-11-15. Исполнитель: 21R-C (только документация, без агентов).
**Статус: `ready`** — документационная часть завершена; handoff 21R-A/B
на момент записи отсутствуют, поэтому разделы 21R в обоих документах
явно помечены **целевым контрактом с pending verification**, а не
проверенной реализацией. Код, тесты, shared fixtures/constants, чужие
handoffs/evidence и рабочий workflow не изменялись.

Evidence root: `artifacts/workflow-corrections/21r-c-20261115T204107Z/`
(далее `<EV>`): `sha256-before.txt`, `sha256-after.txt`, `checks.txt`.

## 1. Входы и версии

- Задание: `docs/qa-workflow/agent-tasks/21r-c-runbook-and-catalogue.md`.
- Прочитаны: `AGENTS.md` (правила репозитория),
  `docs/qa-workflow/handoffs/21-independent-workflow-review.md`,
  `coordination-wave-24.md`, `21c-cli-and-repeat-review.md` и оба
  редактируемых документа.
- Code-fact сверка выполнена по чтению `tools/workflow.py`,
  `tools/run-workflow.sh`, `tools/_python.sh`,
  `infrastructure/workflow/{orchestrator,state,envelopes,contracts,
  adapters,index,locks}.py`, `test_data/utils/workflow.py`,
  `test_data/consts/workflow.py` — подробности и file:line в
  `<EV>/checks.txt`.

| Файл | SHA-256 до | SHA-256 после |
| --- | --- | --- |
| `knowledge/integrations/qa-workflow.md` | `5f64bf46…` | `bae95f82…` |
| `knowledge/components/workflow.md` | `5b369ec0…` | `a95ab874…` |

Все прочитанные code inputs на момент чтения совпали с принятыми
SHA 21C (orchestrator `19e506b9…`, state `a7c85ee1…`, envelopes
`8caf13c3…`, contracts `e1caf5c7…`, adapters `9a9b23a5…`, index
`305f3fa2…`, locks `851cd1b7…`, workflow.py `489bf41a…`,
run-workflow.sh `1de31a27…`) — документация написана против этой
проверенной версии 20R2.

**Peer drift (не проверенная версия):** к концу сессии
`infrastructure/workflow/state.py` `a7c85ee1… → 3d5fea11…` и
`infrastructure/workflow/envelopes.py` `8caf13c3… → 14696422…` изменились
— это область 21R-A, работа в процессе; содержимое не читалось и не
учитывалось. `orchestrator.py` (область 21R-B) не изменялся. Handoff
A/B отсутствуют: `ls handoffs | grep -E '21r-[ab]'` пуст, читать
нечего — финальная сверка по §4 остаётся координатору.

## 2. Изменения

### `knowledge/integrations/qa-workflow.md` (runbook)

- Новый раздел «Запуск: интерпретатор и глобальные флаги» (21C F1):
  - интерпретатор `PYTHON` → `.venv/bin/python` → `python3`;
    закрепление `PYTHON=.venv/bin/python` для 19A (голый `python3` без
    зависимостей даёт неочищенный ImportError, не 69);
  - глобальные `--store-dir`/`--workflow-id` **до** subcommand;
    `--workflow-id` обязателен при >1 `wf-*/state.json` в store —
    автовыбора active-линии по `index.json` нет (`_resolve_workflow_id`
    сканирует директории); без флага все команды → `BLOCKED: multiple
    workflows present…` (69);
  - конкретные команды `status`/`doctor`/`resume`/`accept`/`pr` для
    multi-workflow store; `init` флаг не использует (линия выбирается
    записью `repo_key + pilot_id` в index).
- «Хранилище»: superseded-линии остаются на диске → после первого
  supersede `--workflow-id` становится обязательным.
- «Accept»: уточнено, что `check` делает реальный делегированный
  dispatch `compile-tests.sh` + `run-tests.sh list` (не пишет state,
  требует живой venv/tools), а `doctor` — read-only отчёт целостности
  без dispatch, **не полное реальное прохождение цепочки**.
- «Публикация TestOps»: `no-op`-verify обновляет
  `last_observation.checked_at`/`state_sha256` — повтор не бит-в-бит
  по state при стабильных identity digests.
- «Восстановление»: `reconcile`/`resume` записывают локальный
  `state.json`; «read-only» относится к отсутствию повторных внешних
  эффектов, а не к собственному хранилищу.
- Новый раздел «Целевой контракт 21R (pending verification)»: 8
  обязательных решений сводного ревью 21 с маппингом 21A/21B → 21R-A/B
  (required-роли/TestOps, запрет retry по пустому search/404, parent
  evidence для inherited intents, полная повторная валидация base
  rebind, type validation схемы, запрет bool-TestOps-ID, boundary-token
  node IDs, контролируемые исходы, base-observation не перезаписывает
  head).

### `knowledge/components/workflow.md` (каталог)

- «Точки входа»: абзац о глобальных флагах и multi-workflow store
  (согласовано с runbook).
- Helpers (замечание 21C §8): `Project` вынесен в отдельную строку;
  `commit_app_head`, `sync_tests_commit`, `drive_commit_to_executed`,
  `publish_handlers`, `fake_pr_for` и пр. помечены как методы класса
  (проверено `^def `/`class` сканом), а не модульные функции; строка
  модульных helpers очищена от них.
- Новый раздел «Семантика повторов и граница fake/live»: verify-
  timestamps и стабильные identity digests; reconcile/resume пишут
  state; check vs doctor; `published` в unit-пробах — fake simulation,
  не live/MVP (реальный пилот pending до immutable commit).
- Новый раздел «Целевой контракт 21R (pending verification)»: записи
  отражают 20R2; финальная сверка каталога с объединённым кодом —
  координатору.

## 3. Команды, exit и evidence

| Команда | Exit | Результат |
| --- | --- | --- |
| Markdown-link check (`.venv/bin/python`, оба docs) | 0 | `ALL_LINKS_OK`: 5 ссылок, включая `../../docs/qa-workflow/handoffs/21-independent-workflow-review.md` |
| `git diff --check` | 0 | чисто; оба docs — untracked (`??`), поэтому trailing whitespace дополнительно проверен `grep -nE ' $'` — совпадений нет |
| Code-fact сверка по чтению parser/API | — | все утверждения подтверждены file:line, см. `<EV>/checks.txt` |
| SHA до/после docs и code inputs | — | `<EV>/sha256-before.txt`, `<EV>/sha256-after.txt` |
| Поиск handoff 21R-A/B | — | отсутствуют на момент записи |

Тесты/collection/CLI smoke не запускались по заданию: документированные
факты подтверждены чтением кода, не выполнением.

## 4. Pending-сверки для координатора (после handoff A/B)

Точные пункты финальной сверки документов с объединённым кодом:

1. **21R-A (`state.py`/`envelopes.py`)**: подтвердить в merged-коде —
   обе PR-роли + TestOps `required` строго true для `published`;
   явная type/domain validation `expected_executions`/`strength_evidence`/
   `junit_summary`/`selection` с чистым 69 вместо crash; bool отклонён
   как TestOps ID (только положительные int). Если появились новые
   публичные имена/исключения — дополнить каталог (это координатору,
   A/B consts-записи интегрируются отдельно).
2. **21R-B (`orchestrator.py`)**: подтвердить — `created`/unknown
   `pr.create` не разрешает retry по пустому search/404 (targeted
   get + exact verification по известному номеру); inherited intents
   разрешаются только через проверяемое parent evidence; base rebind
   после T8 — полная повторная source/scenario/provenance/environment
   проверка без переиспользования head; boundary-token matching node
   IDs; controlled outcomes для missing spec/search exceptions/corrupt
   TestOps state; base observation не перезаписывает head publication.
3. Сверить неизменность задокументированной семантики `check`/`doctor`/
   `reconcile`/`verify-testops`/`_resolve_workflow_id` после merge и
   снять пометку pending у разделов 21R.
4. Если A/B добавляют CLI-флаги/действия — синхронизировать раздел
   глобальных флагов и таблицу точек входа.

## 5. Точные ограничения для 19A

- `--workflow-id` обязателен в любом store с >1 линией (после первого
  supersede или нескольких пилотов); `init` его не принимает — линия
  выбирается `repo_key + pilot_id`.
- Закреплять `PYTHON=.venv/bin/python`; голый `python3` → необработанный
  ImportError, а не чистый 69.
- `check` запускает реальный `compile-tests.sh` + `run-tests.sh list`
  — требует живой venv/tools; `doctor` этот dispatch не заменяет.
- Реальный пилот (patch head + dirty tests) остаётся `executed`/pending
  до immutable commit; `pr create` заблокирован до commit head +
  live transport.
- Повторный `verify-testops` обновляет `checked_at` — сравнение state
  после повторов не бит-в-бит по файлу; identity digests стабильны.

## 6. Границы выполнения

- Изменено только: `knowledge/integrations/qa-workflow.md`,
  `knowledge/components/workflow.md`, этот handoff, `<EV>/`.
- Не тронуты: README/plans/старые handoffs, реализация, тесты, shared
  fixtures/constants, чужие evidence; рабочий workflow и accepted
  execution state — read-only.
- Не выполнялось: запуск других агентов, pytest/unit/collection, CLI
  subprocess smoke, сеть/SUT/API/UI, Docker/Gradle/CI, TestOps/PR
  writes, Git commit/push/checkout/reset, чтение/копирование секретов.
- Все pre-existing незакоммиченные изменения других участников
  сохранены; peer drift зафиксирован, но не учитывался как проверенная
  версия.
