"""Evidence packet builder for the manual AI dashboard workflow.

This module reads only the local business SQLite database through the dashboard
readonly connection. It does not call Jin10 REST, market data APIs, Telegram, or
any model API.
"""

from __future__ import annotations

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

PRIORITY_WEIGHT = {
    PRIORITY_IMPORTANT: 4,
    PRIORITY_HIGH: 2,
    "T1_NORMAL": 1,
    "T0_NONE": 0,
}

MAX_EVIDENCE = 25
CONTEXT_PADDING_MINUTES = 30


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
    scored = [score_row(row, asset_keywords) for row in rows]
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
    return filtered[:MAX_EVIDENCE]


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


def score_row(row: dict[str, Any], asset_keywords: list[str]) -> dict[str, Any]:
    text = f"{row.get('title') or ''} {row.get('content') or ''}".strip()
    asset_count, asset_hits = score_keywords(text, asset_keywords)
    macro_count, macro_hits = score_keywords(text, MACRO_KEYWORDS)
    high_count, high_hits = score_keywords(text, list(HIGH_PRIORITY))
    priority_level = str(row.get("priority_level") or "T0_NONE")
    priority_weight = PRIORITY_WEIGHT.get(priority_level, 0)
    important_bonus = 2 if row.get("important") else 0
    bold_bonus = 1 if row.get("has_bold") else 0
    raw_score = (
        asset_count * 5
        + high_count * 3
        + macro_count
        + priority_weight
        + important_bonus
        + bold_bonus
    )
    matched_keywords = list(dict.fromkeys(asset_hits + high_hits + macro_hits))
    relevance_score = round(min(raw_score / 15, 1), 3)
    news_id = str(row.get("id") or "")
    return {
        **row,
        "news_id": news_id,
        "relevance_score": relevance_score,
        "matched_keywords": matched_keywords,
        "selected": True,
    }
