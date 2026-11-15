# 19A — локальная подготовка Git/PR

Ты — исполнитель 19A. Подготовь конкретный локальный пакет для будущего
Git/PR, без commit/push/создания PR. Других агентов не запускай.

Рабочая папка: `/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Приложение: `/Users/zenalark/PycharmProjects/Test-java/niffler-py-st3`.
Это два отдельных Git-репозитория. Сохрани все незакоммиченные изменения;
не меняй index, ветки, checkout, Git config и remotes.

Прочитай AGENTS.md, docs/plans/qa-workflow-mvp.md,
docs/qa-workflow/handoffs/coordination-wave-15.md,
docs/qa-workflow/handoffs/coordination-wave-17.md,
docs/qa-workflow/handoffs/coordination-wave-18.md,
docs/qa-workflow/handoffs/08-final-review.md и относящиеся к проверяемым
файлам разделы knowledge. В приложении проверь применимые AGENTS.md.

Разрешённая запись — только:
- `docs/qa-workflow/handoffs/19a-git-pr-preparation.md`;
- новый каталог `artifacts/git-pr/19a-<UTC>/`.
19B параллельно готовит контракт; его файлы и общие индексы не редактируй.

Задача:
1. Read-only Git-инвентаризация обоих репозиториев: текущие HEAD/ветка,
   staged/unstaged/untracked, предполагаемые target/base и происхождение
   этих выводов. Не выводи credentials в URL. Сети для этой задачи не нужно;
   локальные remote refs не выдавай за свежую серверную картину.
2. Предложи состав изменений отдельно для приложения и QA-проекта:
   включить/исключить/требует решения с причинами. Учти новые untracked
   исходники: обычный git diff их не показывает. Не включай .env,
   credentials, artifacts, локальные логи и build-каталоги. Исторические
   versioned handoffs не удаляй и не исправляй. Production fix остаётся
   только @Valid у request body updateCategory; Java-регрессию выдели явно.
3. Сохрани allowlist, безопасные patch/source snapshots и SHA-256
   выбранных файлов с repo/path, включая untracked. Не копируй весь checkout
   или весь artifacts; проверь выбранные материалы на секреты без печати
   найденных значений. Перед завершением перепроверь снимок на изменение.
4. Подготовь отдельные title/body для предлагаемых draft PR приложения
   и автотестов либо обоснуй иной состав. Укажи покрытие, red/green,
   run-ni_5bvnc, launch 57317, ограничения evidence 07 и provenance 10/17,
   ссылку между изменениями и pending поля. Не выдумывай head SHA/PR URL.
   Успех API/TestOps не закрывает MVP.
5. Сопоставь принятые source SHA с файлами, предлагаемыми к публикации.
   Отдельно перечисли проверки, которые потребуются после будущих правок
   оркестратора и фиксации commit. Dirty snapshot digest не является
   immutable Git head; будущие commits не превращают старый прогон в новый.
6. Подготовь конкретный план будущих commit/push/draft PR с точными
   репозиториями, составом, предлагаемыми ветками и проверками. Команды
   только запиши как план, не исполняй. Фактически неизвестные target,
   владение репозиторием или доступ перечисли точно, без лишних согласований.

Не запускай API/UI, Docker/Gradle, CI, TestOps, commit/push/PR.
Старые evidence и executions/state неизменяемы. Источники не исправляй:
обнаруженные проблемы передай координатору с конкретными файлами.

Проверки: git diff --check обоих репозиториев, целостность нового пакета,
полнота выбранных untracked, ссылки и отсутствие секретов в новых файлах.
Unit/collection не повторяй для документационной подготовки.
Handoff: ready/blocked/needs_decision, версии входов, изменённые файлы,
команды/exit codes, evidence, собственные проверки отдельно от исторических,
ограничения и предложения для координатора. Пакет предварительный:
перед публикацией после реализации оркестратора его нужно актуализировать.
