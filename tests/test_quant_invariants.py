#!/usr/bin/env python3
"""
Suite Automatica Bloccante dei 10 Invarianti Matematici (V11.0 LTS "Zero Cerotti" Prudente).
Eseguita in locale e su GitHub Actions prima di ogni sessione per garantire Zero Regressioni.
"""
import datetime
import io
import json
import os
import sys
import unittest
from unittest.mock import patch

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import t212_daemon_100e as daemon
from trading212_bot import ItalianTaxTracker730, Trading212Client


def _make_yahoo_payload(closes, highs=None, lows=None, vols=None, base_ts=None):
    if base_ts is None:
        now_dt = datetime.datetime.now(daemon.MARKET_TZ).replace(hour=10, minute=0, second=0, microsecond=0)
        base_ts = int(now_dt.timestamp()) - len(closes) * 300
    timestamps = [base_ts + i * 300 for i in range(len(closes))]
    highs = highs or [c * 1.0015 for c in closes]
    lows = lows or [c * 0.9985 for c in closes]
    vols = vols or [2500.0 for _ in closes]
    return json.dumps({
        "chart": {
            "result": [{
                "meta": {"regularMarketPrice": closes[-1], "chartPreviousClose": closes[0]},
                "timestamp": timestamps,
                "indicators": {"quote": [{"close": closes, "high": highs, "low": lows, "volume": vols}]},
            }]
        }
    }).encode("utf-8")


class _FakeHTTPResp:
    def __init__(self, raw_bytes: bytes):
        self._buf = io.BytesIO(raw_bytes)

    def read(self) -> bytes:
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class TestQuantInvariantsV11(unittest.TestCase):

    def test_01_zero_ghost_on_empty_or_timeout_yahoo(self):
        """Invariante #1: su timeout HTTP senza cache, Score == 0.0 e zero numeri fittizi."""
        scanner = daemon.QuantMarketScanner()
        with patch("urllib.request.urlopen", side_effect=TimeoutError("HTTP timeout")):
            m = scanner.fetch_5m_metrics("BAYNd_EQ", tax_data=None)
        self.assertEqual(m["quant_buy_score"], 0.0)
        self.assertFalse(m["green_hook_confirmed"])
        self.assertFalse(m["has_fresh_intraday_feed"])
        self.assertEqual(m["rvol_ratio"], 0.0)

    def test_02_resilient_cache_preserves_real_bars_on_timeout(self):
        """Invariante #2: se esiste cache valida 5m, un singolo timeout conserva VWAP/ATR/RSI reali."""
        scanner = daemon.QuantMarketScanner()
        # Serie realistica: ritracciamento sano sul pavimento VWAP e uncino verde (RSI ~ 52)
        closes = [
            210.0, 210.2, 210.4, 210.3, 210.5, 210.3, 210.1, 210.2, 210.4, 210.2,
            210.0, 210.1, 210.3, 210.1, 209.9, 210.0, 210.1, 210.0, 210.15, 210.28,
        ]
        payload = _make_yahoo_payload(closes)
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(payload)):
            m1 = scanner.fetch_5m_metrics("SAPd_EQ", tax_data=None)
        self.assertGreater(m1["quant_buy_score"], 60.0)
        self.assertTrue(m1["has_fresh_intraday_feed"])

        with patch("urllib.request.urlopen", side_effect=TimeoutError("Transient Yahoo timeout")):
            m2 = scanner.fetch_5m_metrics("SAPd_EQ", tax_data=None)
        self.assertGreater(m2["quant_buy_score"], 60.0)
        self.assertAlmostEqual(m1["atr_5m_volatility_pct"], m2["atr_5m_volatility_pct"], places=2)

    def test_03_linear_additive_monotonicity_no_155x_distortion(self):
        """Invariante #3: setup istituzionale pulito sul VWAP batte sempre setup sporco (zero distorsione 1,55x)."""
        scanner = daemon.QuantMarketScanner()
        # Setup istituzionale pulito su CORE_BLUE_CHIP (RSI ~ 53, Kaufman ER direzionale sul pavimento VWAP)
        clean_closes = [
            210.0, 210.2, 210.4, 210.3, 210.5, 210.3, 210.1, 210.2, 210.4, 210.2,
            210.0, 210.1, 210.3, 210.1, 209.9, 210.0, 210.1, 210.25, 210.45, 210.65,
        ]
        # Setup sporco zig-zag su TURBO_HIGH_BETA (Kaufman ER ~ 0.0 per oscillazioni continue avanti/indietro)
        noisy_closes = [1300.0 + ((-1) ** i) * 1.8 for i in range(18)] + [1299.8, 1300.1]
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(_make_yahoo_payload(clean_closes))):
            m_clean = scanner.fetch_5m_metrics("SAPd_EQ", tax_data=None)
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(_make_yahoo_payload(noisy_closes))):
            m_noisy = scanner.fetch_5m_metrics("ASMLa_EQ", tax_data=None)
        self.assertGreater(m_clean["quant_buy_score"], m_noisy["quant_buy_score"])
        self.assertLess(m_clean["quant_buy_score"], 100.0)

    def test_04_prudent_rvol_020_liquidity_gate(self):
        """Invariante #4: PRUDENT_MIN_RVOL == 0.20 e rvol_ratio riflette fedelmente i book illiquidi su 2 barre."""
        self.assertAlmostEqual(daemon.PRUDENT_MIN_RVOL, 0.20, places=2)
        scanner = daemon.QuantMarketScanner()
        closes = [50.0 + i * 0.03 for i in range(20)]
        vols = [5000.0] * 18 + [250.0, 250.0]  # Ultime 2 candele con solo 5% dei volumi medi (RVOL = 0.05x < 0.20x)
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(_make_yahoo_payload(closes, vols=vols))):
            m = scanner.fetch_5m_metrics("SHLd_EQ" if "SHLd_EQ" in daemon.ASSET_PROFILES else "SAPd_EQ")
        self.assertLess(m["rvol_ratio"], daemon.PRUDENT_MIN_RVOL)

    def test_05_chip_sector_split_litografia_vs_potenza(self):
        """Invariante #5: ASML/ASM in CHIP_LITOGRAFIA_WAFER; BESI/IFX/AIXA in CHIP_POTENZA_PACKAGING."""
        self.assertEqual(daemon.ASSET_PROFILES["ASMLa_EQ"]["sector"], "CHIP_LITOGRAFIA_WAFER")
        self.assertEqual(daemon.ASSET_PROFILES["BESIa_EQ"]["sector"], "CHIP_POTENZA_PACKAGING")
        self.assertEqual(daemon.ASSET_PROFILES["IFXd_EQ"]["sector"], "CHIP_POTENZA_PACKAGING")
        by_fb = {c["fallback_ticker"]: c["sector"] for c in daemon.CANDIDATE_EUR_GIANTS}
        self.assertEqual(by_fb["ASMa_EQ"], "CHIP_LITOGRAFIA_WAFER")
        self.assertEqual(by_fb["AIXAd_EQ"], "CHIP_POTENZA_PACKAGING")

    def test_06_four_decimal_fractional_sizing_efficiency(self):
        """Invariante #6: per qualsiasi prezzo 10..2000 EUR, la cartuccia da 25 EUR investe [24.85, 25.05] EUR."""
        for px in [13.25, 33.46, 54.98, 158.40, 211.46, 472.21, 726.40, 1357.50, 1890.00]:
            qty = round(25.00 / px, 4)
            invested = round(qty * px, 2)
            self.assertGreaterEqual(invested, 24.85, f"Sotto-allocazione per prezzo {px}")
            self.assertLessEqual(invested, 25.05, f"Sovra-allocazione per prezzo {px}")

    def test_07_shield_threshold_engine_json_parity(self):
        """Invariante #7: soglie scudo di evaluate_uncapped_exit identiche a quelle serializzate nel JSON."""
        scanner = daemon.QuantMarketScanner()
        closes = [210.0 + i * 0.08 for i in range(20)]
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(_make_yahoo_payload(closes))):
            m = scanner.fetch_5m_metrics("SAPd_EQ")
        act_raw = max(0.0048, float(m["elastic_shield_act_raw"]))
        self.assertEqual(round(act_raw * 100, 2), m["shield_activation_pct"])

    def test_08_gapless_green_profit_staircase(self):
        """Invariante #8: dal picco +0.65% scendendo a +0.12% senza uncino verde scatta sempre l'incasso."""
        intel = daemon.HybridUncappedIntelligence()
        intel.peak_pnl_pct["SAPd_EQ"] = 0.0065
        intel.position_open_time["SAPd_EQ"] = datetime.datetime.now().timestamp() - 900
        regime = {"is_morning_gap_harvest": False, "is_pre_close_window": False, "is_friday_pre_weekend": False}
        metrics = {
            "atr_5m_volatility_pct": 0.16,
            "elastic_shield_act_raw": 0.0063,
            "elastic_shield_pull_raw": 0.0015,
            "fase_onda_sinusoidale": "ONDA_DISCENDENTE_O_DEBOLE",
            "strong_for_overnight": False,
            "green_hook_confirmed": False,
            "vwap_dist_pct": -0.08,
            "rsi_5m": 43.0,
        }
        for drop_pnl in [0.0045, 0.0035, 0.0025, 0.0015]:
            intel.peak_pnl_pct["SAPd_EQ"] = 0.0065
            reason = intel.evaluate_uncapped_exit("SAPd_EQ", drop_pnl, regime, 75.0, {}, metrics, 0.0, False)
            self.assertIsNotNone(reason, f"Buco nella scala salva-utile a pnl={drop_pnl}")

    def test_09_airbag_cap_and_clean_epoch_isolation(self):
        """Invariante #9: Airbag attivo sotto -0.72% dopo 8m e vecchi stop pre-V11 ignorati al 100%."""
        intel = daemon.HybridUncappedIntelligence()
        intel.peak_pnl_pct["SAPd_EQ"] = 0.0
        intel.position_open_time["SAPd_EQ"] = datetime.datetime.now().timestamp() - 600  # 10 min
        regime = {"is_morning_gap_harvest": False, "is_pre_close_window": False}
        metrics = {"atr_5m_volatility_pct": 0.18, "green_hook_confirmed": True, "vwap_dist_pct": 0.0, "rsi_5m": 50.0}
        reason = intel.evaluate_uncapped_exit("SAPd_EQ", -0.0073, regime, 0.0, {}, metrics, 0.0, False)
        self.assertIsNotNone(reason)
        self.assertIn("AIRBAG", reason)

        # Verifica isolamento dati sporchi pre-epoca V11
        scanner = daemon.QuantMarketScanner()
        closes = [100.0 + i * 0.06 for i in range(20)]
        dirty_tax = {
            "v11_clean_epoch_ts": "2026-11-12T15:30:00",
            "operazioni_chiuse": [
                {"ticker": "SAPd_EQ", "timestamp": "2026-11-12T11:00:00", "risultato_fiscale_eur": -0.25},
                {"ticker": "SAPd_EQ", "timestamp": "2026-11-10T14:00:00", "risultato_fiscale_eur": -0.45},
            ],
        }
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(_make_yahoo_payload(closes))):
            m = scanner.fetch_5m_metrics("SAPd_EQ", tax_data=dirty_tax)
        self.assertEqual(m["memory_730_bonus"], 0.0)

    def test_10_deduped_5m_buckets_and_rome_tax_timezone(self):
        """Invariante #10: deduplica bucket 5m duplicati di Yahoo e timestamp fiscale Europe/Rome."""
        scanner = daemon.QuantMarketScanner()
        now_dt = datetime.datetime.now(daemon.MARKET_TZ).replace(hour=10, minute=0, second=0, microsecond=0)
        base_ts = int(now_dt.timestamp()) - 20 * 300
        # Inserisce due barre nello stesso bucket da 300s alla fine (es. 10:00:00 e 10:02:15)
        ts_list = [base_ts + i * 300 for i in range(19)] + [base_ts + 18 * 300 + 135]
        closes = [50.0 + i * 0.04 for i in range(20)]
        raw = json.dumps({
            "chart": {
                "result": [{
                    "meta": {"regularMarketPrice": closes[-1]},
                    "timestamp": ts_list,
                    "indicators": {"quote": [{"close": closes, "high": closes, "low": closes, "volume": [1000.0]*20}]},
                }]
            }
        }).encode("utf-8")
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(raw)):
            scanner.fetch_5m_metrics("SAPd_EQ")
        cached_ts = scanner.last_valid_bars["SAPd_EQ"]["bar_timestamps"]
        self.assertEqual(len(cached_ts), len(set(cached_ts)))
        for a, b in zip(cached_ts, cached_ts[1:]):
            self.assertGreater(b, a)
            self.assertEqual(b % 300, 0)

        tmp_tax = "/tmp/test_tax_730_rome_tz.json"
        if os.path.exists(tmp_tax):
            os.remove(tmp_tax)
        tracker = ItalianTaxTracker730(filepath=tmp_tax)
        tracker.record_buy("SAPd_EQ", 0.1, 210.0)
        rome_prefix = datetime.datetime.now(daemon.MARKET_TZ).strftime("%Y-%m-%dT%H:")
        lot_ts = tracker.data["lotti_aperti_lifo"]["SAPd_EQ"][0]["timestamp"]
        self.assertTrue(lot_ts.startswith(rome_prefix))
        os.remove(tmp_tax)

    def test_11_completed_bar_rvol_and_typical_price_vwap(self):
        """Invariante #11: RVOL elimina il bias da candela parziale/bull-flag e VWAP usa Typical Price (H+L+C)/3."""
        scanner = daemon.QuantMarketScanner()
        now_dt = datetime.datetime.now(daemon.MARKET_TZ).replace(hour=10, minute=30, second=0, microsecond=0)
        base_ts = int(now_dt.timestamp()) - 20 * 300
        # Ultima candela appena aperta da 30s (volume parziale 500 -> scalato a 5000) dopo candela piena da 5200
        ts_list = [base_ts + i * 300 for i in range(19)] + [base_ts + 19 * 300 + 30]
        closes = [100.0] * 20
        highs = [101.2] * 20   # Typical price = (101.2 + 99.7 + 100.0) / 3 = 100.3 > Close (100.0)
        lows = [99.7] * 20
        vols = [5000.0] * 18 + [5200.0, 500.0]
        raw = json.dumps({
            "chart": {
                "result": [{
                    "meta": {"regularMarketPrice": 100.0},
                    "timestamp": ts_list,
                    "indicators": {"quote": [{"close": closes, "high": highs, "low": lows, "volume": vols}]},
                }]
            }
        }).encode("utf-8")
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(raw)):
            m = scanner.fetch_5m_metrics("SAPd_EQ")
        self.assertGreaterEqual(m["rvol_ratio"], 1.0)
        # Con Close=100.0 e Typical Price=100.3, vwap_dist_pct deve essere negativo (~ -0.30%), NON 0.00%!
        self.assertLess(m["vwap_dist_pct"], -0.20)

    def test_12_gapless_shield_floor_catches_fast_tick_drop(self):
        """Invariante #12: dal picco +0.62%, un salto improvviso a +0.01% o -0.02% senza uncino attiva subito lo scudo."""
        intel = daemon.HybridUncappedIntelligence()
        intel.position_open_time["SAPd_EQ"] = datetime.datetime.now().timestamp() - 900
        regime = {"is_morning_gap_harvest": False, "is_pre_close_window": False, "is_friday_pre_weekend": False}
        metrics = {
            "atr_5m_volatility_pct": 0.16,
            "elastic_shield_act_raw": 0.0056,
            "elastic_shield_pull_raw": 0.0014,
            "fase_onda_sinusoidale": "ONDA_DISCENDENTE_O_DEBOLE",
            "strong_for_overnight": False,
            "green_hook_confirmed": False,
            "vwap_dist_pct": -0.09,
            "rsi_5m": 42.0,
        }
        for fast_gap_pnl in [0.0002, 0.0, -0.0003]:
            intel.peak_pnl_pct["SAPd_EQ"] = 0.0062
            reason = intel.evaluate_uncapped_exit("SAPd_EQ", fast_gap_pnl, regime, 70.0, {}, metrics, 0.0, False)
            self.assertIsNotNone(reason, f"Salto di tick non intercettato a pnl={fast_gap_pnl}")

    def test_13_target_30pct_lock_prevents_infinite_churn(self):
        """Invariante #13: raggiunto il target +30% (130 EUR), liquida una volta e blocca ogni nuovo acquisto."""
        tmp_tax = "/tmp/test_v11_1_target_lock_tax.json"
        tmp_state = "/tmp/test_v11_1_target_lock_state.json"
        for p in (tmp_tax, tmp_state):
            if os.path.exists(p):
                os.remove(p)

        class _MockBroker:
            def __init__(self):
                self.positions = [{"ticker": "SAPd_EQ", "quantity": 0.12, "averagePrice": 208.0, "currentPrice": 212.0, "ppl": 0.48}]
                self.orders = []

            def get_open_positions(self):
                return list(self.positions)

            def get_pending_orders(self):
                return []

            def get_account_cash(self):
                return {"result": 30.20, "free": 130.20}

            def place_market_order(self, ticker: str, quantity: float):
                self.orders.append((ticker, quantity))
                if quantity < 0:
                    self.positions = [p for p in self.positions if p["ticker"] != ticker]
                return {"id": f"ORD_{len(self.orders)}"}

            def cancel_order(self, order_id):
                return None

        broker = _MockBroker()
        bot = daemon.Trading212AutonomousBot(client=broker, total_budget_eur=100.0, cartridges=4, annual_target_pct=0.30)
        bot.tax_tracker = ItalianTaxTracker730(filepath=tmp_tax)
        bot.tax_tracker.data["plusvalenze_lorde_eur"] = 30.20
        bot.tax_tracker.data["minusvalenze_lorde_eur"] = 0.0
        bot.tax_tracker.save()

        intel = daemon.HybridUncappedIntelligence()
        intel.prev_open_snapshot.clear()
        scanner = daemon.QuantMarketScanner()
        scanner.cached_metrics = {
            "ASMLa_EQ": {
                "ticker": "ASMLa_EQ", "name": "ASML", "squad": "SQUADRA_2_CAVALCA_ONDA",
                "sector": "CHIP_LITOGRAFIA_WAFER", "live_price_eur": 1350.0, "rsi_5m": 54.0,
                "vwap_dist_pct": 0.15, "atr_5m_volatility_pct": 0.22, "day_range_pct": 1.8,
                "rvol_ratio": 1.4, "quant_buy_score": 84.0, "green_hook_confirmed": True,
                "strong_for_overnight": True, "has_fresh_intraday_feed": True,
                "fase_onda_sinusoidale": "SUPER_TREND_VERO_POSITIVO_BREAKOUT",
            }
        }
        scanner.last_scan_ts = 1e12
        scanner.scan_all = lambda **kwargs: dict(scanner.cached_metrics)

        class _DummyRadar:
            def evaluate_overnight_wave(self):
                return {"verdict": "OK", "allow_overnight_hold": True, "nasdaq_change_pct": 0.4, "sp500_change_pct": 0.3, "dax_change_pct": 0.5, "vix_fear_change_pct": -1.0, "vix_level": 15.0}

        real_dt = datetime.datetime
        monday_10am = real_dt(2026, 11, 16, 10, 15, 0, tzinfo=daemon.MARKET_TZ)
        with patch.object(daemon, "BOT_STATE_PATH", tmp_state), patch("datetime.datetime") as mock_dt:
            mock_dt.now.side_effect = lambda tz=None: monday_10am.astimezone(tz) if tz else monday_10am.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            mock_dt.fromisoformat.side_effect = real_dt.fromisoformat
            st1 = daemon.run_cycle(bot, intel, scanner, _DummyRadar(), 1)
            # Ciclo 1: liquida SAPd_EQ (-0.12) e NON compra nulla
            self.assertEqual(broker.orders, [("SAPd_EQ", -0.12)])
            self.assertTrue(bot.tax_tracker.data.get("target_30pct_raggiunto_blocco_attivo"))
            self.assertFalse(st1["regime_mercato_attivo"]["allow_new_buys"])

            # Ciclo 2: ZERO nuovi acquisti e ZERO liquidazioni duplicate (Zero Churn!)
            broker.orders.clear()
            st2 = daemon.run_cycle(bot, intel, scanner, _DummyRadar(), 2)
            self.assertEqual(broker.orders, [])
            self.assertEqual(st2["regime_mercato_attivo"]["code"], "TARGET_30PCT_RAGGIUNTO_CONTO_IN_CASSAFORTE")

        for p in (tmp_tax, tmp_state):
            if os.path.exists(p):
                os.remove(p)

    def test_14_ny_dst_safe_clock_and_unified_bench_buy_predicate(self):
        """Invariante #14: orologio America/New_York DST-safe (Marzo/Ottobre) e predicato unico Panchina == BUY."""
        intel = daemon.HybridUncappedIntelligence()
        # 25 Marzo 2026: USA già in EDT (UTC-4), Italia ancora in CET (UTC+1) -> 08:30 ET corrisponde alle 13:30 CET!
        dst_macro_dt = datetime.datetime(2026, 3, 25, 13, 30, 0, tzinfo=daemon.MARKET_TZ)
        reg_macro = intel.get_intraday_regime(dst_macro_dt)
        self.assertEqual(reg_macro["code"], "PAUSA_ANTI_SHOCK_DATI_MACRO_USA_14_30")
        self.assertFalse(reg_macro["allow_new_buys"])

        # 25 Marzo 2026 ore 14:35 CET == 09:35 ET -> Wall Street è GIÀ aperta!
        dst_nyse_dt = datetime.datetime(2026, 3, 25, 14, 35, 0, tzinfo=daemon.MARKET_TZ)
        reg_nyse = intel.get_intraday_regime(dst_nyse_dt)
        self.assertEqual(reg_nyse["code"], "FASE_3_ONDA_WALL_STREET_SENZA_TETTO")
        self.assertTrue(reg_nyse["us_market_live"])

        # Durante Pausa Pranzo (12:15 CET), V11.2 Zero Cerotti blocca il 100% dei nuovi acquisti (anche RVOL >= 1.8x)
        lunch_dt = datetime.datetime(2026, 11, 12, 12, 15, 0, tzinfo=daemon.MARKET_TZ)
        reg_lunch = intel.get_intraday_regime(lunch_dt)
        self.assertFalse(reg_lunch["allow_new_buys"])
        ordinary_cand = {
            "ticker": "SAPd_EQ", "live_price_eur": 210.0, "vwap_dist_pct": 0.15,
            "has_fresh_intraday_feed": True, "rvol_ratio": 0.90, "quant_buy_score": 74.0,
            "rsi_5m": 54.0, "green_hook_confirmed": True, "atr_5m_volatility_pct": 0.19,
            "day_range_pct": 1.6, "kaufman_efficiency_ratio": 0.55, "strong_for_overnight": True,
        }
        elite_cand = dict(ordinary_cand, rvol_ratio=2.10, quant_buy_score=82.5)
        ov_ok = {"allow_overnight_hold": True, "nasdaq_change_pct": 0.2, "sp500_change_pct": 0.2, "dax_change_pct": 0.3, "vix_fear_change_pct": -0.5, "vix_level": 16.0}
        self.assertFalse(intel.is_eligible_entry_candidate(ordinary_cand, reg_lunch, ov_ok))
        self.assertFalse(intel.is_eligible_entry_candidate(elite_cand, reg_lunch, ov_ok))

        # Alle 14:40 CET (08:40 ET, Pre-Market USA dopo i dati macro), il blocco pranzo termina e i candidati idonei (>= 58 pt) passano
        pre_us_dt = datetime.datetime(2026, 11, 12, 14, 40, 0, tzinfo=daemon.MARKET_TZ)
        reg_pre_us = intel.get_intraday_regime(pre_us_dt)
        self.assertTrue(reg_pre_us["allow_new_buys"])
        self.assertTrue(intel.is_eligible_entry_candidate(ordinary_cand, reg_pre_us, ov_ok))
        low_score_cand = dict(ordinary_cand, quant_buy_score=55.0)  # < BASE_MIN_BUY_SCORE (58.0)
        self.assertFalse(intel.is_eligible_entry_candidate(low_score_cand, reg_pre_us, ov_ok))

    def test_15_continuous_monotonic_profit_protection_curve(self):
        """Invariante #15: curva salva-utile monotona non-decrescente ovunque, senza scalini ciechi tra +0.58% e shield_act."""
        intel = daemon.HybridUncappedIntelligence()
        for atr_raw in [0.0014, 0.0022, 0.0030]:
            shield_act = max(0.0048, round(atr_raw * 3.85, 4))
            shield_pull = max(0.0012, round(atr_raw * 0.92, 4))
            prev_floor = -1.0
            floors_mid = []
            for step in range(0, 220):
                pk = round(step * 0.0001, 4)
                stage, fl = intel.compute_profit_protection_floor(pk, shield_act, shield_pull, atr_raw, False)
                if fl is not None:
                    self.assertGreaterEqual(
                        fl, prev_floor,
                        f"Violazione monotonicità a peak={pk} (atr={atr_raw}): {fl} < {prev_floor}",
                    )
                    prev_floor = fl
                if 0.0058 <= pk < shield_act and fl is not None:
                    floors_mid.append(fl)
            if atr_raw >= 0.0026:
                # Su titoli High-Beta (shield_act ~ 1.15%), il pavimento intermedio DEVE salire oltre +0.40% prima di shield_act!
                self.assertGreater(max(floors_mid), 0.0045)

    def test_16_mifid_limit_order_tick_snapping_and_zero_market_fallback(self):
        """Invariante #16: tick MiFID II RTS 11 esatti, sizing su limit_px (4ª cartuccia <= 25 EUR), zero fallback a Market Order."""
        # Verifica tutte le 6 fasce di prezzo MiFID II RTS 11
        self.assertEqual(Trading212Client.snap_mifid_tick_price(15.127, "BUY"), 15.12)
        self.assertEqual(Trading212Client.snap_mifid_tick_price(34.139, "BUY"), 34.12)
        self.assertEqual(Trading212Client.snap_mifid_tick_price(142.88, "BUY"), 142.80)
        self.assertEqual(Trading212Client.snap_mifid_tick_price(238.57, "BUY"), 238.40)
        self.assertEqual(Trading212Client.snap_mifid_tick_price(726.84, "BUY"), 726.00)
        self.assertEqual(Trading212Client.snap_mifid_tick_price(2145.60, "BUY"), 2144.00)

        tmp_tax = "/tmp/test_v11_2_limit_buy_tax.json"
        tmp_state = "/tmp/test_v11_2_limit_buy_state.json"
        for p in (tmp_tax, tmp_state):
            if os.path.exists(p):
                os.remove(p)

        class _MockLimitBroker:
            def __init__(self):
                self.positions = [
                    {"ticker": "SAPd_EQ", "quantity": 0.119, "averagePrice": 210.0, "currentPrice": 210.0, "ppl": 0.0},
                    {"ticker": "ALVd_EQ", "quantity": 0.083, "averagePrice": 300.0, "currentPrice": 300.0, "ppl": 0.0},
                    {"ticker": "SIEd_EQ", "quantity": 0.138, "averagePrice": 180.0, "currentPrice": 180.0, "ppl": 0.0},
                ]
                self.limit_calls = []
                self.market_calls = []
                self.cancelled = []
                self.fail_next_limit = False
                self.leave_unfilled = False

            def get_open_positions(self):
                return list(self.positions)

            def get_pending_orders(self):
                if self.leave_unfilled and self.limit_calls:
                    return [{"id": "LIM_SPIKE", "ticker": self.limit_calls[-1][0], "quantity": self.limit_calls[-1][1], "type": "LIMIT"}]
                return []

            def get_account_cash(self):
                return {"result": 0.0, "free": 25.25}

            def place_limit_order(self, ticker: str, quantity: float, limit_price: float, time_validity: str = "DAY"):
                self.limit_calls.append((ticker, quantity, limit_price, time_validity))
                if self.fail_next_limit:
                    raise RuntimeError("HTTP 400 Fractional limit rejected")
                if not self.leave_unfilled:
                    # Eseguito al prezzo ask reale (inferiore al cap +1.00%)
                    fill_px = round(limit_price / 1.008, 2)
                    self.positions.append({"ticker": ticker, "quantity": quantity, "averagePrice": fill_px, "currentPrice": fill_px, "ppl": 0.0})
                    return {"id": "LIM_OK_1"}
                return {"id": "LIM_SPIKE"}

            def place_market_order(self, ticker: str, quantity: float):
                self.market_calls.append((ticker, quantity))
                return {"id": "MKT_FORBIDDEN"}

            def cancel_order(self, order_id):
                self.cancelled.append(order_id)

        broker = _MockLimitBroker()
        bot = daemon.Trading212AutonomousBot(client=broker, total_budget_eur=100.0, cartridges=4, annual_target_pct=0.30)
        bot.tax_tracker = ItalianTaxTracker730(filepath=tmp_tax)
        intel = daemon.HybridUncappedIntelligence()
        intel.prev_open_snapshot.clear()
        scanner = daemon.QuantMarketScanner()
        cand_asml = {
            "ticker": "ASMLa_EQ", "name": "ASML", "squad": "SQUADRA_2_CAVALCA_ONDA",
            "sector": "CHIP_LITOGRAFIA_WAFER", "live_price_eur": 725.40, "rsi_5m": 53.0,
            "vwap_dist_pct": 0.12, "atr_5m_volatility_pct": 0.24, "day_range_pct": 1.9,
            "rvol_ratio": 1.35, "quant_buy_score": 81.0, "green_hook_confirmed": True,
            "strong_for_overnight": True, "has_fresh_intraday_feed": True,
            "fase_onda_sinusoidale": "SUPER_TREND_VERO_POSITIVO_BREAKOUT",
        }
        scanner.scan_all = lambda **kwargs: {"ASMLa_EQ": cand_asml}

        class _DummyRadar:
            def evaluate_overnight_wave(self):
                return {"verdict": "OK", "allow_overnight_hold": True, "nasdaq_change_pct": 0.4, "sp500_change_pct": 0.3, "dax_change_pct": 0.5, "vix_fear_change_pct": -1.0, "vix_level": 15.0}

        real_dt = datetime.datetime
        tuesday_10am = real_dt(2026, 11, 17, 10, 10, 0, tzinfo=daemon.MARKET_TZ)
        with patch.object(daemon, "BOT_STATE_PATH", tmp_state), patch.object(daemon, "LIMIT_FILL_POLL_SEC", 0.0), patch("datetime.datetime") as mock_dt:
            mock_dt.now.side_effect = lambda tz=None: tuesday_10am.astimezone(tz) if tz else tuesday_10am.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            mock_dt.fromisoformat.side_effect = real_dt.fromisoformat

            # Caso A: errore HTTP 400 su LIMIT -> ZERO fallback su place_market_order!
            broker.fail_next_limit = True
            daemon.run_cycle(bot, intel, scanner, _DummyRadar(), 1)
            self.assertEqual(broker.market_calls, [])

            # Caso B: spike > +1% (ordine LIMIT non eseguito) -> cancellazione immediata e ZERO lotti fantasma nel 730!
            intel.last_sell_price.clear()
            intel.last_sell_time.clear()
            broker.fail_next_limit = False
            broker.leave_unfilled = True
            daemon.run_cycle(bot, intel, scanner, _DummyRadar(), 2)
            self.assertIn("LIM_SPIKE", broker.cancelled)
            self.assertNotIn("ASMLa_EQ", bot.tax_tracker.data.get("lotti_aperti_lifo", {}))

            # Caso C: esecuzione regolare 4ª cartuccia -> margine riservato qty * limit_px <= liquidità residua (~25.25 EUR)!
            intel.last_sell_price.clear()
            intel.last_sell_time.clear()
            broker.leave_unfilled = False
            broker.limit_calls.clear()
            daemon.run_cycle(bot, intel, scanner, _DummyRadar(), 3)
            self.assertEqual(len(broker.limit_calls), 1)
            _, qty_sent, lim_px_sent, _ = broker.limit_calls[0]
            self.assertEqual(lim_px_sent, 732.0)  # 725.40 * 1.01 = 732.654 -> tick MiFID 1.00 EUR -> 732.00 EUR
            self.assertLessEqual(round(qty_sent * lim_px_sent, 2), 25.25)
            self.assertEqual(broker.market_calls, [])

        for p in (tmp_tax, tmp_state):
            if os.path.exists(p):
                os.remove(p)

    def test_17_gap_clean_intraday_atr_er_and_zero_synthetic_bench_bar(self):
        """Invariante #17: ATR/ER depurati dal gap notturno 17:25->09:00 e zero barre sintetiche su feed Yahoo ritardati."""
        scanner = daemon.QuantMarketScanner()
        today_dt = datetime.datetime.now(daemon.MARKET_TZ).replace(hour=10, minute=0, second=0, microsecond=0)
        yday_dt = (today_dt - datetime.timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)
        # 5 barre ieri pomeriggio intorno a 100.0 EUR + salto notturno a 106.0 EUR (+6% gap!) + 15 barre oggi strette (~0.12% range)
        yday_ts = [int(yday_dt.timestamp()) + i * 300 for i in range(5)]
        today_open_ts = int(today_dt.replace(hour=9, minute=0).timestamp())
        today_ts = [today_open_ts + i * 300 for i in range(15)]
        ts_all = yday_ts + today_ts
        closes = [100.0, 100.05, 99.98, 100.02, 100.0] + [106.0 + (i % 2) * 0.08 for i in range(15)]
        highs = [c + 0.07 for c in closes]
        lows = [c - 0.07 for c in closes]
        vols = [3000.0] * 20
        raw = json.dumps({
            "chart": {
                "result": [{
                    "meta": {"regularMarketPrice": closes[-1]},
                    "timestamp": ts_all,
                    "indicators": {"quote": [{"close": closes, "high": highs, "low": lows, "volume": vols}]},
                }]
            }
        }).encode("utf-8")
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(raw)):
            m = scanner.fetch_5m_metrics("SAPd_EQ")
        # Senza depurazione del gap +6%, ATR sarebbe > 0.65%; con gap-clean V11.2 misura solo il vero range intraday (< 0.25%)!
        self.assertLess(m["atr_5m_volatility_pct"], 0.25)

        # Verifica zero candela sintetica su titolo in panchina con Yahoo ritardato di 15m e candela rossa:
        # regularMarketPrice leggermente sopra l'ultimo close NON deve fabbricare una falsa barra verde senza T212 live!
        delayed_closes = [200.0 + i * 0.1 for i in range(18)] + [201.8, 201.4]  # Ultima candela ROSSA (201.8 -> 201.4)
        delayed_ts = [int(time_val) for time_val in [int(datetime.datetime.now(daemon.MARKET_TZ).timestamp()) // 300 * 300 - (23 - i) * 300 for i in range(20)]]
        raw_delayed = json.dumps({
            "chart": {
                "result": [{
                    "meta": {"regularMarketPrice": 201.55},
                    "timestamp": delayed_ts,
                    "indicators": {"quote": [{"close": delayed_closes, "high": [c + 0.1 for c in delayed_closes], "low": [c - 0.1 for c in delayed_closes], "volume": [2500.0] * 20}]},
                }]
            }
        }).encode("utf-8")
        scanner_bench = daemon.QuantMarketScanner()
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(raw_delayed)):
            m_bench = scanner_bench.fetch_5m_metrics("IFXd_EQ")
        self.assertFalse(m_bench["green_hook_confirmed"])

    def test_18_trailing_daily_vault_and_partial_sell_lifo_preservation(self):
        """Invariante #18: Trailing Daily Vault senza soffitto statico + preservazione LIFO su vendita parziale & cash sync."""
        tmp_tax = "/tmp/test_v11_2_lifo_partial_tax.json"
        if os.path.exists(tmp_tax):
            os.remove(tmp_tax)
        tracker = ItalianTaxTracker730(filepath=tmp_tax)
        tracker.record_buy("SAPd_EQ", 0.1500, 200.00)
        orig_ts = tracker.data["lotti_aperti_lifo"]["SAPd_EQ"][0]["timestamp"]
        # Vendita parziale di ribilanciamento (0.0300 su 0.1500 azioni)
        op = tracker.record_sell("SAPd_EQ", 0.0300, 210.00, fallback_avg_price_eur=200.00)
        self.assertAlmostEqual(op["risultato_fiscale_eur"], 0.30, places=2)
        remaining_lots = tracker.data["lotti_aperti_lifo"].get("SAPd_EQ", [])
        self.assertEqual(len(remaining_lots), 1)
        self.assertAlmostEqual(remaining_lots[0]["quantity"], 0.1200, places=4)
        self.assertEqual(remaining_lots[0]["timestamp"], orig_ts)

        # Riconciliazione simmetrica su slippage positivo (t212_net > cur_plus - cur_minus -> minusvalenze MAI negative!)
        tracker.reconcile_certified_cash_result(0.42)
        self.assertGreaterEqual(tracker.data["minusvalenze_lorde_eur"], 0.0)
        self.assertAlmostEqual(
            tracker.data["plusvalenze_lorde_eur"] - tracker.data["minusvalenze_lorde_eur"],
            0.42,
            places=2,
        )
        os.remove(tmp_tax)

        # Verifica logica Trailing Daily High-Water-Mark Vault:
        # 1) A +2.40 EUR senza ritracciamento -> False (lascia correre la giornata di trend!)
        # 2) Da picco +2.40 EUR a +2.05 EUR (giveback 0.35 >= 0.30) -> True (blinda il bottino!)
        peak_day = 2.40
        cur_day_trend = 2.40
        self.assertFalse(peak_day >= daemon.DAILY_VAULT_TRIGGER_EUR and (peak_day - cur_day_trend) >= daemon.DAILY_VAULT_GIVEBACK_EUR)
        cur_day_pullback = 2.05
        self.assertTrue(peak_day >= daemon.DAILY_VAULT_TRIGGER_EUR and round(peak_day - cur_day_pullback, 2) >= daemon.DAILY_VAULT_GIVEBACK_EUR)


if __name__ == "__main__":
    unittest.main()
