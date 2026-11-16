# 19A2-APP — актуализировать локальный Git/PR-пакет приложения

Ты — исполнитель 19A2-APP. Папка QA-документов:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Приложение: `/Users/zenalark/PycharmProjects/Test-java/niffler-py-st3`.
Других агентов не запускай. 19A2-QA параллельно готовит QA-пакет;
не трогай его область. Это локальная подготовка без публикации.

Прочитай применимые AGENTS.md, [wave 26](../handoffs/coordination-wave-26.md),
решения 19A из wave 19, старый handoff 19A, wave 17 и финальные
requirement/scenarios/mapping пилота. 21R2 offline принят; его исходники
не проверять повторно и не менять.

Write scope: только новый
`docs/qa-workflow/handoffs/19a2-app-package-refresh.md` и новый
`artifacts/git-pr/19a2-app-<UTC>/` внутри QA. Приложение read-only.
Никаких изменений Git index/веток/config/remotes/checkout обоих репозиториев.

1. Read-only Git-инвентаризация приложения: текущие HEAD/ветка,
   staged/unstaged/untracked, локальный base/ref (не свежий сервер).
   Состав принят: production fix только `@Valid` у request body
   updateCategory + Java regression `CategoriesControllerValidationTest`.
   Base main; feature-ветка — предложение, не реально созданная ветка.
2. Новый allowlist двух файлов, snapshot и SHA-256, tracked patch и
   полный учёт untracked test. Сверить с прежним принятым patch
   `04eb4c874139610869793f0c72843b1a9cb338832973697cf56e25b7ba87937e`
   и Java manifest run-36tzwapr; при реальном drift — handoff с точными
   различиями, без исправления приложения/истории. Не включать build/
   caches/logs/.env/secrets/артефакты всего checkout.
3. `pr-title.txt`, `pr-body.md`: дефект и поведение после fix, отдельно
   Java regression, исторические baseline/head и API run-ni_5bvnc,
   launch 57317. Явно указать base+patch вместо immutable head; не
   заявлять, что исторический прогон выполнялся из будущего commit/PR.
   Взаимная ссылка QA PR pending до появления реального URL.
4. Конкретный будущий план commit/push/draft PR, точные пути/ветка/base,
   checks и body-file. Только записать команды. Обозначить необходимость
   будущей read-only серверной проверки base/прав, неизвестного исхода
   create/дедупликации и сохранения remote PR number до повторов.
   Не запрашивать новые согласования в этом read-only задании.

Проверки: before/after snapshot SHA против checkout, отсутствие новых
неучтённых файлов приложения, secret scan выбранного allowlist без
вывода значений, diff --check обоих репозиториев. Unit/Java/collection
не повторять: код не меняется, используются принятые исторические evidence.
Сверить неизменность 19 protected SHA по списку 20R2 и 15 API source SHA
manifest run-ni_5bvnc (read-only). Сохранять все чужие изменения.
Никаких сети/fetch/SUT/API/UI/Docker/Gradle/CI/TestOps/PR writes,
Git commit/push/checkout/reset или чтения/копирования секретов.
Handoff ready/blocked/needs_decision: точные SHA/состав, checks/exit/
evidence, title/body paths, публикационный план и ограничения.
После отчёта остановиться: общая приёмка QA+APP и будущее разрешение
Git writes — координатору. Полный MVP не объявлять завершённым.
