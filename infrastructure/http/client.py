"""Один request — один HTTP-запрос, включая отрицательные ответы."""
import json
from dataclasses import dataclass
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPCookieProcessor, Request, build_opener


class PreparationError(RuntimeError):
    """Ошибка подготовки/транспорта без секретных URL и payload в сообщении."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: object

    def json(self):
        try:
            return json.loads(self.body)
        except (ValueError, UnicodeError):
            raise PreparationError("Ответ не содержит корректный JSON") from None


class HttpClient:
    def __init__(self, base_url, *, opener=None, timeout=15):
        parsed = urlsplit(base_url)
        try:
            parsed.port
        except ValueError:
            raise PreparationError("Невалидный порт HTTP origin") from None
        if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            raise PreparationError("Нужен HTTP(S) origin без credentials")
        self.base_url = base_url.rstrip("/")
        self.cookies = CookieJar()
        self.opener = opener or build_opener(HTTPCookieProcessor(self.cookies), NoRedirect())
        self.timeout = timeout

    def request(self, method, path, *, payload=None, form=None, headers=None):
        if not path.startswith("/") or path.startswith("//"):
            raise PreparationError("Разрешён только относительный путь HTTP-запроса")
        outgoing = dict(headers or {})
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            outgoing["Content-Type"] = "application/json"
        if form is not None:
            data = urlencode(form, doseq=True).encode()
            outgoing["Content-Type"] = "application/x-www-form-urlencoded"
        request = Request(self.base_url + path, data=data, headers=outgoing, method=method)
        try:
            response = self.opener.open(request, timeout=self.timeout)
        except HTTPError as error:
            response = error  # 3xx/4xx/5xx — данные, без повторного запроса.
        except (URLError, OSError, ValueError):
            raise PreparationError("HTTP-транспорт недоступен") from None
        with response:
            return HttpResponse(response.code, response.read(), response.headers)


class CategoriesApi:
    def __init__(self, client, token):
        self.client = client
        self.headers = {"Authorization": f"Bearer {token}"}

    def all(self):
        return self.client.request("GET", "/api/categories/all?excludeArchived=false", headers=self.headers)

    def add(self, category):
        return self.client.request("POST", "/api/categories/add", payload=category, headers=self.headers)

    def update(self, category):
        return self.client.request("PATCH", "/api/categories/update", payload=category, headers=self.headers)


def require_status(response, expected, step):
    if response.status != expected:
        raise PreparationError(f"{step}: ожидался HTTP {expected}, получен {response.status}")
    return response
