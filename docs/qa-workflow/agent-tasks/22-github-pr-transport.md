# 22 — GitHub PR transport и CLI wiring без реальных публикаций

**Поручение разделено по запросу пользователя.** Запускать
[22A](22a-github-http-transport.md) и [22B](22b-pr-body-and-checkpoints.md)
параллельно; [22C](22c-cli-and-http-integration.md) — после их
документированной приёмки координатором. [Wave 28](../handoffs/coordination-wave-28.md),
[общий интерфейс](../design/22-pr-transport-interface.md).
Ниже общий контракт покрытия, не отдельная четвёртая задача.
Целиком вместе с A/B/C это поручение не выполнять. Общую приёмку и
сводный handoff 22 оформляет координатор после всех частей.

Ты — исполнитель 22 QA workflow Niffler. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Других агентов не запускай. Прочитай AGENTS.md, локальный run-tests skill,
[wave 27](../handoffs/coordination-wave-27.md), wave 19/26, handoff 21R2,
19A2-QA/APP и runbook/каталог workflow. 21/21R2 offline приняты;
локальные Git/PR-пакеты 19A2 приняты. Git writes НЕ разрешены.

## Зачем

Production CLI пока не поставляет PrTransport, `gh` локально не найден.
Ручной draft PR не докажет live-идемпотентность оркестратора. Реализуй
минимальный GitHub REST transport на stdlib + явное CLI wiring, чтобы
будущая разрешённая публикация проходила через существующие durable
intents и recovery. Не устанавливать gh/новые зависимости и не делать
реальных GitHub-запросов к репозиториям/аккаунтам.

Допускается только read-only чтение публичной официальной документации
GitHub REST (docs.github.com) для точных схем/endpoints/pagination/errors.
Сохрани URL/дату и фактически использованные поля в design/evidence,
не выдавай синтетические fixtures за живые ответы. Приложение/SUT,
GitHub repository API, TestOps и любые remote writes запрещены.

## Реализация

1. `PrTransport.search/create/get`: полноценная HTTP-инъекция для offline
   tests; сетевой клиент создаёт запрос только при явном разрешённом
   вызове CLI. Default transport по-прежнему отключён. Явный глобальный
   флаг выбора transport; search/get/reconcile/resume требуют --online,
   create дополнительно --execute. Ни status/init/doctor/prepare, ни
   отсутствие флагов не читают реальные credentials и не вызывают сеть.
2. Только GitHub.com и api.github.com; строгая нормализация известных
   repo identities owner/repo. Не передавать credentials на произвольные
   hosts/redirects. Token только из env при разрешённом вызове, без
   печати/argv/state/evidence. Для тестов только фиктивные credentials;
   не читать пользовательские .env/ключи/токены и не выполнять auth login.
3. Fresh полный search по repo/head/base, с пагинацией и проверкой полноты;
   targeted get известного number; получение реальных body/head SHA/
   полного состава PR files для exact validation. Частичные, повреждённые,
   неоднозначные ответы не становятся пустым «ничего нет». Closed/merged/
   non-draft и чужой repo/head/spec не выдавать за нужный draft PR.
   Создавать только draft. Неподтверждённое соответствие => blocked.
4. Разрешить существующий разрыв body-контракта: prepare сейчас хранит
   только body_sha256, PrSpec не содержит текста/пути, а remote create
   требует body. Зафиксируй воспроизводимый источник body, привязанный
   digest к spec/intent; изменённый/пропавший body блокирует до POST.
   Не реконструировать body по текущему произвольному файлу после crash.
   Согласовать семантику absent/null/empty body с exact validation.
5. Durable intent до POST; timeout/ошибка/нечитаемый ответ после dispatch
   => unknown, никаких автоматических HTTP retries записи. Read failures
   контролируются без raw exceptions/секретов в логе. Number читаемого
   create сохраняется до следующих verification reads; lost-save/crash
   не даёт второй create. 404/[] после unknown и любой известный lineage
   effect не разрешают recreate. Сохранять guards 21R2, commit/tree и
   app/tests required, не обходить фазные gates ради теста wiring.
6. Реальный CLI boundary проверить subprocess через локальный fake HTTP
   backend/подмену без выхода в сеть. Не добавлять production-флаг,
   позволяющий произвольные hosts или отключение guards ради тестов.
   Отделить реальные parser/dispatch проверки от programmatic simulations.

## Write scope

- новый `infrastructure/workflow/github.py`;
- `infrastructure/workflow/adapters.py`, `orchestrator.py`,
  `tools/workflow.py` — только нужный transport/body/CLI контракт;
- новые `tests/unit/test_workflow_github.py`,
  `tests/unit/test_workflow_github_cli.py`,
  `test_data/consts/workflow_github.py`;
- `knowledge/components/workflow.md`, `knowledge/components/consts.md`,
  `knowledge/integrations/qa-workflow.md`;
- новый `docs/qa-workflow/design/22-github-pr-transport.md`,
  `docs/qa-workflow/handoffs/22-github-pr-transport.md`,
  `artifacts/workflow-github/22-<UTC>/`.

State/envelopes/contracts/index/locks и старые tests/fixtures/consts
read-only. Если совместимость требует иного source scope, зафиксируй
конкретную зависимость вместо неявного расширения. Не менять исторические
handoff, пакеты 19A2 и accepted evidence. README/plans остаются координатору.

## Проверки и handoff

Meaningful offline tests: полная/частичная pagination; missing/foreign/
closed/merged PR; body/hash/files/head mismatch; malformed create result;
timeout после POST с simulate remote effect; crash после читаемого number
до verification; unknown+[]; known number+404/error; lineage two-hop;
повтор успешного create/adoption даёт ноль новых POST; default/no flags/
missing credential => ноль HTTP вызовов. Проверить app/tests.
Считать HTTP GET/POST и runner dispatch, не только return outcome.

Выполнить свои новые regression-файлы, `test_workflow_intents.py`,
`test_workflow_21r_b.py`, `test_workflow_21r2.py`,
`test_workflow_20r2.py::TestR2GitHeadSeparation`, full-chain fake repeat.
Все stores/basetemp/cache/JUnit внутри своего evidence. Полный unit/
collection без новой конкретной причины не повторять. Зафиксировать
точные before/after source/doc SHA; baseline — accepted-inputs из wave 26.
19 protected SHA и 15 API sources manifest run-ni_5bvnc неизменны.

Никаких live PR/TestOps/SUT/API/UI/Docker/Gradle/CI, Git commit/push/
fetch/checkout/reset, установки gh/зависимостей, доступа к реальным
credentials. Исключение сети только для публичных официальных docs,
указанное выше. Сохрани все чужие незакоммиченные изменения; рабочий
workflow initialized, accepted execution state read-only.
Handoff ready/blocked: design, exact SHA, команды/exit/counts/evidence,
HTTP counters, CLI vs programmatic, документационные источники и
непроверенные live-схемы. Готовый transport ещё не разрешает live writes.
После отчёта остановись: координатор принимает 22, инкрементально обновляет
QA-пакет и только затем готовит отдельное разрешение commit/push/draft PR.
