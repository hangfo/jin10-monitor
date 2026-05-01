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
import struct
from datetime import datetime
from html import escape
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
    "x-app-id": "SO1EJGmNgCtmpcPF",
    "x-version": "1.0.0",
}

# ─── 工具函数 ────────────────────────────────────────────────────────────────

def get_headers() -> dict:
    return {**BASE_HEADERS, "User-Agent": random.choice(UA_POOL)}


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
        "ping_interval": 20,
        "ping_timeout": 10,
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
    data = item.get("data", {})
    if not isinstance(data, dict):
        data = {}
    title = clean_html(str(data.get("title") or item.get("title") or ""))
    content = clean_html(str(data.get("content") or item.get("content") or ""))
    return title, content


def match_keywords(text: str) -> tuple[bool, bool]:
    """返回 (是否命中任意关键词, 是否命中高优先级)"""
    if not KEYWORDS:
        return True, any(k in text for k in HIGH_PRIORITY)
    hit = any(k in text for k in KEYWORDS)
    hi  = any(k in text for k in HIGH_PRIORITY)
    return hit, hi


def clean_html(raw: str) -> str:
    return re.sub(r"<[^>]+>", "", raw).strip()


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


def format_message(item: dict, high: bool) -> str:
    icon    = "🚨" if high else "📰"
    title, content = item_text(item)
    ts      = item.get("time", "")
    try:
        ts = datetime.fromtimestamp(int(ts)).strftime("%H:%M:%S")
    except Exception:
        pass

    parts = [f"{icon} <b>金十快讯</b>  {ts}"]
    if title:
        parts.append(f"<b>{escape(title)}</b>")
    if content:
        parts.append(escape(content))
    return "\n".join(parts)


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

seen_ids: set[str] = set()


def is_new(item: dict) -> bool:
    fid = str(item.get("id", ""))
    if not fid or fid in seen_ids:
        return False
    seen_ids.add(fid)
    if len(seen_ids) > 2000:          # 防止无限增长
        oldest = list(seen_ids)[:500]
        for i in oldest:
            seen_ids.discard(i)
    return True


# ─── REST 轮询（备用 / 冷启动） ───────────────────────────────────────────────

FLASH_API = "https://flash-api.jin10.com/get_flash_list"


async def poll_once(session: aiohttp.ClientSession) -> list[dict]:
    params = {"category": "-1", "id": "0", "vip": "0"}
    try:
        async with session.get(
            FLASH_API,
            params=params,
            headers=get_headers(),
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                return data.get("data", [])
            log.warning("REST 状态码: %s", resp.status)
    except asyncio.TimeoutError:
        log.warning("REST 超时")
    except Exception as e:
        log.warning("REST 异常: %s", e)
    return []


async def poll_loop(session: aiohttp.ClientSession) -> None:
    """轮询模式：每隔 POLL_INTERVAL 秒拉一次，仅处理新条目"""
    log.info("▶ 启动 REST 轮询（间隔 %ss）", POLL_INTERVAL)
    while True:
        items = await poll_once(session)
        for item in items:
            if is_new(item):
                await handle_item(session, item)
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
                            await handle_item(session, data)
                    elif code == 1200 and isinstance(data, list):
                        if not skipped_initial_list:
                            for item in data:
                                if isinstance(item, dict):
                                    seen_ids.add(str(item.get("id", "")))
                            skipped_initial_list = True
                            log.info("WebSocket 初始历史列表已预热去重：%d 条", len(data))
                            continue
                        for item in data:
                            if isinstance(item, dict) and item.get("action") in {1, 2} and is_new(item):
                                await handle_item(session, item)
        except Exception as e:
            log.warning("WebSocket 断线: %s，%ss 后重连", e, WS_RECONNECT_DELAY)
            await asyncio.sleep(WS_RECONNECT_DELAY)


# ─── 核心处理 ────────────────────────────────────────────────────────────────

async def handle_item(session: aiohttp.ClientSession, item: dict) -> None:
    title, content = item_text(item)
    text    = f"{title} {content}"

    hit, high = match_keywords(text)
    if not hit:
        return

    log.info("[%s] %s", "🚨HIGH" if high else "INFO", text[:80])
    msg = format_message(item, high)
    await send_telegram(session, msg)


async def run_once(limit: int) -> None:
    connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        items = await poll_once(session)
        log.info("一次性抓取完成：收到 %d 条，处理前 %d 条", len(items), min(limit, len(items)))
        for item in reversed(items[:limit]):
            await handle_item(session, item)


# ─── 主入口 ─────────────────────────────────────────────────────────────────

async def main() -> None:
    log.info("=== 金十快讯监控启动 ===")
    log.info("关键词: %s 条  Telegram: %s", len(KEYWORDS), "已配置" if TG_TOKEN else "未配置（仅打印）")

    connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        # 冷启动：先拉一批历史条目填充 seen_ids（不推送），避免重启后刷屏
        log.info("冷启动：预加载已有快讯 ID …")
        items = await poll_once(session)
        for item in items:
            seen_ids.add(str(item.get("id", "")))
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
    return parser.parse_args()


if __name__ == "__main__":
    try:
        args = parse_args()
        if args.once:
            asyncio.run(run_once(max(1, args.limit)))
        else:
            asyncio.run(main())
    except KeyboardInterrupt:
        log.info("已手动停止")
