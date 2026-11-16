# 22C — design: CLI wiring `--pr-transport {none,github}` и offline-интеграция

Дата: 2026-11-16. Реализация — `tools/workflow.py` (только wiring);
принятые 22A/22AR (`infrastructure/workflow/github.py`) и 22B
(`orchestrator.py`, `adapters.py`, `state.py`) не изменялись.
Статус проверки: только offline fake-HTTP/git регрессии и
subprocess-прогоны production CLI; live GitHub repository/API вызовы,
реальные токены и Git writes не выполнялись.

## Изменение CLI

Глобальный аргумент `--pr-transport {none,github}` добавлен на уровень
top-level parser рядом с `--store-dir` и `--workflow-id`: он
обрабатывается **до** subcommand и наследуется всеми действиями.
Значение по умолчанию — `none`: поведение без флага неизменно
(`pr search`/`pr create` отвечают `WorkflowPermissionError` → exit 77
«no PR transport configured»).

```python
def _orchestrator(options):
    pr_transports = None
    if options.pr_transport == "github" and _needs_pr_transport(options):
        from infrastructure.workflow.github import GitHubPrTransport
        transport = GitHubPrTransport()
        pr_transports = {"app": transport, "tests": transport}
    return orch.Orchestrator(ROOT, store_dir=options.store_dir,
                             pr_transports=pr_transports)
```

`_needs_pr_transport` ограничивает wiring командами, которые способны
дойти до вызова транспорта: `pr create`, `pr search`, `reconcile`,
`resume`. На `status`, `init`, `doctor`, `accept`, `check`, executions,
TestOps и `pr prepare` модуль `github` не импортируется и объект не
строится — выбранный транспорт не является разрешением, и ни одна ранняя
команда не может спровоцировать credential-чтение или HTTP.

Импорт и конструкция ленивы и чисты: `GitHubPrTransport()` не читает
env, не трогает filesystem и не делает запросов; default-провайдер
`EnvGitHubToken` читает `GITHUB_TOKEN` только при построении
auth-заголовков внутри уже авторизованного `_request`. Один объект
транспорта передаётся в обе PR-роли (`app` и `tests`), как того требует
интерфейс `Orchestrator(pr_transports={...})`; role-разрешение идёт
через существующий `_pr_transport(role)` без изменений.

## Guard-матрица (без изменений в orchestrator)

| Команда | --pr-transport github | --online | --execute | Эффект |
| --- | --- | --- | --- | --- |
| status/init/doctor/pr prepare/прочие | да | — | — | транспорт не конструируется; 0 HTTP, 0 credential |
| reconcile/resume | да | нет | — | транспорт конструируется (без I/O); `pr.create` intent → `kept`; 0 HTTP |
| pr search | да | нет | — | 77; 0 HTTP, 0 credential |
| pr create | да | нет | любой | 77 «needs --execute and --online»; 0 HTTP |
| pr create | нет (default none) | да | да | 77 «no PR transport»; 0 HTTP |
| pr create | да | да | да | search → один POST → durable number → `get` detail→files→detail → verified/created |
| pr create | да | да | да, без `GITHUB_TOKEN` | `GitHubAuthError` до первого запроса → controlled 69; 1 попытка credential, 0 HTTP |

`--execute` без `--online` не производит POST — проверено subprocess-ом.
`--body <file>` остаётся публичным флагом и по-прежнему передаётся в
`pr_prepare(body_path=...)`: точные UTF-8 байты, durable snapshot в
`wf-*/payloads/`, редоказательство перед dispatch — механика 22B не
тронута.

## Offline-интеграционные проверки

Subprocess-уровень (`tests/unit/test_workflow_github_cli.py`):
настоящий `tools/workflow.py` запускается отдельным процессом против
temp-fixture (commit-head + clean-tests проект до `executed` через
`test_data.utils.workflow.Project`, записанные repo-relative пути
переведены в абсолютные и входные digests перепривязаны — сами входы не
изменены). Fake bootstrap — `sitecustomize.py` из
`test_data/consts/workflow_github_cli.SITECUSTOMIZE` через `PYTHONPATH`:
по JSON-сценарию (`WF_GH_FAKE_SCENARIO`) заменяет только http-слой
`UrllibHttp` и `GitReadAdapter` по зарегистрированным repo_path и ведёт
лог HTTP/credential/git-событий (`WF_GH_FAKE_LOG`). Endpoint остаётся
`api.github.com`; никакого флага произвольного endpoint или отключения
guard'ов в production не добавлено. Незнакомые checkout'ы получают
реальный адаптер с записью события.

Программный уровень: `_orchestrator` wiring (роли app/tests, отсутствие
wiring на ранних командах и при `none`, отсутствие I/O у конструктора —
provider/HTTP подсчитаны monkeypatch'ем) и полная цепочка
`Orchestrator → GitHubPrTransport → FakeHttp` с контролем порядка
GET list → POST → detail → files → detail.

Покрытие subprocess: порядок глобального флага (после action — exit 2,
недопустимое значение — exit 2), default `none`, ноль HTTP/credential
на ранних командах и без разрешающих флагов, отсутствие токена —
controlled результат с нулём HTTP, verified create на обеих ролях со
счётчиками 4 GET (list + files + 2 detail) и 1 POST, no-op повтор.

Crash-границы 22B через production CLI: POST transport-error →
`unknown`, `reconcile --online` при пустом search → `blocked` (intent
unresolved), повторный `pr create` — 69 и POST остаётся 1; созданный
номер 404 на первом detail → `created` с durable number, повтор —
targeted-get `blocked`, новый POST не диспатчится; частично читаемый
ответ create (только number/url) → `created`, ошибка `get` при повторе
→ `unknown`, POST = 1.

## Ограничения

- Живой GitHub API, реальные credentials и публикация не проверялись;
  offline-готовность не означает live-верификацию или завершение MVP.
- Fake bootstrap подменяет только http-слой и git identity; guards,
  фазы, intents, durable checkpoints и сигнатуры A/B остаются
  продукционными.
- `--pr-transport github` не добавляет network healthcheck: выбранный
  транспорт не проверяется до первого авторизованного вызова.
- Новые файлы: `tests/unit/test_workflow_github_cli.py`,
  `test_data/consts/workflow_github_cli.py`, этот документ, handoff и
  evidence под `artifacts/workflow-github/22c-20261115T224726Z/`.
  Изменён только `tools/workflow.py` из production-кода.
