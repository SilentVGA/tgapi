# tgapi - 极简 Telegram 接码系统

一个单文件、无 Web 框架、专为低内存 NAT 机器设计的 Telegram 验证码接收网站。

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
> 注意：如果是受限的 Debian/Ubuntu 系统，请使用 pip install telethon --break-system-packages

启动后访问 `http://你的IP:8000/admin` 进入管理面板（默认密码 admin123，请在代码顶部修改）。


> 对.session文件的要求：
> 
> 必须是 Telethon 原生 SQLite 数据库文件。
> 
> 文件头必须以 SQLite format 3 开头（导入时会自动校验）。
> 
> 不支持 StringSession 纯文本字符串。
> 
> 不支持 Pyrogram 的 .session 文件（底层表结构不同）。
> 
> 不支持 JSON 格式的自定义 session 文件。

---

## ✨ 核心功能

### 🎯 现代化接码页面
- UUID 安全隔离：接码链接使用随机 UUID（如 /getcode/a1b2c3d4-...），不在 URL 中暴露手机号，防止遍历攻击。
- 现代 UI 设计：采用卡片式布局与渐变背景，验证码大字号高亮显示，2FA 密码独立展示，视觉清晰舒适。
- 纯手动刷新：接码页面无自动轮询，仅在用户点击“Refresh”时获取最新数据，极致节省服务器资源与客户端连接数。

### 📂 原生 .session 文件存储
- 告别 SQLite 数据库：每个账号独立保存为 Telethon 原生 .session 文件 + .meta.json 元数据文件。
- 格式完全兼容：生成的 .session 文件可直接被 tg-transformer、opentele 及任何标准 Telethon 脚本加载使用。
- 热插拔管理：支持在后台直接上传外部 .session 文件导入，也支持通过手机号+验证码在线登录生成。

### 🔑 灵活的 API 配置
- 官方 API 默认：内置 Telegram Desktop 官方 API（api_id=2040），添加账号时无需手动填写即可直接使用。
- 自定义 API 支持：同时保留 API_ID / API_HASH 输入框，兼容使用私有 API 生成的 session 文件。

### 🛠️ 轻量管理面板
- 一键操作：每个账号提供 Copy（复制接码链接）、Go（打开接码页）、Delete（删除账号）三个快捷按钮。
- 零框架依赖：完全基于 Python 内置 http.server 构建，无 Flask/FastAPI 等额外开销，128MB 内存机器轻松运行。
- 懒加载机制：脚本启动时不预连接任何账号，仅当接码页面被访问时才动态唤醒对应客户端，空闲时自动释放连接。

---
[查看开源协议](https://github.com/SilentVGA/tgapi/blob/main/LICENSE)
