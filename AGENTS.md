# Jin10-Monitor 操作协议（核心版）

> 完整规则见 PROTOCOL.md，遇到复杂情况时引用。

---

## 项目基本信息

- 仓库：https://github.com/hangfo/jin10-monitor
- 分支：main（已与 origin/main 绑定）
- 本地路径：/Users/rich/jin10-monitor
- 虚拟环境：source .venv/bin/activate

---

## 一、绝对禁令（不得违反）

1. 禁止用 MCP API 直接写 GitHub 文件
2. 禁止未经我确认直接 commit 或 push
3. 禁止 force push（`--force` / `--force-with-lease`），除非我明确授权
4. 禁止 `git reset --hard` / `git clean -fd` / `git rebase --skip`，除非我明确授权
5. 禁止把 Telegram token、chat_id、API key、cookie 等任何真实密钥提交到 Git
6. 禁止把多个无关改动合并进一个 commit
7. 如果 diff 无法用非技术语言向普通人解释清楚，说明改动不清晰，不允许提交

---

## 二、每次开始修改前（必须执行）

```bash
git branch --show-current     # 确认在 main 分支
git status                    # 确认无未提交的脏文件
git pull --rebase             # 同步远程，防止历史分叉
git log --oneline -5          # 确认当前 HEAD
```

如果不在 main 分支，立即停止并告知我。

---

## 三、标准变更流程（按顺序执行）

```
1. 给我修改计划 → 2. 等我确认
→ 3. 改代码
→ 4. 给我 diff（含三层说明）→ 5. 等我确认
→ 6. 更新 CHANGELOG.md
→ 7. git add → git commit → git push
```

CHANGELOG 必须在 commit 前更新，确保两者内容一致。

---

## 四、diff 必须包含三层说明

**① 非技术总结（最重要）**
用产品/业务语言说明：改了什么、为什么、对系统有什么影响。
如果无法用普通语言解释，不允许提交。

**② 文件级说明**
逐文件说明：改了什么、是逻辑变更还是格式/文档变更、是否有删除逻辑。
如果涉及删除代码（超过 5 行），必须单独标注"【删除】"并说明删除理由，否则不允许提交。

**③ 风险评估**
是否影响：WebSocket / REST / Telegram 推送 / SQLite 历史库 / 启动方式 / 配置字段。
标明风险等级：低 / 中 / 高。

---

## 五、diff 分级规则

**小改动**（diff ≤ 30 行，不涉及核心链路）
→ 按标准流程执行，无需额外拆分。

**大改动**（满足以下任一条件）
- diff 超过 80 行
- 修改 WebSocket / REST / Telegram / SQLite 核心逻辑
- 删除或重构现有函数
- 修改启动方式 / 配置字段 / 依赖

→ 必须先拆分为多个步骤，逐步执行，每步等我确认后再继续。

---

## 六、commit 格式（必须遵守）

```
type(scope): 简短描述

问题：说明原因
修改：说明具体改动
影响：说明影响范围
验证：列出实际执行过的命令和结果
```

type 只能用：`fix` / `feat` / `refactor` / `chore` / `docs` / `test` / `perf`

commit body 四段缺一不可，缺失视为不合格 commit。

---

## 七、遇到异常立即停止

以下情况出现，立即停止，不得继续执行，不得自行处理：

- CONFLICT
- push rejected
- rebase 失败
- detached HEAD
- 本地与远程 HEAD 不一致
- git status 显示异常

停止后按格式汇报（见 PROTOCOL.md 第十三节），等我指示。

---

## 八、其他关键规则

- 启动新代码前，必须先 Ctrl+C 停掉旧进程
- 回滚只能用 `git revert <hash>`，禁止 `git reset --hard`
- 大改动开始前，记录当前 HEAD hash，作为回滚基准
- 每次 commit 前必须同步更新 CHANGELOG.md
- .env 只能提交 .env.example，真实密钥禁止入库
- **如果修改可能影响稳定性，必须优先保证系统可用，而不是代码优化或重构**
- 完整规则、测试要求、汇报格式见 PROTOCOL.md
