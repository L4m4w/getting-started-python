"""22A регрессии: stdlib GitHub REST `GitHubPrTransport`.

Покрытие строго offline: injectable HTTP layer и token provider, без
сети, env-токенов и живых credentials. Считаются HTTP GET/POST вызовы,
а не только outcomes: lazy constructor, полная/оборванная/повторная/
посторонняя пагинация, malformed data, body/files/head conflicts,
closed/merged/non-draft, null/empty/nonempty body, repo/redirect
boundaries, timeout/unreadable create и ровно один POST без
verification GET.
"""
import json

import allure
import pytest

from infrastructure.http.client import HttpResponse
from infrastructure.workflow import github
from test_data.consts import workflow_github as c


class UnexpectedRoute(BaseException):
    """Маршрут не объявлен: ошибка фикстуры, а не поведение transport'а."""


class FakeHttp:
    """Подмена HTTP-слоя: (method, path) → ответ/исключение/очередь."""

    def __init__(self, routes=None):
        self.routes = dict(routes or {})
        self.calls = []

    def request(self, endpoint, method, path, *, headers=None, payload=None):
        self.calls.append({"endpoint": endpoint, "method": method,
                           "path": path, "headers": dict(headers or {}),
                           "payload": payload})
        action = self.routes.get((method, path))
        if action is None:
            raise UnexpectedRoute(f"unexpected request: {method} {path}")
        if isinstance(action, (list, tuple)):
            queue = list(action)
            action = queue.pop(0)
            if queue:
                self.routes[(method, path)] = queue
            else:
                del self.routes[(method, path)]
        if isinstance(action, BaseException):
            raise action
        return action

    def count(self, method):
        return sum(1 for call in self.calls if call["method"] == method)


def _resp(status, payload, headers=None):
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return HttpResponse(status, body.encode("utf-8"), dict(headers or {}))


def _transport(http, provider=None, **kwargs):
    kwargs.setdefault("page_size", c.PAGE_SIZE)
    kwargs.setdefault("max_pages", c.MAX_PAGES)
    return github.GitHubPrTransport(
        token_provider=provider or (lambda: c.TOKEN), http=http, **kwargs)


def _paths(http):
    return [(call["method"], call["path"]) for call in http.calls]


@allure.epic("Инфраструктура")
@allure.feature("Workflow GitHub transport")
@allure.story("Lazy constructor и injectable provider")
@allure.severity(allure.severity_level.NORMAL)
class TestConstruction:

    @allure.title("Конструктор pure: ноль HTTP и ноль вызовов provider")
    def test_constructor_is_io_free(self):
        with allure.step("Создать transport со spy provider и FakeHttp"):
            http = FakeHttp()
            calls = []

            def provider():
                calls.append(1)
                return c.TOKEN

            _transport(http, provider=provider)
        with allure.step("Проверить отсутствие побочных эффектов"):
            assert http.calls == []
            assert calls == []

    @allure.title("Невалидные http/page_size/max_pages/provider отклоняются")
    def test_invalid_arguments_rejected(self):
        with allure.step("Проверить ValueError на не-объект http и лимиты"):
            with pytest.raises(ValueError):
                github.GitHubPrTransport(http=object())
            with pytest.raises(ValueError):
                github.GitHubPrTransport(token_provider="token")
            with pytest.raises(ValueError):
                _transport(FakeHttp(), page_size=0)
            with pytest.raises(ValueError):
                _transport(FakeHttp(), max_pages=-2)

    @allure.title("EnvGitHubToken читает только заданную переменную при вызове")
    def test_env_provider_lazy_and_scoped(self, monkeypatch):
        with allure.step("Проверить, что env читается вызовом, не конструктором"):
            provider = github.EnvGitHubToken(c.TOKEN_ENV)
            monkeypatch.setenv(c.TOKEN_ENV, c.TOKEN)
            assert provider() == c.TOKEN
            monkeypatch.delenv(c.TOKEN_ENV)
            assert provider() is None


@allure.epic("Инфраструктура")
@allure.feature("Workflow GitHub transport")
@allure.story("search: fresh pagination и строгая нормализация")
@allure.severity(allure.severity_level.BLOCKER)
class TestSearch:

    @allure.title("Полный двухстраничный обход: все refs нормализованы")
    def test_full_two_page_walk(self):
        http = FakeHttp({
            ("GET", c.pulls_path(1)): _resp(
                200, [c.pr_payload(number=1), c.pr_payload(number=2)],
                headers={"Link": c.next_link(c.pulls_path(2))}),
            ("GET", c.pulls_path(2)): _resp(
                200, [c.pr_payload(number=3)]),
        })
        with allure.step("Выполнить search"):
            refs = _transport(http).search(c.SEARCH_KEY)
        with allure.step("Проверить refs и счётчик GET"):
            assert http.count("GET") == 2
            assert http.count("POST") == 0
            assert [ref.number for ref in refs] == [1, 2, 3]
            ref = refs[0]
            assert ref.repo == c.REPO_KEY
            assert ref.title == c.TITLE
            assert ref.head_branch == c.HEAD_BRANCH
            assert ref.base_branch == c.BASE_BRANCH
            assert ref.head_sha == c.HEAD_SHA
            assert ref.body_sha256 == c.BODY_SHA256
            assert ref.files == []

    @allure.title("Пустой список — легитимный пустой ответ за один GET")
    def test_empty_result(self):
        http = FakeHttp({("GET", c.pulls_path(1)): _resp(200, [])})
        with allure.step("Search на пустой выдаче"):
            assert _transport(http).search(c.SEARCH_KEY) == []
            assert http.count("GET") == 1

    @allure.title("Обрыв обхода: ошибка второй страницы не превращается в []")
    def test_broken_walk_raises(self):
        http = FakeHttp({
            ("GET", c.pulls_path(1)): _resp(
                200, [c.pr_payload(number=1)],
                headers={"Link": c.next_link(c.pulls_path(2))}),
            ("GET", c.pulls_path(2)): _resp(500, {"message": "x"}),
        })
        with allure.step("Проверить controlled error и счётчики"):
            with pytest.raises(github.GitHubHttpError):
                _transport(http).search(c.SEARCH_KEY)
            assert http.count("GET") == 2

    @allure.title("Пустая страница с rel=next — недоказанная полнота")
    def test_empty_middle_page_raises(self):
        http = FakeHttp({("GET", c.pulls_path(1)): _resp(
            200, [], headers={"Link": c.next_link(c.pulls_path(2))})})
        with allure.step("Проверить ResponseError"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).search(c.SEARCH_KEY)
            assert http.count("GET") == 1

    @allure.title("Повтор number на следующей странице — inconclusive")
    def test_duplicate_number_raises(self):
        http = FakeHttp({
            ("GET", c.pulls_path(1)): _resp(
                200, [c.pr_payload(number=1)],
                headers={"Link": c.next_link(c.pulls_path(2))}),
            ("GET", c.pulls_path(2)): _resp(200, [c.pr_payload(number=1)]),
        })
        with allure.step("Проверить ResponseError на дубликат"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).search(c.SEARCH_KEY)

    @allure.title("Бесконечный rel=next ограничен max_pages")
    def test_max_pages_bound(self):
        routes = {}
        for page in range(1, c.MAX_PAGES + 1):
            routes[("GET", c.pulls_path(page))] = _resp(
                200, [c.pr_payload(number=page)],
                headers={"Link": c.next_link(c.pulls_path(page + 1))})
        http = FakeHttp(routes)
        with allure.step("Проверить ResponseError и ровно max_pages GET"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).search(c.SEARCH_KEY)
            assert http.count("GET") == c.MAX_PAGES

    @allure.title("Malformed Link header — controlled error")
    def test_malformed_link_header(self):
        http = FakeHttp({("GET", c.pulls_path(1)): _resp(
            200, [c.pr_payload()], headers={"Link": c.MALFORMED_LINK})})
        with allure.step("Проверить ResponseError"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).search(c.SEARCH_KEY)

    @allure.title("Malformed item: отсутствующее поле останавливает search")
    def test_malformed_item(self):
        item = c.pr_payload()
        del item["head"]
        http = FakeHttp({("GET", c.pulls_path(1)): _resp(200, [item])})
        with allure.step("Проверить ResponseError"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).search(c.SEARCH_KEY)

    @allure.title("Чужой base.repo в item — response error, не кандидат")
    def test_foreign_base_repo(self):
        http = FakeHttp({("GET", c.pulls_path(1)): _resp(
            200, [c.pr_payload(base_repo="Other-Org/Other-Repo")])})
        with allure.step("Проверить ResponseError"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).search(c.SEARCH_KEY)

    @allure.title("Неожиданное значение state — response error")
    def test_unexpected_state(self):
        http = FakeHttp({("GET", c.pulls_path(1)): _resp(
            200, [c.pr_payload(state="half-open")])})
        with allure.step("Проверить ResponseError"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).search(c.SEARCH_KEY)

    @allure.title("Начальный не-200 — controlled HttpError, один GET")
    def test_non_200(self):
        http = FakeHttp({("GET", c.pulls_path(1)): _resp(422, {})})
        with allure.step("Проверить HttpError и счётчик"):
            with pytest.raises(github.GitHubHttpError):
                _transport(http).search(c.SEARCH_KEY)
            assert http.count("GET") == 1

    @allure.title("Closed/non-draft/fork-head PR не теряются — возвращаются как кандидаты")
    def test_conflicts_surfaced_not_dropped(self):
        items = [c.pr_payload(number=1, state="closed"),
                 c.pr_payload(number=2, draft=False),
                 c.pr_payload(number=3, head_repo="Fork-Owner/Fork-Repo")]
        http = FakeHttp({("GET", c.pulls_path(1, size=5)):
                         _resp(200, items)})
        with allure.step("Проверить, что конфликты видны orchestrator'у"):
            refs = _transport(http, page_size=5).search(c.SEARCH_KEY)
            assert [ref.number for ref in refs] == [1, 2, 3]

    @allure.title("Параметры запроса: state=all, head=owner:branch, base")
    def test_query_parameters(self):
        http = FakeHttp({("GET", c.pulls_path(1)): _resp(200, [])})
        with allure.step("Search и проверка точного пути"):
            _transport(http).search(c.SEARCH_KEY)
            assert http.calls[0]["path"] == c.pulls_path(1)
            assert c.TITLE_KEY not in http.calls[0]["path"]

    @allure.title("Отсутствующие head/base — параметры не отправляются")
    @pytest.mark.parametrize("missing", ("head_branch", "base_branch"))
    def test_optional_filters(self, missing):
        key = dict(c.SEARCH_KEY)
        key[missing] = None
        path = c.pulls_path(1, head=None if missing == "head_branch" else c.HEAD_BRANCH,
                            base=None if missing == "base_branch" else c.BASE_BRANCH)
        http = FakeHttp({("GET", path): _resp(200, [])})
        with allure.step("Search без одного фильтра"):
            _transport(http).search(key)
            assert http.calls[0]["path"] == path

    @allure.title("Строгая граница repo: чужие hosts/формы отклоняются без HTTP")
    @pytest.mark.parametrize("repo", (
        "evil.github.com/Org/Repo", "github.com.evil/Org/Repo",
        "https://github.com/Org/Repo", "git@github.com:Org/Repo",
        "github.com/Org", "github.com/Org/Repo/extra",
        "github.com//Repo", "github.com/Org/.", "github.com/Org/..",
        "", "  ", None, 42))
    def test_repo_boundary(self, repo):
        http = FakeHttp()
        with allure.step(f"Проверить отказ для repo={repo!r}"):
            with pytest.raises(github.GitHubSpecError):
                _transport(http).search({"repo": repo})
            assert http.calls == []

    @allure.title("Невалидный тип ключа и фильтров — SpecError без HTTP")
    def test_invalid_key_types(self):
        http = FakeHttp()
        with allure.step("Проверить SpecError"):
            with pytest.raises(github.GitHubSpecError):
                _transport(http).search("not-a-key")
            with pytest.raises(github.GitHubSpecError):
                _transport(http).search(dict(c.SEARCH_KEY, head_branch=""))
            with pytest.raises(github.GitHubSpecError):
                _transport(http).search(dict(c.SEARCH_KEY, base_branch=5))
            assert http.calls == []


@allure.epic("Инфраструктура")
@allure.feature("Workflow GitHub transport")
@allure.story("get: targeted re-read с полным составом")
@allure.severity(allure.severity_level.BLOCKER)
class TestGet:

    def _routes(self, pr_payload=None, files=None, pr_status=200):
        item = c.pr_payload() if pr_payload is None else pr_payload
        files = c.FILES if files is None else files
        routes = {("GET", c.pr_path()): _resp(pr_status, item)}
        if files:
            page1, page2 = files[:c.PAGE_SIZE], files[c.PAGE_SIZE:]
            routes[("GET", c.files_path(1))] = _resp(
                200, [c.file_payload(name) for name in page1],
                headers={"Link": c.next_link(c.files_path(2))}
                if page2 else None)
            if page2:
                routes[("GET", c.files_path(2))] = _resp(
                    200, [c.file_payload(name) for name in page2])
        else:
            routes[("GET", c.files_path(1))] = _resp(200, [])
        return routes

    @allure.title("Полный get: open draft + две страницы files")
    def test_full_get(self):
        http = FakeHttp(self._routes())
        with allure.step("Выполнить get"):
            ref = _transport(http).get(c.REPO_KEY, c.NUMBER)
        with allure.step("Проверить ref и порядок вызовов"):
            assert ref.number == c.NUMBER
            assert ref.repo == c.REPO_KEY
            assert ref.url.endswith(f"/pull/{c.NUMBER}")
            assert ref.head_sha == c.HEAD_SHA
            assert ref.body_sha256 == c.BODY_SHA256
            assert ref.files == sorted(c.FILES)
            assert _paths(http) == [
                ("GET", c.pr_path()),
                ("GET", c.files_path(1)),
                ("GET", c.files_path(2)),
                ("GET", c.pr_path())]

    @allure.title("Доказанный 404 — единственный источник None")
    def test_404_returns_none(self):
        http = FakeHttp({("GET", c.pr_path()): _resp(404, {"message": "nf"})})
        with allure.step("Проверить None и один GET"):
            assert _transport(http).get(c.REPO_KEY, c.NUMBER) is None
            assert http.count("GET") == 1

    @allure.title("Не-200/не-404 — controlled HttpError")
    def test_non_200(self):
        http = FakeHttp({("GET", c.pr_path()): _resp(503, {})})
        with allure.step("Проверить HttpError"):
            with pytest.raises(github.GitHubHttpError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)

    @allure.title("Closed PR — отказ без чтения files")
    def test_closed_refused(self):
        http = FakeHttp(self._routes(c.pr_payload(state="closed")))
        with allure.step("Проверить PrStateError и один GET"):
            with pytest.raises(github.GitHubPrStateError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)
            assert _paths(http) == [("GET", c.pr_path())]

    @allure.title("Merged PR — отказ")
    def test_merged_refused(self):
        http = FakeHttp(self._routes(c.pr_payload(merged=True)))
        with allure.step("Проверить PrStateError"):
            with pytest.raises(github.GitHubPrStateError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)

    @allure.title("Non-draft PR — отказ")
    def test_non_draft_refused(self):
        http = FakeHttp(self._routes(c.pr_payload(draft=False)))
        with allure.step("Проверить PrStateError"):
            with pytest.raises(github.GitHubPrStateError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)

    @allure.title("Отсутствующее поле draft — недоказанный draft, отказ")
    def test_absent_draft_refused(self):
        item = c.pr_payload()
        del item["draft"]
        http = FakeHttp(self._routes(item))
        with allure.step("Проверить PrStateError"):
            with pytest.raises(github.GitHubPrStateError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)

    @allure.title("Чужой head.repo — отказ, не кандидат")
    def test_foreign_head_repo(self):
        http = FakeHttp(self._routes(
            c.pr_payload(head_repo="Fork-Owner/Fork-Repo")))
        with allure.step("Проверить PrStateError"):
            with pytest.raises(github.GitHubPrStateError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)

    @allure.title("Null head.repo (удалённый fork) — отказ")
    def test_null_head_repo(self):
        http = FakeHttp(self._routes(c.pr_payload(head_repo=None)))
        with allure.step("Проверить PrStateError"):
            with pytest.raises(github.GitHubPrStateError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)

    @allure.title("Чужой base.repo — response error")
    def test_foreign_base_repo(self):
        http = FakeHttp(self._routes(
            c.pr_payload(base_repo="Other-Org/Other-Repo")))
        with allure.step("Проверить ResponseError"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)

    @allure.title("Несовпадающий number — response error")
    def test_number_mismatch(self):
        http = FakeHttp(self._routes(c.pr_payload(number=c.OTHER_NUMBER)))
        with allure.step("Проверить ResponseError"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)

    @allure.title("Malformed payload — response error")
    def test_malformed_payload(self):
        item = c.pr_payload()
        del item["title"]
        http = FakeHttp(self._routes(item))
        with allure.step("Проверить ResponseError"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)

    @allure.title("Ошибка files — HttpError, ложный ref не возвращается")
    def test_files_error(self):
        routes = self._routes()
        routes[("GET", c.files_path(1))] = _resp(422, {})
        http = FakeHttp(routes)
        with allure.step("Проверить HttpError и счётчики"):
            with pytest.raises(github.GitHubHttpError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)
            assert http.count("GET") == 2

    @allure.title("Malformed file entry — response error")
    def test_files_malformed(self):
        routes = self._routes()
        bad = c.file_payload("x.py")
        del bad["filename"]
        routes[("GET", c.files_path(1))] = _resp(200, [bad])
        http = FakeHttp(routes)
        with allure.step("Проверить ResponseError"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)

    @allure.title("Дубликат filename в обходе — inconclusive")
    def test_files_duplicate(self):
        routes = self._routes()
        routes[("GET", c.files_path(1))] = _resp(
            200, [c.file_payload("a.py"), c.file_payload("a.py")])
        http = FakeHttp(routes)
        with allure.step("Проверить ResponseError"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)

    @allure.title("Невалидный number/repo — SpecError без HTTP")
    @pytest.mark.parametrize("repo,number", (
        (c.REPO_KEY, 0), (c.REPO_KEY, -3), (c.REPO_KEY, "x"),
        (c.REPO_KEY, True), ("git.invalid/Org/Repo", 5)))
    def test_invalid_args(self, repo, number):
        http = FakeHttp()
        with allure.step("Проверить SpecError"):
            with pytest.raises(github.GitHubSpecError):
                _transport(http).get(repo, number)
            assert http.calls == []


@allure.epic("Инфраструктура")
@allure.feature("Workflow GitHub transport")
@allure.story("create: один draft POST, читаемый number до verification")
@allure.severity(allure.severity_level.BLOCKER)
class TestCreate:

    def _routes(self, status=201, payload=None, headers=None):
        item = c.pr_payload() if payload is None else payload
        return {("POST", f"/repos/{c.OWNER}/{c.NAME}/pulls"):
                _resp(status, item, headers=headers)}

    @allure.title("Успешный create: ref из ответа, POST=1, GET=0")
    def test_create_ok(self):
        http = FakeHttp(self._routes())
        with allure.step("Выполнить create"):
            ref = _transport(http).create(c.spec())
        with allure.step("Проверить ref, payload и счётчики"):
            assert ref.number == c.NUMBER
            assert ref.repo == c.REPO_KEY
            assert ref.url.endswith(f"/pull/{c.NUMBER}")
            assert ref.title == c.TITLE
            assert ref.head_sha == c.HEAD_SHA
            assert ref.body_sha256 == c.BODY_SHA256
            assert http.count("POST") == 1
            assert http.count("GET") == 0
            sent = http.calls[0]
            assert sent["payload"] == {
                "title": c.TITLE, "head": c.HEAD_BRANCH,
                "base": c.BASE_BRANCH, "draft": True, "body": c.BODY_TEXT}

    @allure.title("Без body — ключ body не отправляется")
    def test_create_without_body(self):
        http = FakeHttp(self._routes())
        with allure.step("Create со spec без тела"):
            _transport(http).create(c.spec(body_text=None, body_sha256=None))
            assert "body" not in http.calls[0]["payload"]

    @allure.title("Пустой body_text канонизируется как отсутствие body")
    def test_create_empty_body_text(self):
        http = FakeHttp(self._routes())
        with allure.step("Create с пустым текстом и null digest"):
            _transport(http).create(c.spec(body_text="", body_sha256=None))
            assert "body" not in http.calls[0]["payload"]

    @allure.title("Digest не соответствует body_text — блок до POST")
    def test_body_digest_mismatch(self):
        http = FakeHttp()
        with allure.step("Проверить SpecError и ноль HTTP"):
            with pytest.raises(github.GitHubSpecError):
                _transport(http).create(
                    c.spec(body_sha256=c.OTHER_BODY_SHA256))
            assert http.calls == []

    @allure.title("Legacy spec: digest без body_text — блок до POST")
    def test_legacy_digest_without_text(self):
        http = FakeHttp()
        spec = {key: value for key, value in c.SPEC.items()
                if key != "body_text"}
        with allure.step("Проверить SpecError и ноль HTTP"):
            with pytest.raises(github.GitHubSpecError):
                _transport(http).create(spec)
            assert http.calls == []

    @allure.title("body_text без digest — блок до POST")
    def test_body_text_without_digest(self):
        http = FakeHttp()
        with allure.step("Проверить SpecError"):
            with pytest.raises(github.GitHubSpecError):
                _transport(http).create(c.spec(body_sha256=None))
            assert http.calls == []

    @allure.title("Пустой текст с digest — блок до POST")
    def test_empty_text_with_digest(self):
        http = FakeHttp()
        with allure.step("Проверить SpecError"):
            with pytest.raises(github.GitHubSpecError):
                _transport(http).create(
                    c.spec(body_text="", body_sha256=c.BODY_SHA256))
            assert http.calls == []

    @allure.title("Невалидные поля spec — SpecError без HTTP")
    @pytest.mark.parametrize("spec", (
        "not-a-spec",
        {"title": "t", "head_branch": "h", "base_branch": "b"},
        {"repo": "git.invalid/Org/Repo", "title": "t", "head_branch": "h",
         "base_branch": "b"},
        {"repo": c.REPO_KEY, "title": "", "head_branch": "h",
         "base_branch": "b"},
        {"repo": c.REPO_KEY, "title": "t", "head_branch": None,
         "base_branch": "b"},
        {"repo": c.REPO_KEY, "title": "t", "head_branch": "h",
         "base_branch": 3},
        {"repo": c.REPO_KEY, "title": "t", "head_branch": "h",
         "base_branch": "b", "body_text": 5, "body_sha256": c.BODY_SHA256},
    ))
    def test_invalid_spec(self, spec):
        http = FakeHttp()
        with allure.step("Проверить SpecError и ноль HTTP"):
            with pytest.raises(github.GitHubSpecError):
                _transport(http).create(spec)
            assert http.calls == []

    @allure.title("Не-201 — один POST, ноль retries, ноль GET")
    @pytest.mark.parametrize("status", (403, 422, 500))
    def test_non_201_no_retry(self, status):
        http = FakeHttp(self._routes(status=status, payload={}))
        with allure.step("Проверить HttpError и счётчики"):
            with pytest.raises(github.GitHubHttpError):
                _transport(http).create(c.spec())
            assert http.count("POST") == 1
            assert http.count("GET") == 0

    @allure.title("Timeout/transport raise после dispatch — controlled error")
    def test_transport_failure(self):
        http = FakeHttp({("POST", f"/repos/{c.OWNER}/{c.NAME}/pulls"):
                         TimeoutError("unit timeout")})
        with allure.step("Проверить HttpError и один POST"):
            with pytest.raises(github.GitHubHttpError):
                _transport(http).create(c.spec())
            assert http.count("POST") == 1

    @allure.title("Нечитаемый JSON create — response error")
    def test_malformed_json(self):
        routes = {("POST", f"/repos/{c.OWNER}/{c.NAME}/pulls"):
                  _resp(201, "{broken")}
        http = FakeHttp(routes)
        with allure.step("Проверить ResponseError"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).create(c.spec())

    @allure.title("201 без number — unreadable, response error")
    def test_unreadable_create(self):
        http = FakeHttp(self._routes(payload={"id": 1}))
        with allure.step("Проверить ResponseError"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).create(c.spec())

    @allure.title("Частично читаемый ответ: number сохраняется до verification")
    def test_partially_readable_create(self):
        http = FakeHttp(self._routes(
            payload={"number": c.NUMBER, "html_url": "https://x/pull/1"}))
        with allure.step("Проверить minimal ref"):
            ref = _transport(http).create(c.spec())
            assert ref.number == c.NUMBER
            assert ref.url == "https://x/pull/1"
            assert ref.title is None

    @allure.title("Create с неожиданным state — number всё равно читаем")
    def test_anomalous_state_readable(self):
        http = FakeHttp(self._routes(payload=c.pr_payload(draft=False)))
        with allure.step("Проверить, что ref возвращается для записи number"):
            ref = _transport(http).create(c.spec())
            assert ref.number == c.NUMBER
            assert http.count("GET") == 0


@allure.epic("Инфраструктура")
@allure.feature("Workflow GitHub transport")
@allure.story("Credentials, repo/redirect boundaries")
@allure.severity(allure.severity_level.BLOCKER)
class TestCredentialsAndBoundaries:

    @allure.title("Provider вызывается только при разрешённом HTTP-вызове")
    def test_provider_called_only_on_request(self):
        http = FakeHttp({("GET", c.pulls_path(1)): _resp(200, [])})
        calls = []

        def provider():
            calls.append(1)
            return c.TOKEN

        transport = _transport(http, provider=provider)
        with allure.step("До вызова provider не вызывался"):
            assert calls == []
        with allure.step("После search — один вызов provider"):
            transport.search(c.SEARCH_KEY)
            assert calls == [1]

    @allure.title("Пустой/отсутствующий токен — AuthError без HTTP")
    @pytest.mark.parametrize("token", (None, "", "   ", 5))
    def test_missing_token(self, token):
        http = FakeHttp()
        with allure.step("Проверить AuthError и ноль HTTP"):
            with pytest.raises(github.GitHubAuthError):
                _transport(http, provider=lambda: token).search(c.SEARCH_KEY)
            assert http.calls == []

    @allure.title("Исключение provider — AuthError без HTTP")
    def test_provider_raises(self):
        http = FakeHttp()

        def provider():
            raise RuntimeError("boom")

        with allure.step("Проверить AuthError"):
            with pytest.raises(github.GitHubAuthError):
                _transport(http, provider=provider).search(c.SEARCH_KEY)
            assert http.calls == []

    @allure.title("Токен — только Bearer header, никогда в URL")
    def test_token_only_in_header(self):
        http = FakeHttp({("GET", c.pulls_path(1)): _resp(200, [])})
        with allure.step("Выполнить search и проверить headers/path"):
            _transport(http).search(c.SEARCH_KEY)
            call = http.calls[0]
            assert call["headers"]["Authorization"] == f"Bearer {c.TOKEN}"
            assert c.TOKEN not in call["path"]
            assert call["endpoint"] == c.API_ENDPOINT

    @allure.title("3xx/redirect не dereference'ится — controlled error, один GET")
    @pytest.mark.parametrize("status", (301, 302, 307))
    def test_redirect_refused(self, status):
        http = FakeHttp({("GET", c.pulls_path(1)): _resp(
            status, "", headers={"Location": "https://evil.example/x"})})
        with allure.step("Проверить HttpError и один вызов"):
            with pytest.raises(github.GitHubHttpError):
                _transport(http).search(c.SEARCH_KEY)
            assert http.count("GET") == 1

    @allure.title("Link URL на чужой host не dereference'ится")
    def test_foreign_link_not_dereferenced(self):
        http = FakeHttp({
            ("GET", c.pulls_path(1)): _resp(
                200, [c.pr_payload()],
                headers={"Link": c.FOREIGN_NEXT_LINK}),
            ("GET", c.pulls_path(2)): _resp(200, []),
        })
        with allure.step("Проверить, что вторая страница — свой путь"):
            _transport(http).search(c.SEARCH_KEY)
            assert http.calls[1]["endpoint"] == c.API_ENDPOINT
            assert http.calls[1]["path"] == c.pulls_path(2)

    @allure.title("Все вызовы идут только на api.github.com")
    def test_fixed_endpoint(self):
        http = FakeHttp({
            ("GET", c.pulls_path(1)): _resp(200, []),
            ("GET", c.pr_path()): _resp(200, c.pr_payload(changed_files=0)),
            ("GET", c.files_path(1)): _resp(200, []),
            ("POST", f"/repos/{c.OWNER}/{c.NAME}/pulls"): _resp(
                201, c.pr_payload()),
        })
        transport = _transport(http)
        with allure.step("Выполнить search/get/create"):
            transport.search(c.SEARCH_KEY)
            transport.get(c.REPO_KEY, c.NUMBER)
            transport.create(c.spec())
        with allure.step("Проверить endpoint всех вызовов"):
            assert all(call["endpoint"] == c.API_ENDPOINT
                       for call in http.calls)
