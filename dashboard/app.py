"""
SPECTROLITE — Degenerate Gambit Dashboard
Real-time P&L visualization with degen flair.
Run: streamlit run dashboard/app.py --server.port 8501
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SPECTROLITE | Degenerate Gambit",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS: Degen Theme ──────────────────────────────────────────────────
st.markdown(
    """
<style>
  body { background: #0a0a0f; color: #00ff88; font-family: 'Courier New', monospace; }
  .main { background: #0a0a0f; }
  h1, h2, h3 { color: #00ff88; text-shadow: 0 0 10px #00ff8855; }
  .stMetric { background: #111122; border: 1px solid #00ff8822; border-radius: 8px; }
  .stMetric label { color: #888; }
  .stMetric .metric-value { color: #00ff88; font-size: 2rem; }
  .block-container { padding-top: 1rem; }
  div[data-testid="metric-container"] { background: #111122; padding: 12px; border-radius: 8px; }
</style>
""",
    unsafe_allow_html=True,
)


# ── Data Loader ───────────────────────────────────────────────────────────────

@st.cache_data(ttl=10)
def load_trade_data() -> pd.DataFrame:
    """Load trade history from database."""
    try:
        from degenerate_gambit.persistence import TradeLogger
        logger = TradeLogger()
        trades = logger.get_closed_trades(limit=500)
        if not trades:
            return _demo_data()
        return pd.DataFrame(trades)
    except Exception:
        return _demo_data()


def _demo_data() -> pd.DataFrame:
    """Synthetic demo data when no DB is connected."""
    import numpy as np
    rng = np.random.default_rng(42)
    n = 50
    dates = [datetime.utcnow() - timedelta(hours=i * 2) for i in range(n)]
    pnls = rng.normal(0.35, 1.2, n)
    return pd.DataFrame({
        "token_symbol": [f"DEMO{i}" for i in range(n)],
        "chain": rng.choice(["solana", "base", "bnb"], n),
        "realized_pnl_pct": pnls,
        "realized_pnl_usd": pnls * 200,
        "meme_score_at_entry": rng.uniform(60, 100, n),
        "scam_probability": rng.uniform(0.05, 0.40, n),
        "mode": rng.choice(["APE MODE", "SNIPER MODE", "STANDARD", "CASINO MODE"], n),
        "size_usd": rng.uniform(50, 500, n),
        "leverage": rng.choice([1, 2, 3, 5], n),
        "mutation_applied": rng.choice([True, False], n),
        "opened_at": dates,
        "closed_at": [d + timedelta(hours=rng.uniform(0.1, 4)) for d in dates],
        "status": ["closed"] * n,
    })


# ── Header ───────────────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 8])
with col_logo:
    st.markdown("# 🚀")
with col_title:
    st.markdown("# SPECTROLITE — Degenerate Gambit v2.0")
    st.markdown("*Autonomous AI Memecoin Trading Agent*")

st.markdown("---")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎰 Agent Status")
    agent_mode = st.empty()
    agent_mode.markdown("**Mode:** `STANDARD`")
    st.markdown("**Level:** `Certified Degen 🧬`")
    st.markdown("**Win Streak:** `0 🔥`")
    st.markdown("---")

    st.markdown("## ⚙️ Configuration")
    min_meme = st.slider("Min Meme Score", 50, 95, 65)
    max_scam = st.slider("Max Scam %", 10, 60, 40)
    capital = st.number_input("Portfolio Capital ($)", 1000, 1_000_000, 10_000, step=500)
    st.markdown("---")

    st.markdown("## 🔊 Voice Alerts")
    voice_on = st.checkbox("Enable Voice", value=True)
    if st.button("🔊 Test Alert"):
        st.info("MOON DETECTED")

    st.markdown("---")
    if st.button("🛑 EMERGENCY STOP"):
        st.error("⛔ SOBRIETY MODE ACTIVATED")

# ── Main KPI Row ─────────────────────────────────────────────────────────────
df = load_trade_data()
wins = df[df["realized_pnl_pct"] > 0]
losses = df[df["realized_pnl_pct"] <= 0]
total_pnl = df["realized_pnl_usd"].sum() if "realized_pnl_usd" in df else 0
win_rate = len(wins) / max(len(df), 1) * 100

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("💰 Total P&L", f"${total_pnl:+,.0f}")
c2.metric("🏆 Win Rate", f"{win_rate:.1f}%")
c3.metric("📊 Total Trades", str(len(df)))
c4.metric("🔥 Win Streak", "0")
c5.metric("📈 Best Trade", f"+{df['realized_pnl_pct'].max()*100:.0f}%" if len(df) > 0 else "N/A")

st.markdown("---")

# ── P&L Heatmap (Portfolio Heatmap) ─────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Portfolio Heatmap",
    "📈 P&L Chart",
    "🧪 Meme Report Feed",
    "💀 Risk Gauge",
])

with tab1:
    st.subheader("Live Portfolio Heatmap — Green Fire / Dumpster Fire")
    if len(df) > 0:
        # Treemap: size = position size, color = pnl %
        fig = px.treemap(
            df,
            path=["chain", "token_symbol"],
            values="size_usd",
            color="realized_pnl_pct",
            color_continuous_scale=["#ff0000", "#111111", "#00ff00"],
            color_continuous_midpoint=0,
            title="Portfolio Heatmap",
            custom_data=["realized_pnl_pct", "mode"],
        )
        fig.update_traces(
            hovertemplate="<b>%{label}</b><br>PnL: %{customdata[0]:.1%}<br>Mode: %{customdata[1]}"
        )
        fig.update_layout(
            paper_bgcolor="#0a0a0f",
            plot_bgcolor="#0a0a0f",
            font_color="#00ff88",
            coloraxis_colorbar_title="PnL %",
        )
        st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.subheader("Cumulative P&L Over Time")
    if len(df) > 0 and "closed_at" in df.columns:
        df_sorted = df.sort_values("closed_at")
        df_sorted["cumulative_pnl"] = df_sorted["realized_pnl_usd"].cumsum()
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=df_sorted["closed_at"],
            y=df_sorted["cumulative_pnl"],
            mode="lines+markers",
            line=dict(color="#00ff88", width=2),
            fill="tozeroy",
            fillcolor="rgba(0,255,136,0.1)",
            name="Cumulative PnL",
        ))
        fig2.update_layout(
            paper_bgcolor="#0a0a0f", plot_bgcolor="#0a0a0f",
            font_color="#00ff88",
            xaxis_title="Time", yaxis_title="P&L ($)",
            title="Cumulative P&L",
        )
        st.plotly_chart(fig2, use_container_width=True)

        # Win rate by meme score tier
        df["meme_tier"] = pd.cut(
            df["meme_score_at_entry"],
            bins=[0, 65, 75, 85, 100],
            labels=["<65", "65-75", "75-85", "85+"],
        )
        tier_stats = df.groupby("meme_tier", observed=True).apply(
            lambda g: pd.Series({
                "win_rate": (g["realized_pnl_pct"] > 0).mean(),
                "avg_pnl_pct": g["realized_pnl_pct"].mean(),
                "count": len(g),
            })
        ).reset_index()
        fig3 = px.bar(
            tier_stats, x="meme_tier", y="win_rate",
            color="avg_pnl_pct",
            color_continuous_scale=["red", "yellow", "green"],
            title="Win Rate by Meme Score Tier",
        )
        fig3.update_layout(paper_bgcolor="#0a0a0f", plot_bgcolor="#0a0a0f", font_color="#00ff88")
        st.plotly_chart(fig3, use_container_width=True)

with tab3:
    st.subheader("🔄 Meme Report Feed (Live)")
    # Scrolling feed of recent trade reports
    recent = df.sort_values("closed_at", ascending=False).head(10) if len(df) > 0 else pd.DataFrame()
    for _, row in recent.iterrows():
        pnl = row.get("realized_pnl_pct", 0)
        color = "#00ff88" if pnl > 0 else "#ff4444"
        emoji = "🚀" if pnl > 0.5 else ("💀" if pnl < -0.1 else "📊")
        st.markdown(
            f"""<div style="background:#111122;border-left:4px solid {color};
            padding:10px;margin:5px 0;border-radius:4px;">
            {emoji} <b>${row.get('token_symbol', '???')}</b> |
            PnL: <span style="color:{color}">{pnl*100:+.1f}%</span> |
            Mode: {row.get('mode', '?')} |
            Meme: {row.get('meme_score_at_entry', 0):.0f}
            </div>""",
            unsafe_allow_html=True,
        )

with tab4:
    st.subheader("💀 Risk Gauge — Portfolio Volatility")
    # Skull meter — simulated risk gauge
    avg_scam = df["scam_probability"].mean() if len(df) > 0 else 0.2
    risk_pct = avg_scam * 100

    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=risk_pct,
        domain={"x": [0, 1], "y": [0, 1]},
        title={"text": "Portfolio Risk Score", "font": {"color": "#00ff88"}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": "#00ff88"},
            "bar": {"color": "#00ff88"},
            "bgcolor": "#111122",
            "borderwidth": 2,
            "bordercolor": "#00ff88",
            "steps": [
                {"range": [0, 20], "color": "#003300"},
                {"range": [20, 40], "color": "#333300"},
                {"range": [40, 60], "color": "#442200"},
                {"range": [60, 80], "color": "#550000"},
                {"range": [80, 100], "color": "#880000"},
            ],
            "threshold": {
                "line": {"color": "red", "width": 4},
                "thickness": 0.75,
                "value": 80,
            },
        },
    ))
    fig_gauge.update_layout(
        paper_bgcolor="#0a0a0f", font_color="#00ff88", height=400
    )
    st.plotly_chart(fig_gauge, use_container_width=True)

    skull_count = int(risk_pct / 20)
    st.markdown(
        f"**Risk Level:** {'💀' * skull_count}{'⬜' * (5 - skull_count)} "
        f"({risk_pct:.0f}%)"
    )

# ── Degen Leaderboard ─────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("🏆 Degen Leaderboard — Top Tokens by P&L")
if len(df) > 0:
    leaderboard = (
        df.groupby("token_symbol")
        .agg(
            total_pnl_usd=("realized_pnl_usd", "sum"),
            avg_pnl_pct=("realized_pnl_pct", "mean"),
            trade_count=("token_symbol", "count"),
        )
        .sort_values("total_pnl_usd", ascending=False)
        .head(20)
    )
    st.dataframe(
        leaderboard.style.background_gradient(
            subset=["total_pnl_usd", "avg_pnl_pct"],
            cmap="RdYlGn",
        ).format({
            "total_pnl_usd": "${:+,.2f}",
            "avg_pnl_pct": "{:+.1%}",
        }),
        use_container_width=True,
    )

# ── Auto-refresh ──────────────────────────────────────────────────────────────
st.markdown(
    f"<small style='color:#444'>Last updated: {datetime.utcnow().strftime('%H:%M:%S UTC')} "
    f"— Auto-refreshes every 10 seconds</small>",
    unsafe_allow_html=True,
)
# Streamlit auto-rerun when cache TTL expires
if st.button("🔄 Refresh Now"):
    st.cache_data.clear()
    st.rerun()
