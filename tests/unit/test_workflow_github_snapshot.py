"""22AR регрессии: полнота files и согласованность snapshot в `get`.

F-22A-1: file list обязан быть полным и уникальным и равняться
объявленному ``changed_files`` PR detail — missing/invalid count,
несовпадение, частичная пагинация и документированный серверный лимит
дают controlled failure. F-22A-2: get читает detail → все страницы
files → detail повторно и отвергает любой drift используемых полей
(number/repo/branches/head/base SHA/title/body/draft/state/merged/
count), ошибочное или 404 повторное чтение. Покрытие строго offline:
stateful fake HTTP, без сети и credentials. Дополнительно — цепочка
`pr_create` через настоящий GitHubPrTransport и принятый orchestrator B
для ролей app и tests: inconsistent get не даёт verified, номер
остаётся записанным, повторный POST=0.
"""
import copy
import json
from urllib.parse import parse_qs, urlsplit

import allure
import pytest

from infrastructure.http.client import HttpResponse
from infrastructure.workflow import adapters, github
from test_data.consts import workflow as wc
from test_data.consts import workflow_github as c
from test_data.consts import workflow_github_snapshot as s
from test_data.utils.workflow import Project


class UnexpectedRoute(BaseException):
    """Маршрут не объявлен: ошибка фикстуры, а не поведение transport'а."""


def _resp(status, payload, headers=None):
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return HttpResponse(status, body.encode("utf-8"), dict(headers or {}))


def _files_page(entries, *, next_page=None, status=200):
    """(status, payload, headers) одной страницы files-эндпоинта."""
    headers = {}
    if next_page is not None:
        headers = {"Link": c.next_link(c.files_path(next_page))}
    return status, [c.file_payload(name) for name in entries], headers


class GetServer:
    """Stateful fake GitHub REST для transport.get: detail→files→detail.

    ``mutate`` применяется к текущему PR при каждом files-запросе —
    второй detail read видит изменённое состояние (модель гонки).
    ``second`` переопределяет ответ второго detail read: HttpResponse,
    исключение или callable. Без override второй ответ совпадает с
    первым — стабильный снимок.
    """

    def __init__(self, pr=None, pages=None, *, mutate=None, second=None):
        self.current = pr if pr is not None else c.pr_payload()
        self.pages = list(pages or [])
        self.mutate = mutate
        self.second = second
        self.calls = []
        self.detail_reads = 0
        self.files_prefix = c.pr_path() + "/files"

    def request(self, endpoint, method, path, *, headers=None,
                payload=None):
        self.calls.append((method, path))
        if method == "GET" and path == c.pr_path():
            self.detail_reads += 1
            if self.detail_reads == 1:
                return _resp(200, copy.deepcopy(self.current))
            second = self.second
            if callable(second):
                return second()
            if isinstance(second, BaseException):
                raise second
            if second is not None:
                return second
            return _resp(200, copy.deepcopy(self.current))
        if method == "GET" and path.startswith(self.files_prefix):
            if self.mutate is not None:
                self.mutate(self.current)
            page = int(parse_qs(urlsplit(path).query)["page"][0])
            if not 0 < page <= len(self.pages):
                raise UnexpectedRoute(f"files page {page} not configured")
            status, entries, page_headers = self.pages[page - 1]
            return _resp(status, entries, headers=page_headers)
        raise UnexpectedRoute(f"unexpected request: {method} {path}")

    def count(self, method):
        return sum(1 for call in self.calls if call[0] == method)


def _transport(http, **kwargs):
    kwargs.setdefault("page_size", c.PAGE_SIZE)
    kwargs.setdefault("max_pages", c.MAX_PAGES)
    return github.GitHubPrTransport(
        token_provider=lambda: c.TOKEN, http=http, **kwargs)


def _page_map(files):
    """Страницы по PAGE_SIZE элементов для заданного списка файлов."""
    pages = []
    chunks = [files[i:i + c.PAGE_SIZE]
              for i in range(0, len(files), c.PAGE_SIZE)] or [[]]
    for index, chunk in enumerate(chunks):
        next_page = index + 2 if index + 1 < len(chunks) else None
        pages.append(_files_page(chunk, next_page=next_page))
    return pages


def _drift(field):
    """Мутатор второго detail read: меняет одно используемое поле PR."""
    mutators = {
        "head_sha": lambda pr: pr["head"].update(sha=s.ALT_HEAD_SHA),
        "base_sha": lambda pr: pr["base"].update(sha=s.ALT_BASE_SHA),
        "head_branch": lambda pr: pr["head"].update(
            ref=s.ALT_HEAD_BRANCH),
        "base_branch": lambda pr: pr["base"].update(
            ref=s.ALT_BASE_BRANCH),
        "title": lambda pr: pr.update(title=s.ALT_TITLE),
        "body": lambda pr: pr.update(body=s.ALT_BODY_TEXT),
        "draft": lambda pr: pr.update(draft=False),
        "state": lambda pr: pr.update(state="closed"),
        "merged": lambda pr: pr.update(merged=True),
        "changed_files": lambda pr: pr.update(
            changed_files=pr["changed_files"] + 1),
        "head_repo_null": lambda pr: pr["head"].update(repo=None),
        "head_repo_foreign": lambda pr: pr["head"].update(
            repo=c.repo_obj(s.FOREIGN_REPO_FULL_NAME)),
        "number": lambda pr: pr.update(number=s.ALT_NUMBER),
        "url": lambda pr: pr.update(html_url=s.ALT_URL),
    }
    return mutators[field]


@allure.epic("Инфраструктура")
@allure.feature("Workflow GitHub transport")
@allure.story("get: полнота files против changed_files")
@allure.severity(allure.severity_level.BLOCKER)
class TestFilesCompleteness:

    @allure.title("Стабильный get: count=0 и пустой files — точный ref")
    def test_zero_count(self):
        http = GetServer(pr=c.pr_payload(changed_files=0),
                         pages=[(200, [], {})])
        with allure.step("Выполнить get"):
            ref = _transport(http).get(c.REPO_KEY, c.NUMBER)
        with allure.step("Проверить ref и точную последовательность GET"):
            assert ref.files == []
            assert http.calls == [("GET", c.pr_path()),
                                  ("GET", c.files_path(1)),
                                  ("GET", c.pr_path())]
            assert http.count("POST") == 0

    @allure.title("Полный обход: count совпадает с уникальными файлами 3 страниц")
    def test_multi_page_complete(self):
        http = GetServer(pr=c.pr_payload(changed_files=len(s.MANY_FILES)),
                         pages=_page_map(s.MANY_FILES))
        with allure.step("Выполнить get"):
            ref = _transport(http).get(c.REPO_KEY, c.NUMBER)
        with allure.step("Проверить состав и 5 GET (detail+3 pages+detail)"):
            assert ref.files == sorted(s.MANY_FILES)
            assert http.calls == [("GET", c.pr_path()),
                                  ("GET", c.files_path(1)),
                                  ("GET", c.files_path(2)),
                                  ("GET", c.files_path(3)),
                                  ("GET", c.pr_path())]
            assert http.count("POST") == 0

    @allure.title("Отсутствующий changed_files — controlled failure")
    def test_missing_count(self):
        pr = c.pr_payload()
        del pr["changed_files"]
        http = GetServer(pr=pr, pages=_page_map(list(c.FILES)))
        with allure.step("Проверить ResponseError до чтения files"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)
            assert http.calls == [("GET", c.pr_path())]

    @allure.title("Невалидный changed_files — controlled failure")
    @pytest.mark.parametrize("bad", (-1, True, "2", 1.5, None))
    def test_invalid_count(self, bad):
        http = GetServer(pr=c.pr_payload(changed_files=bad),
                         pages=_page_map(list(c.FILES)))
        with allure.step(f"Проверить ResponseError для count={bad!r}"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)
            assert http.calls == [("GET", c.pr_path())]

    @allure.title("Усечённый files < count без Link — controlled failure")
    def test_files_fewer_than_count(self):
        http = GetServer(pr=c.pr_payload(changed_files=len(c.FILES)),
                         pages=[_files_page([c.FILES[0], c.FILES[1]])])
        with allure.step("Проверить ResponseError без повторного detail"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)
            assert http.calls == [("GET", c.pr_path()),
                                  ("GET", c.files_path(1))]

    @allure.title("Лишние files > count — controlled failure")
    def test_files_more_than_count(self):
        http = GetServer(pr=c.pr_payload(changed_files=1),
                         pages=[_files_page(list(c.FILES))])
        with allure.step("Проверить ResponseError"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)
            assert http.calls == [("GET", c.pr_path()),
                                  ("GET", c.files_path(1))]

    @allure.title("count выше документированного лимита — controlled failure до files")
    def test_over_documented_limit(self):
        http = GetServer(
            pr=c.pr_payload(changed_files=s.OVER_LIMIT_COUNT),
            pages=[])
        with allure.step("Проверить ResponseError без files-запроса"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)
            assert http.calls == [("GET", c.pr_path())]

    @allure.title("Недостача на последней странице (пропуск) — controlled failure")
    def test_skipped_tail(self):
        http = GetServer(
            pr=c.pr_payload(changed_files=len(s.MANY_FILES)),
            pages=_page_map(s.MANY_FILES[:-1]))
        with allure.step("4 уникальных файла против count=5 — ResponseError"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)
            assert http.calls == [("GET", c.pr_path()),
                                  ("GET", c.files_path(1)),
                                  ("GET", c.files_path(2))]

    @allure.title("Дубликат filename на следующей странице — controlled failure")
    def test_duplicate_across_pages(self):
        http = GetServer(
            pr=c.pr_payload(changed_files=3),
            pages=[_files_page([c.FILES[0], c.FILES[1]], next_page=2),
                   _files_page([c.FILES[1], c.FILES[2]])])
        with allure.step("Проверить ResponseError на дубликат"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)

    @allure.title("Ошибка следующей страницы — HttpError, не partial set")
    def test_broken_next_page(self):
        http = GetServer(
            pr=c.pr_payload(changed_files=3),
            pages=[_files_page([c.FILES[0], c.FILES[1]], next_page=2),
                   (404, [], {})])
        with allure.step("Проверить HttpError и 3 GET до отказа"):
            with pytest.raises(github.GitHubHttpError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)
            assert http.calls == [("GET", c.pr_path()),
                                  ("GET", c.files_path(1)),
                                  ("GET", c.files_path(2))]


@allure.epic("Инфраструктура")
@allure.feature("Workflow GitHub transport")
@allure.story("get: согласованность повторного detail read")
@allure.severity(allure.severity_level.BLOCKER)
class TestSnapshotConsistency:

    def _stable(self):
        return GetServer(pr=c.pr_payload(changed_files=len(c.FILES)),
                         pages=_page_map(list(c.FILES)))

    @allure.title("Стабильный snapshot — точный ref, два detail read")
    def test_stable_get_exact(self):
        http = self._stable()
        with allure.step("Выполнить get и сверить со spec"):
            ref = _transport(http).get(c.REPO_KEY, c.NUMBER)
            assert adapters.pr_ref_exact(ref, c.spec()) is True
        with allure.step("Проверить detail→files→detail и POST=0"):
            assert http.calls == [("GET", c.pr_path()),
                                  ("GET", c.files_path(1)),
                                  ("GET", c.files_path(2)),
                                  ("GET", c.pr_path())]
            assert http.count("POST") == 0

    @allure.title("Drift используемого поля во время files — controlled failure")
    @pytest.mark.parametrize("field", (
        "head_sha", "base_sha", "head_branch", "base_branch", "title",
        "body", "draft", "state", "merged", "changed_files",
        "head_repo_null", "head_repo_foreign", "number", "url"))
    def test_drift_refused(self, field):
        http = self._stable()
        http.mutate = _drift(field)
        with allure.step(f"Проверить ResponseError на drift {field}"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)
        with allure.step("Проверить, что второй detail read выполнен"):
            assert http.calls[-1] == ("GET", c.pr_path())
            assert http.count("POST") == 0

    @allure.title("404 повторного detail — controlled failure, не None")
    def test_second_read_404(self):
        http = self._stable()
        http.second = _resp(404, {"message": "nf"})
        with allure.step("Проверить controlled error"):
            with pytest.raises(github.GitHubTransportError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)
            assert http.calls[-1] == ("GET", c.pr_path())

    @allure.title("Не-200 повторного detail — HttpError")
    def test_second_read_error(self):
        http = self._stable()
        http.second = _resp(500, {"message": "x"})
        with allure.step("Проверить HttpError"):
            with pytest.raises(github.GitHubHttpError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)

    @allure.title("Нечитаемый JSON повторного detail — ResponseError")
    def test_second_read_malformed(self):
        http = self._stable()
        http.second = _resp(200, "{broken")
        with allure.step("Проверить ResponseError"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)

    @allure.title("Повторный detail без обязательного поля — ResponseError")
    def test_second_read_missing_field(self):
        pr = c.pr_payload(changed_files=len(c.FILES))
        del pr["title"]
        http = self._stable()
        http.second = _resp(200, pr)
        with allure.step("Проверить ResponseError"):
            with pytest.raises(github.GitHubResponseError):
                _transport(http).get(c.REPO_KEY, c.NUMBER)


class ChainServer:
    """Fake GitHub для полной цепочки pr_create (search→POST→get)."""

    def __init__(self, spec, mode):
        self.spec = spec
        self.mode = mode
        self.calls = []
        slug = spec["repo"].split("/", 1)[1]
        self.current = c.pr_payload(
            title=spec["title"], body=spec.get("body_text"),
            head_ref=spec["head_branch"], base_ref=spec["base_branch"],
            head_sha=spec["head_sha"], head_repo=slug, base_repo=slug,
            changed_files=len(spec["files"])
            + (1 if mode == "incomplete-files" else 0))

    def request(self, endpoint, method, path, *, headers=None,
                payload=None):
        self.calls.append((method, path))
        status = 200
        if method == "POST":
            payload_out = copy.deepcopy(self.current)
            status = 201
        elif "/files?" in path:
            if self.mode == "head-race":
                self.current["head"]["sha"] = s.ALT_HEAD_SHA
            payload_out = [c.file_payload(p) for p in self.spec["files"]]
        elif "/pulls?" in path:
            payload_out = []
        else:
            payload_out = copy.deepcopy(self.current)
        return _resp(status, payload_out)

    def count(self, method):
        return sum(1 for call in self.calls if call[0] == method)


@allure.epic("Инфраструктура")
@allure.feature("Workflow GitHub transport")
@allure.story("pr_create через настоящий transport: snapshot для app/tests")
@allure.severity(allure.severity_level.BLOCKER)
class TestOrchestratorSnapshot:

    def _project(self, root, role):
        class GitHubProject(Project):
            def init(self, orchestrator=None, **overrides):
                overrides.setdefault("app_repo", c.REPO_KEY)
                if role == "tests":
                    overrides.setdefault(
                        "tests_repo", s.TESTS_REPO_KEY)
                return super().init(orchestrator, **overrides)

        return GitHubProject(root)

    @pytest.mark.parametrize("role", ("app", "tests"))
    @pytest.mark.parametrize(
        "mode", ("control", "incomplete-files", "head-race"))
    def test_pr_create_chain(self, tmp_path, role, mode):
        project = self._project(tmp_path / f"{role}-{mode}", role)
        with allure.step("Довести workflow до executed"):
            project.drive_commit_to_executed()
            orchestrator = project.orchestrator()
            files = [wc.CHANGED_APP_FILE] if role == "app" \
                else list(wc.TEST_FILES)
            orchestrator.pr_prepare(
                role, title="snapshot probe", head_branch="wf/probe",
                base_branch="main", files=files)
        with allure.step("Собрать spec и настроить fake GitHub"):
            spec = project.workflow_state()[
                "publications"]["pr"][role]["spec"]
            server = ChainServer(spec, mode)
            transport = github.GitHubPrTransport(
                token_provider=lambda: c.TOKEN, http=server)
            orchestrator = project.orchestrator(
                pr_transports={role: transport})
        with allure.step("Выполнить pr_create"):
            outcome = orchestrator.pr_create(role, execute=True,
                                             online=True)
        with allure.step("Проверить outcome, запись номера и счётчики"):
            entry = project.workflow_state()[
                "publications"]["pr"][role]
            if mode == "control":
                assert outcome["outcome"] == "verified"
                assert entry["status"] == "verified"
            else:
                assert outcome["outcome"] != "verified"
                assert entry["status"] != "verified"
            assert entry["number"] == c.NUMBER
            assert server.count("POST") == 1
        with allure.step("Повторный pr_create — ноль новых POST"):
            orchestrator.pr_create(role, execute=True, online=True)
            assert server.count("POST") == 1
            assert project.workflow_state()[
                "publications"]["pr"][role]["number"] == c.NUMBER
