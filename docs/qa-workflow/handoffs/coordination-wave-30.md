# Приёмка 22AR и допуск 22C

Дата: 2026-11-16. **22AR принят; исправленная 22A и ранее принятая
22B совместно приняты в offline-границах. Можно запускать
[22C](../agent-tasks/22c-cli-and-http-integration.md).** Весь этап 22
ещё не завершён: production CLI wiring и его интеграция впереди.
Live PR и Git writes этим решением не разрешены.

## Проверенная версия

Прочитаны [handoff 22AR](22ar-github-snapshot-corrections.md), новый
design, github.py и regression tests. Точные входы/принятые SHA:
`artifacts/workflow-github/coordinator-22ar-review-20261116/accepted-inputs.sha256.json`.
Исходный `reviewed-inputs.sha256.json` в том же каталоге фиксирует
версию начала проверки. Ключевые SHA совпадают с handoff:

- github.py: `2d27e9978e5db215b780ad084271d0038b545e66b30b4cb1f867f5f759554019`;
- adapters.py: `10ac33420b94b39e9f98d7981e03c8fbfd82a52f47d945adefa9f864c815f35c`;
- orchestrator.py: `bdd8196589b2aaafbb3410d24f387ebcf284304847a379dd0680a67652feb993`.

B source/tests/consts и tools/workflow.py не изменялись при 22AR.
Следующий исполнитель C получает окончательную версию A, не peer-снимок
из раннего handoff B. Старые handoff/evidence сохранены неизменными.

## Собственные проверки координатора

Evidence: `artifacts/workflow-github/coordinator-22ar-review-20261116/`.

Собственный pytest — **161 passed**, exit 0, `targeted.xml`:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/unit/test_workflow_github.py \
  tests/unit/test_workflow_github_snapshot.py \
  tests/unit/test_workflow_pr_payload.py \
  -q --basetemp=artifacts/workflow-github/coordinator-22ar-review-20261116/pytest-temp \
  -o cache_dir=artifacts/workflow-github/coordinator-22ar-review-20261116/pytest-cache \
  --junitxml=artifacts/workflow-github/coordinator-22ar-review-20261116/targeted.xml
```

Это A 86 + snapshot 39 + неизменённые B payload 36. Полный unit/
collection и прежние 96 regressions/31 fake-repeat из wave 29 заново
не повторялись: B и общая orchestration не менялись.

Обе собственные пробы wave 29 повторены из новых побайтных копий:

- `github-probes.py`: control exact=True, GET detail/files/detail;
  incomplete-files и head-race → GitHubResponseError, ref не возвращён.
- `github-integration-probes-v2.py`: настоящий A+B на корректном
  GitHub fake commit/tree, control verified; обе негативные цепочки
  остаются **created**, number=137 сохранён, POST=1. Ложного verified нет.
  App/tests и отсутствие повторного POST дополнительно проверены
  integration-регрессиями TestOrchestratorSnapshot в новом файле.

Оба script exit 0 означает завершение; выводы сделаны по фактическим
ошибкам/status/counters в JSON, а не по exit одному. Versions — exit 0,
Python 3.13.15/pins совпали. Reviewed inputs, 19 protected SHA и 15 API
source SHA совпали до/после; diff --check обоих репозиториев — exit 0.
Рабочий workflow initialized, исторические execution/TestOps state неизменны.

## Принятые исправления

`get` требует валидный changed_files, не принимает count выше
MAX_LISTED_FILES=3000, сверяет exact count полного уникального file list.
Missing/invalid/mismatched count не позволяет вернуть подтверждённый ref.
Detail после files повторяется: использованные identity/spec/status/
count поля должны совпасть. Base repo сверяется с requested repo при
каждой нормализации; base SHA входит в сравнение, как и head/title/body/
draft/state/merged. Drift/ошибка/404 второго чтения — controlled failure.

Один GET при первичном 404 по-прежнему возвращает None; это не разрешает
recreate. Create по-прежнему один POST без verification GET до checkpoint
B. Сигнатуры A/B и hierarchy exceptions не менялись. Оба P1 wave 29
закрыты на проверенных путях; новых блокирующих замечаний не осталось.

Снимок согласован по наблюдаемым полям двух detail reads, не атомарен
и не обещает, что PR не изменится после чтения или что скрытая гонка
между одинаковыми endpoint snapshots невозможна. Live API не вызывался:
формы/лимит/API version основаны на источниках исполнителя и synthetic
fixtures; подтверждение живого GitHub ещё предстоит по отдельному разрешению.

## Поручение C и оставшиеся границы

Передать пользователю готовое поручение 22C. C пишет только CLI,
свои tests/consts и общие каталоги/runbook; A/B source read-only.
Использовать существующий `--body` → body_path, не вводить `--body-path`
из описательной неточности handoff B без необходимости. `get` ожидаемо
делает два detail GET и files pages; fake HTTP counters C это учитывают.
Все ранние команды/default/missing flags — ноль HTTP/реальных token reads.

После C координатор проверяет целый 22 и инкрементально обновляет QA
пакет. APP/19A2 и A/B повторно запускать не нужно без drift/новых findings.
Immutable heads, draft PR, live идемпотентность и итоговая оценка MVP
остаются открытыми. Текущие Git checkout/index не переключались;
commit/push/PR не выполнялись и не разрешены.

В этой проверке не было сети/официальных docs/live repository API,
реальных tokens/.env, SUT/TestOps/Docker/Gradle/CI, изменения исторических
пакетов/evidence или запуска агентов. Ограничения evidence 07,
provenance 10/17 и close-аудита wave 17 сохраняются. Upload/close
run-ni_5bvnc/launch 57317 не повторять.
