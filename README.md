# tgapi - 极简 Telegram 接码系统

一个单文件、无 Web 框架、专为低内存 NAT 机器设计的 Telegram 验证码接收网站。[如何使用？](https://github.com/FalseFor/tgapi/edit/main/README.md#-%E5%BF%AB%E9%80%9F%E4%BD%BF%E7%94%A8)

![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python)
![License](https://img.shields.io/badge/License-MIT-green)
![Memory](https://img.shields.io/badge/Memory-✓128MB-orange?logo=linux)

## ✨ 核心特性

###  极致轻量 & 懒加载
- **零框架依赖**：仅依赖 `telethon`，完全使用 Python 内置的 `http.server` 和 `sqlite3` 构建。
- **内存占用极低**：采用“懒加载”策略。脚本启动时**不连接**任何 Telegram 账号，仅在用户访问特定接码页面时才动态唤醒客户端。128MB 内存的 NAT 机器也能轻松运行。

### ️ 智能状态与验证码检测
- **精准封号检测**：自动向 `@SpamBot` 发送 `/start`，精准识别账号状态（正常 / 掉线 / 死亡封号）。
- **智能验证码提取**：优化正则匹配逻辑，兼容“验证码已发送至邮箱”等提示文本，仅提取并显示**最新一条**验证码，拒绝历史消息干扰。
- **2FA 支持**：自动记录并显示账号的 2FA 密码。


### 🔒 安全与隔离
- **UUID 隔离**：每个 Telegram 账号生成独立的 UUID 接码路径，互不干扰。
- **面板保护**：内置简单的 Cookie 会话验证与密码保护。

---

##  环境要求

仅需一个第三方库：

```bash
pip install telethon
```
*(如果是受限的 Debian/Ubuntu 系统，请使用 `pip install telethon --break-system-packages`)*

---

## ⚡ 快速使用
1. 修改 `main.py` 顶部的配置：
   ```python
   ADMIN_PASSWORD = "你的面板密码"
   SERVER_PORT = 8000  # 监听端口
   ```

2. 运行脚本：
   ```bash
   python3 main.py
   ```

3. 前往`my.telegram.org`登录账号，前往[API获取页面](https://my.telegram.org/apps)获取API ID、API Hash

4. 访问管理面板：
   - 地址：`http://你的IP:端口/admin`
   - 在面板中添加 Telegram 账号（需填入 Phone、API ID、API Hash）。
