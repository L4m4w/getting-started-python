# 22A — design: stdlib GitHub REST `GitHubPrTransport`

Дата: 2026-11-16. Реализация — `infrastructure/workflow/github.py`.
Статус проверки: только offline fake-HTTP регрессии; live GitHub
repository/API вызовы не выполнялись и не верифицированы (см.
«Ограничения»). Это описание контракта для 22B/22C, не разрешение
публикации.

## Официальная документация (единственный сетевой источник)

Прочитано read-only 2026-11-16, docs.github.com:

- `https://docs.github.com/en/rest/pulls/pulls` — endpoints
  `GET /repos/{owner}/{repo}/pulls` (list, параметры `state`, `head`,
  `base`, `per_page`, `page`), `POST /repos/{owner}/{repo}/pulls`
  (`title`, `head`, `base`, `body`, `draft`),
  `GET /repos/{owner}/{repo}/pulls/{pull_number}`,
  `GET /repos/{owner}/{repo}/pulls/{pull_number}/files`.
- `https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api`
  — `Link` header, `rel="next"` как признак следующей страницы.

Фактически используемые поля ответов:

- PR item: `number` (int), `state` (`open`/`closed`), `title` (str),
  `html_url` (str), `draft` (bool; при нормализации отсутствие
  трактуется как `false` — недоказанный draft), `body` (str|null),
  `head`/`base` объекты: `ref` (str), `sha` (40/64-hex),
  `repo` (`full_name`; `head.repo` может быть `null` — удалённый fork,
  `base.repo` null недопустим), `merged` (bool — только полный PR в
  `get`, в list-схеме не требуется).
- Files entry: `filename` (str), `status` (str; валидируется на
  присутствие, в состав не входит).
- `Link` header — парсится только `rel`-маркер; URL из него никогда
  не dereference'ится (следующая страница строится параметром `page`
  собственного запроса).

Остальные поля игнорируются (allowlist-подход: лишние ключи —
не ошибка, отсутствующие обязательные — `GitHubResponseError`).

## HTTP-слой

`GitHubPrTransport(token_provider=None, http=None, *, timeout_s=30,
page_size=100, max_pages=100)`.

- `token_provider` — zero-arg callable → str token. Вызывается
  только внутри санкционированного HTTP-вызова (lazy, один вызов
  provider'а на HTTP-запрос в текущей реализации — заголовки собираются
  один раз на метод). По умолчанию `EnvGitHubToken()` читает
  `GITHUB_TOKEN` из env в момент вызова — конструктор env не читает.
  Пустой/не-str токен или исключение provider'а → `GitHubAuthError`
  до первого HTTP-запроса.
- `http` — объект с `request(endpoint, method, path, *, headers=None,
  payload=None)` → ответ с int `status`, `body` (bytes|str),
  `headers` (case-insensitive mapping/HTTPMessage). По умолчанию
  `UrllibHttp` поверх `infrastructure.http.client.HttpClient`
  (stdlib urllib, отказ от redirect через `NoRedirect`, bounded
  timeout). Endpoint всегда `https://api.github.com`.
- Конструктор: zero HTTP, zero token-provider вызовов, zero env/file
  чтений. Валидация аргументов (`request` callable, provider callable,
  положительные int лимиты) — `ValueError`.

## Endpoints и запросы

| Метод | Запросы |
|-------|---------|
| `search(key)` | `GET /repos/{o}/{r}/pulls?state=all&head={o}:{head}&base={base}&per_page=&page=` — fresh walk до исчерпания `rel="next"` |
| `create(spec)` | один `POST /repos/{o}/{r}/pulls` `{title, head, base, draft: true, body?}`; ровно 1 POST, 0 GET |
| `get(repo, n)` | `GET /repos/{o}/{r}/pulls/{n}` → `GET .../files?per_page=&page=` fresh walk |

Заголовки каждого запроса: `Accept: application/vnd.github+json`,
`X-GitHub-Api-Version: 2026-03-10`, `Authorization: Bearer <token>`.
Токен — только header, никогда в URL/query.

## Repo/identity boundary

Единственная принятая форма repo — canonical
`github.com/owner/repo` key (строго три сегмента, host `github.com`
case-insensitive, owner `[A-Za-z0-9][A-Za-z0-9-]{0,38}`, name
`[A-Za-z0-9._-]{1,100}` не `.`/`..`). `evil.github.com`, URL-формы,
scp-like, лишние сегменты → `GitHubSpecError` до любого HTTP.
Ответный `base.repo.full_name` обязан равняться запрошенному
репозиторию (case-insensitive): pull, отданный чужим base —
`GitHubResponseError`, такой PR не может стать кандидатом.

## Pagination

`_walk_pages` — единственный путь обхода list-эндпоинтов
(search items и get files):

- продолжение строго по `rel="next"` в `Link`; отсутствие `next` =
  доказанный конец; достигнут `max_pages` при живом `next` →
  `GitHubResponseError` (недоказанная полнота, не тихий усечённый
  результат);
- страница `len > per_page`, пустая страница при живом `next`,
  malformed `Link`, не-JSON, не-array → `GitHubResponseError`;
- не-200 на любой странице → `GitHubHttpError` (неполный набор не
  возвращается и не превращается в `[]`);
- duplicate `number` в search walk / duplicate `filename` в files
  walk → `GitHubResponseError` (недостоверный набор).

## Body contract (с 22B)

- Remote `body: null` и `body: ""` нормализуются в
  `PrRef.body_sha256 = None`; непустой body хешируется SHA-256 от
  точных UTF-8 bytes, без trim и конвертации переводов строк.
- `create` до POST проверяет пару `body_text`/`body_sha256`:
  отсутствующий ключ `body_text` + null digest → body не отправляется
  (legacy spec без тела); `body_text` null/"" допустим только с
  null digest; непустой текст обязан иметь 64-hex digest и хешироваться
  в него — иначе `GitHubSpecError` до первого HTTP-вызова.
  Записанный digest без воспроизводимого текста (legacy/incomplete
  spec) — локальный блок, никогда не угадывается и не переписывается.
- POST payload всегда содержит `"draft": true`.

## Status/identity validation

`get` после строгой нормализации отвечает:

- HTTP 404 → единственный источник `None`;
- `state != "open"` → `GitHubPrStateError` (closed);
- `merged == true` → `GitHubPrStateError`;
- `draft` не `true` (включая отсутствие поля) → `GitHubPrStateError`;
- `head.repo` null (удалённый fork) или `full_name` чужого repo →
  `GitHubPrStateError` — чужой head не может подтвердить этот PR;
- `number` ответа ≠ запрошенному → `GitHubResponseError`;
- ошибка/неполнота files walk → `GitHubHttpError`/`GitHubResponseError`;
  возвращаются только реально прочитанные отсортированные filenames.

`search` не применяет status-фильтрацию: closed/merged/non-draft/
fork-head PR возвращаются как `PrRef`-кандидаты, чтобы конфликт
не превратился в ложный пустой набор; решение о конфликте —
за orchestrator (`_verify_pr`/`pr_ref_matches`).

`create` принимает ответ как есть: поле `draft`/`state` ответа не
отвергается — читаемый number должен быть возвращён для checkpoint
(полный ref при успешной нормализации, минимальный ref
`{repo, number, url}` когда остальное нечитаемо; совсем нечитаемый
ответ → `GitHubResponseError`). Files в create-ref не выдумываются
из spec — `files=[]`, поля ref только из ответа сервера.

## Ошибки

Все наследуют `GitHubTransportError(WorkflowError)` — сообщения без
токенов и сырых тел ответов:

- `GitHubSpecError` — невалидный key/spec/number; до HTTP;
- `GitHubAuthError` — provider не дал пригодный токен; до HTTP;
- `GitHubHttpError` — transport raise (timeout/conn) или неожиданный
  HTTP status; для POST = unknown outcome, повтор запрещён;
- `GitHubResponseError` — malformed/foreign/incomplete данные;
- `GitHubPrStateError` — удалённый PR существует, но не open unmerged
  same-repo draft.

Retry нет нигде; `create` — ровно один POST, ноль GET.
Redirect-ответ (3xx) доходит до transport'а как status →
`GitHubHttpError`; credentials на другой origin не уходят ни через
redirect (`HttpClient` их отвергает), ни через `Link` URL
(не dereference'ятся), ни через repo-key формы (только canonical
host в пути).

## Ограничения

- Live GitHub API не вызывался: формы endpoints, схемы и поля —
  по документации 2026-11-16 + offline fake-HTTP; реальное поведение
  API (rate limits, дополнительные статусы, draft-flag в list) не
  верифицировано. Перед live wiring (22C+) требуется отдельное
  разрешение и проверка на реальном стенде/аккаунте.
- `title_key` из search key намеренно не отправляется в запрос —
  server-side фильтра такого нет; точное совпадение title —
  ответственность orchestrator над полным набором кандидатов.
- `head_sha`/`files`/`spec_sha256` из spec в POST не передаются
  (API их не принимает); файлы в remote PR задаёт git push ветки,
  не create-запрос.
- Документация описывает `merged` для одиночного PR; list-эндпоинт его
  не гарантирует — `search` его не требует, `get` требует.
