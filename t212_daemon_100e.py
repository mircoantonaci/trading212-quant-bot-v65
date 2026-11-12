#!/usr/bin/env python3
"""
Demone Quantitativo Autonomo Trading 212 (100,00 EUR / 4 Cartucce da 25,00 EUR)
Versione 4.5 — Ibrida 2+2 Senza Tetto + RADAR PREDITTIVO ONDA NOTTURNA (Wall Street + VIX + VWAP)
=================================================================================================
Come il bot evita le onde negative della notte e cavalca quelle positive:
Alle ore 17:15-17:28 (prima che Francoforte chiuda alle 17:30), Wall Street (New York) è GIÀ
aperta da quasi 2 ore (dalle 15:30). Il modulo `OvernightWaveRadar` legge in tempo reale:
  1. Nasdaq 100 / Composite (^IXIC) — il motore mondiale dei titoli tecnologici
  2. S&P 500 (^GSPC) — la direzione dei grandi fondi istituzionali USA
  3. Indice della Paura VIX (^VIX) — se sale forte, i fondi stanno scappando dal rischio
  4. Posizione del singolo titolo rispetto al suo VWAP e RSI di fine pomeriggio

Decisione Automatica alle 17:15-17:28 per ciascuna cartuccia:
  - SE RADAR = ONDA NOTTURNA POSITIVA (Wall Street verde + VIX calmo + Titolo forte sopra VWAP):
    -> MANTIENE APERTA la cartuccia durante la notte (e se c'è liquidità libera compra il leader)
       per incassare il salto positivo ("Gap Up") delle ore 09:00 del mattino dopo!
  - SE RADAR = ONDA NOTTURNA NEGATIVA / PERICOLO (Wall Street rossa o VIX in allarme o Titolo debole):
    -> ATTIVA LO SCUDO ANTI-NOTTE: vende prima delle 17:30 e mette i profitti al sicuro in
       contanti EUR, schivando il ribasso notturno e tenendo le munizioni pronte per comprare
       a sconto alle 09:01 del mattino dopo!
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime
import json
import os
import sys
import time
import urllib.request
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo

MARKET_TZ = ZoneInfo("Europe/Rome")

from trading212_bot import (
    Trading212Client,
    Trading212AutonomousBot,
    EUR_ZERO_FEE_UNIVERSE,
    BASE_DIR,
    BOT_STATE_PATH,
)

CREDENTIALS_PATH = os.path.join(BASE_DIR, "t212_credentials.json")

ASSET_PROFILES: Dict[str, Dict[str, Any]] = {
    "RHMd_EQ": {
        "yahoo": "RHM.DE",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "DIFESA_AEROSPAZIO",
        "role_desc": "Turbo High-Beta Difesa/Aerospazio (Senza Tetto)",
        "ref_price_eur": 725.00,
        "shield_activation_pct": 0.0080,
        "shield_pullback_pct": 0.0018,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    "ENRd_EQ": {
        "yahoo": "ENR.DE",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "ENERGIA_RETI_AI",
        "role_desc": "Turbo High-Beta Energia & Reti Data Center AI (Senza Tetto)",
        "ref_price_eur": 56.50,
        "shield_activation_pct": 0.0078,
        "shield_pullback_pct": 0.0018,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    "ADYENa_EQ": {
        "yahoo": "ADYEN.AS",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "FINTECH_PAGAMENTI",
        "role_desc": "Turbo High-Beta Fintech & Pagamenti Globali (Senza Tetto)",
        "ref_price_eur": 1450.00,
        "shield_activation_pct": 0.0075,
        "shield_pullback_pct": 0.0017,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    "CBKd_EQ": {
        "yahoo": "CBK.DE",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "BANCHE_FINANZA",
        "role_desc": "Cecchino High-Beta Bancario DAX (Senza Tetto)",
        "ref_price_eur": 19.20,
        "shield_activation_pct": 0.0062,
        "shield_pullback_pct": 0.0014,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    "BESIa_EQ": {
        "yahoo": "BESI.AS",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "SEMICONDUTTORI_CHIP",
        "role_desc": "Turbo High-Beta Packaging Chip AI (Senza Tetto)",
        "ref_price_eur": 132.00,
        "shield_activation_pct": 0.0082,
        "shield_pullback_pct": 0.0019,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    "ZALd_EQ": {
        "yahoo": "ZAL.DE",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "ECOMMERCE_CONSUMER",
        "role_desc": "Cecchino High-Beta E-Commerce DAX (Senza Tetto)",
        "ref_price_eur": 32.50,
        "shield_activation_pct": 0.0065,
        "shield_pullback_pct": 0.0015,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    "DTEd_EQ": {
        "yahoo": "DTE.DE",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "TELECOMUNICAZIONI",
        "role_desc": "Incasso Veloce Intraday (Senza Tetto)",
        "ref_price_eur": 25.90,
        "shield_activation_pct": 0.0055,
        "shield_pullback_pct": 0.0013,
        "beta_tier": "DEFENSIVE_LOW_BETA",
    },
    "ALVd_EQ": {
        "yahoo": "ALV.DE",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "ASSICURAZIONI_FINANZA",
        "role_desc": "Incasso Veloce Intraday (Senza Tetto)",
        "ref_price_eur": 461.60,
        "shield_activation_pct": 0.0060,
        "shield_pullback_pct": 0.0014,
        "beta_tier": "CORE_BLUE_CHIP",
    },
    "SIEd_EQ": {
        "yahoo": "SIE.DE",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "INDUSTRIA_INFRASTRUTTURE",
        "role_desc": "Incasso Veloce / Rotazione (Senza Tetto)",
        "ref_price_eur": 279.50,
        "shield_activation_pct": 0.0065,
        "shield_pullback_pct": 0.0015,
        "beta_tier": "CORE_BLUE_CHIP",
    },
    "SAPd_EQ": {
        "yahoo": "SAP.DE",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "SOFTWARE_CLOUD",
        "role_desc": "Cavalca-Onda Lunga & Gap Notturno Selettivo (Senza Tetto)",
        "ref_price_eur": 217.80,
        "shield_activation_pct": 0.0072,
        "shield_pullback_pct": 0.0017,
        "beta_tier": "CORE_BLUE_CHIP",
    },
    "IFXd_EQ": {
        "yahoo": "IFX.DE",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "SEMICONDUTTORI_CHIP",
        "role_desc": "Cavalca-Onda Semiconduttori & Gap Notturno Selettivo (Senza Tetto)",
        "ref_price_eur": 49.70,
        "shield_activation_pct": 0.0078,
        "shield_pullback_pct": 0.0018,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    "ASMLa_EQ": {
        "yahoo": "ASML.AS",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "SEMICONDUTTORI_CHIP",
        "role_desc": "Cavalca-Onda AI/Chip & Gap Notturno Selettivo (Senza Tetto)",
        "ref_price_eur": 1313.00,
        "shield_activation_pct": 0.0080,
        "shield_pullback_pct": 0.0018,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    "BAYNd_EQ": {
        "yahoo": "BAYN.DE",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "PHARMA_BIOTECH",
        "role_desc": "Turbo High-Beta Farmaceutico & Biotech DAX (Senza Tetto)",
        "ref_price_eur": 56.60,
        "shield_activation_pct": 0.0070,
        "shield_pullback_pct": 0.0016,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    "VNAd_EQ": {
        "yahoo": "VNA.DE",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "REAL_ESTATE_TASSI",
        "role_desc": "Cecchino High-Beta Immobiliare & Sensibile ai Tassi (Senza Tetto)",
        "ref_price_eur": 17.25,
        "shield_activation_pct": 0.0065,
        "shield_pullback_pct": 0.0015,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    "AIRd_EQ": {
        "yahoo": "AIR.DE",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "AVIAZIONE_CIVILE_GLOBALE",
        "role_desc": "Cavalca-Onda Aviazione Civile & Aerospazio (Senza Tetto)",
        "ref_price_eur": 206.10,
        "shield_activation_pct": 0.0068,
        "shield_pullback_pct": 0.0015,
        "beta_tier": "CORE_BLUE_CHIP",
    },
}

VERIFIED_UNIVERSE_CACHE_PATH = os.path.join(BASE_DIR, "t212_verified_universe.json")

# BLINDATURA #20 (V8.8 Dynamic Radar "Stocks-In-Play" DAX 40 + AEX 25 in EUR a 0,00 EUR commissioni):
# Candidati aggiuntivi certificati per ISIN su XETRA (Germania) ed Euronext Amsterdam (Olanda).
CANDIDATE_EUR_GIANTS: List[Dict[str, Any]] = [
    {
        "fallback_ticker": "MTXd_EQ",
        "name": "MTU Aero Engines AG",
        "isin": "DE000A0D9PT0",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "MTX.DE",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "MOTORI_AEROSPAZIO",
        "role_desc": "Turbo High-Beta Motori Jet & Difesa DAX (Senza Tetto)",
        "ref_price_eur": 320.00,
        "shield_activation_pct": 0.0074,
        "shield_pullback_pct": 0.0017,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    {
        "fallback_ticker": "ASMa_EQ",
        "name": "ASM International NV",
        "isin": "NL0000334118",
        "exchange": "Euronext Amsterdam",
        "yahoo": "ASM.AS",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "SEMICONDUTTORI_CHIP",
        "role_desc": "Turbo High-Beta Wafer & Chip AI Olanda (Senza Tetto)",
        "ref_price_eur": 560.00,
        "shield_activation_pct": 0.0080,
        "shield_pullback_pct": 0.0018,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    {
        "fallback_ticker": "DBKd_EQ",
        "name": "Deutsche Bank AG",
        "isin": "DE0005140008",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "DBK.DE",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "BANCHE_FINANZA",
        "role_desc": "Cecchino High-Beta Investment Banking DAX (Senza Tetto)",
        "ref_price_eur": 16.50,
        "shield_activation_pct": 0.0064,
        "shield_pullback_pct": 0.0015,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    {
        "fallback_ticker": "MUV2d_EQ",
        "name": "Munich Re (Münchener Rück)",
        "isin": "DE0008430026",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "MUV2.DE",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "ASSICURAZIONI_FINANZA",
        "role_desc": "Colosso Riassicurativo Globale DAX (Senza Tetto)",
        "ref_price_eur": 485.00,
        "shield_activation_pct": 0.0060,
        "shield_pullback_pct": 0.0014,
        "beta_tier": "CORE_BLUE_CHIP",
    },
    {
        "fallback_ticker": "DTGd_EQ",
        "name": "Daimler Truck Holding AG",
        "isin": "DE000DTR0CK8",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "DTG.DE",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "VEICOLI_INDUSTRIALI",
        "role_desc": "Colosso Trasporti Pesanti & Mobilità DAX (Senza Tetto)",
        "ref_price_eur": 39.00,
        "shield_activation_pct": 0.0065,
        "shield_pullback_pct": 0.0015,
        "beta_tier": "CORE_BLUE_CHIP",
    },
    {
        "fallback_ticker": "ADSd_EQ",
        "name": "Adidas AG",
        "isin": "DE000A1EWW60",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "ADS.DE",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "CONSUMER_BRAND_GLOBALE",
        "role_desc": "Cavalca-Onda Sportswear & Brand Globale DAX (Senza Tetto)",
        "ref_price_eur": 220.00,
        "shield_activation_pct": 0.0070,
        "shield_pullback_pct": 0.0016,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    {
        "fallback_ticker": "MRKd_EQ",
        "name": "Merck KGaA",
        "isin": "DE0006599905",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "MRK.DE",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "PHARMA_BIOTECH",
        "role_desc": "Colosso Life Science & Chimica Semiconduttori DAX (Senza Tetto)",
        "ref_price_eur": 155.00,
        "shield_activation_pct": 0.0064,
        "shield_pullback_pct": 0.0015,
        "beta_tier": "CORE_BLUE_CHIP",
    },
    {
        "fallback_ticker": "SHLd_EQ",
        "name": "Siemens Healthineers AG",
        "isin": "DE000SHL1006",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "SHL.DE",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "MEDTECH_DIAGNOSTICA",
        "role_desc": "Colosso MedTech & Diagnostica AI DAX (Senza Tetto)",
        "ref_price_eur": 52.00,
        "shield_activation_pct": 0.0062,
        "shield_pullback_pct": 0.0014,
        "beta_tier": "CORE_BLUE_CHIP",
    },
    {
        "fallback_ticker": "EOANd_EQ",
        "name": "E.ON SE",
        "isin": "DE000ENAG999",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "EOAN.DE",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "UTILITIES_RETI_ELETTRICHE",
        "role_desc": "Incasso Veloce Difensivo Reti Elettriche Europee (Senza Tetto)",
        "ref_price_eur": 13.00,
        "shield_activation_pct": 0.0055,
        "shield_pullback_pct": 0.0013,
        "beta_tier": "DEFENSIVE_LOW_BETA",
    },
    {
        "fallback_ticker": "RWEd_EQ",
        "name": "RWE AG",
        "isin": "DE0007037129",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "RWE.DE",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "ENERGIA_RINNOVABILE_POWER",
        "role_desc": "Colosso Generazione Elettrica & Rinnovabili DAX (Senza Tetto)",
        "ref_price_eur": 32.00,
        "shield_activation_pct": 0.0062,
        "shield_pullback_pct": 0.0014,
        "beta_tier": "CORE_BLUE_CHIP",
    },
    {
        "fallback_ticker": "DHLd_EQ",
        "name": "DHL Group (Deutsche Post)",
        "isin": "DE0005552004",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "DHL.DE",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "LOGISTICA_GLOBALE",
        "role_desc": "Colosso Logistica & Spedizioni Mondiali DAX (Senza Tetto)",
        "ref_price_eur": 38.00,
        "shield_activation_pct": 0.0060,
        "shield_pullback_pct": 0.0014,
        "beta_tier": "CORE_BLUE_CHIP",
    },
    {
        "fallback_ticker": "BASd_EQ",
        "name": "BASF SE",
        "isin": "DE000BASF111",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "BAS.DE",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "CHIMICA_INDUSTRIALE",
        "role_desc": "Colosso Chimica Industriale Globale DAX (Senza Tetto)",
        "ref_price_eur": 45.00,
        "shield_activation_pct": 0.0062,
        "shield_pullback_pct": 0.0014,
        "beta_tier": "CORE_BLUE_CHIP",
    },
    {
        "fallback_ticker": "BMWd_EQ",
        "name": "BMW AG",
        "isin": "DE0005190003",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "BMW.DE",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "AUTOMOTIVE_PREMIUM",
        "role_desc": "Colosso Automotive Luxury DAX (Senza Tetto)",
        "ref_price_eur": 78.00,
        "shield_activation_pct": 0.0064,
        "shield_pullback_pct": 0.0015,
        "beta_tier": "CORE_BLUE_CHIP",
    },
    {
        "fallback_ticker": "INGAa_EQ",
        "name": "ING Groep NV",
        "isin": "NL0011821202",
        "exchange": "Euronext Amsterdam",
        "yahoo": "INGA.AS",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "BANCHE_FINANZA",
        "role_desc": "Colosso Bancario Europeo AEX Olanda (Senza Tetto)",
        "ref_price_eur": 16.00,
        "shield_activation_pct": 0.0060,
        "shield_pullback_pct": 0.0014,
        "beta_tier": "CORE_BLUE_CHIP",
    },
    {
        "fallback_ticker": "PRXa_EQ",
        "name": "Prosus NV",
        "isin": "NL0013654783",
        "exchange": "Euronext Amsterdam",
        "yahoo": "PRX.AS",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "TECH_HOLDING_AI",
        "role_desc": "Turbo High-Beta Tech & AI Global Holding AEX (Senza Tetto)",
        "ref_price_eur": 38.00,
        "shield_activation_pct": 0.0072,
        "shield_pullback_pct": 0.0016,
        "beta_tier": "TURBO_HIGH_BETA",
    },
]


def discover_and_verify_eur_giants(client: Trading212Client) -> int:
    """
    Interroga una sola volta il catalogo ufficiale di Trading 212 (/equity/metadata/instruments)
    o legge la cache locale verificata per attivare solo i ticker realmente negoziabili in EUR
    su XETRA (*d_EQ) ed Euronext Amsterdam (*a_EQ) corrispondenti agli ISIN ufficiali.
    """
    verified_map: Dict[str, str] = {}
    if os.path.exists(VERIFIED_UNIVERSE_CACHE_PATH):
        try:
            with open(VERIFIED_UNIVERSE_CACHE_PATH, "r", encoding="utf-8") as f:
                verified_map = json.load(f)
        except Exception:
            verified_map = {}

    if len(verified_map) < len(CANDIDATE_EUR_GIANTS):
        try:
            instruments = client._request("GET", "/equity/metadata/instruments")
            if isinstance(instruments, list):
                by_isin: Dict[str, List[Dict[str, Any]]] = {}
                for inst in instruments:
                    if inst.get("currencyCode") == "EUR":
                        isin_code = str(inst.get("isin", "")).strip()
                        if isin_code:
                            by_isin.setdefault(isin_code, []).append(inst)
                for cand in CANDIDATE_EUR_GIANTS:
                    c_isin = cand["isin"]
                    matches = by_isin.get(c_isin, [])
                    if matches:
                        preferred = [
                            m["ticker"]
                            for m in matches
                            if str(m.get("ticker", "")).endswith(("d_EQ", "a_EQ"))
                        ]
                        chosen_tkr = preferred[0] if preferred else str(matches[0].get("ticker", ""))
                        if chosen_tkr:
                            verified_map[c_isin] = chosen_tkr
                if verified_map:
                    with open(VERIFIED_UNIVERSE_CACHE_PATH, "w", encoding="utf-8") as f:
                        json.dump(verified_map, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[RADAR DISCOVERY] Uso universo base / cache locale ({e})", flush=True)

    added_count = 0
    for cand in CANDIDATE_EUR_GIANTS:
        tkr = verified_map.get(cand["isin"])
        if not tkr:
            continue
        EUR_ZERO_FEE_UNIVERSE[tkr] = {
            "name": cand["name"],
            "exchange": cand["exchange"],
            "currency": "EUR",
            "isin": cand["isin"],
            "tobin_tax": "0.00%",
        }
        ASSET_PROFILES[tkr] = {
            "yahoo": cand["yahoo"],
            "squad": cand["squad"],
            "sector": cand["sector"],
            "role_desc": cand["role_desc"],
            "ref_price_eur": cand["ref_price_eur"],
            "shield_activation_pct": cand["shield_activation_pct"],
            "shield_pullback_pct": cand["shield_pullback_pct"],
            "beta_tier": cand["beta_tier"],
        }
        added_count += 1
    return added_count


def compute_rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    recent = deltas[-period:]
    gains = sum(d for d in recent if d > 0) / period
    losses = sum(-d for d in recent if d < 0) / period
    if losses == 0:
        return 100.0 if gains > 0 else 50.0
    rs = gains / losses
    return round(100.0 - (100.0 / (1.0 + rs)), 1)


class OvernightWaveRadar:
    """
    Radar Predittivo dell'Onda Notturna (Wall Street + Indice della Paura VIX + DAX):
    Poiché New York apre alle 15:30 e Francoforte chiude alle 17:30, tra le 17:15 e le 17:28
    abbiamo quasi 2 ore di dati reali dagli USA per sapere se i grandi fondi americani stanno
    comprando (Onda Notturna Positiva -> tenere aperto per il salto delle 09:00) oppure
    vendendo (Onda Notturna Negativa -> incassare subito in EUR prima delle 17:30).
    """

    def __init__(self) -> None:
        self.last_check_ts: float = 0.0
        self.cached_radar: Dict[str, Any] = {}

    def _fetch_index_change_pct(self, symbol: str) -> float:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=5m&range=1d"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                res = data["chart"]["result"][0]
                meta = res.get("meta", {})
                prev_close = float(meta.get("chartPreviousClose") or meta.get("previousClose") or 0.0)
                closes = [
                    float(c)
                    for c in res["indicators"]["quote"][0].get("close", [])
                    if c is not None
                ]
                if closes and prev_close > 0:
                    return round(((closes[-1] - prev_close) / prev_close) * 100.0, 2)
                if len(closes) >= 2 and closes[0] > 0:
                    return round(((closes[-1] - closes[0]) / closes[0]) * 100.0, 2)
        except Exception:
            pass
        return 0.0

    def evaluate_overnight_wave(self, force: bool = False) -> Dict[str, Any]:
        now_ts = time.time()
        if not force and self.cached_radar and (now_ts - self.last_check_ts) < 120.0:
            return self.cached_radar

        sp500_pct = self._fetch_index_change_pct("%5EGSPC")
        nasdaq_pct = self._fetch_index_change_pct("%5EIXIC")
        dax_pct = self._fetch_index_change_pct("%5EGDAXI")
        vix_pct = self._fetch_index_change_pct("%5EVIX")

        # Regola istituzionale per prevedere l'Onda Notturna:
        # - Wall Street positiva (media Nasdaq + S&P500 >= +0.10%)
        # - Indice della Paura VIX calmo (non sta esplodendo oltre +2.5%)
        us_avg_pct = round((nasdaq_pct * 0.6 + sp500_pct * 0.4), 2)
        is_positive_wave = (us_avg_pct >= 0.10 and vix_pct <= 2.5) or (
            us_avg_pct >= 0.0 and dax_pct >= 0.35 and vix_pct <= 1.0
        )

        if is_positive_wave:
            verdict = "ONDA_NOTTURNA_POSITIVA_CAVALCA_IL_GAP_09_00"
            explanation = (
                f"Wall Street spinge al rialzo (Nasdaq {nasdaq_pct:+.2f}%, S&P500 {sp500_pct:+.2f}%, "
                f"VIX {vix_pct:+.2f}%): ALTA PROBABILITÀ di salto positivo domattina alle 09:00. "
                "Il bot MANTIENE APERTE per la notte le cartucce forti sopra il VWAP!"
            )
        else:
            verdict = "ONDA_NOTTURNA_INCERTA_O_NEGATIVA_SCUDO_ATTIVO"
            explanation = (
                f"Prudenza notturna (Nasdaq {nasdaq_pct:+.2f}%, S&P500 {sp500_pct:+.2f}%, "
                f"DAX {dax_pct:+.2f}%, VIX {vix_pct:+.2f}%): alle 17:15 il bot INCASSA IN CONTANTI EUR "
                "i profitti fatti in giornata per evitare cali notturni e comprare a sconto alle 09:00!"
            )

        self.cached_radar = {
            "verdict": verdict,
            "allow_overnight_hold": is_positive_wave,
            "nasdaq_change_pct": nasdaq_pct,
            "sp500_change_pct": sp500_pct,
            "dax_change_pct": dax_pct,
            "vix_fear_change_pct": vix_pct,
            "spiegazione_strategica": explanation,
        }
        self.last_check_ts = now_ts
        return self.cached_radar


class QuantMarketScanner:
    """Scanner quantitativo a 5 minuti con Fusione Zero-Latency (Tick Real-Time Trading 212 + Storico 5m)."""

    def __init__(self) -> None:
        self.live_prices: Dict[str, float] = {
            tkr: float(prof["ref_price_eur"]) for tkr, prof in ASSET_PROFILES.items()
        }
        self.has_t212_realtime: Dict[str, bool] = {}
        # Buffer di candele a 5 minuti costruite in tempo reale (0ms) dai prezzi live di Trading 212
        self.realtime_5m_bars: Dict[str, Dict[int, Dict[str, float]]] = {
            tkr: {} for tkr in ASSET_PROFILES
        }
        self.last_scan_ts: float = 0.0
        self.cached_metrics: Dict[str, Dict[str, Any]] = {}

    def update_t212_live_price(self, ticker: str, price_eur: float) -> None:
        if price_eur > 0 and ticker in ASSET_PROFILES:
            px = round(price_eur, 4)
            self.live_prices[ticker] = px
            self.has_t212_realtime[ticker] = True
            now_dt = datetime.datetime.now(MARKET_TZ)
            hm = now_dt.hour * 60 + now_dt.minute
            # Registra candele 5m real-time SOLO a mercato aperto (evita barre piatte notturne/weekend che distorcono RSI e ATR alle 09:00!)
            if now_dt.weekday() < 5 and (9 * 60 <= hm < 17 * 60 + 30):
                bucket_5m = int(time.time() // 300) * 300
                bars = self.realtime_5m_bars.setdefault(ticker, {})
                if bucket_5m not in bars:
                    bars[bucket_5m] = {"open": px, "high": px, "low": px, "close": px}
                else:
                    b = bars[bucket_5m]
                    b["high"] = max(b["high"], px)
                    b["low"] = min(b["low"], px)
                    b["close"] = px

    def fetch_5m_metrics(
        self,
        ticker: str,
        tax_data: Optional[Dict[str, Any]] = None,
        dax_change_pct: float = 0.0,
    ) -> Dict[str, Any]:
        prof = ASSET_PROFILES[ticker]
        ysymbol = prof["yahoo"]
        # V8.3: range=5d garantisce continuità matematica 09:00-09:20 evitando il buco di 0 candele di range=1d per il delay XETRA di 15m
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ysymbol}?interval=5m&range=5d"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)"},
        )
        closes: List[float] = []
        highs: List[float] = []
        lows: List[float] = []
        vols: List[float] = []
        bar_timestamps: List[int] = []
        last_yahoo_ts: int = 0
        yahoo_today_bars: int = 0
        today_date = datetime.datetime.now(MARKET_TZ).date()
        try:
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                result = data["chart"]["result"][0]
                meta_info = result.get("meta", {})
                reg_px = meta_info.get("regularMarketPrice")
                if reg_px and not self.has_t212_realtime.get(ticker):
                    self.live_prices[ticker] = round(float(reg_px), 4)
                timestamps = result.get("timestamp", [])
                quote = result["indicators"]["quote"][0]
                for ts, c, h, l, v in zip(
                    timestamps,
                    quote.get("close", []),
                    quote.get("high", []),
                    quote.get("low", []),
                    quote.get("volume", []),
                ):
                    if c is not None and h is not None and l is not None:
                        closes.append(float(c))
                        highs.append(float(h))
                        lows.append(float(l))
                        vols.append(float(v or 0.0))
                        ts_int = int(ts)
                        bar_timestamps.append(ts_int)
                        last_yahoo_ts = ts_int
                        if datetime.datetime.fromtimestamp(ts_int, tz=MARKET_TZ).date() == today_date:
                            yahoo_today_bars += 1
        except Exception:
            pass

        # BLINDATURA #11: Fusione Zero-Latency (0ms) - filtra eventuali barre fuori orario di borsa
        rt_bars = self.realtime_5m_bars.get(ticker, {})
        avg_vol_est = (sum(vols[-6:]) / 6.0) if len(vols) >= 6 else 1000.0
        for b_ts in sorted(rt_bars.keys()):
            b_dt = datetime.datetime.fromtimestamp(b_ts, tz=MARKET_TZ)
            b_hm = b_dt.hour * 60 + b_dt.minute
            if b_dt.weekday() < 5 and (9 * 60 <= b_hm < 17 * 60 + 30) and b_ts > last_yahoo_ts:
                b = rt_bars[b_ts]
                closes.append(b["close"])
                highs.append(b["high"])
                lows.append(b["low"])
                vols.append(avg_vol_est)
                bar_timestamps.append(b_ts)

        if closes:
            last_c = self.live_prices.get(ticker, closes[-1])
            if abs(last_c - closes[-1]) > 1e-4:
                closes.append(last_c)
                highs.append(max(last_c, closes[-2]))
                lows.append(min(last_c, closes[-2]))
                vols.append(avg_vol_est)
                bar_timestamps.append(int(time.time()))
            rsi_14 = compute_rsi(closes, 14)
            # Calcola VWAP e High/Low sulla seduta odierna (o sulle ultime 24 barre reali tra le 09:00 e le 09:15)
            today_date = datetime.datetime.now(MARKET_TZ).date()
            today_indices = [
                idx
                for idx, ts_val in enumerate(bar_timestamps)
                if datetime.datetime.fromtimestamp(ts_val, tz=MARKET_TZ).date() == today_date
            ]
            if len(today_indices) >= 1:
                sess_closes = [closes[i] for i in today_indices]
                sess_highs = [highs[i] for i in today_indices]
                sess_lows = [lows[i] for i in today_indices]
                sess_vols = [vols[i] for i in today_indices]
            else:
                sess_closes = closes[-24:]
                sess_highs = highs[-24:]
                sess_lows = lows[-24:]
                sess_vols = vols[-24:]
            day_high = max(max(sess_highs), last_c) if sess_highs else last_c
            day_low = min(min(sess_lows), last_c) if sess_lows else last_c
            dip_from_high_pct = ((last_c - day_high) / day_high) * 100.0 if day_high > 0 else 0.0
            day_range_pct = ((day_high - day_low) / day_low) * 100.0 if day_low > 0 else 1.2
            tot_vol = sum(sess_vols)
            vwap = (
                sum(c * v for c, v in zip(sess_closes, sess_vols)) / tot_vol
                if tot_vol > 0
                else sum(sess_closes) / len(sess_closes)
            )
            vwap_dist_pct = ((last_c - vwap) / vwap) * 100.0 if vwap > 0 else 0.0
        else:
            today_indices = []
            last_c = self.live_prices.get(ticker, float(prof["ref_price_eur"]))
            rsi_14 = 48.0
            dip_from_high_pct = -0.50
            day_range_pct = 1.50
            vwap_dist_pct = -0.15

        if len(closes) >= 6:
            first_today_idx = today_indices[0] if today_indices else 0
            ref_idx_2 = max(first_today_idx, len(closes) - 2)
            ref_idx_3 = max(first_today_idx, len(closes) - 3)
            ref_idx_4 = max(first_today_idx, len(closes) - 4)
            ref_idx_7 = max(first_today_idx, len(closes) - 7)
            price_turning_down = (closes[-1] < closes[ref_idx_2])
            falling_knife = (closes[-1] < closes[ref_idx_2] and closes[ref_idx_2] < closes[ref_idx_3])
            breakout_candle = (closes[-1] > highs[ref_idx_2]) if len(highs) >= 2 else False
            higher_low = (lows[-1] >= lows[ref_idx_2]) if len(lows) >= 2 else True
            green_hook_confirmed = not falling_knife and (closes[-1] >= closes[ref_idx_2] or higher_low)
            slope_rising = (closes[-1] >= closes[ref_idx_3])
            slope_15m_pct = ((closes[-1] - closes[ref_idx_4]) / closes[ref_idx_4] * 100.0) if closes[ref_idx_4] > 0 else 0.0
            slope_30m_pct = ((closes[-1] - closes[ref_idx_7]) / closes[ref_idx_7] * 100.0) if closes[ref_idx_7] > 0 else slope_15m_pct
            avg_recent_vol = sum(vols[-6:-1]) / 5.0 if sum(vols[-6:-1]) > 0 else 1.0
            volume_drying_up = (vols[-1] < avg_recent_vol * 0.90)
            rvol_ratio = round(vols[-1] / avg_recent_vol, 2) if avg_recent_vol > 0 else 1.0
            # BLINDATURA #8: Calcolo ATR (Average True Range) a 5m per Scudo Elastico sulla Volatilità
            tr_pcts: List[float] = []
            start_idx = max(1, len(closes) - 14)
            for i in range(start_idx, len(closes)):
                prev_c = closes[i - 1]
                if prev_c > 0:
                    tr = max(
                        highs[i] - lows[i],
                        abs(highs[i] - prev_c),
                        abs(lows[i] - prev_c),
                    )
                    tr_pcts.append(tr / prev_c)
            atr_5m_pct = (sum(tr_pcts) / len(tr_pcts)) if tr_pcts else 0.0018

            # BLINDATURA #13 (Pilastro 2): Indice di Pulizia dell'Onda di Kaufman (Efficiency Ratio 10 barre)
            k_win = min(10, len(closes) - 1)
            net_move = abs(closes[-1] - closes[-1 - k_win])
            path_move = sum(abs(closes[j] - closes[j - 1]) for j in range(len(closes) - k_win, len(closes)))
            kaufman_er = round(net_move / path_move, 2) if path_move > 0 else 0.35
        else:
            ref_idx_2 = max(0, len(closes) - 2)
            price_turning_down = False
            breakout_candle = False
            higher_low = True
            green_hook_confirmed = True
            slope_rising = True
            slope_15m_pct = 0.10
            slope_30m_pct = 0.15
            volume_drying_up = False
            rvol_ratio = 1.0
            atr_5m_pct = 0.0018
            kaufman_er = 0.35

        # MOTORE V9.1 MULTI-STRATEGIA + PAVIMENTO VWAP (Ingresso attaccato al VWAP, Veto sugli acquisti estesi):
        # 1) STRATEGIA A - MOMENTUM BREAKOUT (Premia 0,00%..+0,45% sopra VWAP; penalizza chi è già scappato > +0,48%):
        if vwap_dist_pct >= -0.15 and (slope_15m_pct >= -0.10 or slope_rising) and 42.0 <= rsi_14 <= 67.5 and green_hook_confirmed:
            rsi_crest_taper = max(0.0, (rsi_14 - 62.0) * 2.5)
            vwap_extension_taper = max(0.0, (vwap_dist_pct - 0.48) * 36.0)
            vwap_floor_bonus = (
                16.0
                if -0.05 <= vwap_dist_pct <= 0.45
                else min(14.0, max(0.0, (vwap_dist_pct + 0.15) * 14.0))
            )
            score_momentum = (
                58.0
                + vwap_floor_bonus
                + min(18.0, max(0.0, (slope_15m_pct + 0.10) * 28.0))
                + (kaufman_er * 14.0)
                + (6.0 if breakout_candle else 0.0)
                - rsi_crest_taper
                - vwap_extension_taper
            )
        else:
            score_momentum = 0.0

        # 2) STRATEGIA B - INSTITUTIONAL VWAP PULLBACK (Copre senza buchi RSI 32..64 attaccato al pavimento VWAP):
        if vwap_dist_pct >= -0.38 and 32.0 <= rsi_14 <= 64.0 and green_hook_confirmed and slope_30m_pct >= -0.45:
            pullback_ext_taper = max(0.0, (vwap_dist_pct - 0.48) * 32.0)
            score_pullback = (
                54.0
                + min(24.0, max(0.0, (64.0 - rsi_14) * 0.95))
                + (12.0 if breakout_candle else 4.0)
                + (kaufman_er * 12.0)
                - pullback_ext_taper
            )
        else:
            score_pullback = 0.0

        # 3) STRATEGIA C - V-BOTTOM SPRING REVERSAL (Solo rimbalzo reale con candela verde closes[-1] > closes[-2]):
        #    Gerarchia V8.9: il contro-trend sotto VWAP ha sempre priorità inferiore rispetto ai Leader sopra il VWAP!
        real_green_bounce = (len(closes) >= 2 and closes[-1] > closes[ref_idx_2] and higher_low)
        if rsi_14 < 38.0 and green_hook_confirmed and (breakout_candle or (real_green_bounce and rsi_14 < 32.0)):
            score_reversal = (
                46.0
                + min(14.0, (38.0 - rsi_14) * 0.85)
                + min(8.0, abs(min(0.0, dip_from_high_pct)) * 3.0)
            )
        else:
            # Se un titolo è sotto il VWAP in trend discendente senza inversione reale, VETO sui falsi rimbalzi!
            score_reversal = max(0.0, min(20.0, (55.0 - rsi_14) * 0.35)) if vwap_dist_pct < -0.55 else 22.0

        base_opp_score = max(score_momentum, score_pullback, score_reversal)

        # BLINDATURA #13: Selettore Dinamico High-Beta "Profit-Velocity Ranker" (4 Pilastri + Cambio Marcia DAX)
        # 1) Potenziale di Velocità di Profitto:
        #    - Con mercato normale/positivo (DAX > -0,50%): spinge sui TURBO_HIGH_BETA (1.12x)
        #    - Con giornata storta/ribassista (DAX <= -0,50%): frena i TURBO_HIGH_BETA (0.82x) e premia i
        #      CORE_BLUE_CHIP / DEFENSIVE_LOW_BETA di ieri (1.18x) che hanno scudi stretti e incassano subito!
        wave_power_pct = (atr_5m_pct * 100.0 * 3.5) + (day_range_pct * 0.45)
        beta_tier = prof.get("beta_tier", "CORE_BLUE_CHIP")
        # Selettore Intelligente Lento/Sicuro vs Veloce/Turbo basato sulla Forza Relativa Reale (Alpha vs VWAP):
        # - Se un titolo TURBO_HIGH_BETA è SOPRA il suo VWAP in spinta (score_momentum >= 55 o score_pullback >= 54),
        #   ha Forza Relativa Istituzionale (Alpha > 0) anche a DAX rosso -> riceve il massimo boost 1.18x!
        # - Se invece il mercato è debole (DAX <= -0,50%) e il titolo Turbo è SOTTO il VWAP, viene frenato (0.78x)
        #   e il bot premia automaticamente i colossi sicuri (CORE_BLUE_CHIP / DEFENSIVE_LOW_BETA = 1.18x)!
        has_institutional_alpha = (vwap_dist_pct >= -0.05 and (score_momentum >= 55.0 or score_pullback >= 54.0))
        if beta_tier == "TURBO_HIGH_BETA" and has_institutional_alpha:
            tier_boost = 1.18
        elif dax_change_pct <= -0.50:
            tier_boost = (
                1.18
                if beta_tier in ("CORE_BLUE_CHIP", "DEFENSIVE_LOW_BETA")
                else 0.78
            )
        else:
            tier_boost = (
                1.14
                if beta_tier == "TURBO_HIGH_BETA"
                else (0.88 if beta_tier == "DEFENSIVE_LOW_BETA" else 1.02)
            )
        profit_velocity_mult = round(max(0.75, min(1.55, (0.75 + wave_power_pct * 0.25) * tier_boost)), 2)

        # 2) Bonus Pulizia Onda di Kaufman (premia onde direzionali pulite, penalizza rumore sporco)
        er_bonus = round((kaufman_er - 0.25) * 18.0, 1)
        er_bonus = max(-6.0, min(10.0, er_bonus))

        # 3) Bonus Spinta Volumi Istituzionali su Uncino Verde
        rvol_bonus = 8.0 if (green_hook_confirmed and rvol_ratio >= 1.15) else 0.0

        # 4) BLINDATURA #17 & #20 - Selettore Dinamico di Regime (Zero Whitelist/Blacklist fisse):
        #    - Se un titolo ha storico negativo (es. Adyen, Zalando, Infineon <= -0,35 EUR), NON viene bannato a vita:
        #      finché resta debole/sporco o sotto il VWAP viene parcheggiato in tribuna (-35 pt),
        #      ma se esplode in vero Breakout Istituzionale sopra il VWAP (vwap >= +0,18%, Kaufman >= 0.32, Uncino Verde)
        #      la penalità storica si azzera istantaneamente per cavalcare il rialzo!
        memory_bonus = 0.0
        if tax_data and "operazioni_chiuse" in tax_data:
            ops_tkr = [
                op for op in tax_data.get("operazioni_chiuse", [])
                if op.get("ticker") == ticker
            ]
            tkr_pnl = sum(float(op.get("risultato_fiscale_eur", 0.0)) for op in ops_tkr)
            is_clean_institutional_breakout = (
                vwap_dist_pct >= 0.18
                and score_momentum >= 60.0
                and kaufman_er >= 0.32
                and green_hook_confirmed
            )
            if tkr_pnl <= -0.35 and len(ops_tkr) >= 4:
                memory_bonus = 0.0 if is_clean_institutional_breakout else -35.0
            else:
                memory_bonus = max(-5.0, min(8.0, round(tkr_pnl * 6.0, 1)))
            today_prefix = datetime.date.today().isoformat()
            today_ops = [
                op for op in ops_tkr
                if str(op.get("timestamp", "")).startswith(today_prefix)
            ]
            if today_ops:
                last_today_pnl = float(today_ops[-1].get("risultato_fiscale_eur", 0.0))
                today_wins = sum(1 for op in today_ops if float(op.get("risultato_fiscale_eur", 0.0)) > 0.0)
                today_losses = sum(1 for op in today_ops if float(op.get("risultato_fiscale_eur", 0.0)) < 0.0)
                if today_losses >= 2 and today_wins < today_losses:
                    memory_bonus = -55.0
                elif last_today_pnl < 0.0:
                    memory_bonus = min(memory_bonus, -22.0)
                elif today_wins >= 2 and today_losses == 0:
                    memory_bonus = max(memory_bonus, min(10.0, round(today_wins * 3.0, 1)))

        # V9.1 Fascia d'Oro Velocità + Gerarchia Pavimento VWAP (Né Tartarughe Immobili, Né Cavalli Pazzi Sporchi):
        atr_pct_100 = atr_5m_pct * 100.0
        now_cet_scan = datetime.datetime.now(MARKET_TZ)
        range_matured = (now_cet_scan.hour > 9) or (now_cet_scan.hour == 9 and now_cet_scan.minute >= 45)
        is_sluggish_turtle = (
            dax_change_pct > -0.50
            and range_matured
            and atr_pct_100 < 0.135
            and day_range_pct < 1.45
        )
        wild_chop_penalty = -18.0 if (atr_pct_100 > 0.38 and kaufman_er < 0.30) else 0.0
        golden_zone_bonus = (
            7.0
            if (
                0.145 <= atr_pct_100 <= 0.34
                and (not range_matured or 1.50 <= day_range_pct <= 4.20)
                and kaufman_er >= 0.24
                and -0.12 <= vwap_dist_pct <= 0.48
            )
            else 0.0
        )

        max_tech_cap = 100.0 if vwap_dist_pct >= -0.20 else 72.0
        if is_sluggish_turtle:
            max_tech_cap = min(max_tech_cap, 62.0)
        tech_score_capped = min(
            max_tech_cap,
            (base_opp_score * profit_velocity_mult)
            + er_bonus
            + rvol_bonus
            + golden_zone_bonus
            + wild_chop_penalty,
        )
        quant_score = round(
            max(0.0, min(100.0, tech_score_capped + memory_bonus)),
            1,
        )

        # Fattore elastico ATR (tra 0.80x su mercato piatto e 1.30x su mercato esplosivo)
        vol_scale = round(max(0.80, min(1.30, atr_5m_pct / 0.0018)), 2)
        base_act = float(prof["shield_activation_pct"])
        base_pull = float(prof["shield_pullback_pct"])
        elastic_shield_act = round(base_act * vol_scale, 4)
        elastic_shield_pull = round(base_pull * vol_scale, 4)

        if rsi_14 > 68.0 and price_turning_down and volume_drying_up:
            sine_phase = "CRESTA_IN_INVERSIONE_FALSO_POSITIVO"
            strong_for_overnight = False
        elif score_momentum >= 55.0 or (rsi_14 > 60.0 and (not price_turning_down or slope_rising or vwap_dist_pct >= 0.0)):
            sine_phase = "SUPER_TREND_VERO_POSITIVO_BREAKOUT"
            strong_for_overnight = True
        elif score_pullback >= 52.0 or (36.0 <= rsi_14 <= 64.0 and (slope_rising or green_hook_confirmed) and vwap_dist_pct >= -0.55):
            sine_phase = "ONDA_ASCENDENTE_SANA_VERO_POSITIVO"
            strong_for_overnight = True
        elif score_reversal >= 50.0 or (rsi_14 < 38.0 and green_hook_confirmed):
            sine_phase = "VALLE_CON_UNCINO_VERDE_PRONTO_ACQUISTO"
            strong_for_overnight = False
        elif rsi_14 < 38.0:
            sine_phase = "COLTELLO_IN_CADUTA_ATTENDERE_UNCINO_VERDE"
            strong_for_overnight = False
        else:
            sine_phase = "ONDA_DISCENDENTE_O_DEBOLE"
            strong_for_overnight = False

        return {
            "ticker": ticker,
            "name": EUR_ZERO_FEE_UNIVERSE[ticker]["name"],
            "squad": prof["squad"],
            "sector": prof["sector"],
            "beta_tier": beta_tier,
            "role_desc": prof["role_desc"],
            "live_price_eur": round(last_c, 2),
            "rsi_5m": rsi_14,
            "dip_from_high_pct": round(dip_from_high_pct, 2),
            "day_range_pct": round(day_range_pct, 2),
            "vwap_dist_pct": round(vwap_dist_pct, 2),
            "atr_5m_volatility_pct": round(atr_5m_pct * 100, 3),
            "atr_elastic_scale": vol_scale,
            "profit_velocity_mult": profit_velocity_mult,
            "kaufman_efficiency_ratio": kaufman_er,
            "rvol_ratio": rvol_ratio,
            "memory_730_bonus": memory_bonus,
            "quant_buy_score": quant_score,
            "fase_onda_sinusoidale": sine_phase,
            "green_hook_confirmed": green_hook_confirmed,
            "strong_for_overnight": strong_for_overnight,
            "yahoo_today_bars": yahoo_today_bars,
            "has_fresh_intraday_feed": (yahoo_today_bars >= 2 or len(today_indices) >= 2),
            "shield_activation_pct": round(elastic_shield_act * 100, 2),
            "shield_pullback_pct": round(elastic_shield_pull * 100, 2),
            "elastic_shield_act_raw": elastic_shield_act,
            "elastic_shield_pull_raw": elastic_shield_pull,
            "pre_shield_breakeven_trigger_pct": 0.60,
            "pre_shield_breakeven_floor_pct": 0.25,
            "tetto_massimo_rialzo": "NESSUN TETTO (Lascia correre i profitti)",
        }

    def scan_all(
        self,
        tax_data: Optional[Dict[str, Any]] = None,
        dax_change_pct: float = 0.0,
        force: bool = False,
        active_tickers: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        now_ts = time.time()
        # Architettura Split-Speed Turbo V9.0 (6s Posizioni Aperte / 24s Radar Globale 29 Titoli):
        # - Ogni 24s (o subito se c'è una cartuccia libera da investire: force=True) scansiona tutti i 29 Colossi.
        # - Nei cicli intermedi da 6s aggiorna a latenza zero le sole cartucce aperte in portafoglio!
        full_radar_due = force or not self.cached_metrics or (now_ts - self.last_scan_ts) >= 22.0
        if full_radar_due:
            tickers = list(ASSET_PROFILES.keys())
            results: Dict[str, Dict[str, Any]] = {}
            with ThreadPoolExecutor(max_workers=20) as pool:
                futures = {
                    tkr: pool.submit(self.fetch_5m_metrics, tkr, tax_data, dax_change_pct)
                    for tkr in tickers
                }
                for tkr, fut in futures.items():
                    results[tkr] = fut.result()
            self.cached_metrics = results
            self.last_scan_ts = now_ts
            return results
        else:
            results = dict(self.cached_metrics)
            open_list = [t for t in (active_tickers or []) if t in ASSET_PROFILES]
            if open_list:
                with ThreadPoolExecutor(max_workers=max(1, len(open_list))) as pool:
                    futures = {
                        tkr: pool.submit(self.fetch_5m_metrics, tkr, tax_data, dax_change_pct)
                        for tkr in open_list
                    }
                    for tkr, fut in futures.items():
                        results[tkr] = fut.result()
            self.cached_metrics = results
            return results


class HybridUncappedIntelligence:
    """
    Motore Ibrido 2+2 Senza Tetto + Selettore Onda Notturna (17:15-17:30):
    - Di giorno: non taglia MAI i rialzi mentre corrono (Scudo Mobile Senza Tetto).
    - Alle 17:15-17:30: interroga il Radar Wall Street + VIX + VWAP:
      * Se si prevede un'Onda Notturna Positiva E il titolo è forte sopra il VWAP -> MANTIENE APERTO
        per catturare il salto ("Gap Up") delle 09:00 del mattino dopo!
      * Se si prevede un'Onda Notturna Negativa/Incerta (o il titolo è debole) -> VENDE E INCASSA
        prima delle 17:30 per proteggere al 100% i profitti!
    """

    def __init__(self) -> None:
        self.peak_pnl_pct: Dict[str, float] = {}
        self.last_sell_price: Dict[str, float] = {}
        self.last_sell_time: Dict[str, float] = {}
        self.last_sell_was_loss: Dict[str, bool] = {}
        self.position_open_time: Dict[str, float] = {}
        self._load_persisted_peaks()

    def _load_persisted_peaks(self) -> None:
        if os.path.exists(BOT_STATE_PATH):
            try:
                with open(BOT_STATE_PATH, "r", encoding="utf-8") as f:
                    st = json.load(f)
                for c in st.get("cartucce_4x25_eur", []):
                    tkr = c.get("ticker")
                    pk = c.get("peak_pnl_pct")
                    op_ts = c.get("opened_at_ts")
                    if tkr and pk is not None:
                        self.peak_pnl_pct[tkr] = float(pk) / 100.0
                    if tkr and op_ts is not None:
                        self.position_open_time[tkr] = float(op_ts)
            except Exception:
                pass
        tax_path = os.path.join(BASE_DIR, "registro_fiscale_730.json")
        if os.path.exists(tax_path):
            try:
                with open(tax_path, "r", encoding="utf-8") as f:
                    tx = json.load(f)
                for tkr, lots in tx.get("lotti_aperti_lifo", {}).items():
                    if lots:
                        ts_str = lots[-1].get("timestamp", "")
                        if ts_str:
                            dt = datetime.datetime.fromisoformat(ts_str)
                            self.position_open_time[tkr] = dt.timestamp()
                today_prefix_init = datetime.date.today().isoformat()
                for op in tx.get("operazioni_chiuse", []):
                    tkr_op = op.get("ticker")
                    ts_op = str(op.get("timestamp", ""))
                    px_op = op.get("sell_price_eur")
                    pnl_op = float(op.get("risultato_fiscale_eur", 0.0))
                    if tkr_op and ts_op and px_op is not None:
                        dt_op = datetime.datetime.fromisoformat(ts_op)
                        self.last_sell_time[tkr_op] = dt_op.timestamp()
                        self.last_sell_price[tkr_op] = float(px_op)
                        self.last_sell_was_loss[tkr_op] = (
                            (pnl_op < 0.0) and ts_op.startswith(today_prefix_init)
                        )
            except Exception:
                pass

    def get_intraday_regime(self, now: datetime.datetime) -> Dict[str, Any]:
        hm = now.hour * 60 + now.minute
        is_friday = (now.weekday() == 4)
        if now.weekday() >= 5:
            return {
                "code": "WEEKEND_BORSA_CHIUSA",
                "description": "Mercati chiusi per il weekend",
                "market_open": False,
                "allow_new_buys": False,
                "is_pre_close_window": False,
                "is_morning_gap_harvest": False,
                "is_friday_pre_weekend": False,
            }
        if hm < 9 * 60 or hm >= 17 * 60 + 30:
            return {
                "code": "DOPOBORSA_NOTTURNO",
                "description": "Borsa XETRA chiusa (09:00-17:30)",
                "market_open": False,
                "allow_new_buys": False,
                "is_pre_close_window": False,
                "is_morning_gap_harvest": False,
                "is_friday_pre_weekend": False,
            }
        if 9 * 60 <= hm < 9 * 60 + 30:
            return {
                "code": "FASE_1A_RACCOLTO_GAP_MATTUTINO_ANTI_GAP_FILL",
                "description": "09:00-09:30: Scudo Ultra-Reattivo (+0,50% / -0,14%) per blindare il salto della notte prima che si sgonfi",
                "market_open": True,
                "allow_new_buys": True,
                "is_pre_close_window": False,
                "is_morning_gap_harvest": True,
                "is_friday_pre_weekend": False,
            }
        if 9 * 60 + 30 <= hm < 10 * 60 + 30:
            return {
                "code": "FASE_1B_SPRINT_MATTUTINO_SENZA_TETTO",
                "description": "09:30-10:30: Sprint direzionale mattutino senza tetto ai rialzi",
                "market_open": True,
                "allow_new_buys": True,
                "is_pre_close_window": False,
                "is_morning_gap_harvest": False,
                "is_friday_pre_weekend": False,
            }
        if 14 * 60 + 28 <= hm <= 14 * 60 + 35:
            return {
                "code": "PAUSA_ANTI_SHOCK_DATI_MACRO_USA_14_30",
                "description": "14:28-14:35: Scudo Anti-Stop-Hunting durante uscita dati Inflazione/Lavoro USA (Scudi vendita attivi, nuovi acquisti in pausa 7 min)",
                "market_open": True,
                "allow_new_buys": False,
                "is_pre_close_window": False,
                "is_morning_gap_harvest": False,
                "is_friday_pre_weekend": False,
                "is_lunch_desert_window": True,
            }
        if 11 * 60 + 15 <= hm < 14 * 60 + 28:
            return {
                "code": "FASE_2_SCUDO_DESERTO_MEZZOGIORNO_11_15_14_35",
                "description": "11:15-14:35: Scudo Pausa Pranzo Europea — gestione/incasso posizioni aperte, stop acquisti ordinari (attesa volumi USA 14:35)",
                "market_open": True,
                "allow_new_buys": True,
                "is_pre_close_window": False,
                "is_morning_gap_harvest": False,
                "is_friday_pre_weekend": False,
                "is_lunch_desert_window": True,
            }
        if 10 * 60 + 30 <= hm < 15 * 60 + 30:
            return {
                "code": "FASE_2_IBRIDA_2X2_BLINDATA_V5",
                "description": "10:30-11:15 & 14:36-15:30: Sessione Istituzionale Attiva (Fascia d'Oro + Pavimento VWAP)",
                "market_open": True,
                "allow_new_buys": True,
                "is_pre_close_window": False,
                "is_morning_gap_harvest": False,
                "is_friday_pre_weekend": False,
                "is_lunch_desert_window": False,
            }
        if 17 * 60 + 15 <= hm < 17 * 60 + 30:
            return {
                "code": "FASE_4_RADAR_SELETTORE_ONDA_NOTTURNA_E_WEEKEND",
                "description": "17:15-17:30: Selettore Vero/Falso Positivo + Evacuazione Totale su Pericolo USA + Scudo Weekend Venerdì",
                "market_open": True,
                "allow_new_buys": True,
                "is_pre_close_window": True,
                "is_morning_gap_harvest": False,
                "is_friday_pre_weekend": is_friday,
            }
        return {
            "code": "FASE_3_ONDA_WALL_STREET_SENZA_TETTO",
            "description": "15:30-17:15: Spinta USA - Pre-Scudo Salva-Utile + Scudo Mobile Senza Tetto",
            "market_open": True,
            "allow_new_buys": True,
            "is_pre_close_window": False,
            "is_morning_gap_harvest": False,
            "is_friday_pre_weekend": False,
        }

    def evaluate_uncapped_exit(
        self,
        ticker: str,
        pnl_pct: float,
        regime: Dict[str, Any],
        best_bench_score: float,
        overnight_radar: Dict[str, Any],
        ticker_metrics: Dict[str, Any],
        realized_net_eur: float = 0.0,
        has_green_hook_bench: bool = False,
    ) -> Optional[str]:
        prof = ASSET_PROFILES.get(ticker, ASSET_PROFILES["SAPd_EQ"])
        # BLINDATURA #8: Usa lo Scudo Elastico adattato alla volatilità ATR a 5m
        atr_raw = float(ticker_metrics.get("atr_5m_volatility_pct", 0.18)) / 100.0
        shield_act = max(0.0072, float(ticker_metrics.get("elastic_shield_act_raw", prof["shield_activation_pct"])))
        shield_pull = max(0.0018, float(ticker_metrics.get("elastic_shield_pull_raw", prof["shield_pullback_pct"])))

        # BLINDATURA #10 + Calibrazione Simmetrica V8.7 (Mossa A: Scala Progressiva Salva-Utile + Zero Strangolamento sopra VWAP)
        daily_vault_active = (realized_net_eur >= 1.60)
        breakeven_trigger = max(0.0040 if daily_vault_active else 0.0042, min(0.0050, round(atr_raw * 2.1, 4)))
        breakeven_floor = max(0.0016 if daily_vault_active else 0.0018, round(breakeven_trigger * 0.45, 4))
        mid_tier_trigger = 0.0058  # ~+0,15 EUR: alza subito il pavimento garantito a +0,38%..+0,44% (~+0,10..+0,11 EUR)!
        mid_tier_floor = 0.0040

        sine_phase = ticker_metrics.get("fase_onda_sinusoidale", "")
        stock_is_strong = bool(ticker_metrics.get("strong_for_overnight", False))
        green_hook_ok = bool(ticker_metrics.get("green_hook_confirmed", False))
        vwap_dist = float(ticker_metrics.get("vwap_dist_pct", 0.0))
        cur_rsi_5m = float(ticker_metrics.get("rsi_5m", 50.0))

        prev_peak = self.peak_pnl_pct.get(ticker, pnl_pct)
        new_peak = max(prev_peak, pnl_pct)
        self.peak_pnl_pct[ticker] = new_peak

        # BLINDATURA #3: Raccolto del Salto Mattutino 09:00-09:30 (Anti-Gap-Fill)
        if regime.get("is_morning_gap_harvest"):
            if new_peak >= 0.0055 and (new_peak - pnl_pct) >= 0.0015 and pnl_pct >= 0.0035:
                return (
                    f"BLINDATURA #3 - RACCOLTO GAP MATTUTINO (09:00-09:30): blindato salto notturno "
                    f"dal picco +{new_peak*100:.2f}% a +{pnl_pct*100:.2f}% prima del Gap-Fill!"
                )

        # BLINDATURA #1 (Stadio 2) + BLINDATURA #8 (ATR Elastico): Scudo Mobile Senza Tetto
        if new_peak >= shield_act and (new_peak - pnl_pct) >= shield_pull and pnl_pct >= 0.0045:
            return (
                f"SCUDO MOBILE ELASTICO SENZA TETTO ({prof['squad']}): cavalcato rialzo fino al picco "
                f"di +{new_peak*100:.2f}% e incassato su inversione a +{pnl_pct*100:.2f}%"
            )

        # BLINDATURA #1 (Stadio 1B - Gradino Progressivo Intermedio):
        # Se il titolo ha già toccato >= +0,58% (~+0,15 EUR), non può MAI più ridiscendere a +0,02 EUR!
        # Se è ancora fortissimo sopra il VWAP (>= +0,15%), NON svenderlo mai sotto +0,36% (~+0,09..+0,11 EUR)!
        if new_peak >= mid_tier_trigger and 0.0018 <= pnl_pct <= mid_tier_floor:
            strong_above_vwap_hold = (
                (vwap_dist >= 0.15 and cur_rsi_5m >= 38.0 and pnl_pct < 0.0036)
                or (vwap_dist >= 0.08 and green_hook_ok and pnl_pct >= 0.0034)
            )
            if not strong_above_vwap_hold:
                return (
                    f"BLINDATURA #1B - SCALA PROGRESSIVA SALVA-UTILE: {ticker} aveva toccato "
                    f"il picco di +{new_peak*100:.2f}% e ha blindato il gradino alto a +{pnl_pct*100:.2f}%!"
                )

        # BLINDATURA #1 (Stadio 1A - Pre-Scudo Salva-Utile Anti-Inversione):
        # NON strangola mai a +0,04 EUR un titolo che è ancora SOPRA il VWAP (vwap_dist >= -0.03 e RSI >= 46);
        # interviene SOLO se il titolo dopo aver toccato +0,42%..+0,57% perde il VWAP o perde forza!
        if new_peak >= breakeven_trigger and 0.0005 <= pnl_pct <= breakeven_floor:
            trend_still_healthy_above_vwap = (vwap_dist >= -0.03 and cur_rsi_5m >= 46.0)
            if not trend_still_healthy_above_vwap:
                return (
                    f"BLINDATURA #1A - PRE-SCUDO SALVA-UTILE SU PERDITA VWAP: {ticker} aveva toccato "
                    f"il picco di +{new_peak*100:.2f}% e ha perso il VWAP a +{pnl_pct*100:.2f}%!"
                )

        # BLINDATURE #4, #5 e #14: Radar Macro / VIX (Intraday H24 + Finestra Pre-Chiusura 17:15-17:30)
        nasdaq_chg = float(overnight_radar.get("nasdaq_change_pct", 0.0))
        sp500_chg = float(overnight_radar.get("sp500_change_pct", 0.0))
        dax_chg = float(overnight_radar.get("dax_change_pct", 0.0))
        vix_chg = float(overnight_radar.get("vix_fear_change_pct", 0.0))
        now_rome_dt = datetime.datetime.now(MARKET_TZ)
        us_market_live = (now_rome_dt.hour > 15) or (now_rome_dt.hour == 15 and now_rome_dt.minute >= 30)
        if us_market_live:
            macro_crash_shield_active = (
                nasdaq_chg <= -1.20
                or sp500_chg <= -1.00
                or (dax_chg <= -1.00 and vix_chg >= 5.0 and nasdaq_chg < 0.0)
                or vix_chg >= 12.0
            )
            severe_macro_crash = (nasdaq_chg <= -1.50 or (dax_chg <= -1.50 and vix_chg >= 8.0) or vix_chg >= 15.0)
        else:
            macro_crash_shield_active = ((dax_chg <= -1.00 and vix_chg >= 5.0) or vix_chg >= 12.0)
            severe_macro_crash = ((dax_chg <= -1.50 and vix_chg >= 8.0) or vix_chg >= 15.0)

        # BLINDATURA #14 (Stadio Uscita): Incasso Protettivo Immediato SOLO IN UTILE sotto vero Scudo Anti-Crollo Intraday
        # REGOLA AUREA V8.2: Non soffocare mai i titoli sopra VWAP o con Wall Street positiva!
        vwap_dist = float(ticker_metrics.get("vwap_dist_pct", 0.0))
        if macro_crash_shield_active and not stock_is_strong and vwap_dist < -0.10:
            if pnl_pct >= 0.0018:
                return (
                    f"BLINDATURA #14 - SCUDO ANTI-CROLLO INTRADAY (Nasdaq {nasdaq_chg:+.2f}%, DAX {dax_chg:+.2f}%, VIX {vix_chg:+.2f}%): "
                    f"metto subito in salvo +{pnl_pct*100:.2f}% prima dell'onda ribassista!"
                )

        if regime.get("is_pre_close_window"):
            wall_street_positive = bool(overnight_radar.get("allow_overnight_hold", False))

            # A) Blocco Falso Positivo (Tripla prova di inversione dalla cresta) - SOLO IN UTILE
            if sine_phase == "CRESTA_IN_INVERSIONE_FALSO_POSITIVO" and pnl_pct >= 0.0010:
                return (
                    f"BLOCCO FALSO POSITIVO NOTTURNO (17:15): {ticker} mostra tripla prova di inversione "
                    f"dalla cresta (RSI {ticker_metrics.get('rsi_5m')} + candela rossa + calo volumi) -> "
                    f"INCASSO SUBITO +{pnl_pct*100:.2f}%!"
                )

            # B) BLINDATURA #5: Scudo Weekend del Venerdì (63 ore di mercati chiusi) - SOLO IN UTILE
            if regime.get("is_friday_pre_weekend") and pnl_pct >= 0.0010:
                super_friday_ok = (
                    stock_is_strong
                    and nasdaq_chg >= 0.50
                    and vix_chg <= 0.0
                )
                if not super_friday_ok:
                    return (
                        f"BLINDATURA #5 - SCUDO WEEKEND VENERDÌ (17:15): incasso +{pnl_pct*100:.2f}% "
                        f"in EUR per evitare 63 ore di rischio geopolitico nel fine settimana!"
                    )

            # C) BLINDATURA #4: Evacuazione su Pericolo Wall Street - SOLO IN UTILE (Mai cristallizzare perdite alle 17:15!)
            if not wall_street_positive:
                if pnl_pct >= 0.0010:
                    return (
                        f"BLINDATURA #4 - EVACUAZIONE NOTTURNA SU PERICOLO USA: Wall Street negativa -> "
                        f"metto in salvo +{pnl_pct*100:.2f}% in contanti prima della notte!"
                    )

            # D) Se Wall Street è positiva: tieni i Veri Positivi, incassa i titoli deboli in utile (>= +0.30%)
            if wall_street_positive and stock_is_strong:
                return None
            if pnl_pct >= 0.0030:
                return (
                    f"SCUDO SELETTIVO 17:15: titolo in fase '{sine_phase}' -> "
                    f"incasso +{pnl_pct*100:.2f}% prima della chiusura!"
                )

        # BLINDATURA #9 (V8.6 Let-Winners-Run): Sblocca SOLO posizioni davvero ferme/piatte da >= 45 minuti
        # (+0,08%..+0,24%, picco < +0,38%, sotto VWAP e Score < 28), senza MAI tagliare a +0,09 EUR i titoli
        # che stanno salendo verso lo Scudo Mobile Senza Tetto (+0,72%..+3,00%)!
        opened_at = self.position_open_time.setdefault(ticker, time.time())
        hours_open = (time.time() - opened_at) / 3600.0
        minutes_open = hours_open * 60.0
        vwap_dist = float(ticker_metrics.get("vwap_dist_pct", 0.0))
        own_score = float(ticker_metrics.get("quant_buy_score", 50.0))
        if (
            minutes_open >= 45.0
            and 0.0008 <= pnl_pct <= 0.0024
            and new_peak < 0.0038
            and vwap_dist < -0.05
            and own_score < 28.0
            and not stock_is_strong
            and not green_hook_ok
            and has_green_hook_bench
            and best_bench_score >= 90.0
        ):
            return (
                f"BLINDATURA #9 - SWITCH STAGNAZIONE IN VERDE (+{pnl_pct*100:.2f}%, 45m+ piatta sotto VWAP -> Leader {best_bench_score:.0f}/100): "
                f"sblocco cartuccia ferma solo in positivo per salire sul razzo in Super-Trend!"
            )

        # BLINDATURA #15 (V9.1 Airbag Economico ~ -0,14..-0,16 EUR):
        # 1) Taglio rapido a ~-0,14 EUR (-0,54%..-0,62%) dopo 12m se perde spinta o rompe il pavimento VWAP senza Uncino Verde.
        # 2) Airbag Economico Invalicabile stretto a -0,64% (~-0,15/-0,16 EUR) dopo 8m senza Uncino Verde (tetto assoluto -0,72%).
        breakdown_stop_pct = -max(0.0054, min(0.0062, round(atr_raw * 2.4, 4)))
        if minutes_open >= 12.0:
            if pnl_pct <= breakdown_stop_pct and (vwap_dist < -0.10 or cur_rsi_5m < 45.0) and not green_hook_ok and not stock_is_strong:
                return (
                    f"BLINDATURA #15 - TAGLIO CHIRURGICO TESI INVALIDATA ({pnl_pct*100:+.2f}% <= {breakdown_stop_pct*100:+.2f}%): "
                    f"rottura pavimento VWAP / perdita spinta -> taglio minimo (~0,14 EUR) e ruoto su Fascia d'Oro!"
                )
        if minutes_open >= 8.0 and ((pnl_pct <= -0.0064 and not green_hook_ok) or pnl_pct <= -0.0072):
            return (
                f"BLINDATURA #15 - AIRBAG ECONOMICO INVALICABILE ({pnl_pct*100:+.2f}%): "
                f"taglio netto entro ~0,15-0,16 EUR per blindare il capitale!"
            )

        return None

    def register_sell(self, ticker: str, sell_price_eur: float, was_loss: bool = False) -> None:
        self.peak_pnl_pct.pop(ticker, None)
        self.position_open_time.pop(ticker, None)
        self.last_sell_price[ticker] = sell_price_eur
        self.last_sell_time[ticker] = time.time()
        self.last_sell_was_loss[ticker] = bool(was_loss)

    def can_buy_ticker(self, ticker: str, live_price_eur: float, vwap_dist_pct: float = 0.0) -> bool:
        if ticker not in self.last_sell_price:
            return True
        last_px = self.last_sell_price[ticker]
        elapsed_min = (time.time() - self.last_sell_time.get(ticker, 0.0)) / 60.0
        # BLINDATURA #17: Se l'ultima uscita è stata uno Stop-Loss (BLINDATURA #15),
        # impone almeno 60 minuti di cooldown E il recupero sopra il VWAP (>= +0,05%)!
        if self.last_sell_was_loss.get(ticker, False):
            return elapsed_min >= 60.0 and vwap_dist_pct >= 0.05
        if live_price_eur <= last_px * (1.0 - 0.0025):
            return True
        return elapsed_min >= 15.0


def load_client() -> Trading212Client:
    env_key = os.environ.get("T212_API_KEY", "").strip()
    env_secret = os.environ.get("T212_API_SECRET", "").strip()
    env_mode = os.environ.get("T212_MODE", "demo").strip() or "demo"
    if env_key:
        return Trading212Client(
            api_key=env_key,
            api_secret=env_secret or None,
            mode=env_mode,
        )
    with open(CREDENTIALS_PATH, "r", encoding="utf-8") as f:
        creds = json.load(f)
    return Trading212Client(
        api_key=creds["api_key"],
        api_secret=creds.get("api_secret"),
        mode=creds.get("mode", "demo"),
    )


def run_cycle(
    bot: Trading212AutonomousBot,
    intel: HybridUncappedIntelligence,
    scanner: QuantMarketScanner,
    radar: OvernightWaveRadar,
    cycle_num: int,
) -> Dict[str, Any]:
    assert bot.client is not None
    client = bot.client
    bot.tax_tracker.load()

    now = datetime.datetime.now(MARKET_TZ).replace(tzinfo=None)
    regime = intel.get_intraday_regime(now)

    # 1. Leggi posizioni aperte e ordini pendenti da Trading 212 (Split-Speed Turbo 6s)
    positions = client.get_open_positions()
    time.sleep(0.3)
    pending_orders = client.get_pending_orders() if len(positions) < bot.cartridges else []

    pos_by_ticker: Dict[str, Dict[str, Any]] = {p.get("ticker", ""): p for p in positions}
    pending_by_ticker: Dict[str, Dict[str, Any]] = {
        o.get("ticker", ""): o for o in pending_orders if o.get("ticker")
    }

    scanner.has_t212_realtime.clear()
    for tkr_all in list(scanner.realtime_5m_bars.keys()):
        if tkr_all not in pos_by_ticker:
            scanner.realtime_5m_bars[tkr_all].clear()
    for tkr_old in list(intel.peak_pnl_pct.keys()):
        if tkr_old not in pos_by_ticker:
            intel.peak_pnl_pct.pop(tkr_old, None)
            intel.position_open_time.pop(tkr_old, None)
    for tkr, p in pos_by_ticker.items():
        cur_px = float(p.get("currentPrice", 0.0))
        scanner.update_t212_live_price(tkr, cur_px)

    # 2. Scansione quantitativa Split-Speed (6s sulle cartucce aperte / 24s sui 29 Colossi o subito se slot libero)
    bot.tax_tracker.load()
    overnight_status = radar.evaluate_overnight_wave()
    dax_live_pct = float(overnight_status.get("dax_change_pct", 0.0))
    need_full_scan = len(pos_by_ticker) < bot.cartridges
    quant_metrics = scanner.scan_all(
        tax_data=bot.tax_tracker.data,
        dax_change_pct=dax_live_pct,
        force=need_full_scan,
        active_tickers=list(pos_by_ticker.keys()),
    )

    # Sincronizzazione automatica 100% con "Profitti/perdite realizzati" certificato da Trading 212 (/equity/account/cash -> result)
    try:
        cash_info = client.get_account_cash()
        t212_realized_res = cash_info.get("result")
        if t212_realized_res is not None:
            t212_net = round(float(t212_realized_res), 2)
            cur_plus = float(bot.tax_tracker.data.get("plusvalenze_lorde_eur", 0.0))
            cur_minus = float(bot.tax_tracker.data.get("minusvalenze_lorde_eur", 0.0))
            if abs((cur_plus - cur_minus) - t212_net) >= 0.01:
                bot.tax_tracker.data["minusvalenze_lorde_eur"] = round(cur_plus - t212_net, 2)
                bot.tax_tracker.save()
        time.sleep(0.3)
    except Exception:
        pass

    # BLINDATURA #6: Interesse Composto Automatico di Kelly (Auto-Compounding sul totale storico)
    realized_net_eur = round(
        float(bot.tax_tracker.data.get("plusvalenze_lorde_eur", 0.0))
        - float(bot.tax_tracker.data.get("minusvalenze_lorde_eur", 0.0)),
        2,
    )
    # BLINDATURA #10: Cassaforte Giornaliera ricalcolata sui soli utili chiusi OGGI (target >= +1,60 EUR/giorno)
    today_prefix = now.date().isoformat()
    today_ops = [
        op for op in bot.tax_tracker.data.get("operazioni_chiuse", [])
        if str(op.get("timestamp", "")).startswith(today_prefix)
    ]
    today_realized_net_eur = round(
        sum(float(op.get("risultato_fiscale_eur", 0.0)) for op in today_ops),
        2,
    )
    today_stops_count = sum(
        1 for op in today_ops if float(op.get("risultato_fiscale_eur", 0.0)) < 0.0
    )
    running_today_pnl = 0.0
    today_peak_realized_eur = 0.0
    stops_after_loot_peak = 0
    for op in today_ops:
        op_pnl = float(op.get("risultato_fiscale_eur", 0.0))
        if today_peak_realized_eur >= 0.80 and op_pnl < 0.0:
            stops_after_loot_peak += 1
        running_today_pnl += op_pnl
        if running_today_pnl > today_peak_realized_eur:
            today_peak_realized_eur = running_today_pnl
            stops_after_loot_peak = 0
    morning_loot_shield_active = (
        today_peak_realized_eur >= 0.80
        and today_realized_net_eur <= (today_peak_realized_eur - 0.30)
    )
    hm_now = now.hour * 60 + now.minute
    lunch_profit_lock_active = (
        today_peak_realized_eur >= 0.80
        and stops_after_loot_peak >= 1
        and (11 * 60 <= hm_now < 14 * 60 + 36)
    )
    compounded_budget_eur = round(bot.total_budget_eur + max(0.0, realized_net_eur), 2)
    dynamic_cartridge_eur = round(compounded_budget_eur / bot.cartridges, 2)
    daily_vault_active = (today_realized_net_eur >= 1.60)

    bench_candidates = [
        m
        for tkr, m in quant_metrics.items()
        if tkr not in pos_by_ticker
        and tkr not in pending_by_ticker
        and bool(m.get("has_fresh_intraday_feed", True))
        and intel.can_buy_ticker(tkr, float(m.get("live_price_eur", 0.0)), float(m.get("vwap_dist_pct", 0.0)))
        and bool(m.get("green_hook_confirmed"))
        and float(m.get("rsi_5m", 100.0))
        <= (67.5 if m.get("fase_onda_sinusoidale") == "SUPER_TREND_VERO_POSITIVO_BREAKOUT" else 64.0)
    ]
    bench_scores = [float(m["quant_buy_score"]) for m in bench_candidates]
    best_bench_score = max(bench_scores) if bench_scores else 0.0
    has_green_hook_bench = any(
        bool(m.get("green_hook_confirmed")) and float(m["quant_buy_score"]) >= 65.0
        for m in bench_candidates
    )

    invested_100e = 0.0
    unrealized_pnl_100e = 0.0
    cartridge_statuses: List[Dict[str, Any]] = []
    actions_taken: List[str] = []

    # 3. Valuta posizioni aperte con logica V6.0 Istituzionale (10 Blindature)
    slot_idx = 1
    for tkr, p in list(pos_by_ticker.items()):
        if tkr not in EUR_ZERO_FEE_UNIVERSE:
            continue
        meta = EUR_ZERO_FEE_UNIVERSE[tkr]
        prof = ASSET_PROFILES.get(tkr, ASSET_PROFILES["SAPd_EQ"])
        tkr_m = quant_metrics.get(tkr, {})
        qty_open = float(p.get("quantity", 0.0))
        avg_price = float(p.get("averagePrice", 0.0))
        cur_price = float(p.get("currentPrice", avg_price))
        ppl = float(p.get("ppl", (cur_price - avg_price) * qty_open))
        cost_eur = round(qty_open * avg_price, 2)
        pnl_pct = (cur_price - avg_price) / avg_price if avg_price > 0 else 0.0

        # Auto-Sync LIFO lot se la posizione è stata aperta dall'istanza Cloud (o viceversa)
        if qty_open > 0 and avg_price > 0:
            open_lots = bot.tax_tracker.data.get("lotti_aperti_lifo", {}).get(tkr, [])
            if not open_lots:
                bot.tax_tracker.record_buy(tkr, qty_open, avg_price)
                intel.peak_pnl_pct[tkr] = max(0.0, pnl_pct)
                intel.position_open_time[tkr] = time.time()
            elif abs(float(open_lots[-1].get("price_eur", avg_price)) - avg_price) / avg_price > 0.0025:
                open_lots[-1]["price_eur"] = round(avg_price, 4)
                open_lots[-1]["quantity"] = qty_open
                bot.tax_tracker.save()
                intel.peak_pnl_pct[tkr] = max(0.0, pnl_pct)
                intel.position_open_time[tkr] = time.time()

        # Ribilanciamento automatico SOLO IN UTILE se una cartuccia supera 1.24x la taglia composta
        max_allowed_cartridge = max(31.00, round(dynamic_cartridge_eur * 1.24, 2))
        if cost_eur > max_allowed_cartridge and regime["market_open"] and cur_price > avg_price and pnl_pct >= 0.0010:
            target_qty = round(dynamic_cartridge_eur / cur_price, 2)
            if target_qty * cur_price > (dynamic_cartridge_eur + 2.00) and target_qty > 0.01:
                target_qty = round(target_qty - 0.01, 2)
            excess_qty = round(qty_open - target_qty, 2)
            if excess_qty >= 0.01:
                client.place_market_order(ticker=tkr, quantity=-excess_qty)
                closed_op = bot.tax_tracker.record_sell(
                    ticker=tkr,
                    sell_qty=excess_qty,
                    sell_price_eur=cur_price,
                    fallback_avg_price_eur=avg_price,
                )
                qty_open = round(qty_open - excess_qty, 2)
                cost_eur = round(qty_open * avg_price, 2)
                ppl = round((cur_price - avg_price) * qty_open, 2)
                actions_taken.append(
                    f"RIBILANCIAMENTO CARTUCCIA COMPOSTA ({dynamic_cartridge_eur:.2f} EUR) su {tkr}: vendute {excess_qty} azioni in eccesso "
                    f"a {cur_price:.2f} EUR (Utile fiscale: {closed_op['risultato_fiscale_eur']:+.2f} EUR)"
                )
                time.sleep(2.5)

        # A) Valuta Scudo Mobile Elastico Senza Tetto + Selettore Onda Notturna + Rotazione Solo in Utile
        # Filtra i candidati della panchina tenendo solo quelli compatibili col Vincolo Settoriale di Markowitz!
        other_active_sectors = {
            ASSET_PROFILES.get(other_tkr, ASSET_PROFILES["SAPd_EQ"])["sector"]
            for other_tkr in pos_by_ticker
            if other_tkr != tkr and other_tkr in EUR_ZERO_FEE_UNIVERSE
        }
        eligible_bench_for_tkr = [
            m for m in bench_candidates if m.get("sector") not in other_active_sectors
        ]
        tkr_best_bench_score = (
            max(float(m["quant_buy_score"]) for m in eligible_bench_for_tkr)
            if eligible_bench_for_tkr
            else 0.0
        )
        tkr_has_green_hook_bench = any(
            bool(m.get("green_hook_confirmed")) and float(m["quant_buy_score"]) >= 65.0
            for m in eligible_bench_for_tkr
        )
        exit_reason = intel.evaluate_uncapped_exit(
            tkr,
            pnl_pct,
            regime,
            tkr_best_bench_score,
            overnight_status,
            tkr_m,
            realized_net_eur=today_realized_net_eur,
            has_green_hook_bench=tkr_has_green_hook_bench,
        )
        if exit_reason and regime["market_open"]:
            order_res = client.place_market_order(ticker=tkr, quantity=-qty_open)
            closed_op = bot.tax_tracker.record_sell(
                ticker=tkr,
                sell_qty=qty_open,
                sell_price_eur=cur_price,
                fallback_avg_price_eur=avg_price,
            )
            intel.register_sell(
                tkr,
                cur_price,
                was_loss=(float(closed_op.get("risultato_fiscale_eur", 0.0)) < 0.0),
            )
            msg = (
                f"{exit_reason} su {tkr} ({meta['name']}): vendute {qty_open} azioni "
                f"a {cur_price:.2f} EUR (Risultato fiscale: {closed_op['risultato_fiscale_eur']:+.2f} EUR, 0,00 EUR comm.)"
            )
            actions_taken.append(msg)
            pos_by_ticker.pop(tkr, None)
            time.sleep(2.5)
            continue

        peak_now = intel.peak_pnl_pct.get(tkr, pnl_pct)
        shield_act = float(tkr_m.get("elastic_shield_act_raw", prof["shield_activation_pct"]))
        shield_pull = float(tkr_m.get("elastic_shield_pull_raw", prof["shield_pullback_pct"]))
        shield_is_armed = peak_now >= shield_act
        breakeven_trigger = 0.0036 if daily_vault_active else 0.0038
        breakeven_floor_pct = 0.16 if daily_vault_active else 0.18
        pre_shield_breakeven_armed = peak_now >= breakeven_trigger
        if shield_is_armed:
            current_floor_pct = round((peak_now - shield_pull) * 100, 2)
        elif pre_shield_breakeven_armed:
            current_floor_pct = breakeven_floor_pct
        else:
            current_floor_pct = None

        overnight_decision_preview = (
            "TIENI PER SALTO 09:00 (Onda Positiva)"
            if (overnight_status.get("allow_overnight_hold") and tkr_m.get("strong_for_overnight"))
            else "INCASSA PRIMA DELLE 17:30 SE IN UTILE (Protezione Onda Negativa)"
        )

        invested_100e += cost_eur
        unrealized_pnl_100e += ppl
        cartridge_statuses.append({
            "slot": slot_idx,
            "ticker": tkr,
            "name": meta["name"],
            "squadra": prof["squad"],
            "settore_markowitz": prof["sector"],
            "ruolo": prof["role_desc"],
            "status": "ESEGUITA_IN_PORTAFOGLIO",
            "quantity": qty_open,
            "avg_price_eur": round(avg_price, 2),
            "current_price_eur": round(cur_price, 2),
            "invested_eur": cost_eur,
            "pnl_eur": round(ppl, 2),
            "pnl_pct": round(pnl_pct * 100, 2),
            "peak_pnl_pct": round(peak_now * 100, 2),
            "tetto_massimo_guadagno": "NESSUN TETTO (Uncapped)",
            "pre_scudo_salva_utile_attivo": pre_shield_breakeven_armed,
            "scudo_mobile_elastico_atr_si_attiva_a_pct": round(shield_act * 100, 2),
            "scudo_mobile_attivo_ora": shield_is_armed,
            "livello_incasso_protetto_pct": current_floor_pct,
            "fase_onda_sinusoidale": tkr_m.get("fase_onda_sinusoidale", "N/A"),
            "decisione_notturna_prevista_17_15": overnight_decision_preview,
            "rsi_5m": tkr_m.get("rsi_5m", 50.0),
            "opened_at_ts": intel.position_open_time.get(tkr, time.time()),
        })
        slot_idx += 1

    # 4. Conta eventuali ordini pendenti
    for tkr, o in pending_by_ticker.items():
        if tkr in EUR_ZERO_FEE_UNIVERSE and tkr not in pos_by_ticker:
            meta = EUR_ZERO_FEE_UNIVERSE[tkr]
            prof = ASSET_PROFILES.get(tkr, ASSET_PROFILES["SAPd_EQ"])
            invested_100e += dynamic_cartridge_eur
            cartridge_statuses.append({
                "slot": slot_idx,
                "ticker": tkr,
                "name": meta["name"],
                "squadra": prof["squad"],
                "settore_markowitz": prof["sector"],
                "status": "ORDINE_IN_CODA",
                "order_id": o.get("id"),
                "quantity": o.get("quantity"),
                "invested_eur": dynamic_cartridge_eur,
            })
            slot_idx += 1

    # 5. INGRESSO BILANCIATO 2+2 CON VINCOLO SETTORIALE DI MARKOWITZ E INTERESSE COMPOSTO
    active_count = len(cartridge_statuses)
    ranked_candidates = sorted(
        quant_metrics.values(),
        key=lambda m: (
            float(m["quant_buy_score"]),
            1
            if (
                0.145 <= float(m.get("atr_5m_volatility_pct", 0.0)) <= 0.34
                and -0.12 <= float(m.get("vwap_dist_pct", 0.0)) <= 0.48
            )
            else 0,
            round(min(0.34, float(m.get("atr_5m_volatility_pct", 0.0))), 3),
        ),
        reverse=True,
    )

    max_investable_before_4th = round(compounded_budget_eur - 18.00, 2)
    if regime["allow_new_buys"] and active_count < bot.cartridges and invested_100e <= max_investable_before_4th:
        sq1_count = sum(
            1 for c in cartridge_statuses if c.get("squadra") == "SQUADRA_1_CECCHINO_GIORNALIERO"
        )
        sq2_count = sum(
            1 for c in cartridge_statuses if c.get("squadra") == "SQUADRA_2_CAVALCA_ONDA"
        )
        active_sectors = {
            c.get("settore_markowitz")
            for c in cartridge_statuses
            if c.get("settore_markowitz")
        }

        for cand in ranked_candidates:
            if active_count >= bot.cartridges or invested_100e > max_investable_before_4th:
                break
            tkr = cand["ticker"]
            if tkr in pos_by_ticker or tkr in pending_by_ticker:
                continue
            cand_squad = cand["squad"]
            cand_sector = cand["sector"]
            live_px = float(cand["live_price_eur"])
            score = float(cand["quant_buy_score"])
            rsi_5m = float(cand["rsi_5m"])
            cand_phase = cand.get("fase_onda_sinusoidale", "")

            # V8.1 Zero-Bottleneck: nessuna gabbia artificiale 2+2 tra Squadra 1 e Squadra 2!
            # Qualsiasi candidato valido delle 3 Strategie può occupare subito lo slot libero,
            # garantendo la diversificazione reale tramite il Vincolo di Markowitz (4 settori industriali diversi).
            if cand_sector in active_sectors:
                continue

            if not intel.can_buy_ticker(tkr, live_px, float(cand.get("vwap_dist_pct", 0.0))):
                continue

            # Se siamo nella finestra 17:15-17:30, compra per la notte SOLO se il Radar prevede Onda Positiva!
            if regime.get("is_pre_close_window"):
                if not (overnight_status.get("allow_overnight_hold") and cand.get("strong_for_overnight")):
                    continue
            else:
                # BLINDATURA #14 (Stadio Ingresso - Veto Anti-Crollo Intraday):
                # Esclude sempre COLTELLO_IN_CADUTA e ONDA_DISCENDENTE_O_DEBOLE,
                # ma consente SIA le Valli con Uncino Verde confermato (Score >= 65) SIA le Onde Ascendenti Sane sopra VWAP!
                nasdaq_c = float(overnight_status.get("nasdaq_change_pct", 0.0))
                sp500_c = float(overnight_status.get("sp500_change_pct", 0.0))
                dax_c = float(overnight_status.get("dax_change_pct", 0.0))
                vix_c = float(overnight_status.get("vix_fear_change_pct", 0.0))
                us_live = (now.hour > 15) or (now.hour == 15 and now.minute >= 30)
                if us_live:
                    intraday_crash_shield = (
                        nasdaq_c <= -1.20
                        or sp500_c <= -1.00
                        or (dax_c <= -1.00 and vix_c >= 5.0 and nasdaq_c < 0.0)
                        or vix_c >= 12.0
                    )
                else:
                    intraday_crash_shield = ((dax_c <= -1.00 and vix_c >= 5.0) or vix_c >= 12.0)
                if intraday_crash_shield:
                    is_valid_valley_rebound = (
                        cand_phase == "VALLE_CON_UNCINO_VERDE_PRONTO_ACQUISTO"
                        and cand.get("green_hook_confirmed", False)
                        and score >= 65.0
                    )
                    is_valid_rising_wave = (
                        cand.get("strong_for_overnight", False)
                        and cand.get("green_hook_confirmed", False)
                        and score >= 30.0
                    )
                    if not (is_valid_valley_rebound or is_valid_rising_wave):
                        continue

                # BLINDATURA #18 (Anti-Stale Opening Price 09:00-09:15):
                # Non comprare mai un titolo da panchina nei primi 15 minuti (09:00-09:15) se Yahoo Finance
                # non ha ancora pubblicato almeno 1 candela della seduta odierna (evita di comprare sul prezzo
                # di chiusura delle 17:30 di ieri mentre il titolo reale su XETRA ha fatto un gap-up +4%)!
                if not cand.get("has_fresh_intraday_feed", True):
                    continue

                # BLINDATURA #2 (Uncino Verde + Soglia Selettiva V8.5 Anti-Cresta RSI <= 67.5)
                # + BLINDATURA #10 (Cassaforte Giornaliera)
                # + BLINDATURA #19 (Scudo Salva-Bottino Mattutino #19A + Freno 4a Cartuccia con VIX >= 4% #19B):
                # I titoli SOPRA il VWAP mantengono sempre soglia libera (52.0) per non perdere nessun rialzo;
                # i titoli SOTTO il VWAP in giornate nervose (VIX >= 3.5%, >= 2 stop o Scudo Salva-Bottino) richiedono Score >= 68.0,
                # e con VIX >= 4.0% la 4a cartuccia entra solo su leader confermati sopra VWAP o con Score >= 70.0!
                # BLINDATURA #22 (V9.2 Scudo Deserto di Mezzogiorno 11:15-14:35 + Lucchetto Salva-Bottino >= +0,80 EUR):
                # 1) Se il mattino ha già incassato >= +0,80 EUR e dopo il picco scatta 1 taglio tra le 11:00 e le 14:35,
                #    scatta il Lucchetto Totale sugli acquisti fino alle 14:36 CET (impossibile rimangiarsi la mattinata!).
                if lunch_profit_lock_active:
                    continue
                # 2) Tra le 11:15 e le 14:35 CET (Pausa Pranzo Europea senza volumi istituzionali), sospende tutti gli
                #    acquisti ordinari, ammettendo SOLO anomalie esplosive di volume reale (RVOL >= 1.80x, Score >= 95, Kaufman >= 0.45).
                if regime.get("is_lunch_desert_window", False):
                    cand_rvol = float(cand.get("rvol_ratio", 0.0))
                    cand_er = float(cand.get("kaufman_efficiency_ratio", 0.0))
                    if not (
                        cand_rvol >= 1.80
                        and score >= 95.0
                        and cand_er >= 0.45
                        and 0.0 <= float(cand.get("vwap_dist_pct", 0.0)) <= 0.40
                    ):
                        continue

                cand_vwap_dist = float(cand.get("vwap_dist_pct", 0.0))
                cand_atr_pct = float(cand.get("atr_5m_volatility_pct", 0.18))
                cand_day_range = float(cand.get("day_range_pct", 2.0))
                range_matured_buy = (now.hour > 9) or (now.hour == 9 and now.minute >= 45)
                # BLINDATURA #21 (V9.1 Fascia d'Oro + Veto Estensione VWAP):
                # 1) Mai comprare un titolo già scappato lontano sopra il pavimento VWAP (> +0,50% sui veloci, > +0,65% sugli altri)!
                max_vwap_entry = 0.50 if cand_atr_pct >= 0.23 else 0.65
                if cand_vwap_dist > max_vwap_entry:
                    continue
                # 2) Mai comprare troppo sotto il pavimento VWAP (< -0,35%) salvo rimbalzo ipervenduto estremo confermato!
                if cand_vwap_dist < -0.35 and (rsi_5m >= 32.0 or score < 68.0):
                    continue
                # 3) In mercato normale (DAX > -0,50%), scarta all'acquisto i titoli statici (ATR < 0,13% e Range < 1,40%)!
                if dax_c > -0.50 and range_matured_buy and cand_atr_pct < 0.13 and cand_day_range < 1.40:
                    continue

                if vix_c >= 4.0 and active_count >= 3 and cand_vwap_dist < 0.05 and score < 70.0:
                    continue
                if cand_vwap_dist < 0.0 and (vix_c >= 3.5 or today_stops_count >= 2 or morning_loot_shield_active):
                    min_required_score = 68.0
                else:
                    min_required_score = 62.0 if daily_vault_active else 52.0
                max_allowed_rsi = (
                    67.5
                    if cand_phase == "SUPER_TREND_VERO_POSITIVO_BREAKOUT"
                    else 64.0
                )
                if rsi_5m > max_allowed_rsi or score < min_required_score or not cand.get("green_hook_confirmed", True):
                    continue

            remaining_budget = round(compounded_budget_eur - invested_100e, 2)
            alloc_eur = min(dynamic_cartridge_eur, remaining_budget)
            if alloc_eur < 18.00:
                break

            qty_to_buy = round(alloc_eur / live_px, 2)
            if qty_to_buy <= 0 and live_px > 0:
                qty_to_buy = round(alloc_eur / live_px, 3)
            if qty_to_buy <= 0:
                continue

            try:
                # Verifica atomica pre-acquisto contro collisioni Cloud/Locale (mai superare 4 cartucce / 100 EUR)
                try:
                    fresh_pos = [
                        p for p in client.get_open_positions()
                        if float(p.get("quantity", 0.0)) > 0
                    ]
                    if len(fresh_pos) >= bot.cartridges or any(p.get("ticker") == tkr for p in fresh_pos):
                        break
                    time.sleep(1.5)
                except Exception:
                    pass
                meta = EUR_ZERO_FEE_UNIVERSE[tkr]
                order_res = client.place_market_order(ticker=tkr, quantity=qty_to_buy)
                est_cost = round(qty_to_buy * live_px, 2)
                bot.tax_tracker.record_buy(ticker=tkr, quantity=qty_to_buy, price_eur=live_px)
                intel.position_open_time[tkr] = time.time()
                invested_100e += est_cost
                active_count += 1
                active_sectors.add(cand_sector)
                if cand_squad == "SQUADRA_1_CECCHINO_GIORNALIERO":
                    sq1_count += 1
                else:
                    sq2_count += 1
                msg = (
                    f"INGRESSO V7.0 HIGH-BETA ({cand_squad} / {cand_sector}) -> BUY {qty_to_buy} {tkr} ({meta['name']}) "
                    f"per {est_cost:.2f} EUR | Score: {score}/100 (Vel: {cand.get('profit_velocity_mult', 1.0)}x, RSI: {rsi_5m}) | Order ID: {order_res.get('id')}"
                )
                actions_taken.append(msg)
                cartridge_statuses.append({
                    "slot": slot_idx,
                    "ticker": tkr,
                    "name": meta["name"],
                    "squadra": cand_squad,
                    "settore_markowitz": cand_sector,
                    "status": "APPENA_ACQUISTATA_V7_HIGH_BETA",
                    "order_id": order_res.get("id"),
                    "quantity": qty_to_buy,
                    "invested_eur": est_cost,
                })
                slot_idx += 1
                time.sleep(2.5)
            except Exception as e:
                # Se un ticker ha restrizioni temporanee sul conto Demo, mettilo in cooldown 30m e passa subito al candidato High-Beta successivo!
                intel.last_sell_price[tkr] = live_px
                intel.last_sell_time[tkr] = time.time()
                actions_taken.append(f"Passaggio al candidato High-Beta successivo ({tkr}: {e})")

    realized_net_eur = round(
        float(bot.tax_tracker.data.get("plusvalenze_lorde_eur", 0.0))
        - float(bot.tax_tracker.data.get("minusvalenze_lorde_eur", 0.0)),
        2,
    )
    virtual_100e_equity = round(bot.total_budget_eur + realized_net_eur + unrealized_pnl_100e, 2)
    free_cash_100e = round(max(0.0, compounded_budget_eur - invested_100e), 2)

    # 6. Verifica Target Annuale +30% (130,00 EUR)
    if virtual_100e_equity >= bot.target_equity_eur:
        bot.liquidate_all_for_withdrawal()
        actions_taken.append(
            f"TARGET +30% RAGGIUNTO ({virtual_100e_equity:.2f} EUR >= 130,00 EUR)! "
            "Liquidazione totale eseguita a 0,00 EUR commissioni."
        )

    state = {
        "timestamp": now.isoformat(timespec="seconds"),
        "cycle": cycle_num,
        "mode": "INSTITUTIONAL_V7_0_DYNAMIC_HIGH_BETA_13_SHIELDS",
        "blindature_attive_v6_istituzionali": [
            "1. Pre-Scudo Salva-Utile (Break-Even Lock: picco >= +0,60% -> pavimento garantito +0,25%)",
            "2. Filtro Uncino Verde sugli Acquisti (Anti-Falling-Knife)",
            "3. Raccolto Gap Mattutino 09:00-09:30 (Anti-Gap-Fill: scudo stretto -0,14% sopra +0,50%)",
            "4. Evacuazione Notturna Totale alle 17:15 se Wall Street è negativa",
            "5. Scudo Weekend del Venerdì alle 17:15 (protezione 63 ore)",
            f"6. Interesse Composto di Kelly (Budget Composto: {compounded_budget_eur:.2f} EUR -> Taglia Cartuccia: {dynamic_cartridge_eur:.2f} EUR)",
            "7. Vincolo di Markowitz su 10 Settori Industriali (4 cartucce su 4 settori diversi)",
            "8. Scudo Elastico sulla Volatilità Reale ATR a 5m (si stringe su mercato piatto, si allarga su mercato esplosivo)",
            "9. Rotazione Dinamica Costo-Opportunità SOLO IN UTILE (>= 45m a +0,18%..scudo se in panchina c'è Score >= 82 con Uncino Verde)",
            f"10. Cassaforte Giornaliera High-Water Mark (>= +1,60 EUR in cassa -> Attiva ora: {daily_vault_active})",
            "11. Fusione Zero-Latency 0ms (Incolla i prezzi in tempo reale di Trading 212 sulle candele 5m eliminando i 15m di ritardo di Yahoo su XETRA)",
            "12. Scudo Anti-Shock Dati Macro USA 14:28-14:35 (Blocca nuovi acquisti nei 7 minuti di caccia agli stop sui dati CPI/NFP delle 14:30)",
            "13. Selettore Dinamico Regime-Adaptive Beta (Cambio Marcia automatico sui 6 colossi sicuri quando DAX <= -0,50%)",
            "14. Scudo Anti-Crollo Intraday Macro & VIX (Veto sugli acquisti in caduta e incasso rapido degli utili >= +0,15%)",
            "15. Taglio Rapido Anti-Discesa Micro-Stop Asimmetrico (-0,45% / ~0,11 EUR se perde Uncino Verde, max -0,75% / ~0,18 EUR invalicabile)",
        ],
        "regime_mercato_attivo": regime,
        "radar_onda_notturna_wall_street": overnight_status,
        "account_id": 52318994,
        "budget_iniziale_vincolato_eur": 100.00,
        "budget_composto_attivo_kelly_eur": compounded_budget_eur,
        "taglia_cartuccia_composta_eur": dynamic_cartridge_eur,
        "cassaforte_giornaliera_attiva": daily_vault_active,
        "capitale_impegnato_cartucce_eur": round(invested_100e, 2),
        "liquidita_libera_su_100e_eur": free_cash_100e,
        "profitto_realizzato_in_cassa_eur": realized_net_eur,
        "profitto_aperto_non_realizzato_eur": round(unrealized_pnl_100e, 2),
        "guadagno_totale_netto_eur": round(realized_net_eur + unrealized_pnl_100e, 2),
        "valore_totale_portafoglio_100e_eur": virtual_100e_equity,
        "target_incasso_automatico_eur": bot.target_equity_eur,
        "commissioni_pagate_eur": 0.00,
        "classifica_scanner_quantitativo_5m": ranked_candidates,
        "titoli_in_cooldown_anti_massimi": intel.last_sell_price,
        "cartucce_4x25_eur": cartridge_statuses,
        "ultime_azioni_bot": actions_taken,
        "riepilogo_fiscale_730": bot.tax_tracker.generate_730_summary(virtual_100e_equity),
    }

    with open(BOT_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    return state


def main():
    parser = argparse.ArgumentParser(description="Trading 212 V6.5 Institutional Zero-Latency Daemon")
    parser.add_argument(
        "--cycles",
        type=int,
        default=0,
        help="Numero di cicli da eseguire (0 = loop infinito H24 locale, >0 = modalità Cloud GitHub Actions)",
    )
    args, _ = parser.parse_known_args()

    print(
        "=== AVVIO DEMONE V6.5 INSTITUTIONAL ZERO-LATENCY: 12 BLINDATURE (MARKOWITZ + KELLY + 0ms + 730) ===",
        flush=True,
    )
    client = load_client()
    added_giants = discover_and_verify_eur_giants(client)
    print(
        f"[RADAR DINAMICO V8.8] Universo EUR Zero-Fee attivo: {len(ASSET_PROFILES)} Colossi DAX40/AEX25 (+{added_giants} nuovi scoperti via ISIN)",
        flush=True,
    )
    bot = Trading212AutonomousBot(client=client, total_budget_eur=100.00, cartridges=4, annual_target_pct=0.30)
    intel = HybridUncappedIntelligence()
    scanner = QuantMarketScanner()
    radar = OvernightWaveRadar()

    cycle = 1
    if os.path.exists(BOT_STATE_PATH):
        try:
            with open(BOT_STATE_PATH, "r", encoding="utf-8") as f:
                prev_st = json.load(f)
                cycle = int(prev_st.get("cycle", 0)) + 1
        except Exception:
            cycle = 1

    pid_lock_path = os.path.join(BASE_DIR, "daemon_pid.lock")
    my_pid = str(os.getpid())
    start_mtime = os.path.getmtime(os.path.abspath(__file__))
    if args.cycles == 0:
        with open(pid_lock_path, "w", encoding="utf-8") as f:
            f.write(my_pid)

    executed = 0
    while True:
        if args.cycles == 0:
            try:
                cur_mtime = os.path.getmtime(os.path.abspath(__file__))
                if cur_mtime > start_mtime:
                    print(f"[HOT-RELOAD] Aggiornamento codice rilevato su disco, ricaricamento in-place (PID {my_pid})...", flush=True)
                    os.execv(sys.executable, [sys.executable] + sys.argv)
            except Exception:
                pass
        if args.cycles == 0 and os.path.exists(pid_lock_path):
            try:
                with open(pid_lock_path, "r", encoding="utf-8") as f:
                    active_pid = f.read().strip()
                if active_pid and active_pid != my_pid:
                    print(f"[INFO] Nuovo demone rilevato (PID {active_pid}), arresto pulito di PID {my_pid}.", flush=True)
                    break
            except Exception:
                pass
        try:
            state = run_cycle(bot, intel, scanner, radar, cycle)
            ov = state["radar_onda_notturna_wall_street"]
            print(
                f"[{state['timestamp']}] Ciclo #{cycle} | "
                f"Valore 100€: {state['valore_totale_portafoglio_100e_eur']:.2f} EUR "
                f"(Cassa: {state['profitto_realizzato_in_cassa_eur']:+.2f} EUR, "
                f"Aperto: {state['profitto_aperto_non_realizzato_eur']:+.2f} EUR, "
                f"Cartuccia Kelly: {state['taglia_cartuccia_composta_eur']:.2f} EUR) | "
                f"Radar Notte: {ov['verdict']} (Nasdaq {ov['nasdaq_change_pct']:+.2f}%, VIX {ov['vix_fear_change_pct']:+.2f}%)",
                flush=True,
            )
            for act in state["ultime_azioni_bot"]:
                print(f"   >>> [AZIONE V6.5]: {act}", flush=True)
        except Exception as e:
            print(f"[ATTENZIONE] Errore temporaneo nel ciclo #{cycle}: {e}", flush=True)

        cycle += 1
        executed += 1
        if args.cycles > 0 and executed >= args.cycles:
            print(f"=== SESSIONE CLOUD COMPLETATA ({executed}/{args.cycles} cicli eseguiti) ===", flush=True)
            break
        time.sleep(5)


if __name__ == "__main__":
    main()
