# SPECTROLITE — Degenerate Gambit v2.0

> *"I am not a bot. I am a force of nature with a terrible risk appetite and beautiful pattern recognition."*

```
AGENT IDENTITY     : SPECTROLITE
CODENAME           : DEGENERATE GAMBIT
VERSION            : 2.0
CLASSIFICATION     : Autonomous AI Memecoin Trading Agent
STACK              : Python · PyTorch · CrewAI · LangGraph · Playwright · Streamlit
```

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Quick Start (Docker)](#quick-start-docker)
5. [Manual Setup (Local)](#manual-setup-local)
6. [Environment Variables](#environment-variables)
7. [CLI Commands](#cli-commands)
8. [Dashboard](#dashboard)
9. [Backtesting](#backtesting)
10. [Monte Carlo Stress Tests](#monte-carlo-stress-tests)
11. [Personality Modes](#personality-modes)
12. [Scam Shield](#scam-shield)
13. [Deployment Scaling](#deployment-scaling)
14. [Monitoring](#monitoring)
15. [Ethical Guardrails & Legal Notice](#ethical-guardrails--legal-notice)

---

## Overview

**SPECTROLITE** is an autonomous, multi-agent AI system designed to identify and trade high-potential memecoin opportunities across Solana, Ethereum, Base, and BNB Chain. It combines:

- **BiLSTM neural pump prediction** — 5-15 minute horizon probability scoring
- **Vibe Engine** — multi-platform sentiment mining (Twitter, Reddit, on-chain narrative)
- **Scam Shield** — 4-layer rug protection (static analysis, dynamic simulation, social scanning, MEV detection)
- **Swarm Intelligence** — consensus-driven alpha wallet surveillance
- **Gamification Layer** — adaptive personality modes (APE / SNIPER / ZEN / CASINO / SOBRIETY)
- **Padre Terminal** — headless Playwright session for DEX execution
- **Real-time Streamlit dashboard** with degen P&L heatmap and meme report feed

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        SPECTROLITE v2.0                         │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Chain       │  │  Sentiment   │  │  Wallet Tracker      │  │
│  │  Analyst     │  │  Engine      │  │  (Swarm Intelligence)│  │
│  │  ×3 workers  │  │  ×2 scouts   │  │                      │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         └─────────────────┴──────────────────────┘             │
│                            │                                    │
│                   ┌────────▼────────┐                          │
│                   │  Signal Fusion  │                          │
│                   │  Engine         │                          │
│                   └────────┬────────┘                          │
│                            │                                    │
│              ┌─────────────▼──────────────┐                    │
│              │      OVERSEER AGENT        │                    │
│              │  (OverseerAgent / CrewAI)  │                    │
│              └──┬───────────┬─────────────┘                    │
│           ┌─────▼──┐  ┌────▼──────────┐                       │
│           │ Scam   │  │ PumpPredictor │                       │
│           │ Slayer │  │ (BiLSTM)      │                       │
│           └─────┬──┘  └────┬──────────┘                       │
│                 └────┬─────┘                                   │
│              ┌───────▼────────┐                                │
│              │ Trade Executor │                                │
│              │ + Position Mgr │                                │
│              └───────┬────────┘                                │
│              ┌───────▼────────┐                                │
│              │ Padre Terminal │                                │
│              │ (Playwright)   │                                │
│              └────────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
     │              │              │               │
  PostgreSQL      Redis         Dashboard      Prometheus
                                (Streamlit)    + Grafana
```

---

## Prerequisites

| Dependency | Version | Notes |
|---|---|---|
| Docker | 24+ | Required for containerized deployment |
| Docker Compose | 2.20+ | Included with Docker Desktop |
| Python | 3.11+ | For local setup only |
| Foundry | latest | `curl -L https://foundry.paradigm.xyz \| bash` — required for honeypot simulation |
| Node.js | 18+ | Optional — for Playwright local debug |

### API Keys Required

| Service | Purpose | Get it at |
|---|---|---|
| `OPENAI_API_KEY` | LLM narrative scoring | platform.openai.com |
| `TELEGRAM_BOT_TOKEN` | Trade alerts & meme reports | @BotFather on Telegram |
| `TELEGRAM_CHAT_ID` | Your chat/channel ID | @userinfobot |
| `TWITTER_BEARER_TOKEN` | Sentiment scraping | developer.twitter.com |
| `NANSEN_API_KEY` | Smart money wallet tracking | nansen.ai |
| `BIRDEYE_API_KEY` | Holder distribution data | birdeye.so |
| `BLOXROUTE_AUTH_TOKEN` | MEV bundle detection | bloxroute.com |
| `GOPLUS_API_KEY` | Contract security fallback | gopluslabs.io |
| `APIFY_API_TOKEN` | Twitter enhanced scraping | apify.com |
| `SMTP_USER` / `SMTP_PASSWORD` | SOBRIETY autopsy email | Your email provider |
| `PADRE_CREDENTIALS_ENCRYPTED` | Padre Terminal access | AES-encrypted (see setup) |

---

## Quick Start (Docker)

```bash
# 1. Clone / unzip the project
cd degenerate-gambit

# 2. Configure environment
cp .env.example .env
# Fill in ALL required API keys in .env

# 3. Build and launch all services
docker-compose up --build --scale chain-worker=3 --scale sentiment-scout=2

# 4. Access dashboard
open http://localhost:8501

# 5. Access Grafana monitoring
open http://localhost:3000  # admin / degenadmin (change in .env)
```

> **Note**: First build downloads Playwright Chromium (~130 MB) and PyTorch. Allow 3-5 minutes.

---

## Manual Setup (Local)

```bash
# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
.venv\Scripts\activate          # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install Playwright browsers
playwright install chromium

# 4. Install Foundry (for honeypot simulation)
curl -L https://foundry.paradigm.xyz | bash
foundryup

# 5. Configure environment
cp .env.example .env
# Edit .env with your credentials

# 6. Initialize database
python -c "from degenerate_gambit.persistence import init_db; import asyncio; asyncio.run(init_db())"

# 7. Run the agent
python -m degenerate_gambit run
```

---

## Environment Variables

Copy `.env.example` to `.env` and populate all values. Key variables:

```bash
# ── Agent identity ─────────────────────────────────────
AGENT_NAME=SPECTROLITE
AGENT_VERSION=2.0

# ── Blockchain ─────────────────────────────────────────
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
ETHEREUM_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
BASE_RPC_URL=https://base-mainnet.g.alchemy.com/v2/YOUR_KEY

# ── Portfolio ─────────────────────────────────────────
INITIAL_CAPITAL_SOL=10.0
MAX_POSITION_PCT=0.15
DAILY_LOSS_LIMIT_PCT=0.25

# ── Database ──────────────────────────────────────────
DATABASE_URL=postgresql://spectrolite:degenpassword@postgres:5432/degenerate_gambit
REDIS_URL=redis://:degenredis@redis:6379

# ── Père Terminal (AES encrypted) ─────────────────────
PADRE_CREDENTIALS_ENCRYPTED=<your_encrypted_blob>
PADRE_ENCRYPTION_KEY=<your_fernet_key>
PADRE_TOTP_SECRET=<your_2fa_secret>
```

See `.env.example` for the full list.

---

## CLI Commands

```bash
# Run the full autonomous agent
python -m degenerate_gambit run

# Run in specific role (used by Docker services)
python -m degenerate_gambit run --mode overseer
python -m degenerate_gambit run --mode chain-worker
python -m degenerate_gambit run --mode sentiment-scout

# Historical backtest
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

Backtests replay historical pump events through the full signal stack:

```bash
python -m degenerate_gambit backtest --dataset pump_fun_2024
```

**Output metrics:**
- Total return %
- Win rate overall + by meme score tier (Tier 1-4)
- Sharpe ratio
- Max drawdown
- Average hold time
- Scaled exit performance (2x / 5x targets)

Results saved as JSON to `results/` and displayed in terminal.

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

**Output:**
- VaR 95% / VaR 99%
- Ruin probability (portfolio → 0)
- Percentile distribution (P10/P25/P50/P75/P90)
- Survival rate per scenario

---

## Personality Modes

SPECTROLITE adapts its behavior based on market conditions and portfolio state:

| Mode | Trigger | Position Size | Notes |
|---|---|---|---|
| **STANDARD** | Default | 100% | Baseline behavior |
| **APE** | Velocity > 3σ | +50% | Ultra-aggressive entry |
| **SNIPER** | Accumulation phase | 10× leverage | Precise quiet entry |
| **ZEN** | Drawdown > 30% | 50% | Meme score ≥ 80 required |
| **CASINO** | Win streak ≥ 5 | 2× | Momentum continuation |
| **SOBRIETY** | Drawdown > 80% | **HALT** | Trading suspended, autopsy generated |

**SOBRIETY MODE** sends a full PDF autopsy report via email and locks all new positions until manual override.

---

## Scam Shield

4-layer protection running on every candidate token:

```
Layer 1: Static Analysis  → Slither + GoPlus API
Layer 2: Dynamic Sim      → Foundry anvil fork buy+sell simulation
Layer 3: Social Scanner   → Twitter rug/scam keyword search
Layer 4: MEV Detection    → IsolationForest mempool anomaly detection
```

Any of the following **hard-rejects** a token:
- Sell tax > 10% (honeypot confirmed)
- `MintFunction` or `BlacklistCapability` detected
- Credible Twitter warning from account > 10k followers (48h blacklist)
- MEV bundle probability > threshold
- Composite scam probability > 40%

---

## Deployment Scaling

```bash
# Production scale (as specified)
docker-compose up -d --scale chain-worker=3 --scale sentiment-scout=2

# Check running services
docker-compose ps

# View agent logs
docker-compose logs -f overseer
docker-compose logs -f chain-worker

# Restart a service
docker-compose restart overseer

# Scale up chain workers dynamically
docker-compose up -d --scale chain-worker=5

# Full teardown
docker-compose down -v
```

---

## Monitoring

| Service | URL | Credentials |
|---|---|---|
| Streamlit Dashboard | http://localhost:8501 | None (public) |
| Prometheus | http://localhost:9090 | None |
| Grafana | http://localhost:3000 | admin / `GRAFANA_PASSWORD` |

**Key Prometheus metrics exposed by agents:**
- `spectrolite_trades_total` — trade count by outcome
- `spectrolite_portfolio_value` — current portfolio value (SOL)
- `spectrolite_scam_blocked_total` — tokens blocked by Scam Shield
- `spectrolite_pump_prediction_score` — BiLSTM prediction histogram
- `spectrolite_personality_mode` — current mode enum
- `spectrolite_win_streak` — current win streak

---

## Project Structure

```
degenerate-gambit/
├── degenerate_gambit/
│   ├── __init__.py
│   ├── __main__.py          # CLI entry point
│   ├── agent.py             # Dependency injection wiring
│   ├── config.py            # Pydantic Settings
│   ├── models/
│   │   ├── types.py         # Core dataclasses & enums
│   │   └── pump_predictor.py  # BiLSTM neural model
│   ├── analysis/
│   │   ├── signal_fusion.py   # Multi-signal merge
│   │   ├── sentiment_engine.py  # Vibe Engine
│   │   ├── chain_analyst.py   # On-chain data
│   │   └── arb_detector.py    # Cross-chain arbitrage
│   ├── wallet/
│   │   ├── wallet_tracker.py  # Alpha wallet surveillance
│   │   └── swarm_intelligence.py  # Consensus voting
│   ├── scam_shield/
│   │   ├── static_analyzer.py   # Slither + GoPlus
│   │   ├── dynamic_simulator.py # Foundry honeypot sim
│   │   ├── social_scanner.py    # Twitter rug scan
│   │   ├── mev_detector.py      # IsolationForest
│   │   └── scam_slayer.py       # Orchestrator
│   ├── gamification/
│   │   ├── mode_manager.py      # Personality modes
│   │   ├── level_system.py      # Level progression
│   │   └── meme_reporter.py     # Post-trade reports
│   ├── execution/
│   │   ├── padre_session.py     # Playwright DEX session
│   │   ├── trade_executor.py    # Full execution pipeline
│   │   └── position_manager.py  # Trailing stops / exits
│   ├── agents/
│   │   └── overseer.py          # Main orchestrator loop
│   ├── notifications/
│   │   └── __init__.py          # Telegram / voice / PDF
│   ├── persistence/
│   │   └── __init__.py          # SQLAlchemy + TradeLogger
│   └── backtest/
│       ├── backtester.py        # Historical simulation
│       └── monte_carlo.py       # Stress testing
├── dashboard/
│   └── app.py               # Streamlit dashboard
├── docker/
│   ├── prometheus.yml
│   └── grafana/
│       └── provisioning/
│           └── datasources/
│               └── prometheus.yml
├── config.yaml              # Master configuration
├── .env.example             # Environment template
├── requirements.txt         # Python dependencies
├── Dockerfile               # Multi-stage build
├── docker-compose.yml       # Full stack orchestration
└── .dockerignore
```

---

## Ethical Guardrails & Legal Notice

> **IMPORTANT — READ BEFORE DEPLOYING**

This software is provided **strictly for educational and research purposes**. By using SPECTROLITE / Degenerate Gambit, you acknowledge and agree:

1. **No Financial Advice**: This system does not constitute financial advice. All trading decisions made autonomously by this agent are speculative and carry significant risk of total capital loss.

2. **Memecoin Risk**: Memecoin markets are highly volatile, largely unregulated, and subject to manipulation. You may lose 100% of invested capital.

3. **Regulatory Compliance**: You are solely responsible for ensuring all trading activities comply with the laws and regulations of your jurisdiction. Automated trading may be restricted or prohibited in your region.

4. **No Warranty**: This software is provided "as is" without warranty of any kind. The authors accept no liability for financial losses, regulatory penalties, or any other damages arising from use of this system.

5. **API Terms of Service**: Use of third-party APIs (Twitter, Nansen, Birdeye, etc.) must comply with each provider's terms of service. Scraping or automated access may violate these terms.

6. **Operator Responsibility**: Any deployment of this system is the sole responsibility of the operator. You must implement appropriate risk controls beyond those built into the system.

7. **SOBRIETY MODE is not a safety net**: The -80% drawdown trigger for SOBRIETY MODE represents catastrophic capital loss. This system is not a substitute for proper position sizing, risk management, and oversight.

**USE ENTIRELY AT YOUR OWN RISK. THE AUTHORS BEAR NO RESPONSIBILITY FOR ANY OUTCOME.**

---

*SPECTROLITE / Degenerate Gambit v2.0 — Built to go stupid. Equipped to survive it.*
