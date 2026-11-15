# Итоги 21A/21B/21C и исправления 21R

Дата: 2026-11-15. Все три результата обнаружены, сверены и приняты как
выполненное независимое ревью. [Сводное решение](21-independent-workflow-review.md):
**needs_corrections**, 12 групп findings. Live PR и обновление финального
Git/PR-пакета ждут исправлений и общей приёмки; полный MVP не завершён.
Прежние handoff и приёмка 20/20R2 сохранены исторически.

Координатор повторил семь scripts в собственном isolated evidence:
`artifacts/workflow-review/coordinator-21-review-20261115/`.
Подтверждены duplicate create (2 remote PR), schema/publication gaps,
recovery dead-ends и остальные findings. Fake full-chain repeat 31/31,
concurrency/recovery 24/24; это simulation. 148 passed пересчитаны по
JUnit ревьюеров, pytest координатор не повторял. 13 accepted inputs,
19 protected files и 15 API sources совпали до/после; рабочий workflow
остался initialized. Оба HEAD прежние, checkout dirty.

Следующая параллельная волна для ручного запуска пользователем:

| Задание | Область записи |
| --- | --- |
| [21R-A](../agent-tasks/21r-a-state-and-envelopes.md) | state.py, envelopes.py, отдельные regression/consts и свой handoff/evidence |
| [21R-B](../agent-tasks/21r-b-orchestration-and-recovery.md) | orchestrator.py, отдельные regression/consts и свой handoff/evidence |
| [21R-C](../agent-tasks/21r-c-runbook-and-catalogue.md) | runbook и каталог workflow, свой handoff/evidence |

Shared fixtures/constants, adapters/contracts/index/locks, CLI и прочие
файлы не менять параллельно без нового решения координатора. Все 21R
читают сводный handoff с обязательными уточнениями. Common catalogue
обновляет только C, A/B передают ему изменения API; финальную сверку
каталога с объединённым кодом выполняет координатор после всех трёх.
Записи новых отдельных test constants в `knowledge/components/consts.md`
интегрирует координатор при той же общей приёмке, не параллельные писатели.

Не запускать прежние 21A/B/C повторно и не запускать единое поручение 21.
Новых агентов координатор не запускал. Во всей 21R сохраняются offline
границы, запрет Git writes/live effects и сохранение исторического evidence.
Промпты передаются в чат. Общая проверка и приёмка — после трёх handoff;
никакая отдельная часть не разрешает зависимый Git/PR этап.
