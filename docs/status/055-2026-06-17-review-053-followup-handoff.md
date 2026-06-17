# 055 - Review 053 后续核查与收口

更新时间：2026-06-17 23:35（Asia/Shanghai）

当前分支：`main`

本轮核查 `/Users/rich/Downloads/jin10-review-053-diff.md` 以及用户粘贴的综合 Review 结论。Review 覆盖 `bab6c66` 到 `4f420a6` 两个提交，核心判断是历史遗留问题已全部归零，并提出 2 个 P1 小修与 1 个 P2 入口建议。

## 核查结论

- 17/17 历史遗留问题归零：接受该结论。
- P1：Provider timeline 圆点方向反了：接受并修复。
- P1：`/system/ws-initial` 缺少行动指南：接受并修复。
- P2：`/analyze/compare` 缺少入口：核查为误报。

## 本轮已修

### Provider timeline 左旧右新

`dashboard/templates/system.html`：

```jinja2
{% for call in provider_call_stats.recent_timeline | reverse %}
```

后端仍按最近活动时间 DESC 聚合，模板显示时反转为左旧右新，符合时间线阅读直觉。

### ws-initial 行动指南

`dashboard/templates/ws_initial_review.html` 新增 3 档只读提示：

- `newer_than_cursor == 0`：无需处理。
- `1 <= newer_than_cursor <= 3`：建议逐条确认。
- `newer_than_cursor > 3`：建议使用 `--catch-up` 手动补拉。

该页面仍只读，不触发 WebSocket、REST、补拉、Telegram 重试或发送。

## 不采纳 / 无需改动

### `/analyze/compare` 入口

Review 认为 compare 路由没有入口，但当前 `main` 已有：

- 顶部主导航：`dashboard/templates/base.html` 中 `/analyze/compare`。
- 历史页顶部按钮：`compare-top-btn`。
- 历史页勾选两条后的底部对比栏：`goCompare()` 生成 `/analyze/compare?ids=...`。
- 测试覆盖：`tests/test_dashboard_analysis.py` 已检查 `compare-top-btn` 与 compare 路由/模板。

因此本轮不重复新增入口，避免 UI 噪声和重复路径。

## 后续开发计划

### 立即优先

1. 继续 Gemini vs GLM 固定 packet A/B。
2. 将结果按机制驱动、方向准确、过度归因、JSON 稳定性和耗时记录。
3. 只在有真实样本后再决定是否重构 GLM Prompt。

### 暂缓

1. webchat2api / ChatGPT proxy：已封存在 `experiment/chatgpt-proxy-provider` 分支，暂不进入 `main`。
2. 公共免费 ChatGPT API / proxy：不建议接入。
3. Anthropic Provider：继续暂缓。

## 验证

已执行：

```bash
.venv/bin/python -m py_compile dashboard/app.py dashboard/analysis_db.py
.venv/bin/python -m pytest tests/test_dashboard_analysis.py -q
.venv/bin/python -m pytest -q
git diff --check
```

结果见本轮最终回复。
