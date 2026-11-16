"""22B регрессии: durable PR body payload и checkpoint читаемого number.

- Body absent/empty/nonempty/CRLF/Unicode/невалидный UTF-8 — canonical
  spec/intent contract (digest по точным UTF-8 bytes, без trim).
- Durable payload snapshot под workflow dir; digest/source/snapshot
  missing/drift блокирует до любого remote read или POST.
- Legacy spec с hash без текста — blocked до safe re-prepare; legacy
  spec без body (digest=None) допускается.
- Читаемый create number/URL сохраняется до verification GET; crash на
  любом save/dispatch не даёт второго create; durable number —
  targeted get, не fresh search.
- Повтор prepare/create/reconcile/resume без новых dispatch;
  unknown+[] и known+404/error; ancestry two-hop.

Все проверки считают fake create/get/search вызовы, не только outcomes;
строго offline в tmp dirs: fake runner / fake PR transport / FakeGit /
isolated stores.
"""
import hashlib

import allure
import pytest

from infrastructure.workflow import adapters
from infrastructure.workflow import state as state_mod
from infrastructure.workflow.state import WorkflowValidationError
from test_data.consts import workflow as C
from test_data.consts import workflow_21r_b as B
from test_data.consts import workflow_21r2 as R2
from test_data.consts import workflow_pr_payload as P
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


def _count(transport, name):
    return sum(1 for op, _ in transport.calls if op == name)


def _mk_ref(spec, number=P.PR_NUMBER):
    return adapters.PrRef(
        repo=spec["repo"], number=number,
        url=P.PR_URL_TEMPLATE.format(number=number),
        title=spec["title"], head_branch=spec["head_branch"],
        base_branch=spec["base_branch"], head_sha=spec.get("head_sha"),
        body_sha256=spec.get("body_sha256"),
        files=list(spec.get("files") or []))


def _prepare_args(role, body_path=None):
    files = [C.CHANGED_APP_FILE] if role == "app" else list(C.TEST_FILES)
    args = dict(title=B.SPEC_TITLE, head_branch=B.HEAD_BRANCH,
                base_branch=B.BASE_BRANCH, files=files)
    if body_path is not None:
        args["body_path"] = str(body_path)
    return args


def _body_file(project, data):
    path = project.root / P.BODY_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_bytes(bytes(data))
    return path


def _snapshot_path(project, spec, workflow_id=None):
    rel = (spec.get("body_snapshot") or {}).get("path")
    if not rel:
        return None
    return _workflow_dir(project, workflow_id) / rel


def _sha(data):
    raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    return hashlib.sha256(raw).hexdigest()


def _install_legacy_spec(project, role, *, body_sha256):
    """Spec в формате до 22B: нет body_text/body_source/body_snapshot."""
    orch = project.orchestrator()
    orch.pr_prepare(role, **_prepare_args(role))
    wf_dir = _workflow_dir(project)
    state = state_mod.load_state(wf_dir)
    entry = state["publications"]["pr"][role]
    legacy = dict(entry["spec"])
    for key in ("body_text", "body_source", "body_snapshot"):
        legacy.pop(key, None)
    legacy["body_sha256"] = body_sha256
    legacy["spec_sha256"] = adapters.spec_digest(legacy)
    entry.update(spec=legacy, spec_sha256=legacy["spec_sha256"])
    state_mod.save_state(wf_dir, state)
    return legacy


def _created_with_readable_number(project, role, body=None, *,
                                  number=P.PR_NUMBER):
    """Executed + prepare (+body) + create: transport возвращает читаемый
    ref, но get() не подтверждает — entry 'created' с номером."""
    project.drive_commit_to_executed()
    remote = []

    def create(spec):
        ref = _mk_ref(spec, number=number)
        remote.append(ref)
        return ref

    transport = adapters.FakePrTransport(
        search_result=[], create_result=create, get_map={})
    orch = project.orchestrator(pr_transports={role: transport})
    body_path = _body_file(project, body) if body is not None else None
    orch.pr_prepare(role, **_prepare_args(role, body_path))
    first = orch.pr_create(role, execute=True, online=True)
    return orch, transport, remote, first


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("22B: body spec contract и durable payload")
@allure.severity(allure.severity_level.BLOCKER)
class TestBodySpecContract:
    @allure.title("Absent body → canonical None/None; create работает")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_absent_body_canonical_none(self, project, role):
        project.drive_commit_to_executed()
        transport = project.fake_pr_for(role)
        orch = project.orchestrator(pr_transports={role: transport})
        orch.pr_prepare(role, **_prepare_args(role))
        spec = _pr_entry(project, role)["spec"]
        with allure.step("Spec: body_text/body_sha256/source/snapshot "
                         "равны None"):
            assert spec["body_text"] is None
            assert spec["body_sha256"] is None
            assert spec["body_source"] is None
            assert spec["body_snapshot"] is None
        with allure.step("Create: transport получил spec без body"):
            outcome = orch.pr_create(role, execute=True, online=True)
            assert outcome["outcome"] == "verified"
            sent = [args[0] for op, args in transport.calls
                    if op == "create"][0]
            assert sent["body_text"] is None
            assert sent["body_sha256"] is None

    @allure.title("Empty body file → canonical None/None")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_empty_body_canonical_none(self, project, role):
        project.drive_commit_to_executed()
        body = _body_file(project, P.BODY_EMPTY)
        orch = project.orchestrator()
        orch.pr_prepare(role, **_prepare_args(role, body))
        spec = _pr_entry(project, role)["spec"]
        assert spec["body_text"] is None
        assert spec["body_sha256"] is None
        assert spec["body_snapshot"] is None
        assert not (_workflow_dir(project) / "payloads").exists()

    @allure.title("Nonempty body → text/digest/источник/snapshot в spec "
                  "и frozen intent")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_nonempty_body_spec_and_snapshot(self, project, role):
        project.drive_commit_to_executed()
        body = _body_file(project, P.BODY_TEXT)
        transport = project.fake_pr_for(role)
        orch = project.orchestrator(pr_transports={role: transport})
        orch.pr_prepare(role, **_prepare_args(role, body))
        spec = _pr_entry(project, role)["spec"]
        with allure.step("Spec несёт точные text/digest/источник/snapshot"):
            assert spec["body_text"] == P.BODY_TEXT
            assert spec["body_sha256"] == _sha(P.BODY_TEXT)
            assert spec["body_source"]["path"] == str(body.resolve())
            assert spec["body_source"]["sha256"] == _sha(P.BODY_TEXT)
            assert spec["body_snapshot"]["sha256"] == _sha(P.BODY_TEXT)
        with allure.step("Snapshot под workflow dir хранит точные bytes"):
            snap = _snapshot_path(project, spec)
            assert snap.is_file()
            assert snap.read_bytes() == P.BODY_TEXT.encode("utf-8")
        with allure.step("Create: transport и intent несут body_text"):
            outcome = orch.pr_create(role, execute=True, online=True)
            assert outcome["outcome"] == "verified"
            sent = [args[0] for op, args in transport.calls
                    if op == "create"][0]
            assert sent["body_text"] == P.BODY_TEXT
            assert sent["body_sha256"] == _sha(P.BODY_TEXT)
            intent = _state(project)["intents"][-1]
            assert intent["target"]["spec"]["body_text"] == P.BODY_TEXT
            assert (intent["target"]["spec"]["body_snapshot"]
                    == spec["body_snapshot"])

    @allure.title("CRLF и Unicode body — точные bytes без нормализации")
    @pytest.mark.parametrize("text", (P.BODY_TEXT_CRLF,
                                     P.BODY_TEXT_UNICODE))
    def test_exact_bytes_crlf_unicode(self, project, text):
        project.drive_commit_to_executed()
        body = _body_file(project, text)
        orch = project.orchestrator()
        orch.pr_prepare("app", **_prepare_args("app", body))
        spec = _pr_entry(project)["spec"]
        assert spec["body_text"] == text
        assert spec["body_sha256"] == _sha(text)
        assert _snapshot_path(project, spec).read_bytes() == \
            text.encode("utf-8")

    @allure.title("Невалидный UTF-8 body — validation error, spec не "
                  "записан")
    def test_invalid_utf8_rejected(self, project):
        project.drive_commit_to_executed()
        body = _body_file(project, P.BODY_INVALID_UTF8)
        orch = project.orchestrator()
        with pytest.raises(WorkflowValidationError):
            orch.pr_prepare("app", **_prepare_args("app", body))
        assert _pr_entry(project)["spec"] is None
        assert not (_workflow_dir(project) / "payloads").exists()

    @allure.title("Missing body file — validation error")
    def test_missing_body_file_rejected(self, project):
        project.drive_commit_to_executed()
        orch = project.orchestrator()
        with pytest.raises(WorkflowValidationError):
            orch.pr_prepare("app", **_prepare_args(
                "app", project.root / "no-such-body.md"))
        assert _pr_entry(project)["spec"] is None

    @allure.title("Повторный prepare — честный no-op без новых эффектов")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_reprepare_idempotent_noop(self, project, role):
        project.drive_commit_to_executed()
        body = _body_file(project, P.BODY_TEXT)
        transport = project.fake_pr_for(role)
        orch = project.orchestrator(pr_transports={role: transport})
        first = orch.pr_prepare(role, **_prepare_args(role, body))
        assert first["outcome"] == "prepared"
        spec = _pr_entry(project, role)["spec"]
        snap = _snapshot_path(project, spec)
        snap_bytes = snap.read_bytes()
        with allure.step("Идентичный повтор — no-op, snapshot неизменён"):
            again = orch.pr_prepare(role, **_prepare_args(role, body))
            assert again["outcome"] == "no-op"
            assert _pr_entry(project, role)["spec"]["spec_sha256"] == \
                spec["spec_sha256"]
            assert snap.read_bytes() == snap_bytes
            assert transport.calls == []


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("22B: digest/source/snapshot guards до dispatch")
@allure.severity(allure.severity_level.BLOCKER)
class TestBodyDigestGuards:
    def _prepared(self, project, role, body=P.BODY_TEXT):
        project.drive_commit_to_executed()
        path = _body_file(project, body)
        transport = project.fake_pr_for(role)
        orch = project.orchestrator(pr_transports={role: transport})
        orch.pr_prepare(role, **_prepare_args(role, path))
        return orch, transport, path

    @allure.title("Snapshot missing → blocked до search/POST")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_snapshot_missing_blocked(self, project, role):
        orch, transport, _ = self._prepared(project, role)
        spec = _pr_entry(project, role)["spec"]
        _snapshot_path(project, spec).unlink()
        with allure.step("Create blocked; ни search, ни POST не ушли"):
            outcome = orch.pr_create(role, execute=True, online=True)
            assert outcome["outcome"] == "blocked"
            assert outcome["exit"] == 69
            assert "snapshot" in outcome["detail"]
            assert transport.calls == []

    @allure.title("Snapshot drift → blocked до search/POST")
    def test_snapshot_drift_blocked(self, project):
        orch, transport, _ = self._prepared(project, "app")
        spec = _pr_entry(project)["spec"]
        _snapshot_path(project, spec).write_bytes(b"tampered payload")
        outcome = orch.pr_create("app", execute=True, online=True)
        assert outcome["outcome"] == "blocked" and outcome["exit"] == 69
        assert transport.calls == []
        assert _pr_entry(project)["status"] == "blocked"

    @allure.title("Source missing → blocked до search/POST")
    def test_source_missing_blocked(self, project):
        orch, transport, body = self._prepared(project, "app")
        body.unlink()
        outcome = orch.pr_create("app", execute=True, online=True)
        assert outcome["outcome"] == "blocked" and outcome["exit"] == 69
        assert transport.calls == []

    @allure.title("Source drift → blocked до search/POST")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_source_drift_blocked(self, project, role):
        orch, transport, body = self._prepared(project, role)
        body.write_text(P.BODY_TEXT_ALT, encoding="utf-8")
        outcome = orch.pr_create(role, execute=True, online=True)
        assert outcome["outcome"] == "blocked" and outcome["exit"] == 69
        assert transport.calls == []

    @allure.title("Tampered spec body_text → digest mismatch, blocked")
    def test_body_text_tamper_blocked(self, project):
        orch, transport, _ = self._prepared(project, "app")
        wf_dir = _workflow_dir(project)
        state = state_mod.load_state(wf_dir)
        state["publications"]["pr"]["app"]["spec"]["body_text"] = \
            P.BODY_TEXT_ALT
        state_mod.save_state(wf_dir, state)
        outcome = orch.pr_create("app", execute=True, online=True)
        assert outcome["outcome"] == "blocked" and outcome["exit"] == 69
        assert transport.calls == []

    @allure.title("Legacy spec: hash без текста — blocked; re-prepare "
                  "разблокирует")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_legacy_hash_without_text_blocked(self, project, role):
        project.drive_commit_to_executed()
        legacy = _install_legacy_spec(project, role,
                                      body_sha256="a" * 64)
        transport = project.fake_pr_for(role)
        orch = project.orchestrator(pr_transports={role: transport})
        with allure.step("Create с невоспроизводимым body — blocked до "
                         "любого remote вызова"):
            outcome = orch.pr_create(role, execute=True, online=True)
            assert outcome["outcome"] == "blocked"
            assert outcome["exit"] == 69
            assert "legacy" in outcome["detail"]
            assert transport.calls == []
        with allure.step("Safe re-prepare создаёт новый spec; create "
                         "проходит"):
            prepared = orch.pr_prepare(role, **_prepare_args(role))
            assert prepared["outcome"] == "prepared"
            outcome = orch.pr_create(role, execute=True, online=True)
            assert outcome["outcome"] == "verified"
            assert _count(transport, "create") == 1

    @allure.title("Legacy spec без body (digest=None) допускается")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_legacy_no_body_spec_allowed(self, project, role):
        project.drive_commit_to_executed()
        _install_legacy_spec(project, role, body_sha256=None)
        transport = project.fake_pr_for(role)
        orch = project.orchestrator(pr_transports={role: transport})
        outcome = orch.pr_create(role, execute=True, online=True)
        assert outcome["outcome"] == "verified"
        assert _count(transport, "create") == 1

    @allure.title("Re-prepare восстанавливает потерянный snapshot "
                  "(идемпотентная запись); unblock — только новым spec")
    def test_reprepare_restores_snapshot(self, project):
        orch, transport, body = self._prepared(project, "app")
        spec = _pr_entry(project)["spec"]
        snap = _snapshot_path(project, spec)
        snap.unlink()
        blocked = orch.pr_create("app", execute=True, online=True)
        assert blocked["outcome"] == "blocked"
        with allure.step("Идентичный re-prepare — no-op по spec, но "
                         "payload восстановлен на диске"):
            again = orch.pr_prepare("app", **_prepare_args("app", body))
            assert again["outcome"] == "no-op"
            assert snap.is_file()
            assert snap.read_bytes() == P.BODY_TEXT.encode("utf-8")
        with allure.step("Blocked entry не снимается молча: create всё "
                         "ещё blocked до осознанного re-prepare"):
            still = orch.pr_create("app", execute=True, online=True)
            assert still["outcome"] == "blocked"
            assert _count(transport, "create") == 0
        with allure.step("Re-prepare нового spec → prepared → verified"):
            args = _prepare_args("app", body)
            args["title"] = "unit PR v2"
            prepared = orch.pr_prepare("app", **args)
            assert prepared["outcome"] == "prepared"
            outcome = orch.pr_create("app", execute=True, online=True)
            assert outcome["outcome"] == "verified"
            assert _count(transport, "create") == 1


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("22B: checkpoint читаемого create number до verification")
@allure.severity(allure.severity_level.BLOCKER)
class TestCreateNumberCheckpoint:
    @allure.title("Number/URL durable до verification GET: mid-get state "
                  "уже содержит created")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_number_durable_before_verify(self, project, role):
        project.drive_commit_to_executed()
        remote = {}

        def create(spec):
            ref = _mk_ref(spec, P.PR_NUMBER)
            remote["ref"] = ref
            return ref

        transport = adapters.FakePrTransport(
            search_result=[], create_result=create)
        observed = {}

        def get(repo, number):
            transport.calls.append(("get", (repo, number)))
            state = _state(project)
            entry = state["publications"]["pr"][role]
            intent = state["intents"][-1]
            observed["entry_status"] = entry["status"]
            observed["entry_number"] = entry["number"]
            observed["entry_url"] = entry["url"]
            observed["intent_status"] = intent["status"]
            observed["intent_evidence"] = dict(
                intent.get("evidence") or {})
            ref = remote.get("ref")
            return ref if ref is not None and ref.number == number \
                else None

        transport.get = get
        body = _body_file(project, P.BODY_TEXT)
        orch = project.orchestrator(pr_transports={role: transport})
        orch.pr_prepare(role, **_prepare_args(role, body))
        outcome = orch.pr_create(role, execute=True, online=True)
        assert outcome["outcome"] == "verified"
        with allure.step("Во время verification GET номер уже durable"):
            assert observed["entry_status"] == "created"
            assert observed["entry_number"] == P.PR_NUMBER
            assert observed["entry_url"] == \
                P.PR_URL_TEMPLATE.format(number=P.PR_NUMBER)
            assert observed["intent_status"] == "completed"
            assert observed["intent_evidence"]["number"] == P.PR_NUMBER
            assert observed["intent_evidence"]["verified"] is None
        with allure.step("После verify — verified, evidence дополнено"):
            entry = _pr_entry(project, role)
            assert entry["status"] == "verified"
            intent = _state(project)["intents"][-1]
            assert intent["evidence"]["verified"] is True
            assert intent["evidence"]["number"] == P.PR_NUMBER

    @allure.title("Crash после POST с читаемым номером перед verify: "
                  "durable number → targeted get, второго create нет")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_crash_after_post_before_verify(self, project, role):
        project.drive_commit_to_executed()
        remote = {}

        def create(spec):
            ref = _mk_ref(spec, P.PR_NUMBER)
            remote["ref"] = ref
            return ref

        transport = adapters.FakePrTransport(
            search_result=[], create_result=create)
        crashed = {"done": False}

        def get(repo, number):
            transport.calls.append(("get", (repo, number)))
            if not crashed["done"]:
                crashed["done"] = True
                raise KeyboardInterrupt("crash after POST before verify")
            return remote["ref"]

        transport.get = get
        orch = project.orchestrator(pr_transports={role: transport})
        orch.pr_prepare(role, **_prepare_args(role))
        with allure.step("KeyboardInterrupt в verification GET"):
            with pytest.raises(KeyboardInterrupt):
                orch.pr_create(role, execute=True, online=True)
        with allure.step("Durable: created + number, intent completed"):
            entry = _pr_entry(project, role)
            assert entry["status"] == "created"
            assert entry["number"] == P.PR_NUMBER
            intent = _state(project)["intents"][-1]
            assert intent["status"] == "completed"
            assert intent["evidence"]["number"] == P.PR_NUMBER
        with allure.step("Повтор: targeted get #N, второго create/search "
                         "нет"):
            outcome = orch.pr_create(role, execute=True, online=True)
            assert outcome["outcome"] == "verified"
            assert _count(transport, "create") == 1
            assert _count(transport, "search") == 1
            # crashed get + reprove get + внутренний get verify
            assert _count(transport, "get") == 3
            assert _pr_entry(project, role)["status"] == "verified"

    @allure.title("Lost save до записи number: dispatched intent "
                  "блокирует, reconcile усваивает, второго create нет")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_lost_save_keeps_blocking_intent(self, project, role,
                                             monkeypatch):
        project.drive_commit_to_executed()
        remote = {}

        def create(spec):
            ref = _mk_ref(spec, P.PR_NUMBER)
            remote["ref"] = ref
            return ref

        transport = adapters.FakePrTransport(
            search_result=lambda key: [remote["ref"]] if remote else [],
            create_result=create)

        def get(repo, number):
            transport.calls.append(("get", (repo, number)))
            return remote.get("ref")

        transport.get = get
        orch = project.orchestrator(pr_transports={role: transport})
        orch.pr_prepare(role, **_prepare_args(role))
        real_save = state_mod.save_state

        def flaky_save(wf_dir, st):
            if any(op == "create" for op, _ in transport.calls):
                raise RuntimeError("lost save after dispatch")
            return real_save(wf_dir, st)

        monkeypatch.setattr(state_mod, "save_state", flaky_save)
        with allure.step("Crash на save после POST — dispatched intent "
                         "сохранён"):
            with pytest.raises(RuntimeError):
                orch.pr_create(role, execute=True, online=True)
        monkeypatch.undo()
        entry = _pr_entry(project, role)
        intent = _state(project)["intents"][-1]
        assert intent["status"] == "dispatched"
        assert entry["status"] == "intent"
        with allure.step("Повторный create blocked до reconcile"):
            outcome = orch.pr_create(role, execute=True, online=True)
            assert outcome["outcome"] == "blocked"
            assert outcome["exit"] == 69
            assert _count(transport, "create") == 1
        with allure.step("Reconcile: fresh search adopted, create=1"):
            report = orch.reconcile(online=True)
            assert report[0]["action"] == "adopted"
            assert _pr_entry(project, role)["status"] == "verified"
            assert _count(transport, "create") == 1

    @allure.title("Get failure во время verify: created сохраняется; "
                  "re-prove targeted get без нового dispatch")
    def test_get_failure_keeps_created(self, project):
        project.drive_commit_to_executed()
        remote = {}

        def create(spec):
            ref = _mk_ref(spec, P.PR_NUMBER)
            remote["ref"] = ref
            return ref

        transport = adapters.FakePrTransport(
            search_result=[], create_result=create)
        failing = {"active": True}

        def get(repo, number):
            transport.calls.append(("get", (repo, number)))
            if failing["active"]:
                raise RuntimeError("get backend down")
            return remote["ref"]

        transport.get = get
        orch = project.orchestrator(pr_transports={"app": transport})
        orch.pr_prepare("app", **_prepare_args("app"))
        first = orch.pr_create("app", execute=True, online=True)
        assert first["outcome"] == "created"
        entry = _pr_entry(project)
        assert entry["status"] == "created"
        assert entry["number"] == P.PR_NUMBER
        intent = _state(project)["intents"][-1]
        assert intent["status"] == "completed"
        assert intent["evidence"]["verified"] is False
        with allure.step("После восстановления get — verified без "
                         "второго create"):
            failing["active"] = False
            second = orch.pr_create("app", execute=True, online=True)
            assert second["outcome"] == "verified"
            assert _count(transport, "create") == 1
            assert _count(transport, "search") == 1

    @allure.title("Повтор create/reconcile/resume с created entry — "
                  "ноль новых dispatch")
    def test_repeat_create_reconcile_resume_no_dispatch(self, project):
        orch, transport, remote, first = _created_with_readable_number(
            project, "app", body=P.BODY_TEXT)
        assert first["outcome"] == "created"
        calls_after_first = list(transport.calls)
        with allure.step("Повторный create — targeted get, blocked"):
            second = orch.pr_create("app", execute=True, online=True)
            assert second["outcome"] == "blocked"
            assert second["exit"] == 69
            assert _count(transport, "create") == 1
        with allure.step("Reconcile/resume без unfinished intents — "
                         "ноль новых вызовов"):
            report = orch.reconcile(online=True)
            assert report == []
            resumed = orch.resume(online=True)
            assert "next_step" in resumed
            assert _count(transport, "create") == 1
            assert _count(transport, "search") == 1
            assert _pr_entry(project)["status"] == "created"

    @allure.title("Unknown + search []: blocked навсегда, retry не "
                  "разрешён (с body spec)")
    def test_unknown_then_zero_search_stays_blocked(self, project):
        project.drive_commit_to_executed()
        body = _body_file(project, P.BODY_TEXT)
        transport = adapters.FakePrTransport(
            search_result=[],
            create_result=adapters.RunOutcome(None, error="timeout"))
        orch = project.orchestrator(pr_transports={"app": transport})
        orch.pr_prepare("app", **_prepare_args("app", body))
        first = orch.pr_create("app", execute=True, online=True)
        assert first["exit"] == 75
        with allure.step("Reconcile со свежим [] — blocked, intent "
                         "unresolved"):
            report = orch.reconcile(online=True)
            assert report[0]["action"] == "blocked"
            state = _state(project)
            assert state["intents"][-1]["status"] in \
                state_mod.UNFINISHED_INTENT_STATUSES
        with allure.step("Create/re-prepare запрещены, dispatch=1"):
            outcome = orch.pr_create("app", execute=True, online=True)
            assert outcome["outcome"] == "blocked"
            outcome = orch.pr_prepare("app", **_prepare_args("app", body))
            assert outcome["outcome"] == "blocked"
            assert _count(transport, "create") == 1

    @allure.title("Known number + get 404/error: created сохранён, "
                  "второго create нет")
    def test_known_number_404_and_error(self, project):
        orch, transport, remote, first = _created_with_readable_number(
            project, "app", body=P.BODY_TEXT)
        assert first["outcome"] == "created"
        spec = _pr_entry(project)["spec"]
        with allure.step("Get возвращает None (404) — blocked, не "
                         "recreate"):
            second = orch.pr_create("app", execute=True, online=True)
            assert second["outcome"] == "blocked"
            assert second["exit"] == 69
            assert _count(transport, "create") == 1
            assert _pr_entry(project)["status"] == "created"
        with allure.step("Get падает — indeterminate unknown"):
            transport.get_map[(spec["repo"], P.PR_NUMBER)] = (
                RuntimeError("get backend down"))
            third = orch.pr_create("app", execute=True, online=True)
            assert third["outcome"] == "unknown"
            assert third["exit"] == 75
            assert _count(transport, "create") == 1
            assert _pr_entry(project)["status"] == "created"


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("22B: lineage two-hop с body spec")
@allure.severity(allure.severity_level.BLOCKER)
class TestBodyLineageTwoHop:
    def _supersede(self, project, orch, *, base_sha, head_sha,
                   from_base=C.APP_BASE_SHA):
        new_id, _ = project.init(
            orch, app_base_sha=base_sha, supersede=True,
            app_head_kind="commit", app_head_git_sha=head_sha,
            app_head_sha256=None)
        project.git.register_commit(
            base_sha, dict(project.git.commits[from_base]))
        project.git.register_commit(
            head_sha, utils.snapshot_tree(project.app_repo))
        return new_id

    def _drive_lineage_executed(self, project, orch, workflow_id,
                                base_sha, head_sha):
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
            project.runner, project.root, P.EXECUTION_HEAD_7,
            C.HEAD_JUNIT, 0, declared={"app_base_sha": head_sha})
        assert orch.run_execution(
            "head", workflow_id=workflow_id)["outcome"] == "recorded"
        utils.write_manifest(
            project.root, P.EXECUTION_BASE_7, C.BASE_JUNIT, 1,
            declared={"app_base_sha": base_sha})
        assert orch.import_execution(
            P.EXECUTION_BASE_7, workflow_id=workflow_id)["outcome"] \
            == "imported"
        assert _state(project, workflow_id)["phase"] == "executed"

    @allure.title("Two-hop: resolved lineage effect + body spec — "
                  "targeted get вместо create")
    @pytest.mark.parametrize("role", ("app", "tests"))
    def test_two_hop_known_number_targeted_get(self, project, role):
        project.drive_commit_to_executed()
        gp_transport = adapters.FakePrTransport(
            search_result=[],
            create_result=adapters.RunOutcome(None, error="timeout"))
        orch = project.orchestrator(pr_transports={role: gp_transport})
        orch.pr_prepare(role, **_prepare_args(role))
        with allure.step("Grandparent: timeout create (unknown intent)"):
            first = orch.pr_create(role, execute=True, online=True)
            assert first["exit"] == 75
        grandparent_id = _state(project)["workflow_id"]
        self._supersede(project, orch, base_sha=C.APP_BASE_SHA_2,
                        head_sha=C.APP_HEAD_COMMIT_SHA_2)
        child_id = self._supersede(
            project, orch, base_sha=R2.APP_BASE_SHA_3,
            head_sha=R2.APP_HEAD_COMMIT_SHA_3,
            from_base=C.APP_BASE_SHA_2)
        with allure.step("Grandparent resolved adopted #N через два hop"):
            spec = _pr_entry(project, role, workflow_id=grandparent_id)[
                "spec"]
            ref = _mk_ref(spec, number=P.PR_LINEAGE_NUMBER)
            resolving = adapters.FakePrTransport(
                search_result=[ref],
                get_map={(spec["repo"], P.PR_LINEAGE_NUMBER): ref})
            orch2 = project.orchestrator(pr_transports={role: resolving})
            report = orch2.reconcile(workflow_id=grandparent_id,
                                     online=True)
            assert report[0]["action"] == "adopted"
        with allure.step("Child executed + prepare с body spec"):
            self._drive_lineage_executed(project, orch2, child_id,
                                         R2.APP_BASE_SHA_3,
                                         R2.APP_HEAD_COMMIT_SHA_3)
            body = _body_file(project, P.BODY_TEXT)
            prepared = orch2.pr_prepare(
                role, workflow_id=child_id,
                **_prepare_args(role, body))
            assert prepared["outcome"] == "prepared"
            child_spec = _pr_entry(project, role, workflow_id=child_id)[
                "spec"]
            assert child_spec["body_text"] == P.BODY_TEXT
        with allure.step("Create: записанный #N редоказан targeted get, "
                         "ни search, ни нового POST"):
            resolving.search_result = []
            resolving.get_map[(child_spec["repo"],
                               P.PR_LINEAGE_NUMBER)] = _mk_ref(
                child_spec, number=P.PR_LINEAGE_NUMBER)
            calls_before = list(resolving.calls)
            outcome = orch2.pr_create(role, workflow_id=child_id,
                                      execute=True, online=True)
            assert outcome["outcome"] == "adopted"
            assert outcome["verified"] is True
            assert outcome["number"] == P.PR_LINEAGE_NUMBER
            new_ops = [op for op, _ in
                       resolving.calls[len(calls_before):]]
            assert new_ops and all(op == "get" for op in new_ops)
            assert _count(gp_transport, "create") == 1
            assert _count(resolving, "create") == 0
            entry = _pr_entry(project, role, workflow_id=child_id)
            assert entry["status"] == "verified"
