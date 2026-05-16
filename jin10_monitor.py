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
import threading
import time
import urllib.parse
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import escape, unescape
from pathlib import Path
from typing import Any, Optional

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


def env_int(name: str, default: int) -> int:
    value = os.getenv(name, "")
    if not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        log.warning("%s=%r 不是有效整数，使用默认值 %s", name, value, default)
        return default


def env_float(name: str, default: float) -> float:
    value = os.getenv(name, "")
    if not value.strip():
        return default
    try:
        return float(value)
    except ValueError:
        log.warning("%s=%r 不是有效数字，使用默认值 %s", name, value, default)
        return default


def env_min_float(name: str, default: float, minimum: float) -> float:
    value = env_float(name, default)
    if value < minimum:
        log.warning("%s=%s 低于下限 %s，使用下限", name, value, minimum)
        return minimum
    return value


def env_range_float(name: str, default: float, minimum: float, maximum: float) -> float:
    value = env_min_float(name, default, minimum)
    if value > maximum:
        log.warning("%s=%s 高于上限 %s，使用上限", name, value, maximum)
        return maximum
    return value


TG_TOKEN   = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
HISTORY_DB = Path(os.getenv("HISTORY_DB", "data/jin10_history.sqlite3"))
APP_IDS = [
    app_id.strip()
    for app_id in os.getenv("JIN10_APP_IDS", "bVBF4FyRTn5NJF5n,SO1EJGmNgCtmpcPF").split(",")
    if app_id.strip()
]
PUSH_IMPORTANT = os.getenv("PUSH_IMPORTANT", "1").lower() not in {"0", "false", "no", "off"}
AUTO_CATCHUP = os.getenv("AUTO_CATCHUP", "1").lower() not in {"0", "false", "no", "off"}
CATCHUP_TELEGRAM = os.getenv("CATCHUP_TELEGRAM", "1").lower() not in {"0", "false", "no", "off"}
CATCHUP_MAX_HOURS = env_int("CATCHUP_MAX_HOURS", 24)
CATCHUP_MAX_STORE = env_int("CATCHUP_MAX_STORE", 1000)
CATCHUP_MAX_SEND = env_int("CATCHUP_MAX_SEND", 120)
CATCHUP_SEND_INTERVAL = env_float("CATCHUP_SEND_INTERVAL", 0.5)
AUTO_CATCHUP_GAP_SECONDS = env_int("AUTO_CATCHUP_GAP_SECONDS", 300)
SHOW_DELAY_IF_SECONDS = max(0, env_int("SHOW_DELAY_IF_SECONDS", 60))
ALLOW_TMP_TELEGRAM = os.getenv("ALLOW_TMP_TELEGRAM", "0").lower() in {"1", "true", "yes", "on"}
TELEGRAM_TIMEOUT = aiohttp.ClientTimeout(total=10)
TELEGRAM_RETRY_DELAYS = (1.0, 3.0)
CURSOR_FUTURE_GRACE_SECONDS = 120
AUTO_CATCHUP_START_BUFFER_SECONDS = 120
AUTO_CATCHUP_SUMMARY_COOLDOWN_SECONDS = 1800
SQLITE_BUSY_TIMEOUT_MS = 5000

PRIORITY_IMPORTANT = "T3_IMPORTANT"
PRIORITY_HIGH = "T2_HIGH"
PRIORITY_NORMAL = "T1_NORMAL"
PRIORITY_NONE = "T0_NONE"

TELEGRAM_STATUS_SENT = "sent"
TELEGRAM_STATUS_FAILED = "failed"
TELEGRAM_STATUS_UNKNOWN_TIMEOUT = "unknown_timeout"
TELEGRAM_STATUS_SKIPPED = "skipped"

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


@dataclass(frozen=True)
class TelegramSendResult:
    status: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == TELEGRAM_STATUS_SENT

def load_keyword_file(env_name: str, fallback: list[str]) -> list[str]:
    """Load one-keyword-per-line config files while keeping built-in defaults safe."""
    file_value = os.getenv(env_name, "").strip()
    if not file_value:
        return list(fallback)

    path = Path(file_value).expanduser()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        log.warning("%s=%s 读取失败，继续使用内置关键词: %s", env_name, file_value, exc)
        return list(fallback)

    keywords = []
    for line in lines:
        value = line.strip()
        if value and not value.startswith("#"):
            keywords.append(value)
    if not keywords:
        log.warning("%s=%s 没有有效关键词，继续使用内置关键词", env_name, file_value)
        return list(fallback)
    log.info("%s 已加载：%s 条（%s）", env_name, len(keywords), path)
    return keywords


# 关键词命中时才推送（空列表 = 全推）
DEFAULT_KEYWORDS = [
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
DEFAULT_HIGH_PRIORITY = [
    "战争", "核", "制裁", "加息", "降息",
    "Bitcoin", "BTC", "ETH", "以太坊", "比特币",
    "伊朗", "以色列",
]

KEYWORDS = load_keyword_file("KEYWORDS_FILE", DEFAULT_KEYWORDS)
HIGH_PRIORITY = load_keyword_file("HIGH_PRIORITY_FILE", DEFAULT_HIGH_PRIORITY)

POLL_INTERVAL = env_range_float("POLL_INTERVAL", 3, 1.0, 60.0)  # 轮询间隔（秒）
WS_RECONNECT_DELAY = env_min_float("WS_RECONNECT_DELAY", 5, 1.0)  # WebSocket 断线重连间隔（秒）

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
    if not title and not content:
        title, content = indicator_item_text(item)
    return title, content


def item_data(item: dict) -> dict:
    data = item.get("data", {})
    return data if isinstance(data, dict) else {}


def clean_number(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "none", "null"} else text


def indicator_item_text(item: dict) -> tuple[str, str]:
    """Format non-news indicator/earnings packets that do not carry title/content."""
    if item.get("type") != 1:
        return "", ""
    data = item_data(item)
    name = clean_html(str(data.get("name") or ""))
    measure = clean_html(str(data.get("measure") or ""))
    period = clean_html(str(data.get("time_period") or ""))
    if not name and not measure:
        return "", ""

    title = " ".join(part for part in [name, period, measure] if part)
    actual = clean_number(data.get("actual"))
    unit = clean_html(str(data.get("unit") or ""))
    consensus = clean_number(data.get("consensus"))
    previous = clean_number(data.get("previous"))
    revised = clean_number(data.get("revised"))

    lines = []
    if actual:
        lines.append(f"公布值：{actual}{unit}")
    if consensus:
        lines.append(f"预期：{consensus}{unit}")
    if previous:
        lines.append(f"前值：{previous}{unit}")
    if revised:
        lines.append(f"修正：{revised}{unit}")
    if data.get("country"):
        lines.append(f"市场：{clean_html(str(data.get('country')))}")
    return title, "\n".join(lines)


def match_keywords(text: str) -> tuple[bool, bool]:
    """返回 (是否命中任意关键词, 是否命中高优先级)"""
    if not KEYWORDS:
        return True, any(k in text for k in HIGH_PRIORITY)
    hit = any(k in text for k in KEYWORDS)
    hi  = any(k in text for k in HIGH_PRIORITY)
    return hit, hi


def item_full_text(item: dict) -> str:
    title, content = item_text(item)
    return " ".join(part for part in [title, content] if part).strip()


def clean_html(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


def compact_text(text: str, limit: int = 42) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


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
        pack_str(last_id or ""),
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


def format_message(item: dict, priority_level: str, *, catchup: bool = False) -> str:
    icon = PRIORITY_ICONS.get(priority_level, "📰")
    priority_label = PRIORITY_LABELS.get(priority_level, priority_level)
    title, content = item_text(item)
    metadata = item_metadata(item)
    bold = has_html_bold(item)
    ts = item_timestamp(item)
    delay_text = format_delay_text(item)

    prefix = "金十快讯 [补拉]" if catchup else "金十快讯"
    parts = [f"{icon} <b>{prefix}</b> <b>{escape(priority_label)}</b>  {ts}"]
    if catchup:
        parts.append(f"发生时间：{escape(ts)}")
    if delay_text:
        parts.append(escape(delay_text))
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
    ts = item_timestamp(item)
    delay_text = format_delay_text(item)
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
    if delay_text:
        lines.append(delay_text)
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

_db_local = threading.local()


def configure_db_connection(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_db() -> sqlite3.Connection:
    conn = getattr(_db_local, "conn", None)
    if conn is None:
        HISTORY_DB.parent.mkdir(parents=True, exist_ok=True)
        conn = configure_db_connection(sqlite3.connect(HISTORY_DB))
        _db_local.conn = conn
    return conn


def open_readonly_history_db() -> sqlite3.Connection:
    path = HISTORY_DB.expanduser()
    path = path if path.is_absolute() else Path.cwd() / path
    if not path.exists():
        raise FileNotFoundError(str(path))
    uri = f"file:{urllib.parse.quote(str(path), safe='/')}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> bool:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
        return True
    return False

def item_datetime(item: dict) -> Optional[datetime]:
    """Normalize Jin10 WS unix timestamps and REST time strings."""
    value = item.get("time")
    if value in (None, ""):
        return None

    text = str(value).strip()
    if isinstance(value, (int, float)) or text.isdigit():
        seconds = float(value)
        if seconds > 1_000_000_000_000:
            seconds /= 1000
        return datetime.fromtimestamp(seconds).replace(microsecond=0)

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def item_timestamp(item: dict) -> str:
    dt = item_datetime(item)
    if dt:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(item.get("time", ""))


def format_cursor_datetime(value: datetime) -> str:
    return value.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def parse_cursor_datetime(value: str) -> Optional[datetime]:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def format_delay_text(
    item: dict,
    *,
    now: Optional[datetime] = None,
    threshold_seconds: int = SHOW_DELAY_IF_SECONDS,
) -> str:
    if threshold_seconds <= 0:
        return ""
    item_dt = item_datetime(item)
    if item_dt is None:
        return ""
    current = now or datetime.now().replace(microsecond=0)
    delay_seconds = int((current - item_dt).total_seconds())
    if delay_seconds < threshold_seconds:
        return ""
    return f"延迟：{delay_seconds}s"


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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS runtime_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS delivery_log (
            message_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            mode TEXT NOT NULL,
            sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (message_id, channel, mode)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS telegram_delivery_status (
            message_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            mode TEXT NOT NULL,
            status TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (message_id, channel, mode)
        )
    """)
    if migrated or needs_history_metadata_backfill(conn):
        backfill_history_metadata(conn)
    bootstrap_runtime_state(conn)
    conn.commit()


def get_state(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM runtime_state WHERE key = ?", (key,)).fetchone()
    return str(row[0]) if row else default


def set_state(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        """
        INSERT INTO runtime_state (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (key, "" if value is None else str(value)),
    )


def latest_history_cursor(
    conn: sqlite3.Connection,
    *,
    now: Optional[datetime] = None,
) -> tuple[str, str]:
    ceiling_dt = (
        (now or datetime.now()).replace(microsecond=0)
        + timedelta(seconds=CURSOR_FUTURE_GRACE_SECONDS)
    )
    rows = conn.execute(
        """
        SELECT published_at, id
        FROM flash_history
        WHERE published_at IS NOT NULL AND published_at != ''
        ORDER BY created_at DESC
        """,
    ).fetchall()
    best: tuple[datetime, str, str] | None = None
    for published_at, fid in rows:
        published_text = str(published_at or "")
        published_dt = parse_cursor_datetime(published_text)
        if published_dt is None or published_dt > ceiling_dt:
            continue
        if best is None or published_dt > best[0]:
            best = (published_dt, published_text, str(fid or ""))
    if best:
        return best[1], best[2]
    return "", ""


def bootstrap_runtime_state(conn: sqlite3.Connection) -> None:
    last_at, last_id = latest_history_cursor(conn)
    if last_at and not get_state(conn, "last_ingested_at"):
        set_state(conn, "last_ingested_at", last_at)
    if last_id and not get_state(conn, "last_ingested_id"):
        set_state(conn, "last_ingested_id", last_id)


def update_ingest_cursor(item: dict) -> None:
    fid = str(item.get("id", ""))
    item_dt = item_datetime(item)
    if not fid or item_dt is None:
        return
    item_dt = item_dt.replace(microsecond=0)
    now = datetime.now().replace(microsecond=0)
    future_limit = now + timedelta(seconds=CURSOR_FUTURE_GRACE_SECONDS)
    if item_dt > future_limit:
        log.warning(
            "跳过推进 last_ingested_at：消息时间 %s 超过当前时间保护阈值 %s（id=%s）",
            format_cursor_datetime(item_dt),
            format_cursor_datetime(future_limit),
            fid,
        )
        return

    conn = get_db()
    current_at = get_state(conn, "last_ingested_at")
    current_dt = parse_cursor_datetime(current_at)
    if current_at and current_dt is None:
        log.warning("last_ingested_at=%s 无法解析，将用当前有效消息修复游标", current_at)
    elif current_dt and current_dt > future_limit:
        log.warning(
            "last_ingested_at=%s 超过当前时间保护阈值 %s，将用当前有效消息修复游标",
            current_at,
            format_cursor_datetime(future_limit),
        )

    if not current_dt or current_dt > future_limit or item_dt >= current_dt:
        set_state(conn, "last_ingested_at", format_cursor_datetime(item_dt))
        set_state(conn, "last_ingested_id", fid)
        conn.commit()


def record_startup(startup_at: datetime) -> None:
    conn = get_db()
    set_state(conn, "last_startup_at", startup_at.isoformat(sep=" ", timespec="seconds"))
    conn.commit()


def history_item_exists(conn: sqlite3.Connection, message_id: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM flash_history WHERE id = ? LIMIT 1",
        (message_id,),
    ).fetchone())


def has_delivery(conn: sqlite3.Connection, message_id: str, *, channel: str, mode: str) -> bool:
    return bool(conn.execute(
        """
        SELECT 1
        FROM delivery_log
        WHERE message_id = ? AND channel = ? AND mode = ?
        LIMIT 1
        """,
        (message_id, channel, mode),
    ).fetchone())


def has_any_delivery(conn: sqlite3.Connection, message_id: str, *, channel: str) -> bool:
    return bool(conn.execute(
        """
        SELECT 1
        FROM delivery_log
        WHERE message_id = ? AND channel = ?
        LIMIT 1
        """,
        (message_id, channel),
    ).fetchone())


def mark_delivery(conn: sqlite3.Connection, message_id: str, *, channel: str, mode: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO delivery_log (message_id, channel, mode, sent_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (message_id, channel, mode),
    )


def record_telegram_delivery_status(
    conn: sqlite3.Connection,
    message_id: str,
    *,
    mode: str,
    status: str,
    detail: str = "",
    channel: str = "telegram",
) -> None:
    if not message_id:
        return
    conn.execute(
        """
        INSERT INTO telegram_delivery_status (message_id, channel, mode, status, detail, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(message_id, channel, mode) DO UPDATE SET
            status = excluded.status,
            detail = excluded.detail,
            updated_at = CURRENT_TIMESTAMP
        """,
        (message_id, channel, mode, status, detail[:500]),
    )


def catchup_summary_status_id(result: dict) -> str:
    window = result.get("window") or {}
    trigger = str(result.get("trigger") or "startup")
    start = str(window.get("start") or "")
    end = str(window.get("end") or "")
    return f"catchup_summary:{trigger}:{start}:{end}"


def catchup_summary_delivery_detail(result: dict, detail: str = "") -> str:
    return (
        f"stored={int(result.get('stored') or 0)} "
        f"push_candidates={int(result.get('push_candidates') or 0)} "
        f"truncated={bool(result.get('truncated'))}"
        + (f" detail={detail}" if detail else "")
    )


def print_telegram_delivery_status(status_filter: str, *, limit: int = 20) -> None:
    params: list[object] = []
    where = ""
    if status_filter == "problem":
        where = "WHERE t.status IN (?, ?, ?)"
        params.extend((TELEGRAM_STATUS_FAILED, TELEGRAM_STATUS_UNKNOWN_TIMEOUT, TELEGRAM_STATUS_SKIPPED))
    elif status_filter != "all":
        where = "WHERE t.status = ?"
        params.append(status_filter)
    params.append(limit)
    try:
        with open_readonly_history_db() as conn:
            rows = conn.execute(
                f"""
                SELECT t.updated_at, t.status, t.mode, t.message_id, t.detail,
                       h.published_at, h.priority_level, h.title, h.content
                FROM telegram_delivery_status t
                LEFT JOIN flash_history h ON h.id = t.message_id
                {where}
                ORDER BY t.updated_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
    except FileNotFoundError as exc:
        log.info("历史库不存在：%s", exc)
        return
    except sqlite3.OperationalError as exc:
        if "telegram_delivery_status" in str(exc):
            log.info("暂无 Telegram 投递状态记录：%s", status_filter)
        else:
            log.warning("Telegram 投递状态读取失败：%s", exc)
        return

    if not rows:
        log.info("暂无 Telegram 投递状态记录：%s", status_filter)
        return

    for row in rows:
        text = compact_text(" ".join(part for part in [str(row["title"] or ""), str(row["content"] or "")] if part), limit=72)
        priority = str(row["priority_level"] or "")
        labels = [str(row["status"]), str(row["mode"])] + ([priority] if priority else [])
        print(f"{row['updated_at']} [{' '.join(labels)}] id={row['message_id']}")
        if row["published_at"]:
            print(f"  消息时间：{row['published_at']}")
        if text:
            print(f"  内容：{text}")
        if row["detail"]:
            print(f"  详情：{compact_text(str(row['detail']), limit=160)}")


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
    conn.commit()


def save_history_item(
    item: dict,
    *,
    hit: bool,
    high: bool,
    source: str,
    priority_level: Optional[str] = None,
    advance_cursor: bool = False,
) -> None:
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
        INSERT INTO flash_history
            (id, published_at, title, content, hit, high, important, has_bold,
             priority_level, has_title, has_pic, pic_url, news_source, source_url,
             style_flags, source, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            published_at = excluded.published_at,
            title = excluded.title,
            content = excluded.content,
            hit = CASE WHEN flash_history.hit = 1 OR excluded.hit = 1 THEN 1 ELSE 0 END,
            high = CASE WHEN flash_history.high = 1 OR excluded.high = 1 THEN 1 ELSE 0 END,
            important = CASE WHEN flash_history.important = 1 OR excluded.important = 1 THEN 1 ELSE 0 END,
            has_bold = CASE WHEN flash_history.has_bold = 1 OR excluded.has_bold = 1 THEN 1 ELSE 0 END,
            priority_level = CASE
                WHEN flash_history.priority_level = ? OR excluded.priority_level = ? THEN ?
                WHEN flash_history.priority_level = ? OR excluded.priority_level = ? THEN ?
                WHEN flash_history.priority_level = ? OR excluded.priority_level = ? THEN ?
                ELSE ?
            END,
            has_title = excluded.has_title,
            has_pic = excluded.has_pic,
            pic_url = excluded.pic_url,
            news_source = excluded.news_source,
            source_url = excluded.source_url,
            style_flags = CASE
                WHEN flash_history.priority_level = ? AND excluded.priority_level != ? THEN flash_history.style_flags
                WHEN flash_history.priority_level = ? AND excluded.priority_level IN (?, ?) THEN flash_history.style_flags
                WHEN flash_history.priority_level = ? AND excluded.priority_level = ? THEN flash_history.style_flags
                ELSE excluded.style_flags
            END,
            raw_json = excluded.raw_json
        """,
        values + (
            PRIORITY_IMPORTANT,
            PRIORITY_IMPORTANT,
            PRIORITY_IMPORTANT,
            PRIORITY_HIGH,
            PRIORITY_HIGH,
            PRIORITY_HIGH,
            PRIORITY_NORMAL,
            PRIORITY_NORMAL,
            PRIORITY_NORMAL,
            PRIORITY_NONE,
            PRIORITY_IMPORTANT,
            PRIORITY_IMPORTANT,
            PRIORITY_HIGH,
            PRIORITY_NORMAL,
            PRIORITY_NONE,
            PRIORITY_NORMAL,
            PRIORITY_NONE,
        ),
    )
    if advance_cursor:
        update_ingest_cursor(item)
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

def is_temp_history_db() -> bool:
    try:
        db_path = HISTORY_DB.expanduser().resolve(strict=False)
    except Exception:
        db_path = HISTORY_DB.expanduser().absolute()
    db_text = str(db_path)
    return db_text.startswith(("/tmp/", "/private/tmp/", "/var/folders/", "/private/var/folders/"))


def telegram_skip_reason() -> str:
    if not TG_TOKEN or not TG_CHAT_ID:
        return "Telegram 未配置"
    if is_temp_history_db() and not ALLOW_TMP_TELEGRAM:
        return (
            f"HISTORY_DB={HISTORY_DB} 是临时测试库，已跳过真实 Telegram 发送；"
            "如需强制发送，设置 ALLOW_TMP_TELEGRAM=1"
        )
    return ""


async def send_telegram(session: aiohttp.ClientSession, text: str) -> TelegramSendResult:
    skip_reason = telegram_skip_reason()
    if skip_reason:
        log.warning("Telegram 已跳过：%s\n%s", skip_reason, text)
        return TelegramSendResult(TELEGRAM_STATUS_SKIPPED, skip_reason)
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    max_attempts = 1 + len(TELEGRAM_RETRY_DELAYS)
    retry_statuses = {500, 502, 503, 504}
    retry_exceptions = (
        aiohttp.ClientConnectorError,
        aiohttp.ClientOSError,
        aiohttp.ServerDisconnectedError,
    )
    for attempt in range(1, max_attempts + 1):
        try:
            async with session.post(url, json=payload, timeout=TELEGRAM_TIMEOUT) as resp:
                body = await resp.text()
                if resp.status == 200:
                    return TelegramSendResult(TELEGRAM_STATUS_SENT)
                should_retry = resp.status in retry_statuses and attempt < max_attempts
                log_fn = log.warning if should_retry else log.error
                log_fn("Telegram 发送失败: status=%s attempt=%s/%s body=%s", resp.status, attempt, max_attempts, body[:500])
                if not should_retry:
                    return TelegramSendResult(TELEGRAM_STATUS_FAILED, f"status={resp.status} body={body[:500]}")
        except asyncio.TimeoutError as exc:
            log.error(
                "Telegram 超时，送达状态未知，未自动重试以避免重复: attempt=%s/%s error=%s",
                attempt,
                max_attempts,
                repr(exc),
            )
            return TelegramSendResult(TELEGRAM_STATUS_UNKNOWN_TIMEOUT, repr(exc))
        except retry_exceptions as exc:
            should_retry = attempt < max_attempts
            log_fn = log.warning if should_retry else log.error
            log_fn(
                "Telegram 网络异常: type=%s attempt=%s/%s error=%s",
                type(exc).__name__,
                attempt,
                max_attempts,
                repr(exc),
            )
            if not should_retry:
                return TelegramSendResult(TELEGRAM_STATUS_FAILED, f"{type(exc).__name__}: {repr(exc)}")
        except Exception as exc:
            log.error(
                "Telegram 异常: type=%s attempt=%s/%s error=%s",
                type(exc).__name__,
                attempt,
                max_attempts,
                repr(exc),
            )
            return TelegramSendResult(TELEGRAM_STATUS_FAILED, f"{type(exc).__name__}: {repr(exc)}")
        await asyncio.sleep(TELEGRAM_RETRY_DELAYS[attempt - 1])
    return TelegramSendResult(TELEGRAM_STATUS_FAILED, "retry attempts exhausted")


# ─── 去重 + 已处理 ID 集合 ───────────────────────────────────────────────────

seen_ids: OrderedDict[str, None] = OrderedDict()


def remember_seen_id(fid: str) -> None:
    if not fid:
        return
    seen_ids[fid] = None
    if len(seen_ids) > 2000:          # 防止无限增长
        for _ in range(500):
            seen_ids.popitem(last=False)


def is_new(item: dict) -> bool:
    fid = str(item.get("id", ""))
    if not fid or fid in seen_ids:
        return False
    remember_seen_id(fid)
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
    return item_datetime(item)


def parse_cli_datetime(value: str, *, label: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise SystemExit(f"{label} 格式应为 YYYY-MM-DD HH:MM 或 YYYY-MM-DD HH:MM:SS")


def previous_page_cursor(dated: list[tuple[datetime, dict]], current_cursor: str) -> str:
    oldest_dt = min(item_dt for item_dt, _ in dated)
    next_dt = oldest_dt - timedelta(seconds=1)
    current_dt = parse_cursor_datetime(current_cursor)
    if current_dt and next_dt >= current_dt:
        next_dt = current_dt - timedelta(seconds=1)
    return format_cursor_datetime(next_dt)


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


def classify_item_for_push(item: dict) -> tuple[bool, bool, str]:
    text = item_full_text(item)
    hit, high = match_keywords(text)
    return hit, high, classify_priority(item, hit=hit, high=high)


def select_catchup_send_candidates(rows: list[dict], max_send: int) -> list[dict]:
    """Keep Telegram catch-up bounded while preserving time order for selected messages."""
    if max_send <= 0:
        return []
    selected_ids: set[str] = set()
    for priority in (PRIORITY_IMPORTANT, PRIORITY_HIGH, PRIORITY_NORMAL):
        for row in rows:
            if len(selected_ids) >= max_send:
                break
            if row["should_push"] and not row["already_delivered"] and row["priority_level"] == priority:
                selected_ids.add(row["id"])
        if len(selected_ids) >= max_send:
            break
    return [row for row in rows if row["id"] in selected_ids]


def build_catchup_summary_items(rows: list[dict], limit: int = 10) -> list[dict]:
    priority_order = {PRIORITY_IMPORTANT: 0, PRIORITY_HIGH: 1}
    candidates = [
        row for row in rows
        if row["should_push"] and row["priority_level"] in priority_order
    ]
    candidates.sort(key=lambda row: (priority_order[row["priority_level"]], row["time"]))

    items = []
    for row in candidates[:limit]:
        title, content = item_text(row["item"])
        text = title or content or str(row["id"])
        items.append({
            "time": row["time"],
            "priority_level": row["priority_level"],
            "text": compact_text(text),
        })
    return items


def catch_up_window(
    start_dt: datetime,
    end_dt: datetime,
    *,
    source: str,
    max_store: int = CATCHUP_MAX_STORE,
    max_send: int = CATCHUP_MAX_SEND,
    sleep_s: float = 0.3,
) -> dict:
    """Backfill a fixed offline window before realtime starts, so old and live messages do not interleave."""
    if end_dt <= start_dt:
        return {
            "ok": True,
            "source": source,
            "window": {"start": start_dt, "end": end_dt},
            "scanned": 0,
            "stored": 0,
            "push_candidates": 0,
            "priority_counts": {},
            "already_stored": 0,
            "already_delivered": 0,
            "send_candidates": [],
            "send_candidate_count": 0,
            "summary_items": [],
            "seen_item_ids": [],
            "truncated": False,
            "error": "",
        }

    cursor = (end_dt + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    max_pages = max(1, min(200, (max_store // 20) + 10))
    last_error = None
    conn = get_db()
    for app_id in APP_IDS:
        seen: set[str] = set()
        collected: list[dict[str, Any]] = []
        pages = 0
        oldest_seen = None
        truncated = False
        existing_total = 0
        try:
            while pages < max_pages and len(collected) < max_store:
                page = fetch_page_sync(cursor, app_id)
                pages += 1
                if not page:
                    break

                dated = []
                page_window_hits = 0
                page_existing_hits = 0
                for item in page:
                    item_dt = parse_item_time(item)
                    if item_dt is None:
                        continue
                    dated.append((item_dt, item))
                    if oldest_seen is None or item_dt < oldest_seen:
                        oldest_seen = item_dt

                    fid = str(item.get("id") or "")
                    if not fid or fid in seen:
                        continue
                    seen.add(fid)

                    if start_dt < item_dt <= end_dt:
                        already_stored = history_item_exists(conn, fid)
                        already_delivered = has_any_delivery(conn, fid, channel="telegram")
                        collected.append({
                            "item_dt": item_dt,
                            "item": item,
                            "already_stored": already_stored,
                            "already_delivered": already_delivered,
                        })
                        page_window_hits += 1
                        if already_stored:
                            page_existing_hits += 1
                        if len(collected) >= max_store:
                            truncated = True
                            break

                existing_total += page_existing_hits
                if page_window_hits > 0 or pages > 1:
                    log.info(
                        "catch-up page=%s source=%s app_id=%s window_hits=%s collected=%s existing=%s",
                        pages,
                        source,
                        app_id,
                        page_window_hits,
                        len(collected),
                        existing_total,
                    )

                if truncated or (oldest_seen and oldest_seen <= start_dt):
                    break
                if dated:
                    cursor = previous_page_cursor(dated, cursor)
                else:
                    break
                time.sleep(sleep_s + random.uniform(0, 0.2))

            collected.sort(key=lambda row: row["item_dt"])
            rows = []
            for entry in collected:
                item_dt = entry["item_dt"]
                item = entry["item"]
                fid = str(item.get("id") or "")
                hit, high, priority_level = classify_item_for_push(item)
                should = should_push(priority_level, hit=hit)
                already_stored = bool(entry["already_stored"])
                already_delivered = bool(entry["already_delivered"])
                if not already_stored:
                    save_history_item(
                        item,
                        hit=hit,
                        high=high,
                        source=source,
                        priority_level=priority_level,
                        advance_cursor=True,
                    )
                rows.append({
                    "id": fid,
                    "time": item_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "item": item,
                    "hit": hit,
                    "high": high,
                    "priority_level": priority_level,
                    "should_push": should,
                    "already_stored": already_stored,
                    "already_delivered": already_delivered,
                })

            send_candidates = select_catchup_send_candidates(rows, max_send)
            summary_items = build_catchup_summary_items(rows)
            priority_counts = {
                priority: sum(1 for row in rows if row["should_push"] and row["priority_level"] == priority)
                for priority in (PRIORITY_IMPORTANT, PRIORITY_HIGH, PRIORITY_NORMAL)
            }
            set_state(conn, "last_catchup_at", datetime.now().replace(microsecond=0).isoformat(sep=" "))
            conn.commit()
            return {
                "ok": True,
                "source": source,
                "app_id": app_id,
                "window": {
                    "start": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "end": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                },
                "pages": pages,
                "scanned": len(rows),
                "stored": sum(1 for row in rows if not row["already_stored"]),
                "push_candidates": sum(1 for row in rows if row["should_push"]),
                "priority_counts": priority_counts,
                "already_stored": sum(1 for row in rows if row["already_stored"]),
                "already_delivered": sum(1 for row in rows if row["already_delivered"]),
                "send_candidates": send_candidates,
                "send_candidate_count": len(send_candidates),
                "summary_items": summary_items,
                "seen_item_ids": [row["id"] for row in rows if row["id"]],
                "truncated": truncated,
                "error": "",
            }
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            log.warning("catch-up app_id %s 失败，尝试下一个: %s", app_id, last_error)
    return {"ok": False, "error": last_error or "未知错误", "send_candidates": [], "summary_items": [], "seen_item_ids": []}


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
                    cursor = previous_page_cursor(dated, cursor)
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


def print_catchup_summary(result: dict) -> None:
    window = result.get("window", {})
    print(f"离线补拉窗口: {window.get('start')} -> {window.get('end')} ok={result.get('ok')}")
    if not result.get("ok"):
        print(f"错误: {result.get('error')}")
        return
    print(f"入库: {result.get('stored', 0)} 条")
    if result.get("already_stored"):
        print(f"已存在未重复入库: {result.get('already_stored', 0)} 条")
    print(f"命中推送条件: {result.get('push_candidates', 0)} 条")
    print(f"已推送过未重复发送: {result.get('already_delivered', 0)} 条")
    print(f"本次候选发送: {result.get('send_candidate_count', 0)} 条")
    if result.get("telegram_enabled"):
        print(f"Telegram 已发送: {result.get('telegram_sent', 0)} 条")
        if result.get("telegram_skipped"):
            print(f"Telegram 已跳过: {result.get('telegram_skipped', 0)} 条")
            print(f"跳过原因: {result.get('telegram_skip_reason', '')}")
        print(f"Telegram 发送失败: {result.get('telegram_failed', 0)} 条")
    if result.get("truncated"):
        print("注意: 补拉入库达到上限，窗口可能被截断。")
    summary_items = result.get("summary_items") or []
    if summary_items:
        print("重点消息:")
        for index, row in enumerate(summary_items, 1):
            icon = PRIORITY_ICONS.get(row.get("priority_level"), "📰")
            print(f"{index}. {icon} {row.get('time', '')} {row.get('text', '')}")


def format_catchup_summary_message(result: dict) -> str:
    window = result.get("window", {})
    counts = result.get("priority_counts") or {}
    trigger = result.get("trigger", "startup")
    title = "金十自愈补拉完成" if trigger == "gap" else "金十离线补拉完成"
    lines = [
        f"📦 <b>{title}</b>",
        f"窗口：{escape(str(window.get('start', '')))} → {escape(str(window.get('end', '')))}",
        f"入库：{int(result.get('stored') or 0)} 条",
        f"已存在未重复入库：{int(result.get('already_stored') or 0)} 条",
        f"命中推送条件：{int(result.get('push_candidates') or 0)} 条",
        (
            "分级："
            f"⚡ {int(counts.get(PRIORITY_IMPORTANT) or 0)} / "
            f"🚨 {int(counts.get(PRIORITY_HIGH) or 0)} / "
            f"📰 {int(counts.get(PRIORITY_NORMAL) or 0)}"
        ),
        "自动补拉只入库和摘要，不逐条推送历史消息。",
    ]
    summary_items = result.get("summary_items") or []
    if summary_items:
        lines.append("")
        lines.append("<b>重点消息：</b>")
        for index, row in enumerate(summary_items, 1):
            icon = PRIORITY_ICONS.get(row.get("priority_level"), "📰")
            lines.append(
                f"{index}. {icon} {escape(str(row.get('time', '')))} "
                f"{escape(str(row.get('text', '')))}"
            )
    if result.get("limited_by_max_hours"):
        lines.append(f"已按 CATCHUP_MAX_HOURS={CATCHUP_MAX_HOURS} 截断较早窗口。")
    if result.get("truncated"):
        lines.append(f"入库达到 CATCHUP_MAX_STORE={CATCHUP_MAX_STORE} 上限，窗口可能未完全覆盖。")
    return "\n".join(lines)


async def run_catch_up(
    start_dt: datetime,
    end_dt: datetime,
    *,
    telegram_enabled: bool,
    max_store: int,
    max_send: int,
    send_interval: float,
) -> dict:
    init_history_db()
    result = await asyncio.to_thread(
        catch_up_window,
        start_dt,
        end_dt,
        source="catchup_manual",
        max_store=max_store,
        max_send=max_send,
    )
    result["telegram_enabled"] = telegram_enabled
    result["telegram_sent"] = 0
    result["telegram_failed"] = 0
    result["telegram_skipped"] = 0
    result["telegram_skip_reason"] = ""
    if not result.get("ok") or not telegram_enabled:
        return result

    skip_reason = telegram_skip_reason()
    if skip_reason:
        result["telegram_skipped"] = len(result.get("send_candidates") or [])
        result["telegram_skip_reason"] = skip_reason
        conn = get_db()
        for row in result.get("send_candidates") or []:
            record_telegram_delivery_status(
                conn,
                row["id"],
                mode="catchup",
                status=TELEGRAM_STATUS_SKIPPED,
                detail=skip_reason,
            )
        conn.commit()
        log.warning("补拉 Telegram 测试已走到发送环节，但被保护规则跳过：%s", skip_reason)
        return result

    connector = aiohttp.TCPConnector(limit=5, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        conn = get_db()
        for row in result.get("send_candidates") or []:
            item = row["item"]
            priority = row["priority_level"]
            msg = format_message(item, priority, catchup=True)
            send_result = await send_telegram(session, msg)
            if send_result.ok:
                mark_delivery(conn, row["id"], channel="telegram", mode="catchup")
                result["telegram_sent"] += 1
            else:
                result["telegram_failed"] += 1
            record_telegram_delivery_status(
                conn,
                row["id"],
                mode="catchup",
                status=send_result.status,
                detail=send_result.detail,
            )
            if send_interval > 0:
                await asyncio.sleep(send_interval)
        conn.commit()
    return result


async def run_auto_catch_up(
    session: aiohttp.ClientSession,
    end_at: datetime,
    *,
    trigger: str = "startup",
) -> dict:
    """Store a missed window; auto mode sends one compact Telegram summary, not every item."""
    conn = get_db()
    last_at = get_state(conn, "last_ingested_at")
    if not last_at:
        return {"ok": True, "skipped": True, "reason": "暂无 last_ingested_at", "trigger": trigger}

    try:
        start_dt = parse_cli_datetime(last_at, label="last_ingested_at")
    except SystemExit as exc:
        return {"ok": False, "error": str(exc), "trigger": trigger}

    future_limit = end_at.replace(microsecond=0) + timedelta(seconds=CURSOR_FUTURE_GRACE_SECONDS)
    if start_dt > future_limit:
        history_at, history_id = latest_history_cursor(conn, now=end_at)
        history_dt = parse_cursor_datetime(history_at)
        if not history_dt:
            return {
                "ok": True,
                "skipped": True,
                "reason": f"last_ingested_at 位于未来且暂无可恢复历史游标：{last_at}",
                "trigger": trigger,
            }
        log.warning(
            "last_ingested_at=%s 超过自动补拉保护阈值 %s，回退到历史库最新有效游标 %s",
            last_at,
            format_cursor_datetime(future_limit),
            history_at,
        )
        set_state(conn, "last_ingested_at", history_at)
        if history_id:
            set_state(conn, "last_ingested_id", history_id)
        conn.commit()
        start_dt = history_dt

    start_dt = start_dt - timedelta(seconds=AUTO_CATCHUP_START_BUFFER_SECONDS)

    limited_by_max_hours = False
    floor_dt = end_at - timedelta(hours=max(1, CATCHUP_MAX_HOURS))
    if start_dt < floor_dt:
        start_dt = floor_dt
        limited_by_max_hours = True

    if end_at <= start_dt:
        return {
            "ok": True,
            "skipped": True,
            "reason": "没有离线窗口",
            "trigger": trigger,
            "window": {
                "start": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "end": end_at.strftime("%Y-%m-%d %H:%M:%S"),
            },
        }

    result = await asyncio.to_thread(
        catch_up_window,
        start_dt,
        end_at,
        source="catchup_auto",
        max_store=CATCHUP_MAX_STORE,
        max_send=0,
    )
    if result.get("ok"):
        for fid in result.get("seen_item_ids") or []:
            remember_seen_id(str(fid))
    result["trigger"] = trigger
    result["limited_by_max_hours"] = limited_by_max_hours
    result["telegram_summary_sent"] = False
    result["telegram_summary_skipped"] = False
    result["telegram_skip_reason"] = ""
    should_send_summary = result.get("ok") and CATCHUP_TELEGRAM and (result.get("stored") or result.get("truncated"))
    if should_send_summary and trigger == "gap":
        last_summary_at = get_state(conn, "last_gap_summary_telegram_at")
        last_summary_dt = parse_cursor_datetime(last_summary_at)
        if last_summary_dt:
            since_last = (end_at.replace(microsecond=0) - last_summary_dt).total_seconds()
            if since_last < AUTO_CATCHUP_SUMMARY_COOLDOWN_SECONDS:
                should_send_summary = False
                log.info(
                    "自愈补拉摘要不发送：距离上次摘要 %.0fs，小于冷却 %ss",
                    since_last,
                    AUTO_CATCHUP_SUMMARY_COOLDOWN_SECONDS,
                )
    if should_send_summary:
        skip_reason = telegram_skip_reason()
        if skip_reason:
            result["telegram_summary_skipped"] = True
            result["telegram_skip_reason"] = skip_reason
            record_telegram_delivery_status(
                conn,
                catchup_summary_status_id(result),
                mode="catchup_summary",
                status=TELEGRAM_STATUS_SKIPPED,
                detail=catchup_summary_delivery_detail(result, skip_reason),
            )
            conn.commit()
            log.warning("自动补拉摘要已生成，但被保护规则跳过 Telegram：%s", skip_reason)
        else:
            send_result = await send_telegram(session, format_catchup_summary_message(result))
            result["telegram_summary_sent"] = send_result.ok
            if trigger == "gap":
                set_state(conn, "last_gap_summary_telegram_at", end_at.replace(microsecond=0).isoformat(sep=" "))
            record_telegram_delivery_status(
                conn,
                catchup_summary_status_id(result),
                mode="catchup_summary",
                status=send_result.status,
                detail=catchup_summary_delivery_detail(result, send_result.detail),
            )
            conn.commit()
    return result


async def poll_loop(session: aiohttp.ClientSession) -> None:
    """轮询模式：每隔 POLL_INTERVAL 秒拉一次，仅处理新条目"""
    log.info("▶ 启动 REST 轮询（间隔 %ss）", POLL_INTERVAL)
    last_loop_at = datetime.now().replace(microsecond=0)
    while True:
        now = datetime.now().replace(microsecond=0)
        gap_seconds = (now - last_loop_at).total_seconds()
        if AUTO_CATCHUP and AUTO_CATCHUP_GAP_SECONDS > 0 and gap_seconds >= AUTO_CATCHUP_GAP_SECONDS:
            log.warning(
                "检测到轮询停顿 %.0fs，执行自愈补拉摘要（阈值 %ss）",
                gap_seconds,
                AUTO_CATCHUP_GAP_SECONDS,
            )
            try:
                catchup_result = await run_auto_catch_up(session, now, trigger="gap")
                if catchup_result.get("skipped"):
                    log.info("自愈补拉：跳过（%s）", catchup_result.get("reason", "无需补拉"))
                elif catchup_result.get("ok"):
                    window = catchup_result.get("window", {})
                    log.info(
                        "自愈补拉完成：%s -> %s，入库 %s 条，命中 %s 条，摘要 %s",
                        window.get("start"),
                        window.get("end"),
                        catchup_result.get("stored", 0),
                        catchup_result.get("push_candidates", 0),
                        "已发送" if catchup_result.get("telegram_summary_sent") else "未发送",
                    )
                else:
                    log.warning("自愈补拉失败，继续实时监控：%s", catchup_result.get("error"))
            except Exception as exc:
                log.warning("自愈补拉异常，继续实时监控：%s", exc)

        last_loop_at = datetime.now().replace(microsecond=0)
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
                                        remember_seen_id(fid)
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
    save_history_item(
        item,
        hit=hit,
        high=high,
        source=source,
        priority_level=priority_level,
        advance_cursor=source in {"ws", "rest", "catchup_auto", "catchup_manual"},
    )
    if not should_push(priority_level, hit=hit):
        return
    if not item_full_text(item):
        log.info("跳过无可显示内容的推送：id=%s type=%s priority=%s", item.get("id", ""), item.get("type", ""), priority_level)
        return

    log.info("\n%s", format_console_message(item, priority_level=priority_level))
    msg = format_message(item, priority_level)
    send_result = await send_telegram(session, msg)
    conn = get_db()
    if send_result.ok:
        mark_delivery(conn, str(item.get("id", "")), channel="telegram", mode="realtime")
    record_telegram_delivery_status(
        conn,
        str(item.get("id", "")),
        mode="realtime",
        status=send_result.status,
        detail=send_result.detail,
    )
    conn.commit()


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
    startup_at = datetime.now().replace(microsecond=0)
    record_startup(startup_at)

    connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        if AUTO_CATCHUP:
            log.info("离线补拉：检查上次入库到本次启动之间的窗口 …")
            try:
                catchup_result = await run_auto_catch_up(session, startup_at)
                if catchup_result.get("skipped"):
                    log.info("离线补拉：跳过（%s）", catchup_result.get("reason", "无需补拉"))
                elif catchup_result.get("ok"):
                    window = catchup_result.get("window", {})
                    log.info(
                        "离线补拉完成：%s -> %s，入库 %s 条，命中 %s 条，摘要 %s",
                        window.get("start"),
                        window.get("end"),
                        catchup_result.get("stored", 0),
                        catchup_result.get("push_candidates", 0),
                        "已发送" if catchup_result.get("telegram_summary_sent") else "未发送",
                    )
                    if catchup_result.get("truncated"):
                        log.warning("离线补拉达到入库上限，窗口可能被截断")
                else:
                    log.warning("离线补拉失败，继续启动实时监控：%s", catchup_result.get("error"))
            except Exception as exc:
                log.warning("离线补拉异常，继续启动实时监控：%s", exc)

        # 冷启动：先拉一批历史条目填充 seen_ids（不推送），避免重启后刷屏
        log.info("冷启动：预加载已有快讯 ID …")
        items = await poll_once(session)
        pending_realtime = []
        for item in items:
            item_dt = parse_item_time(item)
            if item_dt and item_dt > startup_at:
                pending_realtime.append(item)
                continue

            fid = str(item.get("id", ""))
            if fid:
                remember_seen_id(fid)
            title, content = item_text(item)
            hit, high = match_keywords(f"{title} {content}")
            save_history_item(item, hit=hit, high=high, source="cold_start")
        log.info("预加载完成，已忽略 %d 条旧快讯", len(seen_ids))
        for item in reversed(pending_realtime):
            if is_new(item):
                await handle_item(session, item, source="rest")
        if pending_realtime:
            log.info("冷启动期间新增 %d 条快讯，已按实时消息处理", len(pending_realtime))

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
    parser.add_argument("--telegram-status", nargs="?", const="problem", choices=["problem", "failed", "unknown_timeout", "skipped", "sent", "all"], help="只读查询 Telegram 投递状态，默认显示 failed/unknown_timeout/skipped")
    parser.add_argument("--telegram-status-limit", type=int, default=20, help="Telegram 投递状态查询返回条数")
    parser.add_argument("--lookup-date", help="回溯查询日期 YYYY-MM-DD")
    parser.add_argument("--lookup-start", help="回溯开始时间 HH:MM，北京时间")
    parser.add_argument("--lookup-end", help="回溯结束时间 HH:MM，北京时间")
    parser.add_argument("--lookup-keywords", default=",".join(KEYWORDS), help="回溯高亮关键词，逗号分隔")
    parser.add_argument("--lookup-max-pages", type=int, default=12, help="回溯最多翻页数")
    parser.add_argument("--lookup-format", choices=["text", "json"], default="text", help="回溯输出格式")
    parser.add_argument("--catch-up", action="store_true", help="手动补拉离线窗口消息")
    parser.add_argument("--from", dest="catchup_from", help="补拉开始时间 YYYY-MM-DD HH:MM[:SS]")
    parser.add_argument("--to", dest="catchup_to", help="补拉结束时间 YYYY-MM-DD HH:MM[:SS]")
    parser.add_argument("--catch-up-telegram", dest="catchup_telegram", action="store_true", default=None, help="补拉后发送 Telegram")
    parser.add_argument("--no-catch-up-telegram", dest="catchup_telegram", action="store_false", help="补拉只入库和终端显示，不发送 Telegram")
    parser.add_argument("--catch-up-max-store", type=int, default=CATCHUP_MAX_STORE, help="补拉最多入库条数")
    parser.add_argument("--catch-up-max-send", type=int, default=CATCHUP_MAX_SEND, help="补拉最多发送 Telegram 条数")
    parser.add_argument("--catch-up-send-interval", type=float, default=CATCHUP_SEND_INTERVAL, help="补拉 Telegram 发送间隔秒数")
    return parser.parse_args()


if __name__ == "__main__":
    try:
        args = parse_args()
        if args.telegram_status is not None:
            print_telegram_delivery_status(args.telegram_status, limit=max(1, args.telegram_status_limit))
        elif args.catch_up:
            init_history_db()
            conn = get_db()
            if args.catchup_from:
                start_dt = parse_cli_datetime(args.catchup_from, label="--from")
            else:
                last_at = get_state(conn, "last_ingested_at")
                if not last_at:
                    raise SystemExit("暂无 last_ingested_at，请使用 --from 指定补拉开始时间")
                start_dt = parse_cli_datetime(last_at, label="last_ingested_at")
            end_dt = parse_cli_datetime(args.catchup_to, label="--to") if args.catchup_to else datetime.now().replace(microsecond=0)
            if end_dt <= start_dt:
                raise SystemExit("--to 必须晚于 --from / last_ingested_at")
            telegram_enabled = CATCHUP_TELEGRAM if args.catchup_telegram is None else bool(args.catchup_telegram)
            result = asyncio.run(run_catch_up(
                start_dt,
                end_dt,
                telegram_enabled=telegram_enabled,
                max_store=max(1, args.catch_up_max_store),
                max_send=max(0, args.catch_up_max_send),
                send_interval=max(0.0, args.catch_up_send_interval),
            ))
            print_catchup_summary(result)
        elif args.lookup_date or args.lookup_start or args.lookup_end:
            if not (args.lookup_date and args.lookup_start and args.lookup_end):
                raise SystemExit("--lookup-date、--lookup-start、--lookup-end 需要同时提供")
            start_dt = parse_cli_datetime(f"{args.lookup_date} {args.lookup_start}", label="lookup start")
            end_dt = parse_cli_datetime(f"{args.lookup_date} {args.lookup_end}", label="lookup end")
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
