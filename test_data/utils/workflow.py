"""Helpers для unit-проверок оркестратора: временные проекты, envelope,
фиктивные evidence и подменный runner/transport. Всё offline в temp dirs."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from infrastructure.reporting.testops import results as tresults
from infrastructure.reporting.testops import state as tstate
from infrastructure.workflow import adapters, contracts
from test_data.consts import workflow as C
from tools import harness as harness_mod


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_doc(root, relpath, content):
    path = Path(root) / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"path": relpath, "sha256": sha256_text(content)}


def unit_scenario_contract(*, expected_bindings=None):
    return contracts.ScenarioContract(
        contract_version=C.UNIT_SCENARIO_CONTRACT_VERSION,
        index=dict(C.UNIT_SCENARIO_INDEX),
        head_scenarios=tuple(C.SCENARIO_IDS),
        base_scenarios=tuple(C.BASE_SCENARIO_IDS),
        expected_bindings=(dict(C.BINDINGS)
                           if expected_bindings is None
                           else dict(expected_bindings)),
    )


def default_source_files():
    files = list(harness_mod.API_SOURCE_FILES)
    for relpath in C.TEST_FILES:
        if relpath not in files:
            files.append(relpath)
    return files


def snapshot_tree(root):
    """Снимок файлов checkout (без служебных artifacts/ и envelopes/)."""
    root = Path(root)
    tree = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith(("artifacts/", "envelopes/")):
            continue
        tree[rel] = path.read_bytes()
    return tree


class FakeRunner:
    """Подмена SubprocessRunner: предикат argv -> handler, счётчик вызовов."""

    def __init__(self, default_code=0):
        self.calls = []
        self.handlers = []
        self.default_code = default_code

    def add(self, predicate, handler):
        self.handlers.append((predicate, handler))
        return self

    def on_tool(self, tool, handler):
        return self.add(lambda argv: len(argv) > 1 and argv[1] == tool,
                        handler)

    def run(self, argv, cwd, line_callback=None, env=None, timeout=None):
        argv = [str(arg) for arg in argv]
        self.calls.append(argv)
        for predicate, handler in reversed(self.handlers):
            if predicate(argv):
                outcome = handler(argv, line_callback)
                if outcome is not None:
                    return outcome
        return adapters.RunOutcome(self.default_code)

    def count(self, predicate):
        return sum(1 for argv in self.calls if predicate(argv))

    def tool_calls(self, tool):
        return [argv for argv in self.calls
                if len(argv) > 1 and argv[1] == tool]


def ok_lines(lines, code=0):
    def handler(argv, on_line):
        for line in lines:
            if on_line:
                on_line(line)
        return adapters.RunOutcome(code, "\n".join(lines) + "\n")
    return handler


def compile_ok(runner):
    runner.on_tool("tools/compile-tests.sh", ok_lines([]))


def list_ok(runner, node_ids):
    runner.add(lambda argv: len(argv) > 1
               and argv[1] == "tools/run-tests.sh" and "list" in argv,
               ok_lines(node_ids))


def junit_case_name(sid, index=None):
    index = index or C.UNIT_SCENARIO_INDEX
    signature = index.get(sid)
    if signature and "#" in signature["full_name"]:
        mod, _, func = signature["full_name"].partition("#")
        return f"{func}[{sid}]", mod
    return sid, ""


def junit_xml(path, counts, names=None, classnames=None):
    names_iter = iter(names or [])
    classes_iter = iter(classnames or [])
    suite = ET.Element("testsuite")

    def add_case(default_name, tag=None):
        attrs = {"name": next(names_iter, default_name)}
        cls = next(classes_iter, None)
        if cls:
            attrs["classname"] = cls
        case = ET.SubElement(suite, "testcase", attrs)
        if tag:
            ET.SubElement(case, tag)

    for _ in range(counts.get("passed", 0)):
        add_case("p")
    for _ in range(counts.get("failed", 0)):
        add_case("f", "failure")
    for _ in range(counts.get("errors", 0)):
        add_case("e", "error")
    for _ in range(counts.get("skipped", 0)):
        add_case("s", "skipped")
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


def scenario_names(count, sids=None):
    """count имён кейсов JUnit с параметризованным scenario ID."""
    if sids is None:
        sids = (list(C.BASE_SCENARIO_IDS)
                if count == len(C.BASE_SCENARIO_IDS)
                else list(C.SCENARIO_IDS))
    else:
        sids = list(sids)
    out = []
    for i in range(count):
        sid = sids[i % len(sids)] + (f"#{i}" if i >= len(sids) else "")
        case_name, _ = junit_case_name(sid)
        out.append(case_name)
    return out


def write_raw_allure_results(results_dir, scenario_outcomes, *,
                             bindings=None, index=None, titles=None):
    """Записать raw Allure *-result.json с русскими titles без scenario ID."""
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    index = index or C.UNIT_SCENARIO_INDEX
    titles = titles or C.UNIT_DISPLAY_TITLES
    for idx, (sid, status) in enumerate(scenario_outcomes.items()):
        sig = index[sid]
        seed = f"{results_dir.name}:{idx}:{sid}".encode("utf-8")
        uuid = hashlib.sha256(seed).hexdigest()[:32]
        labels = []
        if bindings and sid in bindings and bindings[sid] is not None:
            labels.append({"name": tresults.ALLURE_ID_LABEL,
                           "value": str(bindings[sid])})
        payload = {
            "uuid": uuid,
            "name": titles.get(sid, "Тестовый сценарий"),
            "fullName": sig["full_name"],
            "status": status,
            "parameters": [{"name": sig["param"],
                            "value": repr(sig["value"])}],
            "labels": labels,
        }
        file_id = hashlib.sha256(f"file:{uuid}".encode("utf-8")).hexdigest()[
            :12]
        (results_dir / f"{file_id}-result.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_manifest(root, run_id, counts, exit_code, *,
                   targets=("tests/api",), declared=None,
                   status="completed", names=None,
                   source_files="default", container_check=None,
                   tests_commit=None, tests_dirty=False,
                   contract_version=harness_mod.API_CONTRACT_VERSION,
                   rechecked_at="2026-01-01T00:00:10+00:00",
                   changed_during_run=(), missing=(),
                   allure_results="default", allure_bindings="default"):
    evidence = Path(root) / "artifacts" / "harness" / run_id
    evidence.mkdir(parents=True, exist_ok=True)
    total = sum(counts.get(key, 0)
                for key in ("passed", "failed", "errors", "skipped"))
    is_head_shape = (
        bool((declared or {}).get("app_patch_sha256"))
        or (counts.get("passed", 0) == len(C.SCENARIO_IDS)
            and total == len(C.SCENARIO_IDS))
    )
    is_base_shape = (
        not (declared or {}).get("app_patch_sha256")
        and counts.get("failed", 0) == len(C.BASE_SCENARIO_IDS)
        and total == len(C.BASE_SCENARIO_IDS)
    )
    default_sids = (
        list(C.SCENARIO_IDS) if is_head_shape
        else list(C.BASE_SCENARIO_IDS) if is_base_shape
        else None
    )
    if names is not None:
        junit_names = list(names)
        junit_classes = None
    elif default_sids is not None:
        pairs = [junit_case_name(sid) for sid in default_sids]
        junit_names = [pair[0] for pair in pairs]
        junit_classes = [pair[1] for pair in pairs]
    else:
        junit_names = scenario_names(total)
        junit_classes = None
    junit_xml(evidence / "junit.xml", counts, names=junit_names,
              classnames=junit_classes)

    source_identity = None
    sources_rel = None
    if source_files == "default":
        source_files = default_source_files()
    if source_files is not None:
        files = []
        copies = []
        for relpath in source_files:
            source = Path(root) / relpath
            dest = evidence / "sources" / relpath
            dest.parent.mkdir(parents=True, exist_ok=True)
            if source.is_file():
                dest.write_bytes(source.read_bytes())
                files.append({"path": relpath,
                              "sha256": sha256_file(source)})
                copies.append(relpath)
        source_identity = {
            "contract_version": contract_version,
            "captured_at": "2026-01-01T00:00:00+00:00",
            "files": files,
            "missing": list(missing) if missing is not None else None,
            "changed_during_run": (list(changed_during_run)
                                   if changed_during_run is not None
                                   else None),
            "rechecked_at": rechecked_at,
            "copies": copies,
        }
        sources_rel = "sources"

    manifest = {
        "schema_version": 2, "run_id": run_id,
        "started_at": "2026-01-01T00:00:00+00:00",
        "finished_at": "2026-01-01T00:00:10+00:00",
        "status": status,
        "repository": {"commit": tests_commit or C.TESTS_COMMIT,
                       "dirty": bool(tests_dirty)},
        "selection": {"scope": "group", "targets": list(targets),
                      "parameter_ids_omitted": False,
                      "browser": None, "browser_version": None},
        "environment": ({"declared": dict(declared),
                         "container_check": dict(
                             container_check or {"performed": False})}
                        if declared else None),
        "source_identity": source_identity,
        "exit_code": exit_code,
        "artifacts": {"allure_results": "allure-results",
                      "junit": "junit.xml", "sources": sources_rel},
        "junit_summary": dict(counts),
    }
    (evidence / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    allure_dir = evidence / "allure-results"
    allure_dir.mkdir(exist_ok=True)
    if (allure_results == "default" and names is None
            and default_sids is not None):
        expected_status = "passed" if is_head_shape else "failed"
        outcomes = {sid: expected_status for sid in default_sids}
        if allure_bindings == "default":
            bindings = dict(C.BINDINGS) if is_head_shape else None
        else:
            bindings = allure_bindings
        write_raw_allure_results(allure_dir, outcomes, bindings=bindings)
    elif isinstance(allure_results, dict):
        bindings = (dict(C.BINDINGS) if allure_bindings == "default"
                    else allure_bindings)
        write_raw_allure_results(allure_dir, allure_results,
                                 bindings=bindings)
    return evidence


def write_allure_result(root, run_id, name, *, uuid=None, full_name=None,
                        parameters=None, status="passed", labels=None):
    """Записать один *-result.json для негативных или адресных проверок."""
    results = Path(root) / "artifacts" / "harness" / run_id / "allure-results"
    results.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(
        f"{name}:{uuid}:{full_name}".encode("utf-8")).hexdigest()[:12]
    path = results / f"{digest}-result.json"
    payload = {"name": name, "status": status}
    if uuid is not None:
        payload["uuid"] = uuid
    if full_name is not None:
        payload["fullName"] = full_name
    if parameters is not None:
        payload["parameters"] = parameters
    if labels is not None:
        payload["labels"] = labels
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def harness_run_handler(root, run_id, counts, exit_code, *,
                        targets=("tests/api",), declared=None, **kw):
    """Fake delegated run: evidence first, then the pytest exit code."""
    def handler(argv, on_line):
        evidence = write_manifest(root, run_id, counts, exit_code,
                                  targets=targets, declared=declared, **kw)
        if on_line:
            on_line(f"Run evidence: {evidence}")
        return adapters.RunOutcome(exit_code)
    return handler


def harness_run(runner, root, run_id, counts, exit_code, **kw):
    runner.add(lambda argv: len(argv) > 1
               and argv[1] == "tools/run-tests.sh" and "group" in argv,
               harness_run_handler(root, run_id, counts, exit_code, **kw))


def on_testops(runner, action, handler):
    runner.add(lambda argv: len(argv) > 1
               and argv[1] == "tools/run-testops.sh" and action in argv,
               handler)


def set_upload_status(root, execution_id, status, launch_id=None):
    """Эмулирует эффект делегированного TestOps CLI в execution state."""
    state_dir = Path(root) / "artifacts" / "testops" / execution_id
    state = tstate.load_state(state_dir)
    if launch_id is not None and state.get("launch") is None:
        tstate.record_launch(state, launch_id, "unit launch",
                             f"{C.TESTOPS_ENDPOINT}/launch/{launch_id}")
    state["upload"]["status"] = status
    tstate.save_state(state_dir, state)


def make_testops_state(root, execution_id, *, upload_status="pending",
                       with_package=True, launch_id=None, results_dir=None,
                       mapping=None, index=None):
    """Execution state.json с реальными digest из build_package_verified."""
    root = Path(root)
    state_dir = root / "artifacts" / "testops" / execution_id
    package_dir = state_dir / C.PACKAGE_DIR_NAME
    state = tstate.new_state(execution_id, C.TESTOPS_ENDPOINT,
                             C.TESTOPS_PROJECT_ID)
    index = index or C.UNIT_SCENARIO_INDEX
    mapping = dict(C.BINDINGS if mapping is None else mapping)
    if results_dir is None:
        candidate = root / "artifacts" / "harness" / execution_id / \
            "allure-results"
        if candidate.is_dir():
            results_dir = candidate
    if results_dir is not None:
        results_dir = Path(results_dir)
        results_dir.mkdir(parents=True, exist_ok=True)
        if not list(results_dir.glob("*-result.json")):
            write_raw_allure_results(
                results_dir, {sid: "passed" for sid in C.SCENARIO_IDS},
                bindings=mapping, index=index)
        loaded = tresults.load_results(results_dir)
        mapped, unmapped = tresults.map_scenarios(loaded, index)
        files = [item for item in results_dir.iterdir() if item.is_file()]
        tstate.record_results(state, results_dir,
                              tresults.results_digest(results_dir),
                              len(files), mapped, unmapped)
        for sid in mapped:
            if sid in mapping:
                tstate.set_binding(state, sid, int(mapping[sid]), "assign")
        if with_package:
            assignments = {
                entry["uuid"]: (sid, entry.get("testops_id"))
                for sid, entry in state["scenarios"].items()
            }
            sub_index = {sid: index[sid] for sid in state["scenarios"]}
            info = tresults.build_package_verified(
                results_dir, package_dir,
                expected_digest=state["results"]["sha256"],
                assignments=assignments, index=sub_index)
            tstate.record_package(state, package_dir, info, "bind")
    elif with_package:
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / "one-result.json").write_text("{}", encoding="utf-8")
        state["package"] = {
            "dir": str(package_dir),
            "sha256": tresults.results_digest(package_dir), "files": 1,
            "results": 1, "mode": "bind",
            "built_at": "2026-01-01T00:00:00+00:00",
            "input_sha256": "e" * 64,
            "assignments_sha256": "a" * 64}
    if launch_id is not None:
        tstate.record_launch(state, launch_id, "unit launch",
                             f"{C.TESTOPS_ENDPOINT}/launch/{launch_id}")
    state["upload"]["status"] = upload_status
    if upload_status in ("sent", "uploaded", "in_progress", "unknown"):
        state["upload"]["attempts"] = max(
            state["upload"].get("attempts") or 0, 1)
        if state.get("package"):
            state["upload"]["package_sha256"] = state["package"]["sha256"]
    tstate.save_state(state_dir, state)
    return state_dir


def testops_local_handlers(runner, root, execution_id, results_dir,
                           mapping, *, launch_id=91, index=None):
    """Fake run-testops.sh plan/assign/package/upload/verify с реальными SHA."""
    state_dir = Path(root) / "artifacts" / "testops" / execution_id
    index = index or C.UNIT_SCENARIO_INDEX

    def ensure_state():
        path = state_dir / "state.json"
        if not path.is_file():
            state_dir.mkdir(parents=True, exist_ok=True)
            tstate.save_state(
                state_dir,
                tstate.new_state(execution_id, C.TESTOPS_ENDPOINT,
                                 C.TESTOPS_PROJECT_ID))
        return tstate.load_state(state_dir)

    def plan(argv, line):
        state = ensure_state()
        results_path = Path(results_dir)
        loaded = tresults.load_results(results_path)
        mapped, unmapped = tresults.map_scenarios(loaded, index)
        files = [item for item in results_path.iterdir() if item.is_file()]
        tstate.record_results(state, results_path,
                              tresults.results_digest(results_path),
                              len(files), mapped, unmapped)
        tstate.save_state(state_dir, state)
        return adapters.RunOutcome(0)

    def assign(argv, line):
        state = ensure_state()
        for pair in argv:
            sid, sep, raw = pair.partition("=")
            if sep and raw.isdigit() and sid in (state.get("scenarios") or {}):
                tstate.set_binding(state, sid, int(raw), "assign")
        tstate.save_state(state_dir, state)
        return adapters.RunOutcome(0)

    def package(argv, line):
        state = ensure_state()
        package_dir = state_dir / C.PACKAGE_DIR_NAME
        results_path = Path((state.get("results") or {}).get("path")
                            or results_dir)
        assignments = {
            entry["uuid"]: (sid, entry.get("testops_id"))
            for sid, entry in (state.get("scenarios") or {}).items()
        }
        sub_index = {sid: index[sid]
                     for sid in (state.get("scenarios") or {})}
        info = tresults.build_package_verified(
            results_path, package_dir,
            expected_digest=state["results"]["sha256"],
            assignments=assignments, index=sub_index)
        tstate.record_package(state, package_dir, info, "bind")
        tstate.save_state(state_dir, state)
        return adapters.RunOutcome(0)

    def upload(argv, line):
        state = ensure_state()
        tstate.begin_upload_attempt(
            state, (state.get("package") or {}).get("sha256"))
        tstate.record_launch(
            state, launch_id, "unit launch",
            f"{C.TESTOPS_ENDPOINT}/launch/{launch_id}")
        tstate.complete_attempt(state, "sent", 0, detail="fake delivered")
        tstate.save_state(state_dir, state)
        return adapters.RunOutcome(0)

    def verify(argv, line):
        state = ensure_state()
        if (state.get("upload") or {}).get("status") == "sent":
            tstate.mark_upload_confirmed(
                state, "fake-rest", detail="fake launch stats matched")
            tstate.save_state(state_dir, state)
            return adapters.RunOutcome(0)
        return adapters.RunOutcome(69)

    on_testops(runner, "plan", plan)
    on_testops(runner, "assign", assign)
    on_testops(runner, "package", package)
    on_testops(runner, "upload", upload)
    on_testops(runner, "verify", verify)


def testops_state_sha(root, execution_id):
    path = Path(root) / "artifacts" / "testops" / execution_id / "state.json"
    return sha256_file(path) if path.is_file() else None


class FakeGit(adapters.GitReadAdapter):
    """Deterministic HEAD/dirty и замороженные деревья коммитов без .git."""

    def __init__(self, repo_path, head=None, dirty=False, *,
                 commits=None, objects=None):
        super().__init__(repo_path)
        self.head = head
        self.dirty = dirty
        self.commits = {}
        for sha, tree in (commits or {}).items():
            self.register_commit(sha, tree)
        self.objects = {sha.lower(): kind
                        for sha, kind in (objects or {}).items()}

    def register_commit(self, sha, tree):
        normalized = {}
        for relpath, content in (tree or {}).items():
            normalized[relpath] = (content.encode("utf-8")
                                   if isinstance(content, str)
                                   else bytes(content))
        self.commits[sha.lower()] = normalized

    def head_commit(self):
        return self.head

    def is_dirty(self):
        return self.dirty

    def object_type(self, rev):
        if not isinstance(rev, str):
            return None
        key = rev.lower()
        if key in self.commits:
            return "commit"
        return self.objects.get(key)

    def commit_file_bytes(self, commit_sha, relpath):
        if (not isinstance(commit_sha, str)
                or not isinstance(relpath, str) or not relpath
                or Path(relpath).is_absolute()
                or ".." in Path(relpath).parts):
            return None
        tree = self.commits.get(commit_sha.lower())
        if tree is None:
            return None
        return tree.get(relpath)

    def changed_files(self, base_sha, head_sha):
        if not isinstance(base_sha, str) or not isinstance(head_sha, str):
            return None
        base_tree = self.commits.get(base_sha.lower())
        head_tree = self.commits.get(head_sha.lower())
        if base_tree is None or head_tree is None:
            return None
        all_paths = set(base_tree) | set(head_tree)
        return sorted(path for path in all_paths
                      if base_tree.get(path) != head_tree.get(path))


class Project:
    """Минимальный QA-проект и app-checkout в tmp dir для offline-прогона."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        for relpath in default_source_files():
            if relpath == C.TEST_FILES[0]:
                write_doc(self.root, relpath, C.TEST_FILE_CONTENT)
            else:
                write_doc(self.root, relpath, f"# contract source {relpath}\n")
        self.requirements = write_doc(self.root, C.REQUIREMENTS_REL,
                                      C.REQUIREMENTS_TEXT)
        self.context_doc = write_doc(self.root, "docs/context.json",
                                     '{"schema_version":1}\n')
        self.scenarios_doc = write_doc(self.root, "docs/scenarios.md",
                                       "# scenarios\n")
        self.review_doc = write_doc(self.root, "docs/review.md",
                                    "# review\n")
        self.impl_doc = write_doc(self.root, "docs/impl.md", "# impl\n")
        self.bindings_doc = write_doc(self.root, "docs/bindings.md",
                                      "# bindings\n")

        self.app_repo = self.root / "app"
        self.app_repo.mkdir(exist_ok=True)
        base_app_tree = {}
        for relpath in C.CONTEXT_SOURCE_PATHS:
            (self.app_repo / relpath).parent.mkdir(parents=True,
                                                   exist_ok=True)
            base_text = f"// base {relpath}\n"
            base_app_tree[relpath] = base_text.encode("utf-8")
            work_text = (f"// @Valid fix {relpath}\n"
                         if relpath == C.CHANGED_APP_FILE else base_text)
            (self.app_repo / relpath).write_text(work_text, encoding="utf-8")

        wrong_app_tree = dict(base_app_tree)
        wrong_app_tree[C.CHANGED_APP_FILE] = b"// unrelated wrong commit\n"
        self.git = FakeGit(
            self.app_repo, head=C.APP_BASE_SHA, dirty=True,
            commits={C.APP_BASE_SHA: base_app_tree,
                     C.WRONG_TREE_COMMIT_SHA: wrong_app_tree},
            objects={C.NON_COMMIT_OBJECT_SHA: "blob"})
        self.tests_git = FakeGit(
            self.root, head=C.TESTS_COMMIT, dirty=False,
            commits={C.TESTS_COMMIT: snapshot_tree(self.root)},
            objects={C.NON_COMMIT_OBJECT_SHA: "blob"})
        self.scenario_contract = unit_scenario_contract()
        self.store_dir = self.root / "artifacts" / "workflow"
        self.runner = FakeRunner()

    def commit_app_head(self, commit_sha=C.APP_HEAD_COMMIT_SHA):
        """Зафиксировать текущее дерево app в FakeGit как immutable commit."""
        self.git.register_commit(commit_sha, snapshot_tree(self.app_repo))
        self.git.head = commit_sha.lower()
        self.git.dirty = False
        return commit_sha.lower()

    def sync_tests_commit(self, commit_sha=C.TESTS_COMMIT):
        """Обновить снимок коммита tests_git текущим деревом self.root."""
        self.tests_git.register_commit(commit_sha, snapshot_tree(self.root))
        self.tests_git.head = commit_sha.lower()
        self.tests_git.dirty = False
        return commit_sha.lower()

    def context_sources(self):
        return [{"path": relpath,
                 "sha256": self.git.file_sha256(relpath),
                 "git_blob": self.git.git_blob(relpath)}
                for relpath in C.CONTEXT_SOURCE_PATHS]

    def envelope(self, kind, payload, *, document=None, actor="human",
                 version="1", name=None):
        doc_key = {"context": "context_doc", "scenarios": "scenarios_doc",
                   "review": "review_doc", "implementation": "impl_doc",
                   "bindings": "bindings_doc"}[kind]
        data = {"envelope_version": 1, "artifact": kind, "actor": actor,
                "version": version,
                "document": document if document is not None
                else getattr(self, doc_key),
                "payload": payload}
        path = self.root / "envelopes" / (name or f"{kind}.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def context_envelope(self, **kw):
        return self.envelope("context",
                             {"sources": self.context_sources()}, **kw)

    def scenarios_envelope(self, **kw):
        return self.envelope(
            "scenarios",
            {"scenario_ids": list(C.SCENARIO_IDS),
             "requirement_coverage": dict(C.SCENARIO_COVERAGE)}, **kw)

    def review_envelope(self, decision="approved", scenarios_sha=None, **kw):
        if scenarios_sha is None:
            scenarios_sha = self.scenarios_digest()
        return self.envelope(
            "review", {"decision": decision,
                       "scenarios_sha256": scenarios_sha}, **kw)

    def impl_envelope(self, **kw):
        return self.envelope("implementation",
                             {"test_files": list(C.TEST_FILES)}, **kw)

    def bindings_envelope(self, **kw):
        return self.envelope(
            "bindings",
            {"mapping": dict(C.BINDINGS), "source": "assign"}, **kw)

    def scenarios_digest(self):
        payload = {"scenario_ids": list(C.SCENARIO_IDS),
                   "requirement_coverage": dict(C.SCENARIO_COVERAGE)}
        from infrastructure.workflow import envelopes as env_mod
        return env_mod.artifact_digest(
            "scenarios", self.scenarios_doc["sha256"], payload)

    def orchestrator(self, **kw):
        from infrastructure.workflow.orchestrator import Orchestrator
        kw.setdefault("runner", self.runner)
        kw.setdefault("git_adapter", self.git)
        kw.setdefault("tests_git_adapter", self.tests_git)
        kw.setdefault("scenario_contract", self.scenario_contract)
        return Orchestrator(self.root, store_dir=self.store_dir, **kw)

    def init(self, orchestrator=None, **overrides):
        orchestrator = orchestrator or self.orchestrator()
        args = dict(pilot_id=C.PILOT_ID, app_repo=C.APP_REPO,
                    app_base_sha=C.APP_BASE_SHA, app_head_kind="patch",
                    app_head_sha256=C.APP_PATCH_SHA256,
                    tests_commit=C.TESTS_COMMIT, tests_dirty=False,
                    requirements_path=C.REQUIREMENTS_REL,
                    requirement_ids=C.REQUIREMENT_IDS,
                    app_repo_path=str(self.app_repo),
                    expected_executions=C.EXPECTED_EXECUTIONS,
                    strength_evidence=C.STRENGTH_EVIDENCE)
        args.update(overrides)
        return orchestrator.init(**args)

    def node_ids(self):
        return [C.NODE_ID.format(sid=sid) for sid in C.SCENARIO_IDS]

    def prepare_harness(self):
        compile_ok(self.runner)
        list_ok(self.runner, self.node_ids())

    def drive_to_implementation_ready(self, orchestrator=None,
                                      **init_overrides):
        orchestrator = orchestrator or self.orchestrator()
        self.prepare_harness()
        self.init(orchestrator, **init_overrides)
        orchestrator.accept("context", self.context_envelope())
        orchestrator.accept("scenarios", self.scenarios_envelope())
        orchestrator.accept("review", self.review_envelope())
        orchestrator.accept("implementation", self.impl_envelope())
        return orchestrator

    def workflow_state(self):
        from infrastructure.workflow import state as state_mod
        state_dir = next(
            path for path in self.store_dir.iterdir()
            if path.is_dir()
            and state_mod.WORKFLOW_ID_RE.fullmatch(path.name))
        return state_mod.load_state(state_dir)

    def drive_to_executed(self, orchestrator=None):
        """implementation_ready + bindings + patch head-run и базовый."""
        orchestrator = self.drive_to_implementation_ready(orchestrator)
        orchestrator.accept("bindings", self.bindings_envelope())
        harness_run(self.runner, self.root, C.EXECUTION_HEAD,
                    C.HEAD_JUNIT, 0,
                    declared={"app_base_sha": C.APP_BASE_SHA,
                              "app_patch_sha256": C.APP_PATCH_SHA256})
        orchestrator.run_execution("head")
        write_manifest(self.root, C.EXECUTION_BASE, C.BASE_JUNIT, 1,
                       declared={"app_base_sha": C.APP_BASE_SHA})
        orchestrator.import_execution(C.EXECUTION_BASE)
        return orchestrator

    def drive_commit_to_executed(self, orchestrator=None,
                                 commit_sha=C.APP_HEAD_COMMIT_SHA):
        """Commit-head + clean tests fixture до executed для PR-тестов."""
        commit_sha = self.commit_app_head(commit_sha)
        self.sync_tests_commit(C.TESTS_COMMIT)
        orchestrator = self.drive_to_implementation_ready(
            orchestrator, app_head_kind="commit",
            app_head_git_sha=commit_sha, app_head_sha256=None)
        orchestrator.accept("bindings", self.bindings_envelope())
        harness_run(self.runner, self.root, C.EXECUTION_HEAD,
                    C.HEAD_JUNIT, 0,
                    declared={"app_base_sha": commit_sha})
        orchestrator.run_execution("head")
        write_manifest(self.root, C.EXECUTION_BASE, C.BASE_JUNIT, 1,
                       declared={"app_base_sha": C.APP_BASE_SHA})
        orchestrator.import_execution(C.EXECUTION_BASE)
        return orchestrator

    def publish_handlers(self):
        """Fake TestOps CLI: upload помечает sent, verify — uploaded."""
        make_testops_state(self.root, C.EXECUTION_HEAD)
        on_testops(
            self.runner, "upload",
            lambda argv, line: (
                set_upload_status(self.root, C.EXECUTION_HEAD,
                                  "sent", launch_id=91),
                adapters.RunOutcome(0))[1])
        on_testops(
            self.runner, "verify",
            lambda argv, line: (
                set_upload_status(self.root, C.EXECUTION_HEAD,
                                  "uploaded"),
                adapters.RunOutcome(0))[1])

    def fake_pr_for(self, role):
        """FakePrTransport, отвечающий созданным PR на search/get."""
        ref_box = {}
        spec_holder = {}

        def create(spec):
            ref = adapters.PrRef(
                repo=spec["repo"], number=41 + len(ref_box),
                url="https://git.invalid/pr/x", title=spec["title"],
                head_branch=spec["head_branch"],
                base_branch=spec["base_branch"],
                head_sha=spec.get("head_sha"),
                body_sha256=spec.get("body_sha256"),
                files=list(spec.get("files") or []))
            ref_box[spec["repo"]] = ref
            spec_holder["spec"] = spec
            return ref
        transport = adapters.FakePrTransport(
            search_result=lambda key: list(ref_box.values()),
            create_result=create)

        def get(repo, number):
            transport.calls.append(("get", (repo, number)))
            ref = ref_box.get(repo)
            return ref if ref is not None and ref.number == number else None
        transport.get = get
        return transport
