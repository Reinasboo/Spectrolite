# ============================================================
# SPECTROLITE — Degenerate Gambit v2.0
# Dockerfile — Multi-stage build
# ============================================================

# ── Stage 1: Builder ──────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    git \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Foundry (anvil) for honeypot simulation
RUN curl -L https://foundry.paradigm.xyz | bash && \
    /root/.foundry/bin/foundryup || true

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium --with-deps

# ── Stage 2: Runtime ─────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libxkbcommon0 \
    libasound2 \
    espeak \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /root/.foundry /root/.foundry
COPY --from=builder /root/.cache/ms-playwright /root/.cache/ms-playwright

# Copy application code
COPY . .

# Add foundry to PATH
ENV PATH="/root/.foundry/bin:${PATH}"

# Create directories
RUN mkdir -p /app/results /app/data /app/models /app/logs

# Non-root user for security
RUN adduser --disabled-password --gecos "" spectrolite && \
    chown -R spectrolite:spectrolite /app
USER spectrolite

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import degenerate_gambit; print('OK')" || exit 1

EXPOSE 8501

CMD ["python", "-m", "degenerate_gambit", "run"]
