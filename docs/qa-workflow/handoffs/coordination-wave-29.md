# Проверка 22A/22B: B принят, get-снимок A требует исправлений

Дата: 2026-11-16. **22B принят в назначенной offline-области.
22A и общая приёмка A/B остаются открытыми. 22C пока не запускать.**
Следующее узкое поручение — [22AR](../agent-tasks/22ar-github-snapshot-corrections.md).
Готовые handoff A/B сохранены неизменными. Новых агентов не запускалось.

## Входы и версия

Прочитаны handoff/design A/B, github.py, adapters/orchestrator,
связанные helpers и новый набор fixtures/tests. Финальные source SHA
соответствуют handoff:

- github.py: `96f1c3f85761c05abcdb139ab1a1ea3cf72856cd7ec2f87acbb385ba76aabffd`;
- adapters.py: `10ac33420b94b39e9f98d7981e03c8fbfd82a52f47d945adefa9f864c815f35c`;
- orchestrator.py: `bdd8196589b2aaafbb3410d24f387ebcf284304847a379dd0680a67652feb993`.

Промежуточный SHA github.py `d4c06ec4…` в handoff B — peer-снимок
незавершённой A; общая проверка координатора использовала финальный
`96f1c3f8…`, не промежуточную версию. tools/workflow.py не менялся:
CLI wiring ещё не реализован. 22B упоминает будущий `--body-path`, но
фактический существующий флаг CLI — `--body`, передающий body_path;
22C сохраняет этот публичный флаг, не обязан вводить новый синоним.

Exact inputs: `artifacts/workflow-github/coordinator-22ab-review-20261116/reviewed-inputs.sha256.json`.
Это reviewed manifest, не утверждение о принятии A.

## Собственные проверки координатора

Evidence: `artifacts/workflow-github/coordinator-22ab-review-20261116/`.

Собственный pytest, exit 0, **218 passed** за 83.28 s, `targeted.xml`:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/unit/test_workflow_github.py tests/unit/test_workflow_pr_payload.py \
  tests/unit/test_workflow_intents.py tests/unit/test_workflow_21r_b.py \
  tests/unit/test_workflow_21r2.py \
  tests/unit/test_workflow_20r2.py::TestR2GitHeadSeparation \
  -q --basetemp=artifacts/workflow-github/coordinator-22ab-review-20261116/pytest-temp \
  -o cache_dir=artifacts/workflow-github/coordinator-22ab-review-20261116/pytest-cache \
  --junitxml=artifacts/workflow-github/coordinator-22ab-review-20261116/targeted.xml
```

Полный unit/collection не повторялся. Новые A 86 и B 36 + прежние
96 regressions проверены на объединённой версии. Full-chain fake repeat
из новой копии — 31/31, exit 0. Это programmatic simulation, не
production CLI с GitHub и не live API. `versions.sh` — exit 0.
19 protected SHA и 15 API sources совпали; рабочий workflow не менялся.

Две собственные серии probes (только fake HTTP, fake Git/runner/temp
stores), exit 0 означает завершение, не отсутствие findings:

- `github-probes.py` / `.json`: transport.get + pr_ref_exact, контроль
  и две негативные мутации. Оба негативных ref ошибочно exact=True.
- `github-integration-probes-v2.py` / `.json`: настоящий
  GitHubPrTransport A + Orchestrator/PrSpec B, корректная commit/tree
  fixture GitHub repo, phase executed. Контроль verified; обе негативные
  пробы также ошибочно verified. На каждую цепочку один POST, затем
  GET PR + GET files; дополнительного GET PR после files нет.

Первый integration script без v2 использовал общий fixture git.invalid:
он корректно блокировался до HTTP и не доказывает эти findings.
V2 задаёт canonical github.com/Unit-Org/Unit-Repo через subclass Project.init,
не меняя source/tests/общие константы. Пробу считать по v2.

## F-22A-1 — P1: неполный files принят как полный

`github.py::get/_read_files` не сверяет число полученных files с
`changed_files` из PR detail. Ответ PR объявляет changed_files=2, files
endpoint возвращает один файл без Link. `get` выдаёт этот один файл как
полный список; если он совпадает с spec.files, `_verify_pr` принимает
его и state становится **verified**. В probe actual_file_entries=1,
declared_changed_files=2, outcome=verified, exit 0.

Сигнал противоречия уже есть в прочитанном ответе, но игнорируется.
Строгая проверка отдельных страниц/дубликатов не доказывает полноту.
Необходимы проверяемый nonnegative int count (без bool) и exact equality
полученного полного уникального списка; missing/invalid count и
truncation/серверный лимит => controlled error, не verified.

## F-22A-2 — P1: get возвращает смесь разных версий PR

`get` читает PR detail один раз, затем читает files и сразу возвращает
PrRef. В fake server при files-запросе head изменяется с 111… на 999…;
возвращённый ref продолжает утверждать прежний head 111…. Orchestrator
с правильным локальным commit/tree принимает **verified**, хотя текущий
remote head уже 999…. Это фактическая интеграционная проба, а не только
отсутствие дополнительного вызова в статическом коде.

Нужен ограниченный согласованный снимок: detail → files → повторный
detail с проверкой используемых identity/spec/status/count полей
(включая head/base SHA, repo/branches/title/body/draft/merged). Drift или
ошибка повторного чтения => controlled inconclusive/blocked, без нового
POST и без ложного verified. Это наблюдение согласованности, не обещание
атомарности или неизменности PR после последнего чтения.

## Решения и следующий шаг

B body_text/body_sha256 и durable number checkpoint приняты на
проверенных путях: UTF-8/CRLF сохраняются, legacy payload не угадывается,
source/snapshot drift блокирует dispatch, number записан до verification
GET, crash/unknown/ancestry не повторяют create. B повторно не запускать.
Имя body_path существовало в API до B; не считать его новым CLI-флагом.

22AR исправляет два findings в github.py с отдельными регрессиями и
повтором координаторских probes из копий. После его handoff координатор
принимает исправленную A + совместимость с принятой B и только затем
передаёт 22C. Сводный 22 и финальная приёмка остаются координатору.

Никаких сети/реальных tokens/GitHub API/PR/TestOps/SUT/Docker/CI/Git
writes не выполнялось. Исторические evidence, пакеты19A2, protected
state и checkout сохранены. Пакет QA будет инкрементально обновлён после
всего 22; live публикации/идемпотентность/MVP остаются открытыми.
