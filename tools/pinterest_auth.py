r"""One-time Pinterest login. Prints the refresh token and the ids of your boards for .env on the server.

Run on your PC, not on the server:
    .venv\Scripts\python tools\pinterest_auth.py

Before that, at developers.pinterest.com -> your app -> Redirect URIs add exactly:
    http://localhost:8085/
"""

import base64
import getpass
import http.server
import json
import secrets
import urllib.parse
import urllib.request
import webbrowser
from typing import Any

REDIRECT = "http://localhost:8085/"
SCOPES = "boards:read,pins:read"
API = "https://api.pinterest.com/v5"


def _wait_for_code(url: str, state: str) -> str:
    found: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if query.get("state") == [state] and query.get("code"):
                found["code"] = query["code"][0]
                body = "Готово, вкладку можно закрыть.".encode()
            else:
                body = "Что-то не так: нет кода или чужой state.".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:
            pass

    print("Открываю браузер. Если не открылся, перейди сам:\n" + url)
    webbrowser.open(url)
    with http.server.HTTPServer(("localhost", 8085), Handler) as server:
        while "code" not in found:
            server.handle_request()
    return found["code"]


def _post_token(app_id: str, secret: str, form: dict[str, str]) -> dict[str, Any]:
    auth = base64.b64encode(f"{app_id}:{secret}".encode()).decode()
    request = urllib.request.Request(
        f"{API}/oauth/token",
        data=urllib.parse.urlencode(form).encode(),
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return dict(json.load(response))


def _boards(token: str) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        f"{API}/boards?page_size=100", headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return list(json.load(response).get("items") or [])


def main() -> None:
    app_id = input("App ID: ").strip()
    secret = getpass.getpass("App secret (ввод не отображается): ").strip()
    state = secrets.token_urlsafe(16)
    query = {
        "client_id": app_id,
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
    }
    code = _wait_for_code("https://www.pinterest.com/oauth/?" + urllib.parse.urlencode(query), state)
    tokens = _post_token(
        app_id, secret, {"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT}
    )
    print("\nВпиши в /opt/sglypa/.env на сервере:\n")
    print(f"PINTEREST_APP_ID={app_id}")
    print("PINTEREST_APP_SECRET=<тот же секрет>")
    print(f"PINTEREST_REFRESH_TOKEN={tokens['refresh_token']}")
    print("PINTEREST_BOARD_ID=<id нужной доски из списка ниже>\n")
    for board in _boards(tokens["access_token"]):
        print(f"  {board['id']}  {board.get('name', '')}  ({board.get('privacy', '')})")


if __name__ == "__main__":
    main()
