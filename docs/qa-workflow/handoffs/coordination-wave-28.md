# Разделение 22: transport и checkpoints параллельно, затем CLI

Дата: 2026-11-16. По запросу пользователя 22 разделён на A/B/C.
Это организация следующего этапа, не отчёт о реализации. Приёмка
19A2 из wave 27 и 21/21R2 из wave 26 сохраняется.

| Поручение | Задача | Область source | Когда запускать |
| --- | --- | --- | --- |
| [22A](../agent-tasks/22a-github-http-transport.md) | GitHub HTTP search/create/get, pagination, response/body validation, HTTP errors | новый github.py, отдельные tests/consts | Сейчас, параллельно с B |
| [22B](../agent-tasks/22b-pr-body-and-checkpoints.md) | Durable body payload и запись читаемого number до verification, crash/recovery | adapters.py, orchestrator.py, отдельные tests/consts | Сейчас, параллельно с A |
| [22C](../agent-tasks/22c-cli-and-http-integration.md) | CLI wiring, subprocess/fake-HTTP integration и общая документация | tools/workflow.py, отдельные tests/consts, каталоги/runbook | После документированной приёмки A/B координатором |

[Общий интерфейс](../design/22-pr-transport-interface.md) закреплён
координатором до параллельной реализации: GitHubPrTransport с lazy
constructor и search/create/get, body_text/body_sha256, нормализация
нового empty body, создание ref до verification reads. A/B читают
один контракт и не редактируют его независимо. При необходимой смене
интерфейса — конкретное решение координатора перед зависимой работой.

Прежнее [единое поручение 22](../agent-tasks/22-github-pr-transport.md)
сохраняет общий контракт покрытия. Не запускать отдельного исполнителя
на всё 22 вместе с A/B/C. Единого писателя общего исходного файла нет:
A не меняет adapters/orchestrator, B не меняет github.py, C не меняет
их реализацию. Общую документацию пишет только C после готовых inputs.

Ожидаемые handoff:
- `22a-github-http-transport.md`;
- `22b-pr-body-and-checkpoints.md`;
- `22c-cli-and-http-integration.md`.

Design/evidence/stores/basetemp/cache/JUnit у каждого отдельные. A
запускает свои HTTP tests, B — payload/crash и назначенные existing
regressions; полную группу никто без причины не дублирует. C проверяет
новые A/B tests и стык с реальным CLI, не выдавая stub всего transport
за интеграцию. Общая окончательная приёмка — координатору после C.
Сводный handoff `22-github-pr-transport.md` в handoffs резервируется
координатору, части его не пишут.

Только A может читать публичную официальную docs.github.com для API
схем, как разрешено исходным 22; никаких repository API/реальных tokens/
live writes. B/C работают без сети. Git/SUT/TestOps/Docker/CI и прочие
запреты исходного 22 сохраняются. Реализация ещё не начата координатором;
агентов запускает пользователь, новых агентов координатор не запускал.

Координатор создал только поручения/общий design/организационный handoff,
обновил текущие индексы и MVP. Код и accepted/protected state неизменны.
Пакеты 19A2 и frozen coordinator snapshots не переписаны; новая/изменённая
процессная документация — ожидаемая дельта для инкрементального обновления
QA-пакета после приёмки всего 22, не drift исполняемого кода.
Полный MVP и реальные Git heads/PR/live идемпотентность остаются открытыми.
