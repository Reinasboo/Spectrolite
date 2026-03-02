Set-StrictMode -Off
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "==> Initialising git repository..." -ForegroundColor Cyan
git init
git branch -M main

Write-Host "==> Setting remote origin..." -ForegroundColor Cyan
$remoteExists = git remote | Select-String "origin"
if ($remoteExists) {
    git remote set-url origin https://github.com/Reinasboo/Spectrolite.git
} else {
    git remote add origin https://github.com/Reinasboo/Spectrolite.git
}

Write-Host "==> Staging all files..." -ForegroundColor Cyan
git add .

Write-Host "==> Committing..." -ForegroundColor Cyan
$msg = @"
feat: Spectrolite - Degenerate Gambit v2.0 initial release

Complete autonomous AI trading agent for Solana / EVM meme-coin markets.

Core architecture
- LangGraph-orchestrated OverseerAgent with full event loop
- Modular sub-agents: ChainAnalyst, SentimentEngine, SignalFusionEngine,
  ScamSlayer, WalletTracker, SwarmIntelligence, PositionManager, TradeExecutor

Signal pipeline
- 3-model ensemble predictor: BiLSTM-Transformer (18 features) + XGBoost
  RegimeClassifier + IsolationForest AnomalyScorer with Brier-score weighting
- Adaptive signal weight learner (EMA, 9 sources, persisted to JSON)
- Persistent WebSocket firehose (pump.fun) with exponential backoff
- Redis pub/sub signal bus eliminating redundant API calls
- Telegram channel monitoring via Telethon MTProto + influencer follower-weight
- CLIP zero-shot meme-image classification (open_clip ViT-B-32)

Execution
- Graduated 6-level trailing stop schedule (20% to 4%)
- Time-based theta-decay exit (20 min / +15% threshold)
- Kelly Criterion quarter-Kelly position sizing with 20-trade warm-up
- Dynamic priority fee estimation via MempoolMonitor (75th-pct, 30s cache)
- Re-entry engine: 25-35% dip bounce on partially-exited positions
- Shared httpx connection pool (HTTP/2, 50 connections) across all services

Scam shield
- Non-blocking Slither static analysis via run_in_executor
- Real-time LP liquidity watcher (DexScreener, 90s poll, 15% drop -> emergency exit)
- MEV bundle detection, honeypot simulation, social coordination scanner

Backtest and research
- Historical backtester with realistic transaction cost model
  (inverse-sqrt-liquidity slippage, DEX fee, priority fee round-trip)
- Monte Carlo simulation

Infrastructure
- Docker Compose stack: agent + Redis + Postgres + Prometheus
- Streamlit dashboard with Plotly charts
- Full pytest suite with asyncio support
- pyright-clean codebase
"@
git commit -m $msg

Write-Host "==> Pushing to GitHub..." -ForegroundColor Cyan
git push -u origin main

Write-Host ""
Write-Host "SUCCESS - https://github.com/Reinasboo/Spectrolite" -ForegroundColor Green
