# SPECTROLITE â€” Degenerate Gambit v2.0

> *"I am not a bot. I am a force of nature with a terrible risk appetite and beautiful pattern recognition."*

```
AGENT IDENTITY     : SPECTROLITE
CODENAME           : DEGENERATE GAMBIT
VERSION            : 2.0
CLASSIFICATION     : Autonomous AI Memecoin Trading Agent
STACK              : Python 3.11+ Â· PyTorch Â· LangGraph Â· Playwright Â· Streamlit Â· Redis
```

---

## Table of Contents

1. [Overview](#overview)
2. [What's New in v2.0](#whats-new-in-v20)
3. [Architecture](#architecture)
4. [Signal Pipeline](#signal-pipeline)
5. [Execution Engine](#execution-engine)
6. [Scam Shield](#scam-shield)
7. [Prerequisites](#prerequisites)
8. [Quick Start (Docker)](#quick-start-docker)
9. [Manual Setup (Local)](#manual-setup-local)
10. [Environment Variables](#environment-variables)
11. [CLI Commands](#cli-commands)
12. [Dashboard](#dashboard)
13. [Backtesting](#backtesting)
14. [Monte Carlo Stress Tests](#monte-carlo-stress-tests)
15. [Personality Modes](#personality-modes)
16. [Deployment Scaling](#deployment-scaling)
17. [Monitoring](#monitoring)
18. [Project Structure](#project-structure)
19. [Ethical Guardrails & Legal Notice](#ethical-guardrails--legal-notice)

---

## Overview

**SPECTROLITE** is an autonomous, multi-agent AI system designed to identify and trade high-potential memecoin opportunities across Solana, Ethereum, Base, and BNB Chain. It combines:

- **3-Model Ensemble Predictor** â€” BiLSTM-Transformer (18 features) + XGBoost RegimeClassifier + IsolationForest AnomalyScorer with adaptive Brier-score weighting
- **Vibe Engine** â€” multi-platform sentiment mining (Twitter with follower-count weighting, Reddit, Telegram MTProto, CLIP visual meme analysis)
- **Scam Shield** â€” 5-layer rug protection (static analysis, dynamic simulation, social scanning, MEV detection, real-time LP depth monitoring)
- **Swarm Intelligence** â€” consensus-driven alpha wallet surveillance
- **Adaptive Signal Learner** â€” EMA-based per-source weight adjustment that improves with every closed trade
- **Redis Signal Bus** â€” pub/sub backbone eliminating redundant API calls across workers
- **Gamification Layer** â€” adaptive personality modes (APE / SNIPER / ZEN / CASINO / SOBRIETY)
- **Padre Terminal** â€” headless Playwright session for DEX execution
- **Real-time Streamlit dashboard** with degen P&L heatmap and meme report feed

---

## What's New in v2.0

### Model & Signal Intelligence

| Improvement | Detail |
|---|---|
| **18-Feature BiLSTM-Transformer** | Extended from 6 to 18 input features. New: `wash_trade_ratio`, `bonding_curve_velocity`, `insider_wallet_pre_position`, `rsi_5m/15m`, `token_age_minutes`, `dev_wallet_sell_pct`, `top_10_holder_concentration`, `cross_chain_arb_spread`, `telegram_mention_velocity`, `volume_acceleration` |
| **Transformer Encoder** | BiLSTM output fed through 2-layer 4-head pre-norm TransformerEncoder (FF=256, GELU) with sinusoidal positional encoding |
| **3-Model Ensemble** | PumpPredictorService (BiLSTM-Transformer) + RegimeClassifier (XGBoost, 4 regimes) + AnomalyScorer (IsolationForest, contamination=5%). Softmax accuracy-weighted combination via rolling Brier scores |
| **Adaptive Signal Weights** | `SignalWeightLearner`: EMA (alpha=0.05) per-source multipliers for 9 signal channels. Min 10 trades to activate. Range 0.30x-2.50x. Persisted to `models/signal_weights.json` |
| **Telegram Monitoring** | Telethon MTProto client monitors 5 default channels. 60-min rolling mention count + velocity z-score. +30% boost vs Twitter (TG breaks alpha 10-30 min earlier) |
| **Influencer Weighting** | Twitter tweets weighted by author follower count: 0.3x (unknown) to 15x (2M+ mega-influencer). Stored as `weighted_influence_score` |
| **CLIP Visual Analysis** | `open_clip` ViT-B-32 zero-shot classification on token icons (CoinGecko). 6-label pipeline: rocket/moon, pepe, dog, celeb, fire, boring. Emits `visual_hype_score` 0-30 |
| **Persistent WebSocket** | `subscribe_pumpfun_firehose()` reconnects with exponential backoff (2s to 120s). 20s ping keepalive. Auto-normalises raw events |
| **Redis Signal Bus** | `SignalPublisher/Subscriber/BusRouter` on `spectrolite:` prefix. Batch pipeline publishing. Eliminates redundant API calls across scaled workers |

### Execution & Risk

| Improvement | Detail |
|---|---|
| **Graduated Trailing Stop** | 6-level schedule: 20% stop at 0% gain down to 4% stop at 5%+ gain. Previously binary 20% to 8% |
| **Theta Decay Exit** | Force-closes positions that do not reach +15% within 20 minutes. Eliminates dead-weight holds |
| **Kelly Criterion Sizing** | Quarter-Kelly position sizing. Requires 20+ trade history. 1% floor, 20% cap. `record_trade_outcome()` feedback loop |
| **Dynamic Priority Fees** | `MempoolMonitor`: Solana 75th-percentile of recent prioritisation fees, EVM `eth_maxPriorityFeePerGas` +25% buffer. 30s per-chain cache |
| **Re-Entry Engine** | `ReEntryEngine`: triggers on 25-35% dip from partial-exit price + volume_z >= 1.5 + scam_prob < 0.35 + within 30 min. Single attempt per position |
| **Shared HTTP Pool** | Module-level `httpx.AsyncClient` (HTTP/2, 50 connections, 20 keepalive). All services share one pool instead of spawning per-session aiohttp sessions |

### Scam Shield Additions

| Improvement | Detail |
|---|---|
| **Non-blocking Slither** | `run_in_executor` wraps the blocking subprocess. Event loop no longer stalls during static analysis |
| **LP Liquidity Watcher** | `LiquidityWatcher`: polls DexScreener every 90s post-entry. Triggers `emergency_callback` on >=15% LP drop in 5-min window |

### Research & Backtest

| Improvement | Detail |
|---|---|
| **Transaction Cost Model** | `_apply_tx_costs()`: inverse-sqrt(liquidity) entry slippage + 1.5x exit slippage (thinner post-pump book) + 2x DEX fee (0.25%) + 2x priority fee (0.2%). Applied to every simulated trade |

---

## Architecture

```
+------------------------------------------------------------------------+
|                         SPECTROLITE v2.0                               |
|                                                                        |
|  +------------------+  +-----------------+  +----------------------+  |
|  |  Chain Analyst   |  | Sentiment Engine|  |  Wallet Tracker      |  |
|  |  x3 workers      |  |  Twitter (wtd)  |  |  Swarm Intelligence  |  |
|  |  pump.fun WS     |  |  Telegram MTProto  |  Nansen smart money  |  |
|  |  DexScreener     |  |  Reddit / CLIP  |  |  Alpha wallet votes  |  |
|  +--------+---------+  +--------+--------+  +-----------+----------+  |
|           +--------------------++--------------------------+           |
|                                |                                       |
|                    +-----------v-----------+                           |
|                    |   Redis Signal Bus    |                           |
|                    |   (pub/sub backbone)  |                           |
|                    +-----------+-----------+                           |
|                                |                                       |
|            +-------------------v--------------------+                 |
|            |          Signal Fusion Engine          |                 |
|            |  + SignalWeightLearner (EMA adaptive)  |                 |
|            +-------------------+--------------------+                 |
|                                |                                       |
|            +-------------------v--------------------+                 |
|            |       3-Model Ensemble Predictor       |                 |
|            |  BiLSTM-Transformer (18 features)      |                 |
|            |  + RegimeClassifier (XGBoost)          |                 |
|            |  + AnomalyScorer (IsolationForest)     |                 |
|            +-------------------+--------------------+                 |
|                                |                                       |
|              +-----------------v------------------+                   |
|              |           OVERSEER AGENT           |                   |
|              |     (LangGraph orchestration)      |                   |
|              +--+------------------+--------------+                   |
|          +------v----+  +----------v-----------+                      |
|          |  Scam     |  |  Trade Executor      |                      |
|          |  Slayer   |  |  MempoolMonitor fees |                      |
|          |  (5 lyr)  |  |  Kelly sizing        |                      |
|          +-----------+  +----------+-----------+                      |
|                         +----------v-----------+                      |
|                         |  Position Manager    |                      |
|                         |  Graduated trail stop|                      |
|                         |  Theta decay exit    |                      |
|                         |  Re-Entry Engine     |                      |
|                         +----------+-----------+                      |
|                         +----------v-----------+                      |
|                         |  Padre Terminal      |                      |
|                         |  (Playwright / DEX)  |                      |
|                         +--------------------  +                      |
+------------------------------------------------------------------------+
     |              |              |               |
  PostgreSQL      Redis         Dashboard      Prometheus
                                (Streamlit)    + Grafana
```

---

## Signal Pipeline

### 1. Data Ingestion
- **ChainAnalyst** â€” BirdEye volume anomalies, holder delta, bonding-curve velocity, DexScreener liquidity. Persistent WebSocket to pump.fun firehose with auto-reconnect
- **SentimentEngine** â€” Twitter (follower-weighted), Telegram (Telethon MTProto), Reddit, CLIP visual meme scoring
- **WalletTracker / SwarmIntelligence** â€” Nansen smart-money transaction monitoring with consensus voting

### 2. Redis Signal Bus
All ingestion workers publish to `spectrolite:{channel}` Redis channels. Downstream consumers subscribe without making redundant HTTP calls. Supports batch pipeline publishing for efficiency.

### 3. Signal Fusion
`SignalFusionEngine` merges all sub-signals into a `ScoredToken`:
- Applies adaptive per-source weights from `SignalWeightLearner`
- Runs 3-model ensemble prediction
- Computes `MemeScore` with weighted visual hype score and blended social velocity

### 4. Ensemble Prediction
```
pump_probability = w_lstm   * P_lstm
                 + w_regime * (P_lstm * regime_score)
                 + w_anomaly* (P_lstm * anomaly_score)
```
Weights are softmax-normalised Brier-score accuracy measured over the last 100 closed trades (equal 0.333 until 30 resolved).

### 5. Adaptive Feedback Loop
After each trade closes, `SignalFusionEngine.record_trade_outcome()` calls:
- `SignalWeightLearner.record_outcome()` â€” EMA updates per-source multipliers
- `EnsemblePredictor.record_outcome()` â€” updates per-model Brier-score accuracy trackers

---

## Execution Engine

### Position Sizing â€” Kelly Criterion
```
kelly_fraction = (win_rate * avg_win - loss_rate * avg_loss) / avg_win
position_size  = capital_bucket * min(kelly * 0.25 * mode_multiplier, 0.20)
```
- Quarter-Kelly for conservative sizing
- Requires 20+ trades in history; falls back to 3% flat during warm-up
- Hard cap: 20% of bucket | Hard floor: 1%

### Priority Fees â€” MempoolMonitor
- **Solana**: 75th percentile of last 20 `getRecentPrioritizationFees` RPC responses
- **EVM**: `eth_maxPriorityFeePerGas` + 25% safety buffer
- 30s cache per chain â€” one RPC round-trip per window, not per trade

### Trailing Stop Schedule
| Unrealised Gain | Stop Distance |
|---|---|
| 0% â€“ 50% | 20% |
| 50% â€“ 100% | 15% |
| 100% â€“ 200% | 10% |
| 200% â€“ 300% | 8% |
| 300% â€“ 500% | 6% |
| 500%+ | 4% |

### Theta Decay Exit
If a position has not reached **+15%** within **20 minutes** of entry it is force-closed regardless of current P&L. Eliminates capital tied up in stalled trades.

### Re-Entry Engine
After a partial exit at a take-profit target, `ReEntryEngine` monitors for a bounce:
- Dip of 25â€“35% from partial-exit price
- Volume z-score >= 1.5
- Scam probability < 35%
- Within 30 minutes of the original exit
- One re-entry attempt per position maximum

---

## Scam Shield

5-layer protection running on every candidate token:

```
Layer 1: Static Analysis     -> Slither (non-blocking) + GoPlus API
Layer 2: Dynamic Simulation  -> Foundry anvil fork buy+sell simulation
Layer 3: Social Scanner      -> Twitter rug/scam keyword search
Layer 4: MEV Detection       -> IsolationForest mempool anomaly scoring
Layer 5: LP Watcher          -> DexScreener 90s liquidity depth polling (post-entry)
```

**Hard-reject conditions (pre-entry):**
- Sell tax > 10% (honeypot confirmed)
- `MintFunction` or `BlacklistCapability` detected by Slither
- Credible Twitter sell warning from account > 10k followers (48h blacklist)
- MEV bundle probability > threshold
- Composite scam probability > 40%

**Emergency exit (post-entry, LP Watcher):**
- LP depth drops >= 15% within a 5-minute window â†’ immediate market exit via `emergency_callback`

---

## Prerequisites

| Dependency | Version | Notes |
|---|---|---|
| Docker | 24+ | Required for containerised deployment |
| Docker Compose | 2.20+ | Included with Docker Desktop |
| Python | 3.11+ | For local setup only |
| Foundry | latest | `curl -L https://foundry.paradigm.xyz \| bash` |
| Node.js | 18+ | Optional â€” Playwright local debug |

### API Keys Required

| Variable | Service | Purpose | Get it at |
|---|---|---|---|
| `OPENAI_API_KEY` | OpenAI | LLM narrative scoring | platform.openai.com |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot | Trade alerts & meme reports | @BotFather |
| `TELEGRAM_CHAT_ID` | Telegram | Your chat/channel ID | @userinfobot |
| `TELEGRAM_API_ID` | Telegram MTProto | Channel monitoring (Telethon) | my.telegram.org |
| `TELEGRAM_API_HASH` | Telegram MTProto | Channel monitoring (Telethon) | my.telegram.org |
| `TWITTER_BEARER_TOKEN` | Twitter/X API v2 | Sentiment + influencer scraping | developer.twitter.com |
| `NANSEN_API_KEY` | Nansen | Smart money wallet tracking | nansen.ai |
| `BIRDEYE_API_KEY` | BirdEye | Holder distribution, OHLCV | birdeye.so |
| `BLOXROUTE_AUTH_TOKEN` | bloXroute | MEV bundle detection | bloxroute.com |
| `GOPLUS_API_KEY` | GoPlus Labs | Contract security fallback | gopluslabs.io |
| `APIFY_API_TOKEN` | Apify | Twitter enhanced scraping actor | apify.com |
| `SMTP_USER` / `SMTP_PASSWORD` | Email | SOBRIETY autopsy PDF | Your email provider |
| `PADRE_CREDENTIALS_ENCRYPTED` | Padre Terminal | AES-encrypted DEX credentials | See setup |

> **Minimum viable config**: `SOLANA_RPC_URL` + `PADRE_CREDENTIALS_ENCRYPTED` + `WALLET_ENCRYPTION_KEY`. All other keys degrade gracefully when absent.

---

## Quick Start (Docker)

```bash
# 1. Clone the repository
git clone https://github.com/Reinasboo/Spectrolite.git
cd Spectrolite

# 2. Configure environment
cp .env.example .env
# Fill in required API keys in .env

# 3. Build and launch all services
docker-compose up --build --scale chain-worker=3 --scale sentiment-scout=2

# 4. Access dashboard
open http://localhost:8501

# 5. Access Grafana
open http://localhost:3000   # admin / degenadmin (change GRAFANA_PASSWORD in .env)
```

> **Note**: First build downloads Playwright Chromium (~130 MB) and PyTorch wheels. Allow 3-5 minutes.

---

## Manual Setup (Local)

```bash
# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate           # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install Playwright browsers
playwright install chromium

# 4. Install Foundry (honeypot simulation)
curl -L https://foundry.paradigm.xyz | bash && foundryup

# 5. Configure environment
cp .env.example .env

# 6. Initialise database
python -c "from degenerate_gambit.persistence import init_db; import asyncio; asyncio.run(init_db())"

# 7. Run
python -m degenerate_gambit run
```

---

## Environment Variables

```bash
# â”€â”€ Agent identity â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
AGENT_NAME=SPECTROLITE
AGENT_VERSION=2.0

# â”€â”€ Blockchain RPC â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
ETHEREUM_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
BASE_RPC_URL=https://base-mainnet.g.alchemy.com/v2/YOUR_KEY
BNB_RPC_URL=https://bsc-dataseed.binance.org/

# â”€â”€ Portfolio â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
INITIAL_CAPITAL_SOL=10.0
MAX_POSITION_PCT=0.15
DAILY_LOSS_LIMIT_PCT=0.25

# â”€â”€ Persistence â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
DATABASE_URL=postgresql://spectrolite:degenpassword@postgres:5432/degenerate_gambit
REDIS_URL=redis://:degenredis@redis:6379

# â”€â”€ Telegram (alerts) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# â”€â”€ Telegram (MTProto channel monitoring) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_api_hash

# â”€â”€ Padre Terminal (AES-256 encrypted credentials) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
PADRE_CREDENTIALS_ENCRYPTED=<base64_ciphertext>
WALLET_ENCRYPTION_KEY=<base64_fernet_key>
```

See [`.env.example`](.env.example) for the complete variable reference.

---

## CLI Commands

```bash
# Run the full autonomous agent
python -m degenerate_gambit run

# Run in specific service role (used by Docker Compose)
python -m degenerate_gambit run --mode overseer
python -m degenerate_gambit run --mode chain-worker
python -m degenerate_gambit run --mode sentiment-scout

# Historical backtest (includes transaction cost model)
python -m degenerate_gambit backtest --dataset pump_fun_2024
python -m degenerate_gambit backtest --dataset pump_fun_2024 --capital 50.0 --output results/backtest.json

# Monte Carlo stress simulation
python -m degenerate_gambit montecarlo --iterations 10000 --output results/mc_report.json

# Launch dashboard only
python -m degenerate_gambit dashboard --port 8501
```

---

## Dashboard

The Streamlit dashboard at `http://localhost:8501` provides:

| Tab | Contents |
|---|---|
| **Portfolio** | Real-time treemap heatmap + cumulative P&L chart |
| **Meme Reports** | Scrolling feed of post-trade degen voice summaries |
| **Risk Monitor** | Skull gauge (0-100% risk), mode indicator, drawdown meter |
| **Leaderboard** | Best meme tiers by win rate + streak tracking |

Auto-refreshes every **10 seconds**.

---

## Backtesting

Backtests replay historical pump events through the full signal stack with realistic transaction costs:

```bash
python -m degenerate_gambit backtest --dataset pump_fun_2024
```

### Transaction Cost Model

Every simulated trade deducts a realistic round-trip cost:

| Cost Component | Formula | Typical value |
|---|---|---|
| Entry slippage | `500 / sqrt(liquidity_usd)` | 0.3% at $25k liquidity |
| Exit slippage | Entry x 1.5 (thinner post-pump book) | 0.45% |
| DEX fee (round-trip) | 0.25% x 2 | 0.50% |
| Priority fee (round-trip) | 0.20% x 2 | 0.40% |
| **Total round-trip** | | **~1.65% at $25k liq** |

### Output Metrics
- Total return % (gross vs net after costs)
- Win rate overall + by meme score tier (Tier 1-4)
- Sharpe ratio
- Max drawdown
- Average hold time
- Scaled exit performance (2x / 5x targets)

---

## Monte Carlo Stress Tests

10,000 iterations across 4 adversarial scenarios:

| Scenario | Loss per event | Probability |
|---|---|---|
| `black_swan_dump` | -80% | 60% |
| `coordinated_rug_wave` | -70% | 50% |
| `liquidity_crisis` | -50% | 70% |
| `MEV_attack_barrage` | -10% per trade | Continuous |

```bash
python -m degenerate_gambit montecarlo --iterations 10000
```

**Output:** VaR 95%/99%, ruin probability, P10/P25/P50/P75/P90 distribution, survival rate per scenario.

---

## Personality Modes

| Mode | Trigger | Position Size | Notes |
|---|---|---|---|
| **STANDARD** | Default | 100% | Baseline Kelly sizing |
| **APE** | Velocity > 3 sigma | +50% | Ultra-aggressive entry |
| **SNIPER** | Accumulation phase | 10x leverage | Precise quiet entry |
| **ZEN** | Drawdown > 30% | 50% | Meme score >= 80 required |
| **CASINO** | Win streak >= 5 | 2x | Momentum continuation |
| **SOBRIETY** | Drawdown > 80% | **HALT** | Trading suspended, PDF autopsy sent |

---

## Deployment Scaling

```bash
# Production scale
docker-compose up -d --scale chain-worker=3 --scale sentiment-scout=2

docker-compose logs -f overseer
docker-compose restart overseer
docker-compose up -d --scale chain-worker=5
docker-compose down -v
```

---

## Monitoring

| Service | URL | Credentials |
|---|---|---|
| Streamlit Dashboard | http://localhost:8501 | None |
| Prometheus | http://localhost:9090 | None |
| Grafana | http://localhost:3000 | admin / GRAFANA_PASSWORD |

**Key Prometheus metrics:**

| Metric | Description |
|---|---|
| `spectrolite_trades_total` | Trade count by outcome label |
| `spectrolite_portfolio_value` | Current portfolio value in USD |
| `spectrolite_scam_blocked_total` | Tokens hard-rejected by Scam Shield |
| `spectrolite_pump_prediction_score` | Ensemble prediction histogram |
| `spectrolite_personality_mode` | Current mode enum value |
| `spectrolite_win_streak` | Consecutive win count |
| `spectrolite_kelly_fraction` | Rolling Kelly sizing fraction |
| `spectrolite_lp_emergency_exits` | LP watcher-triggered emergency exits |

---

## Project Structure

```
Spectrolite/
â”œâ”€â”€ degenerate_gambit/
â”‚   â”œâ”€â”€ __init__.py
â”‚   â”œâ”€â”€ __main__.py                  # CLI entry point
â”‚   â”œâ”€â”€ agent.py                     # Dependency injection + shared HTTP pool
â”‚   â”œâ”€â”€ config.py                    # Pydantic Settings
â”‚   â”‚
â”‚   â”œâ”€â”€ models/
â”‚   â”‚   â”œâ”€â”€ types.py                 # Core dataclasses & enums
â”‚   â”‚   â”œâ”€â”€ pump_predictor.py        # BiLSTM-Transformer (18 features)
â”‚   â”‚   â””â”€â”€ ensemble.py              # 3-model ensemble + OutcomeTracker   [NEW]
â”‚   â”‚
â”‚   â”œâ”€â”€ analysis/
â”‚   â”‚   â”œâ”€â”€ signal_fusion.py         # Multi-signal merge + ensemble wiring
â”‚   â”‚   â”œâ”€â”€ signal_weight_learner.py # EMA adaptive per-source weights      [NEW]
â”‚   â”‚   â”œâ”€â”€ sentiment_engine.py      # Vibe Engine: Twitter/TG/Reddit/CLIP
â”‚   â”‚   â”œâ”€â”€ chain_analyst.py         # On-chain data + persistent WS
â”‚   â”‚   â”œâ”€â”€ arb_detector.py          # Cross-chain arbitrage
â”‚   â”‚   â””â”€â”€ redis_signal_bus.py      # Pub/sub signal backbone              [NEW]
â”‚   â”‚
â”‚   â”œâ”€â”€ wallet/
â”‚   â”‚   â”œâ”€â”€ wallet_tracker.py        # Alpha wallet surveillance
â”‚   â”‚   â””â”€â”€ swarm_intelligence.py    # Consensus voting
â”‚   â”‚
â”‚   â”œâ”€â”€ scam_shield/
â”‚   â”‚   â”œâ”€â”€ static_analyzer.py       # Non-blocking Slither + GoPlus
â”‚   â”‚   â”œâ”€â”€ dynamic_simulator.py     # Foundry honeypot simulation
â”‚   â”‚   â”œâ”€â”€ social_scanner.py        # Twitter rug scan
â”‚   â”‚   â”œâ”€â”€ mev_detector.py          # IsolationForest MEV detection
â”‚   â”‚   â”œâ”€â”€ lp_watcher.py            # Real-time LP depth monitoring         [NEW]
â”‚   â”‚   â””â”€â”€ scam_slayer.py           # 5-layer orchestrator
â”‚   â”‚
â”‚   â”œâ”€â”€ gamification/
â”‚   â”‚   â”œâ”€â”€ mode_manager.py          # Personality modes
â”‚   â”‚   â”œâ”€â”€ level_system.py          # Level progression
â”‚   â”‚   â””â”€â”€ meme_reporter.py         # Post-trade degen reports
â”‚   â”‚
â”‚   â”œâ”€â”€ execution/
â”‚   â”‚   â”œâ”€â”€ padre_session.py         # Playwright DEX session
â”‚   â”‚   â”œâ”€â”€ trade_executor.py        # Kelly sizing + MempoolMonitor
â”‚   â”‚   â”œâ”€â”€ position_manager.py      # Graduated trailing stop + theta exit
â”‚   â”‚   â””â”€â”€ reentry_engine.py        # Bounce re-entry logic                 [NEW]
â”‚   â”‚
â”‚   â”œâ”€â”€ agents/
â”‚   â”‚   â””â”€â”€ overseer.py              # LangGraph main orchestrator loop
â”‚   â”‚
â”‚   â”œâ”€â”€ notifications/
â”‚   â”‚   â””â”€â”€ __init__.py              # Telegram alerts / voice / PDF autopsy
â”‚   â”‚
â”‚   â”œâ”€â”€ persistence/
â”‚   â”‚   â””â”€â”€ __init__.py              # SQLAlchemy + TradeLogger
â”‚   â”‚
â”‚   â””â”€â”€ backtest/
â”‚       â”œâ”€â”€ backtester.py            # Historical simulation + cost model
â”‚       â””â”€â”€ monte_carlo.py           # Adversarial stress testing
â”‚
â”œâ”€â”€ dashboard/
â”‚   â””â”€â”€ app.py                       # Streamlit dashboard
â”œâ”€â”€ docker/
â”‚   â”œâ”€â”€ prometheus.yml
â”‚   â””â”€â”€ grafana/provisioning/datasources/prometheus.yml
â”œâ”€â”€ config.yaml                      # Master configuration
â”œâ”€â”€ .env.example                     # Environment variable template
â”œâ”€â”€ requirements.txt                 # Python dependencies
â”œâ”€â”€ Dockerfile                       # Multi-stage build
â”œâ”€â”€ docker-compose.yml               # Full stack orchestration
â”œâ”€â”€ .gitignore
â””â”€â”€ .dockerignore
```

---

## Ethical Guardrails & Legal Notice

> **IMPORTANT â€” READ BEFORE DEPLOYING**

This software is provided **strictly for educational and research purposes**. By using SPECTROLITE / Degenerate Gambit, you acknowledge and agree:

1. **No Financial Advice**: This system does not constitute financial advice. All trading decisions are speculative and carry significant risk of total capital loss.
2. **Memecoin Risk**: Memecoin markets are highly volatile, largely unregulated, and subject to manipulation. You may lose 100% of invested capital.
3. **Regulatory Compliance**: You are solely responsible for ensuring all trading activities comply with the laws and regulations of your jurisdiction.
4. **No Warranty**: This software is provided "as is" without warranty of any kind. The authors accept no liability for financial losses or any other damages.
5. **API Terms of Service**: Use of third-party APIs must comply with each provider's terms. Automated access may violate those terms.
6. **Operator Responsibility**: Any deployment is the sole responsibility of the operator. You must implement risk controls beyond those built in.
7. **SOBRIETY MODE is not a safety net**: The -80% drawdown trigger represents catastrophic capital loss. This system is not a substitute for human oversight.

**USE ENTIRELY AT YOUR OWN RISK. THE AUTHORS BEAR NO RESPONSIBILITY FOR ANY OUTCOME.**

---

*SPECTROLITE / Degenerate Gambit v2.0 â€” Built to go stupid. Equipped to survive it.*
