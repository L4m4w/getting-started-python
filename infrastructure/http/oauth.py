"""Authorization code + PKCE без перехода на frontend и вывода секретов."""
import base64
import hashlib
import secrets
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from infrastructure.http.client import PreparationError, require_status
from test_data.consts.category_update import OAUTH_CLIENT_ID, OAUTH_REDIRECT_URI, OAUTH_SCOPE


class Forms(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.forms = []
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.current = {"action": attrs.get("action", ""), "fields": {}}
            self.forms.append(self.current)
        elif (tag == "input" and self.current is not None and attrs.get("name")
              and attrs.get("type", "text") not in ("submit", "button", "reset", "checkbox", "radio")
              and "disabled" not in attrs):
            self.current["fields"].setdefault(attrs["name"], []).append(attrs.get("value", ""))

    def handle_endtag(self, tag):
        if tag == "form":
            self.current = None


def local_path(client, location):
    target = urlsplit(urljoin(client.base_url + "/", location))
    origin = urlsplit(client.base_url)
    if (target.scheme, target.netloc) != (origin.scheme, origin.netloc):
        raise PreparationError("OAuth: неожиданный origin перехода")
    return target.path + ("?" + target.query if target.query else "")


def csrf(client, fields):
    if fields.get("_csrf"):
        return fields["_csrf"]
    for cookie in client.cookies:
        if cookie.name == "XSRF-TOKEN":
            return cookie.value
    raise PreparationError("OAuth: CSRF token отсутствует")


def register(client, username, password):
    page = require_status(client.request("GET", "/register"), 200, "register form")
    forms = Forms(page.body.decode()).forms
    fields = forms[0]["fields"] if forms else {}
    response = client.request("POST", "/register", form={
        "username": username, "password": password, "passwordSubmit": password,
        "_csrf": csrf(client, fields),
    })
    require_status(response, 201, "register")


def obtain_token(client, username, password):
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    path = "/oauth2/authorize?" + urlencode(dict(
        response_type="code", client_id=OAUTH_CLIENT_ID, scope=OAUTH_SCOPE,
        redirect_uri=OAUTH_REDIRECT_URI, code_challenge=challenge,
        code_challenge_method="S256", state=state,
    ))
    response = client.request("GET", path)
    submitted = set()
    for _ in range(12):  # Ограничение протокольных переходов, не retries.
        if response.status in (302, 303):
            location = response.headers.get("Location", "")
            target = urlsplit(location)
            callback = urlsplit(OAUTH_REDIRECT_URI)
            if (target.scheme, target.netloc, target.path) == (callback.scheme, callback.netloc, callback.path):
                query = parse_qs(target.query)
                if query.get("state") != [state] or len(query.get("code", [])) != 1:
                    raise PreparationError("OAuth callback: отсутствует code или не совпадает state")
                token = client.request("POST", "/oauth2/token", form=dict(
                    grant_type="authorization_code", code=query["code"][0],
                    redirect_uri=OAUTH_REDIRECT_URI, client_id=OAUTH_CLIENT_ID, code_verifier=verifier,
                ))
                body = require_status(token, 200, "token exchange").json()
                if not isinstance(body, dict) or not isinstance(body.get("access_token"), str) or not body["access_token"]:
                    raise PreparationError("OAuth token exchange: access_token отсутствует")
                return body["access_token"]
            path = local_path(client, location)
            response = client.request("GET", path)
            continue
        require_status(response, 200, "OAuth form")
        forms = Forms(response.body.decode()).forms
        login = next((f for f in forms if "username" in f["fields"] and "password" in f["fields"]), None)
        consent = next((f for f in forms if "client_id" in f["fields"] and "state" in f["fields"]), None)
        form = login or consent
        if form is None:
            raise PreparationError("OAuth: неизвестная форма login/consent")
        kind = "login" if login else "consent"
        if kind in submitted:
            raise PreparationError(f"OAuth: повторная форма {kind} после отправки")
        submitted.add(kind)
        fields = dict(form["fields"])
        fields["_csrf"] = csrf(client, fields)
        if login:
            fields.update(username=username, password=password)
        else:
            fields.update(client_id=OAUTH_CLIENT_ID, scope=OAUTH_SCOPE)
        response = client.request("POST", local_path(client, form["action"] or path), form=fields)
    raise PreparationError("OAuth: превышено число протокольных переходов")
