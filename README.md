# tgapi - 极简 Telegram 接码系统

一个单文件、无 Web 框架、专为低内存 NAT 机器设计的 Telegram 验证码接收 Python 脚本。支持导入导出 `.session` + `.json` 账号包、随机设备指纹、真实手机号检测与 2FA 管理。

![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python)
![License](https://img.shields.io/badge/License-MIT-green)
![Memory](https://img.shields.io/badge/Memory-<96MB-orange?logo=linux)

---

## ⚡ 部署与使用

仅需一个第三方依赖，无需数据库，开箱即用：

```bash
apt install python3 python3-pip
pip install telethon
python3 main.py
```

> 如果是受限制的 Debian/Ubuntu 系统，请使用：
> `pip install telethon --break-system-packages`

启动后访问：

```
http://你的IP:8000/admin
```

默认管理员密码为 `admin123`，请在代码顶部修改：

```python
ADMIN_PASSWORD = "admin123"
```

---

## 📦 账号导入 / 导出格式

导入时需要上传一个 **ZIP 压缩包**，其内部结构为：

```
accounts.zip
├── +1323456789/
│   ├── +1323456789.session
│   └── +1323456789.json
├── +447911123456/
│   ├── +447911123456.session
│   └── +447911123456.json
└── ...
```

- `.session` 必须是 **Telethon 原生 SQLite 数据库文件**（文件头为 `SQLite format 3`）。
- `.json` 用于描述账号元数据，支持的字段包括：手机号、2FA 密码、`api_id` / `app_id`、`api_hash` / `app_hash`，以及设备信息（`device_model`、`system_version`、`app_version`、`lang_pack`、`system_lang_code`）。
- JSON 中缺少 API 凭据的账号，可在导入确认页选择一个平台作为兜底。
- 导入时可为全部账号统一设置 Tag，并可选择设备指纹来源。

导出时：

- **单个账号**：下载一个包含 `.session` 与 `.json` 的 ZIP 包。
- **批量导出**：下载 `sessions.zip`，每个账号一个独立文件夹，结构与导入格式一致，可直接再次导入。

不支持 StringSession 纯文本、Pyrogram `.session` 或其他自定义格式。

---

## ✨ 核心功能

### 🎯 接码页面
- UUID 随机账号 ID，接码链接不直接暴露手机号。
- 自动显示最新 Telegram 验证码，支持显示已保存的 2FA 密码。
- 显示会话状态（Session active / offline）与账号状态（活跃、冻结、删除、限流等）。
- 支持手动刷新与按需下载账号包。

### 🖥️ 设备指纹
- 内置多套真实设备指纹池：Windows、Linux、macOS、Android、iOS。
- 登录或导入时可选择：随机全部、指定平台、或固定默认指纹。
- 每个账号的指纹会随元数据持久化，并在导出 JSON 中保留。

### 🔑 API 平台支持
- 内置：Android、iOS、Desktop（Windows/Linux）、macOS、Nagram、Nicegram、Custom。
- Custom 模式可手动填写任意 `API_ID` / `API_HASH`，并记忆最近一次使用的凭据。
- 面板会对官方共享 API ID 可能带来的封号风险做出提示。

### 📱 手机号管理
- 独立 Phone 页面：逐条编辑已保存的手机号。
- 支持单个或全量检测真实手机号：连接 Telegram 读取账号实际号码，并与本地存储自动同步。
- 批量检测提供实时进度展示。

### 🔐 2FA 管理
- 独立 2FA 页面，直接向 Telegram 服务器真实修改两步验证密码。
- 支持逐账号修改，也支持勾选多个账号批量设置同一新密码。
- 修改成功后自动更新本地保存的 2FA 密码。

### 🗑️ Revoke / Delete
- **Revoke**：调用 Telegram 注销面板持有的会话，并删除本地文件；其他设备上的会话不受影响。
- **Delete**：仅删除服务器本地的 `.session` 与元数据文件，不会注销 Telegram 账号。
- 均支持单个操作与批量操作。

### 🏷️ Tag 标签
- 每个账号支持自定义标签，可随时在 Tags 页面批量编辑。
- 复制接码链接或导出账号时，可顺带为所选账号统一设置标签。
- 账号列表支持按区号与标签筛选。

### 🧭 账号列表
- Copy：复制接码链接。
- Open：打开接码页面。
- Revoke / Delete：处理本地或远端会话。
- 随机选择、全选、批量复制接码 Key、批量下载账号包。

### ⚡ 按需连接
脚本启动时不会主动连接所有 Telegram 账号，仅在访问接码页面、检测手机号、修改 2FA 或执行 Revoke 时才动态连接对应客户端，更适合低内存服务器。

---

## 📁 文件结构

```
tgapi/
├── main.py
└── sessions/
    ├── settings.json
    ├── UUID.session
    ├── UUID.meta.json
    └── ...
```

| 文件 | 用途 |
| --- | --- |
| `main.py` | 主程序 |
| `sessions/*.session` | Telethon 原生 Session |
| `sessions/*.meta.json` | 账号元数据（手机号、2FA、API、设备指纹、Tag、时间戳等） |
| `sessions/settings.json` | API 平台相关设置 |

账号文件使用随机 UUID 保存，不直接使用手机号作为服务器文件名。

---

## 🔒 管理员登录

管理面板使用单个管理员密码。默认密码：

```
admin123
```

修改 `main.py` 顶部：

```python
ADMIN_PASSWORD = "你的密码"
```

即可更换管理员密码。

---

## 💾 轻量运行

项目仅依赖：

- Python 标准库
- Telethon

不需要 Flask、FastAPI、Django、MySQL、Redis 或 Nginx。Web 服务直接使用 Python 内置 `http.server`，账号数据使用 Telethon SQLite Session + JSON，适合 NAT VPS、低内存 VPS 和轻量服务器。

---

[查看开源协议](https://github.com/SilentVGA/tgapi/blob/main/LICENSE) · [联系作者](https://t.me/lrlbl)
