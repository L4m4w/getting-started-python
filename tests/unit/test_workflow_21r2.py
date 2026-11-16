"""21R2 регрессии: durable guard известного remote effect после supersede.

- Разрешение parent intent снимает ложный stale blocker, но сохраняет
  durable guard: известный номер PR в ancestry редоказывается targeted
  get до любого нового dispatch — пустой search не разрешает второй
  create (F-21R-B-1).
- Terminal completed/created effect, записанный до supersede, наследуется
  как resolved snapshot и защищает новую линию так же.
- Второй supersede (grandparent→parent→child) не теряет ни unresolved
  ancestry (fail-closed через recorded supersedes-цепочку), ни известный
  remote effect.
- Контроль: линия без записанного эффекта выполняет свой первый create.

Все проверки считают реальные fake create/get вызовы до и после, а не
только outcomes; строго offline в tmp dirs: fake runner / fake PR
transport / isolated stores.
"""
import allure
import pytest

from infrastructure.workflow import adapters
from infrastructure.workflow import state as state_mod
from test_data.consts import workflow as C
from test_data.consts import workflow_21r_b as B
from test_data.consts import workflow_21r2 as R2
from test_data.utils import workflow as utils


@pytest.fixture
def project(tmp_path):
    return utils.Project(tmp_path / "proj")


def _state(project, workflow_id=None):
    if workflow_id is not None:
        return state_mod.load_state(project.store_dir / workflow_id)
    return project.workflow_state()


def _workflow_dir(project, workflow_id):
    return project.store_dir / workflow_id


def _pr_entry(project, role="app", workflow_id=None):
    return _state(project, workflow_id)["publications"]["pr"][role]


def _creates(transport):
    return [name for name, _ in transport.calls if name == "create"]


def _mk_ref(spec, number):
    return adapters.PrRef(
        repo=spec["repo"], number=number,
        url=B.PR_URL_TEMPLATE.format(number=number),
        title=spec["title"], head_branch=spec["head_branch"],
        base_branch=spec["base_branch"], head_sha=spec.get("head_sha"),
        body_sha256=spec.get("body_sha256"),
        files=list(spec.get("files") or []))


def _prepare_args(role, title):
    return dict(title=title, head_branch=B.HEAD_BRANCH,
                base_branch=B.BASE_BRANCH,
                files=[C.CHANGED_APP_FILE] if role == "app"
                else list(C.TEST_FILES))


def _inherited_pr(project, workflow_id, role="app"):
    return [i for i in _state(project, workflow_id)["inherited_intents"]
            if i.get("operation") == "pr.create"
            and (i.get("target") or {}).get("repo") == role]


def _register_child_commits(project, base_sha, head_sha, *,
                            from_base=C.APP_BASE_SHA):
    project.git.register_commit(
        base_sha, dict(project.git.commits[from_base]))
    project.git.register_commit(
        head_sha, utils.snapshot_tree(project.app_repo))


def _drive_lineage_executed(project, orch, workflow_id, base_sha,
                            head_sha, head_run, base_run):
    """Re-accept цепочки + head run + base import для новой линии."""
    orch.accept("context", project.context_envelope(),
                workflow_id=workflow_id)
    orch.accept("scenarios", project.scenarios_envelope(),
                workflow_id=workflow_id)
    orch.accept("review", project.review_envelope(),
                workflow_id=workflow_id)
    orch.accept("implementation", project.impl_envelope(),
                workflow_id=workflow_id)
    orch.accept("bindings", project.bindings_envelope(),
                workflow_id=workflow_id)
    utils.harness_run(
        project.runner, project.root, head_run, C.HEAD_JUNIT, 0,
        declared={"app_base_sha": head_sha})
    assert orch.run_execution(
        "head", workflow_id=workflow_id)["outcome"] == "recorded"
    utils.write_manifest(project.root, base_run, C.BASE_JUNIT, 1,
                         declared={"app_base_sha": base_sha})
    assert orch.import_execution(
        base_run, workflow_id=workflow_id)["outcome"] == "imported"
    assert _state(project, workflow_id)["phase"] == "executed"


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("21R2: resolved parent intent сохраняет guard remote effect")
@allure.severity(allure.severity_level.BLOCKER)
class TestR2ResolvedParentLineageGuard:
    """Parent adopted #N → snapshot resolved → child не повторяет create."""

    def _supersede_setup(self, project, role):
        """Parent executed + timed-out create; superseded commit-head
        lineage на втором base."""
        project.drive_commit_to_executed()
        transport = adapters.FakePrTransport(
            search_result=[],
            create_result=adapters.RunOutcome(None, error="timeout"))
        orch = project.orchestrator(pr_transports={role: transport})
        orch.pr_prepare(role, **_prepare_args(role, B.PARENT_SPEC_TITLE))
        first = orch.pr_create(role, execute=True, online=True)
        old_id = _state(project)["workflow_id"]
        new_id, _ = project.init(
            orch, app_base_sha=C.APP_BASE_SHA_2, supersede=True,
            app_head_kind="commit",
            app_head_git_sha=C.APP_HEAD_COMMIT_SHA_2,
            app_head_sha256=None)
        return orch, transport, first, old_id, new_id

    def _resolve_parent(self, project, role, old_id,
                        number=R2.PR_LINEAGE_NUMBER):
        """Reconcile parent с точным ref — adopted resolution с номером."""
        spec = _pr_entry(project, role, workflow_id=old_id)["spec"]
        ref = _mk_ref(spec, number=number)
        resolving = adapters.FakePrTransport(
            search_result=[ref],
            get_map={(spec["repo"], number): ref})
        orch2 = project.orchestrator(pr_transports={role: resolving})
        report = orch2.reconcile(workflow_id=old_id, online=True)
        return orch2, resolving, report

    def _executed_child(self, project, orch2, role, new_id):
        """Довести новую линию до executed и подготовить несовместимый
        spec; transport перестаёт видеть parent PR в search."""
        _register_child_commits(project, C.APP_BASE_SHA_2,
                                C.APP_HEAD_COMMIT_SHA_2)
        _drive_lineage_executed(
            project, orch2, new_id, C.APP_BASE_SHA_2,
            C.APP_HEAD_COMMIT_SHA_2, R2.EXECUTION_HEAD_4,
            R2.EXECUTION_BASE_3)
        prepared = orch2.pr_prepare(
            role, workflow_id=new_id,
            **_prepare_args(role, B.CHILD_SPEC_TITLE))
        assert prepared["outcome"] == "prepared"
        return _pr_entry(project, role, workflow_id=new_id)["spec"]

    @allure.title("Parent adopted + search []: child blocked, второго "
                  "create нет")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_resolved_parent_zero_search_no_new_create(
            self, project, role):
        orch, transport, first, old_id, new_id = self._supersede_setup(
            project, role)
        assert first["exit"] == 75
        orch2, resolving, report = self._resolve_parent(
            project, role, old_id)
        assert report[0]["action"] == "adopted"
        child_spec = self._executed_child(project, orch2, role, new_id)
        with allure.step("Search не видит PR #parent, targeted get "
                         "доказывает несовместимый remote effect"):
            resolving.search_result = []
            outcome = orch2.pr_create(role, workflow_id=new_id,
                                      execute=True, online=True)
            assert outcome["outcome"] == "blocked"
            assert outcome["exit"] == 69
        with allure.step("Ни один transport не получил новый create"):
            assert len(_creates(resolving)) == 0
            assert len(_creates(transport)) == 1
            entry = _pr_entry(project, role, workflow_id=new_id)
            assert entry["status"] == "blocked"
            assert str(R2.PR_LINEAGE_NUMBER) in entry["blocked_reason"]
            inherited = _inherited_pr(project, new_id, role)
            assert len(inherited) == 1
            assert inherited[0]["status"] == "resolved"
            assert (inherited[0]["resolved_in_parent"]
                    ["parent_evidence"]["number"]) == R2.PR_LINEAGE_NUMBER
            assert child_spec["spec_sha256"] == entry["spec"]["spec_sha256"]

    @allure.title("Parent adopted + get None (404): blocked, без "
                  "автоматического recreate")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_resolved_parent_get_none_blocked(self, project, role):
        orch, transport, first, old_id, new_id = self._supersede_setup(
            project, role)
        orch2, resolving, report = self._resolve_parent(
            project, role, old_id)
        assert report[0]["action"] == "adopted"
        self._executed_child(project, orch2, role, new_id)
        with allure.step("Recorded number не читается — blocked, не "
                         "recreate"):
            resolving.search_result = []
            resolving.get_map = {}
            outcome = orch2.pr_create(role, workflow_id=new_id,
                                      execute=True, online=True)
            assert outcome["outcome"] == "blocked"
            assert outcome["exit"] == 69
            assert len(_creates(resolving)) == 0
            assert len(_creates(transport)) == 1

    @allure.title("Parent adopted + get error: indeterminate unknown, "
                  "create=0")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_resolved_parent_get_error_unknown(self, project, role):
        orch, transport, first, old_id, new_id = self._supersede_setup(
            project, role)
        orch2, resolving, report = self._resolve_parent(
            project, role, old_id)
        assert report[0]["action"] == "adopted"
        child_spec = self._executed_child(project, orch2, role, new_id)
        with allure.step("Targeted get падает — эффект indeterminate"):
            resolving.search_result = []
            resolving.get_map[(child_spec["repo"],
                               R2.PR_LINEAGE_NUMBER)] = (
                RuntimeError("get backend down"))
            outcome = orch2.pr_create(role, workflow_id=new_id,
                                      execute=True, online=True)
            assert outcome["outcome"] == "unknown"
            assert outcome["exit"] == 75
            assert len(_creates(resolving)) == 0
            assert len(_creates(transport)) == 1

    @allure.title("Parent adopted + ref несовместим со spec: blocked")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_resolved_parent_mismatch_ref_blocked(self, project, role):
        orch, transport, first, old_id, new_id = self._supersede_setup(
            project, role)
        orch2, resolving, report = self._resolve_parent(
            project, role, old_id)
        assert report[0]["action"] == "adopted"
        child_spec = self._executed_child(project, orch2, role, new_id)
        with allure.step("Fetched ref не совпадает со spec — blocked"):
            resolving.search_result = []
            bad = _mk_ref(child_spec, number=R2.PR_LINEAGE_NUMBER)
            bad.head_sha = "f" * 40
            resolving.get_map[(child_spec["repo"],
                               R2.PR_LINEAGE_NUMBER)] = bad
            outcome = orch2.pr_create(role, workflow_id=new_id,
                                      execute=True, online=True)
            assert outcome["outcome"] == "blocked"
            assert outcome["exit"] == 69
            assert len(_creates(resolving)) == 0
            assert len(_creates(transport)) == 1

    @allure.title("Parent adopted + exact ref по текущему spec: "
                  "adoption без нового create")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_resolved_parent_exact_ref_adopted(self, project, role):
        orch, transport, first, old_id, new_id = self._supersede_setup(
            project, role)
        orch2, resolving, report = self._resolve_parent(
            project, role, old_id)
        assert report[0]["action"] == "adopted"
        child_spec = self._executed_child(project, orch2, role, new_id)
        with allure.step("Targeted get доказывает exact spec — "
                         "verified adoption"):
            resolving.search_result = []
            resolving.get_map[(child_spec["repo"],
                               R2.PR_LINEAGE_NUMBER)] = _mk_ref(
                child_spec, number=R2.PR_LINEAGE_NUMBER)
            outcome = orch2.pr_create(role, workflow_id=new_id,
                                      execute=True, online=True)
            assert outcome["outcome"] == "adopted"
            assert outcome["verified"] is True
            assert outcome["number"] == R2.PR_LINEAGE_NUMBER
        with allure.step("Entry verified, история сохранена, create=0, "
                         "повтор — no-op"):
            entry = _pr_entry(project, role, workflow_id=new_id)
            assert entry["status"] == "verified"
            assert entry["number"] == R2.PR_LINEAGE_NUMBER
            assert len(_creates(resolving)) == 0
            assert len(_creates(transport)) == 1
            assert _inherited_pr(project, new_id, role)[0]["status"] \
                == "resolved"
            again = orch2.pr_create(role, workflow_id=new_id,
                                    execute=True, online=True)
            assert again["outcome"] == "no-op"
            assert len(_creates(resolving)) == 0

    @allure.title("Re-prepare несовместимого spec: guard сохраняется, "
                  "create=0")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_blocked_survives_reprepare(self, project, role):
        orch, transport, first, old_id, new_id = self._supersede_setup(
            project, role)
        orch2, resolving, report = self._resolve_parent(
            project, role, old_id)
        assert report[0]["action"] == "adopted"
        self._executed_child(project, orch2, role, new_id)
        resolving.search_result = []
        first_try = orch2.pr_create(role, workflow_id=new_id,
                                    execute=True, online=True)
        assert first_try["outcome"] == "blocked"
        with allure.step("Re-prepare другого spec — lineage guard "
                         "всё ещё действует"):
            prepared = orch2.pr_prepare(
                role, workflow_id=new_id, title=B.SPEC_TITLE,
                head_branch="h2", base_branch="m2")
            assert prepared["outcome"] == "prepared"
            outcome = orch2.pr_create(role, workflow_id=new_id,
                                      execute=True, online=True)
            assert outcome["outcome"] == "blocked"
            assert outcome["exit"] == 69
            assert len(_creates(resolving)) == 0
            assert len(_creates(transport)) == 1

    @allure.title("Revision + re-prepare: записанный lineage-эффект "
                  "не теряется")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_blocked_survives_revision(self, project, role):
        orch, transport, first, old_id, new_id = self._supersede_setup(
            project, role)
        orch2, resolving, report = self._resolve_parent(
            project, role, old_id)
        assert report[0]["action"] == "adopted"
        self._executed_child(project, orch2, role, new_id)
        resolving.search_result = []
        blocked = orch2.pr_create(role, workflow_id=new_id,
                                  execute=True, online=True)
        assert blocked["outcome"] == "blocked"
        with allure.step("Новая ревизия линии (изменённые requirements, "
                         "тот же commit head) доведена до executed"):
            (project.root / C.REQUIREMENTS_REL).write_text(
                C.REQUIREMENTS_TEXT + "# rev2\n", encoding="utf-8")
            project.sync_tests_commit(C.TESTS_COMMIT)
            project.init(orch2, app_base_sha=C.APP_BASE_SHA_2,
                         app_head_kind="commit",
                         app_head_git_sha=C.APP_HEAD_COMMIT_SHA_2,
                         app_head_sha256=None)
            assert _state(project, new_id)["input"]["revision"] == 2
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
                project.runner, project.root, R2.EXECUTION_HEAD_5,
                C.HEAD_JUNIT, 0,
                declared={"app_base_sha": C.APP_HEAD_COMMIT_SHA_2})
            assert orch2.run_execution(
                "head", workflow_id=new_id)["outcome"] == "recorded"
            rebind = orch2.import_execution(R2.EXECUTION_BASE_3,
                                            workflow_id=new_id)
            assert rebind["outcome"] == "rebound"
            assert _state(project, new_id)["phase"] == "executed"
        with allure.step("Re-prepare + create — записанный эффект "
                         "всё ещё блокирует"):
            prepared = orch2.pr_prepare(
                role, workflow_id=new_id, title=B.SPEC_TITLE,
                head_branch="h3", base_branch="m3",
                files=([C.CHANGED_APP_FILE] if role == "app"
                       else list(C.TEST_FILES)))
            assert prepared["outcome"] == "prepared"
            outcome = orch2.pr_create(role, workflow_id=new_id,
                                      execute=True, online=True)
            assert outcome["outcome"] == "blocked"
            assert outcome["exit"] == 69
            assert len(_creates(resolving)) == 0
            assert len(_creates(transport)) == 1
            inherited = _inherited_pr(project, new_id, role)
            assert inherited[0]["status"] == "resolved"


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("21R2: terminal effect до supersede и two-hop ancestry")
@allure.severity(allure.severity_level.BLOCKER)
class TestR2TerminalAndTwoHop:
    def _verified_parent(self, project, role,
                         number=R2.PR_TERMINAL_NUMBER):
        """Parent executed + prepare + verified create — terminal intent
        с записанным remote effect ещё до supersede."""
        project.drive_commit_to_executed()
        remote = []

        def create(spec):
            ref = _mk_ref(spec, number=number)
            remote.append(ref)
            transport.get_map[(spec["repo"], number)] = ref
            return ref

        transport = adapters.FakePrTransport(
            search_result=[], create_result=create)
        orch = project.orchestrator(pr_transports={role: transport})
        orch.pr_prepare(role, **_prepare_args(role, B.PARENT_SPEC_TITLE))
        first = orch.pr_create(role, execute=True, online=True)
        return orch, transport, remote, first

    def _supersede(self, project, orch, *, base_sha, head_sha,
                   from_base=C.APP_BASE_SHA):
        new_id, _ = project.init(
            orch, app_base_sha=base_sha, supersede=True,
            app_head_kind="commit", app_head_git_sha=head_sha,
            app_head_sha256=None)
        _register_child_commits(project, base_sha, head_sha,
                                from_base=from_base)
        return new_id

    @allure.title("Terminal created до supersede: эффект наследуется и "
                  "блокирует дубль")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_terminal_effect_before_supersede(self, project, role):
        orch, transport, remote, first = self._verified_parent(
            project, role)
        assert first["outcome"] == "verified" and len(remote) == 1
        old_id = _state(project)["workflow_id"]
        with allure.step("Supersede: terminal intent наследуется как "
                         "resolved snapshot с записанным номером"):
            new_id = self._supersede(
                project, orch, base_sha=C.APP_BASE_SHA_2,
                head_sha=C.APP_HEAD_COMMIT_SHA_2)
            inherited = _inherited_pr(project, new_id, role)
            assert len(inherited) == 1
            assert inherited[0]["status"] == "resolved"
            assert inherited[0]["inherited_from"] == old_id
            assert (inherited[0]["resolved_in_parent"]
                    ["parent_evidence"]["number"]) \
                == R2.PR_TERMINAL_NUMBER
        with allure.step("Новая линия executed; search [] не разрешает "
                         "второй create"):
            child_transport = adapters.FakePrTransport(
                search_result=[],
                get_map={(remote[0].repo, R2.PR_TERMINAL_NUMBER):
                         remote[0]})
            orch2 = project.orchestrator(
                pr_transports={role: child_transport})
            _drive_lineage_executed(
                project, orch2, new_id, C.APP_BASE_SHA_2,
                C.APP_HEAD_COMMIT_SHA_2, R2.EXECUTION_HEAD_4,
                R2.EXECUTION_BASE_3)
            prepared = orch2.pr_prepare(
                role, workflow_id=new_id,
                **_prepare_args(role, B.CHILD_SPEC_TITLE))
            assert prepared["outcome"] == "prepared"
            outcome = orch2.pr_create(role, workflow_id=new_id,
                                      execute=True, online=True)
            assert outcome["outcome"] == "blocked"
            assert outcome["exit"] == 69
            assert len(_creates(child_transport)) == 0
            assert len(_creates(transport)) == 1
            assert len(remote) == 1

    @allure.title("Two-hop: terminal effect переживает второй supersede")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_two_hop_known_effect_survives(self, project, role):
        orch, transport, remote, first = self._verified_parent(
            project, role)
        assert first["outcome"] == "verified"
        grandparent_id = _state(project)["workflow_id"]
        parent_id = self._supersede(
            project, orch, base_sha=C.APP_BASE_SHA_2,
            head_sha=C.APP_HEAD_COMMIT_SHA_2)
        with allure.step("Второй supersede: записанный эффект "
                         "доползает до grandchild"):
            child_id = self._supersede(
                project, orch, base_sha=R2.APP_BASE_SHA_3,
                head_sha=R2.APP_HEAD_COMMIT_SHA_3,
                from_base=C.APP_BASE_SHA_2)
            inherited = _inherited_pr(project, child_id, role)
            assert len(inherited) == 1
            assert inherited[0]["status"] == "resolved"
            assert inherited[0]["inherited_from"] == grandparent_id
            assert (inherited[0]["resolved_in_parent"]
                    ["parent_evidence"]["number"]) \
                == R2.PR_TERMINAL_NUMBER
        with allure.step("Grandchild executed; create блокируется "
                         "записанным эффектом, дубля нет"):
            child_transport = adapters.FakePrTransport(
                search_result=[],
                get_map={(remote[0].repo, R2.PR_TERMINAL_NUMBER):
                         remote[0]})
            orch2 = project.orchestrator(
                pr_transports={role: child_transport})
            _drive_lineage_executed(
                project, orch2, child_id, R2.APP_BASE_SHA_3,
                R2.APP_HEAD_COMMIT_SHA_3, R2.EXECUTION_HEAD_5,
                R2.EXECUTION_BASE_4)
            prepared = orch2.pr_prepare(
                role, workflow_id=child_id,
                **_prepare_args(role, B.CHILD_SPEC_TITLE))
            assert prepared["outcome"] == "prepared"
            outcome = orch2.pr_create(role, workflow_id=child_id,
                                      execute=True, online=True)
            assert outcome["outcome"] == "blocked"
            assert outcome["exit"] == 69
            assert len(_creates(child_transport)) == 0
            assert len(_creates(transport)) == 1
            assert len(remote) == 1

    @allure.title("Two-hop: unresolved ancestry остаётся fail-closed, "
                  "resolution через цепочку supersedes")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_two_hop_unresolved_ancestry(self, project, role):
        project.drive_commit_to_executed()
        transport = adapters.FakePrTransport(
            search_result=[],
            create_result=adapters.RunOutcome(None, error="timeout"))
        orch = project.orchestrator(pr_transports={role: transport})
        orch.pr_prepare(role, **_prepare_args(role, B.PARENT_SPEC_TITLE))
        assert orch.pr_create(role, execute=True,
                              online=True)["exit"] == 75
        grandparent_id = _state(project)["workflow_id"]
        parent_id = self._supersede(
            project, orch, base_sha=C.APP_BASE_SHA_2,
            head_sha=C.APP_HEAD_COMMIT_SHA_2)
        with allure.step("Второй supersede до разрешения grandparent: "
                         "unresolved ancestry не теряется"):
            child_id = self._supersede(
                project, orch, base_sha=R2.APP_BASE_SHA_3,
                head_sha=R2.APP_HEAD_COMMIT_SHA_3,
                from_base=C.APP_BASE_SHA_2)
            inherited = _inherited_pr(project, child_id, role)
            unresolved = [i for i in inherited
                          if i["status"] != "resolved"]
            assert len(unresolved) == 1
            assert unresolved[0]["inherited_from"] == grandparent_id
        with allure.step("Grandparent ещё unresolved — prepare child "
                         "fail-closed"):
            orch2 = project.orchestrator(pr_transports={})
            out = orch2.pr_prepare(role, workflow_id=child_id,
                                   **_prepare_args(role,
                                                   B.CHILD_SPEC_TITLE))
            assert out["outcome"] == "blocked" and out["exit"] == 69
        with allure.step("Reconcile grandparent adopted — resolution "
                         "доходит через два hop"):
            spec = _pr_entry(project, role,
                             workflow_id=grandparent_id)["spec"]
            ref = _mk_ref(spec, number=R2.PR_LINEAGE_NUMBER)
            resolving = adapters.FakePrTransport(
                search_result=[ref],
                get_map={(spec["repo"], R2.PR_LINEAGE_NUMBER): ref})
            orch3 = project.orchestrator(
                pr_transports={role: resolving})
            report = orch3.reconcile(workflow_id=grandparent_id,
                                     online=True)
            assert report[0]["action"] == "adopted"
            _drive_lineage_executed(
                project, orch3, child_id, R2.APP_BASE_SHA_3,
                R2.APP_HEAD_COMMIT_SHA_3, R2.EXECUTION_HEAD_5,
                R2.EXECUTION_BASE_4)
            prepared = orch3.pr_prepare(
                role, workflow_id=child_id,
                **_prepare_args(role, B.CHILD_SPEC_TITLE))
            assert prepared["outcome"] == "prepared"
            inherited = _inherited_pr(project, child_id, role)
            assert inherited[0]["status"] == "resolved"
            assert (inherited[0]["resolved_in_parent"]
                    ["parent_evidence"]["number"]) \
                == R2.PR_LINEAGE_NUMBER
        with allure.step("Записанный эффект блокирует create и в "
                         "grandchild-линии"):
            resolving.search_result = []
            outcome = orch3.pr_create(role, workflow_id=child_id,
                                      execute=True, online=True)
            assert outcome["outcome"] == "blocked"
            assert outcome["exit"] == 69
            assert len(_creates(resolving)) == 0
            assert len(_creates(transport)) == 1


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("21R2: контрольные сценарии без записанного эффекта")
@allure.severity(allure.severity_level.BLOCKER)
class TestR2LineageGuardControls:
    @allure.title("Первая линия без ancestry: обычный create работает")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_first_create_no_ancestry_works(self, project, role):
        project.drive_commit_to_executed()
        transport = project.fake_pr_for(role)
        orch = project.orchestrator(pr_transports={role: transport})
        orch.pr_prepare(role, **_prepare_args(role, B.SPEC_TITLE))
        with allure.step("Create без записанного эффекта — verified"):
            outcome = orch.pr_create(role, execute=True, online=True)
            assert outcome["outcome"] == "verified"
            assert len(_creates(transport)) == 1
            assert _pr_entry(project, role)["status"] == "verified"

    @allure.title("Supersede без PR-эффекта в parent: новый create "
                  "разрешён")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_supersede_without_effect_can_create(self, project, role):
        orch = project.drive_commit_to_executed()
        old_id = _state(project)["workflow_id"]
        new_id, _ = project.init(
            orch, app_base_sha=C.APP_BASE_SHA_2, supersede=True,
            app_head_kind="commit",
            app_head_git_sha=C.APP_HEAD_COMMIT_SHA_2,
            app_head_sha256=None)
        assert new_id != old_id
        assert _inherited_pr(project, new_id, role) == []
        _register_child_commits(project, C.APP_BASE_SHA_2,
                                C.APP_HEAD_COMMIT_SHA_2)
        transport = project.fake_pr_for(role)
        orch2 = project.orchestrator(pr_transports={role: transport})
        _drive_lineage_executed(
            project, orch2, new_id, C.APP_BASE_SHA_2,
            C.APP_HEAD_COMMIT_SHA_2, R2.EXECUTION_HEAD_4,
            R2.EXECUTION_BASE_3)
        with allure.step("Новая линия без эффекта выполняет свой первый "
                         "create"):
            orch2.pr_prepare(role, workflow_id=new_id,
                             **_prepare_args(role, B.CHILD_SPEC_TITLE))
            outcome = orch2.pr_create(role, workflow_id=new_id,
                                      execute=True, online=True)
            assert outcome["outcome"] == "verified"
            assert len(_creates(transport)) == 1
            assert _pr_entry(project, role, workflow_id=new_id)[
                "status"] == "verified"
