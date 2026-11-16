"""33-P-A регрессии: canonical immutable tests repo identity.

Покрытие чистого parser'а ``require_remote_repo_key`` (принятые
http/https/ssh/git/scp/``.git`` spellings нормализуются в
``github.com/owner/repo``; local/bare/traversal/userinfo/port/query/
fragment отклоняются без HTTP и token reads), записи
``identity.tests_repo`` через ``init --tests-repo``, optional
legacy-чтения state без поля, immutable resume-контракта до записей
state/index и выдачи canonical key в tests PR spec. Всё offline в
temp dirs; реальный temp Git checkout создаётся только внутри tmp_path.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import allure
import pytest

from infrastructure.workflow import adapters, github
from infrastructure.workflow import index as index_mod
from infrastructure.workflow import state as state_mod
from infrastructure.workflow.state import (
    WorkflowBlockedError, WorkflowSchemaError,
    WorkflowValidationError)
from test_data.consts import workflow as C
from test_data.consts import workflow_tests_repo as RC
from test_data.utils import workflow as utils

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "tools" / "workflow.py"


@pytest.fixture
def project(tmp_path):
    return utils.Project(tmp_path / "proj")


def _workflow_dir(project):
    return next(
        path for path in project.store_dir.iterdir()
        if path.is_dir()
        and state_mod.WORKFLOW_ID_RE.fullmatch(path.name))


def _drop_tests_repo_identity(project):
    """Synthetic consistent legacy fixture; production state is never migrated."""
    workflow_dir = _workflow_dir(project)
    path = state_mod.state_path(workflow_dir)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["input"]["identity"].pop("tests_repo", None)
    # Construct a self-consistent pre-field fixture, not a corrupt modern state.
    # A real old context was accepted against the identity without tests_repo.
    context = data["artifacts"].get("context") or {}
    if context.get("status") == "accepted":
        context["bound_input_digests"]["identity"] = (
            state_mod.canonical_digest(data["input"]["identity"]))
    state_mod.validate_state(data)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def _store_tree(project):
    """No-write snapshot всего workflow store (33R-A).

    Каждая запись под ``store_dir`` фиксируется: директории (включая
    пустые) как ``("dir",)``, файлы как ``("file", sha256, mtime_ns)``
    и symlink'и как ``("symlink", target text)``. Документированное
    исключение — transient lock-артефакты (``*.lock``/``*.lock-gate``):
    отклонённый init мог успеть создать lock gate до отказа, поэтому
    они отфильтровываются как механический шум, а не содержимое
    index/state. Mtime директорий исключено по той же причине (создание
    и удаление lock-файла трогает родительскую директорию). Сравнение
    снимков доказывает «нет записей index/state»: совпадают байты И
    mtime, а не только содержимое.
    """
    store = project.store_dir
    tree = {}
    if not store.is_dir():
        return tree
    for path in sorted(store.rglob("*")):
        rel = path.relative_to(store).as_posix()
        if path.name.endswith((".lock", ".lock-gate")):
            continue
        if path.is_symlink():
            tree[rel] = ("symlink", str(path.readlink()))
        elif path.is_dir():
            tree[rel] = ("dir",)
        elif path.is_file():
            info = path.stat()
            tree[rel] = ("file",
                         hashlib.sha256(path.read_bytes()).hexdigest(),
                         info.st_mtime_ns)
        else:
            tree[rel] = ("other",)
    return tree


@allure.epic("Инфраструктура")
@allure.feature("Workflow tests repo identity")
@allure.story("Строгий parser canonical remote key")
@allure.severity(allure.severity_level.CRITICAL)
class TestRemoteRepoKeyParser:

    @allure.title("принятые spellings нормализуются в canonical key")
    @pytest.mark.parametrize("value", [
        RC.TESTS_REPO, RC.TESTS_REPO_HTTP, RC.TESTS_REPO_SSH,
        RC.TESTS_REPO_GIT, RC.TESTS_REPO_SCP, RC.TESTS_REPO_KEY,
        RC.TESTS_REPO_UPPER_HOST])
    def test_accepted_spellings(self, value):
        assert state_mod.require_remote_repo_key(
            value, "tests_repo") == RC.TESTS_REPO_KEY

    @allure.title("local/bare/traversal/userinfo/port/query/fragment "
                  "отклоняются")
    @pytest.mark.parametrize("value", RC.INVALID_TESTS_REPO_INPUTS)
    def test_rejected_inputs(self, value):
        with pytest.raises(WorkflowValidationError):
            state_mod.require_remote_repo_key(value, "tests_repo")

    @allure.title("raw traversal не нормализуется в canonical key "
                  "(проверка до normalize во всех формах)")
    @pytest.mark.parametrize("value", RC.TRAVERSAL_TESTS_REPO_INPUTS)
    def test_traversal_rejected(self, value):
        with pytest.raises(WorkflowValidationError):
            state_mod.require_remote_repo_key(value, "tests_repo")

    @allure.title("не-строки отклоняются")
    @pytest.mark.parametrize("value", [None, 17, ["a/b"], {}])
    def test_rejected_types(self, value):
        with pytest.raises(WorkflowValidationError):
            state_mod.require_remote_repo_key(value, "tests_repo")

    @allure.title("тот же owner/repo контракт, что у transport "
                  "без его конструирования")
    def test_transport_contract_shared(self, tmp_path):
        parse = github.GitHubPrTransport._parse_repo_key
        assert parse(RC.TESTS_REPO_KEY) == ("Unit-Tests-Org",
                                            "Unit-Tests-Repo")
        for value in (str(tmp_path), "/abs/local", "owner/repo",
                      "git.invalid/o/r", "github.com/o/r/extra"):
            with pytest.raises(github.GitHubSpecError):
                parse(value)
            with pytest.raises(WorkflowValidationError):
                state_mod.require_remote_repo_key(value, "tests_repo")


@allure.epic("Инфраструктура")
@allure.feature("Workflow tests repo identity")
@allure.story("init --tests-repo → immutable identity.tests_repo")
@allure.severity(allure.severity_level.BLOCKER)
class TestInitIdentity:

    @allure.title("init записывает canonical tests_repo; workflow_id "
                  "и local path неизменны")
    def test_init_records_canonical(self, project):
        orchestrator = project.orchestrator()
        workflow_id, outcome = project.init(orchestrator)
        assert outcome == "created"
        state = project.workflow_state()
        assert state["input"]["identity"]["tests_repo"] \
            == RC.TESTS_REPO_KEY
        assert state["input"]["locals"]["tests_repo_path"] \
            == str(project.root)
        assert workflow_id == state_mod.workflow_id_for(
            C.PILOT_ID, C.APP_REPO_KEY, C.APP_BASE_SHA)

    @allure.title("принятые spellings init → тот же canonical key")
    @pytest.mark.parametrize("value", [
        RC.TESTS_REPO, RC.TESTS_REPO_SSH, RC.TESTS_REPO_SCP,
        RC.TESTS_REPO_KEY])
    def test_init_spellings(self, tmp_path, value):
        project = utils.Project(tmp_path / "proj")
        project.init(tests_repo=value)
        assert project.workflow_state()["input"]["identity"][
            "tests_repo"] == RC.TESTS_REPO_KEY

    @allure.title("новый init без remote или с невалидным remote "
                  "отклоняется до записей store")
    @pytest.mark.parametrize("value",
                             [None, *RC.INVALID_TESTS_REPO_INPUTS,
                              *RC.TRAVERSAL_TESTS_REPO_INPUTS])
    def test_init_rejects_before_writes(self, project, value):
        with pytest.raises(WorkflowValidationError):
            project.init(tests_repo=value)
        assert not index_mod.index_path(project.store_dir).is_file()
        assert (not project.store_dir.is_dir()
                or not list(project.store_dir.iterdir()))

    @allure.title("resume с тем же remote → resumed; другой → блок "
                  "до записей state/index")
    def test_resume_conflict_no_writes(self, project):
        orchestrator = project.orchestrator()
        project.init(orchestrator)
        _, outcome = project.init(orchestrator)
        assert outcome == "resumed"
        # Snapshot ПОСЛЕ разрешённого resume: сравнение no-write идёт
        # относительно состояния с уже записанным journal/index.
        before = _store_tree(project)
        with pytest.raises(WorkflowBlockedError):
            project.init(orchestrator,
                         tests_repo=RC.TESTS_REPO_OTHER_KEY)
        assert _store_tree(project) == before

    @allure.title("race: конфликт, прошедший lock-free probe, ловится "
                  "под index lock до любой записи")
    def test_index_phase_conflict_no_writes(self, project, monkeypatch):
        orchestrator = project.orchestrator()
        project.init(orchestrator)
        before = _store_tree(project)
        real_find = index_mod.find_entry
        calls = {"n": 0}

        def blind_once(index, repo_key, pilot_id):
            calls["n"] += 1
            if calls["n"] == 1:
                # Проигранная гонка: probe не увидел запись победителя.
                return None
            return real_find(index, repo_key, pilot_id)

        saved = []
        monkeypatch.setattr(index_mod, "find_entry", blind_once)
        monkeypatch.setattr(index_mod, "save_index",
                            lambda *a, **k: saved.append((a, k)))
        with pytest.raises(WorkflowBlockedError):
            project.init(orchestrator,
                         tests_repo=RC.TESTS_REPO_OTHER_KEY)
        assert calls["n"] >= 2 and not saved
        assert _store_tree(project) == before

    @allure.title("race: state, появившийся после index-phase, ловится "
                  "под workflow lock до любой записи")
    def test_workflow_lock_recheck_no_writes(self, project, monkeypatch):
        orchestrator = project.orchestrator()
        project.init(orchestrator)
        before = _store_tree(project)
        real_load = state_mod.load_state
        calls = {"n": 0}

        def late_state(workflow_dir):
            calls["n"] += 1
            if calls["n"] <= 2:
                # Победитель закоммитил index entry, но его state ещё
                # не виден ни probe, ни index-phase re-check.
                return None
            return real_load(workflow_dir)

        saved = []
        monkeypatch.setattr(state_mod, "load_state", late_state)
        monkeypatch.setattr(index_mod, "save_index",
                            lambda *a, **k: saved.append((a, k)))
        with pytest.raises(WorkflowBlockedError):
            project.init(orchestrator,
                         tests_repo=RC.TESTS_REPO_OTHER_KEY)
        # Третий load — под workflow lock: именно он ловит конфликт.
        assert calls["n"] == 3 and not saved
        assert _store_tree(project) == before

    @allure.title("state без tests_repo читается; resume и tests PR "
                  "блокируются без backfill")
    def test_legacy_state_no_backfill(self, project):
        orchestrator = project.drive_commit_to_executed()
        path = _drop_tests_repo_identity(project)
        before = path.read_bytes()
        with allure.step("legacy state читается без миграции"):
            assert orchestrator.status()["input"]["identity"].get(
                "tests_repo") is None
        with allure.step("resume без identity → controlled block"):
            with pytest.raises(WorkflowBlockedError):
                project.init(orchestrator)
        with allure.step("tests PR без identity → controlled block"):
            with pytest.raises(WorkflowBlockedError):
                orchestrator.pr_prepare(
                    "tests", title="legacy", head_branch="wf/h",
                    base_branch="main")
        assert path.read_bytes() == before
        with allure.step("app PR spec по-прежнему работает"):
            result = orchestrator.pr_prepare(
                "app", title="legacy", head_branch="wf/h",
                base_branch="main")
            assert result["outcome"] == "prepared"
            spec = project.workflow_state()["publications"]["pr"][
                "app"]["spec"]
            assert spec["repo"] == C.APP_REPO_KEY


    @allure.title("Удаление identity без согласованного context digest остаётся corruption")
    def test_removed_identity_with_stale_digest_rejected(self, project):
        with allure.step("Создать executed fixture и испортить только identity"):
            orchestrator = project.drive_commit_to_executed()
            path = state_mod.state_path(_workflow_dir(project))
            data = json.loads(path.read_text(encoding="utf-8"))
            data["input"]["identity"].pop("tests_repo", None)
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            corrupted = path.read_bytes()
        with allure.step("Schema guard отвергает stale phase без миграции или записи"):
            with pytest.raises(WorkflowSchemaError):
                orchestrator.status()
            assert path.read_bytes() == corrupted


@allure.epic("Инфраструктура")
@allure.feature("Workflow tests repo identity")
@allure.story("optional schema identity.tests_repo")
@allure.severity(allure.severity_level.CRITICAL)
class TestSchemaCompat:

    @allure.title("state без tests_repo валиден; невалидная запись "
                  "отклоняется схемой")
    @pytest.mark.parametrize("bad", [
        None, "", "owner/repo", "/abs/path", "git.invalid/o/r",
        "github.com/o/r/extra", 17,
        "GitHub.com/Unit-Tests-Org/Unit-Tests-Repo"])
    def test_schema_validation(self, project, bad):
        project.init()
        path = _drop_tests_repo_identity(project)
        assert state_mod.load_state(path.parent)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["input"]["identity"]["tests_repo"] = bad
        path.write_text(json.dumps(data, indent=2) + "\n",
                        encoding="utf-8")
        with pytest.raises(WorkflowSchemaError):
            state_mod.load_state(path.parent)

    @allure.title("canonical remote в identity читается")
    def test_schema_accepts_canonical(self, project):
        project.init()
        state = project.workflow_state()
        assert state["input"]["identity"]["tests_repo"] \
            == RC.TESTS_REPO_KEY


@allure.epic("Инфраструктура")
@allure.feature("Workflow tests repo identity")
@allure.story("tests PR spec использует canonical remote key")
@allure.severity(allure.severity_level.BLOCKER)
class TestPrSpecRepo:

    @allure.title("pr prepare --repo tests → spec.repo == canonical key, "
                  "принимаемый transport'ом")
    def test_tests_spec_repo(self, project):
        orchestrator = project.drive_commit_to_executed()
        result = orchestrator.pr_prepare(
            "tests", title="unit PR", head_branch="wf/h",
            base_branch="main")
        assert result["outcome"] == "prepared"
        spec = project.workflow_state()["publications"]["pr"][
            "tests"]["spec"]
        assert spec["repo"] == RC.TESTS_REPO_KEY
        assert github.GitHubPrTransport._parse_repo_key(
            spec["repo"]) == ("Unit-Tests-Org", "Unit-Tests-Repo")
        with allure.step("spec digest отличается от legacy local path"):
            variant = {key: value for key, value in spec.items()
                       if key != "spec_sha256"}
            variant["repo"] = str(project.root)
            assert adapters.spec_digest(variant) \
                != spec["spec_sha256"]

    @allure.title("pr prepare --repo app без изменений")
    def test_app_spec_repo(self, project):
        orchestrator = project.drive_commit_to_executed()
        orchestrator.pr_prepare(
            "app", title="unit PR", head_branch="wf/h",
            base_branch="main")
        spec = project.workflow_state()["publications"]["pr"][
            "app"]["spec"]
        assert spec["repo"] == C.APP_REPO_KEY

    @allure.title("spec snapshot в intent.target.spec несёт canonical key")
    def test_intent_spec_snapshot(self, project):
        project.drive_commit_to_executed()
        transport = project.fake_pr_for("tests")
        orchestrator = project.orchestrator(
            pr_transports={"tests": transport})
        orchestrator.pr_prepare(
            "tests", title="unit PR", head_branch="wf/h",
            base_branch="main")
        outcome = orchestrator.pr_create("tests", execute=True,
                                         online=True)
        assert outcome["outcome"] == "verified"
        intent = next(item for item in
                      project.workflow_state()["intents"]
                      if item["operation"] == "pr.create")
        assert intent["target"]["spec"]["repo"] == RC.TESTS_REPO_KEY

    @allure.title("pr_ref_matches/exact: repo equality по canonical key")
    def test_pr_ref_repo_equality(self, project):
        orchestrator = project.drive_commit_to_executed()
        orchestrator.pr_prepare(
            "tests", title="unit PR", head_branch="wf/h",
            base_branch="main")
        spec = project.workflow_state()["publications"]["pr"][
            "tests"]["spec"]
        ref = adapters.PrRef(
            repo=RC.TESTS_REPO_KEY, number=7, title=spec["title"],
            head_branch=spec["head_branch"],
            base_branch=spec["base_branch"],
            head_sha=spec["head_sha"],
            body_sha256=spec["body_sha256"],
            files=list(spec["files"]))
        assert adapters.pr_ref_matches(ref, spec)
        assert adapters.pr_ref_exact(ref, spec)
        foreign = adapters.PrRef(
            repo=RC.TESTS_REPO_OTHER_KEY, number=8,
            title=spec["title"], head_branch=spec["head_branch"],
            base_branch=spec["base_branch"])
        assert not adapters.pr_ref_matches(foreign, spec)

    @allure.title("bound_input_digests[identity] фиксирует tests_repo")
    def test_identity_digest_binding(self, project):
        project.drive_to_implementation_ready()
        state = project.workflow_state()
        bound = state["artifacts"]["context"]["bound_input_digests"]
        assert bound["identity"] == state_mod.canonical_digest(
            state["input"]["identity"])
        with allure.step("другой tests_repo → другой identity digest"):
            other = dict(state["input"]["identity"])
            other["tests_repo"] = RC.TESTS_REPO_OTHER_KEY
            assert state_mod.canonical_digest(other) \
                != bound["identity"]


@allure.epic("Инфраструктура")
@allure.feature("Workflow tests repo identity")
@allure.story("реальный temp Git checkout: local path и remote разделены")
@allure.severity(allure.severity_level.BLOCKER)
class TestRealGitCheckout:

    @staticmethod
    def _git(repo, *args):
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    @allure.title("local tests_repo_path обслуживает git/tree gates; "
                  "spec.repo — canonical remote")
    def test_real_git_tests_head(self, tmp_path):
        project = utils.Project(tmp_path / "proj")
        repo = tmp_path / "tests-repo"
        for rel, content in utils.snapshot_tree(project.root).items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self._git(repo, "init", "-q")
        self._git(repo, "add", "-A")
        self._git(repo, "-c", "user.name=unit", "-c",
                  "user.email=unit@example.invalid", "commit", "-qm",
                  "unit")
        head = self._git(repo, "rev-parse", "HEAD")
        porcelain = self._git(repo, "status", "--porcelain")
        orchestrator = project.orchestrator(tests_git_adapter=None)
        with allure.step("init: local checkout + canonical remote"):
            # Никаких FakeGit-констант: commit и dirty определяются
            # настоящим temp репозиторием через real GitReadAdapter.
            project.init(orchestrator, tests_repo_path=str(repo),
                         tests_repo=RC.TESTS_REPO,
                         tests_commit=None, tests_dirty=None)
            state = project.workflow_state()
            assert state["input"]["identity"]["tests_repo"] \
                == RC.TESTS_REPO_KEY
            assert state["input"]["locals"]["tests_repo_path"] \
                == str(repo)
            assert state["input"]["revision_data"]["tests_repo"][
                "commit"] == head.lower()
            assert state["input"]["revision_data"]["tests_repo"][
                "dirty"] is (porcelain != "")
        with allure.step("pr prepare tests по локальному git; "
                         "spec.repo — canonical remote"):
            result = orchestrator.pr_prepare(
                "tests", title="unit PR", head_branch="wf/h",
                base_branch="main")
            assert result["outcome"] == "prepared", result
            spec = project.workflow_state()["publications"]["pr"][
                "tests"]["spec"]
            assert spec["repo"] == RC.TESTS_REPO_KEY
            assert spec["head_sha"] == head.lower()


@allure.epic("Инфраструктура")
@allure.feature("Workflow tests repo identity")
@allure.story("CLI init --tests-repo")
@allure.severity(allure.severity_level.NORMAL)
class TestCliFlag:

    def _cli(self, project, *args):
        argv = [sys.executable, str(CLI), "--store-dir",
                str(project.store_dir), *args]
        return subprocess.run(argv, cwd=project.root,
                              capture_output=True, text=True, timeout=60)

    @allure.title("init без --tests-repo → usage exit 2; "
                  "с флагом → created")
    def test_init_flag_required(self, project):
        base = ["init", "--pilot-id", C.PILOT_ID, "--app-repo",
                C.APP_REPO, "--app-base-sha", C.APP_BASE_SHA,
                "--app-patch-sha256", C.APP_PATCH_SHA256,
                "--tests-commit", C.TESTS_COMMIT, "--tests-clean",
                "--requirements",
                str(project.root / C.REQUIREMENTS_REL)]
        with allure.step("без флага — usage error"):
            result = self._cli(project, *base)
            assert result.returncode == 2
        with allure.step("с canonical remote — created"):
            result = self._cli(project, *base,
                               "--tests-repo", RC.TESTS_REPO)
            assert result.returncode == 0, result.stderr
            assert '"created"' in result.stdout
        with allure.step("state содержит canonical identity"):
            state = project.workflow_state()
            assert state["input"]["identity"]["tests_repo"] \
                == RC.TESTS_REPO_KEY
