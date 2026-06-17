# 054 - ChatGPT Proxy 实验封存与主线回退交接

更新时间：2026-06-17 23:10（Asia/Shanghai）

当前分支：`experiment/chatgpt-proxy-provider`

本轮从 Gemini vs GLM 小样本 A/B 继续，发现 GLM 主要失败原因不是答案质量，而是 GLM-4.7 默认开启 thinking 后把输出放进 `reasoning_content`，导致 OpenAI-compatible `content` 为空并触发 `finish_reason=length`。随后又尝试把 ChatGPT 手工流通过 webchat2api 变成本机 OpenAI-compatible proxy。由于账号安全、条款风险和代理稳定性仍需独立验证，本轮将 webchat2api 作为技术债封存，不并入 `main` 主线。

## 已完成

- 新增 `scripts/run_provider_ab.py`：
  - 读取历史 `analysis_runs.id` 对应的固定 packet。
  - 自动加载项目 `.env`。
  - 可调用 `gemini`、`compatible`、`chatgpt_proxy` 等 provider。
  - 输出原始 JSON 与 `summary.md` 到 `exports/provider_ab_runs/`。
  - 不写业务历史库、不触发采集、不请求金十 REST、不重发 Telegram。
- 参数化 `OpenAICompatibleProvider`：
  - 仍兼容现有 `COMPAT_LLM_*`。
  - 支持独立 env prefix，用于实验性 `CHATGPT_PROXY_*`。
  - 对 GLM / BigModel / Zhipu / Z.ai 自动关闭 thinking。
  - 可用 `COMPAT_LLM_THINKING=auto/enabled/disabled` 覆盖。
- 新增 `chatgpt_proxy` Provider slot：
  - `CHATGPT_PROXY_LABEL`
  - `CHATGPT_PROXY_BASE_URL`
  - `CHATGPT_PROXY_API_KEY`
  - `CHATGPT_PROXY_MODEL`
  - `CHATGPT_PROXY_MAX_TOKENS`
  - `CHATGPT_PROXY_TEMPERATURE`
  - 默认关闭；必须同时配置 base URL 和 key 才可用。
- 新增 `scripts/webchat2api/manage.sh`：
  - 克隆 / 更新 `zqbxdev/webchat2api` 到 `.local/webchat2api`。
  - 创建本机 Python venv。
  - 生成强随机 `LOGIN_SECRET` / `WEBCHAT2API_AUTH_KEY`。
  - 通过 launchd 托管本机 `127.0.0.1:5083`。
  - 输出 Dashboard `.env` 片段。
  - 支持从本机 token 文件导入 GPT access token，不把 token 放进命令行参数或聊天记录。
- 新增 `docs/operations/002-webchat2api-local-proxy.md`：
  - 记录账号安全边界、账号选择建议、启动命令、导入方式和固定 packet 测试方式。
- `.gitignore` 新增 `.local/`，避免提交 webchat2api 源码、账号池、密钥和本机运行数据。

## 真实观察

- Gemini：
  - 答案通常更聚焦，弱证据时更克制。
  - 免费端在高峰期会出现 `503 high demand`。
- GLM：
  - 关闭 thinking 前，常见 `reasoning_content` 消耗 token、`content` 为空。
  - 关闭 thinking 后，10/40 与 7/38 样本可以稳定返回正文，但仍有 429 和较长耗时。
  - 适合作为低成本备用 provider，不建议完全替代 Gemini。
- webchat2api：
  - 本机后端可启动并通过 `/health`。
  - 当前账号池为空，`chatgpt_proxy` 调用会到达本机 proxy，但上游返回 `502 upstream_error`。
  - 尚未导入测试 ChatGPT 账号，未完成真实 ChatGPT A/B。

## 风险判断

- webchat2api 是 Web 能力逆向封装，存在账号受限、封禁、验证码、Turnstile 和条款风险。
- 不建议使用 Business / 主 ChatGPT 账号。
- 推荐仅使用低价值测试账号或免费账号。
- 不接公共未知 proxy，不提交 token / cookie / session。
- 即便使用独立 Gmail，仍可能因设备、IP、恢复信息、浏览器环境等因素存在关联风险。

## 当前封存策略

- 当前分支保留：`experiment/chatgpt-proxy-provider`
- 不 merge 到 `main`。
- 不提交 `exports/`。
- `.local/webchat2api` 保持本机忽略目录，不入库。
- `main` 继续之前的主线开发。

## 下一步推荐

### 立即做

1. 提交并 push 当前实验分支，作为技术债快照。
2. 切回 `main`。
3. `git pull --rebase` 同步远端。
4. 确认 `main` 工作区干净。
5. 继续主线任务：Provider A/B 观察、历史管理和系统只读诊断，不把 ChatGPT proxy 混入主线。

### 暂缓

1. webchat2api 真实账号导入。
2. `chatgpt_proxy` 进入 Dashboard 默认调用。
3. 公共免费 ChatGPT API / proxy 接入。
4. 使用 Business ChatGPT 账号。

### 后续若恢复实验

1. 新建或使用低价值免费 ChatGPT 测试账号。
2. 在本机生成 token 文件，例如 `.local/webchat2api/gpt-token.txt`。
3. 执行：

```bash
scripts/webchat2api/manage.sh import-gpt-token .local/webchat2api/gpt-token.txt
scripts/webchat2api/manage.sh accounts
.venv/bin/python scripts/run_provider_ab.py ar_20260609_030425_c9c7a9 --providers chatgpt_proxy
```

4. 导入后删除临时 token 文件。
5. 只用固定 packet 做离线 A/B，不直接进入 `/analyze` 自动后台调用链。

## 验证

已执行：

```bash
zsh -n scripts/webchat2api/manage.sh
.venv/bin/python -m py_compile dashboard/providers/base.py dashboard/providers/compatible_provider.py scripts/run_provider_ab.py
.venv/bin/python -m pytest tests/test_dashboard_analysis.py -q
.venv/bin/python -m pytest -q
git diff --check
```

结果：

- `tests/test_dashboard_analysis.py`: `72 passed`
- 全量测试：`214 passed`
- `git diff --check`: passed

## 换新 session 提示

复制给下一轮：

```text
继续 /Users/rich/jin10-monitor 项目。

先读取：
1. AGENTS.md
2. docs/status/054-2026-06-17-chatgpt-proxy-experiment-debt-handoff.md
3. docs/status/053-2026-06-11-review-052-followup-handoff.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- webchat2api / chatgpt_proxy 已在 experiment/chatgpt-proxy-provider 分支作为技术债封存，暂不进 main。
- GLM compatible provider 的 thinking disabled 修复和离线 A/B runner 已在该分支验证；是否 cherry-pick 到 main 需单独决策。
- main 继续原主线：Provider 小样本 A/B、历史管理、/system 只读诊断，不接公共 ChatGPT proxy，不使用 Business 账号。
- exports/ 和 .local/ 都是本地产物，不提交。

下一步：
1. 确认 main 是否干净并同步 origin/main。
2. 继续主线开发，不恢复 webchat2api，除非明确要求。
3. 若要恢复 ChatGPT proxy 实验，只用低价值测试账号和固定 packet 离线 A/B。
```
