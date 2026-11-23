#!/usr/bin/env python3
"""
Motore Autonomo Parallelo #2 — Dual Momentum Dinamico + Oro Fisico (Budget Dedicato: 1.000,00 EUR)
==================================================================================================
- Gira in parallelo sul medesimo conto Trading 212 Invest (Demo/Live) con "Muraglia Cinese" ermetica
  rispetto al Bot Intraday da 100,00 EUR (`0` ticker in comune con i 47 Colossi intraday, contabilità
  e riconciliazione cassa completamente separate in `longterm_vault_1000e.json`).
- Strategia Istituzionale Dual Momentum (Gary Antonacci / Meb Faber) + Scudo Oro Fisico + Tasso BCE:
  1. Momentum Relativo Risk-Adjusted (3M + 6M + 1M / Volatilità Annualizzata) per selezionare i migliori
     2 ETF Motori Globali ad Accumulazione (45%) + i migliori 2 Campioni Azionari Globali (30%).
  2. Momentum Assoluto & Semaforo Media Mobile (SMA 100/150 + rendimento > tasso BCE `XEON`):
     se un'azione o ETF entra in mercato ribassista, non subisce i crolli da -35% ma ruota
     automaticamente nello Scudo Oro Fisico (`4GLDd_EQ`, fino al 35%) e nel Monetario BCE (`DBXTd_EQ` XEON).
  3. Disciplina Anti-Spread: controllo d'emergenza giornaliero H24 sul Cloud a PC spento, rotazione
     ordinaria al massimo settimanale (>= 7 giorni) con ordini Limit protetti MiFID II (+0,50% cap).
  4. Liquidabilità Immediata: comando `--cashout-all` o `--cashout-profits` per incassare in 2 secondi
     a borsa aperta senza vincoli né penali (0,00 EUR commissioni).
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime
import json
import math
import os
import statistics
import sys
import time
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

MARKET_TZ = ZoneInfo("Europe/Rome")

from trading212_bot import (
    BASE_DIR,
    EUR_ZERO_FEE_UNIVERSE,
    Trading212Client,
    atomic_write_json,
)

CREDENTIALS_PATH = os.path.join(BASE_DIR, "t212_credentials.json")
LONGTERM_STATE_PATH = os.path.join(BASE_DIR, "longterm_vault_1000e.json")

INITIAL_LONGTERM_BUDGET_EUR = 1000.00
LONGTERM_LIMIT_CAP_PCT = 0.0100  # +1,00% tetto Limit protetto MiFID II RTS 11
REBALANCE_MIN_INTERVAL_DAYS = 7.0
MIN_TRADE_DELTA_EUR = 45.00

# Universo Certificato EUR Zero-Fee (12 strumenti: 100% disgiunti dai 47 titoli intraday, 0% cambio FX, 0% Tobin Tax)
DUAL_MOMENTUM_UNIVERSE: Dict[str, Dict[str, Any]] = {
    # --- SAFE HAVENS (ORO FISICO + TASSO OVERNIGHT BCE) ---
    "4GLDd_EQ": {
        "name": "Xetra-Gold Physical Gold ETC (EUR)",
        "isin": "DE000A0S9GB0",
        "yahoo": "4GLD.DE",
        "bucket": "GOLD_SAFE_HAVEN",
        "sub_group": "PHYSICAL_GOLD",
        "tax_regime_it": "ETC_REDDITI_DIVERSI_COMPENSA_MINUS_100PCT",
        "ref_price_eur": 106.70,
    },
    "DBXTd_EQ": {
        "name": "Xtrackers II EUR Overnight Rate Swap XEON (Acc)",
        "isin": "LU0290358497",
        "yahoo": "XEON.DE",
        "bucket": "CASH_SAFE_HAVEN",
        "sub_group": "ECB_OVERNIGHT_RATE",
        "tax_regime_it": "ETF_ACCUMULAZIONE_ZERO_TASSE_DIVIDENDI",
        "ref_price_eur": 150.87,
    },
    # --- 5 MOTORI ETF GLOBALI AD ACCUMULAZIONE (0% TASSE SUI DIVIDENDI INTERNI) ---
    "SXRVd_EQ": {
        "name": "iShares Nasdaq 100 UCITS ETF (EUR Acc)",
        "isin": "IE00B53SZB19",
        "yahoo": "SXRV.DE",
        "bucket": "ETF_ENGINE",
        "sub_group": "US_TECH_GROWTH",
        "tax_regime_it": "ETF_ACCUMULAZIONE_ZERO_TASSE_DIVIDENDI",
        "ref_price_eur": 1360.60,
    },
    "QDVEd_EQ": {
        "name": "iShares S&P 500 Information Technology (EUR Acc)",
        "isin": "IE00B3WJKG14",
        "yahoo": "QDVE.DE",
        "bucket": "ETF_ENGINE",
        "sub_group": "US_TECH_GROWTH",
        "tax_regime_it": "ETF_ACCUMULAZIONE_ZERO_TASSE_DIVIDENDI",
        "ref_price_eur": 39.64,
    },
    "IS3Rd_EQ": {
        "name": "iShares Edge MSCI World Momentum Factor (EUR Acc)",
        "isin": "IE00BP3QZ825",
        "yahoo": "IS3R.DE",
        "bucket": "ETF_ENGINE",
        "sub_group": "WORLD_MOMENTUM",
        "tax_regime_it": "ETF_ACCUMULAZIONE_ZERO_TASSE_DIVIDENDI",
        "ref_price_eur": 87.42,
    },
    "XDEQQd_EQ": {
        "name": "Xtrackers MSCI World Quality (EUR Acc)",
        "isin": "IE00BL25JL35",
        "yahoo": "XDEQ.DE",
        "bucket": "ETF_ENGINE",
        "sub_group": "WORLD_QUALITY",
        "tax_regime_it": "ETF_ACCUMULAZIONE_ZERO_TASSE_DIVIDENDI",
        "ref_price_eur": 79.14,
    },
    "IQQ0d_EQ": {
        "name": "iShares Edge MSCI World Min Volatility (EUR Acc)",
        "isin": "IE00B8FHGS14",
        "yahoo": "IQQ0.DE",
        "bucket": "ETF_ENGINE",
        "sub_group": "WORLD_MIN_VOL",
        "tax_regime_it": "ETF_ACCUMULAZIONE_ZERO_TASSE_DIVIDENDI",
        "ref_price_eur": 71.41,
    },
    # --- 5 CAMPIONI AZIONARI GLOBALI "FORTEZZA" (0% TOBIN TAX, 0% DOPPIA TASSA DIVIDENDI UK/BRK) ---
    "BRYNd_EQ": {
        "name": "Berkshire Hathaway Inc Class B (EUR)",
        "isin": "US0846707026",
        "yahoo": "BRYN.DE",
        "gettex": "GETTEX:BRYN",
        "bucket": "STOCK_COMPOUNDER",
        "sub_group": "HOLDING_BUFFETT",
        "tax_regime_it": "AZIONE_REDDITI_DIVERSI_0PCT_DIVIDEND_TAX",
        "ref_price_eur": 523.80,
    },
    "LINd_EQ": {
        "name": "Linde PLC (EUR)",
        "isin": "IE000S9YS762",
        "yahoo": "LIN.DE",
        "gettex": "GETTEX:LIN",
        "bucket": "STOCK_COMPOUNDER",
        "sub_group": "INDUSTRIAL_GASES_HYDROGEN",
        "tax_regime_it": "AZIONE_REDDITI_DIVERSI_COMPENSA_MINUS_100PCT",
        "ref_price_eur": 465.00,
    },
    "RENa_EQ": {
        "name": "RELX PLC (EUR Amsterdam)",
        "isin": "GB00B2B0DG97",
        "yahoo": "REN.AS",
        "bucket": "STOCK_COMPOUNDER",
        "sub_group": "DATA_ANALYTICS_AI_UK0WHT",
        "tax_regime_it": "AZIONE_REDDITI_DIVERSI_0PCT_RITENUTA_UK",
        "ref_price_eur": 35.20,
    },
    "WKLa_EQ": {
        "name": "Wolters Kluwer NV (EUR Amsterdam)",
        "isin": "NL0000395903",
        "yahoo": "WKL.AS",
        "bucket": "STOCK_COMPOUNDER",
        "sub_group": "ENTERPRISE_SOFTWARE_DATA",
        "tax_regime_it": "AZIONE_REDDITI_DIVERSI_COMPENSA_MINUS_100PCT",
        "ref_price_eur": 84.24,
    },
    "ADa_EQ": {
        "name": "Koninklijke Ahold Delhaize NV (EUR Amsterdam)",
        "isin": "NL0011794037",
        "yahoo": "AD.AS",
        "bucket": "STOCK_COMPOUNDER",
        "sub_group": "CONSUMER_STAPLES_DEFENSIVE",
        "tax_regime_it": "AZIONE_REDDITI_DIVERSI_COMPENSA_MINUS_100PCT",
        "ref_price_eur": 34.84,
    },
}


def load_t212_client() -> Trading212Client:
    env_key = os.environ.get("T212_API_KEY", "").strip()
    env_secret = os.environ.get("T212_API_SECRET", "").strip()
    env_mode = os.environ.get("T212_MODE", "demo").strip() or "demo"
    if env_key:
        return Trading212Client(api_key=env_key, api_secret=env_secret or None, mode=env_mode)
    with open(CREDENTIALS_PATH, "r", encoding="utf-8") as f:
        creds = json.load(f)
    return Trading212Client(
        api_key=creds["api_key"],
        api_secret=creds.get("api_secret"),
        mode=creds.get("mode", "demo"),
    )


def verify_zero_intraday_overlap(intraday_tickers: Optional[set[str]] = None) -> bool:
    ref = intraday_tickers if intraday_tickers is not None else set(EUR_ZERO_FEE_UNIVERSE.keys())
    overlap = set(DUAL_MOMENTUM_UNIVERSE.keys()) & ref
    if overlap:
        raise RuntimeError(f"Violazione Muraglia Cinese: ticker sovrapposti col bot intraday: {sorted(overlap)}")
    return True


def fetch_daily_series_1y(ticker: str) -> List[float]:
    meta = DUAL_MOMENTUM_UNIVERSE[ticker]
    sym = meta["yahoo"]
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1y"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)"},
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    res = raw["chart"]["result"][0]
    closes = [
        float(c)
        for c in res["indicators"]["quote"][0].get("close", [])
        if c is not None and float(c) > 0
    ]
    reg_px = float(res.get("meta", {}).get("regularMarketPrice") or 0.0)
    if reg_px > 0 and closes:
        closes[-1] = reg_px
    return closes


def compute_instrument_momentum_metrics(
    ticker: str,
    closes: List[float],
    risk_free_comp_pct: float = 0.0,
) -> Dict[str, Any]:
    meta = DUAL_MOMENTUM_UNIVERSE[ticker]
    if len(closes) < 30:
        px = float(closes[-1]) if closes else float(meta["ref_price_eur"])
        return {
            "ticker": ticker,
            "name": meta["name"],
            "bucket": meta["bucket"],
            "sub_group": meta["sub_group"],
            "live_price_eur": round(px, 4),
            "ret_1m_pct": 0.0,
            "ret_3m_pct": 0.0,
            "ret_6m_pct": 0.0,
            "ret_12m_pct": 0.0,
            "composite_mom_pct": 0.0,
            "ann_vol_pct": 15.0,
            "dm_sharpe_score": 0.0,
            "sma_100": round(px, 4),
            "sma_150": round(px, 4),
            "sma_150_dist_pct": 0.0,
            "is_bull_trend": ticker in ("4GLDd_EQ", "DBXTd_EQ"),
            "is_hard_bear_break": False,
            "bars_count": len(closes),
        }

    cur_px = float(closes[-1])
    idx_1m = max(0, len(closes) - 22)
    idx_3m = max(0, len(closes) - 64)
    idx_6m = max(0, len(closes) - 127)

    ret_1m = ((cur_px / closes[idx_1m]) - 1.0) * 100.0 if closes[idx_1m] > 0 else 0.0
    ret_3m = ((cur_px / closes[idx_3m]) - 1.0) * 100.0 if closes[idx_3m] > 0 else 0.0
    ret_6m = ((cur_px / closes[idx_6m]) - 1.0) * 100.0 if closes[idx_6m] > 0 else 0.0
    ret_12m = ((cur_px / closes[0]) - 1.0) * 100.0 if closes[0] > 0 else 0.0

    win_100 = closes[-min(100, len(closes)):]
    win_150 = closes[-min(150, len(closes)):]
    sma_100 = sum(win_100) / len(win_100)
    sma_150 = sum(win_150) / len(win_150)
    sma_150_dist = ((cur_px - sma_150) / sma_150) * 100.0 if sma_150 > 0 else 0.0

    tail_rets = [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(max(1, len(closes) - 126), len(closes))
        if closes[i - 1] > 0
    ]
    if len(tail_rets) >= 10:
        ann_vol = statistics.stdev(tail_rets) * math.sqrt(252.0) * 100.0
    else:
        ann_vol = 15.0

    eff_vol = max(8.0, ann_vol)
    composite_mom = 0.50 * ret_3m + 0.35 * ret_6m + 0.15 * ret_1m
    dm_score = composite_mom / eff_vol

    if ticker == "DBXTd_EQ":
        is_bull = True
        hard_bear = False
    elif ticker == "4GLDd_EQ":
        is_bull = (cur_px >= sma_150 * 0.985) or (composite_mom > 0.0)
        hard_bear = (cur_px < sma_150 * 0.95) and (ret_3m < -3.0)
    else:
        above_ma = (cur_px >= sma_150) or (cur_px >= sma_100 and ret_1m > 0.0)
        beats_cash = composite_mom > risk_free_comp_pct
        is_bull = bool(above_ma and beats_cash)
        hard_bear = bool(cur_px < (sma_150 * 0.965) and ret_1m < -2.0)

    return {
        "ticker": ticker,
        "name": meta["name"],
        "bucket": meta["bucket"],
        "sub_group": meta["sub_group"],
        "tax_regime_it": meta["tax_regime_it"],
        "live_price_eur": round(cur_px, 4),
        "ret_1m_pct": round(ret_1m, 2),
        "ret_3m_pct": round(ret_3m, 2),
        "ret_6m_pct": round(ret_6m, 2),
        "ret_12m_pct": round(ret_12m, 2),
        "composite_mom_pct": round(composite_mom, 2),
        "ann_vol_pct": round(ann_vol, 2),
        "dm_sharpe_score": round(dm_score, 4),
        "sma_100": round(sma_100, 4),
        "sma_150": round(sma_150, 4),
        "sma_150_dist_pct": round(sma_150_dist, 2),
        "is_bull_trend": is_bull,
        "is_hard_bear_break": hard_bear,
        "bars_count": len(closes),
    }


def compute_dual_momentum_target_weights(
    metrics_by_ticker: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, float], str, List[str]]:
    """
    Calcola i pesi target ottimali (somma esatta = 1.0000) secondo la legge Dual Momentum + Oro:
    - Base Risk-On:
      * 20,0% Oro Fisico (`4GLDd_EQ`, o `10,0%` se l'Oro stesso è in bear trend)
      * 45,0% Top 2 ETF Motori Globali col Semaforo Verde (`2 x 22,5%`, max 1 US_TECH_GROWTH puro)
      * 30,0% Top 2 Azioni Campioni Globali col Semaforo Verde (`2 x 15,0%`, sub_group distinti)
      *  5,0% Riserva Tasso BCE (`DBXTd_EQ` XEON)
    - Protezione Automatica Risk-Off (Mercato Orso):
      * Ogni slot azionario/ETF privo di candidati in Semaforo Verde non resta esposto ai crolli,
        ma confluisce automaticamente in Oro Fisico (fino al tetto prudenziale del 35,0% se Oro è in bull trend)
        e per la parte restante nel Monetario BCE `XEON` (`DBXTd_EQ`).
    """
    weights: Dict[str, float] = {}
    notes: List[str] = []

    gold_m = metrics_by_ticker.get("4GLDd_EQ", {})
    gold_bull = bool(gold_m.get("is_bull_trend", True))
    base_gold_w = 0.20 if gold_bull else 0.10
    weights["4GLDd_EQ"] = base_gold_w

    # 1) Selezione Top 2 ETF Engines (2 x 22,5% = 45,0%)
    etf_cands = sorted(
        (
            m for m in metrics_by_ticker.values()
            if m.get("bucket") == "ETF_ENGINE" and bool(m.get("is_bull_trend", False))
        ),
        key=lambda x: float(x.get("dm_sharpe_score", 0.0)),
        reverse=True,
    )
    chosen_etfs: List[Dict[str, Any]] = []
    used_etf_groups: set[str] = set()
    for em in etf_cands:
        grp = str(em.get("sub_group", ""))
        if grp in used_etf_groups:
            continue
        chosen_etfs.append(em)
        used_etf_groups.add(grp)
        if len(chosen_etfs) == 2:
            break
    for em in chosen_etfs:
        weights[em["ticker"]] = round(weights.get(em["ticker"], 0.0) + 0.225, 4)
    unfilled_etf_w = round(0.45 - 0.225 * len(chosen_etfs), 4)

    # 2) Selezione Top 2 Stock Compounders (2 x 15,0% = 30,0%)
    stk_cands = sorted(
        (
            m for m in metrics_by_ticker.values()
            if m.get("bucket") == "STOCK_COMPOUNDER" and bool(m.get("is_bull_trend", False))
        ),
        key=lambda x: float(x.get("dm_sharpe_score", 0.0)),
        reverse=True,
    )
    chosen_stocks: List[Dict[str, Any]] = []
    used_stk_groups: set[str] = set()
    for sm in stk_cands:
        grp = str(sm.get("sub_group", ""))
        if grp in used_stk_groups:
            continue
        chosen_stocks.append(sm)
        used_stk_groups.add(grp)
        if len(chosen_stocks) == 2:
            break
    for sm in chosen_stocks:
        weights[sm["ticker"]] = round(weights.get(sm["ticker"], 0.0) + 0.150, 4)
    unfilled_stk_w = round(0.30 - 0.150 * len(chosen_stocks), 4)

    defensive_overflow = round((0.20 - base_gold_w) + unfilled_etf_w + unfilled_stk_w, 4)
    if defensive_overflow > 0 and gold_bull:
        extra_gold = min(round(0.35 - weights["4GLDd_EQ"], 4), round(defensive_overflow * 0.50, 4))
        if extra_gold > 0:
            weights["4GLDd_EQ"] = round(weights["4GLDd_EQ"] + extra_gold, 4)
            defensive_overflow = round(defensive_overflow - extra_gold, 4)

    xeon_w = round(0.05 + defensive_overflow, 4)
    weights["DBXTd_EQ"] = round(weights.get("DBXTd_EQ", 0.0) + xeon_w, 4)

    # Normalizzazione esatta a 1.0000
    tot_w = round(sum(weights.values()), 4)
    if abs(tot_w - 1.0) > 1e-6:
        weights["DBXTd_EQ"] = round(max(0.0, weights.get("DBXTd_EQ", 0.0) + (1.0 - tot_w)), 4)

    active_risk_slots = len(chosen_etfs) + len(chosen_stocks)
    if active_risk_slots == 4:
        regime_label = "FULL_BULL_MOMENTUM_4_SU_4_ATTIVI"
        notes.append("Tutti i 4 motori di crescita (2 ETF + 2 Azioni Leader) sono in trend rialzista sopra SMA e sopra tasso BCE.")
    elif active_risk_slots >= 2:
        regime_label = f"SELETTIVO_IBRIDO_{active_risk_slots}_SU_4_CON_SCUDO_ORO_XEON"
        notes.append(f"{active_risk_slots}/4 slot azionari in trend positivo; le quote deboli sono protette in Oro Fisico e Monetario BCE.")
    else:
        regime_label = "SCUDO_DIFENSIVO_BEAR_MARKET_ORO_E_XEON"
        notes.append("Mercati azionari sotto media di lungo periodo: capitale protetto in Oro Fisico + Tasso BCE XEON.")

    return {k: v for k, v in weights.items() if v > 0}, regime_label, notes


class DualMomentumVault1000E:
    """Gestore autonomo del Portafoglio #2 Dual Momentum + Oro (1.000,00 EUR isolati)."""

    def __init__(
        self,
        client: Optional[Trading212Client] = None,
        state_path: str = LONGTERM_STATE_PATH,
        initial_budget_eur: float = INITIAL_LONGTERM_BUDGET_EUR,
    ) -> None:
        verify_zero_intraday_overlap()
        self.client = client
        if self.client is not None and hasattr(self.client, "extra_allowed_eur_tickers"):
            self.client.extra_allowed_eur_tickers |= set(DUAL_MOMENTUM_UNIVERSE.keys())
        self.state_path = state_path
        self.initial_budget_eur = round(float(initial_budget_eur), 2)
        self.state: Dict[str, Any] = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        default_st: Dict[str, Any] = {
            "timestamp": "",
            "mode": "DUAL_MOMENTUM_GOLD_VAULT_1000E_V1",
            "initial_budget_eur": INITIAL_LONGTERM_BUDGET_EUR,
            "compounded_budget_eur": INITIAL_LONGTERM_BUDGET_EUR,
            "invested_cost_eur": 0.0,
            "market_value_eur": 0.0,
            "uninvested_cash_eur": INITIAL_LONGTERM_BUDGET_EUR,
            "unrealized_pnl_eur": 0.0,
            "realized_net_pnl_eur": 0.0,
            "total_net_return_eur": 0.0,
            "total_net_return_pct": 0.0,
            "total_portfolio_value_eur": INITIAL_LONGTERM_BUDGET_EUR,
            "paused_by_user_cashout": False,
            "last_rebalance_ts": 0.0,
            "last_rebalance_iso": "",
            "regime_dual_momentum": "IN_ATTESA_PRIMA_SCANSIONE",
            "target_weights": {},
            "lotti_lifo": {},
            "operazioni_chiuse": [],
            "posizioni_attive": [],
            "classifica_dual_momentum_1y": [],
            "ultime_azioni_vault": [],
        }
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    default_st.update(loaded)
            except Exception:
                pass
        return default_st

    def save_state(self) -> None:
        atomic_write_json(self.state_path, self.state, indent=2)

    def scan_universe_1y(self) -> Dict[str, Dict[str, Any]]:
        tickers = list(DUAL_MOMENTUM_UNIVERSE.keys())
        series_map: Dict[str, List[float]] = {}
        with ThreadPoolExecutor(max_workers=6) as pool:
            futs = {tkr: pool.submit(fetch_daily_series_1y, tkr) for tkr in tickers}
            for tkr, fut in futs.items():
                try:
                    series_map[tkr] = fut.result()
                except Exception:
                    series_map[tkr] = []

        gx_map = {
            meta["gettex"]: tkr
            for tkr, meta in DUAL_MOMENTUM_UNIVERSE.items()
            if meta.get("gettex")
        }
        if gx_map:
            try:
                payload = json.dumps({
                    "symbols": {"tickers": list(gx_map.keys()), "query": {"types": []}},
                    "columns": ["close"],
                }).encode("utf-8")
                req = urllib.request.Request(
                    "https://scanner.tradingview.com/germany/scan",
                    data=payload,
                    headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
                )
                with urllib.request.urlopen(req, timeout=4) as resp:
                    for row in json.loads(resp.read().decode("utf-8")).get("data", []):
                        tkr_hit = gx_map.get(row.get("s", ""))
                        px_hit = float((row.get("d") or [0.0])[0] or 0.0)
                        if tkr_hit and px_hit > 0 and series_map.get(tkr_hit):
                            series_map[tkr_hit][-1] = px_hit
            except Exception:
                pass

        xeon_m = compute_instrument_momentum_metrics("DBXTd_EQ", series_map.get("DBXTd_EQ", []), 0.0)
        rf_hurdle = max(0.0, float(xeon_m.get("composite_mom_pct", 0.0)))

        metrics: Dict[str, Dict[str, Any]] = {"DBXTd_EQ": xeon_m}
        for tkr in tickers:
            if tkr == "DBXTd_EQ":
                continue
            metrics[tkr] = compute_instrument_momentum_metrics(
                tkr,
                series_map.get(tkr, []),
                risk_free_comp_pct=rf_hurdle,
            )
        return metrics

    def _record_lifo_buy(self, ticker: str, qty: float, price_eur: float) -> None:
        lots = self.state.setdefault("lotti_lifo", {}).setdefault(ticker, [])
        lots.append({
            "timestamp": datetime.datetime.now(MARKET_TZ).replace(tzinfo=None).isoformat(timespec="seconds"),
            "ticker": ticker,
            "isin": DUAL_MOMENTUM_UNIVERSE[ticker]["isin"],
            "quantity": round(qty, 6),
            "price_eur": round(price_eur, 4),
            "total_eur": round(qty * price_eur, 4),
        })

    def _record_lifo_sell(
        self,
        ticker: str,
        sell_qty: float,
        sell_price_eur: float,
        fallback_avg_px: float,
        reason: str,
    ) -> float:
        lots = self.state.setdefault("lotti_lifo", {}).setdefault(ticker, [])
        rem = sell_qty
        cost_basis = 0.0
        while rem > 1e-7 and lots:
            last = lots[-1]
            lq = float(last["quantity"])
            lp = float(last["price_eur"])
            if lq <= rem + 1e-7:
                cost_basis += lq * lp
                rem -= lq
                lots.pop()
            else:
                cost_basis += rem * lp
                last["quantity"] = round(lq - rem, 6)
                last["total_eur"] = round(last["quantity"] * lp, 4)
                rem = 0.0
        if rem > 1e-7:
            cost_basis += rem * (fallback_avg_px if fallback_avg_px > 0 else sell_price_eur)
        if not lots:
            self.state.get("lotti_lifo", {}).pop(ticker, None)

        proceeds = sell_qty * sell_price_eur
        pnl = round(proceeds - cost_basis, 2)
        self.state["realized_net_pnl_eur"] = round(float(self.state.get("realized_net_pnl_eur", 0.0)) + pnl, 2)
        self.state.setdefault("operazioni_chiuse", []).append({
            "timestamp": datetime.datetime.now(MARKET_TZ).replace(tzinfo=None).isoformat(timespec="seconds"),
            "ticker": ticker,
            "name": DUAL_MOMENTUM_UNIVERSE[ticker]["name"],
            "quantity": round(sell_qty, 6),
            "sell_price_eur": round(sell_price_eur, 4),
            "proceeds_eur": round(proceeds, 2),
            "cost_lifo_eur": round(cost_basis, 2),
            "realized_pnl_eur": pnl,
            "reason": reason,
        })
        return pnl

    def _safe_get_positions(self) -> List[Dict[str, Any]]:
        assert self.client is not None
        for attempt in range(4):
            try:
                return self.client.get_open_positions()
            except Exception as exc:
                if "429" in str(exc) and attempt < 3:
                    time.sleep(5.2)
                    continue
                raise
        return []

    def _execute_protected_limit_buy(
        self,
        ticker: str,
        alloc_eur: float,
        live_price_eur: float,
        pre_qty: float = 0.0,
        poll_sec: float = 1.0,
    ) -> Optional[Tuple[float, float, Any]]:
        assert self.client is not None
        if alloc_eur < 5.0 or live_price_eur <= 0:
            return None
        limit_px = Trading212Client.snap_mifid_tick_price(
            live_price_eur * (1.0 + LONGTERM_LIMIT_CAP_PCT),
            side="BUY",
        )
        qty = Trading212Client.quantize_buy_quantity_floor(alloc_eur, limit_px, decimals=4)
        if qty <= 0:
            return None

        try:
            order_res = self.client.place_limit_order(
                ticker=ticker,
                quantity=qty,
                limit_price=limit_px,
                time_validity="DAY",
            )
        except Exception as err:
            qty_fb = Trading212Client.quantize_buy_quantity_floor(alloc_eur, limit_px, decimals=2)
            if qty_fb > 0 and qty_fb != qty and "400" in str(err):
                qty = qty_fb
                order_res = self.client.place_limit_order(
                    ticker=ticker,
                    quantity=qty,
                    limit_price=limit_px,
                    time_validity="DAY",
                )
            else:
                raise

        ord_id = order_res.get("id") if isinstance(order_res, dict) else None
        was_cancelled_unfilled = False
        if poll_sec > 0 and ord_id is not None:
            deadline = time.time() + max(12.0, poll_sec)
            while time.time() < deadline:
                time.sleep(2.0)
                try:
                    pend = self.client.get_pending_orders()
                    if not any(o.get("id") == ord_id for o in pend):
                        break
                except Exception:
                    break
        if ord_id is not None:
            try:
                pend = self.client.get_pending_orders()
                if any(o.get("id") == ord_id for o in pend):
                    self.client.cancel_order(ord_id)
                    was_cancelled_unfilled = True
                    if poll_sec > 0:
                        time.sleep(0.5)
            except Exception:
                pass

        # Sul monetario BCE XEON (DBXTd_EQ, vol. annua 0,15%, spread XETRA ~0,007%), il prezzo resta
        # quasi immobile tutto il giorno e il matcher Limit tick-driven può attendere minuti un nuovo tick:
        # in finestra continua XETRA esegue istantaneamente il medesimo quantitativo quantizzato anti-overrun.
        if was_cancelled_unfilled and ticker == "DBXTd_EQ" and poll_sec > 0:
            mkt_qty = Trading212Client.quantize_buy_quantity_floor(alloc_eur, live_price_eur * 1.003, decimals=4)
            if mkt_qty > 0:
                try:
                    mkt_res = self.client.place_market_order(ticker=ticker, quantity=mkt_qty)
                except Exception as err:
                    mkt_qty_fb = Trading212Client.quantize_buy_quantity_floor(alloc_eur, live_price_eur * 1.003, decimals=2)
                    if mkt_qty_fb > 0 and "400" in str(err):
                        mkt_res = self.client.place_market_order(ticker=ticker, quantity=mkt_qty_fb)
                    else:
                        mkt_res = None
                if isinstance(mkt_res, dict) and mkt_res.get("id") is not None:
                    ord_id = mkt_res.get("id")
                time.sleep(1.5)

        post_pos = next(
            (p for p in self._safe_get_positions() if p.get("ticker") == ticker and float(p.get("quantity", 0.0)) > pre_qty + 1e-7),
            None,
        )
        if post_pos is None and poll_sec > 0:
            time.sleep(1.5)
            post_pos = next(
                (p for p in self._safe_get_positions() if p.get("ticker") == ticker and float(p.get("quantity", 0.0)) > pre_qty + 1e-7),
                None,
            )
        if post_pos is None:
            return None
        delta_qty = round(float(post_pos["quantity"]) - pre_qty, 6)
        fill_px = float(post_pos.get("averagePrice") or live_price_eur)
        if poll_sec > 0:
            time.sleep(2.5)
        return delta_qty, fill_px, ord_id

    @staticmethod
    def is_xetra_trading_window(now: Optional[datetime.datetime] = None) -> bool:
        dt = now.astimezone(MARKET_TZ) if (now and now.tzinfo) else (now.replace(tzinfo=MARKET_TZ) if now else datetime.datetime.now(MARKET_TZ))
        if dt.weekday() >= 5:
            return False
        hm = dt.hour * 60 + dt.minute
        return (9 * 60 + 15) <= hm <= (17 * 60 + 15)

    def cashout(self, profits_only: bool = False) -> List[str]:
        """Incasso immediato in contanti EUR (totale 100% oppure solo i profitti eccedenti i 1.000 EUR)."""
        assert self.client is not None
        actions: List[str] = []
        raw_pos = [
            p for p in self._safe_get_positions()
            if p.get("ticker") in DUAL_MOMENTUM_UNIVERSE and float(p.get("quantity", 0.0)) > 0
        ]
        if not raw_pos:
            actions.append("Nessuna posizione aperta nel Vault 1.000 EUR da incassare (già 100% contanti EUR).")
            if not profits_only:
                self.state["paused_by_user_cashout"] = True
            self.refresh_status_only()
            self.state["ultime_azioni_vault"] = actions
            self.save_state()
            return actions

        tot_mkt_val = sum(float(p["quantity"]) * float(p.get("currentPrice", p.get("averagePrice", 0.0))) for p in raw_pos)
        realized_so_far = float(self.state.get("realized_net_pnl_eur", 0.0))
        uninvested = max(0.0, round(self.initial_budget_eur + realized_so_far - sum(float(p["quantity"]) * float(p.get("averagePrice", 0.0)) for p in raw_pos), 2))
        total_eq = tot_mkt_val + uninvested

        if profits_only:
            surplus = round(total_eq - self.initial_budget_eur, 2)
            if surplus < 5.0:
                actions.append(f"Nessun surplus >= 5,00 EUR sopra i {self.initial_budget_eur:.2f} EUR da incassare (Valore attuale: {total_eq:.2f} EUR).")
                self.refresh_status_only()
                self.state["ultime_azioni_vault"] = actions
                self.save_state()
                return actions
            sell_fraction = min(1.0, surplus / max(1.0, tot_mkt_val))
        else:
            sell_fraction = 1.0

        for p in raw_pos:
            tkr = p["ticker"]
            qty_open = float(p["quantity"])
            cur_px = float(p.get("currentPrice", p.get("averagePrice", 0.0)))
            avg_px = float(p.get("averagePrice", cur_px))
            qty_sell = qty_open if sell_fraction >= 0.999 else round(math.floor(qty_open * sell_fraction * 10000.0) / 10000.0, 4)
            if qty_sell <= 0:
                continue
            self.client.place_market_order(ticker=tkr, quantity=-qty_sell)
            pnl = self._record_lifo_sell(tkr, qty_sell, cur_px, avg_px, reason="INCASSO_UTENTE_IMMEDIATO")
            actions.append(
                f"INCASSO IMMEDIATO {'PROFITTI' if profits_only else 'INTEGRALE 100%'} -> SELL {qty_sell} {tkr} a {cur_px:.4f} EUR (Risultato: {pnl:+.2f} EUR, 0,00 EUR comm.)"
            )
            time.sleep(0.30)

        if not profits_only:
            self.state["paused_by_user_cashout"] = True
        self.refresh_status_only()
        self.state["ultime_azioni_vault"] = actions
        self.save_state()
        return actions

    def refresh_status_only(
        self,
        metrics: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        assert self.client is not None
        if metrics is None:
            metrics = self.scan_universe_1y()
        target_w, regime_lbl, notes = compute_dual_momentum_target_weights(metrics)

        open_lt = [
            p for p in self._safe_get_positions()
            if p.get("ticker") in DUAL_MOMENTUM_UNIVERSE and float(p.get("quantity", 0.0)) > 0
        ]
        realized_net = round(float(self.state.get("realized_net_pnl_eur", 0.0)), 2)
        compounded_budget = round(max(100.0, self.initial_budget_eur + realized_net), 2)

        invested_cost = 0.0
        mkt_val = 0.0
        unrealized = 0.0
        pos_details: List[Dict[str, Any]] = []

        for p in open_lt:
            tkr = p["ticker"]
            meta = DUAL_MOMENTUM_UNIVERSE[tkr]
            q = float(p.get("quantity", 0.0))
            avg_p = float(p.get("averagePrice", 0.0))
            cur_p = float(p.get("currentPrice", avg_p))
            cost_e = round(q * avg_p, 2)
            val_e = round(q * cur_p, 2)
            ppl_e = round(float(p.get("ppl", val_e - cost_e)), 2)
            pnl_pct = round(((cur_p - avg_p) / avg_p) * 100.0, 2) if avg_p > 0 else 0.0
            invested_cost += cost_e
            mkt_val += val_e
            unrealized += ppl_e

            # Auto-allinea lotto LIFO se mancante
            lots = self.state.setdefault("lotti_lifo", {}).get(tkr, [])
            if not lots and q > 0 and avg_p > 0:
                self._record_lifo_buy(tkr, q, avg_p)

            m_info = metrics.get(tkr, {})
            pos_details.append({
                "ticker": tkr,
                "name": meta["name"],
                "bucket": meta["bucket"],
                "quantity": round(q, 6),
                "avg_price_eur": round(avg_p, 4),
                "current_price_eur": round(cur_p, 4),
                "invested_eur": cost_e,
                "market_value_eur": val_e,
                "pnl_eur": ppl_e,
                "pnl_pct": pnl_pct,
                "target_weight_pct": round(target_w.get(tkr, 0.0) * 100.0, 1),
                "is_bull_trend": bool(m_info.get("is_bull_trend", True)),
                "sma_150_dist_pct": m_info.get("sma_150_dist_pct", 0.0),
            })

        invested_cost = round(invested_cost, 2)
        mkt_val = round(mkt_val, 2)
        unrealized = round(unrealized, 2)
        uninvested_cash = round(max(0.0, compounded_budget - invested_cost), 2)
        total_val = round(mkt_val + uninvested_cash, 2)
        total_ret_eur = round(total_val - self.initial_budget_eur, 2)
        total_ret_pct = round((total_ret_eur / self.initial_budget_eur) * 100.0, 2)

        ranked_1y = sorted(
            metrics.values(),
            key=lambda x: float(x.get("dm_sharpe_score", 0.0)),
            reverse=True,
        )
        now_iso = datetime.datetime.now(MARKET_TZ).replace(tzinfo=None).isoformat(timespec="seconds")
        self.state.update({
            "timestamp": now_iso,
            "initial_budget_eur": self.initial_budget_eur,
            "compounded_budget_eur": compounded_budget,
            "invested_cost_eur": invested_cost,
            "market_value_eur": mkt_val,
            "uninvested_cash_eur": uninvested_cash,
            "unrealized_pnl_eur": unrealized,
            "realized_net_pnl_eur": realized_net,
            "total_net_return_eur": total_ret_eur,
            "total_net_return_pct": total_ret_pct,
            "total_portfolio_value_eur": total_val,
            "regime_dual_momentum": regime_lbl,
            "note_strategiche": notes,
            "target_weights": {k: round(v * 100.0, 2) for k, v in target_w.items()},
            "posizioni_attive": sorted(pos_details, key=lambda x: x["market_value_eur"], reverse=True),
            "classifica_dual_momentum_1y": ranked_1y,
        })
        self.save_state()
        return self.state

    def run_rebalance_cycle(
        self,
        force_rebalance: bool = False,
        now: Optional[datetime.datetime] = None,
        poll_sec: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Esegue il controllo Dual Momentum + Oro:
        - Se `paused_by_user_cashout` è attivo (e non `force_rebalance`), aggiorna solo le metriche senza comprare.
        - Fuori orario XETRA (`09:15-17:15 CET` Lun-Ven), aggiorna le metriche senza inviare ordini.
        - A mercato aperto:
          1) Primo posizionamento automatico se il Vault è ancora vuoto (`len(open_lt) == 0`);
          2) Scudo Giornaliero Anti-Crollo immediato se una posizione rompe `SMA_150` di oltre `-3,5%` (`is_hard_bear_break`);
          3) Rotazione ordinaria settimanale (`>= 7` giorni dall'ultimo ribilanciamento) sulle sole fette deviate `>= 45 EUR`.
        """
        assert self.client is not None
        metrics = self.scan_universe_1y()
        target_w, regime_lbl, _ = compute_dual_momentum_target_weights(metrics)

        if bool(self.state.get("paused_by_user_cashout", False)) and not force_rebalance:
            return self.refresh_status_only(metrics)
        if force_rebalance:
            self.state["paused_by_user_cashout"] = False

        if not self.is_xetra_trading_window(now):
            return self.refresh_status_only(metrics)

        open_lt = {
            p["ticker"]: p
            for p in self._safe_get_positions()
            if p.get("ticker") in DUAL_MOMENTUM_UNIVERSE and float(p.get("quantity", 0.0)) > 0
        }
        now_ts = now.timestamp() if now else time.time()
        last_reb_ts = float(self.state.get("last_rebalance_ts", 0.0))
        days_since_reb = (now_ts - last_reb_ts) / 86400.0 if last_reb_ts > 0 else 999.0

        init_cost_check = sum(
            float(p.get("quantity", 0.0)) * float(p.get("averagePrice", 0.0))
            for p in open_lt.values()
        )
        is_initial_deploy = (len(open_lt) == 0) or (last_reb_ts == 0.0) or (init_cost_check < self.initial_budget_eur * 0.95)
        emergency_bear_tickers = [
            tkr for tkr in open_lt
            if tkr not in ("4GLDd_EQ", "DBXTd_EQ")
            and bool(metrics.get(tkr, {}).get("is_hard_bear_break", False))
            and target_w.get(tkr, 0.0) == 0.0
        ]
        due_weekly_rotation = days_since_reb >= REBALANCE_MIN_INTERVAL_DAYS

        if not (force_rebalance or is_initial_deploy or emergency_bear_tickers or due_weekly_rotation):
            return self.refresh_status_only(metrics)

        actions: List[str] = []
        did_trade = False

        # FASE 1: VENDITE (uscita da posizioni non più in target o riduzione eccessi >= MIN_TRADE_DELTA_EUR)
        realized_before = float(self.state.get("realized_net_pnl_eur", 0.0))
        est_budget = max(100.0, self.initial_budget_eur + realized_before)

        for tkr, p in list(open_lt.items()):
            if not (force_rebalance or is_initial_deploy or due_weekly_rotation) and tkr not in emergency_bear_tickers:
                continue
            q_open = float(p.get("quantity", 0.0))
            avg_px = float(p.get("averagePrice", 0.0))
            cur_px = float(p.get("currentPrice", avg_px))
            cur_val = q_open * cur_px
            tgt_val = est_budget * float(target_w.get(tkr, 0.0))

            if tgt_val <= 1.0:
                self.client.place_market_order(ticker=tkr, quantity=-q_open)
                reason = (
                    "SCUDO_ANTI_CROLLO_SMA150" if tkr in emergency_bear_tickers else "ROTAZIONE_DUAL_MOMENTUM_USCITA"
                )
                pnl = self._record_lifo_sell(tkr, q_open, cur_px, avg_px, reason=reason)
                actions.append(
                    f"{reason} -> SELL {q_open} {tkr} ({DUAL_MOMENTUM_UNIVERSE[tkr]['name']}) a {cur_px:.4f} EUR (PnL: {pnl:+.2f} EUR)"
                )
                open_lt.pop(tkr, None)
                did_trade = True
                if poll_sec > 0:
                    time.sleep(0.35)
            elif (cur_val - tgt_val) >= MIN_TRADE_DELTA_EUR and (force_rebalance or due_weekly_rotation):
                excess_eur = cur_val - tgt_val
                q_trim = round(math.floor((excess_eur / cur_px) * 10000.0) / 10000.0, 4)
                if 0 < q_trim < q_open:
                    self.client.place_market_order(ticker=tkr, quantity=-q_trim)
                    pnl = self._record_lifo_sell(tkr, q_trim, cur_px, avg_px, reason="RIBILANCIAMENTO_PESO_TARGET")
                    p["quantity"] = round(q_open - q_trim, 6)
                    actions.append(
                        f"RIBILANCIAMENTO TARGET -> SELL {q_trim} {tkr} a {cur_px:.4f} EUR (PnL: {pnl:+.2f} EUR)"
                    )
                    did_trade = True
                    if poll_sec > 0:
                        time.sleep(0.35)

        # FASE 2: ACQUISTI CON MARKETABLE LIMIT ORDER PROTETTI (+0,50% MiFID II)
        realized_now = float(self.state.get("realized_net_pnl_eur", 0.0))
        compounded_budget = round(max(100.0, self.initial_budget_eur + realized_now), 2)
        current_cost_sum = sum(
            float(p.get("quantity", 0.0)) * float(p.get("averagePrice", 0.0))
            for p in open_lt.values()
        )
        available_vault_cash = round(max(0.0, compounded_budget - current_cost_sum), 2)

        try:
            acct_cash = self.client.get_account_cash()
            # Riserva sempre almeno 110 EUR sul conto broker per non intaccare mai i 100 EUR del bot intraday!
            broker_safe_free = max(0.0, float(acct_cash.get("free", available_vault_cash)) - 110.0)
            available_vault_cash = min(available_vault_cash, round(broker_safe_free, 2))
        except Exception:
            pass

        for tkr, w_tgt in sorted(target_w.items(), key=lambda kv: kv[1], reverse=True):
            if available_vault_cash < 15.0:
                break
            m_tkr = metrics.get(tkr, {})
            live_px = float(m_tkr.get("live_price_eur") or DUAL_MOMENTUM_UNIVERSE[tkr]["ref_price_eur"])
            cur_p_obj = open_lt.get(tkr)
            cur_val = (
                float(cur_p_obj.get("quantity", 0.0)) * float(cur_p_obj.get("currentPrice", live_px))
                if cur_p_obj else 0.0
            )
            tgt_val = round(compounded_budget * w_tgt, 2)
            needed_eur = round(tgt_val - cur_val, 2)
            min_delta = 15.0 if (is_initial_deploy or cur_val == 0.0) else MIN_TRADE_DELTA_EUR
            if needed_eur < min_delta:
                continue

            alloc_eur = min(needed_eur, available_vault_cash)
            if alloc_eur <= available_vault_cash and available_vault_cash - alloc_eur < 5.0:
                alloc_eur = round(alloc_eur * 0.996, 2)
            if alloc_eur < 15.0:
                continue

            pre_q_now = float(cur_p_obj.get("quantity", 0.0)) if cur_p_obj else 0.0
            fill_info = self._execute_protected_limit_buy(tkr, alloc_eur, live_px, pre_qty=pre_q_now, poll_sec=poll_sec)
            if fill_info is not None:
                filled_qty, fill_px, ord_id = fill_info
                spent = round(filled_qty * fill_px, 2)
                self._record_lifo_buy(tkr, filled_qty, fill_px)
                available_vault_cash = round(max(0.0, available_vault_cash - spent), 2)
                did_trade = True
                actions.append(
                    f"INGRESSO DUAL MOMENTUM LIMIT ({round(w_tgt*100,1):.1f}%) -> BUY {filled_qty} {tkr} "
                    f"({DUAL_MOMENTUM_UNIVERSE[tkr]['name']}) a {fill_px:.4f} EUR (Tot: {spent:.2f} EUR, Order ID: {ord_id})"
                )

        if did_trade or is_initial_deploy:
            self.state["last_rebalance_ts"] = now_ts
            self.state["last_rebalance_iso"] = datetime.datetime.fromtimestamp(now_ts, tz=MARKET_TZ).replace(tzinfo=None).isoformat(timespec="seconds")
        if actions:
            self.state["ultime_azioni_vault"] = actions

        return self.refresh_status_only(metrics)


def print_vault_summary(st: Dict[str, Any]) -> None:
    print("\n" + "═" * 92)
    print(" 🏛️  PORTAFOGLIO #2: DUAL MOMENTUM DINAMICO + ORO FISICO (VAULT ISOLATO 1.000,00 €)")
    print("═" * 92)
    print(f" ⏱️  Aggiornato:        {st.get('timestamp', 'N/D')} | Ultimo Ribilanciamento: {st.get('last_rebalance_iso') or 'N/D'}")
    print(f" 🧭 Regime Attivo:     {st.get('regime_dual_momentum', 'N/D')}")
    tot_v = float(st.get("total_portfolio_value_eur", 1000.0))
    ret_e = float(st.get("total_net_return_eur", 0.0))
    ret_p = float(st.get("total_net_return_pct", 0.0))
    inv_e = float(st.get("invested_cost_eur", 0.0))
    uninv_e = float(st.get("uninvested_cash_eur", 0.0))
    unr_e = float(st.get("unrealized_pnl_eur", 0.0))
    real_e = float(st.get("realized_net_pnl_eur", 0.0))
    print("─" * 92)
    print(f" 💰 VALORE VAULT (BASE 1.000,00 €): {tot_v:,.2f} € ({ret_e:+.2f} € / {ret_p:+.2f}%)")
    print(f"    ├─ Investito a Mercato:  {inv_e:,.2f} € | Liquidità Vault: {uninv_e:,.2f} €")
    print(f"    └─ PnL Aperto:           {unr_e:+.2f} € | Utili Realizzati: {real_e:+.2f} € | Commissioni: 0,00 €")

    pos_list = st.get("posizioni_attive", [])
    print("\n" + "─" * 92)
    print(f" 📦 POSIZIONI ATTIVE NEL VAULT 1.000 € ({len(pos_list)} STRUMENTI — ZERO CONFLITTI COL BOT 100 €)")
    print("─" * 92)
    for p in pos_list:
        sem = "🟢 BULL" if p.get("is_bull_trend") else "🟡 CAUTO"
        print(
            f" • [{p['ticker']:<9}] {p['name']:<44} | Target: {p['target_weight_pct']:>4.1f}% | {sem}"
        )
        print(
            f"    Valore: {p['market_value_eur']:>7.2f} € (Costo: {p['invested_eur']:>7.2f} €) | "
            f"PnL: {p['pnl_eur']:+6.2f} € ({p['pnl_pct']:+5.2f}%) | SMA150: {p['sma_150_dist_pct']:+5.2f}%"
        )

    acts = st.get("ultime_azioni_vault", [])
    if acts:
        print("\n 📜 Ultime Operazioni Eseguite:")
        for a in acts[-6:]:
            print(f"    • {a}")
    print("═" * 92 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Motore #2 Dual Momentum + Oro (1.000,00 EUR isolati)")
    parser.add_argument("--auto-daily", action="store_true", help="Controllo giornaliero Cloud H24 (posiziona o protegge in automatico)")
    parser.add_argument("--force-rebalance", action="store_true", help="Forza allineamento immediato ai pesi Dual Momentum target")
    parser.add_argument("--status-only", action="store_true", help="Aggiorna e stampa solo lo stato senza inviare ordini")
    parser.add_argument("--cashout-all", action="store_true", help="Incassa immediatamente il 100%% del Vault in contanti EUR")
    parser.add_argument("--cashout-profits", action="store_true", help="Incassa solo i profitti netti sopra 1.000,00 EUR")
    parser.add_argument("--resume", action="store_true", help="Riattiva l'investimento automatico dopo un --cashout-all")
    args = parser.parse_args()

    client = load_t212_client()
    vault = DualMomentumVault1000E(client=client)

    if args.cashout_all:
        acts = vault.cashout(profits_only=False)
        for a in acts:
            print(a)
        print_vault_summary(vault.state)
        return
    if args.cashout_profits:
        acts = vault.cashout(profits_only=True)
        for a in acts:
            print(a)
        print_vault_summary(vault.state)
        return
    if args.resume:
        vault.state["paused_by_user_cashout"] = False
        vault.save_state()

    if args.status_only:
        st = vault.refresh_status_only()
    else:
        st = vault.run_rebalance_cycle(force_rebalance=bool(args.force_rebalance or args.resume))
    print_vault_summary(st)


if __name__ == "__main__":
    main()
