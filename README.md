# tgapi - 极简 Telegram 接码系统

一个单文件、无 Web 框架、专为低内存 NAT 机器设计的 Telegram 验证码接收网站。支持直接上传、下载 Telethon `.session` 文件。

![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python)
![License](https://img.shields.io/badge/License-MIT-green)
![Memory](https://img.shields.io/badge/Memory-✓128MB-orange?logo=linux)

## ⚡ 部署与使用

仅需一个第三方依赖，无需数据库，开箱即用：

```bash
apt install python3 python3-pip
pip install telethon
python3 main.py
```

> 注意：如果是受限的 Debian/Ubuntu 系统，请使用 `pip install telethon --break-system-packages`

启动后访问 `http://你的IP:8000/admin` 进入管理面板。

默认管理员密码为 `admin123`，请在代码顶部修改：

```python
ADMIN_PASSWORD = "admin123"
```

> 对 `.session` 文件的要求：
>
> - 必须是 Telethon 原生 SQLite 数据库文件。
> - 文件头必须以 `SQLite format 3` 开头，导入时会自动校验。
> - 不支持 StringSession 纯文本字符串。
> - 不支持 Pyrogram 的 `.session` 文件。
> - 不支持 JSON 格式的自定义 Session 文件。

---

## ✨ 核心功能

### 🎯 接码页面

- UUID 随机账号 ID，接码链接不会直接暴露手机号。
- 自动显示最新 Telegram 验证码。
- 支持显示账号保存的 2FA 密码。
- 支持手动刷新。
- 自动检测 Session 和账号状态。
- Session 下载功能默认开启。

### 📂 原生 `.session` 文件管理

每个账号独立保存为 Telethon 原生 `.session` 文件和 `.meta.json` 元数据文件。

支持：

- 后台直接上传 `.session` 文件。
- 手机号 + 验证码登录生成 `.session`。
- 删除服务器上的本地 Session。
- 下载原始 Telethon `.session` 文件。

删除账号只会删除服务器上的本地 `.session`、`.session-journal` 和 `.meta.json` 文件，不主动注销 Telegram 账号。

### ⬇️ Session 下载与文件名识别

Session 下载默认开启。

下载文件名格式：

```text
+123456789-2FA-API_ID-API_HASH.session
```

上传 `.session` 文件时，系统会自动尝试从文件名识别：

- 手机号
- 2FA
- API_ID
- API_HASH

系统从右侧识别 API_ID 和 API_HASH，因此 2FA 中包含 `-` 时也可以正常解析。

如果管理面板中手动填写了对应字段，则优先使用手动填写的数据。

### 🔑 API 平台支持

支持：

- Android
- iOS
- Desktop
- Desktop Windows
- Desktop Linux
- macOS
- Custom API

默认使用 Telegram Desktop API。添加账号和导入 Session 时均可选择 API 平台，Custom 模式可手动填写 API_ID 和 API_HASH。

### 🏷️ Tag 标签

每个账号支持自定义 Tag，用于后台区分和管理账号，并可随时修改。

### 🛠️ 轻量管理面板

每个账号提供：

- **Copy**：复制接码链接。
- **Go**：打开接码页面。
- **Delete**：删除服务器上的本地账号数据。
- **Session download**：开启或关闭 Session 下载。
- **Tag**：修改账号标签。

新登录和新导入的账号默认开启 Session 下载。

### ⚡ 按需连接

脚本启动时不会主动连接所有 Telegram 账号，仅在访问对应接码页面时动态连接对应客户端，更适合低内存服务器。

如果 Session 已失效、被其他客户端注销、无法授权或账号异常，接码页面会显示对应状态。

---

## 📁 文件结构

```text
tgapi/
├── main.py
└── sessions/
    ├── settings.json
    ├── UUID.session
    ├── UUID.meta.json
    └── ...
```

| 文件 | 用途 |
|---|---|
| `main.py` | 主程序 |
| `sessions/*.session` | Telethon 原生 Session |
| `sessions/*.meta.json` | 账号元数据 |
| `sessions/settings.json` | API 平台相关设置 |

账号文件使用随机 UUID 保存，不直接使用手机号作为服务器文件名。

---

## 🔒 管理员登录

管理面板使用单个管理员密码。

默认：

```text
admin123
```

修改 `main.py`：

```python
ADMIN_PASSWORD = "你的密码"
```

即可更换管理员密码。

---

## 💾 轻量运行

项目仅依赖：

- Python 标准库
- Telethon

不需要 Flask、FastAPI、Django、MySQL、Redis 或 Nginx。

Web 服务直接使用 Python 内置 `http.server`，账号数据使用 Telethon SQLite Session + JSON，适合 NAT VPS、低内存 VPS 和轻量服务器。

---

[查看开源协议](https://github.com/SilentVGA/tgapi/blob/main/LICENSE) · [联系作者](https://t.me/lrlbl)
