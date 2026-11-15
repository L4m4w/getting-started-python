"""GitHub REST pull-request transport for the QA workflow (stdlib only).

`GitHubPrTransport` implements the `PrTransport` protocol
(`adapters.PrTransport`) against the public GitHub REST API:

- ``search(key)`` — a fresh paginated ``GET /repos/{o}/{r}/pulls`` walk
  with ``state=all`` plus the documented ``head``/``base`` filters.
  Every returned item is strictly normalized; closed, merged, non-draft
  and fork-head PRs are kept in the result as conflict candidates so a
  remote effect can never be dropped into a false empty set.
- ``create(spec)`` — exactly one ``POST /repos/{o}/{r}/pulls`` with
  ``draft: true``, after a local spec/body-digest check. No verification
  GET and no retry happen inside create: a readable number is returned
  as soon as the POST response proves it, so the caller can persist the
  remote effect before any further read.
- ``get(repo, number)`` — targeted ``GET /repos/{o}/{r}/pulls/{n}`` plus
  a strict paginated ``.../files`` walk and a second detail read:
  detail → files → detail. The file list must be complete and unique
  and must equal the declared ``changed_files`` count; the two detail
  reads must agree on every used field. Returns ``None`` only on a
  direct 404 of the first read; a closed, merged, non-draft, foreign,
  incomplete or drifting PR is refused via a controlled error, never
  surfaced as the expected draft.

Boundaries: only ``api.github.com`` is ever contacted; the canonical
``github.com/owner/repo`` repo key is the single accepted identity;
the Authorization token is fetched lazily per call from the injected
provider (the default reads ``GITHUB_TOKEN`` at call time) and is sent
only as a ``Bearer`` header — never in URLs, and never forwarded to
other hosts because redirects are refused by the underlying client and
``Link`` URLs are never dereferenced (they are only a has-next signal).

Documentation sources (read 2026-11-16, docs.github.com):
- ``/en/rest/pulls/pulls`` — list/get/create/files endpoints, response
  fields (``number``, ``state``, ``draft``, ``merged``, ``title``,
  ``body``, ``html_url``, ``head``/``base`` ``ref``/``sha``/``repo``,
  ``changed_files``), status codes (200/201/304/404/406/422/500/503),
  the ``per_page`` (max 100) / ``page`` parameters and the documented
  3000-file listing limit;
- ``/en/rest/using-the-rest-api/using-pagination-in-the-rest-api`` —
  ``Link`` header ``rel="next"`` semantics.
"""
import hashlib
import json
import os
import re
from urllib.parse import urlencode

from infrastructure.http.client import HttpClient

from . import state as state_mod
from .adapters import PrRef, PrTransport

GITHUB_API_ENDPOINT = "https://api.github.com"
GITHUB_REPO_HOST = "github.com"
API_VERSION = "2026-03-10"
ACCEPT_HEADER = "application/vnd.github+json"
DEFAULT_TIMEOUT_S = 30
DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 100
DEFAULT_TOKEN_ENV = "GITHUB_TOKEN"
# docs.github.com /en/rest/pulls/pulls (2026-11-16): "Responses include
# a maximum of 3000 files" — a count above it is never provable.
MAX_LISTED_FILES = 3000

OWNER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}")
REPO_NAME_RE = re.compile(r"[A-Za-z0-9._-]{1,100}")
LINK_PAIR_RE = re.compile(r'<([^>]+)>\s*;\s*rel\s*=\s*"([^"]+)"')

KNOWN_PR_STATES = ("open", "closed")

# Every field the transport consumes from a PR detail payload; the two
# reads of one ``get`` must agree on all of them for the snapshot to be
# treated as consistent.
SNAPSHOT_FIELDS = ("number", "state", "title", "url", "draft",
                   "body_sha256", "head_branch", "head_sha", "head_repo",
                   "base_branch", "base_sha", "merged", "changed_files")


class GitHubTransportError(state_mod.WorkflowError):
    """Controlled GitHub transport failure; carries no secrets/payloads."""


class GitHubSpecError(GitHubTransportError):
    """The search key or create spec is invalid; no remote call is made."""


class GitHubAuthError(GitHubTransportError):
    """The token provider could not supply a usable credential."""


class GitHubHttpError(GitHubTransportError):
    """HTTP transport failure or an unexpected response status."""


class GitHubResponseError(GitHubTransportError):
    """A response is malformed, foreign or incomplete; nothing is guessed."""


class GitHubPrStateError(GitHubTransportError):
    """The remote PR exists but is closed/merged/non-draft/foreign."""


class EnvGitHubToken:
    """Default token provider: reads ``GITHUB_TOKEN`` at call time only."""

    def __init__(self, env_var=DEFAULT_TOKEN_ENV):
        self._env_var = env_var

    def __call__(self):
        return os.environ.get(self._env_var)


class UrllibHttp:
    """Default injected HTTP layer: one bounded HttpClient per request.

    ``HttpClient`` refuses every redirect, so a 3xx response surfaces as
    a status and can never lead credentials to another origin.
    """

    def __init__(self, timeout_s=DEFAULT_TIMEOUT_S):
        self._timeout_s = timeout_s

    def request(self, endpoint, method, path, *, headers=None, payload=None):
        return HttpClient(endpoint, timeout=self._timeout_s).request(
            method, path, headers=headers, payload=payload)


def _required(mapping, key, operation):
    if not isinstance(mapping, dict) or key not in mapping:
        raise GitHubResponseError(f"{operation}: missing field {key}")
    return mapping[key]


def _required_str(value, field, operation):
    if not isinstance(value, str):
        raise GitHubResponseError(f"{operation}: field {field} is not a string")
    return value


def _required_int(value, field, operation, *, minimum=None):
    if isinstance(value, bool) or not isinstance(value, int):
        raise GitHubResponseError(
            f"{operation}: field {field} is not an integer")
    if minimum is not None and value < minimum:
        raise GitHubResponseError(
            f"{operation}: field {field} below {minimum}")
    return value


def _required_bool(value, field, operation):
    if not isinstance(value, bool):
        raise GitHubResponseError(
            f"{operation}: field {field} is not a boolean")
    return value


def _header(response, name):
    """Case-insensitive single header lookup over dict/HTTPMessage."""
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    try:
        value = headers.get(name)
        if value is not None:
            return value
    except AttributeError:
        pass
    try:
        for key, value in headers.items():
            if str(key).lower() == name.lower():
                return value
    except AttributeError:
        pass
    return None


class GitHubPrTransport(PrTransport):
    """stdlib GitHub REST pull-request transport.

    ``token_provider`` is a zero-argument callable returning the token;
    it is invoked only inside an authorized HTTP call, never at
    construction. ``http`` is the injected layer exposing
    ``request(endpoint, method, path, *, headers=None, payload=None)``
    and returning an object with integer ``status``, ``body`` (bytes or
    str) and ``headers`` (case-insensitive mapping); the default is
    `UrllibHttp` over the project's bounded no-redirect `HttpClient`.
    Construction performs no network, credential or file access.
    """

    def __init__(self, token_provider=None, http=None, *,
                 timeout_s=DEFAULT_TIMEOUT_S, page_size=DEFAULT_PAGE_SIZE,
                 max_pages=DEFAULT_MAX_PAGES):
        if http is not None and not callable(getattr(http, "request", None)):
            raise ValueError("http layer must expose request()")
        if token_provider is not None and not callable(token_provider):
            raise ValueError("token_provider must be callable")
        self._token_provider = token_provider or EnvGitHubToken()
        self._http = http or UrllibHttp(timeout_s=timeout_s)
        self._page_size = self._positive_int(page_size, "page_size")
        self._max_pages = self._positive_int(max_pages, "max_pages")

    @staticmethod
    def _positive_int(value, name):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
        return value

    # -- plumbing ------------------------------------------------------

    def _auth_headers(self):
        try:
            token = self._token_provider()
        except Exception:
            raise GitHubAuthError("token provider failed") from None
        if not isinstance(token, str) or not token.strip():
            raise GitHubAuthError("no GitHub token from the provider")
        return {"Accept": ACCEPT_HEADER,
                "X-GitHub-Api-Version": API_VERSION,
                "Authorization": f"Bearer {token}"}

    def _request(self, method, path, *, headers, payload=None, operation):
        """One HTTP call; transport failures collapse to GitHubHttpError."""
        try:
            response = self._http.request(
                GITHUB_API_ENDPOINT, method, path,
                headers=headers, payload=payload)
        except Exception:
            raise GitHubHttpError(f"{operation}: transport error") from None
        status = getattr(response, "status", None)
        body = getattr(response, "body", None)
        if isinstance(status, bool) or not isinstance(status, int):
            raise GitHubResponseError(
                f"{operation}: malformed transport response")
        if not isinstance(body, (bytes, str)):
            raise GitHubResponseError(
                f"{operation}: malformed transport response")
        return status, _header(response, "link"), body

    @staticmethod
    def _json(body, operation):
        try:
            return json.loads(body)
        except (TypeError, ValueError, UnicodeError):
            raise GitHubResponseError(
                f"{operation}: response is not valid JSON") from None

    @staticmethod
    def _parse_repo_key(repo):
        """Strict canonical ``github.com/owner/repo`` -> (owner, name)."""
        if not isinstance(repo, str) or not repo.strip():
            raise GitHubSpecError(
                "repo must be the canonical github.com/owner/repo key")
        parts = repo.strip().split("/")
        if len(parts) != 3 or parts[0].lower() != GITHUB_REPO_HOST:
            raise GitHubSpecError(
                f"repo {parts[0] if parts else repo!r} is not the "
                f"{GITHUB_REPO_HOST}/owner/repo canonical key")
        owner, name = parts[1], parts[2]
        if not OWNER_RE.fullmatch(owner):
            raise GitHubSpecError("repo owner has an unexpected shape")
        if not REPO_NAME_RE.fullmatch(name) or name in (".", ".."):
            raise GitHubSpecError("repo name has an unexpected shape")
        return owner, name

    @staticmethod
    def _has_next(link_header, operation):
        if link_header is None:
            return False
        pairs = LINK_PAIR_RE.findall(link_header)
        if not pairs:
            raise GitHubResponseError(
                f"{operation}: malformed Link header")
        return "next" in {rel for _, rel in pairs}

    def _walk_pages(self, headers, base_path, query, operation):
        """Strict fresh walk of a page-numbered list endpoint.

        ``rel="next"`` in the Link header is the only has-more signal;
        link URLs are never dereferenced — the next request rebuilds the
        documented ``page`` parameter itself. Any anomaly (empty middle
        page, over-full page, missing last page, malformed Link) stops
        the walk as inconclusive instead of faking completeness.
        """
        items = []
        for page in range(1, self._max_pages + 1):
            params = dict(query)
            params["per_page"] = self._page_size
            params["page"] = page
            path = base_path + "?" + urlencode(params)
            status, link, body = self._request(
                "GET", path, headers=headers, operation=operation)
            if status != 200:
                raise GitHubHttpError(
                    f"{operation}: HTTP {status} on page {page}")
            payload = self._json(body, operation)
            if not isinstance(payload, list):
                raise GitHubResponseError(
                    f"{operation}: page {page} is not an array")
            if len(payload) > self._page_size:
                raise GitHubResponseError(
                    f"{operation}: page {page} exceeds per_page")
            has_next = self._has_next(link, operation)
            if not payload and has_next:
                raise GitHubResponseError(
                    f"{operation}: empty page {page} with a next link")
            items.extend(payload)
            if not has_next:
                return items
        raise GitHubResponseError(
            f"{operation}: page limit {self._max_pages} reached with a "
            "next link")

    # -- normalization -------------------------------------------------

    def _normalize_item(self, payload, owner, name, operation, *,
                        detail=False):
        """Strict allowlist normalization of one PR payload.

        Only fields the transport actually uses are checked; extra fields
        are ignored. ``base.repo.full_name`` must equal the requested
        repository — a pull listed by one repo's endpoint whose base is a
        different repo is unresolvable. ``head.repo`` may be null (a
        deleted fork) or foreign; the caller decides whether that is a
        usable candidate. ``detail=True`` additionally requires the
        full-detail fields ``merged`` and ``changed_files``, which the
        list schema does not carry.
        """
        if not isinstance(payload, dict):
            raise GitHubResponseError(f"{operation}: item is not an object")
        info = {}
        info["number"] = _required_int(
            _required(payload, "number", operation), "number", operation,
            minimum=1)
        state = _required_str(
            _required(payload, "state", operation), "state", operation)
        if state not in KNOWN_PR_STATES:
            raise GitHubResponseError(
                f"{operation}: unexpected state {state!r}")
        info["state"] = state
        info["title"] = _required_str(
            _required(payload, "title", operation), "title", operation)
        info["url"] = _required_str(
            _required(payload, "html_url", operation), "html_url", operation)
        draft = payload.get("draft", False)
        if not isinstance(draft, bool):
            raise GitHubResponseError(
                f"{operation}: field draft is not a boolean")
        info["draft"] = draft
        body = _required(payload, "body", operation)
        if body is not None and not isinstance(body, str):
            raise GitHubResponseError(
                f"{operation}: field body is not a string or null")
        info["body_sha256"] = self._body_sha256(body)
        head = self._ref_side(payload, "head", operation,
                              repo_nullable=True)
        base = self._ref_side(payload, "base", operation,
                              repo_nullable=False)
        repo_key = f"{owner}/{name}".lower()
        if base["repo_name"].lower() != repo_key:
            raise GitHubResponseError(
                f"{operation}: base.repo {base['repo_name']!r} is not "
                f"the requested repository")
        info["head_branch"] = head["ref"]
        info["head_sha"] = head["sha"]
        info["head_repo"] = head["repo_name"]
        info["base_branch"] = base["ref"]
        info["base_sha"] = base["sha"]
        if detail:
            info["merged"] = _required_bool(
                _required(payload, "merged", operation), "merged", operation)
            info["changed_files"] = _required_int(
                _required(payload, "changed_files", operation),
                "changed_files", operation, minimum=0)
        return info

    def _ref_side(self, payload, field, operation, *, repo_nullable):
        side = _required(payload, field, operation)
        if not isinstance(side, dict):
            raise GitHubResponseError(
                f"{operation}: field {field} is not an object")
        ref = _required_str(
            _required(side, "ref", operation), f"{field}.ref", operation)
        sha = _required_str(
            _required(side, "sha", operation), f"{field}.sha", operation)
        if not state_mod.HEX40_64.fullmatch(sha):
            raise GitHubResponseError(
                f"{operation}: field {field}.sha is not a commit SHA")
        repo = _required(side, "repo", operation)
        if repo is None:
            if not repo_nullable:
                raise GitHubResponseError(
                    f"{operation}: field {field}.repo is null")
            repo_name = None
        else:
            if not isinstance(repo, dict):
                raise GitHubResponseError(
                    f"{operation}: field {field}.repo is not an object")
            repo_name = _required_str(
                _required(repo, "full_name", operation),
                f"{field}.repo.full_name", operation)
        return {"ref": ref, "sha": sha, "repo_name": repo_name}

    @staticmethod
    def _body_sha256(body):
        """Remote null/empty normalize to None; exact UTF-8 otherwise."""
        if body is None or body == "":
            return None
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    @staticmethod
    def _to_ref(repo_key, info, files):
        return PrRef(repo=repo_key, number=info["number"], url=info["url"],
                     title=info["title"], head_branch=info["head_branch"],
                     base_branch=info["base_branch"],
                     head_sha=info["head_sha"],
                     body_sha256=info["body_sha256"], files=list(files))

    @staticmethod
    def _readable_ref(payload, repo_key):
        """Minimal PrRef when only number/url of a create are readable."""
        if not isinstance(payload, dict):
            return None
        number = payload.get("number")
        if isinstance(number, bool) or not isinstance(number, int) \
                or number <= 0:
            return None
        url = payload.get("html_url")
        return PrRef(repo=repo_key, number=number,
                     url=url if isinstance(url, str) else None)

    # -- PrTransport ---------------------------------------------------

    def search(self, key):
        """Fresh full PR list for the repo/head/base key, or an error.

        Returns every remotely matching PR — including closed, merged,
        non-draft and fork-head ones — as ``PrRef`` candidates (``files``
        is not part of the list schema and stays empty). The caller
        performs key/exact filtering; nothing is dropped into a false
        empty set.
        """
        operation = "pr-search"
        owner, name = self._search_target(key)
        headers = self._auth_headers()
        query = {"state": "all"}
        head_branch = key.get("head_branch")
        base_branch = key.get("base_branch")
        if head_branch is not None:
            query["head"] = f"{owner}:{head_branch}"
        if base_branch is not None:
            query["base"] = base_branch
        items = self._walk_pages(
            headers, f"/repos/{owner}/{name}/pulls", query, operation)
        refs, seen = [], set()
        for item in items:
            info = self._normalize_item(item, owner, name, operation)
            if info["number"] in seen:
                raise GitHubResponseError(
                    f"{operation}: duplicate PR number "
                    f"{info['number']} in the walk")
            seen.add(info["number"])
            refs.append(self._to_ref(key["repo"], info, files=[]))
        return refs

    def _search_target(self, key):
        if not isinstance(key, dict):
            raise GitHubSpecError("search key must be a mapping")
        owner, name = self._parse_repo_key(key.get("repo"))
        for field in ("head_branch", "base_branch"):
            value = key.get(field)
            if value is not None and (not isinstance(value, str) or not value):
                raise GitHubSpecError(
                    f"search key {field} must be a non-empty string or null")
        return owner, name

    def create(self, spec):
        """One draft POST; returns a ref whose number is already readable.

        The spec/body pair is validated before any POST: ``body_text``
        must hash to ``body_sha256``, and a recorded digest without
        reproducible text blocks the create locally. Exactly one POST is
        issued — never retried; on a 201 the response fields are
        normalized (server-reported, never echoed from the spec). If
        only the number/url are readable, a minimal ref still returns so
        the caller can persist the remote effect; a fully unreadable
        response raises a controlled error.
        """
        operation = "pr-create"
        repo_key = spec.get("repo") if isinstance(spec, dict) else None
        owner, name, payload = self._create_fields(spec)
        headers = self._auth_headers()
        status, _link, body = self._request(
            "POST", f"/repos/{owner}/{name}/pulls", headers=headers,
            payload=payload, operation=operation)
        if status != 201:
            raise GitHubHttpError(f"{operation}: HTTP {status}")
        data = self._json(body, operation)
        try:
            info = self._normalize_item(data, owner, name, operation)
            repo_slug = f"{owner}/{name}".lower()
            if info["head_repo"] is None \
                    or info["head_repo"].lower() != repo_slug:
                raise GitHubResponseError(
                    f"{operation}: head.repo does not match the "
                    "requested repository")
        except GitHubTransportError:
            minimal = self._readable_ref(data, repo_key)
            if minimal is not None:
                return minimal
            raise
        return self._to_ref(repo_key, info, files=[])

    def _create_fields(self, spec):
        if not isinstance(spec, dict):
            raise GitHubSpecError("create spec must be a mapping")
        owner, name = self._parse_repo_key(spec.get("repo"))
        payload = {"title": self._spec_str(spec, "title"),
                   "head": self._spec_str(spec, "head_branch"),
                   "base": self._spec_str(spec, "base_branch"),
                   "draft": True}
        body = self._create_body(spec)
        if body is not None:
            payload["body"] = body
        return owner, name, payload

    @staticmethod
    def _spec_str(spec, field):
        value = spec.get(field)
        if not isinstance(value, str) or not value:
            raise GitHubSpecError(
                f"spec field {field} must be a non-empty string")
        return value

    def _create_body(self, spec):
        """Pair ``body_text``/``body_sha256`` before any POST.

        New canonical specs carry the reproducible text plus the digest
        of its exact UTF-8 bytes; absent/null/empty text is only valid
        with a null digest. A recorded digest without reproducible text
        (a legacy or incomplete spec) is a local block — never a guessed
        body — and a non-empty text is sent only when it hashes to the
        pinned digest.
        """
        digest = spec.get("body_sha256")
        if "body_text" not in spec:
            if digest is not None:
                raise GitHubSpecError(
                    "spec records body_sha256 without body_text; the "
                    "exact body is not reproducible — re-prepare required")
            return None
        text = spec.get("body_text")
        if text is None or text == "":
            if digest is not None:
                raise GitHubSpecError(
                    "spec pins a body digest without reproducible text; "
                    "re-prepare required")
            return None
        if not isinstance(text, str):
            raise GitHubSpecError("spec body_text must be a string or null")
        if not isinstance(digest, str) or not state_mod.HEX64.fullmatch(digest):
            raise GitHubSpecError(
                "spec body_text is present but body_sha256 is missing "
                "or not a 64-hex digest")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != digest:
            raise GitHubSpecError(
                "spec body_text does not hash to the pinned body_sha256; "
                "refusing POST")
        return text

    def get(self, repo, number):
        """Consistent snapshot of one PR, or None on a proven direct 404.

        The read sequence is detail → all files pages → detail again.
        The returned ref carries the real server-reported body digest,
        head SHA and the complete file list — the number of unique files
        read must equal the declared ``changed_files`` count, and the
        second detail read must agree with the first on every used field
        (number/repo/branches/head/base SHA/title/body/draft/state/
        merged/count). A PR that is not an open, unmerged same-repo
        draft — or whose response, file walk or confirmation read cannot
        be proven complete and consistent — is refused with a controlled
        error instead of producing a false verified reference.
        """
        operation = "pr-get"
        owner, name = self._parse_repo_key(repo)
        if isinstance(number, bool) or not isinstance(number, int) \
                or number <= 0:
            raise GitHubSpecError(
                "pull number must be a positive integer")
        headers = self._auth_headers()
        detail_path = f"/repos/{owner}/{name}/pulls/{number}"
        status, _link, body = self._request(
            "GET", detail_path, headers=headers, operation=operation)
        if status == 404:
            return None
        if status != 200:
            raise GitHubHttpError(f"{operation}: HTTP {status}")
        info = self._normalize_item(
            self._json(body, operation), owner, name, operation,
            detail=True)
        if info["number"] != number:
            raise GitHubResponseError(
                f"{operation}: returned number {info['number']} != "
                f"requested {number}")
        if info["state"] != "open":
            raise GitHubPrStateError(
                f"{operation}: remote PR #{number} is {info['state']}")
        if info["merged"]:
            raise GitHubPrStateError(
                f"{operation}: remote PR #{number} is merged")
        if not info["draft"]:
            raise GitHubPrStateError(
                f"{operation}: remote PR #{number} is not a draft")
        repo_slug = f"{owner}/{name}".lower()
        if info["head_repo"] is None:
            raise GitHubPrStateError(
                f"{operation}: head repository of PR #{number} is not "
                "readable")
        if info["head_repo"].lower() != repo_slug:
            raise GitHubPrStateError(
                f"{operation}: head of PR #{number} belongs to "
                f"{info['head_repo']!r}")
        if info["changed_files"] > MAX_LISTED_FILES:
            raise GitHubResponseError(
                f"{operation}: PR #{number} declares "
                f"{info['changed_files']} changed files, above the "
                f"documented {MAX_LISTED_FILES}-file listing limit; "
                "the file set is not provably complete")
        files = self._read_files(headers, owner, name, number)
        if len(files) != info["changed_files"]:
            raise GitHubResponseError(
                f"{operation}: read {len(files)} unique files but PR "
                f"#{number} declares changed_files="
                f"{info['changed_files']}")
        info2 = self._reconfirm_detail(
            headers, detail_path, owner, name, number, operation)
        for field_name in SNAPSHOT_FIELDS:
            if info[field_name] != info2[field_name]:
                raise GitHubResponseError(
                    f"{operation}: field {field_name} changed between "
                    f"the two reads of PR #{number}")
        return self._to_ref(repo, info, files)

    def _reconfirm_detail(self, headers, detail_path, owner, name,
                          number, operation):
        """Second detail read of the same PR inside one ``get``.

        A vanished or malformed second read is a controlled failure —
        the snapshot of the first read alone is not enough evidence.
        """
        status, _link, body = self._request(
            "GET", detail_path, headers=headers, operation=operation)
        if status == 404:
            raise GitHubResponseError(
                f"{operation}: PR #{number} could not be re-read "
                "(HTTP 404) for the snapshot check")
        if status != 200:
            raise GitHubHttpError(
                f"{operation}: HTTP {status} on the confirmation read")
        return self._normalize_item(
            self._json(body, operation), owner, name, operation,
            detail=True)

    def _read_files(self, headers, owner, name, number):
        """Complete paginated filename list of one PR, or an error."""
        operation = "pr-files"
        items = self._walk_pages(
            headers, f"/repos/{owner}/{name}/pulls/{number}/files",
            {}, operation)
        files, seen = [], set()
        for item in items:
            if not isinstance(item, dict):
                raise GitHubResponseError(
                    f"{operation}: file entry is not an object")
            filename = _required_str(
                _required(item, "filename", operation), "filename",
                operation)
            _required_str(
                _required(item, "status", operation), "status", operation)
            if filename in seen:
                raise GitHubResponseError(
                    f"{operation}: duplicate filename {filename!r}")
            seen.add(filename)
            files.append(filename)
        return sorted(files)
