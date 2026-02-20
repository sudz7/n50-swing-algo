"""
N50 Swing Algo — Backend API v5
Data: nsepython library (official NSE data, works from cloud servers)
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import pandas as pd
import threading
import logging
import time
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── NIFTY 50 ─────────────────────────────────────────────────────────────────
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
    "RELIANCE": "Energy",    "TCS": "IT",             "HDFCBANK": "Banking",
    "INFY": "IT",            "ICICIBANK": "Banking",  "HINDUNILVR": "FMCG",
    "SBIN": "Banking",       "BHARTIARTL": "Telecom", "ITC": "FMCG",
    "KOTAKBANK": "Banking",  "LT": "Infra",           "AXISBANK": "Banking",
    "ASIANPAINT": "Paints",  "MARUTI": "Auto",        "WIPRO": "IT",
    "SUNPHARMA": "Pharma",   "TITAN": "Consumer",     "BAJFINANCE": "NBFC",
    "POWERGRID": "Power",    "NTPC": "Power",          "TATASTEEL": "Metal",
    "JSWSTEEL": "Metal",     "ADANIPORTS": "Port",    "HCLTECH": "IT",
    "ULTRACEMCO": "Cement",  "NESTLEIND": "FMCG",     "TATAMOTORS": "Auto",
    "M&M": "Auto",           "ONGC": "Energy",         "COALINDIA": "Mining",
    "BPCL": "Energy",        "GRASIM": "Conglomerate", "TECHM": "IT",
    "INDUSINDBK": "Banking", "EICHERMOT": "Auto",     "DRREDDY": "Pharma",
    "CIPLA": "Pharma",       "DIVISLAB": "Pharma",    "BAJAJFINSV": "NBFC",
    "TATACONSUM": "FMCG",    "APOLLOHOSP": "Healthcare","BRITANNIA": "FMCG",
    "HEROMOTOCO": "Auto",    "HINDALCO": "Metal",     "SBILIFE": "Insurance",
    "HDFCLIFE": "Insurance", "UPL": "Agro",           "SHRIRAMFIN": "NBFC",
    "BEL": "Defence",        "TRENT": "Retail",
}

# ─── CACHE ────────────────────────────────────────────────────────────────────
_cache: dict = {}
_cache_ts: float = 0
_fetching: bool = False
CACHE_TTL = 3600  # 1 hour

# ─── DATA FETCHER (nsepython) ─────────────────────────────────────────────────
def fetch_stock(symbol: str) -> pd.DataFrame:
    from nsepython import equity_history
    end   = datetime.now().strftime("%d-%m-%Y")
    start = (datetime.now() - timedelta(days=90)).strftime("%d-%m-%Y")

    # equity_history returns a DataFrame directly
    df = equity_history(symbol, "EQ", start, end)

    if df is None or df.empty:
        raise ValueError(f"Empty data for {symbol}")

    # Normalise column names to lowercase
    df.columns = [c.strip().lower() for c in df.columns]

    # Map NSE column names → standard names
    col_map = {
        "ch_timestamp":        "date",
        "ch_opening_price":    "open",
        "ch_trade_high_price": "high",
        "ch_trade_low_price":  "low",
        "ch_closing_price":    "close",
    }
    df = df.rename(columns=col_map)

    # Keep only what we need
    needed = [c for c in ["date", "open", "high", "low", "close"] if c in df.columns]
    df = df[needed]

    df["date"]  = pd.to_datetime(df["date"], errors="coerce")
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["close"]).sort_values("date").tail(60).reset_index(drop=True)
    return df


def fetch_nifty() -> dict:
    try:
        from nsepython import nsefetch
        data = nsefetch("https://www.nseindia.com/api/allIndices")
        for idx in data.get("data", []):
            if idx.get("index") == "NIFTY 50":
                return {
                    "price":     round(float(idx["last"]), 2),
                    "change":    round(float(idx["change"]), 2),
                    "changePct": round(float(idx["percentChange"]), 2),
                }
        logger.warning("NIFTY 50 not found in allIndices response")
    except Exception as e:
        logger.error(f"Nifty index error: {e}")
    return {"price": 22450.0, "change": 0.0, "changePct": 0.0}

# ─── INDICATORS ───────────────────────────────────────────────────────────────
def calc_rsi(s: pd.Series, p: int = 14) -> float:
    if len(s) < p + 1:
        return 50.0
    d = s.diff().dropna()
    g = d.clip(lower=0).rolling(p).mean().iloc[-1]
    l = (-d.clip(upper=0)).rolling(p).mean().iloc[-1]
    if l == 0:
        return 100.0
    return round(100 - 100 / (1 + g / l), 2)

def calc_macd(s: pd.Series) -> dict:
    if len(s) < 26:
        return {"macd": 0, "signal": 0, "hist": 0}
    m   = s.ewm(span=12, adjust=False).mean() - s.ewm(span=26, adjust=False).mean()
    sig = m.ewm(span=9, adjust=False).mean()
    return {
        "macd":   round(float(m.iloc[-1]), 2),
        "signal": round(float(sig.iloc[-1]), 2),
        "hist":   round(float((m - sig).iloc[-1]), 2),
    }

def calc_bb(s: pd.Series, p: int = 20) -> dict:
    if len(s) < p:
        v = float(s.iloc[-1])
        return {"upper": v, "lower": v, "mid": v, "width": 0}
    sma = s.rolling(p).mean().iloc[-1]
    std = s.rolling(p).std().iloc[-1]
    return {
        "upper": round(float(sma + 2 * std), 2),
        "lower": round(float(sma - 2 * std), 2),
        "mid":   round(float(sma), 2),
        "width": round(float(std * 4 / sma * 100), 2) if sma else 0,
    }

def calc_atr(hi: pd.Series, lo: pd.Series, cl: pd.Series, p: int = 14) -> float:
    if len(cl) < p + 1:
        return 0
    # Reset indices to avoid alignment issues on concat
    hi = hi.reset_index(drop=True)
    lo = lo.reset_index(drop=True)
    cl = cl.reset_index(drop=True)
    tr = pd.concat([
        hi - lo,
        (hi - cl.shift()).abs(),
        (lo - cl.shift()).abs(),
    ], axis=1).max(axis=1)
    return round(float(tr.rolling(p).mean().iloc[-1]), 2)

def to_strike(price: float) -> int:
    if price > 5000: return round(price / 100) * 100
    if price > 1000: return round(price / 50)  * 50
    if price > 500:  return round(price / 20)  * 20
    return round(price / 10) * 10

def next_expiry() -> str:
    t = datetime.now()
    d = (3 - t.weekday() + 7) % 7 or 7
    return (t + timedelta(days=d)).strftime("%d %b '%y")

# ─── SIGNAL ENGINE ────────────────────────────────────────────────────────────
def generate_signal(sym: str, df: pd.DataFrame) -> dict:
    prices = df["close"].tolist()
    highs  = df["high"].tolist()
    lows   = df["low"].tolist()
    if len(prices) < 10:
        return None

    s     = pd.Series(prices)
    price = prices[-1]
    rsi   = calc_rsi(s)
    macd  = calc_macd(s)
    bb    = calc_bb(s)
    atr   = calc_atr(pd.Series(highs), pd.Series(lows), s)
    ema9  = round(float(s.ewm(span=9,  adjust=False).mean().iloc[-1]), 2)
    ema21 = round(float(s.ewm(span=21, adjust=False).mean().iloc[-1]), 2)
    sma20 = round(float(s.rolling(20).mean().iloc[-1]), 2) if len(prices) >= 20 else price
    chg   = round((price - prices[-2]) / prices[-2] * 100, 2) if len(prices) > 1 else 0
    chg5  = round((price - prices[-6]) / prices[-6] * 100, 2) if len(prices) > 5 else 0

    sc, rs = 0, []
    if rsi < 35:   sc += 2;   rs.append("RSI oversold")
    elif rsi > 65: sc -= 2;   rs.append("RSI overbought")
    elif rsi < 50: sc += 0.5
    else:          sc -= 0.5

    if macd["hist"] > 0: sc += 1.5; rs.append("MACD bullish crossover")
    else:                sc -= 1.5; rs.append("MACD bearish crossover")

    if ema9 > ema21: sc += 1; rs.append("9EMA above 21EMA")
    else:            sc -= 1; rs.append("9EMA below 21EMA")

    rng   = bb["upper"] - bb["lower"]
    bbpos = (price - bb["lower"]) / rng if rng > 0 else 0.5
    if bbpos < 0.2:   sc += 1.5; rs.append("Price near BB lower band")
    elif bbpos > 0.8: sc -= 1.5; rs.append("Price near BB upper band")

    if price > sma20 * 1.02:   sc += 0.5
    elif price < sma20 * 0.98: sc -= 0.5

    direction  = "LONG" if sc >= 1 else "SHORT" if sc <= -1 else "NEUTRAL"
    confidence = min(99, round(abs(sc) / 6 * 100))
    k  = to_strike(price)
    ex = next_expiry()

    if direction == "LONG":
        if confidence > 70:
            opt = "Bull Call Spread"
            det = {"buy": f"{sym} {k} CE", "sell": f"{sym} {to_strike(price*1.03)} CE",
                   "expiry": ex, "maxProfit": f"₹{round(atr*3)}", "maxLoss": f"₹{round(atr*1.5)}", "premium": f"₹{round(atr*1.2)}"}
        else:
            opt = "ATM Call Buy"
            det = {"buy": f"{sym} {k} CE", "expiry": ex,
                   "target": f"₹{round(price*1.04,2)}", "stopLoss": f"₹{round(price*0.985,2)}", "premium": f"₹{round(atr*0.8)}"}
    elif direction == "SHORT":
        if confidence > 70:
            opt = "Bear Put Spread"
            det = {"buy": f"{sym} {k} PE", "sell": f"{sym} {to_strike(price*0.97)} PE",
                   "expiry": ex, "maxProfit": f"₹{round(atr*3)}", "maxLoss": f"₹{round(atr*1.5)}", "premium": f"₹{round(atr*1.2)}"}
        else:
            opt = "ATM Put Buy"
            det = {"buy": f"{sym} {k} PE", "expiry": ex,
                   "target": f"₹{round(price*0.96,2)}", "stopLoss": f"₹{round(price*1.015,2)}", "premium": f"₹{round(atr*0.8)}"}
    else:
        opt = "Iron Condor"
        det = {"sellCall": f"{sym} {to_strike(price*1.025)} CE", "buyCall": f"{sym} {to_strike(price*1.04)} CE",
               "sellPut":  f"{sym} {to_strike(price*0.975)} PE", "buyPut":  f"{sym} {to_strike(price*0.96)} PE",
               "expiry": ex, "premium": f"₹{round(atr*0.6)}"}

    return {
        "sym": sym, "sector": SECTOR_MAP.get(sym, "Misc"),
        "price": round(price, 2), "change": chg, "change5d": chg5,
        "rsi": rsi, "macd": macd, "bb": bb, "bbPos": round(bbpos, 2),
        "sma20": sma20, "ema9": ema9, "ema21": ema21, "atr": atr,
        "score": round(sc, 2), "direction": direction, "confidence": confidence,
        "reasons": rs[:3], "optionStrategy": opt, "optionDetails": det,
        "priceHistory": [round(p, 2) for p in prices[-60:]],
        "lastUpdated": datetime.now().isoformat(),
    }

# ─── BATCH FETCHER ────────────────────────────────────────────────────────────
def do_fetch():
    global _cache, _cache_ts, _fetching
    if _fetching:
        return
    _fetching = True
    logger.info("Fetching all Nifty 50 via nsepython...")
    results = []

    for sym in NIFTY50_SYMBOLS:
        try:
            df  = fetch_stock(sym)
            if df.empty or len(df) < 10:
                logger.warning(f"✗ {sym}: insufficient data ({len(df)} rows)")
                continue
            sig = generate_signal(sym, df)
            if sig:
                results.append(sig)
                logger.info(f"✓ {sym}: ₹{sig['price']} [{sig['direction']}]")
            time.sleep(0.5)  # polite delay
        except Exception as e:
            logger.error(f"✗ {sym}: {e}")
            continue

    logger.info(f"Fetch complete: {len(results)}/{len(NIFTY50_SYMBOLS)} stocks")

    if results:
        longs    = sum(1 for s in results if s["direction"] == "LONG")
        shorts   = sum(1 for s in results if s["direction"] == "SHORT")
        neutrals = sum(1 for s in results if s["direction"] == "NEUTRAL")
        _cache = {
            "stocks": results,
            "nifty": fetch_nifty(),
            "summary": {"longs": longs, "shorts": shorts, "neutrals": neutrals, "total": len(results)},
            "fetchedAt": datetime.now().isoformat(),
            "nextRefresh": CACHE_TTL,
            "dataSource": "NSE India (via nsepython)",
        }
        _cache_ts = time.time()
        logger.info("✓ Cache updated")
    else:
        logger.error("No results — all fetches failed")

    _fetching = False

# ─── LIFESPAN ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=do_fetch, daemon=True).start()
    logger.info("Startup: background fetch triggered")
    yield

app = FastAPI(title="N50 Swing Algo API", version="5.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ─── ROUTES ───────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "message": "N50 Swing Algo API v5 — nsepython"}

@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "cacheAge": round(time.time() - _cache_ts) if _cache_ts else None,
        "stocksCached": len(_cache.get("stocks", [])) if _cache else 0,
        "fetching": _fetching,
    }

@app.get("/api/test")
def test():
    """Test NSE connectivity with INFY."""
    try:
        df = fetch_stock("INFY")
        return {
            "status": "ok",
            "symbol": "INFY",
            "rows": len(df),
            "columns": list(df.columns),
            "lastClose": round(float(df["close"].iloc[-1]), 2),
            "lastDate": str(df["date"].iloc[-1].date()),
        }
    except Exception as e:
        # Also return raw columns if possible for debugging
        try:
            from nsepython import equity_history
            end   = datetime.now().strftime("%d-%m-%Y")
            start = (datetime.now() - timedelta(days=10)).strftime("%d-%m-%Y")
            raw = equity_history("INFY", "EQ", start, end)
            return {"status": "error", "message": str(e), "rawColumns": list(raw.columns) if hasattr(raw, 'columns') else str(type(raw))}
        except Exception as e2:
            return {"status": "error", "message": str(e), "rawError": str(e2)}

@app.get("/api/refresh")
def refresh():
    """Manually trigger a re-fetch."""
    global _fetching
    if _fetching:
        return {"status": "already fetching"}
    threading.Thread(target=do_fetch, daemon=True).start()
    return {"status": "fetch started"}

@app.get("/api/stocks")
def get_stocks():
    # Fresh cache — return immediately
    if _cache and (time.time() - _cache_ts) < CACHE_TTL:
        return JSONResponse(content=_cache)

    # Stale cache — return it and refresh in background
    if _cache:
        if not _fetching:
            threading.Thread(target=do_fetch, daemon=True).start()
        return JSONResponse(content=_cache)

    # Still loading first time
    if _fetching:
        return JSONResponse(status_code=503, content={
            "error": "Data is loading for the first time, please retry in 60 seconds",
            "fetching": True,
        })

    # Nothing yet — trigger and return 503
    threading.Thread(target=do_fetch, daemon=True).start()
    return JSONResponse(status_code=503, content={
        "error": "Fetching data now, please retry in 60 seconds",
        "fetching": True,
    })
