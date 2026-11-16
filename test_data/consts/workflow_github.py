"""Фиктивные данные unit-проверок GitHubPrTransport; реальных ID/токенов нет.

Payload'ы повторяют форму GitHub REST API (Pull Request / Pull Request
Simple / Diff Entry / Link pagination) по официальной документации
docs.github.com от 2026-11-16, но все идентификаторы, SHA, токены и URL
вымышленные и не относятся к реальным репозиториям или проекту Niffler.
"""
import hashlib
from urllib.parse import urlencode

OWNER = "Unit-Org"
NAME = "Unit-Repo"
REPO_FULL_NAME = f"{OWNER}/{NAME}"
REPO_KEY = f"github.com/{REPO_FULL_NAME}"
API_ENDPOINT = "https://api.github.com"
TOKEN = "unit-gh-token"
TOKEN_ENV = "UNIT_GH_TOKEN_VAR"

HEAD_BRANCH = "wf/unit-head"
BASE_BRANCH = "main"
TITLE_KEY = "[wf-0123456789abcdef]"
TITLE = f"{TITLE_KEY} unit PR"
NUMBER = 137
OTHER_NUMBER = 55
HEAD_SHA = "1" * 40
BASE_SHA = "a" * 40
FOREIGN_HEAD_SHA = "9" * 40

PAGE_SIZE = 2
MAX_PAGES = 4

BODY_TEXT = "Тело PR\nвторая строка\n"
BODY_SHA256 = hashlib.sha256(BODY_TEXT.encode("utf-8")).hexdigest()
OTHER_BODY_TEXT = "Other body\n"
OTHER_BODY_SHA256 = hashlib.sha256(
    OTHER_BODY_TEXT.encode("utf-8")).hexdigest()

SEARCH_KEY = {"repo": REPO_KEY, "head_branch": HEAD_BRANCH,
              "base_branch": BASE_BRANCH, "title_key": TITLE_KEY}
FILES = ["src/b.py", "src/a.py", "src/c.py"]

SPEC = {"repo": REPO_KEY, "title_key": TITLE_KEY, "title": TITLE,
        "body_sha256": BODY_SHA256, "body_text": BODY_TEXT,
        "files": list(FILES), "head_branch": HEAD_BRANCH,
        "base_branch": BASE_BRANCH, "head_sha": HEAD_SHA,
        "spec_sha256": "f" * 64}


def spec(**overrides):
    value = dict(SPEC)
    value.update(overrides)
    return value


def repo_obj(full_name=REPO_FULL_NAME):
    return {"full_name": full_name, "id": 4242}


def pr_payload(number=NUMBER, state="open", draft=True, title=TITLE,
               body=BODY_TEXT, head_ref=HEAD_BRANCH, head_sha=HEAD_SHA,
               base_ref=BASE_BRANCH, base_sha=BASE_SHA,
               head_repo=REPO_FULL_NAME, base_repo=REPO_FULL_NAME,
               merged=False, url=None, changed_files=len(FILES)):
    """Минимальный набор полей Pull Request, используемый transport'ом."""
    head = {"ref": head_ref, "sha": head_sha,
            "repo": repo_obj(head_repo) if head_repo is not None else None}
    base = {"ref": base_ref, "sha": base_sha,
            "repo": repo_obj(base_repo) if base_repo is not None else None}
    return {"number": number, "state": state, "title": title,
            "html_url": url or f"https://github.com/{REPO_FULL_NAME}"
                               f"/pull/{number}",
            "draft": draft, "body": body, "head": head, "base": base,
            "merged": merged, "changed_files": changed_files,
            "user": {"login": "unit"},
            "created_at": "2026-01-01T00:00:00Z"}


def file_payload(filename, status="modified"):
    return {"filename": filename, "status": status, "sha": "c" * 40,
            "additions": 1, "deletions": 1, "changes": 2,
            "blob_url": "https://api.github.com/x",
            "raw_url": "https://api.github.com/y",
            "contents_url": "https://api.github.com/z"}


def pulls_path(page=1, size=PAGE_SIZE, head=HEAD_BRANCH, base=BASE_BRANCH):
    """Путь list-эндпоинта в порядке параметров, строимом transport'ом."""
    params = {"state": "all"}
    if head is not None:
        params["head"] = f"{OWNER}:{head}"
    if base is not None:
        params["base"] = base
    params["per_page"] = size
    params["page"] = page
    return f"/repos/{OWNER}/{NAME}/pulls?" + urlencode(params)


def pr_path(number=NUMBER):
    return f"/repos/{OWNER}/{NAME}/pulls/{number}"


def files_path(page=1, size=PAGE_SIZE, number=NUMBER):
    params = {"per_page": size, "page": page}
    return f"/repos/{OWNER}/{NAME}/pulls/{number}/files?" \
        + urlencode(params)


def next_link(path):
    """Валидный rel="next" Link header; URL никогда не dereference'ится."""
    return f'<{API_ENDPOINT}{path}>; rel="next"'


FOREIGN_NEXT_LINK = '<https://evil.example/steal?page=2>; rel="next"'
MALFORMED_LINK = "link-without-entries"
