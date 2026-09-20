import asyncio
import uuid
import re
import os
import json
import shutil
import threading
import time
import secrets
import zipfile
import io
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

CALLING_CODES = tuple(sorted({
    "1", "7",
    "20", "27", "30", "31", "32", "33", "34", "36", "39",
    "40", "41", "43", "44", "45", "46", "47", "48", "49",
    "51", "52", "53", "54", "55", "56", "57", "58",
    "60", "61", "62", "63", "64", "65", "66",
    "81", "82", "84", "86", "90", "91", "92", "93", "94", "95", "98",
    "211", "212", "213", "216", "218", "220", "221", "222", "223", "224", "225",
    "226", "227", "228", "229", "230", "231", "232", "233", "234", "235", "236",
    "237", "238", "239", "240", "241", "242", "243", "244", "245", "246", "248",
    "249", "250", "251", "252", "253", "254", "255", "256", "257", "258", "260",
    "261", "262", "263", "264", "265", "266", "267", "268", "269",
    "290", "291", "297", "298", "299",
    "350", "351", "352", "353", "354", "355", "356", "357", "358", "359",
    "370", "371", "372", "373", "374", "375", "376", "377", "378", "380",
    "381", "382", "383", "385", "386", "387", "389",
    "420", "421", "423",
    "500", "501", "502", "503", "504", "505", "506", "507", "508", "509",
    "590", "591", "592", "593", "594", "595", "596", "597", "598", "599",
    "670", "672", "673", "674", "675", "676", "677", "678", "679",
    "680", "681", "682", "683", "685", "686", "687", "688", "689",
    "690", "691", "692",
    "850", "852", "853", "855", "856", "880", "886",
    "960", "961", "962", "963", "964", "965", "966", "967", "968",
    "970", "971", "972", "973", "974", "975", "976", "977",
    "992", "993", "994", "995", "996", "998"
}, key=lambda item: (-len(item), item)))

SETTINGS_PATH = os.path.join(SESSIONS_DIR, "settings.json")

os.makedirs(SESSIONS_DIR, exist_ok=True)

main_loop = asyncio.new_event_loop()
clients = {}
pending_logins = {}
# Temporary uploaded sessions waiting for the filename-option confirmation page.
pending_imports = {}
pending_imports_lock = threading.Lock()
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
*{box-sizing:border-box}html,body{margin:0;padding:0;min-height:100%;background:var(--bg);color:var(--text);font-family:Inter,system-ui,-apple-system,"Segoe UI",Arial,sans-serif}body{min-height:100vh}body.admin{padding:0;display:block}.container{width:100%;max-width:460px;margin:0 auto;padding:24px}.container.wide{max-width:none;padding:0}.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:20px}h1{font-size:22px;margin:0 0 20px}h2{font-size:15px;margin:0 0 14px}.label{font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);margin:0 0 7px;font-weight:700}.value{border:1px solid var(--line);background:var(--panel2);border-radius:10px;padding:11px;min-height:44px;display:flex;align-items:center;justify-content:center;word-break:break-all;font-family:ui-monospace,monospace}.status{font-size:13px;color:var(--muted);text-align:center;margin:12px 0}.status.error{color:var(--danger);font-weight:700}.status.ok{color:var(--success);font-weight:700}.actions,.item-actions{display:flex;gap:8px;flex-wrap:wrap}.button,button,input[type="submit"]{appearance:none;border:1px solid var(--line);background:var(--panel2);color:var(--text);border-radius:9px;padding:9px 13px;font-size:13px;font-weight:650;text-decoration:none;cursor:pointer;transition:.15s}.button:hover,button:hover{border-color:var(--accent);transform:translateY(-1px)}.button.primary,button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}.button.danger,button.danger{color:var(--danger);background:transparent;border-color:var(--danger)}.input,input[type="text"],input[type="password"],input[type="file"],input[type="number"],select{width:100%;border:1px solid var(--line);border-radius:9px;padding:10px 11px;font-size:13px;background:var(--input);color:var(--text);margin:0 0 12px}input:focus,select:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 16%,transparent)}form{margin:0}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}.small{font-size:12px;color:var(--muted);word-break:break-all}.inline-form{display:inline-flex}.tag-form{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.tag-form input{margin:0;flex:1;min-width:130px}.dashboard{display:grid;grid-template-columns:240px minmax(0,1fr);min-height:100vh}.sidebar{border-right:1px solid var(--line);background:var(--sidebar);padding:22px 14px;position:sticky;top:0;height:100vh}.brand{padding:8px 12px 24px;font-weight:800;font-size:20px;letter-spacing:.08em}.brand small{display:block;color:var(--muted);font-size:10px;letter-spacing:.14em;margin-top:5px}.nav-label{color:var(--muted);font-size:10px;font-weight:800;letter-spacing:.14em;padding:10px 12px}.nav-item{display:flex;align-items:center;gap:10px;padding:11px 12px;border-radius:9px;color:var(--muted);text-decoration:none;font-size:13px;margin:3px 0}.nav-item:hover,.nav-item.active{background:var(--panel2);color:var(--text)}.sidebar-bottom{position:absolute;bottom:20px;left:14px;right:14px}.main{padding:28px;max-width:1450px;width:100%;margin:0 auto}.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:26px}.topbar h1{margin:0;font-size:25px}.subtitle{font-size:13px;color:var(--muted);margin-top:5px}.live{display:flex;align-items:center;gap:8px;color:var(--success);font-size:12px;font-weight:700}.dot{width:8px;height:8px;border-radius:50%;background:var(--success);box-shadow:0 0 12px var(--success)}.stats{display:grid;grid-template-columns:minmax(180px,320px);gap:14px;margin-bottom:18px}.stat{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px}.stat-value{font-size:28px;font-weight:800;margin-top:8px}.admin-grid{display:grid;grid-template-columns:minmax(320px,1fr) minmax(320px,1fr);gap:16px;margin-bottom:18px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px}.panel-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.panel-title{font-size:15px;font-weight:800}.panel-desc{font-size:12px;color:var(--muted);margin-top:4px}.accounts-head{display:flex;justify-content:space-between;align-items:center;margin:22px 0 12px}.accounts-list{display:grid;grid-template-columns:1fr;gap:12px}.item{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;word-break:break-all}.item-top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.item-phone{font-size:16px;font-weight:800}.item-code{font-family:ui-monospace,monospace;background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:9px 10px;margin:13px 0}.account-meta{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin:10px 0 14px}.account-meta .small{background:var(--panel2);border-radius:7px;padding:7px}.switch-row{display:flex;align-items:center;justify-content:space-between;gap:12px;border-top:1px solid var(--line);padding-top:13px;margin-top:12px}.switch{position:relative;display:inline-block;width:42px;height:23px}.switch input{opacity:0;width:0;height:0}.slider{position:absolute;inset:0;background:#8b95a7;border-radius:20px;cursor:pointer}.slider:before{content:"";position:absolute;width:17px;height:17px;left:3px;top:3px;background:#fff;border-radius:50%;transition:.2s}.switch input:checked+.slider{background:var(--success)}.switch input:checked+.slider:before{transform:translateX(19px)}@media(max-width:900px){.dashboard{grid-template-columns:1fr}.sidebar{position:static;height:auto;border-right:0;border-bottom:1px solid var(--line);padding:10px 12px;display:block}.brand{padding:5px 10px 10px}.brand small,.nav-label{display:none}.nav{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px}.nav-item{white-space:normal;justify-content:center;text-align:center;margin:0;padding:10px 8px}.sidebar-bottom{position:static;margin-top:5px}.sidebar-bottom .nav-item{width:100%}.main{padding:18px}.stats,.admin-grid{grid-template-columns:1fr}.accounts-list{grid-template-columns:1fr}}.form-panel{max-width:900px}.bulk-panel{margin:18px 0}.bulk-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px;margin:12px 0}.bulk-option{display:flex;align-items:center;gap:9px;border:1px solid var(--line);background:var(--panel2);padding:10px;border-radius:9px;font-size:13px}.bulk-option input{width:auto;margin:0}.bulk-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}@media(max-width:640px){.topbar{align-items:flex-start;gap:10px}.row{grid-template-columns:1fr}.account-meta{grid-template-columns:1fr}.item-top{flex-direction:column}.topbar h1{font-size:21px}}.admin-grid .form-panel{max-width:none}.accounts-toolbar{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:flex-end;margin:0 0 16px}.code-filters{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 16px}.code-chip{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:999px;padding:7px 12px;font-size:12px;font-weight:650;text-decoration:none}.code-chip:hover,.code-chip.active{border-color:var(--text)}.code-chip .n{color:var(--muted)}.accounts-toolbar .button,.accounts-toolbar button,.item-actions .button,.item-actions button,.item-actions .button.danger,.item-actions button.danger,.accounts-toolbar .button.primary,.accounts-toolbar button.primary{background:var(--panel);color:var(--text);border-color:var(--line)}.random-field{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.random-field input[type="number"]{width:96px;margin:0}.item-check{display:flex;align-items:flex-start;gap:12px}.item-check>input{width:auto;margin:6px 0 0}.tag-list,.download-list{display:flex;flex-direction:column;gap:8px}.tag-row{display:grid;grid-template-columns:minmax(140px,240px) minmax(0,1fr);gap:10px;align-items:center;border:1px solid var(--line);background:var(--panel2);border-radius:9px;padding:10px}.tag-row input{margin:0}.select-all-row{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:650}.select-all-row input{width:auto;margin:0}@media(max-width:640px){.tag-row{grid-template-columns:1fr}.accounts-toolbar{align-items:flex-start}}
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

ADMIN_TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>__TITLE__ · TGAPI</title><style>__STYLE__</style></head><body class="admin"><div class="dashboard"><aside class="sidebar"><div class="brand">TGAPI<small>SESSION CONTROL PANEL</small></div><div class="nav-label">MANAGEMENT</div><nav class="nav"><a class="nav-item __DASH_ACTIVE__" href="/admin">Dashboard</a><a class="nav-item __ACCOUNTS_ACTIVE__" href="/admin/accounts">Accounts</a><a class="nav-item __ADD_ACTIVE__" href="/admin/add_account">Add Account</a><a class="nav-item __DOWNLOAD_ACTIVE__" href="/admin/session_download_page">Session Download</a><a class="nav-item __TAGS_ACTIVE__" href="/admin/tags">Tags</a></nav><div class="sidebar-bottom"><a class="nav-item" href="/admin/logout">Logout</a></div></aside><main class="main">__CONTENT__</main></div>__SCRIPT__</body></html>"""

LOGIN_PANEL = """<section class="panel form-panel"><div class="panel-head"><div><div class="panel-title">Account Login</div><div class="panel-desc">Choose an API platform, enter a phone number, then verify the Telegram login code.</div></div></div><form method="post" action="/admin/send_code"><div class="row"><div><div class="label">Phone</div><input type="text" name="phone" required></div><div><div class="label">API Platform</div><select class="platform-select" name="platform" onchange="updatePlatformInfo(this)">__PLATFORM_OPTIONS__</select><div class="small platform-info"></div></div></div><div class="row custom-api-fields"><div><div class="label">API_ID</div><input type="text" name="api_id" value="__API_ID_VALUE__" placeholder="Custom API_ID"></div><div><div class="label">API_HASH</div><input type="text" name="api_hash" value="__API_HASH_VALUE__" placeholder="Custom API_HASH"></div></div><div class="label">Tag</div><input type="text" name="tag" placeholder="optional"><div class="actions"><button class="primary" type="submit">Send Verification Code</button></div></form></section>"""

IMPORT_PANEL = """<section class="panel form-panel"><div class="panel-head"><div><div class="panel-title">Session Import</div><div class="panel-desc">Upload a native Telethon SQLite .session file or a ZIP. After upload, the filename is parsed on the next page.</div></div></div><form method="post" action="/admin/import_session" enctype="multipart/form-data"><div class="label">Session File or ZIP</div><input type="file" name="session_file" required><div class="small">Expected filename: +countrycode-number-2fa-apiid-apihash-tag.session</div><div class="actions"><button class="primary" type="submit">Upload and Continue</button></div></form></section>"""

IMPORT_REVIEW_TEMPLATE = """<section class="panel form-panel"><div class="panel-head"><div><div class="panel-title">Import Session Options</div><div class="panel-desc">Select which parts of the filename should be used. If unchecked, you may enter a custom value or leave Phone, 2FA, or Tag empty. API credentials must still be supplied through a platform or custom API.</div></div></div>
<form method="post" action="/admin/import_session_review">
<input type="hidden" name="token" value="__TOKEN__">
<div class="bulk-list">
<label class="bulk-option"><input type="checkbox" name="use_phone" value="1" checked onchange="toggleImportCustom()"> Phone</label>
<label class="bulk-option"><input type="checkbox" name="use_2fa" value="1" checked onchange="toggleImportCustom()"> 2FA</label>
<label class="bulk-option"><input type="checkbox" name="use_api" value="1" checked onchange="toggleImportCustom()"> API</label>
<label class="bulk-option"><input type="checkbox" name="use_tag" value="1" checked onchange="toggleImportCustom()"> Tag</label>
</div>
<div class="panel" style="margin:14px 0">
<div class="label">Filename values</div>
<div class="small">__FILES__</div>
</div>
<div class="row">
<div class="import-custom-phone"><div class="label">Custom Phone</div><input type="text" name="phone" placeholder="Leave empty to use the phone stored in the session"></div>
<div class="import-custom-2fa"><div class="label">Custom 2FA</div><input type="password" name="password_2fa" placeholder="Optional"></div>
</div>
<div class="row">
<div class="import-custom-tag"><div class="label">Custom Tag</div><input type="text" name="tag" placeholder="Optional"></div>
<div class="import-api-settings"><div class="label">API Platform (when API is unchecked)</div><select class="platform-select" name="platform" onchange="updatePlatformInfo(this)">__PLATFORM_OPTIONS__</select><div class="small platform-info"></div></div>
</div>
<div class="row custom-api-fields import-api-settings">
<div><div class="label">API_ID</div><input type="text" name="api_id" value="__API_ID_VALUE__" placeholder="Custom API_ID"></div>
<div><div class="label">API_HASH</div><input type="text" name="api_hash" value="__API_HASH_VALUE__" placeholder="Custom API_HASH"></div>
</div>
<div class="actions"><button class="primary" type="submit">Import Sessions</button><a class="button" href="/admin/add_account">Cancel</a></div>
</form></section>"""

IMPORT_REVIEW_SCRIPT = """<script>
function toggleImportCustom() {
    var usePhone = document.querySelector('input[name="use_phone"]');
    var use2fa = document.querySelector('input[name="use_2fa"]');
    var useApi = document.querySelector('input[name="use_api"]');
    var useTag = document.querySelector('input[name="use_tag"]');
    var phone = document.querySelector('.import-custom-phone');
    var twofa = document.querySelector('.import-custom-2fa');
    var api = document.querySelectorAll('.import-api-settings');
    var tag = document.querySelector('.import-custom-tag');
    if (phone) phone.style.display = usePhone && usePhone.checked ? 'none' : 'block';
    if (twofa) twofa.style.display = use2fa && use2fa.checked ? 'none' : 'block';
    if (tag) tag.style.display = useTag && useTag.checked ? 'none' : 'block';
    for (var i = 0; i < api.length; i++) api[i].style.display = useApi && useApi.checked ? 'none' : 'block';
}
document.addEventListener("DOMContentLoaded", toggleImportCustom);
</script>"""

ADD_ACCOUNT_CONTENT = """<div class="topbar"><div><h1>Add Account</h1><div class="subtitle">Create a local Telethon session or import an existing session file.</div></div><div class="live"><span class="dot"></span> Server online</div></div><div class="admin-grid">__LOGIN_PANEL____IMPORT_PANEL__</div>"""

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

ACCOUNTS_SCRIPT = """<script>
function pageOrigin() {
    try {
        return window.location.origin || "";
    } catch (e) {
        return "";
    }
}
function applyPageOrigin(key) {
    var origin = pageOrigin();
    if (!key || !origin) {
        return key;
    }
    var marker = "/getcode/";
    var pathIdx = key.indexOf(marker);
    if (pathIdx < 0) {
        return key;
    }
    var prefix = key.slice(0, pathIdx);
    var sep = prefix.lastIndexOf("--");
    if (sep >= 0) {
        return prefix.slice(0, sep + 2) + origin + key.slice(pathIdx);
    }
    return origin + key.slice(pathIdx);
}
function rewriteKeyAttributes() {
    var nodes = document.querySelectorAll("[data-key], [data-copy]");
    for (var i = 0; i < nodes.length; i++) {
        var key = nodes[i].getAttribute("data-key");
        var copy = nodes[i].getAttribute("data-copy");
        if (key) {
            nodes[i].setAttribute("data-key", applyPageOrigin(key));
        }
        if (copy) {
            nodes[i].setAttribute("data-copy", applyPageOrigin(copy));
        }
    }
    var hidden = document.getElementById("page-origin");
    if (hidden) {
        hidden.value = pageOrigin();
    }
}
function selectedAccountBoxes() {
    return Array.prototype.slice.call(document.querySelectorAll("#account-items input[name=\\"account_ids\\"]:checked"));
}
function copySelectedKeys() {
    var boxes = selectedAccountBoxes();
    var lines = [];
    for (var i = 0; i < boxes.length; i++) {
        var key = applyPageOrigin(boxes[i].getAttribute("data-key"));
        if (key) {
            lines.push(key);
        }
    }
    if (!lines.length) {
        return;
    }
    copyText(lines.join("\\n"));
}
function randomSelect() {
    var input = document.getElementById("random-count");
    var n = parseInt(input && input.value ? input.value : "0", 10);
    var boxes = document.querySelectorAll("#account-items input[name=\\"account_ids\\"]");
    if (!boxes.length) {
        return;
    }
    if (isNaN(n) || n < 0) {
        n = 0;
    }
    if (n > boxes.length) {
        n = boxes.length;
    }
    var idx = [];
    for (var i = 0; i < boxes.length; i++) {
        boxes[i].checked = false;
        idx.push(i);
    }
    for (var i = idx.length - 1; i > 0; i--) {
        var j = Math.floor(Math.random() * (i + 1));
        var tmp = idx[i];
        idx[i] = idx[j];
        idx[j] = tmp;
    }
    for (var i = 0; i < n; i++) {
        boxes[idx[i]].checked = true;
    }
}
function toggleAll(src) {
    var boxes = document.querySelectorAll("#account-items input[name=\\"account_ids\\"]");
    for (var i = 0; i < boxes.length; i++) {
        boxes[i].checked = src.checked;
    }
}
function toggleDownloadAll(src) {
    var boxes = document.querySelectorAll("#download-settings-form input[name=\\"account_ids\\"]");
    for (var i = 0; i < boxes.length; i++) {
        boxes[i].checked = src.checked;
    }
}
document.addEventListener("DOMContentLoaded", function() {
    rewriteKeyAttributes();
    var form = document.getElementById("bulk-form");
    if (form) {
        form.addEventListener("submit", function() {
            var hidden = document.getElementById("page-origin");
            if (hidden) {
                hidden.value = pageOrigin();
            }
        });
    }
});
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
    phone = stored_phone_digits(phone)

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

        if meta and stored_phone_digits(meta.get("phone", "")) == phone:
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


def normalize_phone_input(phone):
    return str(phone or "").strip().replace(" ", "").replace("-", "")


def stored_phone_digits(phone):
    raw = str(phone or "").strip()
    if raw.startswith("+"):
        raw = raw[1:]
    raw = raw.replace(" ", "").replace("-", "")
    return "".join(ch for ch in raw if ch.isdigit())


def phone_calling_code(phone):
    raw = stored_phone_digits(phone)
    if not raw:
        return ""
    for code in CALLING_CODES:
        if raw.startswith(code) and len(raw) > len(code):
            return code
    return raw[:1] if raw else ""


def calling_code_counts(accounts):
    counts = {}
    for meta in accounts:
        code = phone_calling_code(meta.get("phone", ""))
        if code:
            counts[code] = counts.get(code, 0) + 1
    return counts


def format_phone_dashed(phone):
    raw = stored_phone_digits(phone)
    if not raw:
        return ""
    for code in CALLING_CODES:
        if raw.startswith(code) and len(raw) > len(code):
            return "+" + code + "-" + raw[len(code):]
    return "+" + raw


def sanitize_filename_part(value):
    text = str(value or "")
    for ch in '\\/:*?"<>|\r\n':
        text = text.replace(ch, "_")
    return text


def session_download_filename(meta):
    phone = format_phone_dashed((meta or {}).get("phone", "")) or "None"
    twofa = str((meta or {}).get("password_2fa", "") or "").strip() or "None"
    twofa = sanitize_filename_part(twofa)
    api_id, api_hash = get_credentials(meta)
    api_hash = sanitize_filename_part(api_hash)
    tag = sanitize_filename_part(str((meta or {}).get("tag", "") or "").strip() or "None")
    # Canonical order: phone - 2FA - API_ID - API_HASH - tag
    return "{0}-{1}-{2}-{3}-{4}.session".format(
        phone, twofa, api_id, api_hash, tag
    )


def parse_session_download_name(filename):
    name = os.path.basename(str(filename or ""))
    if name.lower().endswith(".session"):
        name = name[:-8]

    # Canonical format:
    # +callingcode-nationalnumber-2fa-apiid-apihash-tag.session
    # Tag is deliberately allowed to contain hyphens.
    match = re.fullmatch(r"\+(\d+)-(\d+)-(.*)-(\d+)-([A-Za-z0-9]+)-(.*)", name)
    if match:
        code, national, twofa, api_id, api_hash, tag = match.groups()
        try:
            api_id = int(api_id)
        except Exception:
            return None
        if twofa in ("", "None"):
            twofa = ""
        if tag in ("", "None"):
            tag = ""
        return {
            "phone": code + national,
            "password_2fa": twofa,
            "api_id": api_id,
            "api_hash": api_hash,
            "tag": tag
        }

    # Backward compatibility with the previous four-part filename format.
    match = re.fullmatch(r"\+(\d+)-(\d+)-(.*)-(\d+)-([A-Za-z0-9]+)", name)
    if match:
        code, national, twofa, api_id, api_hash = match.groups()
        try:
            api_id = int(api_id)
        except Exception:
            return None
        if twofa in ("", "None"):
            twofa = ""
        return {
            "phone": code + national,
            "password_2fa": twofa,
            "api_id": api_id,
            "api_hash": api_hash,
            "tag": ""
        }
    return None


def card_key_line(phone, base_url, account_id):
    digits = stored_phone_digits(phone)
    if digits:
        return "+{0}--{1}/getcode/{2}".format(digits, base_url, account_id)
    return "{0}/getcode/{1}".format(base_url, account_id)


def sanitize_base_url(raw):
    raw = str(raw or "").strip().rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        return ""
    if not parsed.netloc:
        return ""
    return parsed.scheme + "://" + parsed.netloc


def header_first(value):
    return str(value or "").split(",")[0].strip()


def is_local_host(host):
    name = str(host or "").split(":")[0].strip().lower().strip("[]")
    return name in ("localhost", "127.0.0.1", "0.0.0.0", "::1", "")


def posted_account_ids(data):
    account_ids = data.get("account_ids", [])
    if not isinstance(account_ids, list):
        account_ids = [account_ids]
    result = []
    seen = set()
    for account_id in account_ids:
        account_id = str(account_id).strip()
        if account_id in seen:
            continue
        if is_safe_account_id(account_id) and os.path.exists(session_path(account_id)):
            result.append(account_id)
            seen.add(account_id)
    return result


def admin_scripts(extra=""):
    platform_data = {key: (None if value is None else [value[0], value[1]]) for key, value in PLATFORM_API.items()}
    return COPY_SCRIPT + PLATFORM_SCRIPT.replace("__PLATFORM_DATA__", json.dumps(platform_data)) + extra


def fill_platform_content(content, settings):
    platform_options = platform_options_html(settings.get("platform", "desktop"))
    safe_api_id = html_escape(str(settings.get("api_id", "")), quote=True) if settings.get("platform") == "custom" else ""
    safe_api_hash = html_escape(str(settings.get("api_hash", "")), quote=True) if settings.get("platform") == "custom" else ""
    return (
        content
        .replace("__PLATFORM_OPTIONS__", platform_options)
        .replace("__API_ID_VALUE__", safe_api_id)
        .replace("__API_HASH_VALUE__", safe_api_hash)
    )


def admin_page(title, content, scripts="", active=""):
    html = ADMIN_TEMPLATE
    html = html.replace("__TITLE__", title)
    html = html.replace("__CONTENT__", content)
    html = html.replace("__SCRIPT__", scripts)
    html = html.replace("__STYLE__", COMMON_STYLE)
    html = html.replace("__DASH_ACTIVE__", "active" if active == "dash" else "")
    html = html.replace("__ACCOUNTS_ACTIVE__", "active" if active == "accounts" else "")
    html = html.replace("__ADD_ACTIVE__", "active" if active == "add" else "")
    html = html.replace("__DOWNLOAD_ACTIVE__", "active" if active == "download" else "")
    html = html.replace("__TAGS_ACTIVE__", "active" if active == "tags" else "")
    return html


def iter_zip_sessions(content):
    buf = io.BytesIO(content)
    with zipfile.ZipFile(buf, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = os.path.basename(info.filename.replace("\\", "/"))
            if not name or name.startswith(".") or name.startswith("__"):
                continue
            if not name.lower().endswith(".session"):
                continue
            yield name, zf.read(info)


def import_review_file_list(entries):
    rows = []
    for entry in entries:
        name = str(entry.get("name", ""))
        parsed = entry.get("parsed")
        if not parsed:
            rows.append('<div class="small"><strong>{0}</strong> — invalid filename format</div>'.format(
                html_escape(name)
            ))
            continue
        rows.append(
            '<div class="small"><strong>{0}</strong> — Phone: {1} | 2FA: {2} | API_ID: {3} | API_HASH: {4} | Tag: {5}</div>'.format(
                html_escape(name),
                html_escape(parsed.get("phone", "") or "(empty)"),
                html_escape(parsed.get("password_2fa", "") or "(empty)"),
                html_escape(str(parsed.get("api_id", ""))),
                html_escape(parsed.get("api_hash", "") or "(empty)"),
                html_escape(parsed.get("tag", "") or "(empty)")
            )
        )
    return "".join(rows) or '<div class="small">No session entries.</div>'


def build_import_review_page(token, entries, settings):
    content = IMPORT_REVIEW_TEMPLATE
    content = content.replace("__TOKEN__", html_escape(token, quote=True))
    content = content.replace("__FILES__", import_review_file_list(entries))
    content = fill_platform_content(content, settings)
    return content


def build_import_entries(upload_name, file_content):
    is_zip = upload_name.lower().endswith(".zip") or file_content.startswith(b"PK")
    if is_zip:
        try:
            raw_entries = list(iter_zip_sessions(file_content))
        except Exception as e:
            return None, "Invalid ZIP: {0}".format(str(e))
        if not raw_entries:
            return None, "No .session files found in ZIP."
        entries = []
        for name, content in raw_entries:
            entries.append({
                "name": name,
                "content": content,
                "parsed": parse_session_download_name(name)
            })
        return entries, None

    parsed = parse_session_download_name(upload_name)
    if not parsed:
        return None, (
            "Invalid session filename. Expected "
            "+countrycode-number-2fa-apiid-apihash-tag.session"
        )
    if not file_content.startswith(b"SQLite format 3"):
        return None, "Invalid file. Native Telethon .session file or ZIP is required."
    return [{
        "name": upload_name,
        "content": file_content,
        "parsed": parsed
    }], None


def build_import_values(parsed, data):
    use_phone = get_first(data, "use_phone", "") == "1"
    use_2fa = get_first(data, "use_2fa", "") == "1"
    use_api = get_first(data, "use_api", "") == "1"
    use_tag = get_first(data, "use_tag", "") == "1"

    phone = stored_phone_digits(parsed.get("phone", "")) if use_phone else stored_phone_digits(
        get_first(data, "phone", "")
    )
    password_2fa = parsed.get("password_2fa", "") if use_2fa else get_first(
        data, "password_2fa", ""
    )
    tag = parsed.get("tag", "") if use_tag else get_first(data, "tag", "").strip()

    if use_api:
        api_id = parsed.get("api_id")
        api_hash = str(parsed.get("api_hash", "") or "")
        platform = "custom"
        error = None
    else:
        platform_raw = get_first(data, "platform", "")
        api_id_raw = get_first(data, "api_id", "")
        api_hash_raw = get_first(data, "api_hash", "")
        api_id, api_hash, platform, error = parse_credentials_with_platform(
            platform_raw, api_id_raw, api_hash_raw
        )

    if not phone:
        phone = ""
    return phone, password_2fa, tag, api_id, api_hash, platform, error


def build_sessions_zip(account_ids):
    buf = io.BytesIO()
    used_names = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for account_id in account_ids:
            meta = load_meta(account_id)
            path = session_path(account_id)
            if meta is None or not os.path.isfile(path):
                continue
            name = session_download_filename(meta)
            final_name = name
            n = 1
            while final_name in used_names:
                n += 1
                final_name = name[:-8] + "-{0}.session".format(n)
            used_names.add(final_name)
            zf.write(path, arcname=final_name)
    return buf.getvalue()


async def import_authorized_session(file_content, phone_input, pwd_input, tag_input, api_id, api_hash, platform):
    tmp_base = os.path.join(SESSIONS_DIR, "_import_{0}".format(uuid.uuid4().hex))

    try:
        with open(tmp_base + ".session", "wb") as f:
            f.write(file_content)
    except Exception as e:
        return {"ok": False, "error": "Write file failed: {0}".format(str(e))}

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

        return {"ok": False, "error": "Import failed: {0}".format(str(e))}

    clean_phone = stored_phone_digits(real_phone)
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
        return {"ok": False, "error": "Move session failed: {0}".format(str(e))}

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

    return {"ok": True, "phone": clean_phone, "id": account_id}


class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def _send_html(self, code, html, no_cache=False):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if no_cache:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _redirect(self, url, cookie=None):
        self.send_response(302)
        self.send_header("Location", url)

        if cookie:
            self.send_header("Set-Cookie", cookie)

        self.end_headers()

    def _send_file(self, data, content_type, filename):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", 'attachment; filename="{0}"'.format(filename))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _get_base_url(self):
        candidates = []

        origin = sanitize_base_url(self.headers.get("Origin", ""))
        if origin:
            candidates.append(origin)

        referer = self.headers.get("Referer", "")
        if referer:
            parsed = urlparse(referer)
            origin = sanitize_base_url("{0}://{1}".format(parsed.scheme, parsed.netloc))
            if origin:
                candidates.append(origin)

        xf_proto = header_first(self.headers.get("X-Forwarded-Proto", "")).lower()
        xf_host = header_first(self.headers.get("X-Forwarded-Host", ""))
        xf_ssl = str(self.headers.get("X-Forwarded-Ssl", "") or "").lower()
        forwarded = self.headers.get("Forwarded", "")

        if forwarded:
            first = forwarded.split(",")[0]
            proto = ""
            host = ""
            for part in first.split(";"):
                part = part.strip()
                lower = part.lower()
                if lower.startswith("proto="):
                    proto = part.split("=", 1)[1].strip().strip('"').lower()
                elif lower.startswith("host="):
                    host = part.split("=", 1)[1].strip().strip('"')
            if host:
                if proto not in ("http", "https"):
                    proto = "https" if xf_ssl == "on" else "http"
                origin = sanitize_base_url("{0}://{1}".format(proto, host))
                if origin:
                    candidates.append(origin)

        if xf_host:
            proto = xf_proto if xf_proto in ("http", "https") else ("https" if xf_ssl == "on" else "http")
            origin = sanitize_base_url("{0}://{1}".format(proto, xf_host))
            if origin:
                candidates.append(origin)

        host = header_first(self.headers.get("Host", ""))
        if host:
            proto = xf_proto if xf_proto in ("http", "https") else "http"
            origin = sanitize_base_url("{0}://{1}".format(proto, host))
            if origin:
                candidates.append(origin)

        public = []
        for item in candidates:
            parsed = urlparse(item)
            if not is_local_host(parsed.hostname):
                public.append(item)
        if public:
            return public[0]
        if candidates:
            return candidates[0]
        return "http://localhost:{0}".format(SERVER_PORT)

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

            self._send_html(200, html, no_cache=True)
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
                download_name = session_download_filename(meta)
                self.send_header(
                    "Content-Disposition",
                    'attachment; filename="{0}"'.format(download_name)
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

        if path in (
            "/admin",
            "/admin/login_new_account",
            "/admin/import_session_page",
            "/admin/import_session_review",
            "/admin/accounts",
            "/admin/add_account",
            "/admin/session_download_page",
            "/admin/tags"
        ):
            if not self._admin_logged_in():
                self._redirect("/admin/login")
                return
            if path in ("/admin/login_new_account", "/admin/import_session_page"):
                self._redirect("/admin/add_account")
                return
            settings = load_settings()
            scripts = admin_scripts()
            if path == "/admin/import_session_review":
                query = parse_qs(urlparse(self.path).query)
                token = str(get_first(query, "token", "") or "").strip()
                with pending_imports_lock:
                    pending = pending_imports.get(token)
                if not pending or time.time() - pending.get("created_at", 0) > 900:
                    if token:
                        with pending_imports_lock:
                            pending_imports.pop(token, None)
                    self._send_html(200, message_page("Error", "Upload expired. Please upload the file again."))
                    return
                entries = pending.get("entries", [])
                valid_count = sum(1 for item in entries if item.get("parsed"))
                if not valid_count:
                    self._send_html(200, message_page("Error", "No valid session filenames were found in the upload."))
                    return
                content = build_import_review_page(token, entries, settings)
                self._send_html(
                    200,
                    admin_page("Import Session Options", content, admin_scripts() + IMPORT_REVIEW_SCRIPT, "add")
                )
                return
            if path == "/admin/add_account":
                content = fill_platform_content(
                    ADD_ACCOUNT_CONTENT.replace("__LOGIN_PANEL__", LOGIN_PANEL).replace("__IMPORT_PANEL__", IMPORT_PANEL),
                    settings
                )
                self._send_html(200, admin_page("Add Account", content, scripts, "add"))
                return
            if path == "/admin/accounts":
                base_url = self._get_base_url()
                accounts = list_accounts()
                query = parse_qs(urlparse(self.path).query)
                selected_cc = str(get_first(query, "cc", "") or "").strip()
                selected_tag = str(get_first(query, "tag", "") or "").strip()
                counts = calling_code_counts(accounts)
                tag_counts = {}
                for meta in accounts:
                    tag = str(meta.get("tag", "") or "").strip()
                    if tag:
                        tag_counts[tag] = tag_counts.get(tag, 0) + 1

                visible = accounts
                if selected_cc and selected_cc != "all":
                    visible = [meta for meta in visible if phone_calling_code(meta.get("phone", "")) == selected_cc]
                else:
                    selected_cc = "all"
                if selected_tag and selected_tag != "all":
                    visible = [meta for meta in visible if str(meta.get("tag", "") or "").strip() == selected_tag]
                else:
                    selected_tag = "all"

                chips = '<a class="code-chip{0}" href="/admin/accounts">all <span class="n">({1})</span></a>'.format(
                    " active" if selected_cc == "all" and selected_tag == "all" else "",
                    len(accounts)
                )
                for code in sorted(counts.keys(), key=lambda item: (int(item) if item.isdigit() else 0, item)):
                    url = "/admin/accounts?cc={0}".format(html_escape(code, quote=True))
                    if selected_tag != "all":
                        url += "&tag=" + html_escape(selected_tag, quote=True)
                    chips += '<a class="code-chip{0}" href="{1}">+{2} <span class="n">({3})</span></a>'.format(
                        " active" if selected_cc == code else "",
                        url,
                        html_escape(code, quote=True),
                        counts[code]
                    )
                chips += '<div style="flex-basis:100%;height:0"></div><span class="small">Tags:</span>'
                for tag in sorted(tag_counts.keys()):
                    url = "/admin/accounts?tag={0}".format(html_escape(tag, quote=True))
                    if selected_cc != "all":
                        url += "&cc=" + html_escape(selected_cc, quote=True)
                    chips += '<a class="code-chip{0}" href="{1}">{2} <span class="n">({3})</span></a>'.format(
                        " active" if selected_tag == tag else "",
                        url,
                        html_escape(tag),
                        tag_counts[tag]
                    )
                items = ""
                for meta in visible:
                    account_id = str(meta.get("id", ""))
                    phone = str(meta.get("phone", ""))
                    copy_value = card_key_line(phone, base_url, account_id)
                    safe_id = html_escape(account_id, quote=True)
                    safe_phone = html_escape(format_phone_dashed(phone) or phone or account_id)
                    safe_copy = html_escape(copy_value, quote=True)
                    items += (
                        '<div class="item"><div class="item-top"><div class="item-check">'
                        '<input form="bulk-form" type="checkbox" name="account_ids" value="{0}" data-key="{1}">'
                        '<div class="item-phone">{2}</div></div><div class="item-actions">'
                        '<button type="button" data-copy="{1}" onclick="copyText(applyPageOrigin(this.dataset.copy))">Copy</button>'
                        '<a class="button" href="/getcode/{0}">Open</a>'
                        '<form class="inline-form" method="post" action="/admin/delete/{0}" onsubmit="return confirm(\'Delete this account and its local session files?\');">'
                        '<button type="submit">Delete</button></form></div></div></div>'
                    ).format(safe_id, safe_copy, safe_phone)
                account_body = items or '<div class="panel"><div class="small">No accounts yet.</div></div>'
                content = (
                    '<div class="topbar"><div><h1>Accounts</h1>'
                    '<div class="subtitle">Copy keys, open receive-code pages, delete sessions, or export selected accounts.</div></div>'
                    '<div class="live"><span class="dot"></span> Server online</div></div>'
                    '<div class="code-filters">{0}</div>'
                    '<form id="bulk-form" method="post" action="/admin/download_keys">'
                    '<input type="hidden" name="base_url" id="page-origin" value="">'
                    '<div class="accounts-toolbar"><div class="random-field">'
                    '<label class="select-all-row"><input type="checkbox" onchange="toggleAll(this)"> Select all</label>'
                    '<input type="number" id="random-count" min="0" step="1" placeholder="Count">'
                    '<button type="button" onclick="randomSelect()">Random</button></div>'
                    '<div class="actions"><button type="button" onclick="copySelectedKeys()">Copy keys</button>'
                    '<button type="submit" formaction="/admin/download_keys">Download keys</button>'
                    '<button type="submit" formaction="/admin/download_sessions_zip">Download sessions</button><button type="submit" class="danger" formaction="/admin/delete_selected" onclick="return confirm(\'Delete selected accounts and their local session files?\')">Delete</button></div></div></form>'
                    '<div id="account-items" class="accounts-list">{1}</div>'
                ).format(chips, account_body)
                self._send_html(200, admin_page("Accounts", content, scripts + ACCOUNTS_SCRIPT, "accounts"))
                return
            if path == "/admin/session_download_page":
                accounts = list_accounts()
                options = ""
                for meta in accounts:
                    account_id = str(meta.get("id", ""))
                    phone = str(meta.get("phone", ""))
                    safe_id = html_escape(account_id, quote=True)
                    safe_phone = html_escape(phone or account_id)
                    checked = " checked" if meta.get("allow_session_download", True) else ""
                    options += '<label class="bulk-option"><input type="checkbox" name="account_ids" value="{0}"{1}><span>{2}</span></label>'.format(safe_id, checked, safe_phone)
                bulk_body = options or '<div class="small">No accounts available.</div>'
                content = (
                    '<div class="topbar"><div><h1>Session Download</h1>'
                    '<div class="subtitle">Choose which accounts can download session files from the receive-code page.</div></div>'
                    '<div class="live"><span class="dot"></span> Server online</div></div>'
                    '<section class="panel bulk-panel"><div class="panel-head"><div>'
                    '<div class="panel-title">Download Permission</div>'
                    '<div class="panel-desc">Checked accounts stay enabled. Save applies the full selection at once.</div></div></div>'
                    '<form id="download-settings-form" method="post" action="/admin/save_session_download">'
                    '<label class="select-all-row"><input type="checkbox" onchange="toggleDownloadAll(this)"> Select all</label>'
                    '<div class="bulk-list">{0}</div>'
                    '<div class="bulk-actions"><button class="primary" type="submit">Save</button></div></form></section>'
                ).format(bulk_body)
                self._send_html(200, admin_page("Session Download", content, scripts + ACCOUNTS_SCRIPT, "download"))
                return
            if path == "/admin/tags":
                accounts = list_accounts()
                rows = ""
                for meta in accounts:
                    account_id = str(meta.get("id", ""))
                    phone = str(meta.get("phone", ""))
                    tag = str(meta.get("tag", ""))
                    safe_id = html_escape(account_id, quote=True)
                    safe_phone = html_escape(phone or account_id)
                    safe_tag = html_escape(tag, quote=True)
                    rows += '<div class="tag-row"><div class="item-phone">{0}</div><input type="text" name="tag__{1}" value="{2}" placeholder="Tag"></div>'.format(safe_phone, safe_id, safe_tag)
                tag_body = rows or '<div class="small">No accounts available.</div>'
                content = (
                    '<div class="topbar"><div><h1>Tags</h1>'
                    '<div class="subtitle">Edit account tags and save them all at once.</div></div>'
                    '<div class="live"><span class="dot"></span> Server online</div></div>'
                    '<section class="panel"><div class="panel-head"><div>'
                    '<div class="panel-title">Account Tags</div>'
                    '<div class="panel-desc">One save writes every tag in the list.</div></div></div>'
                    '<form method="post" action="/admin/save_tags"><div class="tag-list">{0}</div>'
                    '<div class="bulk-actions"><button class="primary" type="submit">Save Tags</button></div></form></section>'
                ).format(tag_body)
                self._send_html(200, admin_page("Tags", content, scripts, "tags"))
                return
            accounts = list_accounts()
            items = ""
            for meta in accounts:
                account_id = str(meta.get("id", ""))
                phone = str(meta.get("phone", ""))
                safe_id = html_escape(account_id, quote=True)
                safe_phone = html_escape(phone or account_id)
                items += '<div class="item"><div class="item-top"><div class="item-phone">{0}</div><div class="item-actions"><a class="button" href="/getcode/{1}">Open</a></div></div></div>'.format(safe_phone, safe_id)
            account_body = items or '<div class="panel"><div class="small">No accounts yet.</div></div>'
            content = (
                '<div class="topbar"><div><h1>Dashboard</h1>'
                '<div class="subtitle">Telegram account and session management</div></div>'
                '<div class="live"><span class="dot"></span> Server online</div></div>'
                '<div class="stats"><div class="stat"><div class="label">Total accounts</div>'
                '<div class="stat-value">{0}</div></div></div>'
                '<div class="accounts-head"><div><div class="panel-title">Accounts</div>'
                '<div class="panel-desc">Open a receive-code page for an account.</div></div>'
                '<a class="button primary" href="/admin/add_account">Add Account</a></div>'
                '<div class="accounts-list">{1}</div>'
            ).format(len(accounts), account_body)
            self._send_html(200, admin_page("Dashboard", content, scripts, "dash"))
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
            phone = normalize_phone_input(get_first(data, "phone", ""))

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
            phone = normalize_phone_input(get_first(data, "phone", ""))
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

                clean_phone = stored_phone_digits(real_phone)
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
            upload_name = str(files["session_file"].get("filename", "") or "")
            entries, error = build_import_entries(upload_name, file_content)
            if error:
                self._send_html(200, message_page("Error", error))
                return

            token = secrets.token_urlsafe(24)
            with pending_imports_lock:
                pending_imports[token] = {
                    "created_at": time.time(),
                    "entries": entries
                }

            settings = load_settings()
            content = build_import_review_page(token, entries, settings)
            self._send_html(
                200,
                admin_page("Import Session Options", content, admin_scripts() + IMPORT_REVIEW_SCRIPT, "add")
            )
            return

        if path == "/admin/import_session_review":
            token = get_first(data, "token", "").strip()
            with pending_imports_lock:
                pending = pending_imports.get(token)

            if not pending or time.time() - pending.get("created_at", 0) > 900:
                with pending_imports_lock:
                    pending_imports.pop(token, None)
                self._send_html(200, message_page("Error", "Upload expired. Please upload the file again."))
                return

            entries = pending.get("entries", [])
            valid_entries = [item for item in entries if item.get("parsed")]
            if not valid_entries:
                with pending_imports_lock:
                    pending_imports.pop(token, None)
                self._send_html(200, message_page("Error", "No valid session filenames were found."))
                return

            phone_custom = stored_phone_digits(get_first(data, "phone", ""))
            pwd_custom = get_first(data, "password_2fa", "")
            tag_custom = get_first(data, "tag", "").strip()

            # Validate the selected/custom API settings once before importing.
            use_api = get_first(data, "use_api", "") == "1"
            if use_api:
                api_id = None
                api_hash = ""
                platform = "custom"
                api_error = None
                # Filename API credentials are validated per entry below.
            else:
                platform_raw = get_first(data, "platform", "")
                api_id_raw = get_first(data, "api_id", "")
                api_hash_raw = get_first(data, "api_hash", "")
                api_id, api_hash, platform, api_error = parse_credentials_with_platform(
                    platform_raw, api_id_raw, api_hash_raw
                )
                if api_error:
                    self._send_html(200, message_page("Error", api_error))
                    return
                remember_credentials(platform, api_id_raw, api_hash_raw)

            async def _import_review():
                lines = []
                ok_count = 0

                for entry in valid_entries:
                    parsed = entry["parsed"]
                    if use_api:
                        entry_api_id = parsed.get("api_id")
                        entry_api_hash = str(parsed.get("api_hash", "") or "")
                        entry_platform = "custom"
                        if not entry_api_id or not entry_api_hash:
                            lines.append(
                                "{0}: invalid API credentials in filename".format(entry["name"])
                            )
                            continue
                    else:
                        entry_api_id = api_id
                        entry_api_hash = api_hash
                        entry_platform = platform

                    use_phone = get_first(data, "use_phone", "") == "1"
                    use_2fa = get_first(data, "use_2fa", "") == "1"
                    use_tag = get_first(data, "use_tag", "") == "1"

                    phone = stored_phone_digits(parsed.get("phone", "")) if use_phone else phone_custom
                    pwd = parsed.get("password_2fa", "") if use_2fa else pwd_custom
                    tag = parsed.get("tag", "") if use_tag else tag_custom

                    if not entry["content"].startswith(b"SQLite format 3"):
                        lines.append("{0}: not a Telethon session".format(entry["name"]))
                        continue

                    result = await import_authorized_session(
                        entry["content"],
                        phone,
                        pwd,
                        tag,
                        entry_api_id,
                        entry_api_hash,
                        entry_platform
                    )
                    if result.get("ok"):
                        ok_count += 1
                        lines.append(
                            "{0}: imported {1}".format(
                                entry["name"], result.get("phone", "")
                            )
                        )
                    else:
                        lines.append(
                            "{0}: {1}".format(
                                entry["name"], result.get("error", "failed")
                            )
                        )

                body = "".join(
                    '<div class="small">{0}</div>'.format(html_escape(item))
                    for item in lines
                )
                title = "Import success" if ok_count else "Import failed"
                return simple_page(
                    title,
                    '{0}<p>{1} imported.</p><div class="actions">'
                    '<a class="button" href="/admin/accounts">Back</a></div>'.format(
                        body, ok_count
                    )
                )

            future = asyncio.run_coroutine_threadsafe(_import_review(), main_loop)
            try:
                html = future.result(timeout=max(60, min(300, 45 * len(valid_entries))))
            except Exception as e:
                html = message_page("Error", "Timeout: {0}".format(str(e)))

            with pending_imports_lock:
                pending_imports.pop(token, None)

            self._send_html(200, html)
            return

        if path == "/admin/save_session_download":
            selected = set(posted_account_ids(data))
            for meta in list_accounts():
                account_id = str(meta.get("id", ""))
                if is_safe_account_id(account_id):
                    update_meta(account_id, allow_session_download=account_id in selected)
            self._redirect("/admin/session_download_page")
            return

        if path == "/admin/save_tags":
            for meta in list_accounts():
                account_id = str(meta.get("id", ""))
                if not is_safe_account_id(account_id):
                    continue
                tag = get_first(data, "tag__{0}".format(account_id), "").strip()
                update_meta(account_id, tag=tag)
            self._redirect("/admin/tags")
            return

        if path == "/admin/download_keys":
            account_ids = posted_account_ids(data)
            if not account_ids:
                self._send_html(200, message_page("Error", "No accounts selected."))
                return
            base_url = sanitize_base_url(get_first(data, "base_url", "")) or self._get_base_url()
            lines = []
            for account_id in account_ids:
                meta = load_meta(account_id) or {}
                lines.append(card_key_line(meta.get("phone", ""), base_url, account_id))
            text = "\n".join(lines) + "\n"
            self._send_file(text.encode("utf-8"), "text/plain; charset=utf-8", "keys.txt")
            return

        if path == "/admin/download_sessions_zip":
            account_ids = posted_account_ids(data)
            if not account_ids:
                self._send_html(200, message_page("Error", "No accounts selected."))
                return
            data_zip = build_sessions_zip(account_ids)
            if not data_zip:
                self._send_html(200, message_page("Error", "No session files to download."))
                return
            self._send_file(data_zip, "application/zip", "sessions.zip")
            return

        if path == "/admin/bulk_session_download":
            selected = set(posted_account_ids(data))
            action = get_first(data, "action", "")
            if action in ("enable", "disable"):
                enabled = action == "enable"
                for account_id in selected:
                    update_meta(account_id, allow_session_download=enabled)
            self._redirect("/admin/session_download_page")
            return

        if path.startswith("/admin/session_download/"):
            account_id = path.split("/admin/session_download/", 1)[-1].strip("/")

            if not is_safe_account_id(account_id):
                self._redirect("/admin/session_download_page")
                return

            meta = load_meta(account_id)
            if meta is not None and os.path.exists(session_path(account_id)):
                update_meta(
                    account_id,
                    allow_session_download=get_first(data, "enabled", "") == "1"
                )

            self._redirect("/admin/session_download_page")
            return

        if path.startswith("/admin/tag/"):
            account_id = path.split("/admin/tag/", 1)[-1].strip("/")

            if not is_safe_account_id(account_id):
                self._redirect("/admin/tags")
                return

            tag = get_first(data, "tag", "").strip()
            update_meta(account_id, tag=tag)
            self._redirect("/admin/tags")
            return

        if path == "/admin/delete_selected":
            account_ids = posted_account_ids(data)
            if not account_ids:
                self._send_html(200, message_page("Error", "No accounts selected."))
                return

            for account_id in account_ids:
                client = clients.pop(account_id, None)

                if client:
                    async def cleanup(client=client, account_id=account_id):
                        try:
                            await client.disconnect()
                        except Exception:
                            pass
                        delete_account(account_id)

                    try:
                        asyncio.run_coroutine_threadsafe(cleanup(), main_loop)
                    except Exception:
                        delete_account(account_id)
                else:
                    delete_account(account_id)

            self._redirect("/admin/accounts")
            return

        if path.startswith("/admin/delete/"):
            account_id = path.split("/admin/delete/", 1)[-1].strip("/")

            if not is_safe_account_id(account_id):
                self._redirect("/admin/accounts")
                return

            client = clients.pop(account_id, None)

            if client:
                async def cleanup():
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                    delete_account(account_id)

                try:
                    asyncio.run_coroutine_threadsafe(cleanup(), main_loop)
                except Exception:
                    delete_account(account_id)
            else:
                delete_account(account_id)

            self._redirect("/admin/accounts")
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
