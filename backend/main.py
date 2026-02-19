"""
N50 Swing Algo — Backend API
Uses yfinance to fetch NSE prices (Yahoo Finance, ~15min delayed, free, no auth needed)
"""

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import asyncio
import logging
from typing import Optional
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="N50 Swing Algo API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # allows all Render subdomains + local dev
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ─── NIFTY 50 SYMBOLS ────────────────────────────────────────────────────────
# Yahoo Finance uses .NS suffix for NSE stocks
NIFTY50_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK",
    "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "WIPRO",
    "SUNPHARMA", "TITAN", "BAJFINANCE", "POWERGRID", "NTPC",
    "TATASTEEL", "JSWSTEEL", "ADANIPORTS", "HCLTECH", "ULTRACEMCO",
    "NESTLEIND", "TATAMOTORS", "M&M", "ONGC", "COALINDIA",
    "BPCL", "GRASIM", "TECHM", "INDUSINDBK", "EICHERMOT",
    "DRREDDY", "CIPLA", "DIVISLAB", "BAJAJFINSV", "TATACONSUM",
    "APOLLOHOSP", "BRITANNIA", "HEROMOTOCO", "HINDALCO", "SBILIFE",
    "HDFCLIFE", "UPL", "SHRIRAMFIN", "BEL", "TRENT",
]

SECTOR_MAP = {
    "RELIANCE": "Energy", "TCS": "IT", "HDFCBANK": "Banking", "INFY": "IT",
    "ICICIBANK": "Banking", "HINDUNILVR": "FMCG", "SBIN": "Banking",
    "BHARTIARTL": "Telecom", "ITC": "FMCG", "KOTAKBANK": "Banking",
    "LT": "Infra", "AXISBANK": "Banking", "ASIANPAINT": "Paints",
    "MARUTI": "Auto", "WIPRO": "IT", "SUNPHARMA": "Pharma",
    "TITAN": "Consumer", "BAJFINANCE": "NBFC", "POWERGRID": "Power",
    "NTPC": "Power", "TATASTEEL": "Metal", "JSWSTEEL": "Metal",
    "ADANIPORTS": "Port", "HCLTECH": "IT", "ULTRACEMCO": "Cement",
    "NESTLEIND": "FMCG", "TATAMOTORS": "Auto", "M&M": "Auto",
    "ONGC": "Energy", "COALINDIA": "Mining", "BPCL": "Energy",
    "GRASIM": "Conglomerate", "TECHM": "IT", "INDUSINDBK": "Banking",
    "EICHERMOT": "Auto", "DRREDDY": "Pharma", "CIPLA": "Pharma",
    "DIVISLAB": "Pharma", "BAJAJFINSV": "NBFC", "TATACONSUM": "FMCG",
    "APOLLOHOSP": "Healthcare", "BRITANNIA": "FMCG", "HEROMOTOCO": "Auto",
    "HINDALCO": "Metal", "SBILIFE": "Insurance", "HDFCLIFE": "Insurance",
    "UPL": "Agro", "SHRIRAMFIN": "NBFC", "BEL": "Defence", "TRENT": "Retail",
}

# ─── CACHE ────────────────────────────────────────────────────────────────────
_cache: dict = {}
_cache_ts: float = 0
CACHE_TTL = 60  # seconds — refresh every 60s (yfinance is delayed anyway)

# ─── TECHNICAL INDICATORS ────────────────────────────────────────────────────
def calc_rsi(series: pd.Series, period: int = 14) -> float:
    if len(series) < period + 1:
        return 50.0
    delta = series.diff().dropna()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.rolling(period).mean().iloc[-1]
    avg_loss = losses.rolling(period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calc_macd(series: pd.Series):
    if len(series) < 26:
        return {"macd": 0, "signal": 0, "hist": 0}
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal_line
    return {
        "macd": round(float(macd_line.iloc[-1]), 2),
        "signal": round(float(signal_line.iloc[-1]), 2),
        "hist": round(float(hist.iloc[-1]), 2),
    }

def calc_bollinger(series: pd.Series, period: int = 20):
    if len(series) < period:
        p = float(series.iloc[-1])
        return {"upper": p, "lower": p, "mid": p, "width": 0}
    sma = series.rolling(period).mean().iloc[-1]
    std = series.rolling(period).std().iloc[-1]
    upper = sma + 2 * std
    lower = sma - 2 * std
    width = round(float((std * 4 / sma) * 100), 2) if sma else 0
    return {
        "upper": round(float(upper), 2),
        "lower": round(float(lower), 2),
        "mid": round(float(sma), 2),
        "width": width,
    }

def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    if len(close) < period + 1:
        return 0
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return round(float(tr.rolling(period).mean().iloc[-1]), 2)

def round_to_strike(price: float) -> int:
    if price > 5000:
        return round(price / 100) * 100
    elif price > 1000:
        return round(price / 50) * 50
    elif price > 500:
        return round(price / 20) * 20
    else:
        return round(price / 10) * 10

def get_next_expiry() -> str:
    today = datetime.now()
    days_until_thursday = (3 - today.weekday() + 7) % 7
    if days_until_thursday == 0:
        days_until_thursday = 7
    expiry = today + timedelta(days=days_until_thursday)
    return expiry.strftime("%d %b '%y")

def generate_signal(sym: str, prices: list, highs: list, lows: list) -> dict:
    if len(prices) < 10:
        return None

    s = pd.Series(prices)
    h = pd.Series(highs)
    l = pd.Series(lows)

    price = prices[-1]
    rsi = calc_rsi(s)
    macd = calc_macd(s)
    bb = calc_bollinger(s)
    atr = calc_atr(h, l, s)

    ema9 = round(float(s.ewm(span=9, adjust=False).mean().iloc[-1]), 2)
    ema21 = round(float(s.ewm(span=21, adjust=False).mean().iloc[-1]), 2)
    sma20 = round(float(s.rolling(20).mean().iloc[-1]), 2) if len(prices) >= 20 else price

    change = round((price - prices[-2]) / prices[-2] * 100, 2) if len(prices) > 1 else 0
    change5d = round((price - prices[-6]) / prices[-6] * 100, 2) if len(prices) > 5 else 0

    score = 0
    reasons = []

    # RSI
    if rsi < 35:
        score += 2; reasons.append("RSI oversold")
    elif rsi > 65:
        score -= 2; reasons.append("RSI overbought")
    elif rsi < 50:
        score += 0.5
    else:
        score -= 0.5

    # MACD
    if macd["hist"] > 0:
        score += 1.5; reasons.append("MACD bullish crossover")
    else:
        score -= 1.5; reasons.append("MACD bearish crossover")

    # EMA
    if ema9 > ema21:
        score += 1; reasons.append("9EMA above 21EMA — bullish")
    else:
        score -= 1; reasons.append("9EMA below 21EMA — bearish")

    # BB position
    bb_range = bb["upper"] - bb["lower"]
    bb_pos = (price - bb["lower"]) / bb_range if bb_range > 0 else 0.5
    if bb_pos < 0.2:
        score += 1.5; reasons.append("Price near BB lower band")
    elif bb_pos > 0.8:
        score -= 1.5; reasons.append("Price near BB upper band")

    # SMA
    if price > sma20 * 1.02:
        score += 0.5
    elif price < sma20 * 0.98:
        score -= 0.5

    direction = "LONG" if score >= 1 else "SHORT" if score <= -1 else "NEUTRAL"
    confidence = min(99, round(abs(score) / 6 * 100))

    strike = round_to_strike(price)
    expiry = get_next_expiry()

    if direction == "LONG":
        if confidence > 70:
            option_strategy = "Bull Call Spread"
            option_details = {
                "buy": f"{sym} {strike} CE",
                "sell": f"{sym} {round_to_strike(price * 1.03)} CE",
                "expiry": expiry,
                "maxProfit": f"₹{round(atr * 3)}",
                "maxLoss": f"₹{round(atr * 1.5)}",
                "premium": f"₹{round(atr * 1.2)}",
            }
        else:
            option_strategy = "ATM Call Buy"
            option_details = {
                "buy": f"{sym} {strike} CE",
                "expiry": expiry,
                "target": f"₹{round(price * 1.04, 2)}",
                "stopLoss": f"₹{round(price * 0.985, 2)}",
                "premium": f"₹{round(atr * 0.8)}",
            }
    elif direction == "SHORT":
        if confidence > 70:
            option_strategy = "Bear Put Spread"
            option_details = {
                "buy": f"{sym} {strike} PE",
                "sell": f"{sym} {round_to_strike(price * 0.97)} PE",
                "expiry": expiry,
                "maxProfit": f"₹{round(atr * 3)}",
                "maxLoss": f"₹{round(atr * 1.5)}",
                "premium": f"₹{round(atr * 1.2)}",
            }
        else:
            option_strategy = "ATM Put Buy"
            option_details = {
                "buy": f"{sym} {strike} PE",
                "expiry": expiry,
                "target": f"₹{round(price * 0.96, 2)}",
                "stopLoss": f"₹{round(price * 1.015, 2)}",
                "premium": f"₹{round(atr * 0.8)}",
            }
    else:
        option_strategy = "Iron Condor"
        option_details = {
            "sellCall": f"{sym} {round_to_strike(price * 1.025)} CE",
            "buyCall": f"{sym} {round_to_strike(price * 1.04)} CE",
            "sellPut": f"{sym} {round_to_strike(price * 0.975)} PE",
            "buyPut": f"{sym} {round_to_strike(price * 0.96)} PE",
            "expiry": expiry,
            "premium": f"₹{round(atr * 0.6)}",
        }

    return {
        "sym": sym,
        "sector": SECTOR_MAP.get(sym, "Misc"),
        "price": round(price, 2),
        "change": change,
        "change5d": change5d,
        "rsi": rsi,
        "macd": macd,
        "bb": bb,
        "bbPos": round(bb_pos, 2),
        "sma20": sma20,
        "ema9": ema9,
        "ema21": ema21,
        "atr": atr,
        "score": round(score, 2),
        "direction": direction,
        "confidence": confidence,
        "reasons": reasons[:3],
        "optionStrategy": option_strategy,
        "optionDetails": option_details,
        "priceHistory": [round(p, 2) for p in prices[-60:]],
        "lastUpdated": datetime.now().isoformat(),
    }


# ─── DATA FETCHER ─────────────────────────────────────────────────────────────
def fetch_all_stocks() -> list:
    """Fetch 60-day daily OHLCV for all Nifty 50 from Yahoo Finance."""
    logger.info("Fetching data from Yahoo Finance...")
    tickers = [f"{s}.NS" for s in NIFTY50_SYMBOLS]

    try:
        # Batch download — much faster than individual calls
        raw = yf.download(
            tickers=tickers,
            period="3mo",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )

        results = []
        for sym in NIFTY50_SYMBOLS:
            ticker = f"{sym}.NS"
            try:
                if len(tickers) == 1:
                    df = raw
                else:
                    df = raw[ticker] if ticker in raw.columns.get_level_values(0) else None

                if df is None or df.empty:
                    logger.warning(f"No data for {sym}")
                    continue

                df = df.dropna()
                if len(df) < 10:
                    continue

                prices = df["Close"].tolist()
                highs = df["High"].tolist()
                lows = df["Low"].tolist()

                signal = generate_signal(sym, prices, highs, lows)
                if signal:
                    results.append(signal)

            except Exception as e:
                logger.error(f"Error processing {sym}: {e}")
                continue

        logger.info(f"Fetched {len(results)} stocks successfully")
        return results

    except Exception as e:
        logger.error(f"Batch download failed: {e}")
        return []


def get_nifty_index() -> dict:
    """Fetch Nifty 50 index value."""
    try:
        nifty = yf.Ticker("^NSEI")
        hist = nifty.history(period="5d", interval="1d")
        if hist.empty:
            return {"price": 22450.0, "change": 0.0, "changePct": 0.0}
        price = round(float(hist["Close"].iloc[-1]), 2)
        prev = round(float(hist["Close"].iloc[-2]), 2) if len(hist) > 1 else price
        change = round(price - prev, 2)
        change_pct = round((change / prev) * 100, 2)
        return {"price": price, "change": change, "changePct": change_pct}
    except Exception as e:
        logger.error(f"Nifty index fetch error: {e}")
        return {"price": 22450.0, "change": 0.0, "changePct": 0.0}


# ─── ROUTES ───────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "message": "N50 Swing Algo API", "version": "1.0.0"}


@app.get("/api/stocks")
def get_stocks():
    global _cache, _cache_ts
    now = time.time()

    if _cache and (now - _cache_ts) < CACHE_TTL:
        logger.info("Returning cached data")
        return JSONResponse(content=_cache)

    stocks = fetch_all_stocks()
    nifty = get_nifty_index()

    if not stocks:
        # Return cached stale data if available, else error
        if _cache:
            return JSONResponse(content=_cache)
        return JSONResponse(status_code=503, content={"error": "Data unavailable"})

    longs = sum(1 for s in stocks if s["direction"] == "LONG")
    shorts = sum(1 for s in stocks if s["direction"] == "SHORT")
    neutrals = sum(1 for s in stocks if s["direction"] == "NEUTRAL")

    response = {
        "stocks": stocks,
        "nifty": nifty,
        "summary": {"longs": longs, "shorts": shorts, "neutrals": neutrals, "total": len(stocks)},
        "fetchedAt": datetime.now().isoformat(),
        "nextRefresh": CACHE_TTL,
        "dataSource": "Yahoo Finance (NSE ~15min delayed)",
    }

    _cache = response
    _cache_ts = now
    return JSONResponse(content=response)


@app.get("/api/stock/{symbol}")
def get_single_stock(symbol: str):
    global _cache
    if _cache and "stocks" in _cache:
        match = next((s for s in _cache["stocks"] if s["sym"] == symbol.upper()), None)
        if match:
            return JSONResponse(content=match)

    # Fetch individually
    ticker = f"{symbol.upper()}.NS"
    try:
        df = yf.download(ticker, period="3mo", interval="1d", auto_adjust=True, progress=False)
        df = df.dropna()
        if df.empty:
            return JSONResponse(status_code=404, content={"error": f"No data for {symbol}"})
        prices = df["Close"].tolist()
        highs = df["High"].tolist()
        lows = df["Low"].tolist()
        signal = generate_signal(symbol.upper(), prices, highs, lows)
        return JSONResponse(content=signal)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "cacheAge": round(time.time() - _cache_ts) if _cache_ts else None,
        "stocksCached": len(_cache.get("stocks", [])) if _cache else 0,
    }
