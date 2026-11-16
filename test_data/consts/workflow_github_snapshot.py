"""Фиктивные данные snapshot-регрессий `GitHubPrTransport.get` (22AR).

Значения для проверки полноты files и согласованности повторного
detail-чтения; все идентификаторы, SHA и URL вымышленные. Базовые
фикстуры импортируются из `test_data.consts.workflow_github`.
"""
from test_data.consts import workflow_github as base

ALT_HEAD_SHA = "7" * 40
ALT_BASE_SHA = "b" * 40
ALT_NUMBER = 555
ALT_TITLE = base.TITLE + " v2"
ALT_BODY_TEXT = "Изменённое тело PR\n"
ALT_URL = f"https://github.com/{base.REPO_FULL_NAME}/pull/{ALT_NUMBER}"
FOREIGN_REPO_FULL_NAME = "Fork-Org/Fork-Repo"
ALT_HEAD_BRANCH = "wf/other-head"
ALT_BASE_BRANCH = "release"

# docs.github.com /en/rest/pulls/pulls (2026-11-16): «Responses include a
# maximum of 3000 files» — выше него полнота недоказуема.
DOCUMENTED_FILE_LIMIT = 3000
OVER_LIMIT_COUNT = DOCUMENTED_FILE_LIMIT + 1

# Пять уникальных файлов — три страницы при PAGE_SIZE=2.
MANY_FILES = ["src/f0.py", "src/f1.py", "src/f2.py", "src/f3.py",
              "src/f4.py"]

# Поля PR detail, которые обязаны совпасть в двух чтениях get.
DRIFT_FIELDS = ("head_sha", "base_sha", "head_branch", "base_branch",
                "title", "body", "draft", "state", "merged",
                "changed_files", "head_repo", "number", "url")

TESTS_REPO_KEY = "github.com/Unit-Tests-Org/Unit-Tests-Repo"
