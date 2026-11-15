# 22AR — design: полнота и согласованность PR snapshot в `get`

Дата: 2026-11-16. Реализация — `infrastructure/workflow/github.py`.
Статус проверки: только offline fake-HTTP регрессии и координаторские
probes из копий; live GitHub repository/API вызовы не выполнялись.
Исправляет два findings из
[wave 29](../handoffs/coordination-wave-29.md): F-22A-1 (неполный
files принят как полный) и F-22A-2 (смешанный snapshot). Принятая
реализация 22B не изменялась; API-сигнатуры search/create/get, PrRef
и состав исключений сохранены.

## Официальная документация (единственный сетевой источник)

Прочитано read-only 2026-11-16, docs.github.com:

- `https://docs.github.com/en/rest/pulls/pulls` — полная схема Pull
  Request включает `changed_files` (required, integer); files
  endpoint: «Responses include a maximum of 3000 files».
- `https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api`
  — `Link` header, `rel="next"`.

`changed_files` относится к полной схеме PR и требуется только на пути
`get` (`detail=True` в `_normalize_item`); list-схема его не несёт,
поэтому `search`/`create` не требуют поле — их контракт не изменился.

## Контракт `get(repo, number)` после исправления

Последовательность чтения: **detail → все страницы files → detail**.

1. Первый detail: 404 → `None` (единственный источник `None`);
   другой не-200 → `GitHubHttpError`; нормализация с `detail=True`
   требует `changed_files` — int ≥ 0, bool/str/float/null/пропуск →
   `GitHubResponseError`. Далее прежние state-gates (open, unmerged,
   draft, same-repo head, совпадающий number).
2. `changed_files > MAX_LISTED_FILES` (3000 — документированный
   серверный лимит выдачи) → `GitHubResponseError` до files-запроса:
   полнота по этому endpoint недоказуема в принципе.
3. Files walk (`_read_files`, прежний строгий обход): уникальные
   `filename`, страницы только по `rel="next"` собственного запроса.
   `len(files) != changed_files` → `GitHubResponseError`. Отсутствие
   `Link` не отменяет count-противоречие; files<count, files>count,
   пропуски и дубликаты — controlled failure.
4. Второй detail read того же пути: 404 → `GitHubResponseError`
   (PR исчез между чтениями); другой не-200 → `GitHubHttpError`;
   malformed payload → `GitHubResponseError`. Нормализованный ответ
   сравнивается по всем используемым полям (`SNAPSHOT_FIELDS`:
   number, state, title, url, draft, body_sha256, head_branch,
   head_sha, head_repo, base_branch, base_sha, merged, changed_files);
   любой drift → `GitHubResponseError`. Repo-часть покрыта повторной
   проверкой `base.repo`/`head.repo` в нормализации и сравнением
   `head_repo`.
5. Только при совпадении всех полей возвращается `PrRef` первого
   чтения — граница утверждения: согласованный наблюдаемый снимок,
   не атомарная блокировка сервера. Действия после последнего чтения
   не гарантируются.

HTTP-счётчики happy path: 2 GET detail + по GET на страницу files.
Нет retry, нет повторных запросов, нет POST. `create` не изменён:
ровно один POST, ноль verification GET до возврата читаемого number;
новые reads добавлены только в `get` (после checkpoint B в
orchestrator — запись номера происходит до `_verify_pr`, как раньше).

## Неизменённые границы

- 404 первого чтения → `None`; `None` остаётся единственным
  «доказанным отсутствием».
- `search` по-прежнему возвращает конфликтные кандидаты и не
  превращает их в пустой список.
- `create` принимает ответ как есть, не выдумывает files из spec.
- Unknown/lineage guards в orchestrator не затронуты: ошибка `get`
  на пути `_verify_pr` даёт не-verified outcome (`created`/`blocked`/
  `unknown`), не повторный POST.
- Исключения без токенов и сырых тел: новые ветви используют те же
  `GitHubResponseError`/`GitHubHttpError`.

## Ограничения

- Live GitHub API не вызывался; лимит 3000 и семантика `changed_files`
  взяты из документации 2026-11-16. Реальное поведение сервера
  (граница лимита, `Link` на последней странице большого PR) не
  верифицировано — требуется отдельное разрешение на live проверку.
- Снимок согласован «на глаз» двух чтений: гонка, которая меняет PR
  и возвращает его обратно между файлами и вторым detail, неотличима —
  это заявленная граница, не атомарность.
- `mergeable` и прочие ленивые поля не используются и не проверяются.
