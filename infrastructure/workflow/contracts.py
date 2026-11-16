"""Versioned source, scenario and historical-provenance contracts for 20R2.

Evidence is never accepted on counts or partial file lists alone:
- ``SourceContract`` enforces the exact versioned allowlist
  (``api-contract-v1`` + accepted implementation test files), path
  uniqueness, live or provenance-verified digests, 1:1 ``sources/`` copies
  and a completed post-run recheck;
- ``ScenarioContract`` enforces exact scenario sets, JUnit/raw Allure
  bijection, UUIDs, per-variant statuses (head all-pass vs red baseline
  negative subset) and ``ALLURE_ID`` bindings via the strict TestOps
  ``results.py`` helpers (``fullName`` + ``parameters``, never display
  titles);
- ``HistoricalBaselineAcceptance`` allows importing a pre-change red
  baseline only when bound to an authoritative versioned acceptance record
  referencing concrete review decisions, exact evidence digests and a
  bounded file-equivalence scope whose current digests still match the
  checkout. Head executions never accept provenance waivers.
"""
from dataclasses import dataclass, field
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from infrastructure.reporting.testops import results as tresults
from test_data.consts import category_update as cat_consts
from tools import harness as harness_mod

from . import state as state_mod

PILOT_SCENARIO_CONTRACT_VERSION = "cat-upd-val-scenarios-v1"
HISTORICAL_PROVENANCE_SCHEMA_VERSION = 1
HISTORICAL_PROVENANCE_KIND = "historical_baseline_acceptance"

# Authoritative historical baseline acceptances documented by coordinator
# review waves. Never invent entries here: every digest is recorded in
# coordination-wave-5.md (baseline run-vzsatlfk) and coordination-wave-14.md
# (17A runtime ALLURE_ID markup equivalence).
DEFAULT_ACCEPTED_HISTORICAL_BASELINES = (
    {
        "schema_version": HISTORICAL_PROVENANCE_SCHEMA_VERSION,
        "kind": HISTORICAL_PROVENANCE_KIND,
        "pilot_id": "category-update-validation",
        "execution_id": "run-vzsatlfk",
        "variant": "base",
        "app_base_sha": "36674280b6878540a9e88f40aaeedf5dfdd2e6ce",
        "manifest_sha256":
            "a8454b11881fc95bc3e1753535ca759fbbbc53d362f955395489106c0cc86718",
        "junit_sha256":
            "bcb47c56ec4a449f13097e7d078e8b97bc7074d139a91326e546d31a3eeb156c",
        "allure_results_sha256":
            "93129e3bc7a8f35a599708d13c0fa37c1c95b8ef7e5bd0b6563b83af86acbdc5",
        "contract_version": harness_mod.API_CONTRACT_VERSION,
        "tests_repo": {
            "commit": "c84483bf6647678d4052eb377e04a682cdaddd74",
            "dirty": True,
        },
        "review_decisions": [
            {
                "path": "docs/qa-workflow/handoffs/coordination-wave-5.md",
                "sha256": ("d48d57cdd81b5b03c74ad26f9ee728e307ac21d2"
                           "0a45aa139675c0a98b076347"),
            },
            {
                "path": "docs/qa-workflow/handoffs/coordination-wave-14.md",
                "sha256": ("535a8e12ace7bd7e5f28931cbfaac2e602337ffc"
                           "64290105d0197eb1da2d2dbd"),
            },
        ],
        "equivalence_scope": {
            "allowed_changed_files": {
                "test_data/consts/category_update.py": {
                    "historical_sha256": ("dc8b900d34b7401a2bcd5542968dfc15"
                                          "184d20abb2c274905448aa910f96b902"),
                    "current_sha256": ("c66a9a9f94e6a53286e5310521211121"
                                       "7e2113de51f78690790cb664c83d3933"),
                    "reason": ("17A added TESTOPS_ALLURE_IDS constants "
                               "accepted in coordination-wave-14"),
                },
                "tests/api/test_category_update.py": {
                    "historical_sha256": ("455ee7506897f6c7b69b8f6e5d54d8d3"
                                          "bd5ea1b48e478eb39793c71e50dbbd3c"),
                    "current_sha256": ("ebd9deaa18398c306cac5f9ecacc4c55"
                                       "4423477c8e38889fd41847878fa7e359"),
                    "reason": ("17A added runtime ALLURE_ID step accepted "
                               "in coordination-wave-14"),
                },
            },
        },
    },
)


@dataclass(frozen=True)
class SourceContract:
    """Versioned source allowlist required in every API run manifest."""
    contract_version: str = harness_mod.API_CONTRACT_VERSION
    required_files: tuple = harness_mod.API_SOURCE_FILES


@dataclass(frozen=True)
class ScenarioContract:
    """Exact scenario signature, variant subset and binding contract."""
    contract_version: str
    index: dict
    head_scenarios: tuple
    base_scenarios: tuple
    expected_bindings: dict = field(default_factory=dict)


def pilot_source_contract():
    return SourceContract()


def pilot_scenario_contract():
    """Live CAT-UPD-VAL scenario contract backed by category_update consts."""
    index = {}
    module = "tests.api.test_category_update"
    for scenario_id, value in zip(cat_consts.INVALID_IDS,
                                  cat_consts.INVALID_NAMES):
        index[scenario_id] = {
            "full_name": f"{module}#test_update_category_rejects_invalid_name",
            "param": "name",
            "value": value,
        }
    for scenario_id, value in zip(cat_consts.VALID_IDS,
                                  cat_consts.VALID_NAMES):
        index[scenario_id] = {
            "full_name": (f"{module}#"
                          "test_update_category_accepts_name_at_length_boundary"),
            "param": "name",
            "value": value,
        }
    bindings = {sid: int(tid)
                for sid, tid in cat_consts.TESTOPS_ALLURE_IDS.items()}
    return ScenarioContract(
        contract_version=PILOT_SCENARIO_CONTRACT_VERSION,
        index=index,
        head_scenarios=tuple([*cat_consts.INVALID_IDS, *cat_consts.VALID_IDS]),
        base_scenarios=tuple(cat_consts.INVALID_IDS),
        expected_bindings=bindings,
    )


def required_source_paths(source_contract, state):
    paths = set(source_contract.required_files)
    impl = ((state.get("artifacts") or {}).get("implementation") or {})
    if impl.get("status") == "accepted":
        paths.update((impl.get("payload") or {}).get("test_files") or ())
    return paths


def validate_source_identity(source_contract, state, manifest, evidence_dir,
                             tests_git, tests_root, *,
                             allowed_historical_files=None):
    """Enforce the full versioned source allowlist, copies and recheck."""
    problems = []
    evidence_dir = Path(evidence_dir)
    tests_root = Path(tests_root)
    source = manifest.get("source_identity")
    if not isinstance(source, dict):
        return ["manifest has no source_identity block"]
    if source.get("contract_version") != source_contract.contract_version:
        problems.append(
            f"source_identity.contract_version "
            f"{source.get('contract_version')!r} != "
            f"{source_contract.contract_version!r}")
    missing_field = source.get("missing")
    if not isinstance(missing_field, list) or missing_field:
        problems.append(
            f"source_identity.missing must be empty, got {missing_field!r}")
    changed_field = source.get("changed_during_run")
    if not isinstance(changed_field, list) or changed_field:
        problems.append(
            "source_identity.changed_during_run must be an empty list "
            f"(completed recheck), got {changed_field!r}")
    rechecked = source.get("rechecked_at")
    if not isinstance(rechecked, str) or not rechecked.strip():
        problems.append("source_identity.rechecked_at missing: post-run "
                        "source recheck did not complete")

    required_paths = required_source_paths(source_contract, state)
    files = source.get("files")
    if not isinstance(files, list) or not files:
        problems.append("source_identity.files must be a non-empty list")
        return problems

    seen_paths = []
    by_path = {}
    for entry in files:
        if not isinstance(entry, dict):
            problems.append("source_identity.files contains a non-object entry")
            continue
        relpath = entry.get("path")
        declared = entry.get("sha256")
        if (not isinstance(relpath, str) or not relpath
                or Path(relpath).is_absolute()
                or ".." in Path(relpath).parts):
            problems.append(
                f"source_identity entry has invalid path: {relpath!r}")
            continue
        if not (isinstance(declared, str)
                and state_mod.HEX64.fullmatch(declared)):
            problems.append(
                f"{relpath}: invalid or missing 64-hex sha256")
            continue
        if relpath in by_path:
            problems.append(f"{relpath}: duplicate entry in source_identity")
            continue
        seen_paths.append(relpath)
        by_path[relpath] = declared.lower()

    seen_set = set(seen_paths)
    missing_required = sorted(required_paths - seen_set)
    if missing_required:
        problems.append(
            "source_identity is missing required contract files: "
            f"{missing_required[:5]}")
    foreign_paths = sorted(seen_set - required_paths)
    if foreign_paths:
        problems.append(
            "source_identity contains paths outside the agreed contract: "
            f"{foreign_paths[:5]}")

    artifacts = manifest.get("artifacts") or {}
    sources_rel = artifacts.get("sources")
    copies = source.get("copies")
    copies_root = None
    if not isinstance(sources_rel, str) or not sources_rel:
        problems.append("manifest.artifacts.sources directory not declared")
    else:
        resolved_copies = (evidence_dir / sources_rel).resolve()
        if not resolved_copies.is_relative_to(evidence_dir.resolve()):
            problems.append("manifest.artifacts.sources escapes evidence_dir")
        elif not resolved_copies.is_dir():
            problems.append(
                f"evidence sources directory missing: {sources_rel}")
        else:
            copies_root = resolved_copies

    if not isinstance(copies, list):
        problems.append("source_identity.copies must be a list")
    else:
        if len(copies) != len(set(copies)):
            problems.append("source_identity.copies contains duplicate paths")
        copy_set = set(copies)
        if copy_set != required_paths:
            diff_missing = sorted(required_paths - copy_set)
            diff_extra = sorted(copy_set - required_paths)
            if diff_missing:
                problems.append(
                    f"source_identity.copies missing required files: "
                    f"{diff_missing[:5]}")
            if diff_extra:
                problems.append(
                    f"source_identity.copies has unexpected files: "
                    f"{diff_extra[:5]}")

    allowed_historical_files = allowed_historical_files or {}
    for relpath, declared in sorted(by_path.items()):
        live_sha = tests_git.file_sha256(relpath) if tests_git else None
        if live_sha is None and (tests_root / relpath).is_file():
            live_sha = state_mod.sha256_file(tests_root / relpath)
        if relpath in allowed_historical_files:
            rule = allowed_historical_files[relpath]
            if declared != rule["historical_sha256"].lower():
                problems.append(
                    f"{relpath}: manifest sha256 does not match accepted "
                    "historical digest")
            if live_sha is None:
                problems.append(f"{relpath}: missing in current checkout")
            elif live_sha.lower() != rule["current_sha256"].lower():
                problems.append(
                    f"{relpath}: current checkout sha256 drifted from "
                    "accepted equivalence target")
        else:
            if live_sha is None:
                problems.append(f"{relpath}: cannot re-verify source digest")
            elif live_sha.lower() != declared:
                problems.append(f"{relpath}: source digest mismatch")

        if copies_root is not None:
            copy_path = copies_root / relpath
            if not copy_path.is_file():
                problems.append(f"{relpath}: source copy missing")
            elif state_mod.sha256_file(copy_path) != declared:
                problems.append(f"{relpath}: source copy mismatch")

    if copies_root is not None:
        actual_copies = {
            item.relative_to(copies_root).as_posix()
            for item in copies_root.rglob("*") if item.is_file()
        }
        unrecorded = sorted(actual_copies - set(by_path))
        if unrecorded:
            problems.append(
                f"unrecorded files in evidence sources/: {unrecorded[:5]}")
    return problems


def _match_junit_scenario(case_name, classname, candidates, index):
    matches = []
    for sid in candidates:
        pattern = r"(?<![A-Za-z0-9_-])" + re.escape(sid) + r"(?![A-Za-z0-9_-])"
        if re.search(pattern, case_name):
            matches.append(sid)
    if len(matches) != 1:
        return None
    sid = matches[0]
    signature = index.get(sid) or {}
    full_name = signature.get("full_name") or ""
    if "#" in full_name and "[" in case_name:
        expected_mod, _, expected_func = full_name.partition("#")
        actual_func = case_name.split("[", 1)[0]
        if actual_func and actual_func != expected_func:
            return None
        if classname and classname != expected_mod:
            return None
    return sid


def _junit_cases(junit_path):
    try:
        root = ET.parse(junit_path).getroot()
    except (OSError, ET.ParseError) as error:
        return None, f"junit.xml unreadable or invalid XML: {error}"
    if root.tag.rsplit("}", 1)[-1] not in ("testsuite", "testsuites"):
        return None, f"unexpected junit root tag: {root.tag!r}"
    cases = []
    for case in root.iter():
        if case.tag.rsplit("}", 1)[-1] != "testcase":
            continue
        tags = {child.tag.rsplit("}", 1)[-1] for child in case}
        outcome = ("errors" if "error" in tags else "failed"
                   if "failure" in tags else "skipped"
                   if "skipped" in tags else "passed")
        cases.append((case.get("name") or "", case.get("classname") or "",
                      outcome))
    return cases, None


def expected_variant_outcomes(scenario_contract, variant, state):
    """Return ({scenario_id: expected_status}, problems) for head or base."""
    problems = []
    scenarios_art = (state.get("artifacts") or {}).get("scenarios") or {}
    scenario_ids = list(scenarios_art.get("scenario_ids") or [])
    if not scenario_ids:
        return {}, ["no accepted scenarios recorded in workflow state"]
    unknown = [sid for sid in scenario_ids
               if sid not in scenario_contract.index]
    if unknown:
        problems.append(
            f"accepted scenarios missing from scenario contract: {unknown}")
        return {}, problems

    revision_data = ((state.get("input") or {}).get("revision_data") or {})
    if variant == "head":
        if (scenario_contract.head_scenarios
                and set(scenario_ids) != set(scenario_contract.head_scenarios)):
            problems.append(
                "accepted scenarios do not match the head scenario contract: "
                f"got {sorted(scenario_ids)}, expected "
                f"{sorted(scenario_contract.head_scenarios)}")
        expected = {sid: "passed" for sid in scenario_ids}
        for req in revision_data.get("expected_executions") or []:
            if req.get("variant") == "head" and req.get("required"):
                exp = req.get("expect") or {}
                if (exp.get("total") is not None
                        and exp.get("total") != len(expected)):
                    problems.append(
                        f"expected_executions head total {exp.get('total')} "
                        f"!= accepted scenario count {len(expected)}")
                if (exp.get("passed") is not None
                        and exp.get("passed") != len(expected)):
                    problems.append(
                        f"expected_executions head passed {exp.get('passed')} "
                        f"!= accepted scenario count {len(expected)}")
        return expected, problems

    if variant == "base":
        base_ids = [sid for sid in scenario_ids
                    if sid in set(scenario_contract.base_scenarios)]
        if (not base_ids
                or set(base_ids) != set(scenario_contract.base_scenarios)):
            problems.append(
                "accepted scenarios do not cover the required baseline "
                f"scenario set {list(scenario_contract.base_scenarios)}")
            return {}, problems
        expected = {sid: "failed" for sid in base_ids}
        strength = revision_data.get("strength_evidence") or {}
        if strength.get("variant") == "base" and strength.get("required"):
            exp = strength.get("expect") or {}
            if (exp.get("total") is not None
                    and exp.get("total") != len(expected)):
                problems.append(
                    f"strength_evidence total {exp.get('total')} != "
                    f"baseline scenario count {len(expected)}")
            if (exp.get("failed") is not None
                    and exp.get("failed") != len(expected)):
                problems.append(
                    f"strength_evidence failed {exp.get('failed')} != "
                    f"baseline scenario count {len(expected)}")
        return expected, problems

    return {}, [f"unsupported execution variant for scenario contract: "
                f"{variant!r}"]


def _allure_id_labels(result_data):
    labels = []
    for entry in result_data.get("labels") or []:
        if (isinstance(entry, dict)
                and entry.get("name") in (tresults.ALLURE_ID_LABEL,
                                          tresults.LEGACY_ID_LABEL)):
            labels.append(entry.get("value"))
    return labels


def validate_scenario_composition(scenario_contract, variant, state, manifest,
                                  evidence_dir, *, testops_state=None):
    """Exact JUnit + raw Allure scenario bijection, statuses and bindings."""
    evidence_dir = Path(evidence_dir)
    expected_outcomes, problems = expected_variant_outcomes(
        scenario_contract, variant, state)
    if problems:
        return problems

    all_known_sids = list(scenario_contract.index.keys())
    junit_rel = ((manifest.get("artifacts") or {}).get("junit") or "junit.xml")
    junit_cases, junit_err = _junit_cases(evidence_dir / junit_rel)
    junit_by_sid = {}
    if junit_err:
        problems.append(junit_err)
    else:
        if len(junit_cases) != len(expected_outcomes):
            problems.append(
                f"junit testcase count {len(junit_cases)} != expected "
                f"{len(expected_outcomes)} for {variant}")
        foreign_junit, duplicate_junit = [], []
        for case_name, classname, outcome in junit_cases:
            sid = _match_junit_scenario(
                case_name, classname, all_known_sids, scenario_contract.index)
            if sid is None or sid not in expected_outcomes:
                foreign_junit.append(case_name or "<unnamed>")
                continue
            if sid in junit_by_sid:
                duplicate_junit.append(sid)
                continue
            junit_by_sid[sid] = outcome
        if foreign_junit:
            problems.append(
                "junit contains cases outside the expected scenario set: "
                f"{foreign_junit[:3]}")
        if duplicate_junit:
            problems.append(
                f"junit contains duplicate scenarios: "
                f"{sorted(set(duplicate_junit))}")
        missing_junit = sorted(set(expected_outcomes) - set(junit_by_sid))
        if missing_junit:
            problems.append(
                f"junit is missing expected scenarios: {missing_junit}")
        for sid, actual_status in sorted(junit_by_sid.items()):
            if actual_status != expected_outcomes[sid]:
                problems.append(
                    f"junit scenario {sid} status is {actual_status!r}, "
                    f"expected {expected_outcomes[sid]!r}")

    allure_rel = ((manifest.get("artifacts") or {}).get("allure_results")
                  or "allure-results")
    allure_dir = evidence_dir / allure_rel
    if not allure_dir.is_dir():
        problems.append(f"allure results directory missing: {allure_rel}")
        return problems

    try:
        scanned = tresults.load_results(allure_dir)
    except tresults.ResultsIntegrityError as error:
        problems.append(str(error))
        return problems
    if not scanned:
        problems.append("allure results directory contains no *-result.json")
        return problems
    try:
        tresults.validate_attachments(allure_dir, scanned)
    except tresults.ResultsIntegrityError as error:
        problems.append(str(error))
        return problems

    expected_index = {sid: scenario_contract.index[sid]
                      for sid in expected_outcomes}
    try:
        uuid_to_sid = tresults.scan_assignments(allure_dir, expected_index)
    except tresults.ResultsIntegrityError as error:
        problems.append(str(error))
        return problems

    missing_allure = sorted(set(expected_outcomes) - set(uuid_to_sid.values()))
    if missing_allure:
        problems.append(
            f"allure results missing expected scenarios: {missing_allure}")
    if len(scanned) != len(expected_outcomes):
        problems.append(
            f"allure result count {len(scanned)} != expected "
            f"{len(expected_outcomes)}")

    bindings_art = ((state.get("artifacts") or {}).get("bindings") or {})
    bindings_accepted = bindings_art.get("status") == "accepted"
    if bindings_accepted:
        bound_map = {sid: int(tid)
                     for sid, tid in (bindings_art.get("mapping") or {}).items()}
    else:
        bound_map = {sid: int(tid)
                     for sid, tid in
                     (scenario_contract.expected_bindings or {}).items()}

    allure_uuid_by_sid = {}
    for path, data in scanned:
        uuid = data["uuid"]
        sid = uuid_to_sid[uuid]
        allure_uuid_by_sid[sid] = uuid
        allure_status = data.get("status")
        if allure_status != expected_outcomes[sid]:
            problems.append(
                f"allure scenario {sid} ({path.name}) status is "
                f"{allure_status!r}, expected {expected_outcomes[sid]!r}")
        if sid in junit_by_sid and allure_status != junit_by_sid[sid]:
            problems.append(
                f"JUnit/Allure status mismatch for {sid}: "
                f"junit={junit_by_sid[sid]!r}, allure={allure_status!r}")

        id_labels = _allure_id_labels(data)
        if len(id_labels) > 1:
            problems.append(
                f"allure scenario {sid} ({path.name}) carries multiple "
                f"ALLURE_ID labels: {id_labels}")
        elif len(id_labels) == 1:
            raw_id = id_labels[0]
            if not (isinstance(raw_id, str) and raw_id.isdigit()
                    and int(raw_id) > 0):
                problems.append(
                    f"allure scenario {sid} ({path.name}) has invalid "
                    f"ALLURE_ID {raw_id!r}")
            elif sid in bound_map and int(raw_id) != bound_map[sid]:
                problems.append(
                    f"allure scenario {sid} ({path.name}) ALLURE_ID "
                    f"{int(raw_id)} != agreed binding {bound_map[sid]}")
        elif variant == "head" and bindings_accepted:
            problems.append(
                f"head allure scenario {sid} ({path.name}) is missing "
                "ALLURE_ID label for accepted bindings")

    if testops_state is not None:
        if testops_state.get("unmapped"):
            problems.append("TestOps execution state records unmapped results")
        recorded_scenarios = testops_state.get("scenarios") or {}
        if recorded_scenarios:
            if set(recorded_scenarios) != set(expected_outcomes):
                problems.append(
                    "TestOps execution state scenario set does not match "
                    "expected outcomes")
            for sid, rec in sorted(recorded_scenarios.items()):
                if sid not in allure_uuid_by_sid:
                    continue
                if rec.get("uuid") != allure_uuid_by_sid[sid]:
                    problems.append(
                        f"TestOps state uuid mismatch for {sid}")
                if rec.get("status") != expected_outcomes[sid]:
                    problems.append(
                        f"TestOps state status mismatch for {sid}: "
                        f"{rec.get('status')!r} != {expected_outcomes[sid]!r}")
                tid = rec.get("testops_id")
                if (tid is not None and sid in bound_map
                        and int(tid) != bound_map[sid]):
                    problems.append(
                        f"TestOps state binding for {sid} ({tid}) != "
                        f"agreed binding {bound_map[sid]}")
    return problems


def validate_historical_provenance_schema(record):
    """Strict structural check of a versioned baseline acceptance record."""
    if not isinstance(record, dict):
        return ["provenance must be a JSON object"]
    required_keys = {
        "schema_version", "kind", "pilot_id", "execution_id", "variant",
        "app_base_sha", "manifest_sha256", "junit_sha256",
        "allure_results_sha256", "contract_version", "tests_repo",
        "review_decisions", "equivalence_scope",
    }
    if "source_identity_missing" in record:
        return ["source_identity_missing waiver is forbidden in 20R2"]
    missing = sorted(required_keys - set(record))
    extra = sorted(set(record) - required_keys)
    if missing or extra:
        msgs = []
        if missing:
            msgs.append(f"provenance missing required keys: {missing}")
        if extra:
            msgs.append(f"provenance has unsupported keys: {extra}")
        return msgs
    problems = []
    if record.get("schema_version") != HISTORICAL_PROVENANCE_SCHEMA_VERSION:
        problems.append(
            f"unsupported provenance schema_version: "
            f"{record.get('schema_version')!r}")
    if record.get("kind") != HISTORICAL_PROVENANCE_KIND:
        problems.append(
            f"unsupported provenance kind: {record.get('kind')!r}")
    if record.get("variant") != "base":
        problems.append(
            "historical provenance is only valid for variant='base'")
    if not (isinstance(record.get("pilot_id"), str)
            and state_mod.PILOT_ID_RE.fullmatch(record["pilot_id"])):
        problems.append("provenance.pilot_id invalid")
    if not (isinstance(record.get("execution_id"), str)
            and state_mod.EXECUTION_ID_RE.fullmatch(record["execution_id"])):
        problems.append("provenance.execution_id invalid")
    if not (isinstance(record.get("app_base_sha"), str)
            and state_mod.HEX40_64.fullmatch(record["app_base_sha"])):
        problems.append("provenance.app_base_sha must be 40-64 hex")
    for field_name in ("manifest_sha256", "junit_sha256",
                       "allure_results_sha256"):
        val = record.get(field_name)
        if not (isinstance(val, str) and state_mod.HEX64.fullmatch(val)):
            problems.append(f"provenance.{field_name} must be 64-hex")
    if not isinstance(record.get("contract_version"), str) or not record[
            "contract_version"]:
        problems.append("provenance.contract_version must be non-empty")
    tests_repo = record.get("tests_repo")
    if (not isinstance(tests_repo, dict)
            or set(tests_repo) != {"commit", "dirty"}
            or not (isinstance(tests_repo.get("commit"), str)
                    and state_mod.HEX40_64.fullmatch(tests_repo["commit"]))
            or not isinstance(tests_repo.get("dirty"), bool)):
        problems.append(
            "provenance.tests_repo must be {commit: hex, dirty: bool}")
    decisions = record.get("review_decisions")
    if not isinstance(decisions, list) or not decisions:
        problems.append(
            "provenance.review_decisions must be a non-empty list")
    else:
        for item in decisions:
            if (not isinstance(item, dict)
                    or set(item) != {"path", "sha256"}
                    or not isinstance(item.get("path"), str)
                    or not item["path"]
                    or Path(item["path"]).is_absolute()
                    or ".." in Path(item["path"]).parts
                    or not (isinstance(item.get("sha256"), str)
                            and state_mod.HEX64.fullmatch(item["sha256"]))):
                problems.append(
                    "each review_decisions entry must have repo-relative "
                    "path and 64-hex sha256")
                break
    scope = record.get("equivalence_scope")
    if (not isinstance(scope, dict)
            or set(scope) != {"allowed_changed_files"}
            or not isinstance(scope.get("allowed_changed_files"), dict)
            or not scope["allowed_changed_files"]):
        problems.append(
            "provenance.equivalence_scope must define non-empty "
            "allowed_changed_files")
    else:
        for relpath, spec in scope["allowed_changed_files"].items():
            if (not isinstance(relpath, str) or not relpath
                    or Path(relpath).is_absolute()
                    or ".." in Path(relpath).parts
                    or not isinstance(spec, dict)
                    or set(spec) != {"historical_sha256", "current_sha256",
                                     "reason"}
                    or not (isinstance(spec.get("historical_sha256"), str)
                            and state_mod.HEX64.fullmatch(
                                spec["historical_sha256"]))
                    or not (isinstance(spec.get("current_sha256"), str)
                            and state_mod.HEX64.fullmatch(
                                spec["current_sha256"]))
                    or not isinstance(spec.get("reason"), str)
                    or not spec["reason"].strip()):
                problems.append(
                    f"invalid equivalence_scope rule for {relpath!r}")
                break
    return problems


def verify_historical_baseline_acceptance(
        record, *, accepted_records, source_contract, state, execution_id,
        variant, manifest, manifest_sha256, evidence_dir, root):
    """Verify that ``record`` is an accepted baseline record and matches disk."""
    if variant != "base":
        return None, [
            "historical provenance is forbidden for head executions; "
            "head evidence must match the live revision directly"
        ]
    schema_problems = validate_historical_provenance_schema(record)
    if schema_problems:
        return None, schema_problems

    identity = state["input"]["identity"]
    pilot_id = identity["pilot_id"]
    key = (pilot_id, execution_id)
    authoritative = None
    for candidate in accepted_records or ():
        if (candidate.get("pilot_id") == pilot_id
                and candidate.get("execution_id") == execution_id):
            authoritative = candidate
            break
    if authoritative is None:
        return None, [
            f"no coordinator-accepted historical baseline provenance record "
            f"exists for ({pilot_id!r}, {execution_id!r}); caller-supplied "
            "payloads cannot self-authorize rejected manifests"
        ]
    if (state_mod.canonical_digest(record)
            != state_mod.canonical_digest(authoritative)):
        return None, [
            f"provenance record for {execution_id} does not match the "
            "accepted coordinator baseline record (tampered or incomplete)"
        ]

    problems = []
    if record["app_base_sha"].lower() != identity["app_base_sha"].lower():
        problems.append(
            "provenance app_base_sha does not match workflow identity")
    if record["contract_version"] != source_contract.contract_version:
        problems.append(
            f"provenance contract_version {record['contract_version']!r} != "
            f"{source_contract.contract_version!r}")
    if record["manifest_sha256"].lower() != (manifest_sha256 or "").lower():
        problems.append("provenance manifest_sha256 does not match manifest")

    evidence_dir = Path(evidence_dir)
    junit_path = evidence_dir / (
        (manifest.get("artifacts") or {}).get("junit") or "junit.xml")
    if not junit_path.is_file():
        problems.append("junit.xml missing for historical baseline check")
    elif (state_mod.sha256_file(junit_path)
          != record["junit_sha256"].lower()):
        problems.append("provenance junit_sha256 does not match junit.xml")

    allure_dir = evidence_dir / (
        (manifest.get("artifacts") or {}).get("allure_results")
        or "allure-results")
    if not allure_dir.is_dir():
        problems.append("allure-results missing for historical baseline check")
    else:
        try:
            actual_allure_sha = tresults.results_digest(allure_dir)
        except OSError as error:
            problems.append(f"cannot hash allure-results: {error}")
            actual_allure_sha = None
        if (actual_allure_sha is not None
                and actual_allure_sha
                != record["allure_results_sha256"].lower()):
            problems.append(
                "provenance allure_results_sha256 does not match "
                "allure-results")

    root = Path(root).resolve()
    for decision in record["review_decisions"]:
        doc_path = (root / decision["path"]).resolve()
        if not doc_path.is_relative_to(root) or not doc_path.is_file():
            problems.append(
                f"referenced review decision missing: {decision['path']}")
        elif state_mod.sha256_file(doc_path) != decision["sha256"].lower():
            problems.append(
                f"referenced review decision digest drifted: "
                f"{decision['path']}")

    allowed_files = record["equivalence_scope"]["allowed_changed_files"]
    req_paths = required_source_paths(source_contract, state)
    outside = sorted(set(allowed_files) - req_paths)
    if outside:
        problems.append(
            f"provenance equivalence_scope references files outside the "
            f"source contract: {outside}")
    if problems:
        return None, problems
    return allowed_files, []
