"""22C регрессии: production CLI `--pr-transport {none,github}` wiring.

Два уровня проверок, строго offline:

- subprocess-прогоны реального `tools/workflow.py` с fake bootstrap'ом
  (`sitecustomize.py` + JSON-сценарий git/http через `WF_GH_FAKE_*` env):
  порядок глобального флага, default `none`, ноль HTTP/credential-чтений
  без разрешающих флагов и на ранних командах, достижимый create по
  temp fixture с fake commit/tree и счётчики GET/POST, а также
  unknown+[], known-number-404 и crash на читаемом номере с нулём
  новых POST;
- программная проверка wiring `_orchestrator` (app/tests роли, lazy
  конструктор без I/O) и полная цепочка Orchestrator → настоящий
  `GitHubPrTransport` → FakeHttp с контролем порядка
  detail → files → detail второго чтения accepted `get`.

Сеть, реальные GitHub API и настоящие credentials не используются.
"""
import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import allure
import pytest

from infrastructure.http.client import HttpResponse
from infrastructure.workflow import adapters, github
from infrastructure.workflow import state as state_mod
from test_data.consts import workflow as wc
from test_data.consts import workflow_github as gc
from test_data.consts import workflow_github_cli as c
from test_data.utils.workflow import Project
from tools import workflow as cli_mod

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "tools" / "workflow.py"
SUBPROCESS_TIMEOUT_S = 120


class _CliProject(Project):
    """Project с canonical github.com repo keys для production CLI."""

    def init(self, orchestrator=None, **overrides):
        overrides.setdefault("app_repo", c.APP_REPO_KEY)
        overrides.setdefault("tests_repo", c.TESTS_REPO_KEY)
        return super().init(orchestrator, **overrides)


def _absolutize_state(project, state):
    """Repo-relative записанные пути → абсолютные пути fixture checkout.

    Production CLI запускается с root=реальный репозиторий: recorded
    относительные пути (requirements, document'ы принятых артефактов,
    ключи `test_files_sha256`) должны разрешаться в файлы fixture.
    Абсолютные пути пропускаются scope-проверкой tests commit
    (`_commit_head_problems`), а в остальных местах резолвятся напрямую.
    """
    revision = state["input"]["revision_data"]
    req = revision.get("requirements") or {}
    if req.get("path") and not Path(req["path"]).is_absolute():
        req["path"] = str(project.root / req["path"])
    for artifact in (state.get("artifacts") or {}).values():
        doc = (artifact or {}).get("document") or {}
        if doc.get("path") and not Path(doc["path"]).is_absolute():
            doc["path"] = str(project.root / doc["path"])
    impl = (state.get("artifacts") or {}).get("implementation") or {}
    sha_map = impl.get("test_files_sha256") or {}
    impl["test_files_sha256"] = {
        (rel if Path(rel).is_absolute() else str(project.root / rel)): sha
        for rel, sha in sha_map.items()}
    # Изменённый requirements.path меняет canonical digest входа:
    # пересчитать привязки, чтобы fixture-state оставался самосогласованным
    # (artifact_digest привязан к payload+document.sha256, не к пути).
    inputs = state_mod.input_digest_map(state["input"]["identity"],
                                        revision)
    for artifact in (state.get("artifacts") or {}).values():
        bound = (artifact or {}).get("bound_input_digests") or {}
        for key in bound:
            bound[key] = inputs[key]
    for history in (state["input"].get("history") or []):
        history["revision_data_sha256"] = \
            state_mod.revision_data_digest(revision)


def _fixture(tmp_path):
    """Commit-head clean-tests проект до executed + абсолютные пути."""
    project = _CliProject(tmp_path)
    project.drive_commit_to_executed()
    workflow_dir = next(
        path for path in project.store_dir.iterdir()
        if path.is_dir() and state_mod.WORKFLOW_ID_RE.fullmatch(path.name))
    state = state_mod.load_state(workflow_dir)
    _absolutize_state(project, state)
    state_mod.save_state(workflow_dir, state)
    return project, workflow_dir


def _serialize_tree(tree):
    return {rel: base64.b64encode(content).decode("ascii")
            for rel, content in tree.items()}


def _git_entry(fake_git, fs_root):
    return {"fs_root": str(Path(fs_root).resolve()),
            "head": fake_git.head,
            "dirty": fake_git.dirty,
            "objects": dict(fake_git.objects),
            "commits": {sha: _serialize_tree(tree)
                        for sha, tree in fake_git.commits.items()}}


def _scenario(project, http_rules):
    git_map = {
        str(project.app_repo.resolve()):
            _git_entry(project.git, project.app_repo),
        str(project.root.resolve()):
            _git_entry(project.tests_git, project.root)}
    return {"git": git_map, "http": list(http_rules)}


def _pulls_re(full_name, suffix=r""):
    return rf"/repos/{full_name}/pulls{suffix}"


def _app_rules(project, workflow_dir, *, post_body=None, detail=None,
               files=None, detail_status=200, detail_error=None):
    """Стандартный набор правил fake HTTP для app PR."""
    title = f"[{workflow_dir.name}] {c.PR_TITLE}"
    payload = detail or gc.pr_payload(
        number=c.PR_NUMBER, title=title, body=c.BODY_TEXT,
        head_ref=c.HEAD_BRANCH, head_sha=wc.APP_HEAD_COMMIT_SHA,
        base_ref=c.BASE_BRANCH, base_sha=wc.APP_BASE_SHA,
        head_repo=c.APP_REPO_FULL, base_repo=c.APP_REPO_FULL,
        url=c.PR_URL,
        changed_files=len(files or [wc.CHANGED_APP_FILE]))
    if detail is None and detail_status == 200:
        detail = payload
    post = post_body if post_body is not None else payload
    file_entries = [{"filename": name, "status": "modified"}
                    for name in (files if files is not None
                                 else [wc.CHANGED_APP_FILE])]
    detail_rule = {"method": "GET",
                   "path_re": _pulls_re(c.APP_REPO_FULL,
                                        rf"/{c.PR_NUMBER}"),
                   "status": detail_status, "body": detail}
    if detail_error:
        detail_rule = {"method": "GET",
                       "path_re": _pulls_re(c.APP_REPO_FULL,
                                            rf"/{c.PR_NUMBER}"),
                       "error": "transport"}
    return [
        {"method": "GET",
         "path_re": _pulls_re(c.APP_REPO_FULL, r"\?.*"),
         "status": 200, "body": []},
        {"method": "GET",
         "path_re": _pulls_re(c.APP_REPO_FULL, rf"/{c.PR_NUMBER}/files\?.*"),
         "status": 200, "body": file_entries},
        detail_rule,
        {"method": "POST",
         "path_re": _pulls_re(c.APP_REPO_FULL),
         "status": 201, "body": post},
    ]


def _env(tmp_path, scenario, *, token=c.UNIT_TOKEN):
    site_dir = tmp_path / "site"
    site_dir.mkdir(exist_ok=True)
    (site_dir / "sitecustomize.py").write_text(
        c.SITECUSTOMIZE, encoding="utf-8")
    scenario_path = tmp_path / "scenario.json"
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
    log_path = tmp_path / "calls.jsonl"
    log_path.touch()
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(site_dir), str(ROOT)]
        + ([os.environ["PYTHONPATH"]]
           if os.environ.get("PYTHONPATH") else []))
    env[c.SCENARIO_ENV] = str(scenario_path)
    env[c.LOG_ENV] = str(log_path)
    env.pop("GITHUB_TOKEN", None)
    if token is not None:
        env["GITHUB_TOKEN"] = token
    return env, log_path


def _cli(args, env, store_dir):
    return subprocess.run(
        [sys.executable, str(CLI), "--store-dir", str(store_dir), *args],
        capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_S,
        env=env, cwd=str(ROOT))


def _events(log_path):
    return [json.loads(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _http(log_path, method=None):
    return [event for event in _events(log_path)
            if event.get("http")
            and (method is None or event["http"] == method)]


def _credentials(log_path):
    return [event for event in _events(log_path) if "credential" in event]


def _body_file(tmp_path):
    path = tmp_path / "pr-body.txt"
    path.write_text(c.BODY_TEXT, encoding="utf-8")
    return path


def _prepare_args(repo="app", body=None):
    args = ["pr", "prepare", "--repo", repo, "--title", c.PR_TITLE,
            "--head-branch", c.HEAD_BRANCH,
            "--base-branch", c.BASE_BRANCH,
            "--files", wc.CHANGED_APP_FILE if repo == "app"
            else wc.TEST_FILES[0]]
    if body is not None:
        args += ["--body", str(body)]
    return args


@allure.epic("Инфраструктура")
@allure.feature("Workflow CLI GitHub transport")
@allure.story("Парсинг глобального --pr-transport")
@allure.severity(allure.severity_level.NORMAL)
class TestCliParser:

    @allure.title("глобальный --pr-transport принимается до action; "
                  "после action отклоняется; недопустимое значение — exit 2")
    def test_global_flag_position(self, tmp_path):
        env, log_path = _env(tmp_path, {"git": {}, "http": []})
        store = tmp_path / "store"
        with allure.step("--pr-transport github до action парсится"):
            result = _cli(["--pr-transport", "github", "status"],
                          env, store)
            assert result.returncode != 2
        with allure.step("флаг после action — usage error"):
            result = _cli(["status", "--pr-transport", "github"],
                          env, store)
            assert result.returncode == 2
        with allure.step("недопустимое значение — usage error"):
            result = _cli(["--pr-transport", "bogus", "status"],
                          env, store)
            assert result.returncode == 2
        with allure.step("ноль HTTP/credential-чтений"):
            assert _http(log_path) == []
            assert _credentials(log_path) == []


@allure.epic("Инфраструктура")
@allure.feature("Workflow CLI GitHub transport")
@allure.story("Guard-матрица online/execute")
@allure.severity(allure.severity_level.CRITICAL)
class TestCliGuards:

    @allure.title("status/doctor/pr prepare с github transport: "
                  "ноль HTTP и ноль credential-чтений")
    def test_early_commands_zero_io(self, tmp_path):
        project, workflow_dir = _fixture(tmp_path)
        scenario = _scenario(project, _app_rules(project, workflow_dir))
        env, log_path = _env(tmp_path, scenario)
        body = _body_file(tmp_path)
        with allure.step("status"):
            result = _cli(["--pr-transport", "github", "status"],
                          env, project.store_dir)
            assert result.returncode == 0, result.stderr
        with allure.step("doctor"):
            result = _cli(["--pr-transport", "github", "doctor"],
                          env, project.store_dir)
            assert result.returncode == 0, result.stderr
        with allure.step("pr prepare (offline, без --online)"):
            result = _cli(["--pr-transport", "github"]
                          + _prepare_args(body=body),
                          env, project.store_dir)
            assert result.returncode == 0, result.stderr
            assert '"prepared"' in result.stdout
        with allure.step("reconcile/resume без --online"):
            for action in ("reconcile", "resume"):
                result = _cli(["--pr-transport", "github", action],
                              env, project.store_dir)
                assert result.returncode == 0, result.stderr
        with allure.step("ноль HTTP и ноль credential-чтений"):
            assert _http(log_path) == []
            assert _credentials(log_path) == []

    @allure.title("pr create/search без разрешающих флагов: exit 77/69, "
                  "ноль HTTP и ноль credential-чтений")
    @pytest.mark.parametrize("args", [
        ["pr", "create", "--repo", "app"],
        ["pr", "create", "--repo", "app", "--online"],
        ["pr", "create", "--repo", "app", "--execute"],
        ["pr", "search", "--repo", "app"],
    ])
    def test_blocked_without_flags(self, tmp_path, args):
        project, workflow_dir = _fixture(tmp_path)
        scenario = _scenario(project, _app_rules(project, workflow_dir))
        env, log_path = _env(tmp_path, scenario)
        with allure.step("prepare spec"):
            result = _cli(["--pr-transport", "github"] + _prepare_args(),
                          env, project.store_dir)
            assert result.returncode == 0, result.stderr
        with allure.step(f"запуск {' '.join(args)}"):
            result = _cli(["--pr-transport", "github"] + args,
                          env, project.store_dir)
            assert result.returncode == 77, result.stderr
            assert "online" in result.stderr or "transport" in result.stderr
        with allure.step("ноль HTTP и ноль credential-чтений"):
            assert _http(log_path) == []
            assert _credentials(log_path) == []

    @allure.title("default none: pr create --online --execute без флага "
                  "transport — permission, ноль HTTP")
    def test_default_none_blocks(self, tmp_path):
        project, workflow_dir = _fixture(tmp_path)
        scenario = _scenario(project, _app_rules(project, workflow_dir))
        env, log_path = _env(tmp_path, scenario)
        with allure.step("prepare spec"):
            result = _cli(_prepare_args(), env, project.store_dir)
            assert result.returncode == 0, result.stderr
        with allure.step("pr create --online --execute без --pr-transport"):
            result = _cli(["pr", "create", "--repo", "app",
                           "--online", "--execute"],
                          env, project.store_dir)
            assert result.returncode == 77
            assert "no PR transport" in result.stderr
        with allure.step("ноль HTTP и ноль credential-чтений"):
            assert _http(log_path) == []
            assert _credentials(log_path) == []

    @allure.title("нет GITHUB_TOKEN: pr create --online --execute "
                  "контролируемо блокируется, ноль HTTP")
    def test_missing_token(self, tmp_path):
        project, workflow_dir = _fixture(tmp_path)
        scenario = _scenario(project, _app_rules(project, workflow_dir))
        env, log_path = _env(tmp_path, scenario, token=None)
        with allure.step("prepare spec"):
            result = _cli(["--pr-transport", "github"] + _prepare_args(),
                          env, project.store_dir)
            assert result.returncode == 0, result.stderr
        with allure.step("pr create --online --execute без токена"):
            result = _cli(["--pr-transport", "github",
                           "pr", "create", "--repo", "app",
                           "--online", "--execute"],
                          env, project.store_dir)
            assert result.returncode == 69, result.stderr
        with allure.step("ровно одна попытка чтения credential, ноль HTTP"):
            assert _http(log_path) == []
            assert len(_credentials(log_path)) == 1


@allure.epic("Инфраструктура")
@allure.feature("Workflow CLI GitHub transport")
@allure.story("Достижимый verified create через production CLI")
@allure.severity(allure.severity_level.BLOCKER)
class TestCliCreate:

    @allure.title("app: prepare → create verified; "
                  "GET list + POST + detail/files/detail по счётчику")
    def test_app_create_verified(self, tmp_path):
        project, workflow_dir = _fixture(tmp_path)
        rules = _app_rules(project, workflow_dir)
        scenario = _scenario(project, rules)
        env, log_path = _env(tmp_path, scenario)
        with allure.step("prepare spec c durable body"):
            result = _cli(["--pr-transport", "github"]
                          + _prepare_args(body=_body_file(tmp_path)),
                          env, project.store_dir)
            assert result.returncode == 0, result.stderr
            assert '"prepared"' in result.stdout
        with allure.step("pr create --online --execute"):
            result = _cli(["--pr-transport", "github",
                           "pr", "create", "--repo", "app",
                           "--online", "--execute"],
                          env, project.store_dir)
            assert result.returncode == 0, result.stderr
            assert '"verified"' in result.stdout
        with allure.step("счётчики HTTP: 4 GET (list+files+2 detail), 1 POST"):
            posts = _http(log_path, "POST")
            gets = _http(log_path, "GET")
            assert len(posts) == 1
            assert len(gets) == 4
            detail_paths = [e["path"] for e in gets
                            if e["path"].endswith(f"/pulls/{c.PR_NUMBER}")]
            assert len(detail_paths) == 2
            files_paths = [e["path"] for e in gets if "/files" in e["path"]]
            assert len(files_paths) == 1
        with allure.step("повторный create — no-op verified, POST не растёт"):
            result = _cli(["--pr-transport", "github",
                           "pr", "create", "--repo", "app",
                           "--online", "--execute"],
                          env, project.store_dir)
            assert result.returncode == 0, result.stderr
            assert len(_http(log_path, "POST")) == 1
        with allure.step("credential прочитан только на authorized "
                         "запросы: search + create + get = 3"):
            credentials = _credentials(log_path)
            assert len(credentials) == 3
            assert all(e["credential"] == "GITHUB_TOKEN"
                       for e in credentials)

    @allure.title("tests: prepare → create verified по clean commit "
                  "и contract scope")
    def test_tests_create_verified(self, tmp_path):
        project, workflow_dir = _fixture(tmp_path)
        title = f"[{workflow_dir.name}] {c.PR_TITLE}"
        detail = gc.pr_payload(
            number=c.PR_NUMBER, title=title, body=c.BODY_TEXT,
            head_ref=c.HEAD_BRANCH, head_sha=wc.TESTS_COMMIT,
            base_ref=c.BASE_BRANCH, base_sha="b" * 40,
            head_repo=c.TESTS_REPO_FULL, base_repo=c.TESTS_REPO_FULL,
            url=c.TESTS_PR_URL, changed_files=len(wc.TEST_FILES))
        rules = [
            {"method": "GET",
             "path_re": _pulls_re(c.TESTS_REPO_FULL, r"\?.*"),
             "status": 200, "body": []},
            {"method": "GET",
             "path_re": _pulls_re(c.TESTS_REPO_FULL,
                                  rf"/{c.PR_NUMBER}/files\?.*"),
             "status": 200,
             "body": [{"filename": name, "status": "modified"}
                      for name in wc.TEST_FILES]},
            {"method": "GET",
             "path_re": _pulls_re(c.TESTS_REPO_FULL, rf"/{c.PR_NUMBER}"),
             "status": 200, "body": detail},
            {"method": "POST",
             "path_re": _pulls_re(c.TESTS_REPO_FULL),
             "status": 201, "body": detail},
        ]
        scenario = _scenario(project, rules)
        env, log_path = _env(tmp_path, scenario)
        with allure.step("prepare spec"):
            result = _cli(["--pr-transport", "github"]
                          + _prepare_args(repo="tests",
                                          body=_body_file(tmp_path)),
                          env, project.store_dir)
            assert result.returncode == 0, result.stderr
        with allure.step("pr create --online --execute"):
            result = _cli(["--pr-transport", "github",
                           "pr", "create", "--repo", "tests",
                           "--online", "--execute"],
                          env, project.store_dir)
            assert result.returncode == 0, result.stderr
            assert '"verified"' in result.stdout
        with allure.step("счётчики: 4 GET, 1 POST на tests repo endpoint"):
            assert len(_http(log_path, "POST")) == 1
            assert len(_http(log_path, "GET")) == 4
            assert all(c.TESTS_REPO_FULL in e["path"]
                       for e in _http(log_path))


@allure.epic("Инфраструктура")
@allure.feature("Workflow CLI GitHub transport")
@allure.story("Crash/unknown границы: ноль новых POST")
@allure.severity(allure.severity_level.CRITICAL)
class TestCliRecovery:

    @allure.title("POST transport error → unknown+[]: reconcile blocked, "
                  "повторный create не диспатчит второй POST")
    def test_unknown_empty_search_no_recreate(self, tmp_path):
        project, workflow_dir = _fixture(tmp_path)
        rules = _app_rules(project, workflow_dir)
        rules[3] = {"method": "POST",
                    "path_re": _pulls_re(c.APP_REPO_FULL),
                    "error": "transport"}
        scenario = _scenario(project, rules)
        env, log_path = _env(tmp_path, scenario)
        with allure.step("prepare spec"):
            result = _cli(["--pr-transport", "github"] + _prepare_args(),
                          env, project.store_dir)
            assert result.returncode == 0, result.stderr
        with allure.step("create: POST падает — outcome unknown"):
            result = _cli(["--pr-transport", "github",
                           "pr", "create", "--repo", "app",
                           "--online", "--execute"],
                          env, project.store_dir)
            assert result.returncode == 75, result.stderr
        with allure.step("reconcile --online: пустой search не доказывает "
                         "отсутствие — blocked, intent unresolved"):
            result = _cli(["--pr-transport", "github",
                           "reconcile", "--online"],
                          env, project.store_dir)
            assert result.returncode == 0, result.stderr
            assert '"blocked"' in result.stdout
        with allure.step("повторный create — blocked без нового POST"):
            result = _cli(["--pr-transport", "github",
                           "pr", "create", "--repo", "app",
                           "--online", "--execute"],
                          env, project.store_dir)
            assert result.returncode == 69, result.stderr
            assert len(_http(log_path, "POST")) == 1

    @allure.title("созданный номер 404 на get: create → created, повтор "
                  "blocked, новый POST не диспатчится")
    def test_known_number_404_no_recreate(self, tmp_path):
        project, workflow_dir = _fixture(tmp_path)
        rules = _app_rules(project, workflow_dir, detail_status=404)
        scenario = _scenario(project, rules)
        env, log_path = _env(tmp_path, scenario)
        with allure.step("prepare spec"):
            result = _cli(["--pr-transport", "github"] + _prepare_args(),
                          env, project.store_dir)
            assert result.returncode == 0, result.stderr
        with allure.step("create: POST 201, verification get 404 — created"):
            result = _cli(["--pr-transport", "github",
                           "pr", "create", "--repo", "app",
                           "--online", "--execute"],
                          env, project.store_dir)
            assert result.returncode == 0, result.stderr
            assert '"created"' in result.stdout
            assert len(_http(log_path, "POST")) == 1
        with allure.step("записанный номер durable в state"):
            state = state_mod.load_state(workflow_dir)
            entry = state["publications"]["pr"]["app"]
            assert entry["status"] == "created"
            assert entry["number"] == c.PR_NUMBER
        with allure.step("повторный create: targeted get 404 — blocked, "
                         "POST не растёт"):
            result = _cli(["--pr-transport", "github",
                           "pr", "create", "--repo", "app",
                           "--online", "--execute"],
                          env, project.store_dir)
            assert result.returncode == 69, result.stderr
            assert len(_http(log_path, "POST")) == 1
            assert len(_http(log_path, "GET")) == 3

    @allure.title("crash на читаемом номере: minimal ref → created; "
                  "ошибка get при повторе — unknown, ноль новых POST")
    def test_unreadable_create_number_no_recreate(self, tmp_path):
        project, workflow_dir = _fixture(tmp_path)
        minimal = {"number": c.PR_NUMBER, "html_url": c.PR_URL}
        rules = _app_rules(project, workflow_dir, post_body=minimal,
                           detail_error="transport")
        scenario = _scenario(project, rules)
        env, log_path = _env(tmp_path, scenario)
        with allure.step("prepare spec"):
            result = _cli(["--pr-transport", "github"] + _prepare_args(),
                          env, project.store_dir)
            assert result.returncode == 0, result.stderr
        with allure.step("create: только номер/url читаемы → created"):
            result = _cli(["--pr-transport", "github",
                           "pr", "create", "--repo", "app",
                           "--online", "--execute"],
                          env, project.store_dir)
            assert result.returncode == 0, result.stderr
            assert '"created"' in result.stdout
        with allure.step("номер записан до verification"):
            state = state_mod.load_state(workflow_dir)
            entry = state["publications"]["pr"]["app"]
            assert entry["status"] == "created"
            assert entry["number"] == c.PR_NUMBER
        with allure.step("повторный create: targeted get падает — "
                         "unknown, второй POST запрещён"):
            result = _cli(["--pr-transport", "github",
                           "pr", "create", "--repo", "app",
                           "--online", "--execute"],
                          env, project.store_dir)
            assert result.returncode == 75, result.stderr
            assert len(_http(log_path, "POST")) == 1


@allure.epic("Инфраструктура")
@allure.feature("Workflow CLI GitHub transport")
@allure.story("Программный wiring и полная цепочка с настоящим transport")
@allure.severity(allure.severity_level.CRITICAL)
class TestProgrammaticWiring:

    @staticmethod
    def _options(**kw):
        base = dict(action="status", pr_action=None,
                    pr_transport="none", store_dir=None)
        base.update(kw)
        return argparse.Namespace(**base)

    @allure.title("_orchestrator: github wiring в app/tests одним "
                  "объектом, lazy без I/O; none и ранние команды — пусто")
    def test_transport_wiring_roles(self, monkeypatch):
        calls = []
        monkeypatch.setattr(github.EnvGitHubToken, "__call__",
                            lambda self: calls.append(self) or "x")
        monkeypatch.setattr(github.UrllibHttp, "request",
                            lambda *a, **k: calls.append("http"))
        with allure.step("github на dispatch-команде → обе роли"):
            orchestrator = cli_mod._orchestrator(
                self._options(action="pr", pr_action="create",
                              pr_transport="github"))
            transport = orchestrator.pr_transports["app"]
            assert isinstance(transport, github.GitHubPrTransport)
            assert orchestrator.pr_transports["tests"] is transport
        with allure.step("github на search/reconcile/resume тоже wired"):
            for options in (self._options(action="pr",
                                          pr_action="search",
                                          pr_transport="github"),
                            self._options(action="reconcile",
                                          pr_transport="github"),
                            self._options(action="resume",
                                          pr_transport="github")):
                o = cli_mod._orchestrator(options)
                assert isinstance(o.pr_transports["app"],
                                  github.GitHubPrTransport)
        with allure.step("github на ранних командах и default none — без "
                         "transport"):
            for options in (
                    self._options(action="status",
                                  pr_transport="github"),
                    self._options(action="doctor",
                                  pr_transport="github"),
                    self._options(action="init",
                                  pr_transport="github"),
                    self._options(action="pr", pr_action="prepare",
                                  pr_transport="github"),
                    self._options(action="pr", pr_action="create",
                                  pr_transport="none"),
                    self._options(action="pr", pr_action="create")):
                assert cli_mod._orchestrator(options).pr_transports == {}
        with allure.step("конструктор не вызывал provider и не делал HTTP"):
            assert calls == []

    @allure.title("полная цепочка Orchestrator + GitHubPrTransport: "
                  "verified create и порядок detail→files→detail")
    def test_full_chain_order(self, tmp_path):
        project = _CliProject(tmp_path)
        project.drive_commit_to_executed()
        workflow_dir = next(
            path for path in project.store_dir.iterdir()
            if path.is_dir()
            and state_mod.WORKFLOW_ID_RE.fullmatch(path.name))

        class FakeHttp:
            def __init__(self):
                self.calls = []

            def request(self, endpoint, method, path, *, headers=None,
                        payload=None):
                self.calls.append((method, path))
                detail = gc.pr_payload(
                    number=c.PR_NUMBER,
                    title=spec_holder["title"], body=c.BODY_TEXT,
                    head_ref=c.HEAD_BRANCH,
                    head_sha=wc.APP_HEAD_COMMIT_SHA,
                    base_ref=c.BASE_BRANCH, base_sha=wc.APP_BASE_SHA,
                    head_repo=c.APP_REPO_FULL,
                    base_repo=c.APP_REPO_FULL,
                    changed_files=1)
                if method == "POST":
                    return HttpResponse(201, json.dumps(detail).encode(),
                                        {})
                if "/files" in path:
                    return HttpResponse(
                        200, json.dumps(
                            [{"filename": wc.CHANGED_APP_FILE,
                              "status": "modified"}]).encode(), {})
                if path.endswith(f"/pulls/{c.PR_NUMBER}"):
                    return HttpResponse(200, json.dumps(detail).encode(),
                                        {})
                return HttpResponse(200, b"[]", {})

        spec_holder = {}
        http = FakeHttp()
        tokens = []
        transport = github.GitHubPrTransport(
            token_provider=lambda: tokens.append(1) or c.UNIT_TOKEN,
            http=http)
        orchestrator = project.orchestrator(
            pr_transports={"app": transport, "tests": transport})
        with allure.step("prepare spec"):
            body = _body_file(tmp_path)
            result = orchestrator.pr_prepare(
                "app", title=c.PR_TITLE, head_branch=c.HEAD_BRANCH,
                base_branch=c.BASE_BRANCH, files=[wc.CHANGED_APP_FILE],
                body_path=body)
            assert result["outcome"] == "prepared"
            state = project.workflow_state()
            spec = state["publications"]["pr"]["app"]["spec"]
            spec_holder["title"] = spec["title"]
        with allure.step("create verified одним POST"):
            result = orchestrator.pr_create("app", execute=True,
                                            online=True)
            assert result["outcome"] == "verified"
            assert result["number"] == c.PR_NUMBER
            assert [m for m, _ in http.calls].count("POST") == 1
        with allure.step("порядок GET: list → detail → files → detail"):
            paths = [p for m, p in http.calls if m == "GET"]
            assert paths[0].startswith("/repos/" + c.APP_REPO_FULL
                                      + "/pulls?")
            assert paths[1].endswith(f"/pulls/{c.PR_NUMBER}")
            assert "/files?" in paths[2]
            assert paths[3].endswith(f"/pulls/{c.PR_NUMBER}")
        with allure.step("token provider вызван только в authorized "
                         "запросах"):
            assert len(tokens) == 3
