"""
LSTM + Transformer Pump Predictor — 5-15 minute horizon.
PyTorch implementation of the AI Prediction Core for Spectrolite.

v2: Upgraded to 18 input features + 2-layer Transformer encoder on top of BiLSTM.

Inputs (18 features):
  [price_velocity, volume_z_score, holder_delta, social_spike_index,
   meme_score, liquidity_ratio, wash_trade_ratio, bonding_curve_velocity,
   insider_wallet_pre_position, order_book_bid_wall_ratio,
   rsi_5m, rsi_15m, token_age_minutes, dev_wallet_sell_pct,
   top_10_holder_concentration, cross_chain_arb_spread,
   telegram_mention_velocity, volume_acceleration]

Output: P(pump_within_15min), confidence_interval, suggested_entry_price
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

logger = logging.getLogger(__name__)

_MODEL_PATH = Path(__file__).parent.parent.parent / "models" / "pump_predictor.pt"

INPUT_FEATURES = [
    "price_velocity",
    "volume_z_score",
    "holder_delta",
    "social_spike_index",
    "meme_score",
    "liquidity_ratio",
    # ── v2 additions ────────────────────────────────
    "wash_trade_ratio",
    "bonding_curve_velocity",
    "insider_wallet_pre_position",
    "order_book_bid_wall_ratio",
    "rsi_5m",
    "rsi_15m",
    "token_age_minutes",
    "dev_wallet_sell_pct",
    "top_10_holder_concentration",
    "cross_chain_arb_spread",
    "telegram_mention_velocity",
    "volume_acceleration",
]
INPUT_SIZE = len(INPUT_FEATURES)      # 18
HIDDEN_SIZE = 128
NUM_LAYERS = 2
DROPOUT = 0.30
SEQ_LEN = 20                          # 20 × 15s ticks = 5 min context
CONFIDENCE_THRESHOLD = 0.72

# Transformer encoder parameters
TRANSFORMER_HEADS = 4
TRANSFORMER_FF_DIM = 256
TRANSFORMER_LAYERS = 2
TRANSFORMER_DROPOUT = 0.10


class PositionalEncoding(nn.Module):
    """Standard sinusoidal positional encoding for the Transformer."""

    def __init__(self, d_model: int, max_len: int = 100, dropout: float = 0.10) -> None:
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)   # (1, max_len, d_model)
        self.register_buffer("pe", pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.pe[:, : x.size(1), :]  # type: ignore[index]
        return self.dropout(x)


class PumpPredictor(nn.Module):
    """
    BiLSTM → Positional Encoding → Transformer Encoder → Output Heads.

    Architecture:
        Input projection  : Linear(18 → hidden*2)
        BiLSTM            : 2 layers, 128 hidden (→ 256 bidirectional)
        Positional Enc    : sinusoidal
        Transformer Enc   : 2 layers, 4 heads, FF=256
        Mean-pool         : across sequence dimension
        Output heads      : pump_prob / confidence_interval / entry_multiplier
    """

    def __init__(
        self,
        input_size: int = INPUT_SIZE,
        hidden_size: int = HIDDEN_SIZE,
        num_layers: int = NUM_LAYERS,
        dropout: float = DROPOUT,
    ) -> None:
        super().__init__()
        self.d_model = hidden_size * 2   # 256 (bidirectional)

        # Input projection to d_model
        self.input_proj = nn.Linear(input_size, self.d_model)

        # Bidirectional LSTM
        self.lstm = nn.LSTM(
            input_size=self.d_model,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
            bidirectional=True,
        )

        # Positional encoding before Transformer
        self.pos_enc = PositionalEncoding(self.d_model, max_len=SEQ_LEN + 10, dropout=TRANSFORMER_DROPOUT)

        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=self.d_model,
            nhead=TRANSFORMER_HEADS,
            dim_feedforward=TRANSFORMER_FF_DIM,
            dropout=TRANSFORMER_DROPOUT,
            batch_first=True,
            norm_first=True,    # pre-norm for training stability
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=TRANSFORMER_LAYERS)

        # Output heads
        self.pump_head = nn.Sequential(
            nn.Linear(self.d_model, 64),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )
        self.confidence_head = nn.Sequential(
            nn.Linear(self.d_model, 32),
            nn.GELU(),
            nn.Linear(32, 2),
            nn.Sigmoid(),
        )
        self.entry_head = nn.Sequential(
            nn.Linear(self.d_model, 32),
            nn.GELU(),
            nn.Linear(32, 1),
            nn.Softplus(),
        )

    def forward(
        self,
        x: torch.Tensor,                      # (batch, seq_len, input_size)
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        # Project input features to d_model
        x = self.input_proj(x)                # (batch, seq_len, d_model)

        # BiLSTM
        lstm_out, _ = self.lstm(x)            # (batch, seq_len, d_model)

        # Add positional encoding
        enc_in = self.pos_enc(lstm_out)       # (batch, seq_len, d_model)

        # Transformer encoder (multi-head self-attention over sequence)
        enc_out = self.transformer(enc_in)    # (batch, seq_len, d_model)

        # Mean pooling over sequence dimension for stable gradient flow
        context = enc_out.mean(dim=1)         # (batch, d_model)

        pump_prob = self.pump_head(context)
        confidence = self.confidence_head(context)
        entry_mult = self.entry_head(context)

        return pump_prob, confidence, entry_mult


class PumpPredictorService:
    """
    Thin wrapper around PumpPredictor that handles load/save,
    online weight updates, and inference.
    """

    def __init__(self, model_path: Optional[Path] = None) -> None:
        self.model = PumpPredictor()
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self._path = model_path or _MODEL_PATH
        self._load_if_exists()
        self.model.eval()

    def _load_if_exists(self) -> None:
        if self._path.exists():
            state = torch.load(self._path, map_location=self.device)
            self.model.load_state_dict(state)
            logger.info(f"PumpPredictor weights loaded from {self._path}")
        else:
            logger.warning("No pre-trained weights found. Using random init.")

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(self.model.state_dict(), self._path)
        logger.info(f"PumpPredictor weights saved to {self._path}")

    @torch.no_grad()
    def predict(
        self,
        feature_sequence: np.ndarray,   # shape (seq_len, input_size) OR (input_size,) → auto-padded
        current_price: float = 1.0,
    ) -> tuple[float, tuple[float, float], float]:
        """
        Returns:
            pump_probability   : float
            confidence_interval: (lower, upper)
            suggested_entry    : absolute price suggestion
        """
        if feature_sequence.ndim == 1:
            # Pad single tick to full sequence
            feature_sequence = np.tile(feature_sequence, (SEQ_LEN, 1))

        if feature_sequence.shape[0] < SEQ_LEN:
            pad_len = SEQ_LEN - feature_sequence.shape[0]
            feature_sequence = np.vstack([
                np.zeros((pad_len, feature_sequence.shape[1])),
                feature_sequence,
            ])

        x = torch.FloatTensor(feature_sequence[-SEQ_LEN:]).unsqueeze(0).to(self.device)
        pump_prob, confidence, entry_mult = self.model(x)

        p = pump_prob.item()
        ci = (confidence[0, 0].item(), confidence[0, 1].item())
        entry = current_price * entry_mult.item()

        return p, ci, entry

    def online_update(
        self,
        feature_sequences: list[np.ndarray],
        labels: list[float],
        learning_rate: float = 1e-4,
        epochs: int = 5,
    ) -> float:
        """
        Incremental (online) weight update from recent trade outcomes.
        Called weekly or after a batch of closed positions.
        Returns average training loss.
        """
        self.model.train()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=learning_rate)
        criterion = nn.BCELoss()

        X = np.stack([
            s[-SEQ_LEN:] if len(s) >= SEQ_LEN else
            np.vstack([np.zeros((SEQ_LEN - len(s), INPUT_SIZE)), s])
            for s in feature_sequences
        ])
        y = np.array(labels, dtype=np.float32)

        dataset = TensorDataset(
            torch.FloatTensor(X),
            torch.FloatTensor(y).unsqueeze(1),
        )
        loader = DataLoader(dataset, batch_size=32, shuffle=True)

        total_loss = 0.0
        for _ in range(epochs):
            for xb, yb in loader:
                xb, yb = xb.to(self.device), yb.to(self.device)
                optimizer.zero_grad()
                pred, _, _ = self.model(xb)
                loss = criterion(pred, yb)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()

        avg_loss = total_loss / (len(loader) * epochs)
        self.model.eval()
        self.save()
        logger.info(f"Online update complete. Avg loss: {avg_loss:.4f}")
        return avg_loss

    def build_feature_vector(
        self,
        # ── Original 6 features ────────────────────────────────────────────
        price_velocity: float,
        volume_z_score: float,
        holder_delta: float,
        social_spike_index: float,
        meme_score: float,
        liquidity_ratio: float,
        # ── v2: 12 additional features ─────────────────────────────────────
        wash_trade_ratio: float = 0.0,
        bonding_curve_velocity: float = 0.0,
        insider_wallet_pre_position: float = 0.0,
        order_book_bid_wall_ratio: float = 0.5,
        rsi_5m: float = 50.0,
        rsi_15m: float = 50.0,
        token_age_minutes: float = 60.0,
        dev_wallet_sell_pct: float = 0.0,
        top_10_holder_concentration: float = 0.5,
        cross_chain_arb_spread: float = 0.0,
        telegram_mention_velocity: float = 0.0,
        volume_acceleration: float = 0.0,
    ) -> np.ndarray:
        """Construct a normalised 18-feature single-tick vector."""
        raw = np.array([
            price_velocity,
            volume_z_score,
            holder_delta,
            social_spike_index,
            meme_score / 100.0,                   # normalise 0-100 → 0-1
            liquidity_ratio,
            # ── v2 features (all pre-normalised to ~[-1, 1] or [0, 1]) ────
            wash_trade_ratio,
            bonding_curve_velocity,
            insider_wallet_pre_position,
            order_book_bid_wall_ratio,
            (rsi_5m - 50.0) / 50.0,              # centre RSI around 0
            (rsi_15m - 50.0) / 50.0,
            min(token_age_minutes / 1440.0, 1.0), # normalise to days, cap at 1
            dev_wallet_sell_pct,
            top_10_holder_concentration,
            cross_chain_arb_spread,
            min(telegram_mention_velocity / 100.0, 1.0),
            volume_acceleration,
        ], dtype=np.float32)
        return np.clip(raw, -10.0, 10.0)
