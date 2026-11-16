# 19A2-QA — актуализировать локальный Git/PR-пакет QA

Ты — исполнитель 19A2-QA. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Других агентов не запускай. Независимый 19A2-APP готовит приложение;
работай параллельно в своей области. Это подготовка, не Git-публикация.

Прочитай AGENTS.md, [wave 26](../handoffs/coordination-wave-26.md),
[решения 19A из wave 19](../handoffs/coordination-wave-19.md), старый
handoff 19A, handoff 21R2, MVP-план, runbook/каталог workflow и TestOps.
21/21R/21R2 приняты как offline review/corrections; не запускать их
повторно. Исторический пакет 19A не является актуальным составом.

## Область записи

Только новый `docs/qa-workflow/handoffs/19a2-qa-package-refresh.md` и
новый `artifacts/git-pr/19a2-qa-<UTC>/`. Все исходники, docs/индексы,
Git index/ветки/config/remotes, workflow/TestOps/execution state и старые
evidence read-only. Приложение не пакетировать: это задача APP.

## Результат

1. Read-only Git-инвентаризация QA: HEAD/ветка, tracked/untracked/staged,
   локальные refs/base. План узкого QA draft PR от `MVP_workflow` и
   отдельной feature-ветки уже принят wave 19. Не предлагать повторно
   выбор master/MVP_workflow; локальные refs не выдавать за свежий сервер.
2. Явный полный allowlist кандидатов к публикации, включая untracked
   workflow/CLI/tests/consts, API/TestOps/harness и документацию. По каждому
   изменённому/новому файлу: включить/исключить/needs_decision с причиной.
   Process docs — отдельный логический commit внутри того же QA PR
   (решение wave 19), не отдельный произвольно выбранный docs PR.
3. Сохранить snapshot выбранных файлов, SHA-256 по repo/path, patch для
   tracked и учёт untracked; before/after recheck. Никаких секретов,
   `.env`, `.venv`, build/cache, всего artifacts или массовых логов.
   Сканировать только точный allowlist; не выводить найденные значения.
   Исторические текстовые handoff сохранять, ссылки проверить. Сырые
   logs не включать автоматически: исключения и недоступность локальных
   evidence из удалённого PR явно описать. Не копировать весь checkout.
4. Найти runtime/review зависимости, не попадающие в Git: pinned baseline
   record с review-document SHA, manifests/source copies/package/intents,
   Java/API/TestOps evidence. Составить список «есть в PR / локально
   недоступно / требует отдельного будущего решения», не менять registry,
   исторические документы или пути ради самодостаточности пакета.
5. Отдельные `pr-title.txt`/`pr-body.md`: конкретное покрытие пилота,
   реализация offline workflow, проверки и пределы. 21R2 coordinator
   targeted и прежние 511 unit не смешивать; результаты брать по точным
   SHA/JUnit. 550 collected из 21R2 — не 550 passed. Сверить 15 API source
   SHA с run-ni_5bvnc, включить bindings/launch 57317 и ограничения
   evidence 07, provenance 10/17, close-аудита wave 17.
6. Конкретный план будущих commits/push/draft PR (НЕ выполнять), точные
   allowlists по логическим commits, base/ветка, проверки. Будущий body
   через `--body-file`; не выдумывать head SHA, cross-links или PR URL.
   Старые run остаются base+patch/dirty, будущий commit не становится
   provenance исторического execution. Реальный workflow initialized.
7. Зафиксировать отдельный открытый пункт: live PR transport в workflow
   CLI отсутствует. Ручная публикация через gh сама по себе не доказывает
   live идемпотентность оркестратора; подготовить список зависимостей и
   конкретных следующих решений, не реализовывать транспорт в этой задаче.

## Проверки и границы

Только offline: snapshot integrity, полнота untracked, локальные ссылки,
secret scan allowlist без значений, diff --check. Код не меняется:
unit/collection заново не повторять; проверить совпадение текущих SHA с
координаторским accepted manifest из wave 26 и указывать источник каждого
измерения. Если drift — конкретный blocker, не править реализацию.
19 protected SHA и 15 API source SHA сверить до/после. Все чужие
незакоммиченные изменения сохранить, staged-состояние не менять.
Никаких сети/fetch/API/UI/SUT/Docker/Gradle/CI/TestOps/PR writes,
commit/push/checkout/reset, чтения/копирования секретов.
Handoff: ready/blocked/needs_decision, версии, точный состав, checks/
exit/evidence, PR title/body files, оставшиеся решения и публикационный
план. После отчёта остановись; интеграция двух пакетов и запрос разрешения
Git writes после конкретной подготовки — координатору.
