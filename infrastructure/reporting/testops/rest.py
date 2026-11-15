"""Read-only REST probe for Allure TestOps launch snapshots.

`RestProbe.read_snapshot(endpoint, launch_id)` returns a plain dict with a
verified view of one launch: identity, processing flag, per-status counts
and the full allowlisted result set. `outcome` is one of:

- ``complete`` — every required response was read, schemas are valid and
  the paginated result walk provably covered the whole set. This does NOT
  mean the upload is confirmed: ``closed``/``ready`` may still be false
  and only the caller compares the snapshot with the expected execution.
- ``missing`` — the direct ``GET /api/launch/{id}`` returned HTTP 404.
- ``unreachable`` — authentication, network, HTTP or a non-launch endpoint
  failure prevented a reliable read.
- ``inconclusive`` — a response violated the confirmed OpenAPI schema, the
  page walk could not prove completeness, or launch metadata drifted
  during the read. Nothing is guessed.

Only allowlisted fields are kept. Test bodies, parameters, traces and
attachments are never retained; tokens and JWTs live only inside the
process, never in the returned dict, reasons, headers logs or files.
Persisting the snapshot as evidence is the caller's responsibility.

Contract sources (agent 14B): OpenAPI 3.1.0 of allure-testops-service
527u01 — ``GET /api/launch/{id}`` (LaunchDto: id, projectId, closed),
``GET /api/launch/{id}/progress`` ({ready}), ``GET /api/launch/{id}/statistic``
([{status, count}]) and ``GET /api/testresult?launchId=..`` (Spring Page of
TestResultDto). Only confirmed parameters are sent: launchId, page, size —
no invented ``sort``; the documented server default applies and ordering
instability is detected by the strict walk instead.

The module performs no I/O at import or construction; the HTTP layer is
injected and defaults to a bounded urllib client that refuses redirects.
"""
import json
from urllib.parse import urlencode

from infrastructure.http.client import HttpClient

OUTCOME_COMPLETE = "complete"
OUTCOME_MISSING = "missing"
OUTCOME_UNREACHABLE = "unreachable"
OUTCOME_INCONCLUSIVE = "inconclusive"

OUTCOMES = (OUTCOME_COMPLETE, OUTCOME_MISSING, OUTCOME_UNREACHABLE,
            OUTCOME_INCONCLUSIVE)

# TestStatus enum from OpenAPI 527u01; informational only — the probe keeps
# every observed status string verbatim (lowercased) and never filters.
KNOWN_STATUSES = ("failed", "broken", "passed", "skipped", "unknown",
                  "in_progress")

DEFAULT_TIMEOUT_S = 30
DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 100

_TOKEN_PATH = "/api/uaa/oauth/token"
_LAUNCH_PATH = "/api/launch/{id}"
_PROGRESS_PATH = "/api/launch/{id}/progress"
_STATISTIC_PATH = "/api/launch/{id}/statistic"
_RESULTS_PATH = "/api/testresult"


class _Fail(Exception):
    """Terminal read failure carrying the contract outcome and a safe reason.

    Reasons contain only the operation name and HTTP status — never
    payloads, headers, tokens or JWTs.
    """

    def __init__(self, outcome, reason):
        super().__init__(reason)
        self.outcome = outcome
        self.reason = reason


class UrllibHttp:
    """Default injected HTTP layer: one bounded HttpClient per request.

    No connection is opened here; `request` performs a single urllib call
    with a bounded timeout. `HttpClient` refuses every redirect, so a
    redirect to another origin can never be followed implicitly.
    """

    def __init__(self, timeout_s=DEFAULT_TIMEOUT_S):
        self._timeout_s = timeout_s

    def request(self, endpoint, method, path, *, headers=None, form=None):
        return HttpClient(endpoint, timeout=self._timeout_s).request(
            method, path, headers=headers, form=form)


def _empty_pagination():
    return {"complete": False, "pages": 0, "total_elements": None}


def _snapshot(outcome=OUTCOME_INCONCLUSIVE, reason="not executed"):
    return {"outcome": outcome, "reason": reason, "launch": None,
            "ready": None, "stats": None, "results": [],
            "pagination": _empty_pagination()}


def _required(mapping, key, operation):
    if not isinstance(mapping, dict) or key not in mapping:
        raise _Fail(OUTCOME_INCONCLUSIVE,
                    f"{operation}: missing field {key}")
    return mapping[key]


def _required_int(value, field, operation, *, minimum=None):
    if isinstance(value, bool) or not isinstance(value, int):
        raise _Fail(OUTCOME_INCONCLUSIVE,
                    f"{operation}: field {field} is not an integer")
    if minimum is not None and value < minimum:
        raise _Fail(OUTCOME_INCONCLUSIVE,
                    f"{operation}: field {field} below {minimum}")
    return value


def _required_bool(value, field, operation):
    if not isinstance(value, bool):
        raise _Fail(OUTCOME_INCONCLUSIVE,
                    f"{operation}: field {field} is not a boolean")
    return value


def _required_str(value, field, operation):
    if not isinstance(value, str):
        raise _Fail(OUTCOME_INCONCLUSIVE,
                    f"{operation}: field {field} is not a string")
    return value


class RestProbe:
    """Read-only snapshot reader for one TestOps launch.

    `token` is the API token exchanged once per `read_snapshot` call for a
    short-lived JWT; both secrets stay in process memory only. `http` is an
    injectable layer exposing
    ``request(endpoint, method, path, *, headers=None, form=None)`` and
    returning a response with integer ``status`` and bytes ``body``; the
    default is `UrllibHttp`. Construction performs no network or file I/O.
    """

    def __init__(self, token, *, http=None, timeout_s=DEFAULT_TIMEOUT_S,
                 page_size=DEFAULT_PAGE_SIZE, max_pages=DEFAULT_MAX_PAGES):
        if not isinstance(token, str) or not token:
            raise ValueError("RestProbe requires a non-empty API token")
        if http is not None and not callable(getattr(http, "request", None)):
            raise ValueError("http layer must expose request()")
        self._token = token
        self._http = http or UrllibHttp(timeout_s=timeout_s)
        self._page_size = self._positive_int(page_size, "page_size")
        self._max_pages = self._positive_int(max_pages, "max_pages")

    @staticmethod
    def _positive_int(value, name):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
        return value

    def read_snapshot(self, endpoint, launch_id):
        """Read one launch and return the contract snapshot dict.

        Executes one token exchange, the launch GET, progress, statistic,
        a strict paginated result walk and a final launch re-read that
        detects metadata drift. Reads are sequential and stop at the first
        failure; whatever was already gathered remains in the dict.
        KeyboardInterrupt and SystemExit propagate to the caller.
        """
        snapshot = _snapshot()
        try:
            lid = self._launch_id(launch_id)
            jwt = self._authenticate(endpoint)
            headers = {"Authorization": f"Bearer {jwt}"}
            launch = self._get_launch(endpoint, headers, lid)
            snapshot["launch"] = launch
            snapshot["ready"] = self._get_progress(endpoint, headers, lid)
            snapshot["stats"] = self._get_statistic(endpoint, headers, lid)
            results, pagination, fail = self._read_results(
                endpoint, headers, lid)
            snapshot["results"] = results
            snapshot["pagination"] = pagination
            if fail is not None:
                raise fail
            self._check_drift(endpoint, headers, lid, launch)
        except _Fail as fail:
            snapshot["outcome"] = fail.outcome
            snapshot["reason"] = fail.reason
            return snapshot
        snapshot["outcome"] = OUTCOME_COMPLETE
        snapshot["reason"] = "snapshot fully read"
        return snapshot

    @staticmethod
    def _launch_id(launch_id):
        if isinstance(launch_id, bool):
            lid = None
        elif isinstance(launch_id, int):
            lid = launch_id
        elif isinstance(launch_id, str) and launch_id.isdigit():
            lid = int(launch_id)
        else:
            lid = None
        if lid is None or lid < 0:
            raise _Fail(OUTCOME_INCONCLUSIVE,
                        "launch_id is not an integer")
        return lid

    def _request(self, endpoint, method, path, *, headers=None, form=None,
                 operation):
        """One HTTP call; transport failures collapse to `unreachable`."""
        try:
            response = self._http.request(
                endpoint, method, path, headers=headers, form=form)
        except Exception:
            raise _Fail(OUTCOME_UNREACHABLE,
                        f"{operation}: transport error") from None
        status = getattr(response, "status", None)
        body = getattr(response, "body", None)
        if isinstance(status, bool) or not isinstance(status, int):
            raise _Fail(OUTCOME_INCONCLUSIVE,
                        f"{operation}: malformed transport response")
        if not isinstance(body, (bytes, str)):
            raise _Fail(OUTCOME_INCONCLUSIVE,
                        f"{operation}: malformed transport response")
        return status, body

    @staticmethod
    def _json(body, operation):
        try:
            return json.loads(body)
        except (TypeError, ValueError, UnicodeError):
            raise _Fail(OUTCOME_INCONCLUSIVE,
                        f"{operation}: response is not valid JSON") from None

    @staticmethod
    def _expect_ok(status, operation):
        if status != 200:
            raise _Fail(OUTCOME_UNREACHABLE,
                        f"{operation}: HTTP {status}")

    def _authenticate(self, endpoint):
        """Exchange the API token for a JWT; secrets stay in memory only."""
        status, body = self._request(
            endpoint, "POST", _TOKEN_PATH, operation="token_exchange",
            form={"grant_type": "apitoken", "scope": "openid",
                  "token": self._token})
        self._expect_ok(status, "token_exchange")
        payload = self._json(body, "token_exchange")
        jwt = _required(payload, "access_token", "token_exchange")
        _required_str(jwt, "access_token", "token_exchange")
        token_type = payload.get("token_type")
        if token_type is not None and (
                not isinstance(token_type, str)
                or token_type.lower() != "bearer"):
            raise _Fail(OUTCOME_INCONCLUSIVE,
                        "token_exchange: unexpected token_type")
        if not jwt:
            raise _Fail(OUTCOME_INCONCLUSIVE,
                        "token_exchange: empty access_token")
        return jwt

    def _get_launch(self, endpoint, headers, launch_id):
        """GET /api/launch/{id}; a direct 404 is the only `missing` source."""
        status, body = self._request(
            endpoint, "GET", _LAUNCH_PATH.format(id=launch_id),
            headers=headers, operation="launch_get")
        if status == 404:
            raise _Fail(OUTCOME_MISSING,
                        f"launch_get: HTTP 404 for launch {launch_id}")
        self._expect_ok(status, "launch_get")
        payload = self._json(body, "launch_get")
        return self._normalize_launch(payload, launch_id)

    @staticmethod
    def _normalize_launch(payload, expected_id):
        operation = "launch_get"
        if not isinstance(payload, dict):
            raise _Fail(OUTCOME_INCONCLUSIVE,
                        f"{operation}: response is not an object")
        lid = _required_int(_required(payload, "id", operation),
                            "id", operation)
        if lid != expected_id:
            raise _Fail(OUTCOME_INCONCLUSIVE,
                        f"{operation}: returned launch id {lid} != "
                        f"requested {expected_id}")
        project_id = _required_int(_required(payload, "projectId", operation),
                                   "projectId", operation)
        closed = _required_bool(_required(payload, "closed", operation),
                                "closed", operation)
        return {"id": lid, "project_id": project_id, "closed": closed}

    def _get_progress(self, endpoint, headers, launch_id):
        status, body = self._request(
            endpoint, "GET", _PROGRESS_PATH.format(id=launch_id),
            headers=headers, operation="progress")
        self._expect_ok(status, "progress")
        payload = self._json(body, "progress")
        return _required_bool(_required(payload, "ready", "progress"),
                              "ready", "progress")

    def _get_statistic(self, endpoint, headers, launch_id):
        """GET /statistic: [{status, count}] -> {status: nonnegative_int}."""
        operation = "statistic"
        status, body = self._request(
            endpoint, "GET", _STATISTIC_PATH.format(id=launch_id),
            headers=headers, operation=operation)
        self._expect_ok(status, operation)
        payload = self._json(body, operation)
        if not isinstance(payload, list):
            raise _Fail(OUTCOME_INCONCLUSIVE,
                        f"{operation}: response is not an array")
        stats = {}
        for item in payload:
            raw_status = _required(item, "status", operation)
            status_name = _required_str(raw_status, "status", operation)
            count = _required_int(_required(item, "count", operation),
                                  "count", operation, minimum=0)
            key = status_name.lower()
            if key in stats:
                raise _Fail(OUTCOME_INCONCLUSIVE,
                            f"{operation}: duplicate status {key!r}")
            stats[key] = count
        return stats

    def _read_results(self, endpoint, headers, launch_id):
        """Strict Spring Page walk of GET /api/testresult.

        Returns (results, pagination, fail): on failure `fail` is a _Fail
        and `results`/`pagination` hold the partial evidence collected so
        far. Only documented parameters are sent (launchId, page, size);
        the server's default sort is used and instability is detected, not
        worked around.
        """
        operation = "testresult"
        results, seen_ids = [], set()
        pagination = _empty_pagination()
        total_expected = pages_expected = None
        for page in range(self._max_pages):
            path = _RESULTS_PATH + "?" + urlencode(
                {"launchId": launch_id, "page": page,
                 "size": self._page_size})
            status, body = self._request(
                endpoint, "GET", path, headers=headers,
                operation=operation)
            if status != 200:
                return results, pagination, _Fail(
                    OUTCOME_UNREACHABLE,
                    f"{operation}: HTTP {status} on page {page}")
            payload = self._json(body, operation)
            if not isinstance(payload, dict):
                return results, pagination, _Fail(
                    OUTCOME_INCONCLUSIVE,
                    f"{operation}: page {page} is not an object")
            try:
                number = _required_int(_required(payload, "number", operation),
                                       "number", operation, minimum=0)
                content = _required(payload, "content", operation)
                if not isinstance(content, list):
                    raise _Fail(OUTCOME_INCONCLUSIVE,
                                f"{operation}: content is not an array")
                total = _required_int(
                    _required(payload, "totalElements", operation),
                    "totalElements", operation, minimum=0)
                total_pages = _required_int(
                    _required(payload, "totalPages", operation),
                    "totalPages", operation, minimum=0)
                last = _required_bool(_required(payload, "last", operation),
                                      "last", operation)
            except _Fail as fail:
                return results, pagination, fail
            pagination["pages"] = page + 1
            if total_expected is None:
                total_expected, pages_expected = total, total_pages
                pagination["total_elements"] = total
                if total > 0 and total_pages == 0:
                    return results, pagination, _Fail(
                        OUTCOME_INCONCLUSIVE,
                        f"{operation}: totalElements {total} contradicts "
                        "totalPages 0")
            elif (total, total_pages) != (total_expected, pages_expected):
                return results, pagination, _Fail(
                    OUTCOME_INCONCLUSIVE,
                    f"{operation}: totals changed during the walk "
                    f"({total_expected}/{pages_expected} -> "
                    f"{total}/{total_pages})")
            if number != page:
                return results, pagination, _Fail(
                    OUTCOME_INCONCLUSIVE,
                    f"{operation}: requested page {page}, got number "
                    f"{number}")
            if not content:
                if not last:
                    return results, pagination, _Fail(
                        OUTCOME_INCONCLUSIVE,
                        f"{operation}: page {page} is empty but not last; "
                        "the walk cannot prove completeness")
            else:
                if number >= pages_expected:
                    return results, pagination, _Fail(
                        OUTCOME_INCONCLUSIVE,
                        f"{operation}: page {number} carries items beyond "
                        f"totalPages {pages_expected}")
                for item in content:
                    try:
                        normalized = self._normalize_result(item, launch_id)
                    except _Fail as fail:
                        return results, pagination, fail
                    if normalized["id"] in seen_ids:
                        return results, pagination, _Fail(
                            OUTCOME_INCONCLUSIVE,
                            f"{operation}: duplicate result id "
                            f"{normalized['id']} in the walk")
                    seen_ids.add(normalized["id"])
                    results.append(normalized)
            if last:
                if pages_expected > 0 and number != pages_expected - 1:
                    return results, pagination, _Fail(
                        OUTCOME_INCONCLUSIVE,
                        f"{operation}: last flag on page {number} but "
                        f"totalPages is {pages_expected}")
                if len(results) != total_expected:
                    return results, pagination, _Fail(
                        OUTCOME_INCONCLUSIVE,
                        f"{operation}: collected {len(results)} results "
                        f"but totalElements is {total_expected}")
                pagination["complete"] = True
                return results, pagination, None
            if number + 1 >= pages_expected:
                return results, pagination, _Fail(
                    OUTCOME_INCONCLUSIVE,
                    f"{operation}: page {number} not last but totalPages "
                    f"{pages_expected} leaves no next page")
        return results, pagination, _Fail(
            OUTCOME_INCONCLUSIVE,
            f"{operation}: page limit {self._max_pages} reached without "
            "a last page")

    @staticmethod
    def _normalize_result(item, launch_id):
        """Allowlist-normalize one TestResultDto; nothing else is kept."""
        operation = "testresult"
        if not isinstance(item, dict):
            raise _Fail(OUTCOME_INCONCLUSIVE,
                        f"{operation}: result entry is not an object")
        result_id = _required_int(_required(item, "id", operation),
                                  "id", operation)
        name = _required_str(_required(item, "name", operation),
                             "name", operation)
        status = _required_str(_required(item, "status", operation),
                               "status", operation)
        test_case_id = item.get("testCaseId")
        if test_case_id is not None:
            test_case_id = _required_int(test_case_id, "testCaseId",
                                         operation)
        result_launch = _required_int(_required(item, "launchId", operation),
                                      "launchId", operation)
        if result_launch != launch_id:
            raise _Fail(OUTCOME_INCONCLUSIVE,
                        f"{operation}: result {result_id} belongs to "
                        f"launch {result_launch}, not {launch_id}")
        project_id = _required_int(_required(item, "projectId", operation),
                                   "projectId", operation)
        hidden = _required_bool(_required(item, "hidden", operation),
                                "hidden", operation)
        retried = item.get("retriedBy")
        retried_by_id = None
        if retried is not None:
            retried_by_id = _required_int(
                _required(retried, "id", operation),
                "retriedBy.id", operation)
        return {"id": result_id, "name": name, "status": status.lower(),
                "test_case_id": test_case_id, "launch_id": result_launch,
                "project_id": project_id, "hidden": hidden,
                "retried_by_id": retried_by_id}

    def _check_drift(self, endpoint, headers, launch_id, original):
        """Re-read the launch; metadata drift invalidates the snapshot.

        A changed id/project/closed means the result set may have been
        read across a processing boundary, so the snapshot cannot be
        trusted as one consistent point in time.
        """
        again = self._get_launch(endpoint, headers, launch_id)
        if again != original:
            raise _Fail(OUTCOME_INCONCLUSIVE,
                        "launch metadata changed while reading the "
                        "result set")
