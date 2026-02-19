import { useState, useEffect, useCallback } from "react";

const _apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
const API_BASE = _apiUrl.startsWith("http") ? _apiUrl : `https://${_apiUrl}`;

// ─── SPARKLINE ────────────────────────────────────────────────────────────────
function Sparkline({ prices, color, width = 88, height = 20 }) {
  if (!prices || prices.length < 2) return null;
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const pts = prices.map((p, i) => {
    const x = (i / (prices.length - 1)) * width;
    const y = height - ((p - min) / range) * (height - 2) - 1;
    return `${x},${y}`;
  }).join(" ");
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5"
        strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

// ─── RSI ARC ──────────────────────────────────────────────────────────────────
function RSIArc({ value }) {
  const c = value < 30 ? "#22c55e" : value > 70 ? "#ef4444" : "#f59e0b";
  const r = 14; const circ = Math.PI * r;
  const offset = circ * (1 - value / 100);
  return (
    <svg width={36} height={22} viewBox="0 0 36 22">
      <path d="M 4 18 A 14 14 0 0 1 32 18" fill="none" stroke="#1e293b" strokeWidth="3.5" />
      <path d="M 4 18 A 14 14 0 0 1 32 18" fill="none" stroke={c} strokeWidth="3.5"
        strokeDasharray={`${circ}`} strokeDashoffset={offset} strokeLinecap="round"
        style={{ transition: "stroke-dashoffset 0.6s" }} />
      <text x="18" y="21" textAnchor="middle" fontSize="7.5" fill={c} fontWeight="700">{value}</text>
    </svg>
  );
}

// ─── SKELETON ROW ─────────────────────────────────────────────────────────────
function SkeletonRow() {
  return (
    <div style={{
      display: "grid", gridTemplateColumns: "110px 100px 64px 64px 40px 56px 68px 100px 1fr",
      padding: "10px 16px", gap: 8, borderBottom: "1px solid rgba(255,255,255,0.025)",
      alignItems: "center",
    }}>
      {[110, 100, 64, 64, 40, 56, 68, 100, 120].map((w, i) => (
        <div key={i} style={{
          height: i === 1 ? 28 : 14, width: "100%", maxWidth: w,
          background: "linear-gradient(90deg,#0f172a 25%,#1e293b 50%,#0f172a 75%)",
          backgroundSize: "200% 100%", borderRadius: 3,
          animation: "shimmer 1.5s infinite",
        }} />
      ))}
    </div>
  );
}

// ─── MAIN APP ─────────────────────────────────────────────────────────────────
export default function App() {
  const [data, setData] = useState([]);
  const [nifty, setNifty] = useState(null);
  const [summary, setSummary] = useState({ longs: 0, shorts: 0, neutrals: 0, total: 0 });
  const [filter, setFilter] = useState("ALL");
  const [sort, setSort] = useState("confidence");
  const [selected, setSelected] = useState(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastFetch, setLastFetch] = useState(null);
  const [nextRefresh, setNextRefresh] = useState(60);
  const [dataSource, setDataSource] = useState("");
  const [countdown, setCountdown] = useState(60);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const res = await fetch(`${API_BASE}/api/stocks`);
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const json = await res.json();
      setData(json.stocks || []);
      setNifty(json.nifty);
      setSummary(json.summary || {});
      setLastFetch(new Date(json.fetchedAt));
      setNextRefresh(json.nextRefresh || 60);
      setCountdown(json.nextRefresh || 60);
      setDataSource(json.dataSource || "");
      setLoading(false);
    } catch (e) {
      setError(e.message);
      setLoading(false);
      // Auto-retry after 15s (handles Render cold start + first fetch)
      setTimeout(fetchData, 15000);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Auto-refresh every nextRefresh seconds
  useEffect(() => {
    if (!nextRefresh) return;
    const iv = setInterval(fetchData, nextRefresh * 1000);
    return () => clearInterval(iv);
  }, [nextRefresh, fetchData]);

  // Countdown timer
  useEffect(() => {
    const iv = setInterval(() => setCountdown(c => Math.max(0, c - 1)), 1000);
    return () => clearInterval(iv);
  }, [lastFetch]);

  const filtered = data
    .filter(s => (filter === "ALL" || s.direction === filter) &&
      (!search || s.sym.toLowerCase().includes(search.toLowerCase())))
    .sort((a, b) =>
      sort === "confidence" ? b.confidence - a.confidence :
      sort === "change" ? b.change - a.change :
      sort === "rsi" ? a.rsi - b.rsi :
      b.score - a.score
    );

  const sel = selected ? data.find(s => s.sym === selected) : null;
  const topLong = data.filter(s => s.direction === "LONG").sort((a, b) => b.confidence - a.confidence)[0];
  const topShort = data.filter(s => s.direction === "SHORT").sort((a, b) => b.confidence - a.confidence)[0];
  const topPicks = [topLong, topShort,
    ...data.filter(s => s.direction !== "NEUTRAL").sort((a, b) => b.confidence - a.confidence).slice(2, 4)
  ].filter(Boolean);

  return (
    <div style={{ fontFamily: "'IBM Plex Mono',monospace", background: "#030a14", minHeight: "100vh", color: "#cbd5e1" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&display=swap');
        *{box-sizing:border-box;margin:0;padding:0}
        @keyframes blink{0%,100%{opacity:1}50%{opacity:0.2}}
        @keyframes fadeUp{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
        @keyframes slideRight{from{opacity:0;transform:translateX(16px)}to{opacity:1;transform:translateX(0)}}
        @keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
        @keyframes spin{to{transform:rotate(360deg)}}
        ::-webkit-scrollbar{width:3px;height:3px}
        ::-webkit-scrollbar-track{background:#0c1524}
        ::-webkit-scrollbar-thumb{background:#1e3a5f;border-radius:2px}
        .row:hover{background:rgba(251,191,36,0.05)!important;cursor:pointer}
        .btn:hover{border-color:rgba(251,191,36,0.35)!important;color:#e2e8f0!important}
        input::placeholder{color:#334155}
        input:focus{outline:none;border-color:rgba(251,191,36,0.3)!important}
      `}</style>

      {/* BG grid */}
      <div style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0,
        backgroundImage: "linear-gradient(rgba(251,191,36,0.025) 1px,transparent 1px),linear-gradient(90deg,rgba(251,191,36,0.025) 1px,transparent 1px)",
        backgroundSize: "48px 48px" }} />

      {/* ── TOPBAR ─────────────────────────────────────────────────────────── */}
      <div style={{ position: "sticky", top: 0, zIndex: 50,
        background: "rgba(3,10,20,0.97)", borderBottom: "1px solid rgba(251,191,36,0.15)",
        backdropFilter: "blur(8px)", padding: "10px 24px",
        display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap" }}>

        {/* Brand */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 34, height: 34, borderRadius: "50%",
            background: "linear-gradient(135deg,#f59e0b,#ef4444)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 16, fontWeight: 900, color: "#000", boxShadow: "0 0 18px rgba(245,158,11,0.35)" }}>⬡</div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "#fbbf24", letterSpacing: "0.1em" }}>N50 SWING ALGO</div>
            <div style={{ fontSize: 8, color: "#334155", letterSpacing: "0.18em" }}>LIVE OPTIONS SIGNAL ENGINE</div>
          </div>
        </div>

        {/* NIFTY INDEX */}
        {nifty && (
          <div style={{ background: "rgba(251,191,36,0.05)", border: "1px solid rgba(251,191,36,0.12)",
            borderRadius: 8, padding: "6px 16px", display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 9, color: "#475569", letterSpacing: "0.15em" }}>NIFTY 50</span>
            <span style={{ fontSize: 20, fontWeight: 800, color: "#fbbf24" }}>{nifty.price?.toFixed(2)}</span>
            <span style={{ fontSize: 11, fontWeight: 600, color: nifty.change >= 0 ? "#22c55e" : "#ef4444" }}>
              {nifty.change >= 0 ? "▲" : "▼"} {Math.abs(nifty.change).toFixed(2)} ({nifty.changePct >= 0 ? "+" : ""}{nifty.changePct}%)
            </span>
          </div>
        )}

        {/* Breadth */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 200 }}>
          <div style={{ flex: 1, maxWidth: 180, height: 5, borderRadius: 3, background: "#0f172a", overflow: "hidden", display: "flex" }}>
            <div style={{ width: `${summary.longs * 2}%`, background: "#22c55e", transition: "width 0.5s" }} />
            <div style={{ width: `${summary.neutrals * 2}%`, background: "#f59e0b", transition: "width 0.5s" }} />
            <div style={{ width: `${summary.shorts * 2}%`, background: "#ef4444", transition: "width 0.5s" }} />
          </div>
          <span style={{ fontSize: 9, color: "#22c55e", fontWeight: 700 }}>▲{summary.longs}</span>
          <span style={{ fontSize: 9, color: "#f59e0b" }}>—{summary.neutrals}</span>
          <span style={{ fontSize: 9, color: "#ef4444", fontWeight: 700 }}>▼{summary.shorts}</span>
        </div>

        {/* Right */}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
          {/* Data source */}
          <span style={{ fontSize: 8, color: "#1e3a5f", letterSpacing: "0.1em" }}>
            {dataSource}
          </span>
          {/* Refresh countdown */}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div style={{ width: 28, height: 28, position: "relative", cursor: "pointer" }} onClick={fetchData} title="Refresh now">
              <svg viewBox="0 0 28 28" width="28" height="28" style={{ position: "absolute" }}>
                <circle cx="14" cy="14" r="12" fill="none" stroke="#0f172a" strokeWidth="2.5" />
                <circle cx="14" cy="14" r="12" fill="none" stroke="#fbbf24" strokeWidth="2.5"
                  strokeDasharray={`${2 * Math.PI * 12}`}
                  strokeDashoffset={`${2 * Math.PI * 12 * (1 - countdown / nextRefresh)}`}
                  strokeLinecap="round"
                  style={{ transform: "rotate(-90deg)", transformOrigin: "center", transition: "stroke-dashoffset 1s linear" }}
                />
              </svg>
              <span style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center",
                justifyContent: "center", fontSize: 7, color: "#fbbf24", fontWeight: 700 }}>{countdown}s</span>
            </div>
          </div>
          {/* Live indicator */}
          {loading ? (
            <div style={{ width: 16, height: 16, border: "2px solid #fbbf24", borderTopColor: "transparent",
              borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
          ) : (
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: error ? "#ef4444" : "#22c55e",
              display: "inline-block", boxShadow: `0 0 8px ${error ? "#ef4444" : "#22c55e"}`,
              animation: "blink 2s infinite" }} />
          )}
        </div>
      </div>

      {/* ── MAIN ───────────────────────────────────────────────────────────── */}
      <div style={{ position: "relative", zIndex: 1, padding: "16px 24px", display: "flex", flexDirection: "column", gap: 14 }}>

        {/* ERROR / COLD-START BANNER */}
        {error && (
          <div style={{ background: "rgba(245,158,11,0.07)", border: "1px solid rgba(245,158,11,0.2)",
            borderRadius: 8, padding: "12px 16px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <div style={{ fontSize: 10, color: "#fbbf24", fontWeight: 700, marginBottom: 4 }}>
                  ⏳ BACKEND WAKING UP (RENDER FREE TIER)
                </div>
                <div style={{ fontSize: 9, color: "#64748b" }}>
                  First request takes ~30 seconds. Retrying automatically…
                </div>
              </div>
              <button onClick={fetchData} style={{ background: "rgba(251,191,36,0.12)", border: "1px solid rgba(251,191,36,0.25)",
                borderRadius: 5, color: "#fbbf24", cursor: "pointer", padding: "5px 14px",
                fontSize: 9, fontFamily: "inherit", letterSpacing: "0.1em" }}>RETRY NOW</button>
            </div>
            <div style={{ marginTop: 8, height: 2, background: "#0f172a", borderRadius: 1, overflow: "hidden" }}>
              <div style={{ height: "100%", background: "linear-gradient(90deg,#f59e0b,#fbbf24)",
                animation: "shimmer 1.5s infinite", backgroundSize: "200% 100%", width: "60%" }} />
            </div>
          </div>
        )}

        {/* TOP PICKS */}
        {!loading && topPicks.length > 0 && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 12, animation: "fadeUp 0.4s ease" }}>
            {topPicks.map((s, i) => (
              <div key={s.sym} onClick={() => setSelected(s.sym)} style={{
                background: s.direction === "LONG"
                  ? "linear-gradient(135deg,rgba(34,197,94,0.07),rgba(34,197,94,0.01))"
                  : "linear-gradient(135deg,rgba(239,68,68,0.07),rgba(239,68,68,0.01))",
                border: `1px solid ${s.direction === "LONG" ? "rgba(34,197,94,0.18)" : "rgba(239,68,68,0.18)"}`,
                borderRadius: 10, padding: "12px 14px", cursor: "pointer",
              }}>
                <div style={{ fontSize: 8, color: "#334155", letterSpacing: "0.15em", marginBottom: 3 }}>
                  {i === 0 ? "★ TOP LONG PICK" : i === 1 ? "★ TOP SHORT PICK" : `#${i + 1} ${s.direction} PICK`}
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 800, color: "#f1f5f9" }}>{s.sym}</div>
                    <div style={{ fontSize: 9, color: "#334155", marginTop: 1 }}>{s.sector}</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 15, fontWeight: 800, color: "#fbbf24" }}>
                      ₹{s.price?.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                    </div>
                    <div style={{ fontSize: 10, color: s.change >= 0 ? "#22c55e" : "#ef4444" }}>
                      {s.change >= 0 ? "+" : ""}{s.change}%
                    </div>
                  </div>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
                  <span style={{ fontSize: 8, fontWeight: 700, letterSpacing: "0.08em",
                    color: s.direction === "LONG" ? "#22c55e" : "#ef4444",
                    background: s.direction === "LONG" ? "rgba(34,197,94,0.1)" : "rgba(239,68,68,0.1)",
                    padding: "2px 7px", borderRadius: 3 }}>
                    {s.direction === "LONG" ? "▲ LONG" : "▼ SHORT"} · {s.optionStrategy}
                  </span>
                  <span style={{ fontSize: 11, fontWeight: 800, color: "#fbbf24" }}>{s.confidence}%</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* CONTROLS */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <input id="symbol-search" name="symbol-search" value={search} onChange={e => setSearch(e.target.value)}
            placeholder="🔍 Search symbol..." style={{
              background: "rgba(15,23,42,0.7)", border: "1px solid rgba(255,255,255,0.07)",
              borderRadius: 6, padding: "6px 12px", color: "#e2e8f0",
              fontSize: 11, fontFamily: "inherit", width: 160,
            }} />

          <div style={{ display: "flex", gap: 6 }}>
            {["ALL", "LONG", "SHORT", "NEUTRAL"].map(f => (
              <button key={f} className="btn" onClick={() => setFilter(f)} style={{
                background: filter === f ? "rgba(251,191,36,0.12)" : "transparent",
                border: `1px solid ${filter === f ? "rgba(251,191,36,0.4)" : "rgba(255,255,255,0.07)"}`,
                borderRadius: 6, padding: "5px 12px",
                color: filter === f ? "#fbbf24" : "#475569",
                fontSize: 9, fontFamily: "inherit", cursor: "pointer",
                letterSpacing: "0.12em", transition: "all 0.15s",
                fontWeight: filter === f ? 700 : 400,
              }}>
                {f}
                {f !== "ALL" && <span style={{ marginLeft: 4, opacity: 0.7 }}>
                  {f === "LONG" ? summary.longs : f === "SHORT" ? summary.shorts : summary.neutrals}
                </span>}
              </button>
            ))}
          </div>

          <div style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center" }}>
            <span style={{ fontSize: 8, color: "#334155", letterSpacing: "0.12em" }}>SORT:</span>
            {["confidence", "change", "rsi", "score"].map(s => (
              <button key={s} className="btn" onClick={() => setSort(s)} style={{
                background: sort === s ? "rgba(251,191,36,0.12)" : "transparent",
                border: `1px solid ${sort === s ? "rgba(251,191,36,0.3)" : "rgba(255,255,255,0.06)"}`,
                borderRadius: 5, padding: "4px 9px",
                color: sort === s ? "#fbbf24" : "#334155",
                fontSize: 8, fontFamily: "inherit", cursor: "pointer",
                letterSpacing: "0.1em", textTransform: "uppercase", transition: "all 0.15s",
              }}>{s}</button>
            ))}
          </div>
        </div>

        {/* TABLE + DETAIL */}
        <div style={{ display: "grid", gridTemplateColumns: sel ? "1fr 380px" : "1fr", gap: 14, alignItems: "start" }}>

          {/* TABLE */}
          <div style={{ background: "rgba(12,21,36,0.6)", border: "1px solid rgba(251,191,36,0.08)", borderRadius: 12, overflow: "hidden" }}>
            <div style={{
              display: "grid", gridTemplateColumns: "110px 100px 64px 64px 40px 56px 68px 100px 1fr",
              padding: "8px 16px", borderBottom: "1px solid rgba(251,191,36,0.08)",
              fontSize: 7.5, color: "#334155", letterSpacing: "0.15em", gap: 8,
              background: "rgba(0,0,0,0.3)",
            }}>
              <span>SYMBOL</span><span>PRICE</span><span>1D%</span><span>5D%</span>
              <span>RSI</span><span>MACD</span><span>BB POS</span><span>SIGNAL</span><span>OPTIONS PLAY</span>
            </div>

            <div style={{ maxHeight: sel ? "calc(100vh - 380px)" : "calc(100vh - 300px)", overflowY: "auto" }}>
              {loading
                ? Array.from({ length: 12 }).map((_, i) => <SkeletonRow key={i} />)
                : filtered.map((s, i) => (
                <div key={s.sym} className="row" onClick={() => setSelected(sel?.sym === s.sym ? null : s.sym)} style={{
                  display: "grid", gridTemplateColumns: "110px 100px 64px 64px 40px 56px 68px 100px 1fr",
                  padding: "8px 16px", gap: 8, alignItems: "center",
                  borderBottom: "1px solid rgba(255,255,255,0.025)",
                  background: sel?.sym === s.sym ? "rgba(251,191,36,0.06)" : "transparent",
                  transition: "background 0.12s",
                  animation: `fadeUp 0.3s ease ${Math.min(i, 20) * 0.012}s both`,
                }}>
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#e2e8f0" }}>{s.sym}</div>
                    <div style={{ fontSize: 8, color: "#1e3a5f", marginTop: 1 }}>{s.sector}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "#fbbf24" }}>
                      ₹{s.price?.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                    </div>
                    <Sparkline prices={s.priceHistory?.slice(-20)} color={s.change >= 0 ? "#22c55e" : "#ef4444"} />
                  </div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: s.change >= 0 ? "#22c55e" : "#ef4444" }}>
                    {s.change >= 0 ? "+" : ""}{s.change}%
                  </div>
                  <div style={{ fontSize: 10, color: s.change5d >= 0 ? "#22c55e" : "#ef4444" }}>
                    {s.change5d >= 0 ? "+" : ""}{s.change5d}%
                  </div>
                  <RSIArc value={s.rsi} />
                  <div style={{ fontSize: 9, fontWeight: 700, color: s.macd?.hist > 0 ? "#22c55e" : "#ef4444" }}>
                    {s.macd?.hist > 0 ? "▲" : "▼"}{Math.abs(s.macd?.macd || 0).toFixed(1)}
                  </div>
                  {/* BB bar */}
                  <div>
                    <div style={{ height: 3, background: "#0f172a", borderRadius: 2, position: "relative", marginBottom: 2 }}>
                      <div style={{
                        position: "absolute", left: `${Math.max(2, Math.min(98, (s.bbPos || 0.5) * 100))}%`,
                        width: 3, height: 3, background: "#fbbf24", borderRadius: "50%",
                        transform: "translateX(-50%)", top: 0, transition: "left 0.5s",
                      }} />
                      <div style={{ width: "100%", height: "100%", background: "linear-gradient(90deg,#1e3a5f,#1e293b)" }} />
                    </div>
                    <div style={{ fontSize: 7, color: "#334155", textAlign: "center" }}>
                      {(s.bbPos || 0) < 0.25 ? "LOW" : (s.bbPos || 0) > 0.75 ? "HIGH" : "MID"}
                    </div>
                  </div>
                  {/* Signal */}
                  <div>
                    <div style={{
                      fontSize: 9, fontWeight: 800, letterSpacing: "0.08em", textAlign: "center",
                      padding: "2px 6px", borderRadius: 3, marginBottom: 3,
                      background: s.direction === "LONG" ? "rgba(34,197,94,0.12)" : s.direction === "SHORT" ? "rgba(239,68,68,0.12)" : "rgba(245,158,11,0.1)",
                      color: s.direction === "LONG" ? "#22c55e" : s.direction === "SHORT" ? "#ef4444" : "#f59e0b",
                    }}>
                      {s.direction === "LONG" ? "▲ LONG" : s.direction === "SHORT" ? "▼ SHORT" : "— NEUT"}
                    </div>
                    <div style={{ height: 3, background: "#0f172a", borderRadius: 2, overflow: "hidden" }}>
                      <div style={{
                        height: "100%", width: `${s.confidence}%`, borderRadius: 2,
                        background: s.direction === "LONG" ? "#22c55e" : s.direction === "SHORT" ? "#ef4444" : "#f59e0b",
                        transition: "width 0.5s",
                      }} />
                    </div>
                    <div style={{ fontSize: 7, color: "#334155", textAlign: "right", marginTop: 1 }}>{s.confidence}%</div>
                  </div>
                  {/* Options */}
                  <div>
                    <div style={{ fontSize: 9, fontWeight: 600, color: "#94a3b8" }}>{s.optionStrategy}</div>
                    <div style={{ fontSize: 8, color: "#334155", marginTop: 1 }}>
                      {s.optionDetails?.buy || (s.optionDetails?.sellCall ? "Multi-leg spread" : "")}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* DETAIL PANEL */}
          {sel && (
            <div style={{
              background: "rgba(12,21,36,0.7)", border: "1px solid rgba(251,191,36,0.15)",
              borderRadius: 12, padding: 18, animation: "slideRight 0.25s ease",
              maxHeight: "calc(100vh - 200px)", overflowY: "auto",
              display: "flex", flexDirection: "column", gap: 14,
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div style={{ fontSize: 22, fontWeight: 900, color: "#f1f5f9" }}>{sel.sym}</div>
                  <div style={{ fontSize: 9, color: "#334155", letterSpacing: "0.1em" }}>{sel.sector} · NSE · F&O</div>
                </div>
                <button onClick={() => setSelected(null)} style={{
                  background: "transparent", border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 5, color: "#475569", cursor: "pointer",
                  padding: "3px 9px", fontSize: 11, fontFamily: "inherit",
                }}>✕</button>
              </div>

              {/* Price */}
              <div style={{ background: "rgba(251,191,36,0.04)", border: "1px solid rgba(251,191,36,0.1)", borderRadius: 8, padding: 14 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div style={{ fontSize: 26, fontWeight: 900, color: "#fbbf24" }}>
                    ₹{sel.price?.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: sel.change >= 0 ? "#22c55e" : "#ef4444" }}>
                      {sel.change >= 0 ? "▲" : "▼"} {Math.abs(sel.change)}%
                    </div>
                    <div style={{ fontSize: 9, color: sel.change5d >= 0 ? "#22c55e" : "#ef4444", marginTop: 2 }}>
                      5D: {sel.change5d >= 0 ? "+" : ""}{sel.change5d}%
                    </div>
                  </div>
                </div>
                <div style={{ marginTop: 10 }}>
                  <Sparkline prices={sel.priceHistory} color="#fbbf24" width={320} height={64} />
                </div>
                <div style={{ fontSize: 8, color: "#1e3a5f", marginTop: 6 }}>
                  {sel.priceHistory?.length || 0} trading days · {dataSource}
                </div>
              </div>

              {/* Signal */}
              <div style={{
                background: sel.direction === "LONG" ? "rgba(34,197,94,0.06)" : sel.direction === "SHORT" ? "rgba(239,68,68,0.06)" : "rgba(245,158,11,0.06)",
                border: `1px solid ${sel.direction === "LONG" ? "rgba(34,197,94,0.2)" : sel.direction === "SHORT" ? "rgba(239,68,68,0.2)" : "rgba(245,158,11,0.2)"}`,
                borderRadius: 8, padding: 14,
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <span style={{
                    fontSize: 15, fontWeight: 900, letterSpacing: "0.08em",
                    color: sel.direction === "LONG" ? "#22c55e" : sel.direction === "SHORT" ? "#ef4444" : "#f59e0b",
                  }}>
                    {sel.direction === "LONG" ? "▲ LONG SIGNAL" : sel.direction === "SHORT" ? "▼ SHORT SIGNAL" : "— NEUTRAL / RANGE"}
                  </span>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 20, fontWeight: 900, color: "#fbbf24" }}>{sel.confidence}%</div>
                    <div style={{ fontSize: 7, color: "#334155", letterSpacing: "0.1em" }}>CONFIDENCE</div>
                  </div>
                </div>
                {sel.reasons?.map((r, i) => (
                  <div key={i} style={{ fontSize: 9, color: "#94a3b8", display: "flex", alignItems: "center", gap: 7, marginTop: 5 }}>
                    <span style={{ color: "#f59e0b", fontSize: 10 }}>◈</span>{r}
                  </div>
                ))}
              </div>

              {/* Indicators grid */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 7 }}>
                {[
                  { l: "RSI(14)", v: sel.rsi, c: sel.rsi < 35 ? "#22c55e" : sel.rsi > 65 ? "#ef4444" : "#f59e0b" },
                  { l: "MACD", v: sel.macd?.macd, c: sel.macd?.macd > 0 ? "#22c55e" : "#ef4444" },
                  { l: "SMA(20)", v: `₹${sel.sma20}`, c: "#94a3b8" },
                  { l: "ATR(14)", v: `₹${sel.atr}`, c: "#94a3b8" },
                  { l: "BB Upper", v: `₹${sel.bb?.upper}`, c: "#ef4444" },
                  { l: "BB Lower", v: `₹${sel.bb?.lower}`, c: "#22c55e" },
                  { l: "EMA(9)", v: `₹${sel.ema9}`, c: "#fbbf24" },
                  { l: "EMA(21)", v: `₹${sel.ema21}`, c: "#f97316" },
                ].map(({ l, v, c }) => (
                  <div key={l} style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.04)", borderRadius: 6, padding: "8px 10px" }}>
                    <div style={{ fontSize: 7.5, color: "#1e3a5f", letterSpacing: "0.1em" }}>{l}</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: c, marginTop: 2 }}>{v}</div>
                  </div>
                ))}
              </div>

              {/* Options strategy */}
              <div style={{ background: "rgba(251,191,36,0.04)", border: "1px solid rgba(251,191,36,0.12)", borderRadius: 8, padding: 14 }}>
                <div style={{ fontSize: 8, color: "#334155", letterSpacing: "0.15em", marginBottom: 6 }}>RECOMMENDED OPTIONS PLAY</div>
                <div style={{ fontSize: 15, fontWeight: 800, color: "#fbbf24", marginBottom: 10 }}>{sel.optionStrategy}</div>
                {Object.entries(sel.optionDetails || {}).map(([k, v]) => (
                  <div key={k} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "5px 0", borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                    <span style={{ fontSize: 9, color: "#334155", textTransform: "uppercase", letterSpacing: "0.08em" }}>
                      {k.replace(/([A-Z])/g, ' $1').trim()}
                    </span>
                    <span style={{ fontSize: 11, fontWeight: 600, color: "#e2e8f0" }}>{v}</span>
                  </div>
                ))}
              </div>

              {/* Entry / Target / SL */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
                {[
                  { l: "ENTRY", v: `₹${sel.price?.toFixed(2)}`, c: "#fbbf24", bg: "rgba(251,191,36,0.07)" },
                  { l: "TARGET", v: `₹${sel.direction === "LONG" ? (sel.price * 1.04).toFixed(2) : (sel.price * 0.96).toFixed(2)}`, c: "#22c55e", bg: "rgba(34,197,94,0.05)" },
                  { l: "STOP LOSS", v: `₹${sel.direction === "LONG" ? (sel.price * 0.985).toFixed(2) : (sel.price * 1.015).toFixed(2)}`, c: "#ef4444", bg: "rgba(239,68,68,0.05)" },
                ].map(({ l, v, c, bg }) => (
                  <div key={l} style={{ background: bg, borderRadius: 7, padding: "9px 8px", textAlign: "center", border: `1px solid ${c}20` }}>
                    <div style={{ fontSize: 7.5, color: "#334155", letterSpacing: "0.12em" }}>{l}</div>
                    <div style={{ fontSize: 12, fontWeight: 800, color: c, marginTop: 4 }}>{v}</div>
                  </div>
                ))}
              </div>

              {/* R:R */}
              <div style={{ background: "rgba(0,0,0,0.2)", borderRadius: 6, padding: "8px 12px",
                display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 9, color: "#334155", letterSpacing: "0.1em" }}>RISK : REWARD</span>
                <span style={{ fontSize: 13, fontWeight: 700, color: "#fbbf24" }}>1 : 2.7</span>
              </div>

              <div style={{ fontSize: 7.5, color: "#1e293b", borderTop: "1px solid rgba(255,255,255,0.03)", paddingTop: 8, lineHeight: 1.6 }}>
                ⚠ Data source: Yahoo Finance NSE (~15 min delayed). This is for educational & research purposes only.
                Not SEBI-registered investment advice. Verify with a certified advisor before trading.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
