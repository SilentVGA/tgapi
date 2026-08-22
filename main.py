import asyncio
import uuid
import re
import os
import json
import shutil
import threading
from html import escape as html_escape
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError

ADMIN_PASSWORD = "admin123"
SERVER_PORT = 8000
SESSIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions")

OFFICIAL_CLIENT_API_ID = 2040
OFFICIAL_CLIENT_API_HASH = "b18441a1ff607e10a989891a5462e627"

DEFAULT_API_ID = OFFICIAL_CLIENT_API_ID
DEFAULT_API_HASH = OFFICIAL_CLIENT_API_HASH

os.makedirs(SESSIONS_DIR, exist_ok=True)

main_loop = asyncio.new_event_loop()
clients = {}
pending_logins = {}
client_locks = {}
file_lock = threading.RLock()

GETCODE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Verification Code</title>
<style>
:root {
    --bg1: #4f7cff;
    --bg2: #7a5cff;
    --card: #ffffff;
    --text: #1e2a3a;
    --muted: #7c8aa0;
    --line: #e3e9f2;
    --code-bg: #f5f8ff;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: linear-gradient(135deg, var(--bg1), var(--bg2));
    padding: 24px;
}
.card {
    width: 400px;
    max-width: 100%;
    background: var(--card);
    border-radius: 24px;
    box-shadow: 0 24px 64px rgba(20, 30, 90, 0.28);
    padding: 40px 36px 32px;
    text-align: center;
}
.badge {
    display: inline-block;
    font-size: 12px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--muted);
    background: #f1f4f9;
    border-radius: 999px;
    padding: 6px 14px;
    margin-bottom: 24px;
}
.code-label {
    font-size: 14px;
    color: var(--muted);
    margin-bottom: 10px;
}
.code {
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 52px;
    font-weight: 700;
    letter-spacing: 10px;
    text-indent: 10px;
    color: var(--text);
    background: var(--code-bg);
    border: 1.5px dashed #c8d4f0;
    border-radius: 16px;
    padding: 24px 8px;
    margin-bottom: 26px;
    user-select: all;
}
.code.waiting {
    font-size: 18px;
    letter-spacing: 1px;
    text-indent: 1px;
    color: #a5b1c6;
    font-weight: 500;
}
.divider {
    height: 1px;
    background: var(--line);
    margin: 0 0 20px;
}
.twofa-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: #f8fafc;
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 14px 18px;
    margin-bottom: 26px;
}
.twofa-label {
    font-size: 12px;
    color: var(--muted);
    letter-spacing: 2px;
    text-transform: uppercase;
}
.twofa-value {
    font-family: Consolas, Menlo, monospace;
    font-size: 18px;
    font-weight: 600;
    color: var(--text);
    user-select: all;
}
.refresh {
    display: inline-block;
    text-decoration: none;
    color: #ffffff;
    background: linear-gradient(135deg, var(--bg1), var(--bg2));
    border-radius: 999px;
    padding: 12px 36px;
    font-size: 15px;
    font-weight: 600;
    box-shadow: 0 8px 20px rgba(79, 124, 255, 0.35);
}
.refresh:hover { opacity: 0.92; }
</style>
</head>
<body>
<div class="card">
    <div class="badge">Telegram Code</div>
    <div class="code-label">Verification Code</div>
    __CODE__
    <div class="divider"></div>
    <div class="twofa-row">
        <span class="twofa-label">2FA Password</span>
        <span class="twofa-value">__2FA__</span>
    </div>
    <a class="refresh" href="/getcode/__ID__">Refresh</a>
</div>
</body>
</html>"""


def is_safe_account_id(value):
    return bool(re.fullmatch(r"[A-Za-z0-9_\-]+", value or ""))


def is_uuid(value):
    return bool(
        re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            value or "",
            re.IGNORECASE
        )
    )


def session_path(account_id):
    return os.path.join(SESSIONS_DIR, f"{account_id}.session")


def session_base(account_id):
    return os.path.join(SESSIONS_DIR, account_id)


def meta_path(account_id):
    return os.path.join(SESSIONS_DIR, f"{account_id}.meta.json")


def remove_session_files(base):
    for path in (base + ".session", base + ".session-journal"):
        try:
            os.remove(path)
        except Exception:
            pass


def cleanup_temporary_sessions():
    if not os.path.isdir(SESSIONS_DIR):
        return

    for name in os.listdir(SESSIONS_DIR):
        if (name.startswith("_tmp_") or name.startswith("_import_")) and (
            name.endswith(".session") or name.endswith(".session-journal")
        ):
            try:
                os.remove(os.path.join(SESSIONS_DIR, name))
            except Exception:
                pass


def load_meta(account_id):
    path = meta_path(account_id)

    if not os.path.exists(path):
        return None

    with file_lock:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None

    if not isinstance(data, dict):
        return None

    data.setdefault("phone", "")
    data.setdefault("api_id", DEFAULT_API_ID)
    data.setdefault("api_hash", DEFAULT_API_HASH)
    data.setdefault("password_2fa", "")
    data.setdefault("latest_code", "")
    data["id"] = account_id

    return data


def save_meta(account_id, meta):
    meta = dict(meta)
    meta.pop("id", None)

    clean = {
        "phone": str(meta.get("phone", "")),
        "api_id": meta.get("api_id", DEFAULT_API_ID),
        "api_hash": str(meta.get("api_hash", DEFAULT_API_HASH)),
        "password_2fa": str(meta.get("password_2fa", "")),
        "latest_code": str(meta.get("latest_code", ""))
    }

    try:
        clean["api_id"] = int(clean["api_id"] or DEFAULT_API_ID)
    except Exception:
        clean["api_id"] = DEFAULT_API_ID

    path = meta_path(account_id)

    with file_lock:
        tmp = path + ".tmp"

        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)

        os.replace(tmp, path)


def update_meta(account_id, **fields):
    meta = load_meta(account_id)

    if meta is None:
        return None

    meta.update(fields)
    save_meta(account_id, meta)

    return meta


def migrate_legacy_sessions():
    if not os.path.isdir(SESSIONS_DIR):
        return

    for name in os.listdir(SESSIONS_DIR):
        if not name.endswith(".session"):
            continue

        account_id = name[:-8]

        if account_id.startswith("_tmp_") or account_id.startswith("_import_"):
            continue

        if not is_safe_account_id(account_id):
            continue

        if is_uuid(account_id):
            continue

        new_id = str(uuid.uuid4())

        try:
            shutil.move(session_path(account_id), session_path(new_id))
        except Exception:
            continue

        old_meta = meta_path(account_id)

        if os.path.exists(old_meta):
            try:
                shutil.move(old_meta, meta_path(new_id))
            except Exception:
                pass
        else:
            save_meta(new_id, {
                "phone": account_id,
                "api_id": DEFAULT_API_ID,
                "api_hash": DEFAULT_API_HASH,
                "password_2fa": "",
                "latest_code": ""
            })

        remove_session_files(session_base(account_id))


def list_accounts():
    accounts = []

    if not os.path.isdir(SESSIONS_DIR):
        return accounts

    for name in sorted(os.listdir(SESSIONS_DIR)):
        if not name.endswith(".session"):
            continue

        account_id = name[:-8]

        if account_id.startswith("_tmp_") or account_id.startswith("_import_"):
            continue

        if not is_safe_account_id(account_id):
            continue

        meta = load_meta(account_id)

        if meta is None:
            meta = {
                "phone": "",
                "api_id": DEFAULT_API_ID,
                "api_hash": DEFAULT_API_HASH,
                "password_2fa": "",
                "latest_code": ""
            }

            save_meta(account_id, meta)
            meta["id"] = account_id

        accounts.append(meta)

    accounts.sort(key=lambda x: str(x.get("phone") or x.get("id") or ""))
    return accounts


def find_account_id_by_phone(phone):
    phone = str(phone or "").replace("+", "").strip()

    if not phone or not os.path.isdir(SESSIONS_DIR):
        return None

    for name in os.listdir(SESSIONS_DIR):
        if not name.endswith(".session"):
            continue

        account_id = name[:-8]

        if account_id.startswith("_tmp_") or account_id.startswith("_import_"):
            continue

        if not is_safe_account_id(account_id):
            continue

        meta = load_meta(account_id)

        if meta and str(meta.get("phone", "")) == phone:
            return account_id

    return None


def delete_account(account_id):
    with file_lock:
        for path in (
            session_path(account_id),
            session_path(account_id) + "-journal",
            meta_path(account_id)
        ):
            try:
                os.remove(path)
            except Exception:
                pass


def get_client_lock(account_id):
    if account_id not in client_locks:
        client_locks[account_id] = asyncio.Lock()

    return client_locks[account_id]


def create_client(base, api_id, api_hash):
    return TelegramClient(
        base,
        api_id,
        api_hash,
        device_model="Desktop",
        system_version="Windows 10",
        app_version="3.4.3 x64",
        lang_code="en",
        system_lang_code="en-US"
    )


def get_credentials(meta):
    api_id = DEFAULT_API_ID
    api_hash = DEFAULT_API_HASH

    if meta:
        try:
            api_id = int(meta.get("api_id") or DEFAULT_API_ID)
        except Exception:
            api_id = DEFAULT_API_ID

        api_hash = str(meta.get("api_hash") or DEFAULT_API_HASH)

    return api_id, api_hash


def parse_credentials(api_id_raw, api_hash_raw):
    api_id_raw = str(api_id_raw or "").strip()
    api_hash_raw = str(api_hash_raw or "").strip()

    if not api_id_raw and not api_hash_raw:
        return DEFAULT_API_ID, DEFAULT_API_HASH, None

    if not api_id_raw or not api_hash_raw:
        return None, None, "API_ID and API_HASH must be both empty or both filled."

    try:
        api_id = int(api_id_raw)
    except Exception:
        return None, None, "Invalid API_ID."

    return api_id, api_hash_raw, None


async def ensure_client(account_id):
    lock = get_client_lock(account_id)

    async with lock:
        if account_id in clients:
            client = clients[account_id]

            try:
                if client.is_connected() and await client.is_user_authorized():
                    return client
            except Exception:
                pass

            clients.pop(account_id, None)

        if not os.path.exists(session_path(account_id)):
            return None

        meta = load_meta(account_id)
        api_id, api_hash = get_credentials(meta)

        client = create_client(session_base(account_id), api_id, api_hash)

        try:
            await client.connect()

            if not await client.is_user_authorized():
                await client.disconnect()
                return None

            clients[account_id] = client

            @client.on(events.NewMessage)
            async def handler(event):
                try:
                    if event.chat_id in (777000, 42777, 424000, 42400, 33300, 22222):
                        text = event.message.message or ""
                        match = re.search(r"\b(\d{5,6})\b", text)

                        if match:
                            update_meta(account_id, latest_code=match.group(1))
                except Exception:
                    pass

            main_loop.create_task(client.run_until_disconnected())

            async def monitor_disconnect():
                try:
                    await client.disconnected
                except Exception:
                    pass

                clients.pop(account_id, None)

            main_loop.create_task(monitor_disconnect())

            return client

        except Exception:
            try:
                await client.disconnect()
            except Exception:
                pass

            return None


def parse_multipart(body, content_type):
    fields = {}
    files = {}

    if not body or not content_type or "boundary=" not in content_type:
        return fields, files

    boundary = content_type.split("boundary=")[-1].strip().strip('"')

    if not boundary:
        return fields, files

    delimiter = b"--" + boundary.encode("utf-8")
    parts = body.split(delimiter)

    for part in parts:
        if not part:
            continue

        part = part.lstrip(b"\r\n")

        if part.startswith(b"--"):
            continue

        if part.endswith(b"\r\n"):
            part = part[:-2]

        if b"\r\n\r\n" not in part:
            continue

        header_blob, content = part.split(b"\r\n\r\n", 1)

        if content.endswith(b"\r\n"):
            content = content[:-2]

        headers = {}

        for line in header_blob.split(b"\r\n"):
            if b":" in line:
                k, v = line.split(b":", 1)
                headers[k.strip().lower().decode("latin-1", "ignore")] = v.strip().decode("latin-1", "ignore")

        disp = headers.get("content-disposition", "")

        if 'name="' not in disp:
            continue

        try:
            name = disp.split('name="')[1].split('"')[0]
        except Exception:
            continue

        if 'filename="' in disp:
            try:
                filename = disp.split('filename="')[1].split('"')[0]
            except Exception:
                filename = ""

            files[name] = {
                "filename": filename,
                "content": content
            }
        else:
            fields[name] = content.decode("utf-8", "ignore")

    return fields, files


def get_first(container, key, default=""):
    value = container.get(key, default)

    if isinstance(value, list):
        return value[0] if value else default

    if value is None:
        return default

    return value


class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def _send_html(self, code, html):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _redirect(self, url, cookie=None):
        self.send_response(302)
        self.send_header("Location", url)

        if cookie:
            self.send_header("Set-Cookie", cookie)

        self.end_headers()

    def _get_base_url(self):
        host = self.headers.get("Host", f"localhost:{SERVER_PORT}")
        proto = self.headers.get("X-Forwarded-Proto", "http")

        return f"{proto}://{host}"

    def _admin_logged_in(self):
        return "admin_session=valid" in self.headers.get("Cookie", "")

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/admin/login":
            html = """
<html>
<body>
<h3>Admin Login</h3>
<form method="post" action="/admin/auth">
Password: <input type="password" name="pwd">
<input type="submit" value="Enter">
</form>
</body>
</html>
"""
            self._send_html(200, html)
            return

        if path.startswith("/getcode/"):
            account_id = path.split("/")[-1]

            if not is_safe_account_id(account_id):
                self._send_html(404, "Not found")
                return

            meta = load_meta(account_id)

            if meta is None or not os.path.exists(session_path(account_id)):
                self._send_html(404, "Not found")
                return

            async def prepare_page():
                await ensure_client(account_id)

            future = asyncio.run_coroutine_threadsafe(prepare_page(), main_loop)

            try:
                future.result(timeout=10)
            except Exception:
                pass

            meta = load_meta(account_id) or meta

            code = str(meta.get("latest_code", ""))
            twofa = str(meta.get("password_2fa", "")) or "None"

            if code:
                code_html = f'<div class="code">{html_escape(code)}</div>'
            else:
                code_html = '<div class="code waiting">Waiting for code...</div>'

            html = (
                GETCODE_TEMPLATE
                .replace("__CODE__", code_html)
                .replace("__2FA__", html_escape(twofa))
                .replace("__ID__", html_escape(account_id, quote=True))
            )

            self._send_html(200, html)
            return

        if path == "/admin/logout":
            self._redirect(
                "/admin/login",
                "admin_session=; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/"
            )
            return

        if path == "/admin":
            if not self._admin_logged_in():
                self._redirect("/admin/login")
                return

            base_url = self._get_base_url()
            accounts = list_accounts()

            items = ""

            for meta in accounts:
                account_id = str(meta.get("id", ""))
                phone = str(meta.get("phone", ""))
                code = str(meta.get("latest_code", ""))

                copy_value = f"+{phone}--{base_url}/getcode/{account_id}" if phone else f"{base_url}/getcode/{account_id}"

                safe_id = html_escape(account_id, quote=True)
                safe_phone = html_escape(phone or account_id)
                safe_code = html_escape(code)
                safe_copy = html_escape(copy_value, quote=True)

                items += f"""
<div>
<input id="copy-{safe_id}" size="80" readonly value="{safe_copy}">
<button type="button" onclick="copyText('copy-{safe_id}')">Copy</button>
<button type="button" onclick="window.open('/getcode/{safe_id}', '_blank')" style="color:blue;">Go</button>
<form method="post" action="/admin/delete/{safe_id}" style="display:inline;">
<button type="submit">Delete</button>
</form>
<br>
Phone: {safe_phone} | Code: {safe_code}
</div>
<br>
"""

            copy_script = """
<script>
function copyText(id) {
    var e = document.getElementById(id);
    e.select();
    e.setSelectionRange(0, 99999);
    document.execCommand("copy");
}
</script>
"""

            html = f"""
<html>
<body>
{copy_script}

<h2>Admin Panel</h2>

<h3>Add New Account</h3>
<form method="post" action="/admin/send_code">
Phone: <input name="phone">
API_ID: <input name="api_id" value="{OFFICIAL_CLIENT_API_ID}"> (official client)
API_HASH: <input name="api_hash" value="{OFFICIAL_CLIENT_API_HASH}"> (official client)
<input type="submit" value="Send Code">
</form>

<h3>Import .session File</h3>
<form method="post" action="/admin/import_session" enctype="multipart/form-data">
Session file: <input type="file" name="session_file" accept=".session"><br>
Phone (optional): <input name="phone"><br>
API_ID (optional): <input name="api_id" placeholder="{OFFICIAL_CLIENT_API_ID}"> (official client default)<br>
API_HASH (optional): <input name="api_hash" placeholder="official"> (official client default)<br>
2FA password (optional): <input type="password" name="password_2fa"><br>
<input type="submit" value="Import">
</form>

<h3>Accounts ({len(accounts)})</h3>
{items}

<a href="/admin/logout">Logout</a>
</body>
</html>
"""
            self._send_html(200, html)
            return

        self._redirect("/admin")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length > 0 else b""

        path = urlparse(self.path).path
        content_type = self.headers.get("Content-Type", "")

        if "multipart/form-data" in content_type:
            fields, files = parse_multipart(body, content_type)
            data = fields
        else:
            data = parse_qs(body.decode("utf-8", "ignore")) if body else {}
            files = {}

        if path == "/admin/auth":
            pwd = get_first(data, "pwd", "")

            if pwd == ADMIN_PASSWORD:
                self._redirect("/admin", "admin_session=valid; Path=/; HttpOnly")
            else:
                self._send_html(200, "Wrong password. <a href='/admin/login'>Back</a>")

            return

        if not self._admin_logged_in():
            self._redirect("/admin/login")
            return

        if path == "/admin/send_code":
            phone = get_first(data, "phone", "").strip()

            api_id, api_hash, error = parse_credentials(
                get_first(data, "api_id", ""),
                get_first(data, "api_hash", "")
            )

            if not phone:
                self._send_html(200, "Missing phone. <a href='/admin'>Back</a>")
                return

            if error:
                self._send_html(200, f"{html_escape(error)} <a href='/admin'>Back</a>")
                return

            async def _send_code():
                tmp_base = os.path.join(SESSIONS_DIR, f"_tmp_{uuid.uuid4().hex}")
                client = create_client(tmp_base, api_id, api_hash)

                try:
                    await client.connect()
                    result = await client.send_code_request(phone)

                    old = pending_logins.get(phone)

                    if old:
                        try:
                            await old["client"].disconnect()
                        except Exception:
                            pass

                        remove_session_files(old["tmp_base"])

                    pending_logins[phone] = {
                        "client": client,
                        "hash": result.phone_code_hash,
                        "api_id": api_id,
                        "api_hash": api_hash,
                        "tmp_base": tmp_base
                    }

                    return f"""
<html>
<body>
<h3>Enter Code for {html_escape(phone)}</h3>
<form method="post" action="/admin/verify">
<input type="hidden" name="phone" value="{html_escape(phone, quote=True)}">
Code: <input name="code"><br><br>
2FA Password: <input type="password" name="password"><br><br>
<input type="submit" value="Login">
</form>
<br>
<a href="/admin">Back</a>
</body>
</html>
"""

                except Exception as e:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass

                    remove_session_files(tmp_base)

                    return f"Error: {html_escape(str(e))}. <a href='/admin'>Back</a>"

            future = asyncio.run_coroutine_threadsafe(_send_code(), main_loop)

            try:
                html = future.result(timeout=30)
            except Exception as e:
                html = f"Timeout: {html_escape(str(e))}. <a href='/admin'>Back</a>"

            self._send_html(200, html)
            return

        if path == "/admin/verify":
            phone = get_first(data, "phone", "").strip()
            code = get_first(data, "code", "").strip()
            pwd = get_first(data, "password", "")

            pending = pending_logins.get(phone)

            if not pending:
                self._send_html(200, "Session expired. <a href='/admin'>Back</a>")
                return

            async def _verify():
                client = pending["client"]
                tmp_base = pending["tmp_base"]

                try:
                    await client.sign_in(phone, code, phone_code_hash=pending["hash"])
                except SessionPasswordNeededError:
                    if not pwd:
                        try:
                            await client.disconnect()
                        except Exception:
                            pass

                        remove_session_files(tmp_base)
                        pending_logins.pop(phone, None)

                        return "2FA password required. <a href='/admin'>Back</a>"

                    try:
                        await client.sign_in(password=pwd)
                    except Exception as e:
                        try:
                            await client.disconnect()
                        except Exception:
                            pass

                        remove_session_files(tmp_base)
                        pending_logins.pop(phone, None)

                        return f"2FA failed: {html_escape(str(e))}. <a href='/admin'>Back</a>"

                except Exception as e:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass

                    remove_session_files(tmp_base)
                    pending_logins.pop(phone, None)

                    return f"Code failed: {html_escape(str(e))}. <a href='/admin'>Back</a>"

                try:
                    client.session.save()
                    me = await client.get_me()
                    real_phone = getattr(me, "phone", "") or phone
                    await client.disconnect()
                except Exception as e:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass

                    remove_session_files(tmp_base)
                    pending_logins.pop(phone, None)

                    return f"Save session failed: {html_escape(str(e))}. <a href='/admin'>Back</a>"

                clean_phone = str(real_phone).replace("+", "").strip()
                existing_id = find_account_id_by_phone(clean_phone)
                account_id = existing_id or str(uuid.uuid4())

                if not is_safe_account_id(account_id):
                    account_id = str(uuid.uuid4())

                old_client = clients.pop(account_id, None)

                if old_client:
                    try:
                        await old_client.disconnect()
                    except Exception:
                        pass

                delete_account(account_id)

                try:
                    shutil.move(tmp_base + ".session", session_path(account_id))
                except Exception as e:
                    remove_session_files(tmp_base)
                    pending_logins.pop(phone, None)

                    return f"Move session failed: {html_escape(str(e))}. <a href='/admin'>Back</a>"

                remove_session_files(tmp_base)

                save_meta(account_id, {
                    "phone": clean_phone,
                    "api_id": pending["api_id"],
                    "api_hash": pending["api_hash"],
                    "password_2fa": pwd,
                    "latest_code": ""
                })

                pending_logins.pop(phone, None)

                return f"""
<html>
<head>
<meta http-equiv="refresh" content="0;url=/admin">
</head>
<body>
Login success.<br>
Phone: {html_escape(clean_phone)}<br>
Session: sessions/{html_escape(account_id)}.session<br>
<a href="/admin">Back</a>
</body>
</html>
"""

            future = asyncio.run_coroutine_threadsafe(_verify(), main_loop)

            try:
                html = future.result(timeout=60)
            except Exception as e:
                html = f"Timeout: {html_escape(str(e))}. <a href='/admin'>Back</a>"

            self._send_html(200, html)
            return

        if path == "/admin/import_session":
            if "session_file" not in files or not files["session_file"]["content"]:
                self._send_html(200, "No file uploaded. <a href='/admin'>Back</a>")
                return

            file_content = files["session_file"]["content"]

            if not file_content.startswith(b"SQLite format 3"):
                self._send_html(
                    200,
                    "Invalid file. Native Telethon .session file is required. <a href='/admin'>Back</a>"
                )
                return

            phone_input = get_first(data, "phone", "").strip()
            pwd_input = get_first(data, "password_2fa", "")

            api_id, api_hash, error = parse_credentials(
                get_first(data, "api_id", ""),
                get_first(data, "api_hash", "")
            )

            if error:
                self._send_html(200, f"{html_escape(error)} <a href='/admin'>Back</a>")
                return

            async def _import():
                tmp_base = os.path.join(SESSIONS_DIR, f"_import_{uuid.uuid4().hex}")

                try:
                    with open(tmp_base + ".session", "wb") as f:
                        f.write(file_content)
                except Exception as e:
                    return f"Write file failed: {html_escape(str(e))}. <a href='/admin'>Back</a>"

                client = create_client(tmp_base, api_id, api_hash)

                try:
                    await client.connect()

                    if not await client.is_user_authorized():
                        raise Exception("session is invalid or unauthorized")

                    client.session.save()
                    me = await client.get_me()
                    real_phone = getattr(me, "phone", "") or phone_input
                    await client.disconnect()

                except Exception as e:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass

                    remove_session_files(tmp_base)

                    return f"Import failed: {html_escape(str(e))}. <a href='/admin'>Back</a>"

                clean_phone = str(real_phone).replace("+", "").strip()
                existing_id = find_account_id_by_phone(clean_phone)
                account_id = existing_id or str(uuid.uuid4())

                if not is_safe_account_id(account_id):
                    account_id = str(uuid.uuid4())

                old_client = clients.pop(account_id, None)

                if old_client:
                    try:
                        await old_client.disconnect()
                    except Exception:
                        pass

                delete_account(account_id)

                try:
                    shutil.move(tmp_base + ".session", session_path(account_id))
                except Exception as e:
                    remove_session_files(tmp_base)

                    return f"Move session failed: {html_escape(str(e))}. <a href='/admin'>Back</a>"

                remove_session_files(tmp_base)

                save_meta(account_id, {
                    "phone": clean_phone,
                    "api_id": api_id,
                    "api_hash": api_hash,
                    "password_2fa": pwd_input,
                    "latest_code": ""
                })

                return f"""
<html>
<head>
<meta http-equiv="refresh" content="0;url=/admin">
</head>
<body>
Import success.<br>
Phone: {html_escape(clean_phone)}<br>
Session: sessions/{html_escape(account_id)}.session<br>
<a href="/admin">Back</a>
</body>
</html>
"""

            future = asyncio.run_coroutine_threadsafe(_import(), main_loop)

            try:
                html = future.result(timeout=60)
            except Exception as e:
                html = f"Timeout: {html_escape(str(e))}. <a href='/admin'>Back</a>"

            self._send_html(200, html)
            return

        if path.startswith("/admin/delete/"):
            account_id = path.split("/")[-1]

            if not is_safe_account_id(account_id):
                self._redirect("/admin")
                return

            client = clients.pop(account_id, None)

            if client:
                future = asyncio.run_coroutine_threadsafe(client.disconnect(), main_loop)

                try:
                    future.result(timeout=5)
                except Exception:
                    pass

            delete_account(account_id)
            self._redirect("/admin")
            return

        self._redirect("/admin")


def start_server():
    migrate_legacy_sessions()
    cleanup_temporary_sessions()

    server = ThreadingHTTPServer(("0.0.0.0", SERVER_PORT), Handler)
    print(f"Server running on port {SERVER_PORT}")
    print(f"Sessions directory: {os.path.abspath(SESSIONS_DIR)}")
    server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.set_event_loop(main_loop)

        server_thread = threading.Thread(target=start_server, daemon=True)
        server_thread.start()

        main_loop.run_forever()
    except KeyboardInterrupt:
        print("Shutting down...")
