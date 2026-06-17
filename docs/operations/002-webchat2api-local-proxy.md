# webchat2api 本机 ChatGPT Proxy 实验入口

更新时间：2026-06-17 23:10（Asia/Shanghai）

本页记录如何把 webchat2api 作为本机 OpenAI-compatible proxy 接入 Dashboard。

## 风险边界

- 仅用于本机实验，不作为默认 Provider。
- 不接入公共未知代理。
- 不建议使用主 ChatGPT / Business 账号。
- 不把 ChatGPT 密码、access token、cookie 粘贴到聊天或文档里。
- 账号凭据只在本机 webchat2api 管理页录入，并保存在 `.local/webchat2api` 下。
- 若出现 403、Turnstile、验证码、账号异常或风控提示，立即停用。

## 你需要准备什么

不要把账号密码、access token、cookie 或 session JSON 发给 Codex 聊天。

推荐准备：

- 一个低价值 ChatGPT 测试账号。
- 或者现有免费 ChatGPT 账号的 GPT access token。
- 不推荐 Business 账号或主账号。

如果使用 API 导入，把 token 放到本机临时文件，例如：

```text
.local/webchat2api/gpt-token.txt
```

文件只放一行 token。导入后可以删除该临时文件。

## 账号选择

优先级：

1. 新建低价值测试账号。
2. 如果必须在现有两个账号里选，优先免费账号。
3. 不建议使用 Business 账号。

Business 账号通常承载工作空间、历史、权限和更高价值身份。一旦 Web 逆向代理触发风控，理论上主要影响被使用的账号，但同一邮箱、同一登录身份、同一设备/IP、同一支付或组织关系可能带来关联风险。因此不要用 Business 账号做第一轮实验。

## 本地启动

```bash
chmod +x scripts/webchat2api/manage.sh
scripts/webchat2api/manage.sh setup
scripts/webchat2api/manage.sh start
scripts/webchat2api/manage.sh open
```

`setup` 会：

- 克隆或更新 `https://github.com/zqbxdev/webchat2api` 到 `.local/webchat2api`。
- 创建 `.local/webchat2api/.venv`。
- 安装 Python 依赖。
- 生成本机强随机 `LOGIN_SECRET` / `WEBCHAT2API_AUTH_KEY`。

默认不构建 web 管理界面，避免首次 `npm ci` 卡住；如需要 UI，再单独执行：

```bash
scripts/webchat2api/manage.sh setup-ui
```

生成的密钥保存在：

```text
.local/webchat2api/.jin10.env
```

该目录已加入 `.gitignore`，不要提交。

## Dashboard 配置

查看需要写入 dashboard `.env` 的配置：

```bash
scripts/webchat2api/manage.sh env
```

输出形如：

```bash
CHATGPT_PROXY_LABEL=ChatGPT Proxy
CHATGPT_PROXY_BASE_URL=http://127.0.0.1:5083/v1
CHATGPT_PROXY_API_KEY=...
CHATGPT_PROXY_MODEL=gpt-4o
CHATGPT_PROXY_MAX_TOKENS=1800
CHATGPT_PROXY_TEMPERATURE=0.2
```

把这些变量写入项目根目录 `.env` 后，Dashboard 的 Provider 下拉框会出现 `ChatGPT Proxy`。

## 账号录入

打开：

```text
http://127.0.0.1:5083
```

使用 `scripts/webchat2api/manage.sh env` 输出里的 `Admin login key` 登录。

在 webchat2api 管理页里添加 GPT 账号。不要把 token、cookie、session JSON 发到聊天里。

如果管理页未构建，也可以用本地 API 导入：

```bash
scripts/webchat2api/manage.sh import-gpt-token .local/webchat2api/gpt-token.txt
scripts/webchat2api/manage.sh accounts
```

导入成功后删除临时 token 文件：

```bash
rm .local/webchat2api/gpt-token.txt
```

## 固定 packet 测试

先用离线 A/B runner，不直接接入 Dashboard 自动后台调用：

```bash
.venv/bin/python scripts/run_provider_ab.py ar_20260609_030425_c9c7a9 --providers chatgpt_proxy
```

确认输出稳定后，再考虑在 `/analyze` 页面手动选择 `ChatGPT Proxy`。

## 常用命令

```bash
scripts/webchat2api/manage.sh status
scripts/webchat2api/manage.sh logs
scripts/webchat2api/manage.sh restart
scripts/webchat2api/manage.sh stop
```
