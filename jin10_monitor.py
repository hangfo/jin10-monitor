"""
金十数据 实时快讯监控 + Telegram 推送
策略：WebSocket 优先，断线自动降级为轮询，双保险架构
"""

import asyncio
import argparse
import inspect
import json
import logging
import os
import random
import re
import sqlite3
import struct
import time
import urllib.parse
import urllib.request
from collections import OrderedDict
from datetime import datetime, timedelta
from html import escape, unescape
from pathlib import Path
from typing import Optional

import aiohttp
import websockets
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("jin10")

# ─── 配置 ───────────────────────────────────────────────────────────────────

TG_TOKEN   = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
HISTORY_DB = Path(os.getenv("HISTORY_DB", "data/jin10_history.sqlite3"))
APP_IDS = [
    app_id.strip()
    for app_id in os.getenv("JIN10_APP_IDS", "bVBF4FyRTn5NJF5n,SO1EJGmNgCtmpcPF").split(",")
    if app_id.strip()
]
PUSH_IMPORTANT = os.getenv("PUSH_IMPORTANT", "1").lower() not in {"0", "false", "no", "off"}

PRIORITY_IMPORTANT = "T3_IMPORTANT"
PRIORITY_HIGH = "T2_HIGH"
PRIORITY_NORMAL = "T1_NORMAL"
PRIORITY_NONE = "T0_NONE"

PRIORITY_ICONS = {
    PRIORITY_IMPORTANT: "⚡",
    PRIORITY_HIGH: "🚨",
    PRIORITY_NORMAL: "📰",
    PRIORITY_NONE: "·",
}
PRIORITY_LABELS = {
    PRIORITY_IMPORTANT: "金十重要",
    PRIORITY_HIGH: "高优先级",
    PRIORITY_NORMAL: "普通命中",
    PRIORITY_NONE: "未推送",
}

# 关键词命中时才推送（空列表 = 全推）
KEYWORDS = [
    # 地缘 / 宏观
    "伊朗", "以色列", "俄罗斯", "乌克兰", "朝鲜", "台湾",
    "制裁", "战争", "军事", "核", "冲突",
    "美联储", "Fed", "加息", "降息", "利率", "货币政策",
    "CPI", "PCE", "非农", "就业", "GDP", "通胀",
    # 能源 / 商品
    "石油", "原油", "OPEC", "天然气",
    "黄金", "白银", "铜", "大宗",
    # 加密
    "比特币", "Bitcoin", "BTC", "以太坊", "ETH",
    "加密", "crypto", "稳定币",
    # 重要机构
    "特朗普", "Trump", "拜登", "美国", "中国", "欧央行",
    "世界银行", "IMF", "G7", "G20",
    # 重点公司 / 人物观察
    "巴菲特", "伯克希尔", "BRK", "Anthropic",
]

# 高优先级关键词（命中后用 🚨 标头，而非普通 📰）
HIGH_PRIORITY = [
    "战争", "核", "制裁", "加息", "降息",
    "Bitcoin", "BTC", "ETH", "以太坊", "比特币",
    "伊朗", "以色列",
]

POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "3"))          # 轮询间隔（秒）
WS_RECONNECT_DELAY = float(os.getenv("WS_RECONNECT_DELAY", "5")) # WebSocket 断线重连间隔（秒）

# ─── 请求头池 ────────────────────────────────────────────────────────────────

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

BASE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Origin": "https://www.jin10.com",
    "Referer": "https://www.jin10.com/",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "x-version": "1.0.0",
}

# ─── 工具函数 ────────────────────────────────────────────────────────────────

def get_headers(app_id: Optional[str] = None) -> dict:
    return {
        **BASE_HEADERS,
        "User-Agent": random.choice(UA_POOL),
        "x-app-id": app_id or APP_IDS[0],
    }


def get_ws_headers() -> dict:
    return {
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
        "User-Agent": random.choice(UA_POOL),
    }


def get_ws_connect_kwargs() -> dict:
    """兼容 websockets 12/13 的 extra_headers 和 14+ 的 additional_headers。"""
    kwargs = {
        "origin": "https://www.jin10.com",
        "ping_interval": None,
        "open_timeout": 10,
    }
    try:
        params = inspect.signature(websockets.connect).parameters
    except (TypeError, ValueError):
        params = {}
    header_arg = "additional_headers" if "additional_headers" in params else "extra_headers"
    kwargs[header_arg] = get_ws_headers()
    return kwargs


def item_text(item: dict) -> tuple[str, str]:
    data = item_data(item)
    raw_title = str(data.get("title") or item.get("title") or "")
    raw_content = str(data.get("content") or item.get("content") or "")
    title = clean_html(raw_title)
    content = clean_html(raw_content)
    if not title:
        match = re.match(r"\s*(?:<b>)?【(?:<b>)?(.+?)(?:</b>)?】(?:</b>)?(.*)", raw_content, re.S)
        if match:
            title = clean_html(match.group(1))
            content = clean_html(match.group(2))
    return title, content


def item_data(item: dict) -> dict:
    data = item.get("data", {})
    return data if isinstance(data, dict) else {}


def match_keywords(text: str) -> tuple[bool, bool]:
    """返回 (是否命中任意关键词, 是否命中高优先级)"""
    if not KEYWORDS:
        return True, any(k in text for k in HIGH_PRIORITY)
    hit = any(k in text for k in KEYWORDS)
    hi  = any(k in text for k in HIGH_PRIORITY)
    return hit, hi


def clean_html(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


def is_important(item: dict) -> bool:
    return bool(item.get("important"))


def has_html_bold(item: dict) -> bool:
    data = item_data(item)
    raw = f"{data.get('title') or ''} {data.get('content') or ''}"
    return bool(re.search(r"</?b\b", raw, re.I))


def item_metadata(item: dict) -> dict:
    title, _ = item_text(item)
    data = item_data(item)
    pic_url = str(data.get("pic") or "").strip()
    news_source = clean_html(str(data.get("source") or ""))
    source_url = str(data.get("source_link") or data.get("link") or data.get("url") or "").strip()
    return {
        "has_title": bool(title),
        "has_pic": bool(pic_url),
        "pic_url": pic_url,
        "news_source": news_source,
        "source_url": source_url,
    }


def classify_priority(item: dict, *, hit: bool, high: bool) -> str:
    if is_important(item):
        return PRIORITY_IMPORTANT
    if high:
        return PRIORITY_HIGH
    if hit:
        return PRIORITY_NORMAL
    return PRIORITY_NONE


def should_push(priority_level: str, *, hit: bool) -> bool:
    return hit or (PUSH_IMPORTANT and priority_level == PRIORITY_IMPORTANT)


def style_flags(item: dict, *, high: bool, priority_level: Optional[str] = None) -> str:
    metadata = item_metadata(item)
    flags = []
    flags.append(priority_level or classify_priority(item, hit=False, high=high))
    if is_important(item):
        flags.append("important")
    if has_html_bold(item):
        flags.append("bold")
    if metadata["has_title"]:
        flags.append("title")
    if metadata["has_pic"]:
        flags.append("pic")
    if metadata["news_source"]:
        flags.append("source")
    if metadata["source_url"]:
        flags.append("source_url")
    if high:
        flags.append("keyword_high")
    return ",".join(flags)


def pack_str(value: str) -> bytes:
    raw = value.encode("utf-8")
    return struct.pack("<H", len(raw)) + raw


def unpack_str(buffer: memoryview, offset: int) -> tuple[str, int]:
    size = struct.unpack_from("<H", buffer, offset)[0]
    offset += 2
    raw = buffer[offset:offset + size].tobytes()
    offset += size
    return raw.decode("utf-8"), offset


def xor_payload(payload: bytes, key: str) -> bytes:
    if not payload or not key:
        return payload
    seed = ord(key[0])
    key_codes = [ord(ch) for ch in key]
    key_len = len(key_codes)
    return bytes(byte ^ key_codes[(idx + seed) % key_len] for idx, byte in enumerate(payload))


def build_ws_login(key: str, last_id: Optional[str] = None) -> bytes:
    payload = b"".join([
        struct.pack("<h", 4002),
        struct.pack("<i", 0),        # 未登录用户 ID
        pack_str(""),
        pack_str("chrome"),
        struct.pack("<i", 0),        # 普通用户
        pack_str("web"),
        pack_str(last_id) if last_id else b"",
    ])
    return xor_payload(payload, key)


def parse_ws_packet(payload: bytes) -> tuple[int, object]:
    buffer = memoryview(payload)
    code = struct.unpack_from("<h", buffer, 0)[0]
    offset = 2

    if code in {1000, 1001, 1002, 1003, 1100, 4002, 1005}:
        text, _ = unpack_str(buffer, offset)
        return code, json.loads(text)

    if code == 1200:
        count = struct.unpack_from("<i", buffer, offset)[0]
        offset += 4
        items = []
        for _ in range(count):
            text, offset = unpack_str(buffer, offset)
            items.insert(0, json.loads(text))
        return code, items

    return code, None


def format_message(item: dict, priority_level: str) -> str:
    icon = PRIORITY_ICONS.get(priority_level, "📰")
    priority_label = PRIORITY_LABELS.get(priority_level, priority_level)
    title, content = item_text(item)
    metadata = item_metadata(item)
    bold = has_html_bold(item)
    ts      = item.get("time", "")
    try:
        ts = datetime.fromtimestamp(int(ts)).strftime("%H:%M:%S")
    except Exception:
        pass

    parts = [f"{icon} <b>金十快讯</b> <b>{escape(priority_label)}</b>  {ts}"]
    if title:
        parts.append(f"<b>{escape(title)}</b>")
    if content:
        safe_content = escape(content)
        parts.append(f"<b>{safe_content}</b>" if bold and not title else safe_content)
    source = metadata["news_source"]
    source_url = metadata["source_url"]
    if source and source_url:
        parts.append(f"来源：<a href=\"{escape(source_url, quote=True)}\">{escape(source)}</a>")
    elif source:
        parts.append(f"来源：{escape(source)}")
    elif source_url:
        parts.append(f"来源链接：<a href=\"{escape(source_url, quote=True)}\">查看</a>")
    if metadata["pic_url"]:
        parts.append(f"图片：<a href=\"{escape(metadata['pic_url'], quote=True)}\">查看</a>")
    return "\n".join(parts)


ANSI_RED = "\033[31m"
ANSI_BOLD = "\033[1m"
ANSI_RESET = "\033[0m"


def apply_console_style(text: str, *, important: bool = False, bold: bool = False) -> str:
    prefixes = []
    if important:
        prefixes.append(ANSI_RED)
    if bold:
        prefixes.append(ANSI_BOLD)
    if not prefixes:
        return text
    return "".join(prefixes) + text + ANSI_RESET


def format_console_message(item: dict, *, priority_level: str) -> str:
    title, content = item_text(item)
    important = is_important(item)
    bold = has_html_bold(item)
    metadata = item_metadata(item)
    ts = item.get("time", "")
    icon = PRIORITY_ICONS.get(priority_level, "📰")
    labels = [PRIORITY_LABELS.get(priority_level, priority_level)]
    if important:
        labels.append("重要")
    if bold:
        labels.append("加粗")
    if metadata["has_pic"]:
        labels.append("有图")
    label_text = f" [{' '.join(labels)}]" if labels else ""
    lines = [f"{icon} {ts}{label_text}"]
    if title:
        lines.append(apply_console_style(title, important=important, bold=True))
    if content:
        lines.append(apply_console_style(content, important=important, bold=bold and not title))
    if metadata["news_source"]:
        lines.append(f"来源：{metadata['news_source']}")
    if metadata["source_url"]:
        lines.append(f"来源链接：{metadata['source_url']}")
    if metadata["pic_url"]:
        lines.append(f"图片：{metadata['pic_url']}")
    return "\n".join(lines)


# ─── 本地历史库 ───────────────────────────────────────────────────────────────

_db_conn: Optional[sqlite3.Connection] = None


def get_db() -> sqlite3.Connection:
    global _db_conn
    if _db_conn is None:
        HISTORY_DB.parent.mkdir(parents=True, exist_ok=True)
        _db_conn = sqlite3.connect(HISTORY_DB, check_same_thread=False)
    return _db_conn


def ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> bool:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
        return True
    return False

def item_timestamp(item: dict) -> str:
    ts = item.get("time", "")
    if isinstance(ts, (int, float)) or str(ts).isdigit():
        return datetime.fromtimestamp(int(ts)).isoformat(sep=" ")
    return str(ts)


def init_history_db() -> None:
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS flash_history (
            id TEXT PRIMARY KEY,
            published_at TEXT,
            title TEXT,
            content TEXT,
            hit INTEGER NOT NULL,
            high INTEGER NOT NULL,
            important INTEGER NOT NULL DEFAULT 0,
            has_bold INTEGER NOT NULL DEFAULT 0,
            priority_level TEXT NOT NULL DEFAULT 'T0_NONE',
            has_title INTEGER NOT NULL DEFAULT 0,
            has_pic INTEGER NOT NULL DEFAULT 0,
            pic_url TEXT NOT NULL DEFAULT '',
            news_source TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            style_flags TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    migrated = False
    migrated |= ensure_column(conn, "flash_history", "important", "important INTEGER NOT NULL DEFAULT 0")
    migrated |= ensure_column(conn, "flash_history", "has_bold", "has_bold INTEGER NOT NULL DEFAULT 0")
    migrated |= ensure_column(conn, "flash_history", "priority_level", "priority_level TEXT NOT NULL DEFAULT 'T0_NONE'")
    migrated |= ensure_column(conn, "flash_history", "has_title", "has_title INTEGER NOT NULL DEFAULT 0")
    migrated |= ensure_column(conn, "flash_history", "has_pic", "has_pic INTEGER NOT NULL DEFAULT 0")
    migrated |= ensure_column(conn, "flash_history", "pic_url", "pic_url TEXT NOT NULL DEFAULT ''")
    migrated |= ensure_column(conn, "flash_history", "news_source", "news_source TEXT NOT NULL DEFAULT ''")
    migrated |= ensure_column(conn, "flash_history", "source_url", "source_url TEXT NOT NULL DEFAULT ''")
    migrated |= ensure_column(conn, "flash_history", "style_flags", "style_flags TEXT NOT NULL DEFAULT ''")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flash_history_published_at ON flash_history(published_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flash_history_high ON flash_history(high)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flash_history_hit ON flash_history(hit)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flash_history_important ON flash_history(important)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flash_history_priority_level ON flash_history(priority_level)")
    if migrated or needs_history_metadata_backfill(conn):
        backfill_history_metadata(conn)
    conn.commit()


def needs_history_metadata_backfill(conn: sqlite3.Connection) -> bool:
    return bool(conn.execute(
        """
        SELECT 1
        FROM flash_history
        WHERE (priority_level = ? AND (hit = 1 OR high = 1 OR important = 1))
           OR (style_flags = '' AND raw_json != '')
        LIMIT 1
        """,
        (PRIORITY_NONE,),
    ).fetchone())


def backfill_history_metadata(conn: sqlite3.Connection, *, limit: int = 5000) -> None:
    rows = conn.execute(
        """
        SELECT id, hit, high, source, raw_json
        FROM flash_history
        WHERE raw_json != ''
        ORDER BY published_at DESC, created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    for fid, hit, high, ingest_source, raw_json in rows:
        try:
            item = json.loads(raw_json)
        except Exception:
            continue
        title, content = item_text(item)
        important = int(is_important(item))
        bold = int(has_html_bold(item))
        metadata = item_metadata(item)
        priority = classify_priority(item, hit=bool(hit), high=bool(high))
        flags = style_flags(item, high=bool(high), priority_level=priority)
        conn.execute(
            """
            UPDATE flash_history
            SET title = ?, content = ?, important = ?, has_bold = ?,
                priority_level = ?, has_title = ?, has_pic = ?, pic_url = ?,
                news_source = ?, source_url = ?, style_flags = ?, source = ?
            WHERE id = ?
            """,
            (
                title,
                content,
                important,
                bold,
                priority,
                int(metadata["has_title"]),
                int(metadata["has_pic"]),
                metadata["pic_url"],
                metadata["news_source"],
                metadata["source_url"],
                flags,
                ingest_source,
                fid,
            ),
        )


def save_history_item(item: dict, *, hit: bool, high: bool, source: str, priority_level: Optional[str] = None) -> None:
    fid = str(item.get("id", ""))
    if not fid:
        return
    title, content = item_text(item)
    important = int(is_important(item))
    bold = int(has_html_bold(item))
    metadata = item_metadata(item)
    priority = priority_level or classify_priority(item, hit=hit, high=high)
    flags = style_flags(item, high=high, priority_level=priority)
    conn = get_db()
    values = (
        fid,
        item_timestamp(item),
        title,
        content,
        int(hit),
        int(high),
        important,
        bold,
        priority,
        int(metadata["has_title"]),
        int(metadata["has_pic"]),
        metadata["pic_url"],
        metadata["news_source"],
        metadata["source_url"],
        flags,
        source,
        json.dumps(item, ensure_ascii=False, sort_keys=True),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO flash_history
            (id, published_at, title, content, hit, high, important, has_bold,
             priority_level, has_title, has_pic, pic_url, news_source, source_url,
             style_flags, source, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        values,
    )
    conn.execute(
        """
        UPDATE flash_history
        SET published_at = ?, title = ?, content = ?, hit = ?, high = ?,
            important = ?, has_bold = ?, priority_level = ?, has_title = ?,
            has_pic = ?, pic_url = ?, news_source = ?, source_url = ?,
            style_flags = ?, source = ?, raw_json = ?
        WHERE id = ?
        """,
        values[1:] + (fid,),
    )
    conn.commit()


def query_history(query: str = "", *, limit: int = 20, high_only: bool = False) -> list[tuple]:
    clauses = []
    params: list[object] = []
    if query:
        clauses.append("(title LIKE ? OR content LIKE ?)")
        like = f"%{query}%"
        params.extend([like, like])
    if high_only:
        clauses.append("(high = 1 OR priority_level = ?)")
        params.append(PRIORITY_IMPORTANT)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(limit)
    return get_db().execute(
        f"""
        SELECT published_at, high, hit, important, has_bold, priority_level,
               has_pic, pic_url, news_source, source_url, style_flags, title, content
        FROM flash_history
        {where}
        ORDER BY published_at DESC, created_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()


def print_history(query: str = "", *, limit: int = 20, high_only: bool = False) -> None:
    init_history_db()
    rows = query_history(query, limit=limit, high_only=high_only)
    if not rows:
        log.info("历史库暂无匹配记录：%s", query or "(最新)")
        return
    for published_at, high, hit, important, bold, priority, has_pic, pic_url, news_source, source_url, flags, title, content in rows:
        icon = PRIORITY_ICONS.get(priority, "·" if not hit else "📰")
        labels = [PRIORITY_LABELS.get(priority, priority)]
        if bold:
            labels.append("加粗")
        if has_pic:
            labels.append("有图")
        label_text = f" [{' '.join(labels)}]" if labels else ""
        print(f"{published_at} {icon}{label_text}")
        if title:
            print(apply_console_style(f"  {title}", important=bool(important), bold=True))
        if content:
            print(apply_console_style(f"  {content}", important=bool(important), bold=bool(bold) and not title))
        if news_source:
            print(f"  来源：{news_source}")
        if source_url:
            print(f"  来源链接：{source_url}")
        if pic_url:
            print(f"  图片：{pic_url}")


# ─── Telegram 推送 ───────────────────────────────────────────────────────────

async def send_telegram(session: aiohttp.ClientSession, text: str) -> None:
    if not TG_TOKEN or not TG_CHAT_ID:
        log.warning("Telegram 未配置，仅打印到控制台：\n%s", text)
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                log.error("Telegram 发送失败: %s", await resp.text())
    except Exception as e:
        log.error("Telegram 异常: %s", e)


# ─── 去重 + 已处理 ID 集合 ───────────────────────────────────────────────────

seen_ids: OrderedDict[str, None] = OrderedDict()


def is_new(item: dict) -> bool:
    fid = str(item.get("id", ""))
    if not fid or fid in seen_ids:
        return False
    seen_ids[fid] = None
    if len(seen_ids) > 2000:          # 防止无限增长
        for _ in range(500):
            seen_ids.popitem(last=False)
    return True


# ─── REST 轮询（备用 / 冷启动） ───────────────────────────────────────────────

FLASH_API = "https://flash-api.jin10.com/get_flash_list"


def flash_params(*, mode: str, max_time: Optional[str] = None) -> dict:
    if mode == "channel":
        params = {
            "channel": "-8200",
            "vip": "1",
            "t": str(int(time.time() * 1000)),
        }
        if max_time:
            params["max_time"] = max_time
        return params
    return {"category": "-1", "id": "0", "vip": "0"}


async def poll_once(session: aiohttp.ClientSession) -> list[dict]:
    attempts = [("channel", app_id) for app_id in APP_IDS]
    attempts.extend(("legacy", app_id) for app_id in APP_IDS)
    for mode, app_id in attempts:
        try:
            async with session.get(
                FLASH_API,
                params=flash_params(mode=mode),
                headers=get_headers(app_id),
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    return data.get("data", [])
                log.warning("REST 状态码: %s (mode=%s app_id=%s)", resp.status, mode, app_id)
        except asyncio.TimeoutError:
            log.warning("REST 超时 (mode=%s app_id=%s)", mode, app_id)
        except Exception as e:
            log.warning("REST 异常: %s (mode=%s app_id=%s)", e, mode, app_id)
    return []


def parse_item_time(item: dict) -> Optional[datetime]:
    value = item.get("time")
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None


def fetch_page_sync(max_time: str, app_id: str, timeout: int = 12) -> list[dict]:
    params = flash_params(mode="channel", max_time=max_time)
    url = f"{FLASH_API}?{urllib.parse.urlencode(params)}"
    headers = get_headers(app_id)
    headers.pop("Accept-Encoding", None)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = json.loads(resp.read().decode("utf-8", "replace"))
    data = raw.get("data")
    if not isinstance(data, list):
        raise RuntimeError(f"意外响应格式: {str(raw)[:200]}")
    return data


def score_keywords(text: str, keywords: list[str]) -> tuple[int, list[str]]:
    lower = text.lower()
    hits = []
    for keyword in keywords:
        keyword = keyword.strip()
        if keyword and keyword.lower() in lower:
            hits.append(keyword)
    return len(hits), hits


def crawl_window(
    start_dt: datetime,
    end_dt: datetime,
    keywords: list[str],
    *,
    max_pages: int = 12,
    sleep_s: float = 0.3,
) -> dict:
    cursor = (end_dt + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    last_error = None
    for app_id in APP_IDS:
        seen: set[str] = set()
        rows = []
        pages = 0
        oldest_seen = None
        try:
            while pages < max_pages:
                page = fetch_page_sync(cursor, app_id)
                pages += 1
                if not page:
                    break

                dated = []
                for item in page:
                    item_dt = parse_item_time(item)
                    if item_dt is None:
                        continue
                    dated.append((item_dt, item))
                    if oldest_seen is None or item_dt < oldest_seen:
                        oldest_seen = item_dt

                    fid = str(item.get("id") or f"{item_dt}-{item_text(item)}")
                    if fid in seen:
                        continue
                    seen.add(fid)

                    if start_dt <= item_dt <= end_dt:
                        title, content = item_text(item)
                        full_text = " ".join(part for part in [title, content] if part).strip()
                        score, hits = score_keywords(full_text, keywords)
                        _, high = match_keywords(full_text)
                        priority_level = classify_priority(item, hit=bool(score), high=high)
                        metadata = item_metadata(item)
                        rows.append({
                            "id": item.get("id"),
                            "time_bj": item_dt.strftime("%Y-%m-%d %H:%M:%S"),
                            "title": title,
                            "content": content,
                            "important": int(is_important(item)),
                            "has_bold": int(has_html_bold(item)),
                            "priority_level": priority_level,
                            "has_pic": int(metadata["has_pic"]),
                            "pic_url": metadata["pic_url"],
                            "news_source": metadata["news_source"],
                            "source_url": metadata["source_url"],
                            "style_flags": style_flags(item, high=high, priority_level=priority_level),
                            "matched_keywords": hits,
                            "match_score": score,
                            "raw": item,
                        })

                if oldest_seen and oldest_seen < start_dt:
                    break
                if dated:
                    cursor = dated[-1][0].strftime("%Y-%m-%d %H:%M:%S")
                else:
                    break
                time.sleep(sleep_s + random.uniform(0, 0.2))

            rows.sort(key=lambda row: row["time_bj"])
            return {
                "ok": True,
                "app_id": app_id,
                "window": {
                    "start": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "end": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                },
                "pages": pages,
                "all_items": rows,
                "matched_items": [row for row in rows if row["match_score"] > 0],
            }
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            log.warning("lookup app_id %s 失败，尝试下一个: %s", app_id, last_error)
    return {"ok": False, "error": last_error or "未知错误"}


def print_lookup(result: dict) -> None:
    window = result.get("window", {})
    print(f"金十快讯窗口: {window.get('start')} -> {window.get('end')} ok={result.get('ok')}")
    if not result.get("ok"):
        print(f"错误: {result.get('error')}")
        return
    rows = result.get("all_items") or []
    for row in rows:
        icon = PRIORITY_ICONS.get(row.get("priority_level"), "📰")
        labels = [PRIORITY_LABELS.get(row.get("priority_level"), row.get("priority_level", ""))]
        if row["has_bold"]:
            labels.append("加粗")
        if row.get("has_pic"):
            labels.append("有图")
        if row["matched_keywords"]:
            labels.append(",".join(row["matched_keywords"]))
        label_text = f" [{' '.join(labels)}]" if labels else ""
        print(f"{icon} {row['time_bj']}{label_text}")
        if row["title"]:
            print(apply_console_style(f"  {row['title']}", important=bool(row["important"]), bold=True))
        if row["content"]:
            print(apply_console_style(f"  {row['content']}", important=bool(row["important"]), bold=bool(row["has_bold"]) and not row["title"]))
        if row.get("news_source"):
            print(f"  来源：{row['news_source']}")
        if row.get("source_url"):
            print(f"  来源链接：{row['source_url']}")
        if row.get("pic_url"):
            print(f"  图片：{row['pic_url']}")
    print(f"\n共 {len(rows)} 条，关键词命中 {len(result.get('matched_items') or [])} 条")


async def poll_loop(session: aiohttp.ClientSession) -> None:
    """轮询模式：每隔 POLL_INTERVAL 秒拉一次，仅处理新条目"""
    log.info("▶ 启动 REST 轮询（间隔 %ss）", POLL_INTERVAL)
    while True:
        items = await poll_once(session)
        for item in items:
            if is_new(item):
                await handle_item(session, item, source="rest")
        jitter = random.uniform(-1.5, 1.5)
        await asyncio.sleep(max(1.0, POLL_INTERVAL + jitter))


# ─── WebSocket 实时（主路） ───────────────────────────────────────────────────

WS_URLS = [
    url.strip()
    for url in os.getenv("WS_URLS", "wss://wss-flash-2.jin10.com/").split(",")
    if url.strip()
]


async def ws_loop(session: aiohttp.ClientSession) -> None:
    log.info("▶ 尝试建立 WebSocket 连接 …")
    while True:
        ws_url = random.choice(WS_URLS)
        try:
            log.info("WebSocket 连接目标: %s", ws_url)
            async with websockets.connect(
                ws_url,
                **get_ws_connect_kwargs(),
            ) as ws:
                log.info("✅ WebSocket 已连接: %s", ws_url)
                secret = ""
                skipped_initial_list = False
                async for raw in ws:
                    if not isinstance(raw, (bytes, bytearray)):
                        continue

                    try:
                        if not secret:
                            packet = bytes(raw)
                            if len(packet) < 12:
                                continue
                            _, seed_b, seed_a = struct.unpack_from("<III", packet, 0)
                            secret = f"{seed_a}.{seed_b}"
                            await ws.send(build_ws_login(secret))
                            log.info("WebSocket 登录包已发送")
                            continue

                        packet = xor_payload(bytes(raw), secret)
                        code, data = parse_ws_packet(packet)
                    except Exception as e:
                        log.debug("WebSocket 消息解析失败: %s", e)
                        continue

                    if code == 1201:
                        await ws.send(b"")
                        continue

                    if code in {1000, 1100} and isinstance(data, dict):
                        if data.get("action") in {1, 2} and is_new(data):
                            await handle_item(session, data, source="ws")
                    elif code == 1200 and isinstance(data, list):
                        if not skipped_initial_list:
                            for item in data:
                                if isinstance(item, dict):
                                    fid = str(item.get("id", ""))
                                    if fid:
                                        seen_ids[fid] = None
                                    title, content = item_text(item)
                                    hit, high = match_keywords(f"{title} {content}")
                                    save_history_item(item, hit=hit, high=high, source="ws_initial")
                            skipped_initial_list = True
                            log.info("WebSocket 初始历史列表已预热去重：%d 条", len(data))
                            continue
                        for item in data:
                            if isinstance(item, dict) and item.get("action") in {1, 2} and is_new(item):
                                await handle_item(session, item, source="ws")
        except Exception as e:
            log.warning("WebSocket 断线: %s，%ss 后重连", e, WS_RECONNECT_DELAY)
            await asyncio.sleep(WS_RECONNECT_DELAY)


# ─── 核心处理 ────────────────────────────────────────────────────────────────

async def handle_item(session: aiohttp.ClientSession, item: dict, *, source: str = "unknown") -> None:
    title, content = item_text(item)
    text    = f"{title} {content}"

    hit, high = match_keywords(text)
    priority_level = classify_priority(item, hit=hit, high=high)
    save_history_item(item, hit=hit, high=high, source=source, priority_level=priority_level)
    if not should_push(priority_level, hit=hit):
        return

    log.info("\n%s", format_console_message(item, priority_level=priority_level))
    msg = format_message(item, priority_level)
    await send_telegram(session, msg)


async def run_once(limit: int) -> None:
    init_history_db()
    connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        items = await poll_once(session)
        log.info("一次性抓取完成：收到 %d 条，处理前 %d 条", len(items), min(limit, len(items)))
        for item in reversed(items[:limit]):
            await handle_item(session, item, source="rest_once")


# ─── 主入口 ─────────────────────────────────────────────────────────────────

async def main() -> None:
    log.info("=== 金十快讯监控启动 ===")
    log.info("关键词: %s 条  Telegram: %s", len(KEYWORDS), "已配置" if TG_TOKEN else "未配置（仅打印）")
    init_history_db()

    connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        # 冷启动：先拉一批历史条目填充 seen_ids（不推送），避免重启后刷屏
        log.info("冷启动：预加载已有快讯 ID …")
        items = await poll_once(session)
        for item in items:
            fid = str(item.get("id", ""))
            if fid:
                seen_ids[fid] = None
            title, content = item_text(item)
            hit, high = match_keywords(f"{title} {content}")
            save_history_item(item, hit=hit, high=high, source="cold_start")
        log.info("预加载完成，已忽略 %d 条旧快讯", len(seen_ids))

        # 并发运行 WS + 轮询（双保险）
        await asyncio.gather(
            ws_loop(session),
            poll_loop(session),
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="金十快讯监控 + Telegram 推送")
    parser.add_argument("--once", action="store_true", help="只抓取一次 REST 快讯，用于本地验证")
    parser.add_argument("--limit", type=int, default=20, help="--once 模式处理的最大条数")
    parser.add_argument("--history", nargs="?", const="", help="查询本地历史库，省略关键词时显示最新记录")
    parser.add_argument("--history-limit", type=int, default=20, help="历史查询返回条数")
    parser.add_argument("--history-high", action="store_true", help="历史查询只显示高优先级记录")
    parser.add_argument("--lookup-date", help="回溯查询日期 YYYY-MM-DD")
    parser.add_argument("--lookup-start", help="回溯开始时间 HH:MM，北京时间")
    parser.add_argument("--lookup-end", help="回溯结束时间 HH:MM，北京时间")
    parser.add_argument("--lookup-keywords", default=",".join(KEYWORDS), help="回溯高亮关键词，逗号分隔")
    parser.add_argument("--lookup-max-pages", type=int, default=12, help="回溯最多翻页数")
    parser.add_argument("--lookup-format", choices=["text", "json"], default="text", help="回溯输出格式")
    return parser.parse_args()


if __name__ == "__main__":
    try:
        args = parse_args()
        if args.lookup_date or args.lookup_start or args.lookup_end:
            if not (args.lookup_date and args.lookup_start and args.lookup_end):
                raise SystemExit("--lookup-date、--lookup-start、--lookup-end 需要同时提供")
            start_dt = datetime.strptime(f"{args.lookup_date} {args.lookup_start}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{args.lookup_date} {args.lookup_end}", "%Y-%m-%d %H:%M")
            if end_dt < start_dt:
                raise SystemExit("--lookup-end 必须晚于 --lookup-start")
            keywords = [kw.strip() for kw in args.lookup_keywords.split(",") if kw.strip()]
            result = crawl_window(start_dt, end_dt, keywords, max_pages=args.lookup_max_pages)
            if args.lookup_format == "json":
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print_lookup(result)
        elif args.history is not None:
            print_history(args.history, limit=max(1, args.history_limit), high_only=args.history_high)
        elif args.once:
            asyncio.run(run_once(max(1, args.limit)))
        else:
            asyncio.run(main())
    except KeyboardInterrupt:
        log.info("已手动停止")
