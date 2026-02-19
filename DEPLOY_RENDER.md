# 🚀 Deploy to Render.com — Step by Step

Your app will be live at two free URLs:
- **Frontend:** `https://n50-frontend.onrender.com`
- **Backend API:** `https://n50-backend.onrender.com`

---

## Step 1 — Push to GitHub

You need a free GitHub account. The code must be in a repo for Render to deploy it.

```bash
# 1. Create a new repo on github.com (click + → New repository)
#    Name it: n50-swing-algo
#    Set to Public (free Render needs public repo, or upgrade for private)

# 2. In your terminal, inside the n50-swing-algo folder:
git init
git add .
git commit -m "Initial commit — N50 Swing Algo"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/n50-swing-algo.git
git push -u origin main
```

---

## Step 2 — Deploy on Render (Blueprint — One Click)

1. Go to → **https://dashboard.render.com**
2. Sign up / log in (free, no credit card)
3. Click **"New +"** → **"Blueprint"**
4. Connect your GitHub account if prompted
5. Select your `n50-swing-algo` repo
6. Render reads `render.yaml` automatically
7. Click **"Apply"**

Render will now:
- Create `n50-backend` (Python FastAPI) — takes ~3 min to build
- Create `n50-frontend` (React static site) — takes ~2 min to build
- Wire `VITE_API_URL` automatically to point frontend → backend

---

## Step 3 — Open Your App

Once both services show **"Live"** (green):

```
https://n50-frontend.onrender.com
```

The first load after the backend spins up takes ~30 seconds (it fetches all 50 stocks from Yahoo Finance).

---

## ⚠️ Free Tier Limitations

| Limitation | Detail |
|---|---|
| **Sleep after 15 min** | Backend spins down if no traffic. First request wakes it (~30s). |
| **750 hrs/month** | Enough for one service running 24/7 |
| **Build minutes** | 400 free build minutes/month |

### Fix the sleep issue (optional)

Add an uptime monitor to ping your backend every 10 min. Free options:
- **UptimeRobot** (https://uptimerobot.com) — free, monitors every 5 min
  - Add HTTP monitor → URL: `https://n50-backend.onrender.com/api/health`
- **Cron-job.org** — free scheduled pings

---

## Updating the App

Any push to `main` branch auto-redeploys:

```bash
# Make changes, then:
git add .
git commit -m "Update signal logic"
git push
# Render auto-deploys in ~3 min
```

---

## Checking Logs

In Render dashboard → click `n50-backend` → **Logs** tab

You'll see:
```
INFO: Fetching data from Yahoo Finance...
INFO: Fetched 50 stocks successfully
INFO: Returning cached data
```

---

## Troubleshooting

**Backend build fails:**
- Check logs in Render dashboard
- Usually a pip install issue — requirements.txt versions can be loosened:
  Change `yfinance==0.2.40` to `yfinance>=0.2.40`

**Frontend shows "FETCH ERROR":**
- Backend might be sleeping — wait 30s and refresh
- Check backend URL: visit `https://n50-backend.onrender.com/api/health` directly

**No stocks loading (empty table):**
- Yahoo Finance might be rate limiting — wait 2 min and retry
- Check backend logs for `yfinance` errors
