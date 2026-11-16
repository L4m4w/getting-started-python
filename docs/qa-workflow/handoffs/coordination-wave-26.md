# Приёмка 21/21R/21R2 и актуализация Git/PR-пакета

Дата: 2026-11-16 (Europe/Volgograd).
**Независимое ревью 21 и исправления 21R/21R2 завершены и приняты
координатором в offline-границах.** P1 F-21R-B-1 закрыт на проверенных
путях. Это не приёмка live PR, не разрешение Git writes и не завершение MVP.
Исторические отказы/ограничения wave 20/21/24/25 сохранены.

## Версия и собственные проверки

Прочитаны [handoff 21R2](21r2-pr-lineage-deduplication.md), изменения
orchestrator, регрессии и документация; исходные handoff не изменены.
SHA orchestrator соответствует исполнителю:
`f9e9d312c889b9f7a896132ddcf1624d1734d98d468cc1b9f17c607267d78607`.
State/envelopes и прежние tests/consts A/B не менялись.

Evidence координатора:
`artifacts/workflow-corrections/coordinator-21r2-review-20261116/`.
`reviewed-inputs.sha256.json` содержит 22 точных SHA проверенной версии
до актуализации статуса двух текущих документов координатором;
`accepted-inputs.sha256.json` — итоговые SHA с этой документационной
актуализацией. `verification-summary.json` — команды/коды и сверки;
`final-verification.json` — финальный контроль.

Собственный pytest — **99 passed**, exit 0, 66.96 s, `targeted.xml`:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/unit/test_workflow_21r2.py tests/unit/test_workflow_21r_b.py \
  tests/unit/test_workflow_intents.py \
  tests/unit/test_workflow_20r.py::TestF1UnresolvedExternalEffect \
  tests/unit/test_workflow_20r2.py::TestR2GitHeadSeparation \
  -q --basetemp=artifacts/workflow-corrections/coordinator-21r2-review-20261116/pytest-temp \
  -o cache_dir=artifacts/workflow-corrections/coordinator-21r2-review-20261116/pytest-cache \
  --junitxml=artifacts/workflow-corrections/coordinator-21r2-review-20261116/targeted.xml
```

Четыре scripts повторены из новых копий, все exit 0:

- **Проба P1:** `inherited-zero-search.py`, assertion=passed,
  remote_numbers=[42], child calls=[search,get,get,get]. Первые
  search/get — parent adoption; child не делает search/create и
  редоказывает известный номер targeted get. PR #101 больше не создаётся.
- Старые B effect probes — **13/13 OK** по outcome/counters.
- C fake full-chain repeat — **31/31**, 0 failed; runner/PR dispatch
  при идентичном повторе не растёт. Published только simulation.
- Real evidence compatibility — **11/11**, head problems=[], baseline
  с закреплённой provenance принят, без неё отклонён по двум файлам
  17A. Пять tree digest harness/TestOps head/base и workflow до/после
  идентичны. Это чтение сохранённого evidence, не API-прогон.

22 reviewed SHA, 19 protected SHA и 15 API sources совпали до/после
проб. `versions.sh` — exit 0, Python 3.13.15/pins OK; diff --check обоих
репозиториев — exit 0. Working workflow остаётся initialized.

24 новых и 75 regression passed исполнителя независимо пересчитаны
по его JUnit; собственный прогон выше проверил тот же набор. Полный
unit/collection координатор не повторял. 511 unit — прежнее измерение
21R-B; 550 collected — измерение collection исполнителя 21R2, не 550
passed. Формулировка handoff «collection не повторялся» ограничена этим
уточнением: `compile-tests.sh` фактически выполнил collection.

## Что принято и пределы

`init --supersede` переносит unresolved/resolved ancestry и terminal
PR intents с известным номером. Обход `supersedes` проверяет связь
предка (до 32 hops, с защитой от циклов). Разрешение intent сохраняет
remote effect guard; перед dispatch известный номер проходит targeted
get и текущие commit/tree/exact-spec guards. Mismatch/404 → blocked,
ошибка get → unknown, ни один из этих исходов не разрешает recreate.

Новые регрессии покрывают app/tests, resolved parent, terminal effect
до supersede, two-hop known/unresolved ancestry, re-prepare/revision и
контроль первого create без прежнего effect. Совместно с принятой
проверкой wave 25 это закрывает независимый этап 21 и его исправления.
На проверенных путях открытых блокирующих findings нет; исчерпывающий
аудит всех возможных локальных state не заявляется.

Live transport PR в production workflow CLI по-прежнему отсутствует;
новые ветки проверены programmatic fake transport, не реальным GitHub.
Ограничения CLI report exit 0 из wave 25 сохраняются. Реальные Git
heads с пилотными правками отсутствуют; QA HEAD
c84483bf6647678d4052eb377e04a682cdaddd74, ветка MVP_workflow; app HEAD
36674280b6878540a9e88f40aaeedf5dfdd2e6ce, main. Оба checkout dirty.

API/TestOps 00–18 остаются принятыми. State/log run-ni_5bvnc, launch
57317, шесть bindings, ограничения evidence 07, provenance 10/17 и
close-аудита wave 17 неизменны. Upload/close не повторять.
Сети/SUT/API/UI, Docker/Gradle/CI/live writes, commit/push/checkout/reset
и запуска агентов координатором не было. Секреты не читались/не копировались.

## Следующая очередь

Актуализировать 19A двумя независимыми частями, запускаемыми пользователем:

- [19A2-QA](../agent-tasks/19a2-qa-package-refresh.md): QA allowlist,
  snapshots/SHA, final PR title/body, зависимости локального evidence,
  конкретный будущий план. Write scope — свой handoff/evidence.
- [19A2-APP](../agent-tasks/19a2-app-package-refresh.md): два файла
  приложения, patch/source identity, title/body и план. Отдельный
  handoff/evidence; приложение read-only.

Могут стартовать параллельно. Общая приёмка и финальный объединённый
Git/PR-план — координатора после обоих результатов. Решения wave 19
сохраняются: QA base MVP_workflow, process docs отдельным логическим
commit внутри QA PR; app base main, только @Valid + Java regression.
Никаких Git writes или новых разрешений из этого решения не следует.
Следующее согласование Git writes — только по конкретному принятому
пакету. Затем нужны immutable heads/реальные draft PR, решение по live
PR transport/интеграции, live идемпотентность и итоговая оценка MVP.
