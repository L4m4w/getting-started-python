"""Фиктивные canonical remote identity tests-репозитория (33-P-A).

Все значения вымышленные и не относятся к реальным GitHub-ресурсам или
проекту Niffler; используются только в unit-проверках в temp dirs.
Canonical форма — ``github.com/owner/repo``; принятые spellings
(http/https/ssh/git URL, scp-подобный ``git@host:path``, суффикс
``.git`` и завершающий ``/``) нормализуются в неё.
"""

TESTS_REPO = "https://github.com/Unit-Tests-Org/Unit-Tests-Repo.git"
TESTS_REPO_HTTP = "http://github.com/Unit-Tests-Org/Unit-Tests-Repo"
TESTS_REPO_SSH = "ssh://github.com/Unit-Tests-Org/Unit-Tests-Repo.git"
TESTS_REPO_GIT = "git://github.com/Unit-Tests-Org/Unit-Tests-Repo/"
TESTS_REPO_SCP = "git@github.com:Unit-Tests-Org/Unit-Tests-Repo.git"
TESTS_REPO_UPPER_HOST = "GitHub.com/Unit-Tests-Org/Unit-Tests-Repo"
TESTS_REPO_KEY = "github.com/Unit-Tests-Org/Unit-Tests-Repo"
TESTS_REPO_OTHER_KEY = "github.com/Unit-Tests-Org/Other-Tests-Repo"

INVALID_TESTS_REPO_INPUTS = (
    "/abs/local/tests",
    "relative/local/path",
    "owner/repo",
    "github.com",
    "github.com/owner",
    "github.com/owner/repo/extra",
    "github.com/../repo",
    "github.com/owner/../repo",
    "git.invalid/Unit-Tests-Org/Unit-Tests-Repo",
    "ftp://github.com/Unit-Tests-Org/Unit-Tests-Repo",
    "https://user@github.com/Unit-Tests-Org/Unit-Tests-Repo",
    "https://github.com:8443/Unit-Tests-Org/Unit-Tests-Repo",
    "https://github.com/Unit-Tests-Org/Unit-Tests-Repo?x=1",
    "https://github.com/Unit-Tests-Org/Unit-Tests-Repo#frag",
    "ssh://git@github.com/Unit-Tests-Org/Unit-Tests-Repo",
    "git@github.com",
    "git@github.com/Unit-Tests-Org/Unit-Tests-Repo",
    "",
    "   ",
)

# Raw traversal / separator anomalies refused BEFORE normalization —
# checking only the normalized key would silently re-brand them into a
# valid canonical identity (F33-A1).
TRAVERSAL_TESTS_REPO_INPUTS = (
    "github.com/Unit-Tests-Org/ignored/../Unit-Tests-Repo",
    "github.com/Unit-Tests-Org/./Unit-Tests-Repo",
    "github.com/Unit-Tests-Org//Unit-Tests-Repo",
    "github.com/Unit-Tests-Org/Unit-Tests-Repo//",
    "https://github.com/Unit-Tests-Org/ignored/../Unit-Tests-Repo",
    "https://github.com/Unit-Tests-Org/./Unit-Tests-Repo",
    "git@github.com:Unit-Tests-Org/../Unit-Tests-Repo",
    "git@github.com:Unit-Tests-Org/./Unit-Tests-Repo",
    "git@github.com:Unit-Tests-Org//Unit-Tests-Repo",
)
