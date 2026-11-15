# Разработка QA workflow

**Весь этап 22 (A/B/AR/C) принят offline.**
[Wave 31](handoffs/coordination-wave-31.md),
[сводный handoff](handoffs/22-github-pr-transport.md): собственные
711 unit passed, full-chain fake repeat 31/31. QA-пакет актуализирован
координатором. Следующий шаг — отдельное разрешение локальных commits
в двух изолированных worktree, без push/PR. Live GitHub/MVP ещё не завершены.
Исходные checkout dirty, рабочий workflow initialized. Ниже история.

**22AR принят, A/B приняты совместно; можно запускать 22C.**
[Wave 30](handoffs/coordination-wave-30.md): собственные 161 passed;
обе отрицательные пробы больше не дают ложного verified.
Следующий шаг — [22C: CLI/integration](agent-tasks/22c-cli-and-http-integration.md).
Весь 22 и live Git/PR ещё не завершены; A/B и 19A2 повторять не нужно.
Ниже предыдущие статусы.

**22A/B проверены: B принят, A требует 22AR; C пока не запускать.**
[Wave 29](handoffs/coordination-wave-29.md): собственные 218 passed и
fake repeat 31/31, но inconsistent count и смена head во время files
дают ложный verified в настоящем A+B на fake HTTP.
Следующее поручение — [22AR](agent-tasks/22ar-github-snapshot-corrections.md).
После его приёмки координатор передаст C. B повторять не нужно.

**22 разделён для параллельной работы:**
[22A — HTTP transport](agent-tasks/22a-github-http-transport.md) и
[22B — body/checkpoints](agent-tasks/22b-pr-body-and-checkpoints.md)
стартуют независимо; [22C — CLI/integration](agent-tasks/22c-cli-and-http-integration.md)
идёт после их приёмки координатором. [Организация wave 28](handoffs/coordination-wave-28.md).
Единое полное 22 не дублировать; агентов запускает пользователь.

**19A2-QA/APP приняты как локальные Git/PR-пакеты:**
[wave 27](handoffs/coordination-wave-27.md). QA — 184 исходных файла,
APP — 2, snapshots/SHA совпали; staged пуст, Git writes не выполнялись.
Следующее поручение — [22: GitHub PR transport/CLI wiring](agent-tasks/22-github-pr-transport.md)
с offline HTTP-проверками до будущей разрешённой публикации.
После него QA-пакет обновляет координатор; 19A2 повторять не нужно.
Live PR/идемпотентность и полный MVP остаются открытыми. Ниже история.

**21/21R/21R2 завершены и приняты в offline-границах.**
[Wave 26](handoffs/coordination-wave-26.md): собственные 99 passed,
проба parent→child больше не создаёт второй PR, fake repeat 31/31.
Следующие параллельные поручения — [19A2-QA](agent-tasks/19a2-qa-package-refresh.md)
и [19A2-APP](agent-tasks/19a2-app-package-refresh.md): актуализация локальных
Git/PR-пакетов. Запускает пользователь. Commit/push/PR не разрешены,
рабочий workflow initialized; live PR и полный MVP не завершены.
Далее исторические статусы.

**21R проверен: A/C приняты, общая приёмка остаётся открытой из-за P1
PR lineage.** [Wave 25](handoffs/coordination-wave-25.md): собственные
129 targeted passed, прежние probes проходят, но parent adoption +
child search [] допускает новый create. Следующее узкое поручение —
[21R2](agent-tasks/21r2-pr-lineage-deduplication.md). A/C повторять не нужно.
Пользователь запускает исполнителя; live Git/PR и полный MVP не завершены.
Ниже сохранены предыдущие статусы.

**21A/21B/21C завершены и проверены координатором; нужны исправления 21R.**
[Сводное ревью](handoffs/21-independent-workflow-review.md),
[решение wave 24](handoffs/coordination-wave-24.md): 12 групп findings,
включая повторный PR create и ослабление published gate.
Следующие независимые поручения: [21R-A](agent-tasks/21r-a-state-and-envelopes.md),
[21R-B](agent-tasks/21r-b-orchestration-and-recovery.md),
[21R-C](agent-tasks/21r-c-runbook-and-catalogue.md).
Исполнителей запускает пользователь; общая приёмка после трёх результатов.
Рабочий workflow initialized, live Git/PR и полный MVP остаются открытыми.
Дальше сохранены предыдущие статусы как история.

Задача 21 подготовлена для параллельного выполнения:
[21A — состояние/evidence](agent-tasks/21a-state-and-evidence-review.md),
[21B — эффекты/recovery](agent-tasks/21b-effects-and-recovery-review.md),
[21C — CLI/повтор](agent-tasks/21c-cli-and-repeat-review.md).
[Wave 23](handoffs/coordination-wave-23.md). Все три стартуют независимо;
общая приёмка координатором — после трёх отчётов.

**20 с исправлениями 20R2 завершён и принят как offline-реализация**:
[wave 22](handoffs/coordination-wave-22.md). Следующее поручение —
[21: независимое ревью и повтор workflow](agent-tasks/21-independent-workflow-review.md).
Полный MVP не завершён; Git/PR и live идемпотентность остаются открытыми.
Исторические остановки ниже сохраняются как ход работ.

20R проверен: старые пять проб проходят, но приёмка 20 остаётся открытой
из-за неполного evidence contract, PR head identity/provenance и checkpoints.
[Wave 21](handoffs/coordination-wave-21.md),
[20R2 — оставшиеся исправления](agent-tasks/20r2-evidence-and-pr-identity.md).
Независимая задача 21 пока не выдана; полный MVP не завершён.

20 реализован, но **пока не принят**: координатор воспроизвёл пять
дефектов, включая обход неизвестного PR create и слабую привязку evidence.
[Wave 20](handoffs/coordination-wave-20.md),
[корректирующее поручение 20R](agent-tasks/20r-orchestrator-corrections.md).
Поручение 21 — только после приёмки исправлений. Полный MVP не завершён.

19A/19B приняты как подготовка с уточнениями контракта:
[wave 19](handoffs/coordination-wave-19.md).
Подготовлено [поручение 20 — минимальный оркестратор](agent-tasks/20-orchestrator-implementation.md).
Оркестратор пока не реализован, полный MVP не завершён.

Следующая волна подготовлена, но ещё не выполнена:
[19A — локальный Git/PR-пакет](agent-tasks/19a-git-pr-preparation.md) и
[19B — контракт оркестратора](agent-tasks/19b-orchestrator-contract.md).
Порядок реализации, проверки повтора и оставшиеся границы:
[wave 18](handoffs/coordination-wave-18.md). Агентов запускает пользователь;
commit/push/PR не разрешены. Полный MVP остаётся незавершённым.

Целевой план: [архитектура и этапы](../plans/qa-workflow.md).
План первого сквозного прохода: [MVP](../plans/qa-workflow-mvp.md).

Задания для передачи исполнителям:
[промпты агентов и параллельные фазы](agent-tasks/README.md).

2026-11-15: **этап 16 завершён и принят**:
[launch 57316](https://allure.qa.guru/launch/57316), шесть passed,
согласованные bindings и свежий REST confirmed, persisted uploaded,
attempts=1. [Приёмка wave 13](handoffs/coordination-wave-13.md).
Следующее поручение — [17: ALLURE_ID и финальный execution](agent-tasks/17-bound-final-execution.md),
без новой публикации TestOps. Полный MVP ещё не завершён.

**17 завершён и принят**: новый execution `run-ni_5bvnc`, шесть passed,
исходные ALLURE_ID и bind-пакет проверены, cleanup/post-down приняты.
[Wave 15](handoffs/coordination-wave-15.md).
**18 завершён и принят**: финальный bind execution опубликован в
[launch 57317](https://allure.qa.guru/launch/57317), uploaded/confirmed,
attempts=1, шесть прежних case IDs без новых кейсов.
[Wave 17](handoffs/coordination-wave-17.md).
Остаются Git/PR, оркестратор/возобновление, сквозная идемпотентность
и оценка MVP. Commit/push/PR пока не разрешены.

Предыдущая приёмка: 15A/15B интегрированы координатором — явный REST verify,
строгий снимок и сверка результатов/bindings. Проверки: 233 unit passed,
248 collected, API-контракт неизменён. Непустой live launch пока не проверен;
внешних публикаций/PR нет. Следующий этап — отдельно разрешённая первая
публикация пилота и live verification:
[координация девятой волны](handoffs/coordination-wave-9.md).

После 07: реальный API baseline — 4 ожидаемых failed;
base + patch — 6 passed. Повторные GET и cleanup категорий подтверждены.
Итоговое независимое ревью 08 и ограничения сохранённого evidence:
[координация третьей волны](handoffs/coordination-wave-3.md).
TestOps и PR не опубликованы. Разделы ниже сохраняют историю предыдущих волн.

## Итерация 2026-11-14

Работа ведётся параллельно в независимых областях: спецификация и сценарии,
анализ API-фреймворка, манифесты harness. Основной агент собирает контекст,
интегрирует результаты и проверяет общее изменение.

Пилот: валидация переименования категории через публичный REST API.

| Артефакт | Назначение |
| --- | --- |
| [Обследование приложения](../plans/qa-workflow-discovery.md) | Репозиторий, исходное наблюдение и кандидат изменения |
| [Требование](pilots/category-update-validation/requirement.md) | Ожидаемое поведение и границы пилота |
| [Сценарии](pilots/category-update-validation/scenarios.md) | Тестовый план и трассировка к требованию |
| [Контекст](pilots/category-update-validation/context.json) | Восемь исходных файлов на фиксированном SHA, Git blob и SHA-256 |
| [Оценка API-фреймворка](api-framework-assessment.md) | Переиспользование, место тестов и путь воспроизведения |

Контекст содержит ссылки и контрольные суммы, а не эмбеддинги. Файлы читаются
из Git на указанном commit; `head_sha` пока отсутствует, поскольку изменение
приложения ещё не создано. Сбор контекста пока выполнен разовой командой,
автоматический обработчик MR/PR не реализован.

## Решения и ограничения

- Независимые задачи делегируются с отдельными областями файлов; общие
  изменения проверяются после интеграции. Это правило закреплено в AGENTS.md.
- Harness развивается на выполненных задачах. Первое улучшение — сохранять
  машинно-читаемый манифест настоящего тестового прогона вместе с Allure/JUnit.
  Реализовано в `tools/harness.py`; обработка ошибок и изоляция результатов
  проверяются шестью новыми unit-случаями. Независимое статическое ревью
  не выявило замечаний.
- Начальный локальный прогон до изменения harness: Python 3.13.15, pytest 9.1.1,
  27 unit-тестов passed, exit code 0; 36 тестов собрано без выполнения UI.
  Материалы: `artifacts/harness/run-mymv1gso/` (локальные, не в Git).
- `java -version` через системный PATH не нашёл Java runtime. Дополнительная
  проверка обнаружила Homebrew JDK 21.0.12.1:
  `/opt/homebrew/opt/openjdk@21/bin/java` и `javac`; оба успешно вызваны с
  `-version`. Для Gradle нужно явно выбрать этот JDK. Внутри PyCharm также
  есть JBR 25, но для пилота выбран требуемый проектом JDK 21.
  Позднее агент 01 выполнил Gradle 8.6 projects/compileJava успешно без правок
  сборки. Приложение не запускалось; воспроизведение пока не подтверждено.
- Docker CLI доступен (29.7.2); daemon и окружение не проверялись.
- Существующий учебный API-фреймворк требует ревью перед переиспользованием.
  Целевое размещение Python API-тестов в текущем проекте принято координатором,
  массовый перенос другого фреймворка не выполнялся.
- Доступ к TestOps и окружение приложения из конкретного SHA ещё не настроены.

## Проверка интеграции

После объединения изменений выполнены `sh tools/compile-tests.sh` и
`sh tools/run-tests.sh group unit`: collection — 42 теста, выполнение —
33 passed / 0 failed / 0 errors / 0 skipped, exit code 0.
Python 3.13.15, pytest 9.1.1, allure-pytest 2.16.2.
Материалы: `artifacts/harness/run-v_7e13gk/`, включая `manifest.json`,
`junit.xml` и `allure-results/`. Проверены локальные ссылки, контрольные
суммы восьми файлов контекста и `git diff --check`.

## Следующая контрольная точка

Решения ревью первой волны и интеграции Java harness:
[отчёт координатора](handoffs/coordination-wave-1.md).
Отчёты 03/04 уже найдены и проверены: контракт fixtures принят для разработки,
MockMvc baseline — 2 passed / 4 ожидаемых failed. 05/06 приняты:
минимальный fix `@Valid` дал 6 MockMvc passed; 6 API-сценариев подготовлены, 58 offline unit
passed; collection — 73 теста. Реальные API-сценарии ещё не выполнялись.
Решения, evidence и следующая передача:
[координация второй волны](handoffs/coordination-wave-2.md).

Эксперимент «до/после» gateway завершён в 05; сохранность данных на
приложении — к 07. MockMvc с подменой downstream-клиента может подтвердить
HTTP-валидацию, но не сохранность данных в БД.
