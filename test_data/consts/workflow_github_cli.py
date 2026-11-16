"""Фиктивные данные 22C CLI-проверок `--pr-transport github`; секретов нет.

Псевдо-репозитории/номера/URL вымышленные и не относятся к реальным
GitHub-ресурсам или проекту Niffler. `SCENARIO_ENV`/`LOG_ENV` — имена
переменных окружения, которыми unit-тесты передают offline-сценарий
fake HTTP/git в production CLI subprocess; реальных сетевых хостов,
токенов и endpoint'ов в них нет.
"""

APP_OWNER = "Unit-Org"
APP_NAME = "Unit-Repo"
APP_REPO_FULL = f"{APP_OWNER}/{APP_NAME}"
APP_REPO_KEY = f"github.com/{APP_REPO_FULL}"

TESTS_OWNER = "Unit-Tests-Org"
TESTS_NAME = "Unit-Tests-Repo"
TESTS_REPO_FULL = f"{TESTS_OWNER}/{TESTS_NAME}"
TESTS_REPO_KEY = f"github.com/{TESTS_REPO_FULL}"

PR_TITLE = "unit CLI PR"
HEAD_BRANCH = "wf/22c-head"
BASE_BRANCH = "main"
PR_NUMBER = 137
PR_URL = f"https://github.com/{APP_REPO_FULL}/pull/{PR_NUMBER}"
TESTS_PR_URL = f"https://github.com/{TESTS_REPO_FULL}/pull/{PR_NUMBER}"
BODY_TEXT = "CLI-тело PR\nвторая строка\n"

UNIT_TOKEN = "unit-cli-gh-token"

# Имена env-переменных fake bootstrap'а: файл JSON-сценария и лог вызовов.
SCENARIO_ENV = "WF_GH_FAKE_SCENARIO"
LOG_ENV = "WF_GH_FAKE_LOG"

# Bootstrap для subprocess-проверок production CLI: по SCENARIO_ENV заменяет
# только http-слой GitHubPrTransport и GitReadAdapter (по зарегистрированным
# repo_path; незнакомые checkout'ы получают реальный адаптер) и считает
# credential-чтения провайдера. Никакой новый endpoint/флаг отключения
# guard'ов в production не вводится: transport остаётся привязанным к
# api.github.com и обычным online/execute guard'ам.
SITECUSTOMIZE = '''\
"""22C fake bootstrap: offline GitHub HTTP + git для CLI subprocess."""
import base64
import hashlib
import json
import os
import re
import sys
from pathlib import Path

_SCEN_ENV = "WF_GH_FAKE_SCENARIO"
_LOG_ENV = "WF_GH_FAKE_LOG"

if os.environ.get(_SCEN_ENV) and os.environ.get(_LOG_ENV):
    _scenario = json.loads(Path(os.environ[_SCEN_ENV]).read_text())
    _log_path = Path(os.environ[_LOG_ENV])

    def _log_event(event):
        with _log_path.open("a", encoding="utf-8") as out:
            out.write(json.dumps(event, sort_keys=True) + "\\n")

    from infrastructure.workflow import adapters as _adapters
    from infrastructure.workflow import github as _gh
    from infrastructure.workflow import state as _st

    _RealGit = _adapters.GitReadAdapter

    def _git_key(repo_path):
        candidate = Path(str(repo_path))
        if candidate.is_absolute():
            return str(candidate.resolve())
        return str(repo_path)

    class _FakeGit:
        def __init__(self, repo_path):
            entry = _scenario["git"][_git_key(repo_path)]
            self._fs_root = Path(entry["fs_root"]).resolve()
            self._head = entry.get("head")
            self._dirty = bool(entry.get("dirty"))
            self._commits = {}
            for sha, tree in (entry.get("commits") or {}).items():
                self._commits[sha.lower()] = {
                    rel: base64.b64decode(content)
                    if isinstance(content, str) else bytes(content)
                    for rel, content in tree.items()}
            self._objects = {sha.lower(): kind for sha, kind
                             in (entry.get("objects") or {}).items()}
            _log_event({"git": "fake-open", "repo": str(repo_path)})

        def _norm(self, relpath):
            if not isinstance(relpath, str) or not relpath:
                return None
            candidate = Path(relpath)
            if candidate.is_absolute():
                try:
                    return candidate.relative_to(self._fs_root).as_posix()
                except ValueError:
                    return None
            if ".." in candidate.parts:
                return None
            return relpath

        def file_bytes(self, relpath):
            path = (self._fs_root / relpath).resolve()
            try:
                path.relative_to(self._fs_root)
            except ValueError:
                return None
            return path.read_bytes() if path.is_file() else None

        def file_sha256(self, relpath):
            data = self.file_bytes(relpath)
            return (hashlib.sha256(data).hexdigest()
                    if data is not None else None)

        def git_blob(self, relpath):
            data = self.file_bytes(relpath)
            if data is None:
                return None
            return hashlib.sha1(
                b"blob %d\\x00" % len(data) + data).hexdigest()

        def head_commit(self):
            return self._head

        def is_dirty(self):
            return self._dirty

        def object_type(self, rev):
            if not isinstance(rev, str) or not _st.HEX40_64.fullmatch(rev):
                return None
            key = rev.lower()
            if key in self._commits:
                return "commit"
            return self._objects.get(key)

        def commit_file_bytes(self, commit_sha, relpath):
            rel = self._norm(relpath)
            if rel is None or not isinstance(commit_sha, str):
                return None
            tree = self._commits.get(commit_sha.lower())
            if tree is None:
                return None
            return tree.get(rel)

        def commit_file_sha256(self, commit_sha, relpath):
            data = self.commit_file_bytes(commit_sha, relpath)
            return (hashlib.sha256(data).hexdigest()
                    if data is not None else None)

        def commit_blob(self, commit_sha, relpath):
            data = self.commit_file_bytes(commit_sha, relpath)
            if data is None:
                return None
            return hashlib.sha1(
                b"blob %d\\x00" % len(data) + data).hexdigest()

        def changed_files(self, base_sha, head_sha):
            base = self._commits.get((base_sha or "").lower())
            head = self._commits.get((head_sha or "").lower())
            if base is None or head is None:
                return None
            return sorted(path for path in set(base) | set(head)
                          if base.get(path) != head.get(path))

    def _git_or_real(repo_path):
        if _git_key(repo_path) in _scenario["git"]:
            return _FakeGit(repo_path)
        _log_event({"git": "real-fallback", "repo": str(repo_path)})
        return _RealGit(repo_path)

    class _Resp:
        def __init__(self, status, body, link=None):
            self.status = status
            self.body = (body if isinstance(body, (str, bytes))
                         else json.dumps(body))
            self.headers = {"link": link} if link else {}

    class _FakeHttp:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, endpoint, method, path, *, headers=None,
                    payload=None):
            _log_event({"http": method, "path": path,
                        "endpoint": endpoint})
            for rule in _scenario.get("http", []):
                if (rule.get("method") == method
                        and re.fullmatch(rule.get("path_re", r"\\Z(?!x)"),
                                         path)):
                    if rule.get("error") == "transport":
                        raise OSError("fake transport error")
                    return _Resp(rule.get("status", 200),
                                 rule.get("body", []),
                                 link=rule.get("link"))
            return _Resp(404, {"message": "no fake route"})

    _EnvToken = _gh.EnvGitHubToken

    class _CountedEnvToken(_EnvToken):
        def __call__(self):
            _log_event({"credential": self._env_var})
            return super().__call__()

    _gh.EnvGitHubToken = _CountedEnvToken
    _gh.UrllibHttp = _FakeHttp
    _adapters.GitReadAdapter = _git_or_real
'''
