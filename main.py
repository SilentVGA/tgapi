import asyncio
import uuid
import datetime
import re
import sqlite3
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

ADMIN_PASSWORD = "admin123"
SERVER_PORT = 8000
DB_PATH = 'accounts.db'

main_loop = asyncio.new_event_loop()
clients = {}
pending_logins = {}

def init_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE,
        uuid TEXT UNIQUE,
        session_string TEXT,
        api_id INTEGER,
        api_hash TEXT,
        password_2fa TEXT,
        latest_code TEXT,
        status TEXT DEFAULT 'unknown',
        last_checked TIMESTAMP
    )''')
    conn.commit()
    conn.close()

init_db()

def db_execute(query, params=()):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(query, params)
    conn.commit()
    conn.close()

def db_fetchall(query, params=()):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    res = conn.execute(query, params).fetchall()
    conn.close()
    return res

def db_fetchone(query, params=()):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    res = conn.execute(query, params).fetchone()
    conn.close()
    return res

async def ensure_client(account_uuid):
    if account_uuid in clients:
        client = clients[account_uuid]
        if client.is_connected() and await client.is_user_authorized():
            return client
    
    acc = db_fetchone("SELECT session_string, api_id, api_hash FROM accounts WHERE uuid=?", (account_uuid,))
    if not acc:
        return None
        
    client = TelegramClient(StringSession(acc[0]), acc[1], acc[2])
    try:
        await client.connect()
        if not await client.is_user_authorized():
            db_execute("UPDATE accounts SET status='offline' WHERE uuid=?", (account_uuid,))
            await client.disconnect()
            return None
            
        clients[account_uuid] = client
        db_execute("UPDATE accounts SET status='online' WHERE uuid=?", (account_uuid,))
        
        @client.on(events.NewMessage)
        async def handler(event):
            try:
                if event.chat_id in (777000, 42777, 424000, 42400, 33300, 22222):
                    text = event.message.message or ""
                    match = re.search(r'\b(\d{5,6})\b', text)
                    if match:
                        db_execute("UPDATE accounts SET latest_code=? WHERE uuid=?", (match.group(1), account_uuid))
                        
                if event.sender_id == 178115495:
                    text = event.message.message or ""
                    dead_msg = "Your account was blocked for violations of the Telegram Terms of Services based on user reports confirmed by our moderators."
                    if dead_msg in text:
                        db_execute("UPDATE accounts SET status='dead', last_checked=? WHERE uuid=?", (datetime.datetime.utcnow(), account_uuid))
                    else:
                        db_execute("UPDATE accounts SET status='normal', last_checked=? WHERE uuid=? AND status!='dead'", (datetime.datetime.utcnow(), account_uuid))
            except Exception:
                pass

        client.add_event_handler(handler)
        main_loop.create_task(client.run_until_disconnected())
        
        async def monitor_disconnect():
            await client.disconnected
            db_execute("UPDATE accounts SET status='offline' WHERE uuid=?", (account_uuid,))
            if account_uuid in clients:
                del clients[account_uuid]
                
        main_loop.create_task(monitor_disconnect())
        return client
        
    except Exception:
        db_execute("UPDATE accounts SET status='offline' WHERE uuid=?", (account_uuid,))
        try:
            await client.disconnect()
        except Exception:
            pass
        return None

async def check_spambot_task(uid, last_checked_str):
    client = await ensure_client(uid)
    if not client:
        return

    now = datetime.datetime.utcnow()
    last_checked = None
    if last_checked_str:
        try:
            last_checked = datetime.datetime.strptime(last_checked_str, "%Y-%m-%d %H:%M:%S.%f")
        except Exception:
            pass

    if not last_checked or (now - last_checked).total_seconds() > 10:
        try:
            await client.send_message(178115495, '/start')
            await asyncio.sleep(3)
        except Exception:
            db_execute("UPDATE accounts SET status='offline' WHERE uuid=?", (uid,))

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass

    def _send_html(self, code, html):
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def _redirect(self, url, cookie=None):
        self.send_response(302)
        self.send_header('Location', url)
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()

    def _get_base_url(self):
        host = self.headers.get('Host', f'localhost:{SERVER_PORT}')
        proto = self.headers.get('X-Forwarded-Proto', 'http')
        return f"{proto}://{host}"

    def do_GET(self):
        path = urlparse(self.path).path
        
        if path == '/admin/login':
            html = '''<!DOCTYPE html><html><body style="font-family:monospace;background:#f4f4f4;padding:50px;text-align:center">
            <h2>Admin Login</h2>
            <form action="/admin/auth" method="post" style="background:white;padding:20px;display:inline-block;border:1px solid #ccc">
                Password: <input type="password" name="pwd" required autofocus>
                <button type="submit">Enter</button>
            </form></body></html>'''
            self._send_html(200, html)
            return

        is_logged_in = 'admin_session=valid' in self.headers.get('Cookie', '')

        if path == '/admin/logout':
            self._redirect('/admin/login', 'admin_session=; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/')
            return

        if path == '/admin':
            if not is_logged_in:
                self._redirect('/admin/login')
                return

            base_url = self._get_base_url()
            rows = db_fetchall("SELECT id, phone, uuid FROM accounts")
            items = ""
            for r in rows:
                val = f"+{r[1]}--{base_url}/getcode/{r[2]}"
                items += f'''<div style="margin-bottom:8px; border-bottom:1px dashed #ccc; padding-bottom:5px;">
                    <input type="text" id="t{r[0]}" value="{val}" readonly style="width:600px; font-family:monospace; border:1px solid #999; padding:4px">
                    <button onclick="var i=document.getElementById('t{r[0]}'); i.select(); document.execCommand('copy'); alert('Copied')">Copy</button>
                    <form action="/admin/delete/{r[0]}" method="post" style="display:inline" onsubmit="return confirm('Delete?')">
                        <button style="color:red">Del</button>
                    </form>
                </div>'''
            
            html = f'''<!DOCTYPE html><html><body style="font-family:monospace;background:#f4f4f4;padding:20px">
            <h1>Admin Panel</h1>
            <div style="background:white; padding:15px; border:1px solid #999; margin-bottom:20px">
                <h3>Add New Account</h3>
                <form action="/admin/send_code" method="post">
                    Phone: <input name="phone" placeholder="+123456789" required style="width:150px">
                    API_ID: <input name="api_id" required style="width:100px">
                    API_HASH: <input name="api_hash" required style="width:250px">
                    <button type="submit" style="background:#007bff; color:white; border:none; padding:5px 10px">Send Code</button>
                </form>
            </div>
            <h3>Accounts ({len(rows)})</h3>
            {items}
            <br><a href="/admin/logout">Logout</a>
            </body></html>'''
            self._send_html(200, html)
            
        elif path.startswith('/getcode/'):
            uid = path.split('/')[-1]
            acc = db_fetchone("SELECT phone, status, latest_code, password_2fa, last_checked FROM accounts WHERE uuid=?", (uid,))
            
            if not acc:
                self._send_html(404, "Not found")
                return
                
            async def prepare_page():
                client = await ensure_client(uid)
                if client:
                    asyncio.create_task(check_spambot_task(uid, acc[4]))
                    await asyncio.sleep(0.5)

            future = asyncio.run_coroutine_threadsafe(prepare_page(), main_loop)
            try:
                future.result(timeout=15)
            except Exception:
                pass
            
            acc = db_fetchone("SELECT phone, status, latest_code, password_2fa, last_checked FROM accounts WHERE uuid=?", (uid,))
            
            html = f'''<!DOCTYPE html><html><body style="font-family:monospace; text-align:center; padding-top:50px; background:#fff">
            <h1>{acc[0]}</h1>
            <div style="font-size:32px; margin:20px 0; font-weight:bold; color:#d9534f">
                {acc[2] or 'Waiting...'}
            </div>
            <div style="font-size:16px; color:#333; margin-bottom:30px">
                Status: <b>{acc[1]}</b> &nbsp;|&nbsp; 2FA: <b>{acc[3] or 'None'}</b>
            </div>
            <button onclick="location.reload()" style="padding:10px 30px; font-size:16px; cursor:pointer">Refresh</button>
            </body></html>'''
            self._send_html(200, html)
        else:
            self._redirect('/admin')

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        data = parse_qs(self.rfile.read(length).decode('utf-8')) if length > 0 else {}
        path = urlparse(self.path).path
        
        if path == '/admin/auth':
            pwd = data.get('pwd', [''])[0]
            if pwd == ADMIN_PASSWORD:
                self._redirect('/admin', 'admin_session=valid; Path=/; HttpOnly')
            else:
                self._send_html(200, "<script>alert('Wrong Password'); location.href='/admin/login';</script>")
            return

        if 'admin_session=valid' not in self.headers.get('Cookie', ''):
            self._redirect('/admin/login')
            return

        if path == '/admin/send_code':
            phone = data.get('phone', [''])[0].strip()
            api_id_str = data.get('api_id', ['0'])[0].strip()
            api_hash = data.get('api_hash', [''])[0].strip()
            
            if not phone or not api_id_str or not api_hash:
                self._send_html(200, "Missing fields. <a href='/admin'>Back</a>")
                return
                
            try:
                api_id = int(api_id_str)
            except Exception:
                self._send_html(200, "Invalid API_ID. <a href='/admin'>Back</a>")
                return

            async def _send_code():
                client = TelegramClient(StringSession(), api_id, api_hash)
                await client.connect()
                try:
                    result = await client.send_code_request(phone)
                    pending_logins[phone] = {"api_id": api_id, "api_hash": api_hash, "hash": result.phone_code_hash, "client": client}
                    return f'''<!DOCTYPE html><html><body style="font-family:monospace;padding:50px;text-align:center">
                    <h1>Enter Code for {phone}</h1>
                    <form action="/admin/verify" method="post" style="background:#f9f9f9;padding:20px;display:inline-block;border:1px solid #ccc">
                        <input type="hidden" name="phone" value="{phone}">
                        Code: <input name="code" required autofocus style="font-size:20px; width:120px; text-align:center"><br><br>
                        2FA Password (if any): <input name="password"><br><br>
                        <button type="submit" style="padding:8px 20px; background:green; color:white; border:none">Login</button>
                    </form></body></html>'''
                except Exception as e:
                    await client.disconnect()
                    return f"Error: {str(e)}. <a href='/admin'>Back</a>"
                    
            future = asyncio.run_coroutine_threadsafe(_send_code(), main_loop)
            html = future.result(timeout=30)
            self._send_html(200, html)
            
        elif path == '/admin/verify':
            phone = data.get('phone', [''])[0]
            code = data.get('code', [''])[0].strip()
            pwd = data.get('password', [None])[0]
            pending = pending_logins.get(phone)
            
            if not pending:
                self._send_html(200, "Session expired. <a href='/admin'>Back</a>")
                return
                
            async def _verify():
                client = pending["client"]
                try:
                    await client.sign_in(phone, code, phone_code_hash=pending["hash"])
                except SessionPasswordNeededError:
                    if not pwd:
                        await client.disconnect()
                        return "2FA Password Required. <a href='/admin'>Back</a>"
                    try:
                        await client.sign_in(password=pwd)
                    except Exception as e:
                        await client.disconnect()
                        return f"2FA Failed: {str(e)}. <a href='/admin'>Back</a>"
                except Exception as e:
                    await client.disconnect()
                    return f"Code Failed: {str(e)}. <a href='/admin'>Back</a>"
                    
                ss = client.session.save()
                await client.disconnect()
                new_uuid = str(uuid.uuid4())
                
                db_execute("INSERT INTO accounts (phone,uuid,session_string,api_id,api_hash,password_2fa,status) VALUES (?,?,?,?,?,?,?)", (phone.replace("+",""), new_uuid, ss, pending["api_id"], pending["api_hash"], pwd, "unknown"))
                
                return "<script>alert('Login Success!'); location.href='/admin';</script>"
                
            future = asyncio.run_coroutine_threadsafe(_verify(), main_loop)
            html = future.result(timeout=30)
            self._send_html(200, html)
            
        elif path.startswith('/admin/delete/'):
            try:
                aid = int(path.split('/')[-1])
                row = db_fetchone("SELECT uuid FROM accounts WHERE id=?", (aid,))
                if row:
                    client = clients.pop(row[0], None)
                    if client:
                        asyncio.run_coroutine_threadsafe(client.disconnect(), main_loop)
                    db_execute("DELETE FROM accounts WHERE id=?", (aid,))
                self._redirect('/admin')
            except Exception:
                self._redirect('/admin')
        else:
            self._redirect('/admin')

def start_server():
    server = ThreadingHTTPServer(('0.0.0.0', SERVER_PORT), Handler)
    print(f"Server running on port {SERVER_PORT}...")
    server.serve_forever()

if __name__ == '__main__':
    try:
        server_thread = threading.Thread(target=start_server, daemon=True)
        server_thread.start()
        main_loop.run_forever()
    except KeyboardInterrupt:
        print("Shutting down...")