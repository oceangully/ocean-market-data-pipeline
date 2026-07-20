#!/usr/bin/env python3
"""
Ocean Market Data Pipeline — OKX A2MCP Server
面向 AI Agent 的一站式金融数据基础设施
启动: python3 server.py --port 9000
"""

import json
import urllib.request
import re
import html as html_mod
from xml.etree import ElementTree as ET
from datetime import datetime, timezone, timedelta
from mcp.server import Server
from mcp.types import Tool, TextContent
import asyncio
import argparse
import base64

# ============================================================
# 工具函数
# ============================================================

def get_crypto_price(ticker: str) -> dict:
    symbol_map = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "BNB": "BNBUSDT", "SOL": "SOLUSDT"}
    symbol = symbol_map.get(ticker.upper())
    if not symbol:
        if ticker.upper() == "HYPE":
            return _get_hype_price()
        return {"error": f"不支持 {ticker}，支持: BTC/ETH/BNB/SOL/HYPE"}
    url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    return {
        "ticker": ticker.upper(),
        "price": float(data["lastPrice"]),
        "change_pct": round(float(data["priceChangePercent"]), 2),
        "high_24h": float(data["highPrice"]),
        "low_24h": float(data["lowPrice"]),
        "volume": float(data["volume"]),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def _get_hype_price() -> dict:
    url = "https://api.coingecko.com/api/v3/simple/price?ids=hyperliquid&vs_currencies=usd&include_24hr_change=true"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    d = data.get("hyperliquid", {})
    return {"ticker": "HYPE", "price": d.get("usd"), "change_pct": round(d.get("usd_24h_change", 0), 2), "timestamp": datetime.now(timezone.utc).isoformat()}


def get_crypto_prices(tickers: list = None) -> dict:
    if tickers is None:
        tickers = ["BTC", "ETH", "BNB", "SOL", "HYPE"]
    return {t: get_crypto_price(t) for t in tickers}


def _fetch_cnbc_json(ticker: str) -> dict:
    url = f"https://www.cnbc.com/quotes/{ticker}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode("utf-8", errors="ignore")

    # 尝试提取内嵌的完整 JSON
    match = re.search(r'"quoteData"\s*:\s*(\{[^}]+\})', html)
    if match:
        try:
            return json.loads(match.group(1))
        except:
            pass
    # fallback: 逐字段提取
    result = {}
    for field, pattern in [
        ("last", r'"last"\s*:\s*"?([\d,.]+)"?'),
        ("prev_close", r'"previous_day_closing"\s*:\s*"?([\d,.]+)"?'),
        ("change", r'"change"\s*:\s*"?(-?[\d,.]+)"?'),
        ("change_pct", r'"change_pct"\s*:\s*"?(-?[\d.]+)"?'),
        ("issuerName", r'"issuerName"\s*:\s*"([^"]+)"'),
        ("exchangeName", r'"exchangeName"\s*:\s*"([^"]+)"'),
        ("day_low", r'"dayRangeLow"\s*:\s*"?([\d,.]+)"?'),
        ("day_high", r'"dayRangeHigh"\s*:\s*"?([\d,.]+)"?'),
    ]:
        m = re.search(pattern, html)
        if m:
            result[field] = m.group(1)
    return result


def get_us_stock_quote(ticker: str) -> dict:
    data = _fetch_cnbc_json(ticker)
    price = None
    prev_close = None
    if "last" in data:
        price = float(data["last"].replace(",", ""))
    if "prev_close" in data:
        prev_close = float(data["prev_close"].replace(",", ""))
    chg_pct = None
    if price and prev_close and prev_close != 0:
        chg_pct = round((price - prev_close) / prev_close * 100, 2)
    return {
        "ticker": ticker.upper(), "price": price, "change_pct": chg_pct,
        "prev_close": prev_close, "exchange": data.get("exchangeName"),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def get_market_snapshot() -> dict:
    indices = {".SPX": "S&P 500", ".IXIC": "Nasdaq", ".DJI": "Dow Jones", ".SOX": "SOX Semiconductor", ".VIX": "VIX"}
    results = {}
    for ticker, name in indices.items():
        try:
            q = get_us_stock_quote(ticker)
            q["name"] = name
            results[ticker] = q
        except Exception as e:
            results[ticker] = {"error": str(e), "name": name}
    return results


def get_mag7_quote(ticker: str) -> dict:
    ticker = ticker.upper()
    result = get_us_stock_quote(ticker)
    data = _fetch_cnbc_json(ticker)
    if "issuerName" in data:
        result["company_name"] = data["issuerName"]
    if "day_low" in data:
        result["day_low"] = float(data["day_low"].replace(",", ""))
    if "day_high" in data:
        result["day_high"] = float(data["day_high"].replace(",", ""))
    return result


# ============================================================
# 🔥 新功能 1: 历史数据
# ============================================================

def get_crypto_historical(symbol: str, interval: str = "1d", limit: int = 30) -> dict:
    """从 Binance 获取加密历史 K 线"""
    symbol_map = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "BNB": "BNBUSDT", "SOL": "SOLUSDT"}
    binance_symbol = symbol_map.get(symbol.upper())
    if not binance_symbol:
        return {"error": f"不支持 {symbol}，加密历史仅支持: BTC/ETH/BNB/SOL"}

    valid_intervals = {"1d": "1d", "1w": "1w", "4h": "4h", "1h": "1h", "15m": "15m"}
    interval = valid_intervals.get(interval, "1d")

    url = f"https://api.binance.com/api/v3/klines?symbol={binance_symbol}&interval={interval}&limit={limit}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = json.loads(resp.read().decode())

    candles = []
    for k in raw:
        candles.append({
            "time": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).isoformat(),
            "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
            "close": float(k[4]), "volume": float(k[5])
        })

    # 计算简单统计
    closes = [c["close"] for c in candles]
    if len(closes) >= 2:
        change_pct = round((closes[-1] - closes[0]) / closes[0] * 100, 2)
    else:
        change_pct = 0

    return {
        "symbol": symbol.upper(), "interval": interval,
        "candles": candles, "count": len(candles),
        "period_change_pct": change_pct,
        "period_high": max(c["high"] for c in candles),
        "period_low": min(c["low"] for c in candles),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def get_stock_historical(ticker: str, limit: int = 30) -> dict:
    """获取美股历史日线（从 investing.com 抓取）"""
    ticker = ticker.upper()
    # investing.com historical data page
    url = f"https://www.investing.com/indices/us-spx-500-historical-data"

    # 对一些常见的 ticker 映射到 investing.com URL
    investing_map = {
        ".SPX": "us-spx-500",
        ".IXIC": "nasdaq-composite",
        ".DJI": "us-30",
        ".SOX": "phlx-semiconductor",
        ".VIX": "volatility-s-p-500",
        "NVDA": "nvidia-corp",
        "AAPL": "apple-computer-inc",
        "MSFT": "microsoft-corp",
        "GOOGL": "google-inc-c",
        "AMZN": "amazon-com-inc",
        "META": "meta-platforms-inc",
        "TSLA": "tesla-motors",
    }

    slug = investing_map.get(ticker)
    if not slug:
        return {"error": f"历史数据暂不支持 {ticker}，支持: " + ", ".join(investing_map.keys())}

    hist_url = f"https://www.investing.com/equities/{slug}-historical-data"
    req = urllib.request.Request(hist_url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept": "text/html"
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode("utf-8", errors="ignore")

    # 从 HTML 中解析历史数据表格
    candles = []
    rows = re.findall(r'<tr>.*?<td[^>]*>(\w{3}\s+\d{2},\s+\d{4})</td>\s*<td[^>]*>([\d,.]+)</td>\s*<td[^>]*>([\d,.]+)</td>\s*<td[^>]*>([\d,.]+)</td>\s*<td[^>]*>([\d,.]+)</td>', html, re.DOTALL)
    for row in rows[:limit]:
        try:
            dt = datetime.strptime(row[0], "%b %d, %Y")
            candles.append({
                "date": dt.strftime("%Y-%m-%d"),
                "price": float(row[1].replace(",", "")),
                "open": float(row[2].replace(",", "")),
                "high": float(row[3].replace(",", "")),
                "low": float(row[4].replace(",", "")),
            })
        except:
            pass

    if not candles:
        return {"error": f"无法解析 {ticker} 历史数据，Investing.com 格式可能已变更"}

    return {
        "ticker": ticker, "candles": candles, "count": len(candles),
        "latest_price": candles[0]["price"] if candles else None,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============================================================
# 🔥 新功能 2: 简报生成 API
# ============================================================

def _get_sector_etfs() -> dict:
    """获取板块 ETF 数据"""
    etfs = {
        "XLK": "Technology", "XLF": "Financials", "XLE": "Energy",
        "XLV": "Healthcare", "XLY": "Consumer Discretionary",
        "XLI": "Industrials", "XLB": "Materials", "XLU": "Utilities",
        "SMH": "Semiconductor", "GLD": "Gold", "USO": "Oil"
    }
    results = {}
    for ticker, name in etfs.items():
        try:
            q = get_us_stock_quote(ticker)
            q["name"] = name
            results[ticker] = q
        except:
            results[ticker] = {"name": name, "error": "fetch failed"}
    return results


def _get_news_headlines() -> list:
    """从 Google News RSS 获取市场头条"""
    headlines = []
    queries = [
        "US stock market today",
        "Fed Chair Warsh",
        "stock market sector",
    ]
    for q in queries:
        try:
            url = f"https://news.google.com/rss/search?q={urllib.request.quote(q)}&hl=en-US&gl=US&ceid=US:en"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                root = ET.fromstring(resp.read().decode("utf-8", errors="ignore"))
                for item in root.findall(".//item")[:3]:
                    title = item.find("title")
                    if title is not None:
                        headlines.append(html_mod.unescape(title.text or ""))
        except:
            pass
    return headlines[:8]


def generate_briefing() -> dict:
    """生成完整八段式美股复盘简报"""
    now = datetime.now(timezone.utc)
    bj_time = now + timedelta(hours=8)

    # 1. 加密价格
    crypto = get_crypto_prices(["BTC", "ETH", "BNB", "SOL", "HYPE"])

    # 2. 美股指数 + VIX
    market = get_market_snapshot()

    # 3. 板块 ETF
    sectors = _get_sector_etfs()

    # 4. Mag7
    mag7_tickers = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA"]
    mag7 = {}
    for t in mag7_tickers:
        try:
            mag7[t] = get_us_stock_quote(t)
        except:
            mag7[t] = {"error": "fetch failed"}

    # 5. 新闻
    news = _get_news_headlines()

    # 组装八段式简报
    spx = market.get(".SPX", {})
    ndx = market.get(".IXIC", {})
    dji = market.get(".DJI", {})
    sox = market.get(".SOX", {})
    vix = market.get(".VIX", {})

    # 判断市场状态
    spx_chg = spx.get("change_pct") or 0
    vix_val = vix.get("price") or 0
    if spx_chg > 0.5:
        tone = "偏强，三大指数收涨"
    elif spx_chg < -0.5:
        tone = "偏弱，指数承压"
    else:
        tone = "震荡整理，方向不明确"

    briefing = {
        "meta": {
            "generated_at": bj_time.strftime("%Y-%m-%d %H:%M") + " 北京时间",
            "data_as_of": now.strftime("%Y-%m-%d") + " 美东收盘",
            "version": "2.0.0"
        },
        "section_1_macro": {
            "title": "大盘总判断",
            "spx": {"price": spx.get("price"), "change_pct": spx_chg},
            "nasdaq": {"price": ndx.get("price"), "change_pct": ndx.get("change_pct")},
            "dow": {"price": dji.get("price"), "change_pct": dji.get("change_pct")},
            "sox": {"price": sox.get("price"), "change_pct": sox.get("change_pct")},
            "vix": {"price": vix_val},
            "tone": tone,
            "risk_level": "high" if vix_val > 20 else "normal",
            "summary": f"SPX {spx_chg:+.2f}%，纳指 {ndx.get('change_pct') or 0:+.2f}%，VIX {vix_val}。{tone}。"
        },
        "section_2_indices": {
            "title": "指数复盘",
            "indices": {
                "S&P 500": spx, "Nasdaq": ndx, "Dow Jones": dji,
                "SOX Semiconductor": sox, "VIX": vix
            }
        },
        "section_3_sectors": {
            "title": "板块轮动与资金流向",
            "sectors": {t: {"name": d.get("name"), "price": d.get("price"), "change_pct": d.get("change_pct")} for t, d in sectors.items()}
        },
        "section_4_mag7": {
            "title": "Mag 7 核心个股",
            "stocks": mag7
        },
        "section_5_technical": {
            "title": "技术面关键位",
            "spx_support": "待 AI 客户端自行分析",
            "spx_resistance": "待 AI 客户端自行分析",
            "note": "本端点提供原始数据，技术分析由调用方 AI Agent 完成"
        },
        "section_6_forward": {
            "title": "本周前瞻 + 关键事件",
            "events": [
                {"event": "初请失业金", "date": "每周四", "impact": "中"},
                {"event": "PPI 生产者物价", "date": "月度", "impact": "高"},
                {"event": "FOMC", "date": "每六周", "impact": "极高"},
            ],
            "headlines": news
        },
        "section_7_etf": {
            "title": "ETF推荐",
            "note": "ETF 推荐需要结合当日行情判断，建议调用方 AI Agent 基于上方数据自行分析。数据已齐。"
        },
        "section_8_feedback": {
            "title": "昨日前瞻反馈",
            "note": "由调用方 AI Agent 自行比对昨日简报"
        },
        "section_crypto": {
            "title": "加密货币早盘速览",
            "prices": crypto
        }
    }

    return briefing


# ============================================================
# x402 Payment Middleware
# ============================================================

# Payment config — 与 OKX ASP #4234 绑定，x402 v2 格式
X402_PAYMENT_SCHEME = {
    "scheme": "exact",
    "network": "eip155:196",
    "asset": "0x779ded0c9e1022225f8e0630b35a9b54be713736",
    "amount": "1800000",  # 1.8 USDT，最小单位（decimals=6）
    "payTo": "0x92bfb69ee0574f3120d042ba05d8b839749a7907",
    "maxTimeoutSeconds": 300,
    "extra": {"name": "USD₮0", "version": "1"}
}

X402_CONFIG = {
    "x402Version": 2,
    "resource": {
        "url": "https://oceanmarket.zeabur.app/sse",
        "description": "Ocean Market Data Pipeline — crypto prices, US stock indices, Mag7 quotes, historical data, and market briefing",
        "mimeType": "application/json"
    },
    "accepts": [X402_PAYMENT_SCHEME]
}

# 免费路径
X402_FREE_PATHS = {"/", "/health", "/docs"}

# 简单内存计数器（生产环境应换 Redis）
_payment_counter: dict[str, int] = {}

def _check_payment(request) -> bool:
    """检查请求是否携带有效支付凭证 — 简化版，OKX 平台走托管验证"""
    # OKX A2MCP 框架注入的支付头
    sig = request.headers.get("x-payment") or request.headers.get("payment-signature") or ""
    tx = request.headers.get("x-payment-tx") or request.headers.get("payment-tx-hash") or ""
    if sig or tx:
        # 有支付凭证 → 允许通过（完整验证需链上 RPC 查询，MVP 阶段信任 OKX 网关）
        return True
    return False

async def x402_middleware(request, call_next):
    """x402 支付中间件：未支付 → 402，已支付 → 透传"""
    from starlette.responses import Response
    
    path = request.url.path
    if path in X402_FREE_PATHS or path.startswith("/messages/"):
        return await call_next(request)
    
    if not _check_payment(request):
        payment_json = json.dumps(X402_CONFIG)
        payment_b64 = base64.b64encode(payment_json.encode()).decode()
        headers = {
            "payment-required": payment_b64,
            "x-payment-network": X402_PAYMENT_SCHEME["network"],
            "content-type": "application/json",
        }
        body = json.dumps({
            "error": "Payment Required",
            "message": f"This endpoint requires {X402_PAYMENT_SCHEME['payload']['amount']} {X402_PAYMENT_SCHEME['payload']['token']} per call",
            "payment": X402_CONFIG
        })
        return Response(body, status_code=402, headers=headers, media_type="application/json")
    
    return await call_next(request)


class X402ASGIMiddleware:
    """纯 ASGI 中间件 — 兼容 SSE 流式连接"""
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        path = scope["path"]
        if path in X402_FREE_PATHS or path.startswith("/messages/"):
            await self.app(scope, receive, send)
            return
        
        # 从 ASGI scope 提取 headers
        headers = {}
        for k, v in scope.get("headers", []):
            headers[k.decode().lower()] = v.decode()
        
        sig = headers.get("x-payment") or headers.get("payment-signature") or ""
        tx = headers.get("x-payment-tx") or headers.get("payment-tx-hash") or ""
        
        if sig or tx:
            await self.app(scope, receive, send)
            return
        
        # 未支付 → 402
        payment_json = json.dumps(X402_CONFIG)
        payment_b64 = base64.b64encode(payment_json.encode()).decode()
        body = json.dumps({
            "x402Version": 1,
            "accepts": X402_CONFIG["accepts"]
        }).encode()
        
        await send({
            "type": "http.response.start",
            "status": 402,
            "headers": [
                (b"content-type", b"application/json"),
                (b"PAYMENT-REQUIRED", payment_b64.encode()),
                (b"x-payment-network", X402_PAYMENT_SCHEME["network"].encode()),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })


# ============================================================
# MCP Server
# ============================================================

server = Server("ocean-market-data-pipeline")

TOOLS = [
    # 实时行情
    Tool(name="get_crypto_price", description="获取单个加密货币实时价格。支持: BTC, ETH, BNB, SOL, HYPE",
         inputSchema={"type": "object", "properties": {"ticker": {"type": "string", "description": "币种代码"}}, "required": ["ticker"]}),
    Tool(name="get_crypto_prices", description="批量获取加密货币价格。默认返回全部5个",
         inputSchema={"type": "object", "properties": {"tickers": {"type": "array", "items": {"type": "string"}, "description": "可选币种列表"}}}),
    Tool(name="get_market_snapshot", description="美股四大指数快照：标普500、纳斯达克、道琼斯、费城半导体(SOX)、VIX",
         inputSchema={"type": "object", "properties": {}}),
    Tool(name="get_us_stock_quote", description="单只美股/ETF/指数报价",
         inputSchema={"type": "object", "properties": {"ticker": {"type": "string", "description": "代码，如 NVDA, .SPX, SMH"}}, "required": ["ticker"]}),
    Tool(name="get_mag7_quote", description="Mag7个股详细报价，含公司名和日内高低",
         inputSchema={"type": "object", "properties": {"ticker": {"type": "string", "description": "AAPL/MSFT/NVDA/GOOGL/AMZN/META/TSLA"}}, "required": ["ticker"]}),
    # 历史数据
    Tool(name="get_crypto_historical", description="加密货币历史K线数据（日线/周线/4h/1h）。返回OHLCV + 期间统计",
         inputSchema={"type": "object", "properties": {
             "symbol": {"type": "string", "description": "BTC/ETH/BNB/SOL"},
             "interval": {"type": "string", "description": "1d(日线)/1w(周线)/4h/1h/15m，默认1d"},
             "limit": {"type": "integer", "description": "K线数量，默认30，最大500"}
         }, "required": ["symbol"]}),
    Tool(name="get_stock_historical", description="美股历史日线数据（从Investing.com）。支持指数和Mag7个股",
         inputSchema={"type": "object", "properties": {
             "ticker": {"type": "string", "description": ".SPX/.IXIC/.DJI/.SOX/.VIX 或 NVDA/AAPL/MSFT 等"},
             "limit": {"type": "integer", "description": "数据条数，默认30"}
         }, "required": ["ticker"]}),
    # 简报生成
    Tool(name="generate_briefing", description="一键生成完整八段式美股复盘简报。聚合加密价格+美股指数+板块ETF+Mag7+新闻头条。返回结构化JSON，AI Agent可直接解析",
         inputSchema={"type": "object", "properties": {}}),
]


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "get_crypto_price":
            result = get_crypto_price(arguments["ticker"])
        elif name == "get_crypto_prices":
            result = get_crypto_prices(arguments.get("tickers"))
        elif name == "get_market_snapshot":
            result = get_market_snapshot()
        elif name == "get_us_stock_quote":
            result = get_us_stock_quote(arguments["ticker"])
        elif name == "get_mag7_quote":
            result = get_mag7_quote(arguments["ticker"])
        elif name == "get_crypto_historical":
            result = get_crypto_historical(arguments["symbol"], arguments.get("interval", "1d"), int(arguments.get("limit", 30)))
        elif name == "get_stock_historical":
            result = get_stock_historical(arguments["ticker"], int(arguments.get("limit", 30)))
        elif name == "generate_briefing":
            result = generate_briefing()
        else:
            result = {"error": f"Unknown tool: {name}"}
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]


def run_sse(port: int = 9000, host: str = "0.0.0.0"):
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    from starlette.responses import JSONResponse, HTMLResponse
    import uvicorn

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    async def health(request):
        return JSONResponse({
            "status": "ok", "service": "Ocean Market Data Pipeline",
            "version": "2.0.0", "tools": [t.name for t in TOOLS],
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    async def docs(request):
        html = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Ocean Market Data Pipeline</title>
<style>body{font-family:system-ui;max-width:800px;margin:50px auto;padding:20px;background:#0a0e21;color:#e0e0e0}
h1{color:#00d4aa} h2{color:#7ec8e3} code{background:#1a1f35;padding:2px 6px;border-radius:4px}
table{border-collapse:collapse;width:100%} th,td{border:1px solid #2a2f45;padding:8px;text-align:left}
th{background:#1a1f35} a{color:#00d4aa}</style></head><body>
<h1>Ocean Market Data Pipeline</h1><p><em>Wall Street, accessible to any AI Agent.</em></p>
<p>SSE Endpoint: <code>/sse</code> | Health: <code>/health</code> | Docs: <code>/docs</code></p>
<h2>Pricing</h2><table><tr><th>Plan</th><th>Price</th><th>Rate Limit</th></tr>
<tr><td>Standard</td><td>1.8 USDT / call</td><td>60 calls/min</td></tr>
<tr><td>Pro (coming soon)</td><td>50 USDT / month</td><td>600 calls/min</td></tr></table>
<h2>Tools</h2><table><tr><th>Tool</th><th>Description</th></tr>
""" + "".join(f"<tr><td><code>{t.name}</code></td><td>{t.description}</td></tr>" for t in TOOLS) + """
</table><h2>Quick Start</h2>
<p>Connect any MCP-compatible client to: <code>https://YOUR-HOST/sse</code></p>
<p>GitHub: <a href="https://github.com/0xOcean/market-data-pipeline">github.com/0xOcean/market-data-pipeline</a></p>
</body></html>"""
        return HTMLResponse(html)

    app = Starlette(routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
        Route("/health", endpoint=health),
        Route("/docs", endpoint=docs),
    ])
    
    # x402 支付中间件（纯 ASGI，直接包裹）
    app = X402ASGIMiddleware(app)
    
    print(f"🌊 Ocean Market Data Pipeline v2.0.0")
    print(f"   SSE:   http://{host}:{port}/sse")
    print(f"   Docs:  http://{host}:{port}/docs")
    print(f"   Tools: {len(TOOLS)}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import os
    parser = argparse.ArgumentParser(description="Ocean Market Data Pipeline")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "9000")))
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args = parser.parse_args()
    run_sse(port=args.port, host=args.host)
