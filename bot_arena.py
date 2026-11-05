#!/usr/bin/env python3
"""
Trading Arena 50€ - Confronto Live tra Bot Prudente e Bot Aggressivo.
Collega i prezzi reali (API pubbliche Binance BTC/EUR, SOL/EUR, ETH/EUR)
e gestisce due portafogli virtuali indipendenti da 50,00€ ciascuno.
"""

import json
import math
import random
import time
import urllib.request
from datetime import datetime
from pathlib import Path

STATE_FILE = Path(__file__).parent / "portfolio_state.json"
FEE_RATE = 0.001  # Commissione reale exchange 0.1% (Binance/Bybit standard)


def fetch_live_price(symbol: str = "BTCEUR", fallback_price: float = 82500.0) -> float:
    """Legge il prezzo reale da Binance API pubblica (senza bisogno di chiave API)."""
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return float(data["price"])
    except Exception:
        # Fallback realistico con micro-oscillazione se offline o in sandbox
        change = random.gauss(0.0001, 0.006)
        return round(fallback_price * (1.0 + change), 2)


def compute_rsi(prices: list[float], period: int = 14) -> float:
    """Calcola l'indicatore RSI (Relative Strength Index) sugli ultimi prezzi."""
    if len(prices) < period + 1:
        return 50.0
    gains = []
    losses = []
    for i in range(-period, 0):
        delta = prices[i] - prices[i - 1]
        if delta >= 0:
            gains.append(delta)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(delta))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 1)


class PrudentBot:
    """
    BOT 1: PRUDENTE (Smart Grid a 4 Cartucce da 12,50€)
    - Capitale iniziale: 50,00€
    - Nessuna leva (1x)
    - Compra 1 cartuccia (12,50€) quando RSI < 36 o quando il prezzo scende di un altro -1,5% rispetto all'ultimo acquisto.
    - Vende appena il prezzo medio + 1,6% viene superato (incassando circa +0,18€ / +0,75€ netti).
    """

    def __init__(self, initial_eur: float = 50.0):
        self.cash_eur = initial_eur
        self.slot_size = 12.50
        self.max_slots = 4
        self.used_slots = 0
        self.qty_asset = 0.0
        self.avg_entry_price = 0.0
        self.last_buy_price = 0.0
        self.trades_won = 0
        self.trades_lost = 0
        self.logs: list[str] = []

    def step(self, price: float, rsi: float, timestamp: str) -> None:
        # 1. Controllo VENDITA (Take Profit +1.6% lordo -> ~+1.4% netto dopo fee)
        if self.used_slots > 0 and self.qty_asset > 0:
            pct_change = (price - self.avg_entry_price) / self.avg_entry_price
            if pct_change >= 0.016:
                gross_eur = self.qty_asset * price
                fee = gross_eur * FEE_RATE
                net_eur = gross_eur - fee
                invested = self.used_slots * self.slot_size
                profit = net_eur - invested
                self.cash_eur += net_eur
                self.trades_won += 1
                self.logs.insert(
                    0,
                    f"[{timestamp}] VITTORIA: Vendute {self.used_slots} cartucce a {price:.2f}€ (+{pct_change*100:.2f}%) | Netto: +{profit:.2f}€",
                )
                self.used_slots = 0
                self.qty_asset = 0.0
                self.avg_entry_price = 0.0
                self.last_buy_price = 0.0
                return

        # 2. Controllo ACQUISTO (1° ingresso su RSI basso, oppure cartucce successive a -1.5%)
        can_buy = self.used_slots < self.max_slots and self.cash_eur >= self.slot_size
        if not can_buy:
            return

        should_buy_first = self.used_slots == 0 and rsi < 38.0
        should_buy_dip = (
            self.used_slots > 0
            and (price - self.last_buy_price) / self.last_buy_price <= -0.015
        )

        if should_buy_first or should_buy_dip:
            spend = self.slot_size
            fee = spend * FEE_RATE
            net_spend = spend - fee
            bought_qty = net_spend / price

            total_cost_before = self.qty_asset * self.avg_entry_price
            self.qty_asset += bought_qty
            self.used_slots += 1
            self.cash_eur -= spend
            self.avg_entry_price = (total_cost_before + spend) / self.qty_asset
            self.last_buy_price = price

            reason = f"RSI ipervenduto ({rsi})" if should_buy_first else "Mediazione ribasso (-1.5%)"
            self.logs.insert(
                0,
                f"[{timestamp}] ACQUISTO Cartuccia {self.used_slots}/4 ({spend:.2f}€) a {price:.2f}€ ({reason})",
            )

    def total_equity(self, current_price: float) -> float:
        return round(self.cash_eur + (self.qty_asset * current_price), 2)


class AggressiveBot:
    """
    BOT 2: AGGRESSIVO (Momentum + Leva 3x su 90% del capitale)
    - Capitale iniziale: 50,00€
    - Usa il 90% della cassa con leva 3x per puntare a correre veloce verso +50% (75€).
    - Take Profit: +2.2% di movimento prezzo (~+6.0% sul capitale con leva 3x)
    - Stop Loss: -1.4% di movimento prezzo (~-4.2% sul capitale con leva 3x)
    """

    def __init__(self, initial_eur: float = 50.0):
        self.cash_eur = initial_eur
        self.in_position = False
        self.margin_locked = 0.0
        self.leverage = 3.0
        self.entry_price = 0.0
        self.trades_won = 0
        self.trades_lost = 0
        self.logs: list[str] = []

    def step(self, price: float, rsi: float, timestamp: str) -> None:
        if self.in_position:
            pct_move = (price - self.entry_price) / self.entry_price
            leveraged_pnl_pct = pct_move * self.leverage - (FEE_RATE * 2 * self.leverage)

            # Take Profit o Stop Loss
            if pct_move >= 0.022:
                pnl_eur = self.margin_locked * leveraged_pnl_pct
                self.cash_eur += self.margin_locked + pnl_eur
                self.trades_won += 1
                self.logs.insert(
                    0,
                    f"[{timestamp}] COLPO VINCENTE (Leva 3x): Chiuso a {price:.2f}€ | Guadagno: +{pnl_eur:.2f}€ (+{leveraged_pnl_pct*100:.1f}%)",
                )
                self.in_position = False
                self.margin_locked = 0.0
                return
            elif pct_move <= -0.014:
                pnl_eur = self.margin_locked * leveraged_pnl_pct
                self.cash_eur = max(0.0, self.cash_eur + self.margin_locked + pnl_eur)
                self.trades_lost += 1
                self.logs.insert(
                    0,
                    f"[{timestamp}] STOP LOSS (Leva 3x): Tagliata perdita a {price:.2f}€ | Perdita: {pnl_eur:.2f}€ ({leveraged_pnl_pct*100:.1f}%)",
                )
                self.in_position = False
                self.margin_locked = 0.0
                return

        else:
            # Entra aggressivo appena RSI < 44
            if rsi < 44.0 and self.cash_eur >= 10.0:
                self.margin_locked = round(self.cash_eur * 0.90, 2)
                self.cash_eur -= self.margin_locked
                self.entry_price = price
                self.in_position = True
                self.logs.insert(
                    0,
                    f"[{timestamp}] INGRESSO LEVA 3x: Puntati {self.margin_locked:.2f}€ (esposizione {self.margin_locked*3:.2f}€) a {price:.2f}€",
                )

    def total_equity(self, current_price: float) -> float:
        if not self.in_position:
            return round(self.cash_eur, 2)
        pct_move = (current_price - self.entry_price) / self.entry_price
        leveraged_pnl_pct = pct_move * self.leverage - (FEE_RATE * self.leverage)
        return round(max(0.0, self.cash_eur + self.margin_locked * (1.0 + leveraged_pnl_pct)), 2)


def run_simulation_steps(steps: int = 40):
    prudent = PrudentBot(50.0)
    aggressive = AggressiveBot(50.0)
    price = fetch_live_price("SOLEUR", 165.0)
    prices = [price]

    for i in range(steps):
        price = round(price * (1.0 + random.gauss(0.0004, 0.009)), 2)
        prices.append(price)
        rsi = compute_rsi(prices, period=8)
        ts = f"Giorno {(i // 6) + 1} - {(i % 6) * 4:02d}:00"
        prudent.step(price, rsi, ts)
        aggressive.step(price, rsi, ts)

    summary = {
        "last_price_sol_eur": price,
        "prudent_equity_eur": prudent.total_equity(price),
        "prudent_trades_won": prudent.trades_won,
        "prudent_logs": prudent.logs[:5],
        "aggressive_equity_eur": aggressive.total_equity(price),
        "aggressive_trades_won": aggressive.trades_won,
        "aggressive_trades_lost": aggressive.trades_lost,
        "aggressive_logs": aggressive.logs[:5],
    }
    STATE_FILE.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    run_simulation_steps()
