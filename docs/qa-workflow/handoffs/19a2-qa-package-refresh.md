# 19A2-QA — актуализированный локальный Git/PR-пакет QA

Дата: 2026-11-16 (снимок 2026-11-15T21:48Z UTC). Исполнитель: `19A2-QA`.
Статус: **`ready`** — пакет собран и проверен локально; состав решён по
wave 19, открытые пункты — только решения момента публикации
(раздел «Оставшиеся решения»). Commit/push/PR не выполнялись; index,
ветки, checkout, staged-состояние и remotes не менялись.

Поручение: [19a2-qa-package-refresh.md](../agent-tasks/19a2-qa-package-refresh.md).
Приёмка и рамки: [coordination-wave-26.md](coordination-wave-26.md),
решения состава: [coordination-wave-19.md](coordination-wave-19.md).
Исторический пакет: [19a-git-pr-preparation.md](19a-git-pr-preparation.md)
(superseded этим пакетом; его состав не актуален).

## Версии и инвентаризация (read-only)

Evidence: `artifacts/git-pr/19a2-qa-20261115T214801Z/` (gitignored).

- QA `getting-started-python`: HEAD
  `c84483bf6647678d4052eb377e04a682cdaddd74`, ветка `MVP_workflow`.
  Локальный кеш `origin/MVP_workflow == HEAD`, `origin/master ==
  9770f36` (отстаёт) — **без fetch, свежесть сервера не доказана**.
  Remote `git@github.com:L4m4w/getting-started-python.git`, credentials
  в URL нет. Staged — пусто, stash — пусто.
- Рабочее дерево на снимок: 18 modified + 164 untracked. Полный дамп:
  `inventory/qa-git-inventory.txt`, списки
  `inventory/qa-{modified,untracked}-all.txt`.
- План wave 19 сохранён: узкий draft PR от `MVP_workflow` на отдельной
  feature-ветке; процессные docs — отдельный логический commit внутри
  того же QA PR. Повторный выбор base не предлагается.
- Рабочий workflow: `artifacts/workflow/wf-17431cddc9919d3d/state.json`
  phase `initialized` (index.json active, revision 1) — подтверждено,
  SHA защищён.
- Приложение не инвентаризировалось и не пакетировалось — область
  19A2-APP. Его handoff `docs/qa-workflow/handoffs/19a2-app-package-refresh.md`
  появился в QA-дереве в ходе этой задачи и учтён в commit B
  (peer-файл, не редактировал).

## Состав публикации (allowlist: 184 кандидата)

`qa/allowlist-qa.{txt,json}` — вердикт и причина по каждому файлу.
Все решения по составу приняты wave 19; `needs_decision` среди файлов нет.

**Commit A — пилотный код и документы (71 файл):**

- 10 modified: `requirements.txt` (+psycopg), `tools/harness.py`
  (группа `api`, manifest schema-2, `api-contract-v1`),
  `tests/unit/test_harness.py`, `test_data/consts/harness.py`,
  `knowledge/components/{README,consts,fixtures,infrastructure}.md`,
  `knowledge/integrations/ci-github.md`, `knowledge/testing/run-tests.md`.
- 61 untracked: `infrastructure/http/` (3),
  `infrastructure/reporting/testops/` (7), `infrastructure/workflow/` (8,
  оркестратор 20/20R/20R2/21R/21R2), `tools/` (6: `java_evidence.py`,
  `run-java-test.sh`, `run-testops.sh`, `run-workflow.sh`, `testops.py`,
  `workflow.py`), `tests/api/` (3), `tests/unit/` (16 новых),
  `test_data/consts/` (11), `test_data/utils/workflow.py`,
  `knowledge/components/workflow.md`,
  `knowledge/integrations/{qa-workflow,testops}.md`, пилотные
  `requirement.md` (M), `scenarios.md` (M), `testops-mapping.md` (??).
- Patch: `qa/commit-A-tracked.patch` (12 M-файлов commit A),
  SHA-256 `1b5ef291b9d1e6ff9dfaf0e620bf869ed19aa4a1910f1c669ec28f91985a6c45`.

**Commit B — процессные документы (113 файлов):**

- 6 modified: `docs/plans/qa-workflow-mvp.md`, `docs/qa-workflow/README.md`,
  `docs/qa-workflow/agent-tasks/{03-runtime-plan,04-gateway-regression,07-integration,README}.md`.
- 107 untracked: `docs/qa-workflow/agent-tasks/` (25),
  `docs/qa-workflow/design/` (4), `docs/qa-workflow/handoffs/` (77:
  все handoffs 00–21R2, coordination-wave 1–26, этот handoff и peer
  `19a2-app-package-refresh.md`), 5 малых логов
  `handoffs/evidence/01-build-readiness/` — **зафиксированное исключение**:
  сырые логи включены, потому что на них прямо ссылается включаемый
  handoff 01 (суммарно ~38 КБ, прошли secret scan). Остальные сырые
  логи/artifacts не включаются.
- Patch: `qa/commit-B-tracked.patch` (6 M-файлов commit B),
  SHA-256 `9a537f10bf636669af2e135446fce3692b69504e4388b16d973a08b0dc5a0813`.

**Исключить (gitignored, в `git status` не появляются):** `.env`,
`.venv/`, `.idea/`, `__pycache__/`, `artifacts/` целиком,
`allure-results/`, `allure-report/`, `.DS_Store`. Недоступность
локальных evidence из удалённого PR описана в `qa/dependencies.md`.

## Snapshot и целостность

- `qa/sources/` — побайтовые копии всех 183 существующих файлов
  allowlist (184-й — этот handoff, хеш ниже дописан после создания).
- `qa/SHA256SUMS.txt` — SHA-256 по repo-path для всех файлов.
- Проверка целостности: все копии == рабочему дереву == SHA256SUMS,
  расхождений 0 (183/183 на момент проверки).
- Untracked учтён полностью: `git ls-files --others --exclude-standard`
  → 164 файла на снимок (+2 peer/мой handoff появились позже и учтены).
- Единственный drift за задачу: новый файл peer 19A2-APP
  `handoffs/19a2-app-package-refresh.md` — добавлен в allowlist/snapshot
  с пометкой перехешировать при публикации.

## Сверки принятых идентичностей (источники измерений указаны)

| Проверка | Результат |
| --- | --- |
| 22 файла `accepted-inputs.sha256.json` координатора (wave 26) | 22/22 совпали до и после |
| 19 protected SHA (список evidence 21R2: workflow/testops/harness state+manifests+junit, coordinator probes) | 19/19 OK до и после |
| 15 API source SHA manifest `run-ni_5bvnc` (`32f1ec89…`, api-contract-v1) | 15/15 совпали до и после |
| Pinned baseline record `DEFAULT_ACCEPTED_HISTORICAL_BASELINES`: SHA `coordination-wave-5.md`, `coordination-wave-14.md`, `category_update.py`, `test_category_update.py` | все совпали с записью |
| `git diff --check` | exit 0 до и после |
| Secret scan allowlist (только точный список, значения не выводились) | 16 срабатываний — все ложные: идентификаторы token/password, синтетические unit-константы, docs-примеры; реальных секретов нет (`secret-scan.txt`) |
| Локальные markdown-ссылки include-файлов | 0 битых; 18 ссылок ведут на tracked-неизменённые файлы base (разрешатся на remote) |
| Staged / index / remotes / config | не изменялись; `git diff --cached` пуст |

Drift не обнаружен. Числа из handoffs не повторялись прогонами:
unit/collection заново не запускались (код не менялся); источники:
coordinator targeted **99 passed** (wave 26, `targeted.xml`),
**24+75** по JUnit 21R2, **511 passed** — прежнее измерение 21R-B,
**550 collected** — collection 21R2, не «550 passed».

## Зависимости вне Git

`qa/dependencies.md`: pinned baseline record (с SHA review-документов,
входящих в commit B), manifests/source copies/пакеты/intents под
`artifacts/`, Java/API/TestOps evidence (launch 57317, state
`7bec44e1…`, upload.log `0f40d658…`), ограничения evidence 07 (F-1/F-2),
provenance 10/17 (operator-declared + live container check),
close-аудит wave 17. Разбивка «есть в PR / локально недоступно /
отдельное будущее решение» — там же; registry, исторические документы
и пути не правились.

## PR title/body

- `pr-title.txt`: `test(api): CAT-UPD-VAL — валидация обновления
  категории: API-тесты, TestOps tooling и offline-оркестратор workflow`
- `pr-body.md`: покрытие (6 сценариев R1–R4, bindings 55373–55378,
  проект 5444), состав двух commits, offline workflow, таблица проверок
  с точными SHA/JUnit без смешивания прогонов, пределы evidence и MVP.

## План будущих Git-операций (НЕ выполнять; иллюстративно)

```sh
# предполагаемая ветка: feature/cat-upd-val-qa-workflow, base: MVP_workflow
git switch -c feature/cat-upd-val-qa-workflow
# commit A — точный allowlist из qa/allowlist-qa.txt, commit=A (71 файл)
git add <файлы commit A>
git commit -m "test(api): CAT-UPD-VAL API-тесты, TestOps tooling и offline-оркестратор"
# commit B — файлы commit=B (113 файлов)
git add <файлы commit B>
git commit -m "docs(qa-workflow): поручения, design, handoffs и приёмки волн 00–26"
git push -u origin feature/cat-upd-val-qa-workflow
gh pr create --draft --base MVP_workflow \
  --title "$(cat pr-title.txt)" --body-file pr-body.md
```

Непосредственно перед операциями обязательно: пересобрать
инвентаризацию и пакет (drift peer-работ возможен), пересчитать
SHA256SUMS против working tree и 19/22/15-файловых сверок, `git fetch` +
проверка свежей base и прав записи, секрет-скан staged-состава,
`git diff --check`. После commit записать новый head SHA; исторические
executions остаются base+patch/dirty и не становятся provenance нового
head. Body передавать только `--body-file`; head SHA, cross-links и PR
URL не выдумывать.

## Открытый пункт: live PR transport

В workflow CLI (`tools/workflow.py` + orchestrator) live PR transport
отсутствует: `pr search`/`create` без транспорта → exit 77; ветки
проверены только fake transport. Ручная публикация через `gh` сама по
себе не доказывает live-идемпотентность оркестратора (intents,
reconcile, lineage guard). Следующие решения для координатора:

1. Контракт и реализация PR transport (GitHub REST/`gh` adapter) —
   отдельное авторизованное поручение, в этой задаче не реализуется.
2. Порядок интеграции пакетов 19A2-QA + 19A2-APP и запрос разрешения
   Git writes — координатору после обоих handoffs.
3. Политика revision после первого commit: `tests_repo.dirty=false` и
   новый head требуют осознанного `init --supersede`/revision +
   provenance-решения для исторических executions.
4. Проверка live-идемпотентности (повторный вход на сервере после
   реальных draft PR) — критерий полного MVP, сейчас недоказана.

## Проверки исполнителя (offline, exit-факты)

| Команда/проверка | Exit | Результат |
| --- | --- | --- |
| Git-инвентаризация read-only (rev-parse/branch/refs/status/diff-check/log/stash) | 0 | `inventory/qa-git-inventory.txt` |
| `shasum -a 256 -c` 19 protected SHA (до) | 0 | 19/19 OK — `inventory/protected-sha-check-before.txt` |
| 22 accepted-inputs SHA (до/после) | — | 22/22 MATCH |
| 15 API sources vs manifest run-ni_5bvnc (до/после) | — | 15/15 MATCH — `inventory/api-sources-check-before.txt` |
| `git diff --check` (до/после) | 0/0 | чисто |
| Snapshot copy + SHA256SUMS integrity | — | 183/183 OK |
| Secret scan 182 файлов allowlist | — | 0 реальных секретов — `secret-scan.txt` |
| Link check include-файлов | — | 0 битых; 18 ссылок на tracked-неизменённые |
| After-recheck status/untracked | — | единственный drift — peer handoff 19A2-APP (учтён) |

Не выполнялось: сеть/fetch, API/UI/SUT, Docker/Gradle/CI/TestOps,
PR writes, commit/push/checkout/reset, чтение/копирование секретов,
unit/collection-прогоны (код не менялся), запуск агентов. Все чужие
незакоммиченные изменения и staged-состояние сохранены.

## Остановка

Пакет готов к приёмке координатора. Интеграция двух пакетов и запрос
разрешения Git writes — после конкретной подготовки, не в этой задаче.
