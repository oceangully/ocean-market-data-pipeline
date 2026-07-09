# Ocean Market Data Pipeline

**Wall Street, accessible to any AI Agent.**

An MCP (Model Context Protocol) server providing real-time and historical financial data for AI agents. Crypto prices, US stock indices, Mag7 quotes, sector ETFs, technical snapshots, and automated daily briefings — all through a single endpoint.

---

## Quick Start

Connect any MCP-compatible client (Claude Desktop, Hermes, Cursor, etc.) to:

```
https://YOUR-HOST/sse
```

No API key required. No sign-up. Just point and call.

---

## Tools

| # | Tool | Description |
|---|------|-------------|
| 1 | `get_crypto_price` | Real-time crypto price (BTC/ETH/BNB/SOL/HYPE) |
| 2 | `get_crypto_prices` | Batch crypto prices (all 5 by default) |
| 3 | `get_market_snapshot` | US market indices: S&P 500, Nasdaq, Dow, SOX, VIX |
| 4 | `get_us_stock_quote` | Single stock/ETF/index quote (e.g. NVDA, .SPX, SMH) |
| 5 | `get_mag7_quote` | Detailed Mag7 quote with company name + day range |
| 6 | `get_crypto_historical` | OHLCV candles (1d/1w/4h/1h/15m) with period stats |
| 7 | `get_stock_historical` | US stock daily history (indices + Mag7) |
| 8 | `generate_briefing` | One-call 8-section daily briefing (crypto + US stocks + news) |

---

## Pricing

| Plan | Price | Rate Limit |
|------|-------|------------|
| **Standard** | **1.8 USDT / call** | 60 calls/min |
| Pro (coming soon) | 50 USDT / month | 600 calls/min |

All prices settled instantly via OKX Payment SDK (x402 standard).

---

## Deployment

### Local

```bash
pip install mcp uvicorn starlette
python3 server.py --port 9000
```

### Public (Cloudflare Tunnel)

```bash
# Terminal 1: Start server
python3 server.py --port 9000

# Terminal 2: Expose via Cloudflare Tunnel
cloudflared tunnel --url http://localhost:9000
# → https://xxxxx.trycloudflare.com
```

### Docker (coming soon)

```bash
docker run -p 9000:9000 ghcr.io/0xocean/market-data-pipeline
```

---

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────┐
│   AI Agent      │────▶│  MCP SSE / HTTPS │────▶│  Data Sources │
│  (Claude/Hermes)│     │  (FastMCP+Starlette)│   │  Binance/CNBC │
└─────────────────┘     └──────────────────┘     └──────────────┘
         │                        │
         ▼                        ▼
   Natural language       Structured JSON
   "what's BTC?"          {"price": 62300, ...}
```

---

## Example: AI Agent Calling `generate_briefing`

```
User: "Give me today's US market recap"

Agent → calls generate_briefing()
Agent ← receives:
{
  "section_1_macro": {...},
  "section_2_indices": {...},
  "section_3_sectors": {...},
  "section_4_mag7": {...},
  "section_crypto": {...},
  "section_6_forward": {"headlines": [...]}
}

Agent → "Here's today's market recap: SPX closed at..."
```

---

## Roadmap

- [x] Crypto real-time prices (5 assets)
- [x] US stock indices + VIX
- [x] Mag7 detailed quotes
- [x] Crypto historical OHLCV (Binance)
- [x] Automated daily briefing
- [ ] Stock historical from reliable source
- [ ] WebSocket streaming prices
- [ ] Technical indicators (RSI, MACD, MA)
- [ ] Chan Theory tools (chan_bi, chan_zhongshu)

---

## License

MIT © 2026 Ocean Market Data Pipeline

---

*Built for the OKX.AI Agent Marketplace. Part of ASP #4234 — Codex Evidence Lab.*
