# Jin10-Monitor 完整操作协议（参考版）

> 日常操作以 AGENTS.md 为准。本文件在大改动、异常处理、复杂情况时引用。

---

## 项目信息

- 仓库：https://github.com/hangfo/jin10-monitor
- 分支：main（已与 origin/main 绑定）
- 本地路径：/Users/rich/jin10-monitor
- 虚拟环境：source .venv/bin/activate
- 当前 HEAD：fa37968（Fix Jin10 websocket keepalive and important alerts）

---

## 一、Git 基本规则

所有代码变更必须走标准 Git 流程：

```bash
git branch --show-current     # 确认分支
git status                    # 确认状态
git pull --rebase             # 同步远程
# 修改代码
git diff                      # 展示给我看
# 等我确认
# 更新 CHANGELOG.md
git add .
git commit -m "..."
git push
```

绝对禁止：
- MCP API 直接创建、修改、覆盖 GitHub 文件
- 直接在 GitHub 网页端修改代码
- `git push --force` / `git push --force-with-lease`（除非我明确授权）
- `git reset --hard` / `git clean -fd` / `git rebase --skip`（除非我明确授权）
- `git rebase --continue` 遇到冲突后自行处理

---

## 二、每次开始修改前必须检查

```bash
git branch --show-current     # 必须是 main
git status                    # 必须是 clean（或已知的未跟踪文件）
git pull --rebase             # 同步远程，防止历史分叉
git log --oneline -5          # 汇报当前最近 5 条 commit
```

如果不在 main 分支，立即停止，告知我当前分支，等待指示。

---

## 三、修改前必须先给方案

在修改代码前，先给我一份修改计划：

1. 本次要解决什么问题
2. 可能涉及哪些文件
3. 是否影响核心链路（WebSocket / REST / Telegram / SQLite）
4. 是否需要新增依赖
5. 是否需要改配置 / .env.example
6. 是否需要更新 README / CHANGELOG
7. 风险等级：低 / 中 / 高
8. 验证方式

只有我确认后，才可以改代码。

---

## 四、diff 审核规则

每次改完后，必须先给我看 diff，不允许直接 commit。

### ① 非技术总结（必须，最重要）

用产品/业务语言说明：
- 这次改了什么
- 为什么要改
- 对系统运行有什么影响
- 是否影响现有使用方式

**如果无法用普通语言解释清楚，说明改动本身不清晰，不允许提交。**

### ② 文件级说明（必须）

逐文件说明：
- 文件名
- 改了什么内容
- 是逻辑变更、配置变更、文档变更，还是格式变更
- 是否有删除逻辑：**如果删除超过 5 行代码，必须单独标注【删除】并说明删除理由，否则不允许提交**
- 是否有重构

### ③ 核心链路影响（必须）

明确说明是否影响：
- WebSocket 实时接收 / keepalive / reconnect 逻辑
- REST 轮询
- 关键词匹配
- Telegram 推送
- SQLite 历史库
- .env 配置字段
- 启动命令
- 错误处理逻辑

### ④ 风险评估（必须）

- 潜在风险
- 最坏情况会出什么问题
- 如何回滚（只能用 `git revert <hash>`）
- 如何验证没有破坏旧功能
- 风险等级：低 / 中 / 高

### ⑤ 测试结果（必须）

必须列出实际执行过的命令和输出，例如：

```bash
python3 -m py_compile jin10_monitor.py     # 语法检查
python jin10_monitor.py --once --limit 5   # REST 一次性抓取
python jin10_monitor.py --history 巴菲特 --history-limit 5   # 历史查询
python jin10_monitor.py                    # WebSocket 实时运行（运行后说明连接状态）
```

不能只说"应该没问题"。如果没有 Telegram 配置，必须注明："未配置 Telegram，只验证控制台输出。"

---

## 五、diff 分级控制

### 小改动（直接执行）

满足全部条件：
- diff ≤ 30 行
- 不涉及 WebSocket / REST / Telegram / SQLite 核心链路
- 不涉及启动方式 / 配置字段 / 依赖

→ 按标准流程执行，提供三层 diff 说明后等我确认。

### 中改动（需拆分说明）

满足任一条件：
- diff 30～80 行
- 涉及核心链路但改动局限于单一模块

→ 先给方案，说明影响范围，等我确认后执行。

### 大改动（必须拆分步骤）

满足任一条件：
- diff 超过 80 行
- 修改 WebSocket / REST / Telegram / SQLite 核心逻辑
- 删除或重构现有函数
- 修改启动方式 / 配置字段 / 依赖 requirements.txt
- 修改消息过滤规则 / 历史存储格式

必须拆分为多个步骤，格式如下：

```
Step 1：做什么
影响文件：
风险等级：
验证方式：

Step 2：做什么
影响文件：
风险等级：
验证方式：
```

每步等我确认后再继续，禁止一次性完成大改动。

---

## 六、commit 规范

每个逻辑变更必须单独一个 commit，禁止把多个无关改动合并。

### commit message 格式

```
type(scope): 简短描述（不超过 60 字符）

问题：
- 说明原问题

修改：
- 说明具体改动

影响：
- 说明影响范围

验证：
- 列出实际执行的命令和结果
```

### 允许的 type

| type | 用途 |
|---|---|
| fix | 修复 bug |
| feat | 新功能 |
| refactor | 重构（不改变功能） |
| chore | 工程配置、依赖 |
| docs | 文档 |
| test | 测试 |
| perf | 性能优化 |

### 示例

```
fix(websocket): add keepalive reconnect handling

问题：
- WebSocket 长时间运行后可能断开，导致实时消息停止接收。

修改：
- 增加 keepalive ping 机制。
- 增加异常断开后的自动重连处理。
- 保留 REST 轮询作为兜底。

影响：
- 提高实时监控稳定性。
- 不改变启动命令。
- 不影响历史查询功能。

验证：
- python3 -m py_compile jin10_monitor.py ✅
- python jin10_monitor.py --once --limit 5 ✅
- python jin10_monitor.py 运行 10 分钟，连接稳定，无异常报错 ✅
```

commit body 四段（问题 / 修改 / 影响 / 验证）缺一不可，缺失视为不合格 commit，不允许推送。

---

## 七、CHANGELOG 规则

必须维护 CHANGELOG.md。如果没有，先创建。

每次 commit 前必须追加更新，按日期倒序，只能追加不能覆盖历史。

### 格式

```markdown
# Changelog

## 2026-05-03

### Fix
- 修复 WebSocket keepalive 断连问题。系统长时间运行时不再中断实时消息接收。

### Feature
- 增加历史查询功能，支持按关键词检索过往快讯。

### Refactor
- 重构消息过滤逻辑，提高代码可读性，不改变功能。

### Chore
- 更新依赖，修复 requirements.txt 版本锁定。
```

要求：
- 每条必须用普通人能看懂的语言描述
- 技术修改必须补充一句业务影响说明
- 不要写"update files"/ "fix bugs"这类无意义描述

---

## 八、README 更新规则

以下情况必须同步更新 README.md：
- 启动命令变化
- 新增 / 删除参数
- .env 配置字段变化
- 依赖变化
- 历史查询方式变化
- Telegram 行为变化
- 运行流程变化

README 更新需进入 diff 审核，与代码改动一起提交。

---

## 九、配置与 Secrets 规则

- .env 文件禁止提交（已在 .gitignore）
- .env.example 可以提交，只包含字段名和示例值，不含真实密钥
- 新增配置项时必须：
  1. 更新 .env.example
  2. 更新 README.md
  3. 更新 CHANGELOG.md
  4. 在 diff 说明中解释默认值和影响

禁止提交：Telegram token / chat_id / API key / cookie / session / 任何真实账户信息。发现即撤销 commit，用 `git revert` 处理。

---

## 十、依赖规则

修改 requirements.txt 时必须说明：
1. 新增了什么依赖
2. 为什么需要，是否有更轻量的替代方案
3. 是否影响部署
4. 是否需要重新 pip install

禁止无理由新增大型依赖。

---

## 十一、测试规则

每次提交前至少执行：

```bash
python3 -m py_compile jin10_monitor.py   # 必做，语法检查
```

涉及 REST：
```bash
python jin10_monitor.py --once --limit 5
```

涉及历史库：
```bash
python jin10_monitor.py --history 巴菲特 --history-limit 5
```

涉及 WebSocket（运行一段时间后说明）：
```bash
python jin10_monitor.py
# 说明：是否连接成功 / 是否登录成功 / 是否收到消息 / 是否有异常报错 / 是否触发 Telegram
```

启动新代码前，必须先 Ctrl+C 停掉旧进程。

---

## 十二、回滚规则

只能用 `git revert`，禁止 `git reset --hard`：

```bash
git revert <commit_hash>   # 生成一个新 commit 撤销指定改动，历史保留
git push
```

需要回滚到某个里程碑版本时，先查 tag：

```bash
git tag
git revert <tag>
```

---

## 十三、遇到异常时汇报格式

出现以下情况立即停止，不得继续：
- CONFLICT / rebase 失败 / push rejected / detached HEAD / branch 不一致

汇报格式：

```
【异常类型】
例如：git conflict / push rejected / test failed / runtime error

【当前命令】
贴出刚刚执行的命令

【错误摘要】
用中文解释错误含义

【受影响文件】
列出相关文件

【可选方案】
给出 1～3 个可选方案

【推荐方案】
说明推荐哪个以及原因
```

不要直接继续执行，等我指示。

---

## 十四、每次完成后汇报格式

```
【完成摘要】
本次改动的非技术说明

【Commit】
abc1234 fix(websocket): ...

【已修改文件】
- jin10_monitor.py
- CHANGELOG.md

【验证】
- python3 -m py_compile jin10_monitor.py ✅
- python jin10_monitor.py --once --limit 5 ✅

【Push】
已推送到 origin/main ✅

【CHANGELOG】
已更新 ✅

【README】
无需更新 / 已更新（说明改了什么）

【风险】
低。未改变启动方式，未修改配置字段。

【后续待办】
如有，列出下一步建议
```

---

## 十五、解释风格要求

每次解释必须同时包含：
1. 非技术版说明（像给产品经理 / 投资研究员解释，不假设对方能看懂代码）
2. 技术版说明
3. 风险说明
4. 验证说明

如果无法用非技术语言讲清楚，不允许提交。

---

## 十六、长期目标与优先级

核心优先级（按重要性排序）：
1. 稳定接收消息，不漏重要快讯
2. Telegram 推送可靠
3. 本地历史可查
4. 出错能自动恢复
5. Git 历史清晰，每次改动可追踪、可回滚、可理解
6. 代码可读性

原则：
- 不为"代码好看"牺牲稳定性
- 不为"重构"引入不必要风险
- 宁可保守，不要激进
- **如果修改可能影响稳定性或数据正确性，必须优先保证系统可用，而不是代码优化**
- 大改动开始前，记录当前 HEAD hash 作为回滚基准
