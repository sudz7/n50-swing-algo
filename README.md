# ⬡ N50 Swing Algo — Options Signal Engine

A full-stack swing trading dashboard for Nifty 50 stocks.
Fetches **real NSE prices** via Yahoo Finance (free, no account needed, ~15 min delayed),
runs technical analysis, and recommends the most favourable options strategy for each stock.

---

## 📊 What It Does

| Feature | Details |
|---|---|
| **Data Source** | Yahoo Finance `.NS` tickers — free, no auth, NSE data |
| **Delay** | ~15 minutes (standard for free Yahoo Finance) |
| **Refresh** | Every 60 seconds (configurable in `backend/main.py`) |
| **Universe** | All 50 Nifty 50 stocks |
| **Indicators** | RSI(14), MACD(12/26/9), EMA(9/21), SMA(20), Bollinger Bands(20,2), ATR(14) |
| **Signals** | LONG / SHORT / NEUTRAL with confidence % |
| **Options** | Bull Call Spread, Bear Put Spread, ATM Call Buy, ATM Put Buy, Iron Condor |

---

## 🏗️ Architecture

```
┌─────────────────┐     HTTP /api/*      ┌──────────────────────┐
│   React + Nginx  │ ──────────────────▶  │  FastAPI + yfinance  │
│   (port 80)      │ ◀──────────────────  │  (port 8000)         │
│                  │     JSON response    │                      │
│  • Dashboard UI  │                      │  • Fetches NSE data  │
│  • Sparklines    │                      │  • Computes signals  │
│  • Options play  │                      │  • 60s cache         │
└─────────────────┘                      └──────────────────────┘
```

---

## 🚀 Quick Start (Docker — Recommended)

### Prerequisites
- Docker Desktop or Docker Engine + Docker Compose

### 1. Clone / unzip the project
```bash
cd n50-swing-algo
```

### 2. Build and start
```bash
docker-compose up --build
```

This will:
1. Build the Python backend (installs yfinance, fastapi, etc.)
2. Build the React frontend (npm install + vite build)
3. Serve the app via Nginx with the backend proxied

### 3. Open the app
```
http://localhost
```

The first load takes ~10–20 seconds as the backend fetches all 50 stocks from Yahoo Finance.

---

## 🛠️ Local Development (No Docker)

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

The Vite dev server proxies `/api/*` → `http://backend:8000`.
If running locally (not Docker), edit `vite.config.js` proxy target to `http://localhost:8000`.

---

## ☁️ Deploying to a Server (VPS / Cloud)

### Option A: Docker on VPS (Ubuntu/Debian)

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Upload project to server
scp -r n50-swing-algo/ user@your-server:/opt/

# SSH in and start
ssh user@your-server
cd /opt/n50-swing-algo
docker-compose up -d --build
```

App runs at `http://your-server-ip`

### Option B: Add HTTPS with Traefik or Certbot

For production with a domain name:

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Get SSL cert
sudo certbot --nginx -d yourdomain.com

# Update nginx.conf to use SSL and update your domain
```

Or use Traefik as a reverse proxy — add to docker-compose.yml:
```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.n50.rule=Host(`yourdomain.com`)"
  - "traefik.http.routers.n50.entrypoints=websecure"
  - "traefik.http.routers.n50.tls.certresolver=letsencrypt"
```

### Option C: Deploy to Render / Railway

**Backend (FastAPI):**
- New service → Web Service → connect repo → root dir: `backend`
- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`

**Frontend (React):**
- New service → Static Site → root dir: `frontend`
- Build: `npm install && npm run build`
- Publish dir: `dist`
- Set env var: `VITE_API_URL=https://your-backend.onrender.com`

---

## ⚙️ Configuration

### Change refresh interval
`backend/main.py` line:
```python
CACHE_TTL = 60  # seconds — increase to reduce Yahoo Finance requests
```

### Change analysis period
```python
raw = yf.download(..., period="3mo", ...)  # "1mo", "3mo", "6mo", "1y"
```

### Add/remove stocks
Edit `NIFTY50_SYMBOLS` list in `backend/main.py` — any NSE symbol that works on Yahoo Finance with `.NS` suffix.

---

## 📡 API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/stocks` | All 50 stocks with signals (cached 60s) |
| `GET /api/stock/{SYMBOL}` | Single stock detail |
| `GET /api/health` | Health check + cache status |
| `GET /` | API info |

---

## 📈 Signal Logic

Each stock is scored on these factors:

| Indicator | LONG | SHORT |
|---|---|---|
| RSI(14) | < 35 (oversold) +2pts | > 65 (overbought) -2pts |
| MACD Histogram | > 0 (bullish) +1.5pts | < 0 (bearish) -1.5pts |
| EMA 9 vs 21 | 9EMA > 21EMA +1pt | 9EMA < 21EMA -1pt |
| BB Position | Near lower band +1.5pts | Near upper band -1.5pts |
| Price vs SMA20 | > SMA20×1.02 +0.5pts | < SMA20×0.98 -0.5pts |

**Score ≥ 1 → LONG | Score ≤ -1 → SHORT | else NEUTRAL**

### Options Strategy Selection

| Signal | Confidence | Strategy |
|---|---|---|
| LONG | > 70% | Bull Call Spread |
| LONG | ≤ 70% | ATM Call Buy |
| SHORT | > 70% | Bear Put Spread |
| SHORT | ≤ 70% | ATM Put Buy |
| NEUTRAL | any | Iron Condor |

---

## ⚠️ Disclaimer

> This tool is for **educational and research purposes only**.
> Data is sourced from Yahoo Finance and is approximately 15 minutes delayed.
> This is **NOT SEBI-registered investment advice**.
> Always verify signals with a certified financial advisor before executing trades.
> Options trading involves significant risk of loss.

---

## 🤝 Upgrading to Real-Time Data

When you're ready for live tick data, replace the yfinance backend with:

| Broker API | Free? | Real-time? | Docs |
|---|---|---|---|
| Zerodha Kite Connect | ₹2000/month | ✅ WebSocket ticks | kite.trade/docs |
| Upstox API v2 | Free with account | ✅ WebSocket | upstox.com/developer |
| Angel SmartAPI | Free with account | ✅ WebSocket | smartapi.angelbroking.com |
| Dhan API | Free with account | ✅ WebSocket | dhanhq.co/docs |

All these support WebSocket for tick-by-tick data which you can pipe into the same
signal engine in `main.py` — just replace the `yf.download()` call with your WebSocket feed.
