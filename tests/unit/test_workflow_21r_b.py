"""21R-B регрессии: исправления orchestration/recovery из ревью 21B (F1–F6)
и 21A (F3/F4).

- F1: `created` + записанный PR number никогда не отправляет второй create
  при пустом поиске — только targeted get + exact verification.
- F2: inherited intents пересверяются с parent-линией; resolution в parent
  снимает stale blocker, ambiguous/corrupt parent остаётся blocked.
- F3/F4: missing spec и search exceptions — контролируемые исходы без
  crash и без перевода неизвестного эффекта в retry-safe.
- F5: corrupt TestOps state — контролируемый 69, байты и dispatch=0.
- F6: наблюдение base-execution не перезаписывает head publication.
- 21A F3: re-import записанного base после ревизии — полная повторная
  проверка + audit rebind; head прошлой ревизии не переиспользуется.
- 21A F4: boundary-token matching node IDs (UNIT-VAL-0010 не покрывает 001).

Все проверки считают dispatch counters, а не только outcomes, и строго
offline в tmp dirs: fake runner / fake PR transport / isolated stores.
"""
import json

import allure
import pytest

from infrastructure.workflow import adapters
from infrastructure.workflow import state as state_mod
from infrastructure.workflow.state import WorkflowBlockedError
from test_data.consts import workflow as C
from test_data.consts import workflow_21r_b as B
from test_data.utils import workflow as utils


@pytest.fixture
def project(tmp_path):
    return utils.Project(tmp_path / "proj")


def _state(project, workflow_id=None):
    if workflow_id is not None:
        return state_mod.load_state(project.store_dir / workflow_id)
    return project.workflow_state()


def _workflow_dir(project, workflow_id=None):
    if workflow_id is not None:
        return project.store_dir / workflow_id
    return next(p for p in project.store_dir.iterdir()
                if p.is_dir() and state_mod.WORKFLOW_ID_RE.fullmatch(p.name))


def _pr_entry(project, role="app", workflow_id=None):
    return _state(project, workflow_id)["publications"]["pr"][role]


def _creates(transport):
    return [name for name, _ in transport.calls if name == "create"]


def _mk_ref(spec, number=B.PR_CREATED_NUMBER):
    return adapters.PrRef(
        repo=spec["repo"], number=number,
        url=B.PR_URL_TEMPLATE.format(number=number),
        title=spec["title"], head_branch=spec["head_branch"],
        base_branch=spec["base_branch"], head_sha=spec.get("head_sha"),
        body_sha256=spec.get("body_sha256"),
        files=list(spec.get("files") or []))


def _prepare_args(role):
    files = [C.CHANGED_APP_FILE] if role == "app" else list(C.TEST_FILES)
    return dict(title=B.SPEC_TITLE, head_branch=B.HEAD_BRANCH,
                base_branch=B.BASE_BRANCH, files=files)


def _created_project(project, role, search=None):
    """Executed + prepare + create: transport возвращает читаемый ref, но
    get() не подтверждает — entry остаётся 'created' с записанным номером."""
    project.drive_commit_to_executed()
    remote = []

    def create(spec):
        ref = _mk_ref(spec)
        remote.append(ref)
        return ref

    transport = adapters.FakePrTransport(
        search_result=search if search is not None else [],
        create_result=create, get_map={})
    orch = project.orchestrator(pr_transports={role: transport})
    orch.pr_prepare(role, **_prepare_args(role))
    first = orch.pr_create(role, execute=True, online=True)
    return orch, transport, remote, first


def _revision2_to_implementation_ready(project, orch):
    """Bump revision новым patch sha и довести новую ревизию до
    implementation_ready: re-accept цепочки + новый head run."""
    project.init(orch, app_head_sha256=C.APP_PATCH_SHA256_2)
    assert _state(project)["input"]["revision"] == 2
    orch.accept("context", project.context_envelope())
    orch.accept("scenarios", project.scenarios_envelope())
    orch.accept("review", project.review_envelope())
    orch.accept("implementation", project.impl_envelope())
    orch.accept("bindings", project.bindings_envelope())
    utils.harness_run(
        project.runner, project.root, B.EXECUTION_HEAD_2, C.HEAD_JUNIT, 0,
        declared={"app_base_sha": C.APP_BASE_SHA,
                  "app_patch_sha256": C.APP_PATCH_SHA256_2})
    assert orch.run_execution("head")["outcome"] == "recorded"
    assert _state(project)["phase"] == "implementation_ready"


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("21B-F1: created PR не пересоздаётся без доказательства")
@allure.severity(allure.severity_level.BLOCKER)
class TestF1CreatedTargetedGet:
    @allure.title("created + пустой search + get None: create остаётся 1")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_get_none_keeps_single_create(self, project, role):
        with allure.step("Довести до created с записанным номером"):
            orch, transport, remote, first = _created_project(
                project, role)
            assert first["outcome"] == "created" and len(remote) == 1
        with allure.step("Повторный create — targeted get, не новый dispatch"):
            second = orch.pr_create(role, execute=True, online=True)
        with allure.step("Blocked, create счётчик заморожен, номер сохранён"):
            assert second["outcome"] == "blocked" and second["exit"] == 69
            assert len(_creates(transport)) == 1
            entry = _pr_entry(project, role)
            assert entry["status"] == "created"
            assert entry["number"] == B.PR_CREATED_NUMBER

    @allure.title("created + get error: indeterminate, create остаётся 1")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_get_error_indeterminate(self, project, role):
        orch, transport, remote, first = _created_project(project, role)
        spec = _pr_entry(project, role)["spec"]
        transport.get_map[(spec["repo"], B.PR_CREATED_NUMBER)] = (
            RuntimeError("get backend down"))
        with allure.step("Targeted get падает — эффект indeterminate"):
            second = orch.pr_create(role, execute=True, online=True)
            assert second["outcome"] == "unknown" and second["exit"] == 75
            assert len(_creates(transport)) == 1
            entry = _pr_entry(project, role)
            assert entry["status"] == "created"
            assert entry["number"] == B.PR_CREATED_NUMBER

    @allure.title("created + get mismatch: blocked, create остаётся 1")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_get_mismatch_blocked(self, project, role):
        orch, transport, remote, first = _created_project(project, role)
        spec = _pr_entry(project, role)["spec"]
        transport.get_map[(spec["repo"], B.PR_CREATED_NUMBER)] = (
            _mk_ref(spec, number=B.PR_CREATED_NUMBER))
        bad = transport.get_map[(spec["repo"], B.PR_CREATED_NUMBER)]
        bad.head_sha = "f" * 40
        with allure.step("Fetched ref не совпадает со spec — blocked"):
            second = orch.pr_create(role, execute=True, online=True)
            assert second["outcome"] == "blocked" and second["exit"] == 69
            assert len(_creates(transport)) == 1
            entry = _pr_entry(project, role)
            assert entry["status"] == "created"
            assert entry["number"] == B.PR_CREATED_NUMBER

    @allure.title("created + exact get: adoption, create остаётся 1")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_exact_get_verifies(self, project, role):
        orch, transport, remote, first = _created_project(project, role)
        spec = _pr_entry(project, role)["spec"]
        transport.get_map[(spec["repo"], B.PR_CREATED_NUMBER)] = (
            _mk_ref(spec, number=B.PR_CREATED_NUMBER))
        with allure.step("Targeted get доказывает exact spec — verified"):
            second = orch.pr_create(role, execute=True, online=True)
            assert second["outcome"] == "verified"
            assert len(_creates(transport)) == 1
            entry = _pr_entry(project, role)
            assert entry["status"] == "verified"
            assert entry["number"] == B.PR_CREATED_NUMBER

    @allure.title("created entry: re-prepare заблокирован")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_reprepare_blocked(self, project, role):
        orch, transport, remote, first = _created_project(project, role)
        spec_before = _pr_entry(project, role)["spec"]["spec_sha256"]
        with allure.step("re-prepare на created entry отклоняется"):
            outcome = orch.pr_prepare(
                role, title=B.CHILD_SPEC_TITLE, head_branch="h2",
                base_branch="m2", files=[])
            assert outcome["outcome"] == "blocked"
            assert _pr_entry(project, role)["spec"]["spec_sha256"] \
                == spec_before
            assert len(_creates(transport)) == 1

    @allure.title("unknown intent + смена ревизии: executed — blocked без "
                  "повторного create")
    def test_unknown_survives_revision_at_executed(self, project):
        with allure.step("create с timeout-транспортом (unknown intent)"):
            project.drive_commit_to_executed()
            transport = adapters.FakePrTransport(
                search_result=[],
                create_result=adapters.RunOutcome(None, error="timeout"))
            orch = project.orchestrator(pr_transports={"app": transport})
            orch.pr_prepare("app", **_prepare_args("app"))
            assert orch.pr_create("app", execute=True, online=True)[
                "exit"] == 75
        with allure.step("Новая ревизия доведена до executed"):
            _revision2_to_implementation_ready(project, orch)
            rebind = orch.import_execution(C.EXECUTION_BASE)
            assert rebind["outcome"] == "rebound"
            assert _state(project)["phase"] == "executed"
        with allure.step("create blocked; повторного dispatch нет"):
            outcome = orch.pr_create("app", execute=True, online=True)
            assert outcome["outcome"] == "blocked" and outcome["exit"] == 69
            assert len(_creates(transport)) == 1

    @allure.title("created + смена ревизии: executed — blocked без "
                  "повторного create")
    def test_created_survives_revision_at_executed(self, project):
        orch, transport, remote, first = _created_project(project, "app")
        assert len(remote) == 1
        with allure.step("Новая ревизия доведена до executed"):
            _revision2_to_implementation_ready(project, orch)
            rebind = orch.import_execution(C.EXECUTION_BASE)
            assert rebind["outcome"] == "rebound"
            assert _state(project)["phase"] == "executed"
        with allure.step("Записанный remote-эффект всё ещё блокирует"):
            outcome = orch.pr_create("app", execute=True, online=True)
            assert outcome["outcome"] == "blocked" and outcome["exit"] == 69
            assert len(_creates(transport)) == 1
            entry = _pr_entry(project)
            assert entry["status"] == "blocked"
            assert entry["number"] == B.PR_CREATED_NUMBER


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("21B-F2: inherited intents пересверяются с parent-линией")
@allure.severity(allure.severity_level.BLOCKER)
class TestF2InheritedIntents:
    def _supersede_setup(self, project, *, head_kind="patch", git_sha=None):
        """Parent at executed + timed-out create; superseded lineage."""
        project.drive_commit_to_executed()
        transport = adapters.FakePrTransport(
            search_result=[],
            create_result=adapters.RunOutcome(None, error="timeout"))
        orch = project.orchestrator(pr_transports={"app": transport})
        orch.pr_prepare("app", title=B.PARENT_SPEC_TITLE,
                        head_branch=B.HEAD_BRANCH,
                        base_branch=B.BASE_BRANCH)
        first = orch.pr_create("app", execute=True, online=True)
        old_id = _state(project)["workflow_id"]
        overrides = dict(app_base_sha=C.APP_BASE_SHA_2, supersede=True,
                         app_head_kind=head_kind,
                         app_head_git_sha=git_sha,
                         app_head_sha256=(C.APP_PATCH_SHA256
                                          if head_kind == "patch" else None))
        new_id, _ = project.init(orch, **overrides)
        return orch, transport, first, old_id, new_id

    def _resolve_parent(self, project, old_id):
        """Reconcile parent с точным ref — adopted/verified resolution."""
        spec = _pr_entry(project, "app", workflow_id=old_id)["spec"]
        ref = _mk_ref(spec, number=B.PR_PARENT_NUMBER)
        resolving = adapters.FakePrTransport(
            search_result=[ref],
            get_map={(spec["repo"], B.PR_PARENT_NUMBER): ref})
        orch2 = project.orchestrator(pr_transports={"app": resolving})
        report = orch2.reconcile(workflow_id=old_id, online=True)
        return orch2, resolving, report

    @allure.title("Parent adopted → новая линия понимает resolution и "
                  "prepare разблокирован")
    def test_parent_adopted_unblocks_new_lineage(self, project):
        orch, transport, first, old_id, new_id = self._supersede_setup(
            project)
        assert first["exit"] == 75
        with allure.step("Reconcile parent: intent adopted"):
            orch2, resolving, report = self._resolve_parent(project, old_id)
            assert report[0]["action"] == "adopted"
            assert _pr_entry(project, "app", workflow_id=old_id)[
                "status"] == "verified"
        with allure.step("Inherited snapshot пересверен и разрешается"):
            prepared = orch2.pr_prepare(
                "app", workflow_id=new_id, title=B.CHILD_SPEC_TITLE,
                head_branch=B.HEAD_BRANCH, base_branch=B.BASE_BRANCH)
            assert prepared["outcome"] == "prepared"
        with allure.step("История сохранена; remote-эффект не продублирован"):
            inherited = [i for i in _state(project, new_id)[
                "inherited_intents"] if i["operation"] == "pr.create"]
            assert len(inherited) == 1
            assert inherited[0]["status"] == "resolved"
            assert inherited[0]["resolved_in_parent"]["parent_status"] \
                == "completed"
            assert len(_creates(resolving)) == 0
            assert len(_creates(transport)) == 1

    @allure.title("Parent intent всё ещё unresolved — блокер сохраняется")
    def test_parent_unresolved_keeps_blocked(self, project):
        orch, transport, first, old_id, new_id = self._supersede_setup(
            project)
        with allure.step("Parent не reconcile-нут — prepare/create blocked"):
            out = orch.pr_prepare(
                "app", workflow_id=new_id, title=B.CHILD_SPEC_TITLE,
                head_branch=B.HEAD_BRANCH, base_branch=B.BASE_BRANCH)
            assert out["outcome"] == "blocked" and out["exit"] == 69
            inherited = [i for i in _state(project, new_id)[
                "inherited_intents"] if i["operation"] == "pr.create"]
            assert inherited[0]["status"] == "unknown"
            assert len(_creates(transport)) == 1

    @allure.title("Missing или corrupt parent state остаётся blocked")
    @pytest.mark.parametrize("mode", ("corrupt", "missing"))
    def test_parent_unreadable_keeps_blocked(self, project, mode):
        orch, transport, first, old_id, new_id = self._supersede_setup(
            project)
        state_path = project.store_dir / old_id / "state.json"
        backup = state_path.read_bytes()
        with allure.step(f"Parent state недоступен: {mode}"):
            if mode == "corrupt":
                state_path.write_bytes(B.CORRUPT_STATE_BYTES)
            else:
                state_path.rename(state_path.with_suffix(".bak"))
            out = orch.pr_prepare(
                "app", workflow_id=new_id, title=B.CHILD_SPEC_TITLE,
                head_branch=B.HEAD_BRANCH, base_branch=B.BASE_BRANCH)
            assert out["outcome"] == "blocked" and out["exit"] == 69
            inherited = [i for i in _state(project, new_id)[
                "inherited_intents"] if i["operation"] == "pr.create"]
            assert inherited[0]["status"] == "unknown"
            assert len(_creates(transport)) == 1
        state_path.write_bytes(backup)
        if mode == "missing":
            state_path.with_suffix(".bak").unlink(missing_ok=True)

    @allure.title("Тот же intent_id, но иной target в parent — ambiguous, "
                  "blocked")
    def test_parent_intent_mismatch_stays_blocked(self, project):
        orch, transport, first, old_id, new_id = self._supersede_setup(
            project)
        orch2, resolving, report = self._resolve_parent(project, old_id)
        assert report[0]["action"] == "adopted"
        with allure.step("Parent intent tampered: другой target под тем "
                         "же id"):
            wf_dir = project.store_dir / old_id
            parent = state_mod.load_state(wf_dir)
            for intent in parent["intents"]:
                if intent["operation"] == "pr.create":
                    intent["target"]["spec_sha256"] = "f" * 64
            state_mod.save_state(wf_dir, parent)
            out = orch2.pr_prepare(
                "app", workflow_id=new_id, title=B.CHILD_SPEC_TITLE,
                head_branch=B.HEAD_BRANCH, base_branch=B.BASE_BRANCH)
            assert out["outcome"] == "blocked" and out["exit"] == 69
            inherited = [i for i in _state(project, new_id)[
                "inherited_intents"] if i["operation"] == "pr.create"]
            assert inherited[0]["status"] == "unknown"

    @allure.title("Supersede: parent resolved, но несовместимый spec новой "
                  "линии не публикуется")
    def test_child_incompatible_spec_not_published(self, project):
        orch, transport, first, old_id, new_id = self._supersede_setup(
            project, head_kind="commit",
            git_sha=C.APP_HEAD_COMMIT_SHA_2)
        with allure.step("Разрешить parent и собрать Git-объекты новой "
                         "линии"):
            orch2, resolving, report = self._resolve_parent(project, old_id)
            assert report[0]["action"] == "adopted"
            parent_spec = _pr_entry(project, "app", workflow_id=old_id)[
                "spec"]
            project.git.register_commit(
                C.APP_BASE_SHA_2,
                dict(project.git.commits[C.APP_BASE_SHA]))
            project.git.register_commit(
                C.APP_HEAD_COMMIT_SHA_2,
                utils.snapshot_tree(project.app_repo))
        with allure.step("Довести новую commit-head линию до executed"):
            orch2.accept("context", project.context_envelope(),
                         workflow_id=new_id)
            orch2.accept("scenarios", project.scenarios_envelope(),
                         workflow_id=new_id)
            orch2.accept("review", project.review_envelope(),
                         workflow_id=new_id)
            orch2.accept("implementation", project.impl_envelope(),
                         workflow_id=new_id)
            orch2.accept("bindings", project.bindings_envelope(),
                         workflow_id=new_id)
            utils.harness_run(
                project.runner, project.root, B.EXECUTION_HEAD_3,
                C.HEAD_JUNIT, 0,
                declared={"app_base_sha": C.APP_HEAD_COMMIT_SHA_2})
            assert orch2.run_execution(
                "head", workflow_id=new_id)["outcome"] == "recorded"
            utils.write_manifest(
                project.root, B.EXECUTION_BASE_2, C.BASE_JUNIT, 1,
                declared={"app_base_sha": C.APP_BASE_SHA_2})
            assert orch2.import_execution(
                B.EXECUTION_BASE_2, workflow_id=new_id)["outcome"] \
                == "imported"
            assert _state(project, new_id)["phase"] == "executed"
        with allure.step("Search видит PR parent (иной title_key) — "
                         "foreign, не публикуется"):
            prepared = orch2.pr_prepare(
                "app", workflow_id=new_id, title=B.CHILD_SPEC_TITLE,
                head_branch=B.HEAD_BRANCH, base_branch=B.BASE_BRANCH,
                files=[C.CHANGED_APP_FILE])
            assert prepared["outcome"] == "prepared"
            outcome = orch2.pr_create("app", workflow_id=new_id,
                                      execute=True, online=True)
            assert outcome["outcome"] == "blocked" and outcome["exit"] == 69
            assert len(_creates(resolving)) == 0
            assert _pr_entry(project, "app", workflow_id=new_id)[
                "status"] == "blocked"

    @allure.title("Reconcile новой линии тоже пересверяет inherited")
    def test_reconcile_resolves_inherited(self, project):
        orch, transport, first, old_id, new_id = self._supersede_setup(
            project)
        orch2, resolving, report = self._resolve_parent(project, old_id)
        assert report[0]["action"] == "adopted"
        with allure.step("reconcile новой линии помечает inherited "
                         "resolved"):
            orch2.reconcile(workflow_id=new_id, online=True)
            inherited = [i for i in _state(project, new_id)[
                "inherited_intents"] if i["operation"] == "pr.create"]
            assert inherited[0]["status"] == "resolved"


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("21B-F3/F4: контролируемые исходы reconcile и create")
@allure.severity(allure.severity_level.BLOCKER)
class TestF34ControlledBoundaries:
    @allure.title("Dispatched pr.create без frozen spec — controlled "
                  "blocked, не KeyError")
    def test_reconcile_missing_spec_blocked(self, project):
        project.drive_commit_to_executed()
        project.orchestrator().pr_prepare(
            "app", title=B.SPEC_TITLE, head_branch=B.HEAD_BRANCH,
            base_branch=B.BASE_BRANCH)
        wf_dir = _workflow_dir(project)
        state = state_mod.load_state(wf_dir)
        intent = state_mod.new_intent(
            state, "pr.create", {"repo": "app", "spec_sha256": "f" * 64})
        intent["status"] = "dispatched"
        state["publications"]["pr"]["app"].update(
            status="intent", spec=None, intent_id=intent["intent_id"])
        state_mod.save_state(wf_dir, state)
        ref = adapters.PrRef(repo="git.invalid/Org/Unit-App", number=9,
                             title="x", head_branch="h", base_branch="m")
        transport = adapters.FakePrTransport(search_result=[ref])
        orch = project.orchestrator(pr_transports={"app": transport})
        with allure.step("reconcile — controlled blocked, search не "
                         "вызывался"):
            report = orch.reconcile(online=True)
            assert report[0]["action"] == "blocked"
            assert transport.calls == []
            reloaded = _state(project)
            kept = [i for i in reloaded["intents"]
                    if i["intent_id"] == intent["intent_id"]][0]
            assert kept["status"] == "dispatched"

    @allure.title("Search exception в reconcile — blocked report, intent "
                  "не становится retryable")
    def test_reconcile_search_exception_blocked(self, project):
        project.drive_commit_to_executed()
        project.orchestrator().pr_prepare(
            "app", title=B.SPEC_TITLE, head_branch=B.HEAD_BRANCH,
            base_branch=B.BASE_BRANCH)
        spec = _pr_entry(project)["spec"]
        wf_dir = _workflow_dir(project)
        state = state_mod.load_state(wf_dir)
        intent = state_mod.new_intent(
            state, "pr.create",
            {"repo": "app", "spec_sha256": spec["spec_sha256"],
             "spec": dict(spec)})
        intent["status"] = "dispatched"
        state["publications"]["pr"]["app"].update(
            status="intent", intent_id=intent["intent_id"])
        state_mod.save_state(wf_dir, state)
        transport = adapters.FakePrTransport(
            search_result=RuntimeError("search backend down"))
        orch = project.orchestrator(pr_transports={"app": transport})
        with allure.step("reconcile — controlled blocked, не crash"):
            report = orch.reconcile(online=True)
            assert report[0]["action"] == "blocked"
            kept = [i for i in _state(project)["intents"]
                    if i["intent_id"] == intent["intent_id"]][0]
            assert kept["status"] == "dispatched"
            assert _pr_entry(project)["status"] == "blocked"

    @allure.title("Search exception в pr_create — blocked 69, create=0, "
                  "entry не poisoned")
    def test_pr_create_search_exception_blocked(self, project):
        project.drive_commit_to_executed()
        transport = adapters.FakePrTransport(
            search_result=RuntimeError("search backend down"))
        orch = project.orchestrator(pr_transports={"app": transport})
        orch.pr_prepare("app", **_prepare_args("app"))
        with allure.step("Search падает — controlled blocked до dispatch"):
            outcome = orch.pr_create("app", execute=True, online=True)
            assert outcome["outcome"] == "blocked" and outcome["exit"] == 69
            assert len(_creates(transport)) == 0
            assert _pr_entry(project)["status"] == "pending"

    @allure.title("Поздний сбой в reconcile не теряет доказанные решения "
                  "ранних intents")
    def test_late_failure_preserves_earlier_decisions(self, project):
        project.drive_commit_to_executed()
        utils.make_testops_state(project.root, C.EXECUTION_HEAD,
                                 upload_status="sent")
        project.orchestrator().pr_prepare(
            "app", title=B.SPEC_TITLE, head_branch=B.HEAD_BRANCH,
            base_branch=B.BASE_BRANCH)
        spec = _pr_entry(project)["spec"]
        wf_dir = _workflow_dir(project)
        state = state_mod.load_state(wf_dir)
        upload_intent = state_mod.new_intent(
            state, "testops.upload", {"execution": C.EXECUTION_HEAD})
        upload_intent["status"] = "dispatched"
        pr_intent = state_mod.new_intent(
            state, "pr.create",
            {"repo": "app", "spec_sha256": spec["spec_sha256"],
             "spec": dict(spec)})
        pr_intent["status"] = "dispatched"
        state_mod.save_state(wf_dir, state)
        transport = adapters.FakePrTransport(
            search_result=RuntimeError("search backend down"))
        orch = project.orchestrator(pr_transports={"app": transport})
        with allure.step("Upload intent adopted, pr intent — controlled "
                         "blocked"):
            report = orch.reconcile(online=True)
            assert report[0]["action"] == "adopted"
            assert report[1]["action"] == "blocked"
            reloaded = _state(project)
            done = [i for i in reloaded["intents"]
                    if i["intent_id"] == upload_intent["intent_id"]][0]
            kept = [i for i in reloaded["intents"]
                    if i["intent_id"] == pr_intent["intent_id"]][0]
            assert done["status"] == "completed"
            assert kept["status"] == "dispatched"


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("21B-F5: corrupt TestOps state — контролируемый 69")
@allure.severity(allure.severity_level.BLOCKER)
class TestF5CorruptTestOps:
    def _corrupt_state(self, project):
        state_dir = (project.root / "artifacts" / "testops"
                     / C.EXECUTION_HEAD)
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / "state.json"
        path.write_bytes(B.CORRUPT_STATE_BYTES)
        return path

    @allure.title("Corrupt state: verify/prepare/publish — 69, байты "
                  "неизменны, dispatch=0")
    def test_corrupt_state_controlled_69(self, project):
        orch = project.drive_to_executed()
        path = self._corrupt_state(project)
        testops_calls = len(project.runner.tool_calls("tools/run-testops.sh"))
        pytest_calls = len(project.runner.tool_calls("tools/run-tests.sh"))
        with allure.step("verify/prepare/publish — controlled 69"):
            with pytest.raises(WorkflowBlockedError):
                orch.verify_testops(C.EXECUTION_HEAD, online=True)
            with pytest.raises(WorkflowBlockedError):
                orch.prepare_testops(C.EXECUTION_HEAD)
            with pytest.raises(WorkflowBlockedError):
                orch.publish_testops(C.EXECUTION_HEAD, execute=True)
        with allure.step("Байты state неизменны, dispatch=0"):
            assert path.read_bytes() == B.CORRUPT_STATE_BYTES
            assert len(project.runner.tool_calls(
                "tools/run-testops.sh")) == testops_calls
            assert len(project.runner.tool_calls(
                "tools/run-tests.sh")) == pytest_calls

    @allure.title("Corrupt state при reconcile upload intent — blocked "
                  "report, не crash")
    def test_corrupt_reconcile_blocked_report(self, project):
        orch = project.drive_to_executed()
        wf_dir = _workflow_dir(project)
        state = state_mod.load_state(wf_dir)
        intent = state_mod.new_intent(
            state, "testops.upload", {"execution": C.EXECUTION_HEAD})
        intent["status"] = "dispatched"
        state_mod.save_state(wf_dir, state)
        path = self._corrupt_state(project)
        with allure.step("reconcile — controlled blocked, байты целы"):
            report = orch.reconcile(online=True)
            assert report[0]["action"] == "blocked"
            kept = [i for i in _state(project)["intents"]
                    if i["intent_id"] == intent["intent_id"]][0]
            assert kept["status"] == "dispatched"
            assert path.read_bytes() == B.CORRUPT_STATE_BYTES


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("21B-F6: наблюдение base не перезаписывает head publication")
@allure.severity(allure.severity_level.BLOCKER)
class TestF6BaseObservation:
    @allure.title("verify_testops(base) после uploaded head — канал "
                  "публикации не меняется")
    def test_verify_base_keeps_head_observation(self, project):
        orch = project.drive_to_executed()
        results_dir = (project.root / "artifacts" / "harness"
                       / C.EXECUTION_HEAD / "allure-results")
        utils.testops_local_handlers(project.runner, project.root,
                                     C.EXECUTION_HEAD, results_dir,
                                     dict(C.BINDINGS))
        orch.prepare_testops(C.EXECUTION_HEAD)
        out = orch.publish_testops(C.EXECUTION_HEAD, execute=True)
        assert out["outcome"] == "uploaded"
        obs0 = dict(_state(project)["publications"]["testops"])
        with allure.step("Base execution uploaded — verify наблюдателя"):
            utils.make_testops_state(project.root, C.EXECUTION_BASE,
                                     upload_status="uploaded", launch_id=66)
            assert orch.verify_testops(
                C.EXECUTION_BASE, online=True)["outcome"] == "no-op"
        with allure.step("Observation всё ещё про head execution"):
            obs1 = _state(project)["publications"]["testops"]
            assert obs1["execution_id"] == C.EXECUTION_HEAD
            assert obs1["last_observation"]["upload_status"] == "uploaded"
            assert obs1["last_observation"]["state_sha256"] == \
                obs0["last_observation"]["state_sha256"]
        with allure.step("reconcile тоже не переписывает канал base-ом"):
            orch.reconcile(online=True)
            assert _state(project)["publications"]["testops"][
                "execution_id"] == C.EXECUTION_HEAD

    @allure.title("Уже confirmed/published не деградирует от наблюдения "
                  "base")
    def test_published_phase_survives_base_observation(self, project):
        project.drive_commit_to_executed()
        results_dir = (project.root / "artifacts" / "harness"
                       / C.EXECUTION_HEAD / "allure-results")
        utils.testops_local_handlers(project.runner, project.root,
                                     C.EXECUTION_HEAD, results_dir,
                                     dict(C.BINDINGS))
        tr_app = project.fake_pr_for("app")
        tr_tests = project.fake_pr_for("tests")
        orch = project.orchestrator(
            pr_transports={"app": tr_app, "tests": tr_tests})
        with allure.step("Довести до published (обе PR-роли + uploaded)"):
            orch.prepare_testops(C.EXECUTION_HEAD)
            orch.publish_testops(C.EXECUTION_HEAD, execute=True)
            orch.pr_prepare("app", **_prepare_args("app"))
            orch.pr_create("app", execute=True, online=True)
            orch.pr_prepare("tests", **_prepare_args("tests"))
            orch.pr_create("tests", execute=True, online=True)
            assert _state(project)["phase"] == "published"
        with allure.step("Base uploaded — verify/reconcile не деградируют "
                         "published"):
            utils.make_testops_state(project.root, C.EXECUTION_BASE,
                                     upload_status="uploaded")
            orch.verify_testops(C.EXECUTION_BASE, online=True)
            assert _state(project)["phase"] == "published"
            orch.reconcile(online=True)
            assert _state(project)["phase"] == "published"
            assert _state(project)["publications"]["testops"][
                "execution_id"] == C.EXECUTION_HEAD

    @allure.title("reconcile upload intent для base не переписывает "
                  "head-канал")
    def test_reconcile_base_upload_keeps_head_channel(self, project):
        orch = project.drive_to_executed()
        results_dir = (project.root / "artifacts" / "harness"
                       / C.EXECUTION_HEAD / "allure-results")
        utils.testops_local_handlers(project.runner, project.root,
                                     C.EXECUTION_HEAD, results_dir,
                                     dict(C.BINDINGS))
        orch.prepare_testops(C.EXECUTION_HEAD)
        orch.publish_testops(C.EXECUTION_HEAD, execute=True)
        utils.make_testops_state(project.root, C.EXECUTION_BASE,
                                 upload_status="uploaded", launch_id=77)
        wf_dir = _workflow_dir(project)
        state = state_mod.load_state(wf_dir)
        intent = state_mod.new_intent(
            state, "testops.upload", {"execution": C.EXECUTION_BASE})
        intent["status"] = "dispatched"
        state_mod.save_state(wf_dir, state)
        with allure.step("reconcile: base intent adopted, канал остаётся "
                         "head"):
            report = orch.reconcile(online=True)
            adopted = [r for r in report
                       if r["intent"] == intent["intent_id"]]
            assert adopted and adopted[0]["action"] == "adopted"
            assert _state(project)["publications"]["testops"][
                "execution_id"] == C.EXECUTION_HEAD


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("21A-F3: re-import записанного base после ревизии")
@allure.severity(allure.severity_level.BLOCKER)
class TestBaseReimport:
    @allure.title("Re-import base после T8 — полная проверка и audit "
                  "rebind; повтор — no-op")
    def test_base_rebind_after_revision(self, project):
        orch = project.drive_to_executed()
        with allure.step("Новая ревизия доведена до implementation_ready"):
            _revision2_to_implementation_ready(project, orch)
        with allure.step("Re-import записанного base — rebound, не "
                         "молчаливый no-op"):
            outcome = orch.import_execution(C.EXECUTION_BASE)
            assert outcome["outcome"] == "rebound"
            assert outcome["bound_revision"] == 2
            entry = next(e for e in _state(project)["executions"]
                         if e["execution_id"] == C.EXECUTION_BASE)
            assert entry["bound_revision"] == 2
            assert entry["rebound_from_revision"] == 1
            assert _state(project)["phase"] == "executed"
            events = [j["event"] for j in _state(project)["journal"]]
            assert "base-rebind" in events
        with allure.step("Повтор после привязки — честный no-op"):
            again = orch.import_execution(C.EXECUTION_BASE)
            assert again["outcome"] == "no-op"

    @allure.title("Re-import на той же ревизии — честный no-op")
    def test_reimport_same_revision_noop(self, project):
        orch = project.drive_to_executed()
        outcome = orch.import_execution(C.EXECUTION_BASE)
        assert outcome["outcome"] == "no-op"

    @allure.title("Head execution прошлой ревизии никогда не "
                  "переиспользуется")
    def test_head_past_revision_never_reused(self, project):
        orch = project.drive_to_executed()
        _revision2_to_implementation_ready(project, orch)
        with allure.step("Re-import head bound=1 — blocked"):
            outcome = orch.import_execution(C.EXECUTION_HEAD)
            assert outcome["outcome"] == "blocked" and outcome["exit"] == 69
            entry = next(e for e in _state(project)["executions"]
                         if e["execution_id"] == C.EXECUTION_HEAD)
            assert entry["bound_revision"] == 1
            assert "rebound_from_revision" not in entry

    @allure.title("Drift evidence источника блокирует rebind, bound "
                  "сохраняется")
    def test_rebind_blocked_on_source_drift(self, project):
        orch = project.drive_to_executed()
        _revision2_to_implementation_ready(project, orch)
        evidence = (project.root / "artifacts" / "harness"
                    / C.EXECUTION_BASE)
        (evidence / "sources" / C.TEST_FILES[0]).write_text(
            B.MUTATED_SOURCE_TEXT)
        with allure.step("Mutated source copy — rebind blocked"):
            outcome = orch.import_execution(C.EXECUTION_BASE)
            assert outcome["outcome"] == "blocked" and outcome["exit"] == 69
            entry = next(e for e in _state(project)["executions"]
                         if e["execution_id"] == C.EXECUTION_BASE)
            assert entry["bound_revision"] == 1
            assert _state(project)["phase"] == "implementation_ready"

    @allure.title("Противоречие provenance с записанным рекордом — blocked")
    def test_rebind_blocked_on_provenance_conflict(self, project):
        orch = project.drive_to_executed()
        _revision2_to_implementation_ready(project, orch)
        wf_dir = _workflow_dir(project)
        state = state_mod.load_state(wf_dir)
        entry = next(e for e in state["executions"]
                     if e["execution_id"] == C.EXECUTION_BASE)
        entry["provenance"] = dict(B.PROVENANCE_A)
        state_mod.save_state(wf_dir, state)
        with allure.step("Re-import с другой provenance — blocked"):
            outcome = orch.import_execution(
                C.EXECUTION_BASE, provenance=dict(B.PROVENANCE_B))
            assert outcome["outcome"] == "blocked" and outcome["exit"] == 69
            entry = next(e for e in _state(project)["executions"]
                         if e["execution_id"] == C.EXECUTION_BASE)
            assert entry["bound_revision"] == 1


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("21A-F4: boundary-token matching collected node IDs")
@allure.severity(allure.severity_level.BLOCKER)
class TestNodeIdBoundary:
    @allure.title("UNIT-VAL-0010 не покрывает UNIT-VAL-001 при accept "
                  "implementation")
    def test_lookalike_node_id_not_accepted(self, project):
        orch = project.orchestrator()
        project.prepare_harness()
        project.init(orch)
        orch.accept("context", project.context_envelope())
        orch.accept("scenarios", project.scenarios_envelope())
        orch.accept("review", project.review_envelope())
        lookalike_nodes = [
            C.NODE_ID.format(sid=C.LOOKALIKE_SCENARIO_ID),
            C.NODE_ID.format(sid=C.SCENARIO_IDS[1]),
            C.NODE_ID.format(sid=C.SCENARIO_IDS[2]),
        ]
        utils.list_ok(project.runner, lookalike_nodes)
        with allure.step("Lookalike node ID не считается покрытием"):
            with pytest.raises(WorkflowBlockedError, match="UNIT-VAL-001"):
                orch.accept("implementation", project.impl_envelope())

    @allure.title("Реальные параметризованные node IDs покрывают сценарии")
    def test_real_parametrized_ids_cover(self, project):
        orch = project.orchestrator()
        project.prepare_harness()
        project.init(orch)
        orch.accept("context", project.context_envelope())
        orch.accept("scenarios", project.scenarios_envelope())
        orch.accept("review", project.review_envelope())
        outcome = orch.accept("implementation", project.impl_envelope())
        assert outcome == "accepted"
