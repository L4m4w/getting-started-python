# Приёмка 22C/всего 22 и готовность локальных Git heads

Дата: 2026-11-16. **22C и весь этап 22 приняты в offline-границах.**
[Сводный handoff](22-github-pr-transport.md). Открытых блокирующих findings
на проверенных путях нет. Исторические отказы A и ограничения всех
прошлых волн сохраняются; полный MVP не завершён.

## Входы и версия

Прочитан handoff/design C, tools/workflow.py, новые subprocess tests/
bootstrap и документация; источники A/B/AR совпали с принятой wave 30.
Ключевые SHA:

- tools/workflow.py: `f9ed251bba6ea5ba428ad17027be2abe94f366455c978a9bbbbf06cf33039e88`;
- github.py: `2d27e9978e5db215b780ad084271d0038b545e66b30b4cb1f867f5f759554019`;
- adapters.py: `10ac33420b94b39e9f98d7981e03c8fbfd82a52f47d945adefa9f864c815f35c`;
- orchestrator.py: `bdd8196589b2aaafbb3410d24f387ebcf284304847a379dd0680a67652feb993`.

Exact inputs: `artifacts/workflow-github/coordinator-22c-review-20261116/reviewed-inputs.sha256.json`;
итоговый accepted manifest и `final-verification.json` в том же каталоге.
Старые handoffs/пакеты/evidence не изменялись. CLI public `--body`
сохранён; произвольный endpoint/disable-guards флаг не добавлен.

## Собственный финальный прогон

На общей версии впервые после изменений shared adapters/orchestrator,
GitHub transport и CLI выполнена вся группа unit; прежний полный unit
был до этих изменений. Дополнительный targeted прогон поверх него не
дублировался.

```sh
PYTEST_ADDOPTS='--basetemp=artifacts/workflow-github/coordinator-22c-review-20261116/pytest-temp -o cache_dir=artifacts/workflow-github/coordinator-22c-review-20261116/pytest-cache' \
  sh tools/run-tests.sh group unit
```

Exit 0, **711 passed**, failures/errors/skips=0, 167.08 s.
Python 3.13.15, pytest 9.1.1, pins совпали. Evidence:
`artifacts/harness/run-y3h45x2t/` — manifest/JUnit/Allure;
`artifacts/workflow-github/coordinator-22c-review-20261116/unit.log`.
Это собственный прогон координатора, не пересказ измерений C.
726 collected из handoff C — отдельная collection всех областей,
не 726 passed; координатор её не повторял.

Повторный full-chain fake script из новой копии — **31/31**, exit 0,
`full-chain-repeat-results.json`; dispatch при идентичном повторе не
растёт. Программная fake-цепочка и реальные CLI subprocess tests внутри
711 различаются; real HTTP/live GitHub здесь не было.

19 protected SHA и 15 API sources совпали до/после; current workflow
initialized, state/log run-ni_5bvnc прежние. Исторические upload/close
не выполнялись. Diff --check обоих репозиториев и ссылки новых docs — OK.
Git refs/checkout/index не изменялись; proposed feature-ветки локально
отсутствуют, staged обоих checkout пуст.

## Обновлённый конкретный Git-пакет

Инкрементальная актуализация 19A2 выполнена координатором, повторных
исполнителей 19A2 не требуется. Новый каталог:
`artifacts/git-pr/coordinator-22-final-20261116/`.

Там exact allowlists по commits, snapshots/SHA, `inventory.json`,
`verification.json`, title/body и **`local-git-plan.md`**. Исходные
19A2 snapshots не переписаны; новая версия включает принятые source/
tests/consts/docs всего 22 и актуальную процессную приёмку.

| Repo | Base | Предлагаемая новая локальная ветка | Коммиты |
| --- | --- | --- | --- |
| niffler-py-st3 | 36674280b6878540a9e88f40aaeedf5dfdd2e6ce (main) | fix/cat-upd-val-gateway-validation | @Valid + Java regression, один |
| getting-started-python | c84483bf6647678d4052eb377e04a682cdaddd74 (MVP_workflow) | feature/cat-upd-val-qa-workflow | A: code/pilot docs; B: process docs |

Состав/хеши конечного пакета определяются его manifest, не старым числом
184 из первоначального 19A2. Сырые artifacts исключены, пять ранее
принятых build-readiness logs остаются точным исключением wave 27.
Новые файлы/обновления проверены targeted secret scan без вывода значений;
совпадения synthetic test credentials отделены от реальных secrets.

## Следующее разрешение: только локальные коммиты

Подготовить две isolated managed worktree от закреплённых bases;
проверить пригодные существующие attached worktree через list_artifacts,
при необходимости использовать create_worktree. Общие dirty checkout
не переключать/не сбрасывать и не очищать после копирования.
Перенести только exact allowlist, проверить staged tree/SHA и создать
один APP commit и два QA commits, записать два конечных head/tree SHA.
Промежуточный QA A зависит от pinned review docs в B; готовность оценивается
по конечному дереву после обоих commits, не промежуточному A.

**Этот handoff сам не разрешает Git writes.** Следующий запрос пользователю
ограничен isolated worktrees/feature-ветками/локальными commits из пакета.
Нет разрешения сети/fetch/push/PR/SUT/Docker/TestOps/credentials/merge.
Такое разделение позволяет получить immutable heads, сохранив текущее
ограничение пользователя и все рабочие изменения.

После heads отдельно подготовить revision/context/review и совместимость
execution с clean commit identity. Старый dirty head evidence не
принимается новым clean head автоматически: не расширять head waiver,
не менять manifest/state истории. Если необходим новый реальный API run,
readiness, scope и cleanup требуют конкретного отдельного разрешения.
Затем — fresh remote refs/права, push/draft PR, live repeat и финальная
оценка MVP. Ранее принятые TestOps launch 57317 и bindings не дублировать.

Координатор не запускал агентов, сеть/live GitHub/SUT/API/UI/CI,
Git commit/push/checkout/reset и не читал реальные credentials/.env.
Ограничения evidence 07, provenance 10/17 и close-аудита wave 17 сохраняются.
