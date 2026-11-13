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
from typing import Dict, Any, List, Optional, Tuple
from zoneinfo import ZoneInfo

MARKET_TZ = ZoneInfo("Europe/Rome")
US_EASTERN_TZ = ZoneInfo("America/New_York")

from trading212_bot import (
    Trading212Client,
    Trading212AutonomousBot,
    EUR_ZERO_FEE_UNIVERSE,
    BASE_DIR,
    BOT_STATE_PATH,
)

CREDENTIALS_PATH = os.path.join(BASE_DIR, "t212_credentials.json")
SCANNER_CACHE_PATH = os.path.join(BASE_DIR, ".scanner_5m_cache.json")
TAX_TRACKER_PATH = os.path.join(BASE_DIR, "registro_fiscale_730.json")
V11_CLEAN_EPOCH_TS = "2026-11-12T15:30:00"
PRUDENT_MIN_RVOL = 0.20
LINEAR_ELITE_SCORE = 80.0
BASE_MIN_BUY_SCORE = 58.0
LIMIT_ORDER_CAP_PCT = 0.0100  # +1,00% tetto anti-spike MiFID II RTS 11
DAILY_VAULT_TRIGGER_EUR = 1.60
DAILY_VAULT_GIVEBACK_EUR = 0.30

ASSET_PROFILES: Dict[str, Dict[str, Any]] = {
    "RHMd_EQ": {
        "yahoo": "RHM.DE",
        "gettex": "GETTEX:RHM",
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
        "gettex": "GETTEX:ENR",
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
        "gettex": "GETTEX:1N8",
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
        "gettex": "GETTEX:CBK",
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
        "gettex": "GETTEX:BSI",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "CHIP_POTENZA_PACKAGING",
        "role_desc": "Turbo High-Beta Packaging Chip AI (Senza Tetto)",
        "ref_price_eur": 132.00,
        "shield_activation_pct": 0.0082,
        "shield_pullback_pct": 0.0019,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    "ZALd_EQ": {
        "yahoo": "ZAL.DE",
        "gettex": "GETTEX:ZAL",
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
        "gettex": "GETTEX:DTE",
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
        "gettex": "GETTEX:ALV",
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
        "gettex": "GETTEX:SIE",
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
        "gettex": "GETTEX:SAP",
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
        "gettex": "GETTEX:IFX",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "CHIP_POTENZA_PACKAGING",
        "role_desc": "Cavalca-Onda Semiconduttori & Gap Notturno Selettivo (Senza Tetto)",
        "ref_price_eur": 49.70,
        "shield_activation_pct": 0.0078,
        "shield_pullback_pct": 0.0018,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    "ASMLa_EQ": {
        "yahoo": "ASML.AS",
        "gettex": "GETTEX:ASME",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "CHIP_LITOGRAFIA_WAFER",
        "role_desc": "Cavalca-Onda AI/Chip & Gap Notturno Selettivo (Senza Tetto)",
        "ref_price_eur": 1313.00,
        "shield_activation_pct": 0.0080,
        "shield_pullback_pct": 0.0018,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    "BAYNd_EQ": {
        "yahoo": "BAYN.DE",
        "gettex": "GETTEX:BAYN",
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
        "gettex": "GETTEX:VNA",
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
        "gettex": "GETTEX:AIR",
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

# BLINDATURA #20 (V11.2 Dynamic Radar "Stocks-In-Play" DAX 40 + AEX 25 + 7 Big Tech USA in EUR a 0,00 EUR commissioni):
# Candidati aggiuntivi certificati per ISIN su XETRA (Germania) ed Euronext Amsterdam (Olanda) con feed GETTEX 0s.
CANDIDATE_EUR_GIANTS: List[Dict[str, Any]] = [
    {
        "fallback_ticker": "MTXd_EQ",
        "name": "MTU Aero Engines AG",
        "isin": "DE000A0D9PT0",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "MTX.DE",
        "gettex": "GETTEX:MTX",
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
        "gettex": "GETTEX:AVS",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "CHIP_LITOGRAFIA_WAFER",
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
        "gettex": "GETTEX:DBK",
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
        "gettex": "GETTEX:MUV2",
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
        "gettex": "GETTEX:DTG",
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
        "isin": "DE000A1EWWW0",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "ADS.DE",
        "gettex": "GETTEX:ADS",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "CONSUMER_BRAND_GLOBALE",
        "role_desc": "Cavalca-Onda Sportswear & Brand Globale DAX (Senza Tetto)",
        "ref_price_eur": 220.00,
        "shield_activation_pct": 0.0070,
        "shield_pullback_pct": 0.0016,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    {
        "fallback_ticker": "CONd_EQ",
        "name": "Continental AG",
        "isin": "DE0005439004",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "CON.DE",
        "gettex": "GETTEX:CON",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "AUTOMOTIVE_COMPONENTI",
        "role_desc": "Colosso Componentistica & Pneumatici DAX (Senza Tetto)",
        "ref_price_eur": 64.00,
        "shield_activation_pct": 0.0066,
        "shield_pullback_pct": 0.0015,
        "beta_tier": "CORE_BLUE_CHIP",
    },
    {
        "fallback_ticker": "FREd_EQ",
        "name": "Fresenius SE & Co. KGaA",
        "isin": "DE0005785604",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "FRE.DE",
        "gettex": "GETTEX:FRE",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "HEALTHCARE_OSPEDALI",
        "role_desc": "Colosso Cliniche & Biopharma Europeo DAX (Senza Tetto)",
        "ref_price_eur": 39.00,
        "shield_activation_pct": 0.0062,
        "shield_pullback_pct": 0.0014,
        "beta_tier": "CORE_BLUE_CHIP",
    },
    {
        "fallback_ticker": "AIXAd_EQ",
        "name": "AIXTRON SE",
        "isin": "DE000A0WMPJ6",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "AIXA.DE",
        "gettex": "GETTEX:AIXA",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "CHIP_POTENZA_PACKAGING",
        "role_desc": "Turbo High-Beta Impianti Epitassia SiC/GaN Chip DAX (Senza Tetto)",
        "ref_price_eur": 15.50,
        "shield_activation_pct": 0.0080,
        "shield_pullback_pct": 0.0018,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    {
        "fallback_ticker": "MRKd_EQ",
        "name": "Merck KGaA",
        "isin": "DE0006599905",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "MRK.DE",
        "gettex": "GETTEX:MRK",
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
        "gettex": "GETTEX:SHL",
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
        "gettex": "GETTEX:EOAN",
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
        "gettex": "GETTEX:RWE",
        "squad": "SQUADRA_1_CECCHINO_GIORNALIERO",
        "sector": "ENERGIA_RINNOVABILE_POWER",
        "role_desc": "Colosso Generazione Elettrica & Rinnovabili DAX (Senza Tetto)",
        "ref_price_eur": 32.00,
        "shield_activation_pct": 0.0062,
        "shield_pullback_pct": 0.0014,
        "beta_tier": "CORE_BLUE_CHIP",
    },
    {
        "fallback_ticker": "DPWd_EQ",
        "name": "DHL Group (Deutsche Post)",
        "isin": "DE0005552004",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "DHL.DE",
        "gettex": "GETTEX:DHL",
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
        "gettex": "GETTEX:BAS",
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
        "gettex": "GETTEX:BMW",
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
        "gettex": "GETTEX:INN1",
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
        "gettex": "GETTEX:1TY",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "TECH_HOLDING_AI",
        "role_desc": "Turbo High-Beta Tech & AI Global Holding AEX (Senza Tetto)",
        "ref_price_eur": 38.00,
        "shield_activation_pct": 0.0072,
        "shield_pullback_pct": 0.0016,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    # --- 7 BIG TECH USA QUOTATE IN EURO SU XETRA (0,00% FX Fee, 0,00% Tobin Tax, Feed GETTEX 0s) ---
    {
        "fallback_ticker": "NVDd_EQ",
        "name": "NVIDIA Corp (EUR)",
        "isin": "US67066G1040",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "NVD.DE",
        "gettex": "GETTEX:NVD",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "CHIP_ACCELERATORI_AI",
        "role_desc": "Turbo High-Beta GPU & AI Accelerators Big Tech USA in EUR (Senza Tetto)",
        "ref_price_eur": 152.00,
        "shield_activation_pct": 0.0082,
        "shield_pullback_pct": 0.0019,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    {
        "fallback_ticker": "MSFd_EQ",
        "name": "Microsoft Corp (EUR)",
        "isin": "US5949181045",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "MSF.DE",
        "gettex": "GETTEX:MSF",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "SOFTWARE_CLOUD",
        "role_desc": "Colosso Cloud Azure & AI Enterprise Big Tech USA in EUR (Senza Tetto)",
        "ref_price_eur": 468.00,
        "shield_activation_pct": 0.0070,
        "shield_pullback_pct": 0.0016,
        "beta_tier": "CORE_BLUE_CHIP",
    },
    {
        "fallback_ticker": "APCd_EQ",
        "name": "Apple Inc (EUR)",
        "isin": "US0378331005",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "APC.DE",
        "gettex": "GETTEX:APC",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "ECOSISTEMA_MOBILE_HARDWARE",
        "role_desc": "Colosso Consumer Ecosystem & Silicon Big Tech USA in EUR (Senza Tetto)",
        "ref_price_eur": 322.00,
        "shield_activation_pct": 0.0068,
        "shield_pullback_pct": 0.0015,
        "beta_tier": "CORE_BLUE_CHIP",
    },
    {
        "fallback_ticker": "AMZd_EQ",
        "name": "Amazon.com Inc (EUR)",
        "isin": "US0231351067",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "AMZ.DE",
        "gettex": "GETTEX:AMZ",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "ECOMMERCE_CONSUMER",
        "role_desc": "Turbo High-Beta AWS Cloud & Global E-Commerce USA in EUR (Senza Tetto)",
        "ref_price_eur": 245.00,
        "shield_activation_pct": 0.0074,
        "shield_pullback_pct": 0.0017,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    {
        "fallback_ticker": "ABEAd_EQ",
        "name": "Alphabet Inc Class A (EUR)",
        "isin": "US02079K3059",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "ABEA.DE",
        "gettex": "GETTEX:ABEA",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "DIGITAL_ADS_SOCIAL_AI",
        "role_desc": "Colosso Search, Gemini AI & Cloud Big Tech USA in EUR (Senza Tetto)",
        "ref_price_eur": 273.00,
        "shield_activation_pct": 0.0072,
        "shield_pullback_pct": 0.0016,
        "beta_tier": "CORE_BLUE_CHIP",
    },
    {
        "fallback_ticker": "FB2Ad_EQ",
        "name": "Meta Platforms Inc (EUR)",
        "isin": "US30303M1027",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "FB2A.DE",
        "gettex": "GETTEX:FB2A",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "DIGITAL_ADS_SOCIAL_AI",
        "role_desc": "Turbo High-Beta Social AI & Digital Ads Big Tech USA in EUR (Senza Tetto)",
        "ref_price_eur": 564.00,
        "shield_activation_pct": 0.0078,
        "shield_pullback_pct": 0.0018,
        "beta_tier": "TURBO_HIGH_BETA",
    },
    {
        "fallback_ticker": "AMDd_EQ",
        "name": "Advanced Micro Devices Inc (EUR)",
        "isin": "US0079031078",
        "exchange": "XETRA (Francoforte)",
        "yahoo": "AMD.DE",
        "gettex": "GETTEX:AMD",
        "squad": "SQUADRA_2_CAVALCA_ONDA",
        "sector": "CHIP_ACCELERATORI_AI",
        "role_desc": "Turbo High-Beta Data Center CPU/GPU AI Big Tech USA in EUR (Senza Tetto)",
        "ref_price_eur": 517.00,
        "shield_activation_pct": 0.0082,
        "shield_pullback_pct": 0.0019,
        "beta_tier": "TURBO_HIGH_BETA",
    },
]


def discover_and_verify_eur_giants(client: Optional[Trading212Client]) -> int:
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

    missing_isins = [c["isin"] for c in CANDIDATE_EUR_GIANTS if c["isin"] not in verified_map]
    if missing_isins and client is not None:
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
                        verified_map[c_isin] = chosen_tkr or ""
                    elif c_isin not in verified_map:
                        verified_map[c_isin] = ""
                if verified_map:
                    with open(VERIFIED_UNIVERSE_CACHE_PATH, "w", encoding="utf-8") as f:
                        json.dump(verified_map, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[RADAR DISCOVERY] Uso universo base / cache locale ({e})", flush=True)

    added_count = 0
    for cand in CANDIDATE_EUR_GIANTS:
        if cand["isin"] in verified_map:
            tkr = verified_map[cand["isin"]]
        else:
            tkr = cand.get("fallback_ticker", "")
        if not tkr:
            # Se l'ISIN è esplicitamente assente su T212 (""), rimuovilo anche se presente da sessioni precedenti
            stale_fb = cand.get("fallback_ticker", "")
            if stale_fb:
                ASSET_PROFILES.pop(stale_fb, None)
                EUR_ZERO_FEE_UNIVERSE.pop(stale_fb, None)
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
            "gettex": cand.get("gettex", ""),
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

    def _fetch_index_snapshot(self, symbol: str) -> Tuple[float, float, bool]:
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
                reg_px = float(meta.get("regularMarketPrice") or 0.0)
                closes = [
                    float(c)
                    for c in res["indicators"]["quote"][0].get("close", [])
                    if c is not None
                ]
                last_lvl = closes[-1] if closes else reg_px
                if closes and prev_close > 0:
                    return round(((closes[-1] - prev_close) / prev_close) * 100.0, 2), round(last_lvl, 2), True
                if len(closes) >= 2 and closes[0] > 0:
                    return round(((closes[-1] - closes[0]) / closes[0]) * 100.0, 2), round(last_lvl, 2), True
                if last_lvl > 0 and prev_close > 0:
                    return round(((last_lvl - prev_close) / prev_close) * 100.0, 2), round(last_lvl, 2), True
        except Exception:
            pass
        return 0.0, 0.0, False

    def evaluate_overnight_wave(self, force: bool = False) -> Dict[str, Any]:
        now_ts = time.time()
        if not force and self.cached_radar and (now_ts - self.last_check_ts) < 120.0:
            return self.cached_radar

        symbols = ("%5EGSPC", "%5EIXIC", "%5EGDAXI", "%5EVIX")
        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = {sym: pool.submit(self._fetch_index_snapshot, sym) for sym in symbols}
            sp500_pct, _, ok_sp = futs["%5EGSPC"].result()
            nasdaq_pct, _, ok_nq = futs["%5EIXIC"].result()
            dax_pct, _, ok_dax = futs["%5EGDAXI"].result()
            vix_pct, vix_raw_lvl, ok_vix = futs["%5EVIX"].result()

        prev = self.cached_radar
        if not ok_sp and prev:
            sp500_pct = float(prev.get("sp500_change_pct", 0.0))
            ok_sp = True
        if not ok_nq and prev:
            nasdaq_pct = float(prev.get("nasdaq_change_pct", 0.0))
            ok_nq = True
        if not ok_dax and prev:
            dax_pct = float(prev.get("dax_change_pct", 0.0))
            ok_dax = True
        if not ok_vix and prev:
            vix_pct = float(prev.get("vix_fear_change_pct", 0.0))
            vix_raw_lvl = float(prev.get("vix_level", 16.0))
            ok_vix = True

        vix_level = vix_raw_lvl if (ok_vix and vix_raw_lvl > 0.0) else 20.0
        us_and_vix_reliable = bool((ok_nq or ok_sp) and ok_vix)

        # V11.2 Regola Istituzionale VIX con Protezione Zero-Ghost su Timeout Yahoo:
        # Se i feed USA/VIX non rispondono e non esiste cache valida, vieta falsi positivi overnight!
        us_avg_pct = round((nasdaq_pct * 0.6 + sp500_pct * 0.4), 2)
        vix_calm_for_overnight = us_and_vix_reliable and ((vix_pct <= 2.5) or (vix_level < 18.5 and vix_pct <= 7.5))
        vix_ultra_calm = us_and_vix_reliable and ((vix_pct <= 1.0) or (vix_level < 17.5 and vix_pct <= 5.0))
        vix_is_elevated_fear = (
            not us_and_vix_reliable
            or (vix_level >= 18.5 and vix_pct >= 3.5)
            or vix_pct >= 9.0
            or vix_level >= 24.0
        )
        is_positive_wave = us_and_vix_reliable and (
            (nasdaq_pct > 0.0 and sp500_pct > 0.0 and us_avg_pct >= 0.25 and vix_calm_for_overnight)
            or (us_avg_pct >= 0.10 and dax_pct >= 0.45 and vix_ultra_calm)
        )

        if is_positive_wave:
            verdict = "ONDA_NOTTURNA_POSITIVA_CAVALCA_IL_GAP_09_00"
            explanation = (
                f"Wall Street spinge al rialzo (Nasdaq {nasdaq_pct:+.2f}%, S&P500 {sp500_pct:+.2f}%, "
                f"VIX {vix_level:.1f} [{vix_pct:+.2f}%]): ALTA PROBABILITÀ di salto positivo domattina alle 09:00. "
                "Il bot MANTIENE APERTE per la notte le cartucce forti sopra il VWAP!"
            )
        else:
            verdict = "ONDA_NOTTURNA_INCERTA_O_NEGATIVA_SCUDO_ATTIVO"
            explanation = (
                f"Prudenza notturna (Nasdaq {nasdaq_pct:+.2f}%, S&P500 {sp500_pct:+.2f}%, "
                f"DAX {dax_pct:+.2f}%, VIX {vix_level:.1f} [{vix_pct:+.2f}%]): alle 17:15 il bot INCASSA IN CONTANTI EUR "
                "i profitti fatti in giornata per evitare cali notturni e comprare a sconto alle 09:00!"
            )

        self.cached_radar = {
            "verdict": verdict,
            "allow_overnight_hold": is_positive_wave,
            "nasdaq_change_pct": nasdaq_pct,
            "sp500_change_pct": sp500_pct,
            "dax_change_pct": dax_pct,
            "vix_fear_change_pct": vix_pct,
            "vix_level": vix_level,
            "vix_is_elevated_fear": vix_is_elevated_fear,
            "spiegazione_strategica": explanation,
        }
        self.last_check_ts = now_ts
        return self.cached_radar


GETTEX_SCANNER_URL = "https://scanner.tradingview.com/germany/scan"


class QuantMarketScanner:
    """Scanner quantitativo a 5 minuti con Fusione Zero-Latency (Tick 0ms Trading 212 + Feed 0s GETTEX + Storico Volumi XETRA)."""

    def __init__(self, cache_path: Optional[str] = None) -> None:
        self.cache_path = cache_path
        self.live_prices: Dict[str, float] = {
            tkr: float(prof["ref_price_eur"]) for tkr, prof in ASSET_PROFILES.items()
        }
        self.has_t212_realtime: Dict[str, bool] = {}
        self.has_gettex_realtime: Dict[str, bool] = {}
        self.last_gettex_ts: Dict[str, float] = {}
        self.last_gettex_batch_ts: float = 0.0
        # Buffer di candele a 5 minuti costruite in tempo reale (0ms T212 / 0s GETTEX)
        self.realtime_5m_bars: Dict[str, Dict[int, Dict[str, float]]] = {
            tkr: {} for tkr in ASSET_PROFILES
        }
        # V11.2 Zero-Ghost Cache: conserva l'ultima serie valida di candele 5m anche tra i batch Cloud (con int keys tipizzate)
        self.last_valid_bars: Dict[str, Dict[str, Any]] = {}
        self.last_scan_ts: float = 0.0
        self.cached_metrics: Dict[str, Dict[str, Any]] = {}
        if self.cache_path:
            self.load_disk_cache()

    def load_disk_cache(self) -> None:
        if not self.cache_path or not os.path.exists(self.cache_path):
            return
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            today_iso = datetime.datetime.now(MARKET_TZ).date().isoformat()
            if raw.get("date") != today_iso:
                return
            for tkr, bmap in raw.get("realtime_5m_bars", {}).items():
                if isinstance(bmap, dict):
                    self.realtime_5m_bars[tkr] = {
                        int(k): {
                            "open": float(v["open"]),
                            "high": float(v["high"]),
                            "low": float(v["low"]),
                            "close": float(v["close"]),
                        }
                        for k, v in bmap.items()
                        if isinstance(v, dict) and "close" in v
                    }
            for tkr, cb in raw.get("last_valid_bars", {}).items():
                if isinstance(cb, dict) and cb.get("closes"):
                    cb["bar_timestamps"] = [int(ts) for ts in cb.get("bar_timestamps", [])]
                    self.last_valid_bars[tkr] = cb
        except Exception:
            pass

    def save_disk_cache(self) -> None:
        if not self.cache_path:
            return
        try:
            today_iso = datetime.datetime.now(MARKET_TZ).date().isoformat()
            payload = {
                "date": today_iso,
                "realtime_5m_bars": {
                    tkr: {str(k): v for k, v in bmap.items()}
                    for tkr, bmap in self.realtime_5m_bars.items()
                    if bmap
                },
                "last_valid_bars": self.last_valid_bars,
            }
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, separators=(",", ":"))
        except Exception:
            pass

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

    def refresh_gettex_live_quotes(self, force: bool = False) -> int:
        """
        Occhio Real-Time 0s GETTEX (Borsa di Monaco di Baviera):
        Aggiorna in un'unica chiamata HTTP batch tutti i 39 Colossi in EUR con ritardo 0 secondi
        (mode == 'streaming'), eliminando il ritardo di 15m di Yahoo Finance sulla panchina senza
        toccare i volumi istituzionali XETRA usati per RVOL. Le posizioni già aperte su Trading 212
        mantengono priorità assoluta sul prezzo esecutivo T212 (0ms).
        """
        now_ts = time.time()
        for tkr_exp, ts_exp in list(self.last_gettex_ts.items()):
            if (now_ts - ts_exp) > 90.0:
                self.has_gettex_realtime[tkr_exp] = False

        if not force and (now_ts - self.last_gettex_batch_ts) < 4.5:
            return 0

        gx_to_tkr = {
            str(prof["gettex"]): tkr
            for tkr, prof in ASSET_PROFILES.items()
            if prof.get("gettex")
        }
        if not gx_to_tkr:
            return 0

        payload = json.dumps({
            "symbols": {"tickers": list(gx_to_tkr.keys()), "query": {"types": []}},
            "columns": ["close", "open|5", "high|5", "low|5", "close|5", "update_mode"],
        }).encode("utf-8")
        req = urllib.request.Request(
            GETTEX_SCANNER_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)",
            },
        )
        now_dt = datetime.datetime.now(MARKET_TZ)
        hm = now_dt.hour * 60 + now_dt.minute
        mkt_open = now_dt.weekday() < 5 and (9 * 60 <= hm < 17 * 60 + 30)
        bucket_5m = int(now_ts // 300) * 300
        updated = 0
        try:
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            for row in raw.get("data", []):
                gx_sym = str(row.get("s", ""))
                vals = row.get("d", [])
                tkr = gx_to_tkr.get(gx_sym)
                if not tkr or len(vals) < 6 or vals[0] is None:
                    continue
                if str(vals[5]) != "streaming":
                    continue
                px = round(float(vals[0]), 4)
                if px <= 0:
                    continue
                o5 = round(float(vals[1]) if vals[1] is not None else px, 4)
                c5 = px
                h5 = round(max(float(vals[2]) if vals[2] is not None else px, o5, c5), 4)
                l5 = round(min(float(vals[3]) if vals[3] is not None else px, o5, c5), 4)
                self.has_gettex_realtime[tkr] = True
                self.last_gettex_ts[tkr] = now_ts
                updated += 1
                if not self.has_t212_realtime.get(tkr, False):
                    self.live_prices[tkr] = px
                    if mkt_open:
                        bars = self.realtime_5m_bars.setdefault(tkr, {})
                        bars[bucket_5m] = {"open": o5, "high": h5, "low": l5, "close": c5}
            if updated > 0:
                self.last_gettex_batch_ts = now_ts
        except Exception:
            pass
        return updated

    def fetch_5m_metrics(
        self,
        ticker: str,
        tax_data: Optional[Dict[str, Any]] = None,
        dax_change_pct: float = 0.0,
    ) -> Dict[str, Any]:
        prof = ASSET_PROFILES[ticker]
        ysymbol = prof["yahoo"]
        now_cet_bar = datetime.datetime.now(MARKET_TZ)
        today_date = now_cet_bar.date()
        has_live_stream = bool(
            self.has_t212_realtime.get(ticker, False)
            or self.has_gettex_realtime.get(ticker, False)
        )
        # V11.1 Range Dinamico: 5d fino alle 11:00 CET (continuità mattutina), 1d dopo le 11:00 quando ci sono >= 20 barre odierne (5x più leggero!)
        cached_prev = self.last_valid_bars.get(ticker)
        use_fast_1d = (
            cached_prev is not None
            and cached_prev.get("cached_date") == today_date.isoformat()
            and int(cached_prev.get("yahoo_today_bars", 0)) >= 18
            and now_cet_bar.weekday() < 5
            and now_cet_bar.hour >= 11
        )
        yrange = "1d" if use_fast_1d else "5d"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ysymbol}?interval=5m&range={yrange}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)"},
        )
        opens: List[float] = []
        closes: List[float] = []
        highs: List[float] = []
        lows: List[float] = []
        vols: List[float] = []
        yahoo_nonzero_vols: List[float] = []
        yahoo_nonzero_buckets: List[int] = []
        bar_timestamps: List[int] = []
        last_yahoo_ts: int = 0
        raw_last_yahoo_ts: int = 0
        yahoo_today_bars: int = 0
        try:
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                result = data["chart"]["result"][0]
                meta_info = result.get("meta", {})
                reg_px = meta_info.get("regularMarketPrice")
                if reg_px and not has_live_stream:
                    self.live_prices[ticker] = round(float(reg_px), 4)
                timestamps = result.get("timestamp", [])
                quote = result["indicators"]["quote"][0]
                raw_opens = quote.get("open") or []
                for idx_q, (ts, c, h, l, v) in enumerate(zip(
                    timestamps,
                    quote.get("close", []),
                    quote.get("high", []),
                    quote.get("low", []),
                    quote.get("volume", []),
                )):
                    if c is not None and h is not None and l is not None:
                        c_f, h_f, l_f = float(c), float(h), float(l)
                        o_raw = raw_opens[idx_q] if idx_q < len(raw_opens) else None
                        o_f = float(o_raw) if o_raw is not None else (closes[-1] if closes else c_f)
                        v_f = float(v or 0.0)
                        ts_int = int(ts)
                        bucket_ts = int(ts_int // 300) * 300
                        b_dt_v = datetime.datetime.fromtimestamp(bucket_ts, tz=MARKET_TZ)
                        is_closing_auction_spike = (b_dt_v.hour == 17 and b_dt_v.minute >= 25)
                        if v_f > 0.0 and not is_closing_auction_spike:
                            if yahoo_nonzero_buckets and yahoo_nonzero_buckets[-1] == bucket_ts:
                                yahoo_nonzero_vols[-1] = max(yahoo_nonzero_vols[-1], v_f)
                            else:
                                yahoo_nonzero_vols.append(v_f)
                                yahoo_nonzero_buckets.append(bucket_ts)
                        # V10.0: Deduplica candele Yahoo nello stesso bucket da 5 minuti (evita barra parziale duplicata)
                        if bar_timestamps and int(bar_timestamps[-1] // 300) * 300 == bucket_ts:
                            closes[-1] = c_f
                            highs[-1] = max(highs[-1], h_f)
                            lows[-1] = min(lows[-1], l_f)
                            if v_f > 0.0:
                                vols[-1] = v_f
                        else:
                            opens.append(o_f)
                            closes.append(c_f)
                            highs.append(h_f)
                            lows.append(l_f)
                            vols.append(v_f)
                            bar_timestamps.append(bucket_ts)
                            if datetime.datetime.fromtimestamp(bucket_ts, tz=MARKET_TZ).date() == today_date:
                                yahoo_today_bars += 1
                        last_yahoo_ts = bucket_ts
                        raw_last_yahoo_ts = ts_int
        except Exception:
            pass

        # V11.0 Blocco 1 (Zero-Ghost Cache): salva serie valida o ripristina da cache reale in caso di timeout HTTP Yahoo
        if len(closes) >= 6:
            self.last_valid_bars[ticker] = {
                "opens": list(opens),
                "closes": list(closes),
                "highs": list(highs),
                "lows": list(lows),
                "vols": list(vols),
                "yahoo_nonzero_vols": list(yahoo_nonzero_vols),
                "bar_timestamps": list(bar_timestamps),
                "last_yahoo_ts": last_yahoo_ts,
                "yahoo_today_bars": yahoo_today_bars,
                "cached_date": today_date.isoformat(),
            }
        elif ticker in self.last_valid_bars:
            cached_b = self.last_valid_bars[ticker]
            closes = list(cached_b["closes"])
            opens = list(cached_b.get("opens") or closes)
            highs = list(cached_b["highs"])
            lows = list(cached_b["lows"])
            vols = list(cached_b["vols"])
            yahoo_nonzero_vols = list(cached_b["yahoo_nonzero_vols"])
            bar_timestamps = list(cached_b["bar_timestamps"])
            last_yahoo_ts = int(cached_b["last_yahoo_ts"])
            yahoo_today_bars = (
                int(cached_b["yahoo_today_bars"])
                if cached_b.get("cached_date") == today_date.isoformat()
                else 0
            )

        # V10.0: Volume medio reale calcolato SOLO sulle candele Yahoo completate con volume > 0
        if len(yahoo_nonzero_vols) >= 2:
            base_v_slice = yahoo_nonzero_vols[-11:-1] if len(yahoo_nonzero_vols) >= 3 else yahoo_nonzero_vols[:-1]
            avg_vol_est = sum(base_v_slice) / len(base_v_slice)
        elif yahoo_nonzero_vols:
            avg_vol_est = yahoo_nonzero_vols[-1]
        else:
            avg_vol_est = 1000.0

        # Ripristina peso VWAP corretto se l'ultima candela in formazione di Yahoo aveva volume = 0
        if vols and vols[-1] <= 0.0:
            vols[-1] = avg_vol_est

        # BLINDATURA #11 (V11.2 In-Place 5m Fusion 0ms/0s + Ponte Cold-Start Intraday):
        # cuce senza sdoppiamenti le candele live di Trading 212 / GETTEX mantenendo intatto RVOL XETRA!
        rt_bars = self.realtime_5m_bars.get(ticker, {})
        for b_ts in sorted(rt_bars.keys()):
            b_bucket = int(b_ts // 300) * 300
            b_dt = datetime.datetime.fromtimestamp(b_bucket, tz=MARKET_TZ)
            b_hm = b_dt.hour * 60 + b_dt.minute
            if b_dt.weekday() < 5 and (9 * 60 <= b_hm < 17 * 60 + 30):
                b = rt_bars[b_ts]
                if bar_timestamps and b_bucket == bar_timestamps[-1]:
                    if (
                        len(opens) == len(closes)
                        and "open" in b
                        and float(b["open"]) > 0
                        and not self.has_t212_realtime.get(ticker, False)
                    ):
                        opens[-1] = float(b["open"])
                    closes[-1] = b["close"]
                    highs[-1] = max(highs[-1], b["high"], opens[-1] if opens else b["high"])
                    lows[-1] = min(lows[-1], b["low"], opens[-1] if opens else b["low"])
                elif b_bucket > last_yahoo_ts and (not bar_timestamps or b_bucket > bar_timestamps[-1]):
                    if bar_timestamps:
                        prev_ts = bar_timestamps[-1]
                        prev_dt = datetime.datetime.fromtimestamp(prev_ts, tz=MARKET_TZ)
                        gap_steps = (b_bucket - prev_ts) // 300
                        if prev_dt.date() == b_dt.date() and 2 <= gap_steps <= 4:
                            p_start = closes[-1]
                            p_end = float(b.get("open", b["close"]))
                            for step_k in range(1, gap_steps):
                                mid_ts = prev_ts + step_k * 300
                                c_prev_step = closes[-1]
                                c_step = round(p_start + (p_end - p_start) * (step_k / float(gap_steps)), 4)
                                opens.append(c_prev_step)
                                closes.append(c_step)
                                highs.append(max(c_prev_step, c_step))
                                lows.append(min(c_prev_step, c_step))
                                vols.append(avg_vol_est)
                                bar_timestamps.append(mid_ts)
                    bar_open_f = float(b.get("open", closes[-1] if closes else b["close"]))
                    opens.append(bar_open_f)
                    closes.append(b["close"])
                    highs.append(max(b["high"], bar_open_f, b["close"]))
                    lows.append(min(b["low"], bar_open_f, b["close"]))
                    vols.append(avg_vol_est)
                    bar_timestamps.append(b_bucket)

        if closes:
            last_c = self.live_prices.get(ticker, closes[-1])
            now_hm = now_cet_bar.hour * 60 + now_cet_bar.minute
            mkt_open_now = now_cet_bar.weekday() < 5 and (9 * 60 <= now_hm < 17 * 60 + 30)
            now_bucket = int(time.time() // 300) * 300
            if abs(last_c - closes[-1]) > 1e-4:
                if (
                    has_live_stream
                    and mkt_open_now
                    and bar_timestamps
                    and now_bucket > bar_timestamps[-1]
                ):
                    prev_c_spot = closes[-1]
                    opens.append(prev_c_spot)
                    closes.append(last_c)
                    highs.append(max(last_c, prev_c_spot))
                    lows.append(min(last_c, prev_c_spot))
                    vols.append(avg_vol_est)
                    bar_timestamps.append(now_bucket)
                else:
                    # Aggiornamento in-place della punta 0ms/spot dentro il bucket corrente (zero candele sintetiche sui dati ritardati!)
                    closes[-1] = last_c
                    highs[-1] = max(highs[-1], last_c)
                    lows[-1] = min(lows[-1], last_c)
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
                sum(((h + l + c) / 3.0) * v for h, l, c, v in zip(sess_highs, sess_lows, sess_closes, sess_vols)) / tot_vol
                if tot_vol > 0
                else sum(sess_closes) / len(sess_closes)
            )
            vwap_dist_pct = ((last_c - vwap) / vwap) * 100.0 if vwap > 0 else 0.0
        else:
            today_indices = []
            last_c = self.live_prices.get(ticker, float(prof["ref_price_eur"]))
            rsi_14 = 50.0
            dip_from_high_pct = 0.0
            day_range_pct = 0.0
            vwap_dist_pct = 0.0

        has_valid_bars = len(closes) >= 6
        if has_valid_bars:
            first_today_idx = today_indices[0] if today_indices else 0
            ref_idx_2 = max(first_today_idx, len(closes) - 2)
            ref_idx_3 = max(first_today_idx, len(closes) - 3)
            ref_idx_4 = max(first_today_idx, len(closes) - 4)
            ref_idx_7 = max(first_today_idx, len(closes) - 7)
            if len(today_indices) == 1 and ref_idx_2 == len(closes) - 1:
                cur_open_09 = (
                    opens[-1]
                    if len(opens) == len(closes) and opens[-1] > 0
                    else ((highs[-1] + lows[-1]) / 2.0)
                )
                price_turning_down = closes[-1] < cur_open_09
                falling_knife = (
                    closes[-1] < cur_open_09
                    and (highs[-1] - lows[-1]) > 0
                    and closes[-1] <= (lows[-1] + 0.25 * (highs[-1] - lows[-1]))
                )
                breakout_candle = (closes[-1] > highs[-2]) if len(highs) >= 2 else False
                higher_low = closes[-1] >= cur_open_09
                green_hook_confirmed = not falling_knife and closes[-1] >= cur_open_09
                entry_hook_confirmed = (
                    green_hook_confirmed
                    and (closes[-1] - cur_open_09) >= (closes[-1] * 0.0005)
                )
            else:
                cur_open = (
                    opens[-1]
                    if len(opens) == len(closes) and opens[-1] > 0
                    else closes[ref_idx_2]
                )
                price_turning_down = (closes[-1] < closes[ref_idx_2]) or (closes[-1] < cur_open)
                falling_knife = (closes[-1] < closes[ref_idx_2] and closes[ref_idx_2] < closes[ref_idx_3])
                breakout_candle = (closes[-1] > highs[ref_idx_2]) if len(highs) >= 2 else False
                higher_low = (lows[-1] >= lows[ref_idx_2]) if len(lows) >= 2 else True
                # V11.2 Invariante #22 (True Green Hook Zero-Cerotti, condiviso con gli Scudi di Uscita):
                # vieta qualsiasi ingresso su candela 5m rossa (close < open) o in ripiegamento dal picco precedente (close < prev_close).
                green_hook_confirmed = (
                    not falling_knife
                    and closes[-1] >= closes[ref_idx_2]
                    and closes[-1] >= cur_open
                )
                # V11.2 Invariante #24 (Anti-Micro-Tick post-Candela Rossa SOLO per nuovi ingressi, zero impatto sugli Scudi):
                # esige almeno +0,05% (1 spread Bid-Ask) sopra open/prev_close e, se la candela 5m precedente era rossa,
                # il recupero strutturale di almeno il 30% del corpo ribassista precedente (blocca i dead-cat tick da +0,02% a :00).
                prev_open_r2 = (
                    opens[ref_idx_2]
                    if len(opens) == len(closes) and opens[ref_idx_2] > 0
                    else closes[ref_idx_3]
                )
                prev_red_drop = max(0.0, prev_open_r2 - closes[ref_idx_2])
                min_entry_body = max(prev_red_drop * 0.30, closes[-1] * 0.0005)
                entry_hook_confirmed = (
                    green_hook_confirmed
                    and (closes[-1] - min(cur_open, closes[ref_idx_2])) >= min_entry_body
                )
            slope_rising = (closes[-1] >= closes[ref_idx_3])
            slope_15m_pct = ((closes[-1] - closes[ref_idx_4]) / closes[ref_idx_4] * 100.0) if closes[ref_idx_4] > 0 else 0.0
            slope_30m_pct = ((closes[-1] - closes[ref_idx_7]) / closes[ref_idx_7] * 100.0) if closes[ref_idx_7] > 0 else slope_15m_pct
            if len(yahoo_nonzero_vols) >= 3:
                # V11.1 RVOL Istituzionale Senza Bias di Candela Parziale:
                # 1) Se l'ultima candela Yahoo è ancora in formazione (0 < offset < 270s), proietta il ritmo reale sui 300s;
                # 2) Confronta il picco delle ultime 2 candele (cattura sia breakout sia Bull-Flag stretta) contro le 10 candele chiuse precedenti!
                intra_bar_offset = raw_last_yahoo_ts - last_yahoo_ts if raw_last_yahoo_ts > last_yahoo_ts else 0
                last_raw_v = yahoo_nonzero_vols[-1]
                if 0 < intra_bar_offset < 270:
                    scaled_last_v = last_raw_v * (300.0 / max(45.0, float(intra_bar_offset)))
                else:
                    scaled_last_v = last_raw_v
                if len(yahoo_nonzero_vols) >= 4:
                    recent_v_base = yahoo_nonzero_vols[-12:-2]
                    eff_vol = max(scaled_last_v, yahoo_nonzero_vols[-2])
                else:
                    recent_v_base = yahoo_nonzero_vols[:-1]
                    eff_vol = scaled_last_v
                avg_recent_vol = sum(recent_v_base) / len(recent_v_base) if recent_v_base else eff_vol
                volume_drying_up = (eff_vol < avg_recent_vol * 0.85)
                rvol_ratio = round(eff_vol / avg_recent_vol, 2) if avg_recent_vol > 0 else 1.0
            else:
                volume_drying_up = False
                rvol_ratio = 0.0
            # Calcolo ATR 5m Intraday Puro (esclude salti overnight/halt > 1800s dal True Range a 5 minuti!)
            tr_pcts: List[float] = []
            start_idx = max(1, len(closes) - 14)
            for i in range(start_idx, len(closes)):
                prev_c = closes[i - 1]
                if prev_c > 0:
                    has_time_gap = (
                        len(bar_timestamps) == len(closes)
                        and (bar_timestamps[i] - bar_timestamps[i - 1]) > 1800
                    )
                    if has_time_gap:
                        tr = highs[i] - lows[i]
                    else:
                        tr = max(
                            highs[i] - lows[i],
                            abs(highs[i] - prev_c),
                            abs(lows[i] - prev_c),
                        )
                    tr_pcts.append(tr / prev_c)
            atr_5m_pct = (sum(tr_pcts) / len(tr_pcts)) if tr_pcts else 0.0018

            # Indice di Pulizia dell'Onda di Kaufman Intraday Puro (Efficiency Ratio senza contaminazione gap 16h)
            if len(today_indices) >= 4:
                k_start = max(first_today_idx, len(closes) - 11)
                net_move = abs(closes[-1] - closes[k_start])
                path_move = sum(abs(closes[j] - closes[j - 1]) for j in range(k_start + 1, len(closes)))
                kaufman_er = round(net_move / path_move, 2) if path_move > 0 else 0.0
            else:
                k_win = min(10, len(closes) - 1)
                net_move = abs(closes[-1] - closes[-1 - k_win])
                path_move = sum(abs(closes[j] - closes[j - 1]) for j in range(len(closes) - k_win, len(closes)))
                kaufman_er = round(net_move / path_move, 2) if path_move > 0 else 0.0
        else:
            # V11.0 Invariante Anti-Fantasma: in assenza di candele reali, ZERO numeri inventati (Score = 0.0)
            ref_idx_2 = 0
            price_turning_down = False
            breakout_candle = False
            higher_low = False
            green_hook_confirmed = False
            entry_hook_confirmed = False
            slope_rising = False
            slope_15m_pct = 0.0
            slope_30m_pct = 0.0
            volume_drying_up = True
            rvol_ratio = 0.0
            atr_5m_pct = 0.0
            kaufman_er = 0.0

        # V11.0 Blocco 2 — RANKING LINEARE ADDITIVO PURO "ZERO CEROTTI" (Validato Walk-Forward 0s: +5,06 EUR / 5gg, 5/5 verdi):
        # 1) Setup Momentum Istituzionale sul pavimento VWAP (-0,15% .. +0,48%, RSI 42..66)
        if has_valid_bars and vwap_dist_pct >= -0.15 and 42.0 <= rsi_14 <= 66.0 and entry_hook_confirmed:
            vwap_extension_taper = max(0.0, (vwap_dist_pct - 0.48) * 32.0)
            score_momentum = (
                68.0
                + (kaufman_er * 14.0)
                + (4.0 if breakout_candle else 0.0)
                - vwap_extension_taper
            )
        else:
            score_momentum = 0.0

        # 2) Setup Institutional VWAP Pullback (-0,35% .. +0,48%, RSI 32..64, trend 30m sano, mai in rottura ribassista sotto VWAP)
        sub_vwap_downtrend = (vwap_dist_pct < -0.05 and slope_15m_pct < -0.10)
        if (
            has_valid_bars
            and vwap_dist_pct >= -0.35
            and not sub_vwap_downtrend
            and 32.0 <= rsi_14 <= 64.0
            and entry_hook_confirmed
            and slope_30m_pct >= -0.45
        ):
            pullback_ext_taper = max(0.0, (vwap_dist_pct - 0.48) * 32.0)
            score_pullback = (
                54.0
                + min(24.0, max(0.0, (64.0 - rsi_14) * 0.95))
                + (kaufman_er * 12.0)
                + (4.0 if breakout_candle else 0.0)
                - pullback_ext_taper
            )
        else:
            score_pullback = 0.0

        base_setup_score = max(score_momentum, score_pullback)
        beta_tier = prof.get("beta_tier", "CORE_BLUE_CHIP")

        # 3) Bonus Lineare di Velocità ATR (0..10 pt) — ZERO distorsione moltiplicativa 1,55x e ZERO saturazione a 100!
        atr_pct_100 = atr_5m_pct * 100.0
        velocity_bonus = round(min(10.0, max(0.0, (atr_pct_100 - 0.12) * 45.0)), 1)
        profit_velocity_mult = round(1.0 + (velocity_bonus / 100.0), 2)

        # 4) Memoria Giornaliera Pulita Post-Epoca V11 (Zero penalità storiche sporche dei giorni/motori precedenti!)
        memory_bonus = 0.0
        if tax_data and "operazioni_chiuse" in tax_data:
            epoch_str = str(tax_data.get("v11_clean_epoch_ts", V11_CLEAN_EPOCH_TS))
            today_prefix = datetime.datetime.now(MARKET_TZ).date().isoformat()
            today_ops = [
                op for op in tax_data.get("operazioni_chiuse", [])
                if op.get("ticker") == ticker
                and str(op.get("timestamp", "")).startswith(today_prefix)
                and str(op.get("timestamp", "")) >= epoch_str
            ]
            if today_ops:
                last_today_pnl = float(today_ops[-1].get("risultato_fiscale_eur", 0.0))
                today_wins = sum(1 for op in today_ops if float(op.get("risultato_fiscale_eur", 0.0)) > 0.0)
                today_losses = sum(1 for op in today_ops if float(op.get("risultato_fiscale_eur", 0.0)) < 0.0)
                if last_today_pnl < 0.0:
                    memory_bonus = -22.0
                elif today_wins >= 2 and today_losses == 0:
                    memory_bonus = 2.0

        if not has_valid_bars or base_setup_score <= 0.0:
            quant_score = 0.0
        else:
            quant_score = round(
                max(0.0, min(100.0, base_setup_score + velocity_bonus + memory_bonus)),
                1,
            )

        # Fattore elastico ATR (tra 0.80x su mercato piatto e 1.30x su mercato esplosivo)
        effective_atr = atr_5m_pct if has_valid_bars and atr_5m_pct > 0 else 0.0018
        vol_scale = round(max(0.80, min(1.30, effective_atr / 0.0018)), 2)
        base_act = float(prof["shield_activation_pct"])
        base_pull = float(prof["shield_pullback_pct"])
        elastic_shield_act = round(max(0.0048, base_act * vol_scale), 4)
        elastic_shield_pull = round(max(0.0012, base_pull * vol_scale), 4)
        be_trig_est = max(0.0042, min(0.0050, round(effective_atr * 2.1, 4)))
        be_floor_est = max(0.0018, round(be_trig_est * 0.45, 4))

        if not has_valid_bars:
            sine_phase = "DATI_INTRADAY_IN_ATTESA"
            strong_for_overnight = False
        elif rsi_14 > 68.0 and price_turning_down and volume_drying_up:
            sine_phase = "CRESTA_IN_INVERSIONE_FALSO_POSITIVO"
            strong_for_overnight = False
        elif score_momentum >= 55.0 or (rsi_14 > 60.0 and vwap_dist_pct >= 0.0 and (not price_turning_down or slope_rising)):
            sine_phase = "SUPER_TREND_VERO_POSITIVO_BREAKOUT"
            strong_for_overnight = vwap_dist_pct >= -0.05
        elif rsi_14 >= 38.0 and (score_pullback >= 52.0 or (38.0 <= rsi_14 <= 64.0 and (slope_rising or green_hook_confirmed) and vwap_dist_pct >= -0.05)):
            sine_phase = "ONDA_ASCENDENTE_SANA_VERO_POSITIVO"
            strong_for_overnight = vwap_dist_pct >= -0.05
        elif rsi_14 < 38.0 and green_hook_confirmed:
            sine_phase = "VALLE_CON_UNCINO_VERDE_PRONTO_ACQUISTO"
            strong_for_overnight = False
        elif rsi_14 < 38.0:
            sine_phase = "COLTELLO_IN_CADUTA_ATTENDERE_UNCINO_VERDE"
            strong_for_overnight = False
        else:
            sine_phase = "ONDA_DISCENDENTE_O_DEBOLE"
            strong_for_overnight = False

        if self.has_t212_realtime.get(ticker, False):
            feed_source = "T212_LIVE_0MS"
        elif self.has_gettex_realtime.get(ticker, False):
            feed_source = "GETTEX_STREAMING_0S"
        else:
            feed_source = "YAHOO_FALLBACK_15M"

        return {
            "ticker": ticker,
            "name": EUR_ZERO_FEE_UNIVERSE[ticker]["name"],
            "squad": prof["squad"],
            "sector": prof["sector"],
            "beta_tier": beta_tier,
            "role_desc": prof["role_desc"],
            "live_price_eur": round(last_c, 4),
            "price_feed_source": feed_source,
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
            "entry_hook_confirmed": entry_hook_confirmed,
            "breakout_5m": breakout_candle,
            "strong_for_overnight": strong_for_overnight,
            "yahoo_today_bars": yahoo_today_bars,
            "has_fresh_intraday_feed": bool(has_valid_bars and (yahoo_today_bars >= 2 or len(today_indices) >= 2)),
            "shield_activation_pct": round(elastic_shield_act * 100, 2),
            "shield_pullback_pct": round(elastic_shield_pull * 100, 2),
            "elastic_shield_act_raw": elastic_shield_act,
            "elastic_shield_pull_raw": elastic_shield_pull,
            "pre_shield_breakeven_trigger_pct": round(be_trig_est * 100, 2),
            "pre_shield_breakeven_floor_pct": round(be_floor_est * 100, 2),
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
        # Architettura Split-Speed Turbo V11.2 + GETTEX 0s (6s Posizioni Aperte / Radar Globale 39 Titoli):
        # - In 1 singola chiamata HTTP batch aggiorna in streaming 0s tutti i 39 Colossi da GETTEX (Monaco).
        # - Ogni 24s (o subito se c'è una cartuccia libera: force=True) ricalcola le metriche 5m di tutti i 39 Colossi.
        full_radar_due = force or not self.cached_metrics or (now_ts - self.last_scan_ts) >= 22.0
        if full_radar_due:
            self.refresh_gettex_live_quotes(force=False)
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
        self.prev_open_snapshot: Dict[str, Tuple[float, float]] = {}
        self._load_persisted_peaks()

    def sync_from_tax_data(self, tx: Dict[str, Any]) -> None:
        """Sincronizza cooldown e ultimi prezzi di vendita post-epoca V11 dal registro fiscale (Anti-Split-Brain)."""
        if not tx:
            return
        epoch_str = str(tx.get("v11_clean_epoch_ts", V11_CLEAN_EPOCH_TS))
        today_prefix_sync = datetime.datetime.now(MARKET_TZ).date().isoformat()
        for op in tx.get("operazioni_chiuse", []):
            tkr_op = op.get("ticker")
            ts_op = str(op.get("timestamp", ""))
            px_op = op.get("sell_price_eur")
            pnl_op = float(op.get("risultato_fiscale_eur", 0.0))
            if tkr_op and ts_op and px_op is not None and ts_op >= epoch_str:
                try:
                    dt_op = datetime.datetime.fromisoformat(ts_op)
                    if dt_op.tzinfo is None:
                        dt_op = dt_op.replace(tzinfo=MARKET_TZ)
                    op_epoch = dt_op.timestamp()
                    if op_epoch >= self.last_sell_time.get(tkr_op, 0.0):
                        self.last_sell_time[tkr_op] = op_epoch
                        self.last_sell_price[tkr_op] = float(px_op)
                        self.last_sell_was_loss[tkr_op] = (
                            (pnl_op < 0.0) and ts_op.startswith(today_prefix_sync)
                        )
                except Exception:
                    pass

    def _load_persisted_peaks(self) -> None:
        if os.path.exists(BOT_STATE_PATH):
            try:
                with open(BOT_STATE_PATH, "r", encoding="utf-8") as f:
                    st = json.load(f)
                state_fresh = False
                st_ts_str = str(st.get("timestamp", ""))
                if st_ts_str:
                    st_dt = datetime.datetime.fromisoformat(st_ts_str)
                    if st_dt.tzinfo is None:
                        st_dt = st_dt.replace(tzinfo=MARKET_TZ)
                    state_fresh = abs(time.time() - st_dt.timestamp()) <= 3600.0
                if state_fresh:
                    cd = st.get("cooldown_state", {})
                    if isinstance(cd, dict):
                        for k, v in cd.get("last_sell_price", {}).items():
                            self.last_sell_price[str(k)] = float(v)
                        for k, v in cd.get("last_sell_time", {}).items():
                            self.last_sell_time[str(k)] = float(v)
                        for k, v in cd.get("last_sell_was_loss", {}).items():
                            self.last_sell_was_loss[str(k)] = bool(v)
                for c in st.get("cartucce_4x25_eur", []):
                    tkr = c.get("ticker")
                    pk = c.get("peak_pnl_pct")
                    op_ts = c.get("opened_at_ts")
                    if tkr and pk is not None:
                        self.peak_pnl_pct[tkr] = float(pk) / 100.0
                    if tkr and op_ts is not None:
                        self.position_open_time[tkr] = float(op_ts)
                    if state_fresh and tkr and c.get("status") == "ESEGUITA_IN_PORTAFOGLIO":
                        avg_p = float(c.get("avg_price_eur", 0.0))
                        cur_p = float(c.get("current_price_eur", avg_p))
                        if avg_p > 0:
                            self.prev_open_snapshot[tkr] = (avg_p, cur_p)
            except Exception:
                pass
        tax_path = TAX_TRACKER_PATH
        if os.path.exists(tax_path):
            try:
                with open(tax_path, "r", encoding="utf-8") as f:
                    tx = json.load(f)
                for tkr, lots in tx.get("lotti_aperti_lifo", {}).items():
                    if lots:
                        ts_str = lots[-1].get("timestamp", "")
                        if ts_str:
                            dt = datetime.datetime.fromisoformat(ts_str)
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=MARKET_TZ)
                            self.position_open_time[tkr] = max(
                                self.position_open_time.get(tkr, 0.0),
                                dt.timestamp(),
                            )
                self.sync_from_tax_data(tx)
            except Exception:
                pass

    def get_intraday_regime(self, now: datetime.datetime) -> Dict[str, Any]:
        now_rome = now if now.tzinfo is not None else now.replace(tzinfo=MARKET_TZ)
        now_ny = now_rome.astimezone(US_EASTERN_TZ)
        hm = now_rome.hour * 60 + now_rome.minute
        ny_hm = now_ny.hour * 60 + now_ny.minute
        us_open = ny_hm >= 9 * 60 + 30  # 09:30 ET apertura reale NYSE/Nasdaq (DST-safe tutto l'anno)
        is_friday = (now_rome.weekday() == 4)
        if now_rome.weekday() >= 5:
            return {
                "code": "WEEKEND_BORSA_CHIUSA",
                "description": "Mercati chiusi per il weekend",
                "market_open": False,
                "allow_new_buys": False,
                "is_pre_close_window": False,
                "is_morning_gap_harvest": False,
                "is_friday_pre_weekend": False,
                "us_market_live": False,
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
                "us_market_live": False,
            }
        if 9 * 60 <= hm < 9 * 60 + 30:
            return {
                "code": "FASE_1A_RACCOLTO_GAP_MATTUTINO_ANTI_GAP_FILL",
                "description": "09:00-09:30: Scudo Ultra-Reattivo (+0,52% / -0,14%) per blindare il salto della notte prima che si sgonfi",
                "market_open": True,
                "allow_new_buys": True,
                "is_pre_close_window": False,
                "is_morning_gap_harvest": True,
                "is_friday_pre_weekend": False,
                "us_market_live": False,
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
                "us_market_live": False,
            }
        if 17 * 60 + 15 <= hm < 17 * 60 + 30:
            return {
                "code": "FASE_4_RADAR_SELETTORE_ONDA_NOTTURNA_E_WEEKEND",
                "description": "17:15-17:30: Blocco Nuovi Acquisti Pre-Chiusura + Selettore Onda Notturna & Scudo Weekend Venerdì",
                "market_open": True,
                "allow_new_buys": False,
                "is_pre_close_window": True,
                "is_morning_gap_harvest": False,
                "is_friday_pre_weekend": is_friday,
                "us_market_live": us_open,
            }
        # Finestra Dati Macro USA ancorata all'orologio reale America/New_York (08:28-08:35 ET, DST-safe Marzo/Ottobre)
        if 8 * 60 + 28 <= ny_hm <= 8 * 60 + 35:
            return {
                "code": "PAUSA_ANTI_SHOCK_DATI_MACRO_USA_14_30",
                "description": "08:28-08:35 ET (14:28-14:35 CET): Scudo Anti-Stop-Hunting durante uscita dati CPI/NFP USA (Scudi vendita attivi, nuovi acquisti in pausa 7 min)",
                "market_open": True,
                "allow_new_buys": False,
                "is_pre_close_window": False,
                "is_morning_gap_harvest": False,
                "is_friday_pre_weekend": False,
                "is_lunch_desert_window": True,
                "us_market_live": False,
            }
        if hm >= 11 * 60 + 15 and ny_hm < 8 * 60 + 28:
            return {
                "code": "FASE_2_CACCIA_ESPLOSIONI_MEZZOGIORNO_MAX2",
                "description": "11:15 CET - 08:27 ET: Cecchino Esplosioni Straordinarie 0s (Max 2/4 Cartucce su Breakout RVOL>=2,2x o Valle Score>=88; 2 slot riservati al pomeriggio)",
                "market_open": True,
                "allow_new_buys": True,
                "is_pre_close_window": False,
                "is_morning_gap_harvest": False,
                "is_friday_pre_weekend": False,
                "is_lunch_desert_window": True,
                "is_midday_sniper_window": True,
                "max_active_slots": 2,
                "us_market_live": False,
            }
        if not us_open:
            return {
                "code": "FASE_2_IBRIDA_2X2_BLINDATA_V5",
                "description": "10:30-11:15 CET & Pre-Market USA (08:36-09:29 ET): Sessione Istituzionale Attiva (Fascia d'Oro + Pavimento VWAP)",
                "market_open": True,
                "allow_new_buys": True,
                "is_pre_close_window": False,
                "is_morning_gap_harvest": False,
                "is_friday_pre_weekend": False,
                "is_lunch_desert_window": False,
                "us_market_live": False,
            }
        return {
            "code": "FASE_3_ONDA_WALL_STREET_SENZA_TETTO",
            "description": "09:30 ET (15:30 CET) - 17:15 CET: Spinta Wall Street - Pre-Scudo Salva-Utile + Scudo Mobile Senza Tetto",
            "market_open": True,
            "allow_new_buys": True,
            "is_pre_close_window": False,
            "is_morning_gap_harvest": False,
            "is_friday_pre_weekend": False,
            "us_market_live": True,
        }

    def compute_profit_protection_floor(
        self,
        peak_pnl_pct: float,
        shield_act: float,
        shield_pull: float,
        atr_raw: float,
        daily_vault_active: bool = False,
    ) -> Tuple[str, Optional[float]]:
        """
        Funzione monotona continua unica (Zero Gradini Ciechi e parità 1:1 Motore == JSON):
        - peak >= shield_act: Scudo Mobile Senza Tetto (peak - shield_pull, gapless fino a -0,05%)
        - 0,58% <= peak < shield_act: Curva Continua Monotona che sale senza buchi da +0,40% fino a (shield_act - shield_pull)
        - breakeven_trigger <= peak < 0,58%: Pre-Scudo Salva-Utile sul pavimento di pareggio protetto
        """
        breakeven_trigger = max(0.0040 if daily_vault_active else 0.0042, min(0.0050, round(atr_raw * 2.1, 4)))
        breakeven_floor = max(0.0016 if daily_vault_active else 0.0018, round(breakeven_trigger * 0.45, 4))
        if peak_pnl_pct >= shield_act:
            return ("UNCAPPED_SHIELD_2", max(-0.0005, round(peak_pnl_pct - shield_pull, 4)))
        if peak_pnl_pct >= 0.0058:
            mid_pull = max(0.0018, round(shield_pull * 1.15, 4))
            upper_anchor = max(0.0040, round(shield_act - shield_pull, 4))
            cont_floor = min(upper_anchor, max(0.0040, round(peak_pnl_pct - mid_pull, 4)))
            return ("CONTINUOUS_CURVE_1B", cont_floor)
        if peak_pnl_pct >= breakeven_trigger:
            return ("PRE_SHIELD_1A", breakeven_floor)
        return ("NONE", None)

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
        daily_vault_active: Optional[bool] = None,
    ) -> Optional[str]:
        prof = ASSET_PROFILES.get(ticker, ASSET_PROFILES["SAPd_EQ"])
        atr_raw = float(ticker_metrics.get("atr_5m_volatility_pct", 0.18)) / 100.0
        shield_act = max(0.0048, float(ticker_metrics.get("elastic_shield_act_raw", prof["shield_activation_pct"])))
        shield_pull = max(0.0012, float(ticker_metrics.get("elastic_shield_pull_raw", prof["shield_pullback_pct"])))

        if daily_vault_active is None:
            daily_vault_active = (realized_net_eur >= DAILY_VAULT_TRIGGER_EUR)

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
            if new_peak >= 0.0052 and (new_peak - pnl_pct) >= 0.0014 and pnl_pct >= 0.0030:
                return (
                    f"BLINDATURA #3 - RACCOLTO GAP MATTUTINO (09:00-09:30): blindato salto notturno "
                    f"dal picco +{new_peak*100:.2f}% a +{pnl_pct*100:.2f}% prima del Gap-Fill!"
                )

        stage_code, stage_floor = self.compute_profit_protection_floor(
            new_peak,
            shield_act,
            shield_pull,
            atr_raw,
            daily_vault_active=daily_vault_active,
        )

        # BLINDATURA #1 (Stadio 2) + BLINDATURA #8 (ATR Elastico V11.2, Gapless Floor >= -0,05%): Scudo Mobile Senza Tetto
        if stage_code == "UNCAPPED_SHIELD_2" and stage_floor is not None and -0.0005 <= pnl_pct <= stage_floor:
            return (
                f"SCUDO MOBILE ELASTICO SENZA TETTO ({prof['squad']}): cavalcato rialzo fino al picco "
                f"di +{new_peak*100:.2f}% e incassato su inversione a {pnl_pct*100:+.2f}%"
            )

        # BLINDATURA #1 (Stadio 1B - Curva Continua Monotona Salva-Utile V11.2, zero scalini ciechi):
        if stage_code == "CONTINUOUS_CURVE_1B" and stage_floor is not None and -0.0005 <= pnl_pct <= stage_floor:
            strong_above_vwap_hold = (
                vwap_dist >= 0.10
                and cur_rsi_5m >= 44.0
                and green_hook_ok
                and pnl_pct >= max(0.0032, round(stage_floor - 0.0008, 4))
            )
            if not strong_above_vwap_hold:
                return (
                    f"BLINDATURA #1B - CURVA CONTINUA SALVA-UTILE: {ticker} aveva toccato "
                    f"il picco di +{new_peak*100:.2f}% e ha blindato il pavimento dinamico ({stage_floor*100:+.2f}%) a {pnl_pct*100:+.2f}%!"
                )

        # BLINDATURA #1 (Stadio 1A - Pre-Scudo Salva-Utile Senza Buchi V11.2):
        if stage_code == "PRE_SHIELD_1A" and stage_floor is not None and -0.0005 <= pnl_pct <= stage_floor:
            trend_still_healthy_above_vwap = (
                vwap_dist >= -0.03 and cur_rsi_5m >= 46.0 and green_hook_ok
            )
            if not trend_still_healthy_above_vwap:
                return (
                    f"BLINDATURA #1A - PRE-SCUDO SALVA-UTILE SU PERDITA VWAP: {ticker} aveva toccato "
                    f"il picco di +{new_peak*100:.2f}% e ha perso spinta/VWAP a {pnl_pct*100:+.2f}%!"
                )

        # BLINDATURE #4, #5 e #14 (VIX Livello Assoluto + % con orologio America/New_York DST-safe):
        nasdaq_chg = float(overnight_radar.get("nasdaq_change_pct", 0.0))
        sp500_chg = float(overnight_radar.get("sp500_change_pct", 0.0))
        dax_chg = float(overnight_radar.get("dax_change_pct", 0.0))
        vix_chg = float(overnight_radar.get("vix_fear_change_pct", 0.0))
        vix_lvl = float(overnight_radar.get("vix_level", 16.0))
        vix_fear_5 = (vix_chg >= 5.0 and (vix_lvl >= 18.5 or vix_chg >= 9.0)) or vix_lvl >= 26.0
        vix_crash_12 = (vix_chg >= 12.0 and vix_lvl >= 18.0) or vix_chg >= 16.0 or vix_lvl >= 30.0
        now_ny_dt = datetime.datetime.now(US_EASTERN_TZ)
        us_market_live = bool(
            regime.get("us_market_live", (now_ny_dt.hour * 60 + now_ny_dt.minute) >= 9 * 60 + 30)
        )
        if us_market_live:
            macro_crash_shield_active = (
                nasdaq_chg <= -1.20
                or sp500_chg <= -1.00
                or (dax_chg <= -1.00 and vix_fear_5 and nasdaq_chg < 0.0)
                or vix_crash_12
            )
        else:
            macro_crash_shield_active = ((dax_chg <= -1.00 and vix_fear_5) or vix_crash_12)

        # BLINDATURA #14 (Stadio Uscita): Incasso Protettivo Immediato SOLO IN UTILE sotto vero Scudo Anti-Crollo Intraday
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
                    and (vix_chg <= 0.0 or (vix_lvl < 16.5 and vix_chg <= 3.0))
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

        # BLINDATURA #9 (V11.1 Switch Stagnazione Ricalibrato sulla Scala Lineare >= 80,0 pt):
        opened_at = self.position_open_time.setdefault(ticker, time.time())
        minutes_open = (time.time() - opened_at) / 60.0
        own_score = float(ticker_metrics.get("quant_buy_score", 50.0))
        if (
            regime.get("allow_new_buys", True)
            and not regime.get("is_lunch_desert_window", False)
            and minutes_open >= 45.0
            and 0.0008 <= pnl_pct <= 0.0024
            and new_peak < 0.0038
            and vwap_dist < -0.05
            and own_score < 28.0
            and not stock_is_strong
            and not green_hook_ok
            and has_green_hook_bench
            and best_bench_score >= LINEAR_ELITE_SCORE
        ):
            return (
                f"BLINDATURA #9 - SWITCH STAGNAZIONE IN VERDE (+{pnl_pct*100:.2f}%, 45m+ piatta sotto VWAP -> Leader {best_bench_score:.0f}/100): "
                f"sblocco cartuccia ferma solo in positivo per salire sul razzo in Super-Trend!"
            )

        # BLINDATURA #15 (V11.2 Airbag Simmetrico Elastico su ATR + Taglio Catastrofico < 8m contro Flash-Crash):
        breakdown_stop_pct = -min(0.0068, max(0.0054, round(atr_raw * 2.30, 4)))
        airbag_no_hook_pct = -min(0.0070, max(0.0064, round(atr_raw * 2.45, 4)))
        if minutes_open < 8.0 and pnl_pct <= -0.0135:
            return (
                f"BLINDATURA #15 - AIRBAG CATASTROFICO ISTANTANEO (<8m, {pnl_pct*100:+.2f}% <= -1,35%): "
                f"taglio d'emergenza immediato contro flash-crash / profit-warning!"
            )
        if minutes_open >= 12.0:
            if pnl_pct <= breakdown_stop_pct and (vwap_dist < -0.10 or cur_rsi_5m < 45.0) and not green_hook_ok and not stock_is_strong:
                return (
                    f"BLINDATURA #15 - TAGLIO CHIRURGICO TESI INVALIDATA ({pnl_pct*100:+.2f}% <= {breakdown_stop_pct*100:+.2f}%): "
                    f"rottura pavimento VWAP / perdita spinta -> taglio minimo (~0,14-0,17 EUR) e ruoto su Fascia d'Oro!"
                )
        if minutes_open >= 8.0 and ((pnl_pct <= airbag_no_hook_pct and not green_hook_ok) or pnl_pct <= -0.0072):
            return (
                f"BLINDATURA #15 - AIRBAG ECONOMICO INVALICABILE ({pnl_pct*100:+.2f}%): "
                f"taglio netto entro ~0,16-0,18 EUR per blindare il capitale!"
            )

        return None

    def is_eligible_entry_candidate(
        self,
        cand: Dict[str, Any],
        regime: Dict[str, Any],
        overnight_status: Dict[str, Any],
        daily_vault_active: bool = False,
        lunch_profit_lock_active: bool = False,
    ) -> bool:
        """Predicato unico di idoneità all'ingresso condiviso 1:1 tra Panchina (Stagnation Switch) e Ciclo BUY."""
        if not regime.get("allow_new_buys", True) or lunch_profit_lock_active:
            return False
        tkr = str(cand.get("ticker", ""))
        live_px = float(cand.get("live_price_eur", 0.0))
        cand_vwap_dist = float(cand.get("vwap_dist_pct", 0.0))
        if not tkr or live_px <= 0.0 or not self.can_buy_ticker(tkr, live_px, cand_vwap_dist):
            return False
        if not bool(cand.get("has_fresh_intraday_feed", False)):
            return False
        cand_rvol = float(cand.get("rvol_ratio", 0.0))
        min_rvol = 0.85 if daily_vault_active else PRUDENT_MIN_RVOL
        if cand_rvol < min_rvol:
            return False

        score = float(cand.get("quant_buy_score", 0.0))
        rsi_5m = float(cand.get("rsi_5m", 100.0))
        min_required_score = 62.0 if daily_vault_active else BASE_MIN_BUY_SCORE
        entry_hook_ok = bool(cand.get("entry_hook_confirmed", cand.get("green_hook_confirmed", False)))
        if (
            rsi_5m > 66.0
            or score < min_required_score
            or not bool(cand.get("green_hook_confirmed", False))
            or not entry_hook_ok
        ):
            return False

        cand_atr_pct = float(cand.get("atr_5m_volatility_pct", 0.0))
        cand_day_range = float(cand.get("day_range_pct", 0.0))
        max_vwap_entry = 0.50 if cand_atr_pct >= 0.23 else 0.65
        if cand_vwap_dist > max_vwap_entry or cand_vwap_dist < -0.35:
            return False
        if cand_atr_pct < 0.13 and cand_day_range < 1.40:
            return False

        # V11.2 Invariante #23 (Cecchino Esplosioni Straordinarie 11:15 CET - 08:27 ET, Max 2/4 Slot):
        # richiede obbligatoriamente feed real-time 0s (GETTEX/T212, mai Yahoo 15m) + uno dei 2 setup straordinari validati (+3,11 EUR / 5gg):
        # 1) Breakout 5m puro: Score >= 82, RVOL >= 2.20x, breakout_5m, Kaufman ER >= 0.45, VWAP in [0.00%, +0.45%]
        # 2) Rimbalzo da Valle con volumi forti: Score >= 88, RVOL >= 2.20x, RSI <= 38.0
        if regime.get("is_midday_sniper_window", False):
            feed_src = str(cand.get("price_feed_source", ""))
            if feed_src not in ("GETTEX_STREAMING_0S", "T212_LIVE_0MS"):
                return False
            cand_er = float(cand.get("kaufman_efficiency_ratio", 0.0))
            is_midday_breakout = (
                score >= 82.0
                and cand_rvol >= 2.20
                and bool(cand.get("breakout_5m", False))
                and cand_er >= 0.45
                and 0.0 <= cand_vwap_dist <= 0.45
            )
            is_midday_valley = (
                score >= 88.0
                and cand_rvol >= 2.20
                and rsi_5m <= 38.0
            )
            if not (is_midday_breakout or is_midday_valley):
                return False

        nasdaq_c = float(overnight_status.get("nasdaq_change_pct", 0.0))
        sp500_c = float(overnight_status.get("sp500_change_pct", 0.0))
        dax_c = float(overnight_status.get("dax_change_pct", 0.0))
        vix_c = float(overnight_status.get("vix_fear_change_pct", 0.0))
        vix_lvl_c = float(overnight_status.get("vix_level", 16.0))

        vix_fear_5_c = (vix_c >= 5.0 and (vix_lvl_c >= 18.5 or vix_c >= 9.0)) or vix_lvl_c >= 26.0
        vix_crash_12_c = (vix_c >= 12.0 and vix_lvl_c >= 18.0) or vix_c >= 16.0 or vix_lvl_c >= 30.0
        now_ny_dt = datetime.datetime.now(US_EASTERN_TZ)
        us_live = bool(regime.get("us_market_live", (now_ny_dt.hour * 60 + now_ny_dt.minute) >= 9 * 60 + 30))
        if us_live:
            intraday_crash_shield = (
                nasdaq_c <= -1.20
                or sp500_c <= -1.00
                or (dax_c <= -1.00 and vix_fear_5_c and nasdaq_c < 0.0)
                or vix_crash_12_c
            )
        else:
            intraday_crash_shield = ((dax_c <= -1.00 and vix_fear_5_c) or vix_crash_12_c)
        if intraday_crash_shield and not bool(cand.get("strong_for_overnight", False)):
            return False

        return True

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
        # V11.0 Zero Cerotti: 60 minuti di cooldown dopo uno Stop-Loss, 15 minuti (o ritracciamento -0,25%) dopo un incasso verde
        if self.last_sell_was_loss.get(ticker, False):
            return elapsed_min >= 60.0
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


LIMIT_FILL_POLL_SEC = 0.85


def _sync_certified_cash_safe(bot: Trading212AutonomousBot, min_interval_sec: float = 5.5) -> None:
    if bot.client is None:
        return
    now_ts = time.time()
    last_ts = float(getattr(bot, "_last_cash_sync_ts", 0.0))
    if (now_ts - last_ts) < min_interval_sec:
        return
    try:
        cash_info = bot.client.get_account_cash()
        setattr(bot, "_last_cash_sync_ts", time.time())
        setattr(bot, "_cash_synced_once", True)
        if isinstance(cash_info, dict):
            if cash_info.get("free") is not None:
                setattr(bot, "_t212_free_cash", float(cash_info["free"]))
            if cash_info.get("result") is not None:
                bot.tax_tracker.reconcile_certified_cash_result(float(cash_info["result"]))
    except Exception:
        pass


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
    intel.sync_from_tax_data(bot.tax_tracker.data)

    now_rome = datetime.datetime.now(MARKET_TZ)
    now = now_rome.replace(tzinfo=None)
    regime = intel.get_intraday_regime(now_rome)

    # 1. Leggi posizioni aperte e ordini pendenti da Trading 212 (con pulizia ordini LIMIT orfani)
    positions = client.get_open_positions()
    if len(positions) < bot.cartridges or getattr(bot, "_had_pending_orders", False):
        time.sleep(0.10)
        raw_pending = client.get_pending_orders()
        pending_orders = []
        for o in raw_pending:
            o_id = o.get("id")
            o_qty = float(o.get("quantity") or 0.0)
            o_type = str(o.get("type", "LIMIT")).upper()
            if regime["market_open"] and o_id is not None and o_qty > 0 and o_type == "LIMIT":
                try:
                    client.cancel_order(o_id)
                    continue
                except Exception:
                    pass
            pending_orders.append(o)
        setattr(bot, "_had_pending_orders", bool(pending_orders))
    else:
        pending_orders = []

    pos_by_ticker: Dict[str, Dict[str, Any]] = {p.get("ticker", ""): p for p in positions if p.get("ticker")}
    pending_by_ticker: Dict[str, Dict[str, Any]] = {
        o.get("ticker", ""): o
        for o in pending_orders
        if o.get("ticker") and float(o.get("quantity") or 0.0) > 0
    }

    # V11.2 Persistenza Candele Real-Time 0ms per l'intera seduta (pota solo i bucket dei giorni precedenti!)
    scanner.has_t212_realtime.clear()
    today_d = now_rome.date()
    for tkr_all, bmap in list(scanner.realtime_5m_bars.items()):
        for b_ts in list(bmap.keys()):
            if datetime.datetime.fromtimestamp(b_ts, tz=MARKET_TZ).date() != today_d:
                bmap.pop(b_ts, None)

    # V11.2 Anti-Split-Brain: se una posizione aperta nel ciclo precedente è stata chiusa da un altro runner/app, attiva subito il cooldown!
    for tkr_prev, (prev_avg, prev_cur) in list(intel.prev_open_snapshot.items()):
        if tkr_prev not in pos_by_ticker and tkr_prev not in pending_by_ticker:
            if (time.time() - intel.last_sell_time.get(tkr_prev, 0.0)) >= 300.0 and prev_avg > 0 and prev_cur > 0:
                intel.register_sell(tkr_prev, prev_cur, was_loss=(prev_cur < prev_avg))

    for tkr_old in list(intel.peak_pnl_pct.keys()):
        if tkr_old not in pos_by_ticker:
            intel.peak_pnl_pct.pop(tkr_old, None)
            intel.position_open_time.pop(tkr_old, None)
    scanner.has_t212_realtime.clear()
    for tkr, p in pos_by_ticker.items():
        cur_px = float(p.get("currentPrice", 0.0))
        scanner.update_t212_live_price(tkr, cur_px)

    # 2. Scansione quantitativa Split-Speed + GETTEX 0s (6s sulle cartucce aperte / 24s sui 39 Colossi o subito se slot libero)
    overnight_status = radar.evaluate_overnight_wave()
    dax_live_pct = float(overnight_status.get("dax_change_pct", 0.0))
    need_full_scan = len(pos_by_ticker) < bot.cartridges
    quant_metrics = scanner.scan_all(
        tax_data=bot.tax_tracker.data,
        dax_change_pct=dax_live_pct,
        force=need_full_scan,
        active_tickers=list(pos_by_ticker.keys()),
    )

    # Sincronizzazione primo avvio / heartbeat con cassa reale Trading 212 (simmetrica su plus/minusvalenze)
    first_cash_sync = not getattr(bot, "_cash_synced_once", False)
    if first_cash_sync or (cycle_num % 5 == 0):
        _sync_certified_cash_safe(bot, min_interval_sec=0.0 if first_cash_sync else 5.5)

    # V11.2 Sanificazione Automatica Lotti LIFO Orfani/Vuoti & Epoca Pulita:
    epoch_str = str(bot.tax_tracker.data.get("v11_clean_epoch_ts", V11_CLEAN_EPOCH_TS))
    lifo_dirty = False
    if bot.tax_tracker.data.get("v11_clean_epoch_ts") != epoch_str:
        bot.tax_tracker.data["v11_clean_epoch_ts"] = epoch_str
        lifo_dirty = True
    lifo_map = bot.tax_tracker.data.setdefault("lotti_aperti_lifo", {})
    for l_tkr in list(lifo_map.keys()):
        if not lifo_map.get(l_tkr) or (l_tkr not in pos_by_ticker and l_tkr not in pending_by_ticker):
            lifo_map.pop(l_tkr, None)
            lifo_dirty = True
    if lifo_dirty:
        bot.tax_tracker.save()

    # BLINDATURA #6: Interesse Composto Automatico di Kelly (Auto-Compounding sul totale storico)
    realized_net_eur = round(
        float(bot.tax_tracker.data.get("plusvalenze_lorde_eur", 0.0))
        - float(bot.tax_tracker.data.get("minusvalenze_lorde_eur", 0.0)),
        2,
    )
    # V11.2 Blocco Permanente Anti-Churn al raggiungimento del Target +30% (130,00 EUR)
    target_30pct_locked = bool(bot.tax_tracker.data.get("target_30pct_raggiunto_blocco_attivo", False)) or (
        realized_net_eur >= round(bot.target_equity_eur - bot.total_budget_eur, 2)
    )
    if target_30pct_locked:
        regime = dict(regime)
        regime["allow_new_buys"] = False
        regime["code"] = "TARGET_30PCT_RAGGIUNTO_CONTO_IN_CASSAFORTE"

    # BLINDATURA #10 (V11.2 Trailing Daily High-Water-Mark Vault: zero tetto ai trend rialzisti, scatta solo su ritracciamento >= 0,30 EUR dal picco >= +1,60 EUR!)
    today_prefix = now_rome.date().isoformat()
    today_ops_all = sorted(
        (
            op for op in bot.tax_tracker.data.get("operazioni_chiuse", [])
            if str(op.get("timestamp", "")).startswith(today_prefix)
        ),
        key=lambda x: str(x.get("timestamp", "")),
    )
    today_realized_net_eur = round(
        sum(float(op.get("risultato_fiscale_eur", 0.0)) for op in today_ops_all),
        2,
    )
    running_today_pnl = 0.0
    today_peak_realized_eur = 0.0
    for op in today_ops_all:
        running_today_pnl = round(running_today_pnl + float(op.get("risultato_fiscale_eur", 0.0)), 4)
        if running_today_pnl > today_peak_realized_eur:
            today_peak_realized_eur = running_today_pnl
    today_peak_realized_eur = round(today_peak_realized_eur, 2)
    today_giveback_eur = round(max(0.0, today_peak_realized_eur - today_realized_net_eur), 2)
    daily_vault_active = (
        today_peak_realized_eur >= DAILY_VAULT_TRIGGER_EUR
        and today_giveback_eur >= DAILY_VAULT_GIVEBACK_EUR
    )

    compounded_budget_eur = round(bot.total_budget_eur + max(0.0, realized_net_eur), 2)
    dynamic_cartridge_eur = round(compounded_budget_eur / bot.cartridges, 2)

    # V11.2 Predicato Unificato Panchina == Ciclo BUY (Zero rotazioni orfane!)
    bench_candidates = [
        m
        for tkr, m in quant_metrics.items()
        if tkr not in pos_by_ticker
        and tkr not in pending_by_ticker
        and intel.is_eligible_entry_candidate(
            m,
            regime,
            overnight_status,
            daily_vault_active=daily_vault_active,
        )
    ]

    invested_100e = 0.0
    unrealized_pnl_100e = 0.0
    cartridge_statuses: List[Dict[str, Any]] = []
    actions_taken: List[str] = []
    real_orders_executed = False

    # 3. Valuta posizioni aperte con logica V11.2 Istituzionale Zero Cerotti
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

        # Auto-Sync LIFO lot 1:1 con posizione reale Trading 212 (elimina automaticamente lotti duplicati o disallineati)
        if qty_open > 0 and avg_price > 0:
            open_lots = bot.tax_tracker.data.get("lotti_aperti_lifo", {}).get(tkr, [])
            tot_lifo_qty = sum(float(l.get("quantity", 0.0)) for l in open_lots)
            if not open_lots:
                bot.tax_tracker.record_buy(tkr, qty_open, avg_price)
                intel.peak_pnl_pct[tkr] = max(0.0, pnl_pct)
                intel.position_open_time[tkr] = time.time()
            elif (
                len(open_lots) != 1
                or abs(tot_lifo_qty - qty_open) > 1e-4
                or abs(float(open_lots[-1].get("price_eur", avg_price)) - avg_price) / avg_price > 0.0025
            ):
                preserved_ts = open_lots[-1].get("timestamp") or now_rome.isoformat(timespec="seconds")
                bot.tax_tracker.data["lotti_aperti_lifo"][tkr] = [{
                    "timestamp": preserved_ts,
                    "ticker": tkr,
                    "isin": meta.get("isin", ""),
                    "quantity": round(qty_open, 6),
                    "price_eur": round(avg_price, 4),
                    "total_eur": round(qty_open * avg_price, 4),
                }]
                bot.tax_tracker.save()
                intel.peak_pnl_pct[tkr] = max(intel.peak_pnl_pct.get(tkr, 0.0), pnl_pct)
                intel.position_open_time.setdefault(tkr, time.time())

        # Ribilanciamento automatico SOLO IN UTILE se una cartuccia supera 1.24x la taglia composta (preserva lotto LIFO residuo)
        max_allowed_cartridge = max(31.00, round(dynamic_cartridge_eur * 1.24, 2))
        if cost_eur > max_allowed_cartridge and regime["market_open"] and cur_price > avg_price and pnl_pct >= 0.0010:
            target_qty = round(dynamic_cartridge_eur / cur_price, 4)
            excess_qty = round(qty_open - target_qty, 4)
            if excess_qty > 0 and (excess_qty * cur_price) >= 2.00:
                client.place_market_order(ticker=tkr, quantity=-excess_qty)
                closed_op = bot.tax_tracker.record_sell(
                    ticker=tkr,
                    sell_qty=excess_qty,
                    sell_price_eur=cur_price,
                    fallback_avg_price_eur=avg_price,
                )
                real_orders_executed = True
                qty_open = round(qty_open - excess_qty, 4)
                cost_eur = round(qty_open * avg_price, 2)
                ppl = round((cur_price - avg_price) * qty_open, 2)
                actions_taken.append(
                    f"RIBILANCIAMENTO CARTUCCIA COMPOSTA ({dynamic_cartridge_eur:.2f} EUR) su {tkr}: vendute {excess_qty} azioni in eccesso "
                    f"a {cur_price:.4f} EUR (Utile fiscale: {closed_op['risultato_fiscale_eur']:+.2f} EUR)"
                )
                time.sleep(0.25)

        # A) Valuta Scudo Mobile Elastico Senza Tetto + Selettore Onda Notturna + Rotazione Solo in Utile
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
            daily_vault_active=daily_vault_active,
        )
        if exit_reason and regime["market_open"]:
            client.place_market_order(ticker=tkr, quantity=-qty_open)
            closed_op = bot.tax_tracker.record_sell(
                ticker=tkr,
                sell_qty=qty_open,
                sell_price_eur=cur_price,
                fallback_avg_price_eur=avg_price,
            )
            real_orders_executed = True
            intel.register_sell(
                tkr,
                cur_price,
                was_loss=(float(closed_op.get("risultato_fiscale_eur", 0.0)) < 0.0),
            )
            msg = (
                f"{exit_reason} su {tkr} ({meta['name']}): vendute {qty_open} azioni "
                f"a {cur_price:.4f} EUR (Risultato fiscale: {closed_op['risultato_fiscale_eur']:+.2f} EUR, 0,00 EUR comm.)"
            )
            actions_taken.append(msg)
            pos_by_ticker.pop(tkr, None)
            time.sleep(0.25)
            continue

        peak_now = intel.peak_pnl_pct.get(tkr, pnl_pct)
        atr_pos_raw = float(tkr_m.get("atr_5m_volatility_pct", 0.18)) / 100.0
        shield_act = max(0.0048, float(tkr_m.get("elastic_shield_act_raw", prof["shield_activation_pct"])))
        shield_pull = max(0.0012, float(tkr_m.get("elastic_shield_pull_raw", prof["shield_pullback_pct"])))
        stage_code, stage_floor = intel.compute_profit_protection_floor(
            peak_now,
            shield_act,
            shield_pull,
            atr_pos_raw,
            daily_vault_active=daily_vault_active,
        )
        shield_is_armed = (stage_code == "UNCAPPED_SHIELD_2")
        pre_shield_breakeven_armed = (stage_code != "NONE")
        current_floor_pct = round(stage_floor * 100, 2) if stage_floor is not None else None

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
            "avg_price_eur": round(avg_price, 4),
            "current_price_eur": round(cur_price, 4),
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

    # 4. Conta eventuali ordini di acquisto pendenti residui
    for tkr, o in pending_by_ticker.items():
        if tkr in EUR_ZERO_FEE_UNIVERSE and tkr not in pos_by_ticker and float(o.get("quantity") or 0.0) > 0:
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

    # 5. INGRESSO LINEARE CON MARKETABLE LIMIT ORDER (+1,00% ANTI-SPIKE MiFID II), ZERO MARKET ORDER AL BUIO
    active_count = len(cartridge_statuses)
    pre_entry_equity = round(bot.total_budget_eur + realized_net_eur + unrealized_pnl_100e, 2)
    if pre_entry_equity >= bot.target_equity_eur:
        regime = dict(regime)
        regime["allow_new_buys"] = False
        regime["code"] = "TARGET_30PCT_RAGGIUNTO_CONTO_IN_CASSAFORTE"

    effective_slot_cap = min(
        bot.cartridges,
        int(regime.get("max_active_slots", bot.cartridges)),
    )
    max_investable_before_4th = round(compounded_budget_eur - 18.00, 2)
    # V11.2 Invariante #24 (Zero Rotazioni su Cache Stantia): se a inizio ciclo le cartucce erano piene
    # (need_full_scan == False) e una vendita a metà ciclo ha liberato uno slot, forza una scansione
    # fresca a 0s su tutta la panchina prima di ordinare i candidati d'acquisto!
    if (
        regime["allow_new_buys"]
        and active_count < effective_slot_cap
        and invested_100e <= max_investable_before_4th
        and not need_full_scan
    ):
        quant_metrics = scanner.scan_all(
            tax_data=bot.tax_tracker.data,
            dax_change_pct=dax_live_pct,
            force=True,
            active_tickers=list(pos_by_ticker.keys()),
        )

    ranked_candidates = sorted(
        quant_metrics.values(),
        key=lambda m: (
            float(m["quant_buy_score"]),
            round(float(m.get("atr_5m_volatility_pct", 0.0)), 3),
            float(m.get("rvol_ratio", 0.0)),
        ),
        reverse=True,
    )

    if regime["allow_new_buys"] and active_count < effective_slot_cap and invested_100e <= max_investable_before_4th:
        active_sectors = {
            c.get("settore_markowitz")
            for c in cartridge_statuses
            if c.get("settore_markowitz")
        }
        live_broker_tickers = set(pos_by_ticker.keys())
        try:
            fresh_pos_once = [
                p for p in client.get_open_positions()
                if float(p.get("quantity", 0.0)) > 0
            ]
            live_broker_tickers = {str(p.get("ticker", "")) for p in fresh_pos_once if p.get("ticker")}
            active_count = max(active_count, len(fresh_pos_once))
        except Exception:
            pass

        for cand in ranked_candidates:
            if active_count >= effective_slot_cap or invested_100e > max_investable_before_4th:
                break
            tkr = cand["ticker"]
            if tkr in pos_by_ticker or tkr in pending_by_ticker or tkr in live_broker_tickers:
                continue
            cand_squad = cand["squad"]
            cand_sector = cand["sector"]
            if cand_sector in active_sectors:
                continue
            if not intel.is_eligible_entry_candidate(
                cand,
                regime,
                overnight_status,
                daily_vault_active=daily_vault_active,
            ):
                continue

            live_px = float(cand["live_price_eur"])
            score = float(cand["quant_buy_score"])
            rsi_5m = float(cand["rsi_5m"])
            if live_px <= 0:
                continue

            limit_px = Trading212Client.snap_mifid_tick_price(
                live_px * (1.0 + LIMIT_ORDER_CAP_PCT),
                side="BUY",
            )
            remaining_budget = round(compounded_budget_eur - invested_100e, 2)
            alloc_eur = min(dynamic_cartridge_eur, remaining_budget)
            broker_free = getattr(bot, "_t212_free_cash", None)
            if broker_free is not None:
                alloc_eur = min(alloc_eur, round(max(0.0, float(broker_free)) * 0.998, 2))
            if alloc_eur < 18.00:
                break

            effective_alloc = (
                round(alloc_eur * 0.996, 2)
                if remaining_budget <= (dynamic_cartridge_eur + 0.50)
                else alloc_eur
            )
            # Taglia dimensionata su limit_px per non eccedere MAI il margine riservato da Trading 212 sulla 4ª cartuccia
            qty_to_buy = round(effective_alloc / limit_px, 4) if limit_px > 0 else 0.0
            if qty_to_buy <= 0:
                continue

            try:
                meta = EUR_ZERO_FEE_UNIVERSE[tkr]
                try:
                    order_res = client.place_limit_order(
                        ticker=tkr,
                        quantity=qty_to_buy,
                        limit_price=limit_px,
                        time_validity="DAY",
                    )
                except Exception as ord_err:
                    fallback_qty = round(effective_alloc / limit_px, 2)
                    if fallback_qty > 0 and fallback_qty != qty_to_buy and (fallback_qty * live_px) >= 18.00 and "400" in str(ord_err):
                        qty_to_buy = fallback_qty
                        order_res = client.place_limit_order(
                            ticker=tkr,
                            quantity=qty_to_buy,
                            limit_price=limit_px,
                            time_validity="DAY",
                        )
                    else:
                        raise

                ord_id = order_res.get("id") if isinstance(order_res, dict) else None
                if LIMIT_FILL_POLL_SEC > 0:
                    time.sleep(LIMIT_FILL_POLL_SEC)

                still_pending = False
                if ord_id is not None:
                    try:
                        cur_pend = client.get_pending_orders()
                        if any(o.get("id") == ord_id for o in cur_pend):
                            try:
                                client.cancel_order(ord_id)
                                if LIMIT_FILL_POLL_SEC > 0:
                                    time.sleep(0.15)
                            except Exception:
                                still_pending = True
                    except Exception:
                        pass

                post_pos_list = client.get_open_positions()
                matched_pos = next(
                    (p for p in post_pos_list if p.get("ticker") == tkr and float(p.get("quantity", 0.0)) > 0),
                    None,
                )

                if matched_pos is not None:
                    filled_qty = round(float(matched_pos.get("quantity", qty_to_buy)), 4)
                    fill_px = float(matched_pos.get("averagePrice") or live_px)
                    est_cost = round(filled_qty * fill_px, 2)
                    bot.tax_tracker.record_buy(ticker=tkr, quantity=filled_qty, price_eur=fill_px)
                    real_orders_executed = True
                    if broker_free is not None:
                        setattr(bot, "_t212_free_cash", max(0.0, float(broker_free) - est_cost))
                    intel.position_open_time[tkr] = time.time()
                    pos_by_ticker[tkr] = {
                        "ticker": tkr,
                        "quantity": filled_qty,
                        "averagePrice": fill_px,
                        "currentPrice": float(matched_pos.get("currentPrice") or fill_px),
                    }
                    live_broker_tickers.add(tkr)
                    invested_100e += est_cost
                    active_count += 1
                    active_sectors.add(cand_sector)
                    msg = (
                        f"INGRESSO V11.2 LIMIT PROTETTO ({cand_squad} / {cand_sector}) -> BUY {filled_qty} {tkr} ({meta['name']}) "
                        f"a {fill_px:.4f} EUR (Tetto Limit MiFID: {limit_px:.4f} EUR, Tot: {est_cost:.2f} EUR) | "
                        f"Score: {score}/100 (ATR: {cand.get('atr_5m_volatility_pct', 0.0):.3f}%, RVOL: {cand.get('rvol_ratio', 0.0)}x, RSI: {rsi_5m}) | Order ID: {ord_id}"
                    )
                    actions_taken.append(msg)
                    cartridge_statuses.append({
                        "slot": slot_idx,
                        "ticker": tkr,
                        "name": meta["name"],
                        "squadra": cand_squad,
                        "settore_markowitz": cand_sector,
                        "status": "APPENA_ACQUISTATA_V11_2_LIMIT_PROTETTO",
                        "order_id": ord_id,
                        "quantity": filled_qty,
                        "avg_price_eur": round(fill_px, 4),
                        "current_price_eur": round(fill_px, 4),
                        "invested_eur": est_cost,
                    })
                    slot_idx += 1
                    if LIMIT_FILL_POLL_SEC > 0:
                        time.sleep(0.20)
                elif still_pending:
                    reserved_eur = round(qty_to_buy * limit_px, 2)
                    setattr(bot, "_had_pending_orders", True)
                    pending_by_ticker[tkr] = {"id": ord_id, "ticker": tkr, "quantity": qty_to_buy, "type": "LIMIT"}
                    live_broker_tickers.add(tkr)
                    invested_100e += reserved_eur
                    active_count += 1
                    active_sectors.add(cand_sector)
                    cartridge_statuses.append({
                        "slot": slot_idx,
                        "ticker": tkr,
                        "name": meta["name"],
                        "squadra": cand_squad,
                        "settore_markowitz": cand_sector,
                        "status": "ORDINE_IN_CODA",
                        "order_id": ord_id,
                        "quantity": qty_to_buy,
                        "invested_eur": reserved_eur,
                    })
                    slot_idx += 1
                else:
                    intel.last_sell_price[tkr] = live_px
                    intel.last_sell_was_loss[tkr] = False
                    intel.last_sell_time[tkr] = time.time() - 600.0
                    actions_taken.append(
                        f"SCUDO ANTI-SPIKE LIMIT (+1,00%): ordine {tkr} annullato perché ask reale > {limit_px:.4f} EUR (zero slippage subito)"
                    )
            except Exception as e:
                intel.last_sell_price[tkr] = live_px
                intel.last_sell_was_loss[tkr] = False
                intel.last_sell_time[tkr] = time.time() - 600.0
                actions_taken.append(f"Passaggio al candidato High-Beta successivo ({tkr}: {e})")

    # Se nel ciclo sono stati eseguiti ordini reali, riallinea la cassa certificata Trading 212 nel rispetto del rate-limit
    if real_orders_executed:
        _sync_certified_cash_safe(bot, min_interval_sec=2.2)

    realized_net_eur = round(
        float(bot.tax_tracker.data.get("plusvalenze_lorde_eur", 0.0))
        - float(bot.tax_tracker.data.get("minusvalenze_lorde_eur", 0.0)),
        2,
    )
    compounded_budget_eur = round(bot.total_budget_eur + max(0.0, realized_net_eur), 2)
    dynamic_cartridge_eur = round(compounded_budget_eur / bot.cartridges, 2)
    virtual_100e_equity = round(bot.total_budget_eur + realized_net_eur + unrealized_pnl_100e, 2)
    free_cash_100e = round(max(0.0, compounded_budget_eur - invested_100e), 2)

    # 6. Verifica Target Annuale +30% (130,00 EUR) — Liquidazione Atomica Unica a Mercato Aperto & Blocco Permanente Zero-Churn
    if virtual_100e_equity >= bot.target_equity_eur:
        already_locked = bool(bot.tax_tracker.data.get("target_30pct_raggiunto_blocco_attivo", False))
        if (pos_by_ticker or pending_by_ticker or not already_locked):
            liquidated_now = False
            if (pos_by_ticker or pending_by_ticker) and regime["market_open"]:
                bot.liquidate_all_for_withdrawal()
                pos_by_ticker.clear()
                pending_by_ticker.clear()
                cartridge_statuses.clear()
                invested_100e = 0.0
                unrealized_pnl_100e = 0.0
                liquidated_now = True
            bot.tax_tracker.load()
            bot.tax_tracker.data["target_30pct_raggiunto_blocco_attivo"] = True
            bot.tax_tracker.save()
            realized_net_eur = round(
                float(bot.tax_tracker.data.get("plusvalenze_lorde_eur", 0.0))
                - float(bot.tax_tracker.data.get("minusvalenze_lorde_eur", 0.0)),
                2,
            )
            compounded_budget_eur = round(bot.total_budget_eur + max(0.0, realized_net_eur), 2)
            virtual_100e_equity = round(bot.total_budget_eur + realized_net_eur + unrealized_pnl_100e, 2)
            free_cash_100e = round(max(0.0, compounded_budget_eur - invested_100e), 2)
            regime = dict(regime)
            regime["allow_new_buys"] = False
            regime["code"] = "TARGET_30PCT_RAGGIUNTO_CONTO_IN_CASSAFORTE"
            if liquidated_now or not already_locked:
                actions_taken.append(
                    f"TARGET +30% RAGGIUNTO E BLINDATO ({virtual_100e_equity:.2f} EUR >= {bot.target_equity_eur:.2f} EUR)! "
                    + (
                        "Liquidazione totale eseguita a 0,00 EUR commissioni e blocco permanente nuovi acquisti attivato."
                        if liquidated_now
                        else "Blocco permanente nuovi acquisti attivato (liquidazione programmata all'apertura Borsa 09:00)."
                    )
                )

    intel.prev_open_snapshot = {
        t: (float(p.get("averagePrice", 0.0)), float(p.get("currentPrice", float(p.get("averagePrice", 0.0)))))
        for t, p in pos_by_ticker.items()
        for _ in (0,)
        if t
    }
    scanner.save_disk_cache()

    state = {
        "timestamp": now.isoformat(timespec="seconds"),
        "cycle": cycle_num,
        "mode": "INSTITUTIONAL_V11_2_LTS_ZERO_CEROTTI",
        "blindature_attive_v6_istituzionali": [
            "1. Occhio Real-Time 0s GETTEX + Zero-Ghost Cache V11.2 (39/39 titoli in streaming 0s Monaco + Cache 5m persistita + Volumi XETRA)",
            "2. Blocco 2 Intraday Puro Gap-Clean (ATR & Kaufman ER depurati dal gap notturno 17:25->09:00 + Asta 17:25 esclusa da RVOL)",
            "3. Marketable Limit Orders MiFID II (+1,00% cap anti-spike calettato su tick RTS 11, zero Market Order al buio)",
            f"4. Allocazione 4 Decimali & Kelly su LimitPrice (Budget: {compounded_budget_eur:.2f} EUR -> 4 Cartucce da {dynamic_cartridge_eur:.2f} EUR)",
            f"5. Matrice Markowitz {len(ASSET_PROFILES)} Colossi EUR Zero-Fee (32 UE + 7 Big Tech USA in EUR, 0% FX/Tobin, 4 settori distinti)",
            "6. Curva Monotona Continua Salva-Utile (Funzione pura unica Motore == JSON, zero gradini ciechi fino allo Scudo Elastico)",
            "7. Airbag Simmetrico Elastico su ATR (~-0,54%..-0,72% oltre 8m + Taglio Catastrofico Istantaneo -1,35% sotto 8m)",
            "8. Orologio DST-Safe America/New_York (Stop Acquisti Pausa Pranzo 11:15-08:35 ET & Pre-Chiusura >=17:15 CET + Onda USA >=+0,25%)",
            f"9. Trailing Daily Vault (Picco oggi: {today_peak_realized_eur:+.2f} EUR, Attiva su ritracciamento >=0,30 EUR: {daily_vault_active}) + Riconciliazione 730 Simmetrica",
        ],
        "regime_mercato_attivo": regime,
        "radar_onda_notturna_wall_street": overnight_status,
        "account_id": 52318994,
        "budget_iniziale_vincolato_eur": 100.00,
        "budget_composto_attivo_kelly_eur": compounded_budget_eur,
        "taglia_cartuccia_composta_eur": dynamic_cartridge_eur,
        "cassaforte_giornaliera_attiva": daily_vault_active,
        "cassaforte_giornaliera_picco_eur": today_peak_realized_eur,
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
        "cooldown_state": {
            "last_sell_price": intel.last_sell_price,
            "last_sell_time": intel.last_sell_time,
            "last_sell_was_loss": intel.last_sell_was_loss,
        },
        "cartucce_4x25_eur": cartridge_statuses,
        "ultime_azioni_bot": actions_taken,
        "riepilogo_fiscale_730": bot.tax_tracker.generate_730_summary(virtual_100e_equity),
    }

    with open(BOT_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    return state


def main():
    parser = argparse.ArgumentParser(description="Trading 212 V11.2 LTS Zero Cerotti Daemon")
    parser.add_argument(
        "--cycles",
        type=int,
        default=0,
        help="Numero di cicli da eseguire (0 = loop infinito H24 locale, >0 = modalità Cloud GitHub Actions)",
    )
    args, _ = parser.parse_known_args()

    print(
        "=== AVVIO DEMONE V11.2 LTS ZERO CEROTTI (GETTEX 0s STREAMING + 39 COLOSSI UE/USA IN EUR + MIFID LIMIT +1%) ===",
        flush=True,
    )
    client = load_client()
    added_giants = discover_and_verify_eur_giants(client)
    print(
        f"[RADAR DINAMICO V11.2] Universo EUR Zero-Fee attivo: {len(ASSET_PROFILES)} Colossi (32 UE + 7 Big Tech USA in EUR, +{added_giants} verificati via ISIN, Feed GETTEX 0s)",
        flush=True,
    )
    bot = Trading212AutonomousBot(client=client, total_budget_eur=100.00, cartridges=4, annual_target_pct=0.30)
    intel = HybridUncappedIntelligence()
    scanner = QuantMarketScanner(cache_path=SCANNER_CACHE_PATH)
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
                f"Radar Notte: {ov['verdict']} (Nasdaq {ov['nasdaq_change_pct']:+.2f}%, VIX {ov.get('vix_level', 16.0):.1f} [{ov['vix_fear_change_pct']:+.2f}%])",
                flush=True,
            )
            for act in state["ultime_azioni_bot"]:
                print(f"   >>> [AZIONE V11.2]: {act}", flush=True)
        except Exception as e:
            print(f"[ATTENZIONE] Errore temporaneo nel ciclo #{cycle}: {e}", flush=True)

        cycle += 1
        executed += 1
        if args.cycles > 0 and executed >= args.cycles:
            print(f"=== SESSIONE CLOUD COMPLETATA ({executed}/{args.cycles} cicli eseguiti) ===", flush=True)
            break
        time.sleep(6.0 if args.cycles > 0 else 5.5)


if __name__ == "__main__":
    main()
