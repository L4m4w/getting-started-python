# 22A — GitHub HTTP transport

Ты — исполнитель 22A. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
22B работает параллельно; других агентов не запускай. Прочитай AGENTS.md,
локальный run-tests skill, [общий контракт 22](22-github-pr-transport.md)
как контекст (не выполнять целиком),
[общий интерфейс](../design/22-pr-transport-interface.md),
[wave 28](../handoffs/coordination-wave-28.md), wave 26/27,
PrTransport/PrRef и `_pr_search_key`/`_verify_pr` из актуального кода.

Твоя часть: stdlib GitHub REST `GitHubPrTransport` с pure/lazy constructor,
injectable HTTP/token provider, search/create/get по закреплённому
интерфейсу. Полная fresh pagination PR/files, строгая проверка ответов,
repo/head/body/files/status, draft-only create, отсутствие HTTP retries
POST, запрет credentials на чужие hosts/redirects. Real credentials
не читать. Ошибки не превращать в []/ложную полноту; body/digest проверять
до POST. Читаемый create number вернуть до verification GET, чтобы B
мог его сохранить. Не изобретать fields из spec вместо server response.

Только read-only публичные официальные docs.github.com разрешены для
схем/endpoints/pagination/errors; сохранить URL/дату/использованные поля.
GitHub repository API/аккаунты, SUT и все реальные writes запрещены.
Синтетические ответы не выдавать за live fixtures.

Write scope строго:
- новый `infrastructure/workflow/github.py`;
- новый `tests/unit/test_workflow_github.py`;
- новый `test_data/consts/workflow_github.py`;
- новый `docs/qa-workflow/design/22a-github-http-transport.md`;
- новый `docs/qa-workflow/handoffs/22a-github-http-transport.md`;
- новый `artifacts/workflow-github/22a-<UTC>/`.

Adapters/orchestrator/CLI, старые tests/consts, общий интерфейс и каталоги
не менять. Нет нужды ждать B: создавай spec fixtures с body_text по
общему контракту. Требуемые изменения протокола — конкретный blocker
координатору, не самостоятельная правка shared files.

Регрессии: HTTP GET/POST counters, zero calls на constructor; пагинация
полная/оборванная/повторная/посторонняя; malformed data; body/files/head
conflict; closed/merged/non-draft; null/empty/nonempty body; strict repo/
redirect boundaries; timeout/нечитаемый create после fake remote write;
POST ровно один, zero verification GET внутри create. Без живой сети.
Выполни свой regression-файл; общий unit/collection/B-тесты не дублируй.
Basetemp/cache/JUnit/stores только свои. Общую CLI integration проверяет
C после приёмки A/B; новые public API/HTTP exception contract опиши
в handoff для B/C и каталога, который обновит C.

Baseline — accepted-inputs wave 26; собственные before/after SHA и peer
изменения B отдельно. 19 protected SHA из 20R2 списка и 15 API sources
manifest run-ni_5bvnc неизменны. Все чужие изменения сохранить.
Никаких live PR/TestOps/SUT/API/UI/Docker/Gradle/CI, Git commit/push/fetch/
checkout/reset, установки gh/deps, реальных tokens/.env. Рабочий workflow,
accepted execution state и исторические evidence read-only; исключение
сети только официальные docs выше. Handoff ready/blocked с SHA/командами/
exit/counts/evidence/HTTP counters/границами. После отчёта остановись:
координатор принимает A/B до выдачи зависимой C. Весь 22/MVP не принимать.
