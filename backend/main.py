"""
N50 Swing Algo — Backend API
Fetches NSE prices via Yahoo Finance (free, ~15min delayed)
Batched fetching + startup pre-cache to avoid Render 30s timeout
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import yfinance as yf
import pandas as pd
import threading
import logging
import time
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="N50 Swing Algo API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ─── NIFTY 50 SYMBOLS ────────────────────────────────────────────────────────
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

# ─── CACHE ───────────────────────────────────────────────────────────────────
_cache: dict = {}
_cache_ts: float = 0
_fetching: bool = False
CACHE_TTL = 120  # seconds

# ─── TECHNICAL INDICATORS ────────────────────────────────────────────────────
def calc_rsi(series: pd.Series, period: int = 14) -> float:
    if len(series) < period + 1:
        return 50.0
    delta = series.diff().dropna()
    gains = delta.clip(lower=0).rolling(period).mean().iloc[-1]
    losses = (-delta.clip(upper=0)).rolling(period).mean().iloc[-1]
    if losses == 0:
        return 100.0
    return round(100 - (100 / (1 + gains / losses)), 2)

def calc_macd(series: pd.Series) -> dict:
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

def calc_bb(series: pd.Series, period: int = 20) -> dict:
    if len(series) < period:
        p = float(series.iloc[-1])
        return {"upper": p, "lower": p, "mid": p, "width": 0}
    sma = series.rolling(period).mean().iloc[-1]
    std = series.rolling(period).std().iloc[-1]
    return {
        "upper": round(float(sma + 2 * std), 2),
        "lower": round(float(sma - 2 * std), 2),
        "mid": round(float(sma), 2),
        "width": round(float((std * 4 / sma) * 100), 2) if sma else 0,
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
    if price > 5000: return round(price / 100) * 100
    if price > 1000: return round(price / 50) * 50
    if price > 500:  return round(price / 20) * 20
    return round(price / 10) * 10

def get_next_expiry() -> str:
    today = datetime.now()
    days = (3 - today.weekday() + 7) % 7 or 7
    return (today + timedelta(days=days)).strftime("%d %b '%y")

def generate_signal(sym: str, prices: list, highs: list, lows: list) -> dict:
    if len(prices) < 10:
        return None
    s = pd.Series(prices)
    price = prices[-1]
    rsi = calc_rsi(s)
    macd = calc_macd(s)
    bb = calc_bb(s)
    atr = calc_atr(pd.Series(highs), pd.Series(lows), s)
    ema9  = round(float(s.ewm(span=9,  adjust=False).mean().iloc[-1]), 2)
    ema21 = round(float(s.ewm(span=21, adjust=False).mean().iloc[-1]), 2)
    sma20 = round(float(s.rolling(20).mean().iloc[-1]), 2) if len(prices) >= 20 else price
    change   = round((price - prices[-2]) / prices[-2] * 100, 2) if len(prices) > 1 else 0
    change5d = round((price - prices[-6]) / prices[-6] * 100, 2) if len(prices) > 5 else 0

    score = 0
    reasons = []
    if rsi < 35:   score += 2;   reasons.append("RSI oversold")
    elif rsi > 65: score -= 2;   reasons.append("RSI overbought")
    elif rsi < 50: score += 0.5
    else:          score -= 0.5

    if macd["hist"] > 0: score += 1.5; reasons.append("MACD bullish crossover")
    else:                score -= 1.5; reasons.append("MACD bearish crossover")

    if ema9 > ema21: score += 1; reasons.append("9EMA above 21EMA")
    else:            score -= 1; reasons.append("9EMA below 21EMA")

    bb_range = bb["upper"] - bb["lower"]
    bb_pos = (price - bb["lower"]) / bb_range if bb_range > 0 else 0.5
    if bb_pos < 0.2:   score += 1.5; reasons.append("Price near BB lower band")
    elif bb_pos > 0.8: score -= 1.5; reasons.append("Price near BB upper band")

    if price > sma20 * 1.02: score += 0.5
    elif price < sma20 * 0.98: score -= 0.5

    direction  = "LONG" if score >= 1 else "SHORT" if score <= -1 else "NEUTRAL"
    confidence = min(99, round(abs(score) / 6 * 100))
    strike = round_to_strike(price)
    expiry = get_next_expiry()

    if direction == "LONG":
        if confidence > 70:
            strategy = "Bull Call Spread"
            details  = {"buy": f"{sym} {strike} CE", "sell": f"{sym} {round_to_strike(price*1.03)} CE",
                        "expiry": expiry, "maxProfit": f"₹{round(atr*3)}", "maxLoss": f"₹{round(atr*1.5)}", "premium": f"₹{round(atr*1.2)}"}
        else:
            strategy = "ATM Call Buy"
            details  = {"buy": f"{sym} {strike} CE", "expiry": expiry,
                        "target": f"₹{round(price*1.04,2)}", "stopLoss": f"₹{round(price*0.985,2)}", "premium": f"₹{round(atr*0.8)}"}
    elif direction == "SHORT":
        if confidence > 70:
            strategy = "Bear Put Spread"
            details  = {"buy": f"{sym} {strike} PE", "sell": f"{sym} {round_to_strike(price*0.97)} PE",
                        "expiry": expiry, "maxProfit": f"₹{round(atr*3)}", "maxLoss": f"₹{round(atr*1.5)}", "premium": f"₹{round(atr*1.2)}"}
        else:
            strategy = "ATM Put Buy"
            details  = {"buy": f"{sym} {strike} PE", "expiry": expiry,
                        "target": f"₹{round(price*0.96,2)}", "stopLoss": f"₹{round(price*1.015,2)}", "premium": f"₹{round(atr*0.8)}"}
    else:
        strategy = "Iron Condor"
        details  = {"sellCall": f"{sym} {round_to_strike(price*1.025)} CE", "buyCall": f"{sym} {round_to_strike(price*1.04)} CE",
                    "sellPut": f"{sym} {round_to_strike(price*0.975)} PE", "buyPut": f"{sym} {round_to_strike(price*0.96)} PE",
                    "expiry": expiry, "premium": f"₹{round(atr*0.6)}"}

    return {
        "sym": sym, "sector": SECTOR_MAP.get(sym, "Misc"),
        "price": round(price, 2), "change": change, "change5d": change5d,
        "rsi": rsi, "macd": macd, "bb": bb, "bbPos": round(bb_pos, 2),
        "sma20": sma20, "ema9": ema9, "ema21": ema21, "atr": atr,
        "score": round(score, 2), "direction": direction, "confidence": confidence,
        "reasons": reasons[:3], "optionStrategy": strategy, "optionDetails": details,
        "priceHistory": [round(p, 2) for p in prices[-60:]],
        "lastUpdated": datetime.now().isoformat(),
    }

# ─── FETCHER (batched to beat 30s timeout) ───────────────────────────────────
def do_fetch():
    global _cache, _cache_ts, _fetching
    if _fetching:
        return
    _fetching = True
    logger.info("Starting batched Yahoo Finance fetch...")
    results = []
    batches = [NIFTY50_SYMBOLS[i:i+10] for i in range(0, len(NIFTY50_SYMBOLS), 10)]

    for batch in batches:
        tickers = [f"{s}.NS" for s in batch]
        try:
            raw = yf.download(
                tickers=tickers, period="1mo", interval="1d",
                group_by="ticker", auto_adjust=True, progress=False, threads=True,
            )
            for sym, ticker in zip(batch, tickers):
                try:
                    df = raw[ticker] if len(tickers) > 1 else raw
                    df = df.dropna()
                    if len(df) < 10:
                        continue
                    sig = generate_signal(sym, df["Close"].tolist(), df["High"].tolist(), df["Low"].tolist())
                    if sig:
                        results.append(sig)
                except Exception as e:
                    logger.warning(f"Skip {sym}: {e}")
        except Exception as e:
            logger.error(f"Batch error: {e}")

    if results:
        longs    = sum(1 for s in results if s["direction"] == "LONG")
        shorts   = sum(1 for s in results if s["direction"] == "SHORT")
        neutrals = sum(1 for s in results if s["direction"] == "NEUTRAL")
        _cache = {
            "stocks": results,
            "nifty": get_nifty_index(),
            "summary": {"longs": longs, "shorts": shorts, "neutrals": neutrals, "total": len(results)},
            "fetchedAt": datetime.now().isoformat(),
            "nextRefresh": CACHE_TTL,
            "dataSource": "Yahoo Finance (NSE ~15min delayed)",
        }
        _cache_ts = time.time()
        logger.info(f"Cache updated: {len(results)} stocks")
    _fetching = False


def get_nifty_index() -> dict:
    try:
        hist = yf.Ticker("^NSEI").history(period="5d", interval="1d")
        if hist.empty:
            return {"price": 22450.0, "change": 0.0, "changePct": 0.0}
        price = round(float(hist["Close"].iloc[-1]), 2)
        prev  = round(float(hist["Close"].iloc[-2]), 2) if len(hist) > 1 else price
        change = round(price - prev, 2)
        return {"price": price, "change": change, "changePct": round(change / prev * 100, 2)}
    except Exception as e:
        logger.error(f"Nifty index error: {e}")
        return {"price": 22450.0, "change": 0.0, "changePct": 0.0}


# ─── STARTUP: pre-fetch in background so first request is instant ─────────────
@app.on_event("startup")
async def startup():
    threading.Thread(target=do_fetch, daemon=True).start()
    logger.info("Background pre-fetch triggered on startup")


# ─── ROUTES ──────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "message": "N50 Swing Algo API"}

@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "cacheAge": round(time.time() - _cache_ts) if _cache_ts else None,
        "stocksCached": len(_cache.get("stocks", [])) if _cache else 0,
        "fetching": _fetching,
    }

@app.get("/api/stocks")
def get_stocks():
    global _cache, _cache_ts

    # If cache is fresh, return it immediately
    if _cache and (time.time() - _cache_ts) < CACHE_TTL:
        return JSONResponse(content=_cache)

    # If currently fetching, return stale cache or wait message
    if _fetching:
        if _cache:
            return JSONResponse(content=_cache)
        return JSONResponse(status_code=503, content={
            "error": "Data is loading, please retry in 30 seconds",
            "fetching": True
        })

    # Trigger background fetch and return stale/empty
    threading.Thread(target=do_fetch, daemon=True).start()

    if _cache:
        return JSONResponse(content=_cache)

    return JSONResponse(status_code=503, content={
        "error": "Fetching data for the first time, please retry in 30 seconds",
        "fetching": True
    })
