"""Manual AI prompt generation and answer parsing for Phase 2A."""

from __future__ import annotations

import html
import json
import re
from typing import Any


PROMPT_VERSION = "v1"
CONFIDENCE_HELP = (
    "置信度是模型基于证据充分度、时间吻合度和因果链条清晰度给出的主观估计，不是交易信号。"
    "≥75% 较可信；50-75% 仅供参考；<50% 证据不足。"
)
JUDGEMENT_VALUES = {"news_driven", "macro_sentiment", "technical_breakout", "unclear"}
DIRECTION_VALUES = {"bullish", "bearish", "mixed"}


SYSTEM_INSTRUCTION = """\
你是一个宏观新闻催化分析助手，专门分析加密货币、大宗商品、外汇和美股的短线行情驱动因素。

严格约束：
1. 只引用 [证据列表] 中提供的消息，不编造不存在的新闻。
2. 每个论点末尾必须标注对应的 news_id（格式：[#news_id]）。
3. 如果证据不足以得出结论，在 missing_evidence 中说明，不强行归因。
4. impact_path 必须具体说明机制，不能只写“利好”或“利空”。
5. 必须说明新闻如何影响风险偏好、利率预期、美元流动性、供需或仓位，而不是只复述新闻。
6. 在证据充分时优先输出 4-8 条 catalysts；不要为了凑数重复同一条传导链。
7. judgement 判定标准必须一致：
   - news_driven：一条或几条具体新闻/数据能直接解释主要波动。
   - macro_sentiment：主要是利率、美元、通胀、就业、地缘风险等宏观风险偏好共同传导，没有单一新闻足够解释。
   - technical_breakout：主要由价格、成交量、突破/跌破等行情结构解释，新闻只是辅助。
   - unclear：证据不足、时间不吻合或因果链不清楚。
8. 如果多个证据属于同一传导链，可合并说明，但 catalysts 应覆盖不同的高置信传导链。
9. 同一个 news_id 只能出现在一个 catalyst；如果同一条新闻有多个影响机制，请合并到同一个 catalyst。
10. 输出严格 JSON，不要 markdown 代码块，不要任何前言后语。

输出格式：
{
  "summary": "一句话结论，≤60字，包含判断类型和主要驱动力",
  "catalysts": [
    {
      "news_id": "消息ID字符串",
      "time": "消息发布时间",
      "headline": "消息标题或首句，≤40字",
      "impact_path": "具体归因机制，≥20字，末尾标注 [#news_id]",
      "confidence": 0.0到1.0,
      "direction": "bullish 或 bearish 或 mixed"
    }
  ],
  "missing_evidence": ["缺失的数据类型，例如：BTC/USDT 1分钟成交量"],
  "judgement": "news_driven 或 macro_sentiment 或 technical_breakout 或 unclear",
  "overall_confidence": 0.0到1.0,
  "caveat": "分析局限性，例如：证据时间窗口可能不完整"
}"""


def generate_prompt(
    *,
    question: str,
    asset: str,
    window_start: str,
    window_end: str,
    evidence: list[dict[str, Any]],
    user_context: str = "",
    market_context: dict[str, Any] | None = None,
) -> str:
    selected = [item for item in evidence if item.get("selected", True)]
    lines = [
        "=" * 60,
        "【系统指令】",
        SYSTEM_INSTRUCTION,
        "",
        "=" * 60,
        "【分析请求】",
        f"分析标的：{asset}",
        f"时间窗口：{window_start} 至 {window_end}",
        f"用户问题：{question}",
    ]
    if user_context:
        lines.extend(["", f"补充描述：{user_context}"])

    if market_context and market_context.get("enabled"):
        lines.extend(render_market_context_lines(market_context))

    lines.extend(
        [
            "",
            "=" * 60,
            f"【证据列表】共 {len(selected)} 条（已过滤不相关条目）",
            "",
        ]
    )

    for index, item in enumerate(selected, 1):
        title = str(item.get("title") or "").strip()
        content = str(item.get("content") or "").strip()
        content_line = title or content[:120]
        extra = f"\n    正文：{content[:160]}" if title and content else ""
        keyword_note = ""
        if item.get("matched_keywords"):
            keyword_note = "\n    命中关键词：" + "，".join(str(k) for k in item["matched_keywords"])
        reason_note = ""
        if item.get("score_reasons"):
            reason_note = "\n    本地评分理由：" + " / ".join(str(k) for k in item["score_reasons"])
        lines.extend(
            [
                f"[{index}] news_id={item.get('news_id') or item.get('id')}",
                f"    时间：{item.get('published_at', '')}",
                f"    优先级：{item.get('priority_level', '')}（相关度 {float(item.get('relevance_score') or 0):.2f}）",
                f"    内容：{content_line}{extra}{keyword_note}{reason_note}",
                f"    来源：{item.get('news_source') or '—'}",
                "",
            ]
        )

    lines.extend(
        [
            "=" * 60,
            "【要求】",
            "请严格按照系统指令的 JSON 格式回答，不要加任何前言或解释。",
            "=" * 60,
        ]
    )
    return "\n".join(lines)


def render_market_context_lines(market_context: dict[str, Any]) -> list[str]:
    lines = [
        "",
        "=" * 60,
        "【结构化行情上下文】",
    ]
    if not market_context.get("ok"):
        lines.extend(
            [
                f"行情数据不可用：{market_context.get('error') or 'market data unavailable'}",
                "注意：不要把缺失行情数据当作价格没有波动。",
            ]
        )
        return lines

    summary = market_context.get("summary") or {}
    lines.extend(
        [
            f"来源：{market_context.get('source') or 'market adapter'}",
            f"交易对：{market_context.get('symbol')}",
            f"周期：{market_context.get('interval')}",
            f"窗口：{market_context.get('start')} 至 {market_context.get('end')}",
            f"K 线数量：{summary.get('count')}",
            f"首根收盘：{summary.get('first_close')}",
            f"末根收盘：{summary.get('last_close')}",
            f"涨跌：{summary.get('move')} ({summary.get('move_pct')}%)",
            f"窗口高点：{summary.get('high')}",
            f"窗口低点：{summary.get('low')}",
            "注意：行情上下文只说明价格变化，不单独证明新闻因果。",
        ]
    )
    return lines


def parse_answer(raw_text: str) -> dict[str, Any]:
    text = str(raw_text or "").strip()
    if not text:
        return empty_parsed()

    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        parsed = try_json(fence_match.group(1))
        if parsed is not None:
            return validate_answer(parsed)

    parsed = try_json(text)
    if parsed is not None:
        return validate_answer(parsed)

    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        parsed = try_json(brace_match.group(0))
        if parsed is not None:
            return validate_answer(parsed)

    parsed = empty_parsed()
    parsed["parse_error"] = True
    parsed["raw_text"] = text[:4000]
    return parsed


def extract_news_ids_from_answer(answer_parsed: dict[str, Any]) -> list[str]:
    return [
        str(item.get("news_id"))
        for item in answer_parsed.get("catalysts") or []
        if isinstance(item, dict) and item.get("news_id")
    ]


def render_answer_with_links(answer_parsed: dict[str, Any]) -> str:
    summary = str(answer_parsed.get("summary") or "")
    catalysts = answer_parsed.get("catalysts") or []
    missing = answer_parsed.get("missing_evidence") or []
    judgement = str(answer_parsed.get("judgement") or "")
    confidence = clamp_float(answer_parsed.get("overall_confidence"), 0, 1)
    caveat = str(answer_parsed.get("caveat") or "")
    ref_labels = {
        str(item.get("news_id") or ""): display_time_label(item.get("time") or "") or short_news_id(item.get("news_id") or "")
        for item in catalysts
        if isinstance(item, dict) and item.get("news_id")
    }

    parts: list[str] = []
    if summary:
        parts.append(f'<p class="answer-summary">{linkify_news_refs(summary, ref_labels)}</p>')

    if catalysts:
        parts.append('<div class="answer-catalysts"><strong>主要催化因素：</strong><ol>')
        for catalyst in catalysts:
            if not isinstance(catalyst, dict):
                continue
            catalyst_confidence = clamp_float(catalyst.get("confidence"), 0, 1)
            confidence_class = (
                "conf-high"
                if catalyst_confidence >= 0.7
                else "conf-mid"
                if catalyst_confidence >= 0.4
                else "conf-low"
            )
            direction = str(catalyst.get("direction") or "")
            direction_icon = {"bullish": "▲ 偏利多", "bearish": "▼ 偏利空", "mixed": "◆ 多空混合"}.get(direction, "")
            news_id = html.escape(str(catalyst.get("news_id") or ""))
            catalyst_time = display_time_label(catalyst.get("time") or "")
            ref_text = ref_labels.get(str(catalyst.get("news_id") or ""), short_news_id(news_id))
            headline = linkify_news_refs(str(catalyst.get("headline") or ""), ref_labels)
            impact_path = linkify_news_refs(str(catalyst.get("impact_path") or ""), ref_labels)
            time_html = f'<span class="cat-time">{html.escape(catalyst_time)}</span> ' if catalyst_time else ""
            parts.append(
                "<li>"
                f"{time_html}"
                f'<span class="cat-headline">{headline}</span> '
                f'<span class="cat-newsid"><a href="/item/{news_id}" class="news-ref" title="{news_id}">[↗ {html.escape(ref_text)}]</a></span><br>'
                f'<span class="cat-path">{impact_path}</span><br>'
                f'<span class="{confidence_class}" title="{html.escape(CONFIDENCE_HELP)}">置信度 {catalyst_confidence:.0%}</span>'
                f' <span class="dir-icon">{html.escape(direction_icon)}</span>'
                "</li>"
            )
        parts.append("</ol></div>")

    if missing:
        parts.append(
            '<div class="answer-missing"><strong>缺失证据：</strong>'
            + "，".join(html.escape(str(item)) for item in missing)
            + "</div>"
        )

    if judgement or confidence:
        labels = {
            "news_driven": "新闻驱动",
            "macro_sentiment": "宏观情绪",
            "technical_breakout": "技术突破",
            "unclear": "无法确认",
        }
        parts.append(
            '<div class="answer-meta">'
            f'判断类型：<strong>{html.escape(labels.get(judgement, judgement))}</strong> '
            f'综合置信度：<strong>{confidence:.0%}</strong>'
            "</div>"
        )

    if caveat:
        parts.append(f'<div class="answer-caveat">{html.escape(caveat)}</div>')
    return "\n".join(parts) if parts else "<p>（无结构化内容）</p>"


def linkify_news_refs(text: str, labels: dict[str, str] | None = None) -> str:
    labels = labels or {}
    escaped = html.escape(text)
    return re.sub(
        r"\[#([^\]]+)\]",
        lambda match: (
            f'<a href="/item/{html.escape(match.group(1))}" class="news-ref" target="_blank" title="{html.escape(match.group(1))}">'
            f"[↗ {html.escape(labels.get(match.group(1), short_news_id(match.group(1))))}]</a>"
        ),
        escaped,
    )


def display_time_label(value: object) -> str:
    text = str(value or "").strip()
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})", text)
    if match:
        return f"{match.group(2)}-{match.group(3)} {match.group(4)}:{match.group(5)}"
    match = re.search(r"(\d{2}):(\d{2})", text)
    return match.group(0) if match else ""


def short_news_id(value: object) -> str:
    text = str(value or "")
    match = re.match(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})", text)
    if match:
        return f"{match.group(2)}-{match.group(3)} {match.group(4)}:{match.group(5)}"
    return text[:10] + ("..." if len(text) > 10 else "")


def try_json(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def empty_parsed() -> dict[str, Any]:
    return {
        "summary": "",
        "catalysts": [],
        "missing_evidence": [],
        "judgement": "unclear",
        "overall_confidence": 0,
        "caveat": "",
        "parse_error": False,
    }


def validate_answer(data: dict[str, Any]) -> dict[str, Any]:
    parsed = empty_parsed()
    parsed["summary"] = str(data.get("summary") or "")[:500]
    parsed["caveat"] = str(data.get("caveat") or "")[:500]
    judgement = str(data.get("judgement") or "unclear")
    parsed["judgement"] = judgement if judgement in JUDGEMENT_VALUES else "unclear"
    parsed["overall_confidence"] = clamp_float(data.get("overall_confidence"), 0, 1)

    catalysts = data.get("catalysts") or []
    if isinstance(catalysts, list):
        parsed["catalysts"] = [
            validate_catalyst(item)
            for item in catalysts
            if isinstance(item, dict)
        ]

    missing_evidence = data.get("missing_evidence") or []
    if isinstance(missing_evidence, list):
        parsed["missing_evidence"] = [str(item)[:200] for item in missing_evidence if item]
    return parsed


def validate_catalyst(item: dict[str, Any]) -> dict[str, Any]:
    direction = str(item.get("direction") or "")
    return {
        "news_id": str(item.get("news_id") or ""),
        "time": str(item.get("time") or ""),
        "headline": str(item.get("headline") or "")[:200],
        "impact_path": str(item.get("impact_path") or "")[:800],
        "confidence": clamp_float(item.get("confidence"), 0, 1),
        "direction": direction if direction in DIRECTION_VALUES else "mixed",
    }


def clamp_float(value: object, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = minimum
    return max(minimum, min(parsed, maximum))
