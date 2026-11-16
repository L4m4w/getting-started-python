# 16A — локальная проверка execution и подготовка пакета

Ты — исполнитель 16A. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Работай самостоятельно, других агентов не запускай.

Прочитай `AGENTS.md`, `knowledge/integrations/testops.md`,
`docs/qa-workflow/handoffs/coordination-wave-9.md`,
`docs/qa-workflow/handoffs/coordination-wave-10.md`,
`docs/qa-workflow/handoffs/10-api-evidence-replay.md` и
`docs/qa-workflow/agent-tasks/16-testops-first-publication.md`.
Последний файл — общий контекст; выполняй только локальную часть,
ограниченную этим поручением. Сетевую подготовку параллельно делает 16B.

Цель: передать координатору проверенный **isolate-кандидат** fix execution
`run-5tsmzg1d`. Окончательный выбор isolate/bind делается после отчёта 16B.
Подготовка isolate локально не разрешает его отправку.

Разрешённая запись:

- `artifacts/testops/run-5tsmzg1d/` — ты единственный писатель до передачи;
- новый уникальный `artifacts/testops-preflight/16a-<UTC>/`;
- `docs/qa-workflow/handoffs/16a-testops-package.md`.

Не меняй README, общие документы/код, приложение, API-контракт, другие
execution state и исторические evidence/handoffs. Сохраняй все чужие
незакоммиченные изменения. Не переключай/не сбрасывай checkout.
Сеть, TestOps create/upload/close/resolve, API/UI, Docker/Gradle,
commit/push/PR запрещены. Не читай секреты ради этой задачи.

Порядок работы:

1. Проверь, не появился ли уже отчёт 16A/16C или следы внешней попытки.
   Прочитай inventory всех локальных TestOps state без их изменения:
   execution, endpoint/project, launch, status/attempts, package digest.
   При повреждении state или признаках попытки выбранного execution
   останови пересборку; не удаляй state/lock и не создавай обходной execution.
2. Проверь source `artifacts/harness/run-5tsmzg1d/allure-results/`,
   manifest/JUnit, шесть CAT-UPD-VAL-001–006 со статусом passed,
   UUID/mapping/attachments, отсутствие посторонних результатов,
   все 15 SHA api-contract-v1 и связь с base+patch по evidence
   `artifacts/integration/catupdval-rerun/`. Baseline не пакетируй.
   Исходные результаты и вложения проверь на секреты без вывода их содержимого.
   При находке остановись, исторические файлы не редактируй.
3. До изменений сохрани исходный state и старый пакет с контрольными
   суммами в собственный evidence. На момент подготовки координатором
   state был schema 1, pending, attempts=0, launch=null; старый пакет
   не содержал input_sha256/assignments_sha256. Перепроверь эти условия.
4. Через штатные CLI/ExecutionLock обнови plan/schema и собери isolate:

   ```sh
   sh tools/run-testops.sh plan --execution run-5tsmzg1d --results artifacts/harness/run-5tsmzg1d/allure-results --endpoint https://allure.qa.guru --project-id 5444
   sh tools/run-testops.sh package --execution run-5tsmzg1d --mode isolate
   ```

   Проверь эффективные значения и записанный endpoint/project:
   exported env не должен незаметно изменить целевой проект.
   Пакет проверяй существующими integrity-функциями без внешних вызовов.
   Не присваивай case IDs и не применяй recovery API.
5. Сохрани execution/source/manifest identity, input/assignments/package
   SHA-256, mode, число файлов, таблицу UUID → scenario → status,
   SHA state до/после, команды и exit codes. Отдельно укажи, что проект
   live не проверялся, isolate остаётся кандидатом, публикации не было.
6. После успешной подготовки прекрати запись в общий execution state:
   дальнейшие изменения только после новой явной передачи владения.
   Если нужен ремонт общего кода, верни конкретный блокер координатору.

Результат: handoff ready / blocked / needs_decision с evidence и
ограничениями. Ready означает готовность локального кандидата,
не разрешение публикации. Выполни `git diff --check`; подходящие проверки
целостности достаточны, unit/API/UI без изменения реализации не запускай.

Не пересказывай старые 233 unit / 248 collected как свои проверки.
Передай результат координатору для объединения с 16B.
