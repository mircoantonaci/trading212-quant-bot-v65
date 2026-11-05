#!/usr/bin/env python3
"""
Bot eToro 100€ (Smart Grid a 4 Cartucce da 25€ - Solo Azioni/ETF Reali Leva X1).
Compatibile con le API Ufficiali di eToro (Demo e Real).
"""

import json
import os
import uuid
import urllib.request
from pathlib import Path

ETORO_BASE_URL = "https://public-api.etoro.com"
CONFIG_PATH = Path(__file__).parent / "etoro_config.json"

# Paniere "Scudo + Big Tech" (Solo Azioni/ETF reali, Leva X1 = Zero commissioni notturne)
WATCHLIST_TICKERS = [
    "NVDA",  # NVIDIA
    "MSFT",  # Microsoft
    "AAPL",  # Apple
    "AMZN",  # Amazon
    "GOOG",  # Alphabet (Google)
    "META",  # Meta Platforms
    "SPY",   # ETF S&P 500
]


class EtoroClient:
    """Client ufficiale per le Public API di eToro."""

    def __init__(self, api_key: str, user_key: str, mode: str = "demo"):
        self.api_key = api_key
        self.user_key = user_key
        self.mode = mode.lower()  # "demo" oppure "real"

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "x-user-key": self.user_key,
            "x-request-id": str(uuid.uuid4()),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def get_portfolio(self) -> dict:
        env_path = "demo" if self.mode == "demo" else "real"
        url = f"{ETORO_BASE_URL}/api/v1/trading/info/{env_path}/portfolio"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def open_position_by_amount(
        self,
        instrument_id: int,
        amount_usd: float,
        take_profit_pct: float = 0.04,
    ) -> dict:
        """
        Apre una posizione in Leva X1 (senza leva = zero costi overnight)
        con Take Profit automatico (+4%).
        """
        env_path = "demo" if self.mode == "demo" else "real"
        url = f"{ETORO_BASE_URL}/api/v2/trading/execution/{env_path}/orders"
        payload = {
            "instrumentId": instrument_id,
            "isBuy": True,
            "leverage": 1,
            "amount": amount_usd,
            "takeProfitPct": take_profit_pct,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))


class SmartPlan100Eur:
    """
    Piano di Gestione per 100,00€ Reali su eToro:
    - 4 Cartucce da 25,00€ ciascuna (Leva X1, zero costi notturni).
    - Cartuccia 1 (25€): Base Scudo su ETF S&P 500 (SPY) o prima Big Tech in ipervenduto.
    - Cartucce 2, 3, 4 (25€ cad.): Rotazione Swing su NVDA, AAPL, MSFT, AMZN, GOOG, META
      quando RSI scende sotto 36 (calo del -3% / -4%), con vendita automatica a +4% (+1,00€ netto a colpo).
    """

    def __init__(self):
        self.total_budget_eur = 100.0
        self.cartridges = [
            {"id": 1, "size_eur": 25.0, "role": "Base / 1° Ingresso RSI < 38", "target_profit_pct": 4.0},
            {"id": 2, "size_eur": 25.0, "role": "2° Ingresso Swing / Mediazione -3%", "target_profit_pct": 4.0},
            {"id": 3, "size_eur": 25.0, "role": "3° Ingresso Opportunità Big Tech", "target_profit_pct": 4.0},
            {"id": 4, "size_eur": 25.0, "role": "Riserva Strategica per Cali Forti", "target_profit_pct": 4.5},
        ]


if __name__ == "__main__":
    plan = SmartPlan100Eur()
    print("Piano 100€ eToro pronto:", json.dumps(plan.cartridges, indent=2, ensure_ascii=False))
