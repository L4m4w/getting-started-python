"""pr verify: read-only re-verification записанного PR по targeted get.

Сценарий из ревизионной репетиции 39C: bump входной ревизии переводит
verified-публикацию в blocked («input revision changed»), при этом
существующий remote-эффект остаётся недоказуемым без смены spec или
ручной правки state. ``pr verify`` закрывает разрыв: freshness, текущая
ревизия, phase executed, корректная записанная identity
(number/spec/spec_sha256), отсутствие unresolved own/inherited
create-intents — и только затем единственный внешний вызов, targeted
``get`` по записанному номеру с commit/tree, body-integrity и exact-spec
проверками против текущей ревизии.

Ветки результата:

- полное точное доказательство → ``verified`` + journal ``pr-verify``
  для текущей ревизии; number/url/spec и completed create-intent
  сохраняются без переписывания;
- доказанный 404, mismatch, неполный/противоречивый snapshot →
  ``blocked``; ``verified``-запись деградирует — ложного утверждения
  не остаётся;
- get-exception → ``unknown`` (75): ``verified``-запись деградирует в
  ``unknown`` — статус допускает повторный verify после восстановления
  remote; для blocked/created записей статус и marker сохраняются;
- нарушение локальной целостности записанной evidence (identity,
  head commit/tree, body payload) на ``verified``-записи →
  деградация в ``blocked`` с описанием находки;
- нет --online/transport, не-ревизионная причина blocked, unresolved
  own/inherited intent → локальный отказ до любого remote-вызова,
  такой отказ не считается отрицательной проверкой и не деградирует
  ``verified``.

Строго offline: fake transports, у которых ``create``/``search``
немедленно падают, и изолированные tmp stores; сеть и реальные
репозитории не используются. В каждой ветке число ``create``-вызовов — 0.
"""
import argparse
import copy
import sys

import allure
import pytest

from infrastructure.workflow import adapters, github
from infrastructure.workflow import orchestrator as orch_mod
from infrastructure.workflow import state as state_mod
from infrastructure.workflow.state import (
    WorkflowBlockedError, WorkflowPermissionError)
from test_data.consts import workflow as C
from test_data.consts import workflow_21r_b as B
from test_data.utils import workflow as utils
from tools import workflow as cli_mod


@pytest.fixture
def project(tmp_path):
    return utils.Project(tmp_path / "proj")


def _state(project, workflow_id=None):
    if workflow_id is not None:
        return state_mod.load_state(project.store_dir / workflow_id)
    return project.workflow_state()


def _workflow_dir(project):
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


def _strict_get_transport(remote):
    """get-only fake: ``search``/``create`` немедленно падают.

    ``remote`` — отображение ``(repo, number) -> PrRef | None |
    Exception``; get записывает вызов и отдаёт/поднимает записанное.
    """
    transport = adapters.FakePrTransport(
        search_result=AssertionError("pr verify never searches"),
        create_result=AssertionError("pr verify never creates"))

    def get(repo, wanted):
        transport.calls.append(("get", (repo, wanted)))
        value = remote.get((repo, wanted))
        if isinstance(value, BaseException):
            raise value
        return value
    transport.get = get
    return transport


def _verified_project(project, role="app", number=B.PR_CREATED_NUMBER):
    """executed + prepare + create verified; remote хранит созданный ref."""
    project.drive_commit_to_executed()
    remote = {}

    def create(spec):
        ref = _mk_ref(spec, number=number)
        remote[(spec["repo"], number)] = ref
        return ref
    transport = adapters.FakePrTransport(
        search_result=[], create_result=create)

    def get(repo, wanted):
        transport.calls.append(("get", (repo, wanted)))
        return remote.get((repo, wanted))
    transport.get = get
    orch = project.orchestrator(pr_transports={role: transport})
    orch.pr_prepare(role, **_prepare_args(role))
    outcome = orch.pr_create(role, execute=True, online=True)
    assert outcome["outcome"] == "verified"
    return orch, transport, remote


def _revision2_to_executed(project, orch, *,
                           head_sha=C.APP_HEAD_COMMIT_SHA,
                           tests_commit=C.TESTS_COMMIT_2):
    """Bump ревизии и повторный прогон до executed.

    ``head_sha``/``tests_commit`` задают, какой вход меняется; чтобы
    записанный spec роли оставался доказуемым, head этой роли менять
    нельзя: для app меняется tests_commit, для tests — app head.
    """
    if head_sha != C.APP_HEAD_COMMIT_SHA:
        project.git.register_commit(
            head_sha, utils.snapshot_tree(project.app_repo))
    project.sync_tests_commit(tests_commit)
    project.init(orch, app_head_kind="commit", app_head_git_sha=head_sha,
                 app_head_sha256=None, tests_commit=tests_commit)
    assert _state(project)["input"]["revision"] == 2
    for kind, envelope in _accept_envelopes(project):
        orch.accept(kind, envelope)
    utils.harness_run(project.runner, project.root, B.EXECUTION_HEAD_2,
                      C.HEAD_JUNIT, 0, tests_commit=tests_commit,
                      declared={"app_base_sha": head_sha})
    assert orch.run_execution("head")["outcome"] == "recorded"
    utils.write_manifest(project.root, B.EXECUTION_BASE_2, C.BASE_JUNIT, 1,
                         tests_commit=tests_commit,
                         declared={"app_base_sha": C.APP_BASE_SHA})
    assert orch.import_execution(B.EXECUTION_BASE_2)[
        "outcome"] == "imported"
    assert _state(project)["phase"] == "executed"


def _revision_blocked_setup(project, role="app"):
    """verified на rev1 → revision bump (head роли сохранён) → blocked."""
    orch, transport, remote = _verified_project(project, role)
    if role == "tests":
        _revision2_to_executed(project, orch,
                               head_sha=C.APP_HEAD_COMMIT_SHA_2,
                               tests_commit=C.TESTS_COMMIT)
    else:
        _revision2_to_executed(project, orch)
    entry = _pr_entry(project, role)
    assert entry["status"] == "blocked"
    assert entry["blocked_reason"] == orch_mod.PR_REVISION_BLOCK_REASON
    return orch, transport, remote


def _accept_envelopes(project):
    """Accept-цепочка повторного доведения ревизии/линии."""
    return [("context", project.context_envelope()),
            ("scenarios", project.scenarios_envelope()),
            ("review", project.review_envelope()),
            ("implementation", project.impl_envelope()),
            ("bindings", project.bindings_envelope())]


def _pr_create_intents(project, workflow_id=None):
    return [i for i in _state(project, workflow_id)["intents"]
            if i["operation"] == "pr.create"]


def _inject_own_intent(project, status):
    """Записанный open pr.create intent рядом с blocked-записью."""
    wf_dir = _workflow_dir(project)
    state = state_mod.load_state(wf_dir)
    entry = state["publications"]["pr"]["app"]
    intent = state_mod.new_intent(
        state, "pr.create",
        {"repo": "app", "spec_sha256": entry["spec_sha256"]})
    intent["status"] = status
    state_mod.save_state(wf_dir, state)
    return intent


def _superseded_child_at_executed(project):
    """Parent executed + unresolved create → child линия до executed.

    У child запись pr.app blocked наследованным (не ревизионным)
    blocker'ом; parent intent остаётся unresolved.
    """
    project.drive_commit_to_executed()
    transport = adapters.FakePrTransport(
        search_result=[],
        create_result=adapters.RunOutcome(None, error="timeout"))
    orch = project.orchestrator(pr_transports={"app": transport})
    orch.pr_prepare("app", title=B.PARENT_SPEC_TITLE,
                    head_branch=B.HEAD_BRANCH, base_branch=B.BASE_BRANCH)
    assert orch.pr_create("app", execute=True, online=True)["exit"] == 75
    old_id = _state(project)["workflow_id"]
    project.git.register_commit(
        C.APP_BASE_SHA_2, dict(project.git.commits[C.APP_BASE_SHA]))
    project.git.register_commit(
        C.APP_HEAD_COMMIT_SHA_2, utils.snapshot_tree(project.app_repo))
    new_id, _ = project.init(
        orch, app_base_sha=C.APP_BASE_SHA_2, supersede=True,
        app_head_kind="commit", app_head_git_sha=C.APP_HEAD_COMMIT_SHA_2,
        app_head_sha256=None)
    orch2 = project.orchestrator()
    for kind, envelope in _accept_envelopes(project):
        orch2.accept(kind, envelope, workflow_id=new_id)
    utils.harness_run(project.runner, project.root, B.EXECUTION_HEAD_3,
                      C.HEAD_JUNIT, 0,
                      declared={"app_base_sha": C.APP_HEAD_COMMIT_SHA_2})
    assert orch2.run_execution("head", workflow_id=new_id)[
        "outcome"] == "recorded"
    utils.write_manifest(project.root, B.EXECUTION_BASE_2, C.BASE_JUNIT, 1,
                         declared={"app_base_sha": C.APP_BASE_SHA_2})
    assert orch2.import_execution(
        B.EXECUTION_BASE_2, workflow_id=new_id)["outcome"] == "imported"
    assert _state(project, new_id)["phase"] == "executed"
    return orch, transport, old_id, new_id


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("pr verify: read-only re-proof записанного PR")
@allure.severity(allure.severity_level.BLOCKER)
class TestVerifyProof:
    @allure.title("rev-blocked exact PR: targeted get → verified; "
                  "number/spec/intent и completed intent неизменны")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_revision_blocked_reverified(self, project, role):
        orch, transport, remote = _revision_blocked_setup(project, role)
        entry = _pr_entry(project, role)
        spec_before = dict(entry["spec"])
        intents_before = copy.deepcopy(_pr_create_intents(project))
        strict = _strict_get_transport(remote)
        verifier = project.orchestrator(pr_transports={role: strict})
        with allure.step("pr verify --online: единственный get по "
                         "записанному номеру"):
            result = verifier.pr_verify(role, online=True)
        with allure.step("Verified: только fresh get, ноль create/search"):
            assert result["outcome"] == "verified"
            assert result["exit"] == 0
            assert result["number"] == B.PR_CREATED_NUMBER
            assert strict.calls == [
                ("get", (spec_before["repo"], B.PR_CREATED_NUMBER))]
            assert len(_creates(transport)) == 1
        with allure.step("Identity и completed create intent сохранены"):
            entry = _pr_entry(project, role)
            assert entry["status"] == "verified"
            assert entry["number"] == B.PR_CREATED_NUMBER
            assert entry["blocked_reason"] is None
            assert entry["spec"] == spec_before
            assert entry["spec_sha256"] == spec_before["spec_sha256"]
            assert entry["intent_id"] == intents_before[0]["intent_id"]
            assert _pr_create_intents(project) == intents_before
        with allure.step("Journal: pr-verify для текущей ревизии"):
            state = _state(project)
            assert state["phase"] == "executed"
            events = [e for e in state["journal"]
                      if e["event"] == "pr-verify"]
            assert len(events) == 1
            assert "revision 2" in events[0]["detail"]

    @allure.title("Повторный verify: fresh get каждый раз; после "
                  "отрицательной проверки verified не сохраняется")
    def test_repeat_verify_and_demote(self, project):
        orch, transport, remote = _revision_blocked_setup(project)
        strict = _strict_get_transport(remote)
        verifier = project.orchestrator(pr_transports={"app": strict})
        with allure.step("Первый verify — verified"):
            assert verifier.pr_verify("app", online=True)[
                "outcome"] == "verified"
        with allure.step("Повтор — новый targeted get, снова verified"):
            assert verifier.pr_verify("app", online=True)[
                "outcome"] == "verified"
            gets = [c for c in strict.calls if c[0] == "get"]
            assert len(gets) == 2
        with allure.step("Remote изменился — свежая проверка деградирует "
                         "verified в blocked"):
            remote[(C.APP_REPO_KEY, B.PR_CREATED_NUMBER)].title = \
                "hijacked title"
            out = verifier.pr_verify("app", online=True)
            assert out["outcome"] == "blocked" and out["exit"] == 69
            entry = _pr_entry(project)
            assert entry["status"] == "blocked"
            assert entry["blocked_reason"] != \
                orch_mod.PR_REVISION_BLOCK_REASON
            assert entry["number"] == B.PR_CREATED_NUMBER
        with allure.step("Не-ревизионная причина blocked не обходится"):
            out = verifier.pr_verify("app", online=True)
            assert out["outcome"] == "blocked" and out["exit"] == 69
            assert len([c for c in strict.calls if c[0] == "get"]) == 3
            assert _creates(strict) == []

    @allure.title("404 по записанному номеру: blocked без поиска "
                  "замены, create и resend")
    def test_get_404_blocked(self, project):
        orch, transport, remote = _revision_blocked_setup(project)
        remote.pop((C.APP_REPO_KEY, B.PR_CREATED_NUMBER))
        strict = _strict_get_transport(remote)
        verifier = project.orchestrator(pr_transports={"app": strict})
        with allure.step("Targeted get → None: доказанное отсутствие"):
            result = verifier.pr_verify("app", online=True)
        with allure.step("Blocked; identity и completed intent сохранены"):
            assert result["outcome"] == "blocked"
            assert result["exit"] == 69
            assert "not found" in result["detail"]
            entry = _pr_entry(project)
            assert entry["status"] == "blocked"
            assert entry["number"] == B.PR_CREATED_NUMBER
            assert entry["spec"]["spec_sha256"] == entry["spec_sha256"]
            assert _pr_create_intents(project)[0]["status"] == "completed"
            assert strict.calls == [
                ("get", (C.APP_REPO_KEY, B.PR_CREATED_NUMBER))]
            assert _creates(strict) == []

    @allure.title("get exception: indeterminate unknown (75), записанное "
                  "состояние и marker сохранены")
    def test_get_exception_unknown(self, project):
        orch, transport, remote = _revision_blocked_setup(project)
        remote[(C.APP_REPO_KEY, B.PR_CREATED_NUMBER)] = \
            RuntimeError("backend down")
        strict = _strict_get_transport(remote)
        verifier = project.orchestrator(pr_transports={"app": strict})
        with allure.step("Targeted get падает — эффект indeterminate"):
            result = verifier.pr_verify("app", online=True)
        with allure.step("unknown exit 75; blocked+marker сохранён"):
            assert result["outcome"] == "unknown"
            assert result["exit"] == 75
            entry = _pr_entry(project)
            assert entry["status"] == "blocked"
            assert entry["blocked_reason"] == \
                orch_mod.PR_REVISION_BLOCK_REASON
            assert entry["number"] == B.PR_CREATED_NUMBER
            errors = [e for e in _state(project).get("errors") or []
                      if e.get("stage") == "pr_verify"]
            assert errors and errors[0]["kind"] == "get_error"
            assert _creates(strict) == []

    @allure.title("Remote ref отличается от spec — blocked "
                  "(title/head/body/files/number)")
    @pytest.mark.parametrize("field,value", [
        ("title", "changed title"),
        ("head_branch", "wf/other"),
        ("base_branch", "release"),
        ("head_sha", "f" * 40),
        ("body_sha256", "f" * 64),
        ("files", ["other/File.java"]),
        ("number", B.PR_CREATED_NUMBER + 1),
    ])
    def test_get_mismatch_blocked(self, project, field, value):
        orch, transport, remote = _revision_blocked_setup(project)
        ref = remote[(C.APP_REPO_KEY, B.PR_CREATED_NUMBER)]
        setattr(ref, field, value)
        strict = _strict_get_transport(remote)
        verifier = project.orchestrator(pr_transports={"app": strict})
        with allure.step(f"get отдаёт ref с другим {field}"):
            result = verifier.pr_verify("app", online=True)
        with allure.step("Blocked; number/spec/intent сохранены"):
            assert result["outcome"] == "blocked"
            assert result["exit"] == 69
            entry = _pr_entry(project)
            assert entry["status"] == "blocked"
            assert entry["number"] == B.PR_CREATED_NUMBER
            assert entry["spec"]["spec_sha256"] == entry["spec_sha256"]
            assert _pr_create_intents(project)[0]["status"] == "completed"
            assert _creates(strict) == []

    @allure.title("Неполный snapshot (голый PrRef) — blocked без create")
    def test_incomplete_ref_blocked(self, project):
        orch, transport, remote = _revision_blocked_setup(project)
        remote[(C.APP_REPO_KEY, B.PR_CREATED_NUMBER)] = adapters.PrRef(
            repo=C.APP_REPO_KEY, number=B.PR_CREATED_NUMBER)
        strict = _strict_get_transport(remote)
        verifier = project.orchestrator(pr_transports={"app": strict})
        with allure.step("get отдаёт ref без title/head/files"):
            result = verifier.pr_verify("app", online=True)
        with allure.step("Blocked; create/search не вызывались"):
            assert result["outcome"] == "blocked"
            assert result["exit"] == 69
            assert _pr_entry(project)["status"] == "blocked"
            assert strict.calls == [
                ("get", (C.APP_REPO_KEY, B.PR_CREATED_NUMBER))]
            assert _creates(strict) == []

    @allure.title("created-запись (number без proof): verify доводит "
                  "до verified тем же targeted get")
    def test_created_entry_verified(self, project):
        project.drive_commit_to_executed()

        def create(spec):
            return _mk_ref(spec)
        transport = adapters.FakePrTransport(
            search_result=[], create_result=create, get_map={})
        orch = project.orchestrator(pr_transports={"app": transport})
        orch.pr_prepare("app", **_prepare_args("app"))
        with allure.step("create вернул ref, get его не подтвердил — "
                         "entry 'created'"):
            assert orch.pr_create("app", execute=True, online=True)[
                "outcome"] == "created"
            assert _pr_entry(project)["number"] == B.PR_CREATED_NUMBER
        spec = _pr_entry(project)["spec"]
        strict = _strict_get_transport(
            {(C.APP_REPO_KEY, B.PR_CREATED_NUMBER): _mk_ref(spec)})
        verifier = project.orchestrator(pr_transports={"app": strict})
        with allure.step("pr verify — exact get доказывает запись"):
            result = verifier.pr_verify("app", online=True)
        with allure.step("verified; completed intent и number сохранены"):
            assert result["outcome"] == "verified"
            assert _pr_entry(project)["status"] == "verified"
            assert _pr_entry(project)["number"] == B.PR_CREATED_NUMBER
            assert _pr_create_intents(project)[0]["status"] == "completed"
            assert len(_creates(transport)) == 1
            assert _creates(strict) == []

    @allure.title("head_sha записанного spec ≠ текущей ревизии: blocked "
                  "до remote-вызова, ноль get")
    def test_stale_head_blocked_locally(self, project):
        orch, transport, remote = _verified_project(project)
        with allure.step("Revision bump с НОВЫМ app head commit"):
            _revision2_to_executed(
                project, orch, head_sha=C.APP_HEAD_COMMIT_SHA_2,
                tests_commit=C.TESTS_COMMIT_2)
            assert _pr_entry(project)["blocked_reason"] == \
                orch_mod.PR_REVISION_BLOCK_REASON
        strict = _strict_get_transport(remote)
        verifier = project.orchestrator(pr_transports={"app": strict})
        with allure.step("spec.head_sha устарел — локальный отказ"):
            result = verifier.pr_verify("app", online=True)
        with allure.step("Blocked; get не вызывался"):
            assert result["outcome"] == "blocked"
            assert result["exit"] == 69
            assert "head_sha" in result["detail"]
            assert strict.calls == []
            assert _pr_entry(project)["status"] == "blocked"
            assert _creates(strict) == []


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("pr verify: guards до любого remote-вызова")
@allure.severity(allure.severity_level.BLOCKER)
class TestVerifyGuards:
    @allure.title("Нет --online: permission, ноль transport-вызовов")
    def test_offline_permission(self, project):
        orch, transport, remote = _revision_blocked_setup(project)
        strict = _strict_get_transport(remote)
        verifier = project.orchestrator(pr_transports={"app": strict})
        with allure.step("pr verify без --online"):
            with pytest.raises(WorkflowPermissionError):
                verifier.pr_verify("app", online=False)
        with allure.step("Get не выполнялся; запись осталась blocked"):
            assert strict.calls == []
            assert _pr_entry(project)["status"] == "blocked"

    @allure.title("Нет transport: permission до любого вызова")
    def test_no_transport_permission(self, project):
        orch, transport, remote = _revision_blocked_setup(project)
        verifier = project.orchestrator()
        with allure.step("pr verify без configured transport"):
            with pytest.raises(WorkflowPermissionError):
                verifier.pr_verify("app", online=True)
        with allure.step("Запись осталась blocked+marker"):
            assert _pr_entry(project)["status"] == "blocked"

    @allure.title("Phase < executed: domain-отказ до transport-вызова")
    def test_phase_guard(self, project):
        project.init()
        strict = _strict_get_transport({})
        verifier = project.orchestrator(pr_transports={"app": strict})
        with allure.step("pr verify на phase initialized"):
            with pytest.raises(WorkflowBlockedError):
                verifier.pr_verify("app", online=True)
        with allure.step("Get не выполнялся"):
            assert strict.calls == []

    @allure.title("pending-запись без remote-эффекта: blocked, ноль "
                  "remote-вызовов")
    def test_pending_no_remote(self, project):
        project.drive_commit_to_executed()
        strict = _strict_get_transport({})
        orch = project.orchestrator(pr_transports={"app": strict})
        orch.pr_prepare("app", **_prepare_args("app"))
        with allure.step("spec подготовлен, но dispatch не было"):
            result = orch.pr_verify("app", online=True)
        with allure.step("Blocked до transport-вызова"):
            assert result["outcome"] == "blocked"
            assert result["exit"] == 69
            assert strict.calls == []

    @allure.title("Unresolved own intent (declared/dispatched/unknown): "
                  "blocked до remote")
    @pytest.mark.parametrize("status",
                             ("declared", "dispatched", "unknown"))
    def test_open_intent_blocks(self, project, status):
        orch, transport, remote = _revision_blocked_setup(project)
        intent = _inject_own_intent(project, status)
        strict = _strict_get_transport(remote)
        verifier = project.orchestrator(pr_transports={"app": strict})
        with allure.step(f"Open intent {intent['intent_id']} ({status})"):
            result = verifier.pr_verify("app", online=True)
        with allure.step("Blocked; intent остаётся unresolved, get не "
                         "вызывался"):
            assert result["outcome"] == "blocked"
            assert result["exit"] == 69
            assert intent["intent_id"] in result["detail"]
            assert strict.calls == []
            kept = [i for i in _pr_create_intents(project)
                    if i["intent_id"] == intent["intent_id"]][0]
            assert kept["status"] == status
            assert _pr_entry(project)["status"] == "blocked"

    @allure.title("Inherited unresolved blocker: blocked до remote; "
                  "после подстановки recorded identity — тот же отказ")
    def test_inherited_blocker(self, project):
        orch, transport, old_id, new_id = \
            _superseded_child_at_executed(project)
        strict = _strict_get_transport({})
        verifier = project.orchestrator(pr_transports={"app": strict})
        with allure.step("Child entry blocked наследованной причиной"):
            out = verifier.pr_verify("app", workflow_id=new_id,
                                     online=True)
            assert out["outcome"] == "blocked" and out["exit"] == 69
            assert strict.calls == []
        with allure.step("Marker + spec + number подставлены — "
                         "inherited всё равно блокирует"):
            parent = _pr_entry(project, "app", old_id)
            wf_dir = project.store_dir / new_id
            state = state_mod.load_state(wf_dir)
            entry = state["publications"]["pr"]["app"]
            entry.update(
                blocked_reason=orch_mod.PR_REVISION_BLOCK_REASON,
                spec=dict(parent["spec"]),
                spec_sha256=parent["spec_sha256"],
                number=B.PR_PARENT_NUMBER)
            state_mod.save_state(wf_dir, state)
            out = verifier.pr_verify("app", workflow_id=new_id,
                                     online=True)
            assert out["outcome"] == "blocked" and out["exit"] == 69
            assert "superseded" in out["detail"]
            assert strict.calls == []
            assert len(_creates(transport)) == 1
            assert _creates(strict) == []

    @allure.title("Испорченная recorded identity (spec_sha256/number): "
                  "локальный отказ, ноль remote")
    @pytest.mark.parametrize("damage", ("spec_sha256", "number"))
    def test_corrupt_identity_blocked(self, project, damage):
        orch, transport, remote = _revision_blocked_setup(project)
        with allure.step(f"Испортить записанное {damage}"):
            wf_dir = _workflow_dir(project)
            state = state_mod.load_state(wf_dir)
            entry = state["publications"]["pr"]["app"]
            if damage == "spec_sha256":
                entry["spec"]["title"] = "tampered title"
            else:
                entry["number"] = None
            state_mod.save_state(wf_dir, state)
        strict = _strict_get_transport(remote)
        verifier = project.orchestrator(pr_transports={"app": strict})
        with allure.step("verify отказывается до transport-вызова"):
            result = verifier.pr_verify("app", online=True)
        with allure.step("Blocked локально; get не вызывался"):
            assert result["outcome"] == "blocked"
            assert result["exit"] == 69
            assert strict.calls == []
            assert _creates(strict) == []


def _retamper_spec(project, mutate, role="app"):
    """Изменить записанный spec на месте, пересчитав его digest.

    Записанная identity остаётся внутренне согласованной (spec
    хешируется в записанный ``spec_sha256``), поэтому проверка доходит
    до head/body-гейтов, а не отсекается на identity.
    """
    wf_dir = _workflow_dir(project)
    state = state_mod.load_state(wf_dir)
    entry = state["publications"]["pr"][role]
    mutate(entry["spec"])
    payload = {key: value for key, value in entry["spec"].items()
               if key != "spec_sha256"}
    entry["spec"]["spec_sha256"] = adapters.spec_digest(payload)
    entry["spec_sha256"] = entry["spec"]["spec_sha256"]
    state_mod.save_state(wf_dir, state)


def _published_project(project):
    """executed + uploaded testops + обе роли PR verified → published."""
    orchestrator = project.drive_commit_to_executed()
    project.publish_handlers()
    outcome = orchestrator.publish_testops(C.EXECUTION_HEAD,
                                           execute=True)
    assert outcome["outcome"] == "uploaded"
    transports = {role: project.fake_pr_for(role)
                  for role in ("app", "tests")}
    orch = project.orchestrator(pr_transports=transports)
    for role in ("app", "tests"):
        files = [C.CHANGED_APP_FILE] if role == "app" else []
        orch.pr_prepare(role, title="unit PR", head_branch="wf/head",
                        base_branch="main", files=files)
        outcome = orch.pr_create(role, execute=True, online=True)
        assert outcome["outcome"] == "verified", outcome
    assert _state(project)["phase"] == "published"
    return orch, transports


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("pr verify: stale verified не переживает свежую проверку")
@allure.severity(allure.severity_level.BLOCKER)
class TestStaleVerifiedDemotion:
    """39DR: деградация ``verified`` по итогам выполненной проверки.

    ``verified`` — подтверждённое утверждение: после свежей проверки,
    которая его не редоказала (indeterminate get, доказанный mismatch,
    нарушение локальной целостности recorded evidence), оно обязано
    быть снято. Recorded number/url/spec и completed create intent
    при этом не переписываются.
    """

    @allure.title("verified + get exception → unknown (75): claim "
                  "снят, identity/intent сохранены, ноль create")
    def test_get_exception_demotes_verified(self, project):
        orch, transport, remote = _verified_project(project)
        spec_before = dict(_pr_entry(project)["spec"])
        intents_before = copy.deepcopy(_pr_create_intents(project))
        remote[(C.APP_REPO_KEY, B.PR_CREATED_NUMBER)] = \
            RuntimeError("backend down")
        strict = _strict_get_transport(remote)
        verifier = project.orchestrator(pr_transports={"app": strict})
        with allure.step("Targeted get падает на verified-записи"):
            result = verifier.pr_verify("app", online=True)
        with allure.step("unknown (75); verified снят, но не заблокирован"):
            assert result["outcome"] == "unknown"
            assert result["exit"] == 75
            entry = _pr_entry(project)
            assert entry["status"] == "unknown"
            assert entry["number"] == B.PR_CREATED_NUMBER
            assert entry["spec"] == spec_before
            assert entry["spec_sha256"] == spec_before["spec_sha256"]
            assert _pr_create_intents(project) == intents_before
            assert _state(project)["phase"] == "executed"
            errors = [e for e in _state(project).get("errors") or []
                      if e.get("stage") == "pr_verify"]
            assert errors and errors[0]["kind"] == "get_error"
            assert strict.calls == [
                ("get", (C.APP_REPO_KEY, B.PR_CREATED_NUMBER))]
            assert _creates(strict) == []

    @allure.title("unknown после временного сбоя: повторный verify "
                  "свежим get снова доводит до verified")
    def test_unknown_reverify_restores_verified(self, project):
        orch, transport, remote = _verified_project(project)
        key = (C.APP_REPO_KEY, B.PR_CREATED_NUMBER)
        good_ref = remote[key]
        remote[key] = RuntimeError("flaky backend")
        strict = _strict_get_transport(remote)
        verifier = project.orchestrator(pr_transports={"app": strict})
        with allure.step("verified + get exception → unknown"):
            assert verifier.pr_verify("app", online=True)[
                "outcome"] == "unknown"
            assert _pr_entry(project)["status"] == "unknown"
        with allure.step("Remote восстановлен — re-verify редоказывает"):
            remote[key] = good_ref
            result = verifier.pr_verify("app", online=True)
        with allure.step("verified восстановлен; ноль create/search"):
            assert result["outcome"] == "verified"
            assert result["exit"] == 0
            entry = _pr_entry(project)
            assert entry["status"] == "verified"
            assert entry["number"] == B.PR_CREATED_NUMBER
            assert entry["blocked_reason"] is None
            gets = [c for c in strict.calls if c[0] == "get"]
            assert gets == [("get", key), ("get", key)]
            assert _creates(strict) == []

    @allure.title("verified + head_sha не текущей ревизии → blocked "
                  "до remote; claim снят, ноль get")
    def test_head_integrity_demotes_verified(self, project):
        orch, transport, remote = _verified_project(project)
        with allure.step("spec.head_sha → не существующий commit SHA "
                         "(digest пересчитан — identity согласована)"):
            _retamper_spec(project, lambda spec: spec.update(
                head_sha="f" * 40))
        strict = _strict_get_transport(remote)
        verifier = project.orchestrator(pr_transports={"app": strict})
        with allure.step("pr verify — отказ на локальной head-проверке"):
            result = verifier.pr_verify("app", online=True)
        with allure.step("Blocked; verified снят, remote не опрашивался"):
            assert result["outcome"] == "blocked"
            assert result["exit"] == 69
            entry = _pr_entry(project)
            assert entry["status"] == "blocked"
            assert "head_sha" in entry["blocked_reason"] or \
                "commit" in entry["blocked_reason"]
            assert entry["blocked_reason"] != \
                orch_mod.PR_REVISION_BLOCK_REASON
            assert entry["number"] == B.PR_CREATED_NUMBER
            assert strict.calls == []
            assert _creates(strict) == []

    @allure.title("verified + невоспроизводимый body payload → blocked; "
                  "claim снят, ноль get")
    def test_body_integrity_demotes_verified(self, project):
        orch, transport, remote = _verified_project(project)
        with allure.step("spec: body_sha256 без body_text (digest "
                         "пересчитан — identity согласована)"):
            _retamper_spec(project, lambda spec: spec.update(
                body_sha256="f" * 64))
        strict = _strict_get_transport(remote)
        verifier = project.orchestrator(pr_transports={"app": strict})
        with allure.step("pr verify — отказ на body-integrity"):
            result = verifier.pr_verify("app", online=True)
        with allure.step("Blocked; verified снят, remote не опрашивался"):
            assert result["outcome"] == "blocked"
            assert result["exit"] == 69
            entry = _pr_entry(project)
            assert entry["status"] == "blocked"
            assert "body" in entry["blocked_reason"]
            assert entry["blocked_reason"] != \
                orch_mod.PR_REVISION_BLOCK_REASON
            assert entry["number"] == B.PR_CREATED_NUMBER
            assert strict.calls == []
            assert _creates(strict) == []

    @allure.title("verified + испорченная recorded identity → blocked; "
                  "claim снят до remote")
    def test_corrupt_identity_demotes_verified(self, project):
        orch, transport, remote = _verified_project(project)
        with allure.step("Записанный number → None"):
            wf_dir = _workflow_dir(project)
            state = state_mod.load_state(wf_dir)
            state["publications"]["pr"]["app"]["number"] = None
            state_mod.save_state(wf_dir, state)
        strict = _strict_get_transport(remote)
        verifier = project.orchestrator(pr_transports={"app": strict})
        with allure.step("pr verify — отказ на recorded identity"):
            result = verifier.pr_verify("app", online=True)
        with allure.step("Blocked; verified снят, remote не опрашивался"):
            assert result["outcome"] == "blocked"
            assert result["exit"] == 69
            assert "identity" in result["detail"]
            entry = _pr_entry(project)
            assert entry["status"] == "blocked"
            assert entry["blocked_reason"] != \
                orch_mod.PR_REVISION_BLOCK_REASON
            assert strict.calls == []
            assert _creates(strict) == []

    @allure.title("published + indeterminate get → unknown; "
                  "refresh_phase опускает workflow до executed")
    def test_published_demotion_recomputes_phase(self, project):
        orch, transports = _published_project(project)
        app_number = _pr_entry(project, "app")["number"]
        strict = _strict_get_transport(
            {(C.APP_REPO_KEY, app_number):
             RuntimeError("backend down")})
        verifier = project.orchestrator(pr_transports={"app": strict})
        with allure.step("pr verify на published workflow — get падает"):
            result = verifier.pr_verify("app", online=True)
        with allure.step("unknown; обязательная публикация не "
                         "подтверждена → фаза пересчитана"):
            assert result["outcome"] == "unknown"
            assert result["exit"] == 75
            state = _state(project)
            assert state["phase"] == "executed"
            entry = _pr_entry(project, "app")
            assert entry["status"] == "unknown"
            assert entry["number"] == app_number
            assert entry["spec"] is not None
            assert _pr_entry(project, "tests")["status"] == "verified"
            assert strict.calls == [
                ("get", (C.APP_REPO_KEY, app_number))]
            assert _creates(strict) == []

    @allure.title("published + mismatch → blocked; фаза пересчитана, "
                  "recorded identity сохранена")
    def test_published_mismatch_recomputes_phase(self, project):
        orch, transports = _published_project(project)
        entry = _pr_entry(project, "app")
        app_number = entry["number"]
        spec = entry["spec"]
        bad_ref = _mk_ref(spec, number=app_number)
        bad_ref.title = "hijacked title"
        strict = _strict_get_transport(
            {(C.APP_REPO_KEY, app_number): bad_ref})
        verifier = project.orchestrator(pr_transports={"app": strict})
        with allure.step("pr verify — remote ref не совпадает со spec"):
            result = verifier.pr_verify("app", online=True)
        with allure.step("Blocked; фаза executed, number/spec сохранены"):
            assert result["outcome"] == "blocked"
            assert result["exit"] == 69
            state = _state(project)
            assert state["phase"] == "executed"
            entry = _pr_entry(project, "app")
            assert entry["status"] == "blocked"
            assert entry["number"] == app_number
            assert entry["spec"] == spec
            assert _pr_entry(project, "tests")["status"] == "verified"
            assert _creates(strict) == []

    @allure.title("Отказ permission (нет --online/transport) — не "
                  "проверка: verified не деградирует")
    def test_permission_refusal_keeps_verified(self, project):
        orch, transport, remote = _verified_project(project)
        strict = _strict_get_transport(remote)
        verifier = project.orchestrator(pr_transports={"app": strict})
        with allure.step("verified + нет --online"):
            with pytest.raises(WorkflowPermissionError):
                verifier.pr_verify("app", online=False)
            assert _pr_entry(project)["status"] == "verified"
        with allure.step("verified + нет transport"):
            bare = project.orchestrator()
            with pytest.raises(WorkflowPermissionError):
                bare.pr_verify("app", online=True)
        with allure.step("Запись осталась verified, ноль вызовов"):
            assert _pr_entry(project)["status"] == "verified"
            assert strict.calls == []
            assert _creates(strict) == []


@allure.epic("Инфраструктура")
@allure.feature("Workflow CLI")
@allure.story("pr verify: wiring и dispatch")
@allure.severity(allure.severity_level.CRITICAL)
class TestCliVerify:
    """CLI-уровень: --pr-transport github wiring и cmd_pr dispatch."""

    @staticmethod
    def _options(**kw):
        base = dict(action="pr", pr_action="verify", repo="app",
                    online=False, execute=False, workflow_id=None,
                    store_dir=None, pr_transport="none", title=None,
                    body=None, files=None, head_branch=None,
                    base_branch=None, head_sha=None)
        base.update(kw)
        return argparse.Namespace(**base)

    @allure.title("--pr-transport github проводит wiring для verify; "
                  "none/default — пусто; конструктор без I/O")
    def test_verify_transport_wiring(self, monkeypatch):
        calls = []
        monkeypatch.setattr(github.EnvGitHubToken, "__call__",
                            lambda self: calls.append(self) or "x")
        monkeypatch.setattr(github.UrllibHttp, "request",
                            lambda *a, **k: calls.append("http"))
        with allure.step("github + pr verify → transport у обеих ролей"):
            orchestrator = cli_mod._orchestrator(
                self._options(pr_transport="github"))
            transport = orchestrator.pr_transports["app"]
            assert isinstance(transport, github.GitHubPrTransport)
            assert orchestrator.pr_transports["tests"] is transport
        with allure.step("default none и явный none — без transport"):
            assert cli_mod._orchestrator(
                self._options()).pr_transports == {}
            assert cli_mod._orchestrator(
                self._options(pr_transport="none")).pr_transports == {}
        with allure.step("pr prepare с github — всё ещё без transport"):
            assert cli_mod._orchestrator(
                self._options(pr_action="prepare",
                              pr_transport="github")).pr_transports == {}
        with allure.step("конструктор не трогал provider и HTTP"):
            assert calls == []

    @allure.title("cmd_pr диспетчит verify с repo/online; парсер "
                  "принимает subcommand и --online")
    def test_cli_dispatch_verify(self, monkeypatch, capsys):
        captured = {}

        class _StubOrchestrator:
            def pr_verify(self, role, workflow_id=None, online=False):
                captured.update(role=role, workflow_id=workflow_id,
                                online=online)
                return {"outcome": "verified",
                        "number": B.PR_CREATED_NUMBER, "exit": 0}

        monkeypatch.setattr(cli_mod, "_orchestrator",
                            lambda options: _StubOrchestrator())
        with allure.step("cmd_pr dispatch → pr_verify(app, online=True)"):
            code = cli_mod.cmd_pr(self._options(online=True), None)
            assert code == 0
            assert captured == {"role": "app", "workflow_id": None,
                                "online": True}
        with allure.step("main() парсит `pr verify --repo app --online`"):
            monkeypatch.setattr(
                sys, "argv",
                ["workflow.py", "pr", "verify", "--repo", "app",
                 "--online"])
            assert cli_mod.main() == 0
            assert '"verified"' in capsys.readouterr().out
