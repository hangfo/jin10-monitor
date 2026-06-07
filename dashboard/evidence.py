"""Evidence packet builder for the manual AI dashboard workflow.

This module reads only the local business SQLite database through the dashboard
readonly connection. It does not call Jin10 REST, market data APIs, Telegram, or
any model API.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from jin10_monitor import (
    HIGH_PRIORITY,
    PRIORITY_HIGH,
    PRIORITY_IMPORTANT,
    format_cursor_datetime,
    parse_cursor_datetime,
    score_keywords,
)

from .db import open_readonly_connection


ASSET_KEYWORD_MAP: dict[str, list[str]] = {
    "BTC": ["比特币", "Bitcoin", "BTC", "加密货币", "crypto", "数字货币"],
    "ETH": ["以太坊", "Ethereum", "ETH", "以太"],
    "黄金": ["黄金", "Gold", "贵金属", "XAU", "黄金期货"],
    "石油": ["原油", "石油", "WTI", "Brent", "布伦特", "OPEC", "能源"],
    "美元": ["美元", "DXY", "美元指数", "美元汇率"],
    "美股": ["纳指", "标普", "道琼斯", "纳斯达克", "S&P", "Nasdaq", "美股"],
    "美联储": ["美联储", "Fed", "联储", "鲍威尔", "Powell", "FOMC", "加息", "降息", "利率"],
    "通胀": ["通胀", "CPI", "PCE", "通货膨胀", "物价"],
    "就业": ["非农", "就业", "失业率", "NFP", "劳工"],
}

MACRO_KEYWORDS = [
    "美联储",
    "Fed",
    "通胀",
    "CPI",
    "利率",
    "特朗普",
    "Trump",
    "关税",
    "地缘",
    "战争",
    "制裁",
    "美国",
    "中国",
]

RATE_LIQUIDITY_KEYWORDS = [
    "美联储",
    "Fed",
    "FOMC",
    "鲍威尔",
    "Powell",
    "加息",
    "降息",
    "利率",
    "收益率",
    "美元",
    "美元指数",
    "非农",
    "NFP",
    "就业",
    "失业率",
    "JOLTS",
    "PMI",
    "通胀",
    "CPI",
    "PCE",
    "流动性",
]

GEO_ENERGY_KEYWORDS = [
    "伊朗",
    "以色列",
    "霍尔木兹",
    "中东",
    "战争",
    "停火",
    "制裁",
    "核",
    "油价",
    "原油",
    "油轮",
    "能源",
    "封锁",
]

CAUSAL_KEYWORDS = [
    "预期",
    "概率",
    "远超预期",
    "强于预期",
    "弱于预期",
    "走强",
    "走弱",
    "上涨",
    "下跌",
    "风险偏好",
    "避险",
    "风险资产",
    "流动性",
    "收益率",
    "美元",
    "通胀",
    "加息",
    "降息",
    "制裁",
    "封锁",
]

DATA_SHOCK_KEYWORDS = [
    "远超预期",
    "强于预期",
    "低于预期",
    "弱于预期",
    "意外",
    "概率",
    "录得",
    "公布",
]

SUMMARY_PATTERNS = [
    "汇总",
    "一览",
    "夜盘要闻",
    "每日",
    "预告",
    "日程",
    "DeepTalk",
    "大师复盘",
]

LIGHT_SUMMARY_PATTERNS = ["整理"]

NOISE_PATTERNS = [
    "广告",
    "开户",
    "直播",
    "订阅",
]

CRYPTO_ASSETS = {"BTC", "ETH"}

PRIORITY_WEIGHT = {
    PRIORITY_IMPORTANT: 4,
    PRIORITY_HIGH: 2,
    "T1_NORMAL": 1,
    "T0_NONE": 0,
}

MAX_EVIDENCE = 40
CONTEXT_PADDING_MINUTES = 30
SCORE_SCALE = 120
DEFAULT_SELECTED_MAX = 10
DEFAULT_SELECTED_MIN = 4
DEFAULT_SELECT_SCORE = 0.35
DEFAULT_FALLBACK_SCORE = 0.25
SUMMARY_SELECT_SCORE = 0.7


def known_assets() -> list[str]:
    return [*ASSET_KEYWORD_MAP.keys(), "其他"]


def resolve_asset_keywords(asset: str) -> list[str]:
    text = str(asset or "").strip()
    if not text or text == "其他":
        return []
    return ASSET_KEYWORD_MAP.get(text.upper(), [text])


def build_evidence_for_preview(
    asset: str,
    window_start: str,
    window_end: str,
) -> tuple[list[dict[str, Any]], str | dict[str, object]]:
    start_dt = parse_cursor_datetime(str(window_start or ""))
    end_dt = parse_cursor_datetime(str(window_end or ""))
    if not start_dt or not end_dt:
        return [], "invalid_time_window"
    if end_dt <= start_dt:
        return [], "end_before_start"
    evidence = build_evidence_packet(asset, start_dt, end_dt)
    return evidence, {
        "source": "local_sqlite_only",
        "label": "local_sqlite_only",
        "jin10_rest_called": False,
        "market_data_called": False,
    }


def build_evidence_packet(
    asset: str,
    window_start: datetime,
    window_end: datetime,
    *,
    extra_keywords: list[str] | None = None,
) -> list[dict[str, Any]]:
    asset_keywords = resolve_asset_keywords(asset)
    for keyword in extra_keywords or []:
        if keyword and keyword not in asset_keywords:
            asset_keywords.append(keyword)

    query_start = format_cursor_datetime(window_start - timedelta(minutes=CONTEXT_PADDING_MINUTES))
    query_end = format_cursor_datetime(window_end + timedelta(minutes=CONTEXT_PADDING_MINUTES))
    rows = fetch_window(query_start, query_end)
    scored = [
        score_row(row, asset_keywords, asset=asset, window_start=window_start, window_end=window_end)
        for row in rows
    ]
    apply_diversity_penalty(scored)
    filtered = [
        row
        for row in scored
        if row["relevance_score"] > 0
        or row["priority_level"] in {PRIORITY_IMPORTANT, PRIORITY_HIGH}
    ]
    filtered.sort(
        key=lambda row: (
            row["relevance_score"],
            row.get("published_at") or "",
        ),
        reverse=True,
    )
    packet = filtered[:MAX_EVIDENCE]
    apply_default_selection(packet)
    return packet


def fetch_window(query_start: str, query_end: str) -> list[dict[str, Any]]:
    with open_readonly_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, published_at, title, content, priority_level, important,
                   has_bold, news_source, source_url, pic_url
            FROM flash_history
            WHERE published_at BETWEEN ? AND ?
            ORDER BY published_at ASC, created_at ASC
            """,
            (query_start, query_end),
        ).fetchall()
    return [dict(row) for row in rows]


def score_row(
    row: dict[str, Any],
    asset_keywords: list[str],
    *,
    asset: str = "",
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> dict[str, Any]:
    text = f"{row.get('title') or ''} {row.get('content') or ''}".strip()
    asset_count, asset_hits = score_keywords(text, asset_keywords)
    macro_count, macro_hits = score_keywords(text, MACRO_KEYWORDS)
    high_count, high_hits = score_keywords(text, list(HIGH_PRIORITY))
    rate_count, rate_hits = score_keywords(text, RATE_LIQUIDITY_KEYWORDS)
    geo_count, geo_hits = score_keywords(text, GEO_ENERGY_KEYWORDS)
    causal_count, causal_hits = score_keywords(text, CAUSAL_KEYWORDS)
    shock_count, shock_hits = score_keywords(text, DATA_SHOCK_KEYWORDS)
    priority_level = str(row.get("priority_level") or "T0_NONE")
    priority_points = {PRIORITY_IMPORTANT: 14, PRIORITY_HIGH: 8, "T1_NORMAL": 3}.get(priority_level, 0)
    crypto_asset = str(asset or "").upper() in CRYPTO_ASSETS
    direct_points = min(asset_count, 2) * (10 if crypto_asset else 16)
    macro_points = min(rate_count, 4) * (9 if crypto_asset else 5)
    geo_points = min(geo_count, 4) * (7 if crypto_asset else 4)
    causal_points = min(causal_count, 4) * 6
    high_points = min(high_count, 3) * 4
    quality_points = min(shock_count, 2) * 5
    flag_points = (4 if row.get("important") else 0) + (2 if row.get("has_bold") else 0)
    substantive_points = (
        direct_points
        + macro_points
        + geo_points
        + causal_points
        + high_points
        + priority_points
        + quality_points
    )
    time_points = time_proximity_points(row.get("published_at"), window_start, window_end) if substantive_points else 0

    title = str(row.get("title") or "")
    content = str(row.get("content") or "")
    title_content = f"{title} {content}"
    summary_penalty = 28 if contains_any(title_content, SUMMARY_PATTERNS) else 0
    light_summary_penalty = 12 if not summary_penalty and contains_any(title_content, LIGHT_SUMMARY_PATTERNS) else 0
    noise_penalty = 24 if contains_any(title_content, NOISE_PATTERNS) else 0
    vague_penalty = 6 if not title and len(content) < 24 else 0
    raw_score = (
        direct_points
        + macro_points
        + geo_points
        + causal_points
        + high_points
        + priority_points
        + quality_points
        + flag_points
        + time_points
        - summary_penalty
        - light_summary_penalty
        - noise_penalty
        - vague_penalty
    )
    relevance_score = round(max(0, min(raw_score, SCORE_SCALE)) / SCORE_SCALE, 3)
    if summary_penalty:
        relevance_score = min(relevance_score, 0.72)
    elif light_summary_penalty:
        relevance_score = min(relevance_score, 0.82)
    matched_keywords = list(dict.fromkeys(asset_hits + high_hits + rate_hits + geo_hits + causal_hits + shock_hits + macro_hits))
    score_components = {
        "direct_asset": direct_points,
        "macro_liquidity": macro_points,
        "geo_energy": geo_points,
        "causal_language": causal_points,
        "priority": priority_points,
        "event_quality": quality_points,
        "time_proximity": time_points,
        "penalty": -(summary_penalty + light_summary_penalty + noise_penalty + vague_penalty),
    }
    score_reasons = build_score_reasons(
        score_components,
        summary_penalty=summary_penalty,
        light_summary_penalty=light_summary_penalty,
        noise_penalty=noise_penalty,
        vague_penalty=vague_penalty,
    )
    news_id = str(row.get("id") or "")
    return {
        **row,
        "news_id": news_id,
        "relevance_score": relevance_score,
        "matched_keywords": matched_keywords,
        "score_components": score_components,
        "score_reasons": score_reasons,
        "selected": False,
    }


def apply_default_selection(rows: list[dict[str, Any]]) -> None:
    selected: set[int] = set()
    for index, row in enumerate(rows):
        score = float(row.get("relevance_score") or 0)
        summary_like = is_summary_like(row)
        if score >= DEFAULT_SELECT_SCORE and (not summary_like or score >= SUMMARY_SELECT_SCORE):
            selected.add(index)
        if len(selected) >= DEFAULT_SELECTED_MAX:
            break

    if len(selected) < DEFAULT_SELECTED_MIN:
        for index, row in enumerate(rows):
            if index in selected:
                continue
            score = float(row.get("relevance_score") or 0)
            if score >= DEFAULT_FALLBACK_SCORE and not is_noise_like(row) and not is_summary_like(row):
                selected.add(index)
            if len(selected) >= DEFAULT_SELECTED_MIN:
                break

    for index, row in enumerate(rows):
        score = float(row.get("relevance_score") or 0)
        summary_like = is_summary_like(row)
        row["selected"] = index in selected
        if row["selected"]:
            row["selection_note"] = "默认选中"
        elif summary_like:
            row["selection_note"] = "汇总/预告默认不选"
        elif score < DEFAULT_FALLBACK_SCORE:
            row["selection_note"] = "低相关默认不选"
        else:
            row["selection_note"] = "候选未选，可手动加入"


def is_summary_like(row: dict[str, Any]) -> bool:
    reasons = {str(reason) for reason in row.get("score_reasons") or []}
    return bool({"汇总/预告降权", "整理类内容降权"} & reasons)


def is_noise_like(row: dict[str, Any]) -> bool:
    reasons = {str(reason) for reason in row.get("score_reasons") or []}
    return bool({"噪声降权", "信息量不足降权"} & reasons)


def contains_any(text: str, patterns: list[str]) -> bool:
    lowered = str(text or "").lower()
    return any(pattern.lower() in lowered for pattern in patterns)


def time_proximity_points(
    published_at: object,
    window_start: datetime | None,
    window_end: datetime | None,
) -> int:
    if not window_start or not window_end:
        return 6
    published = parse_cursor_datetime(str(published_at or ""))
    if not published:
        return 0
    if window_start <= published <= window_end:
        return 12
    distance = min(abs(published - window_start), abs(published - window_end))
    minutes = distance.total_seconds() / 60
    if minutes <= 10:
        return 9
    if minutes <= 30:
        return 5
    return 2


def build_score_reasons(
    components: dict[str, int],
    *,
    summary_penalty: int,
    light_summary_penalty: int,
    noise_penalty: int,
    vague_penalty: int,
) -> list[str]:
    reasons: list[str] = []
    if components["macro_liquidity"] >= 18:
        reasons.append("利率/美元/流动性传导")
    elif components["macro_liquidity"]:
        reasons.append("宏观流动性相关")
    if components["geo_energy"] >= 14:
        reasons.append("地缘/能源风险传导")
    elif components["geo_energy"]:
        reasons.append("地缘风险相关")
    if components["causal_language"] >= 12:
        reasons.append("因果链条较明确")
    if components["direct_asset"]:
        reasons.append("直接命中分析标的")
    if components["event_quality"]:
        reasons.append("数据/预期差")
    if components["time_proximity"] >= 9:
        reasons.append("贴近分析窗口")
    if summary_penalty:
        reasons.append("汇总/预告降权")
    if light_summary_penalty:
        reasons.append("整理类内容降权")
    if noise_penalty:
        reasons.append("噪声降权")
    if vague_penalty:
        reasons.append("信息量不足降权")
    if components["priority"] >= 14:
        reasons.append("高优先级快讯")
    return reasons[:6]


def apply_diversity_penalty(rows: list[dict[str, Any]]) -> None:
    seen: dict[str, int] = {}
    for row in sorted(rows, key=lambda item: item.get("published_at") or ""):
        key = diversity_key(row)
        if not key:
            continue
        count = seen.get(key, 0)
        seen[key] = count + 1
        if count < 2:
            continue
        penalty = min(0.18, 0.06 * (count - 1))
        row["relevance_score"] = round(max(0, float(row.get("relevance_score") or 0) - penalty), 3)
        row.setdefault("score_reasons", []).append("同主题重复降权")
        components = row.get("score_components")
        if isinstance(components, dict):
            components["diversity_penalty"] = -round(penalty * 100)


def diversity_key(row: dict[str, Any]) -> str:
    title = str(row.get("title") or row.get("content") or "")
    normalized = re.sub(r"\W+", "", title.lower())
    keywords = [str(item) for item in row.get("matched_keywords") or []][:3]
    if len(normalized) >= 14:
        return normalized[:18]
    return "|".join(keywords)
