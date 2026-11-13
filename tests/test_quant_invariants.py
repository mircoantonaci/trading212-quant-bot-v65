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

    def setUp(self):
        self._tmp_bot_state = "/tmp/test_v11_hermetic_state.json"
        self._tmp_scan_cache = "/tmp/test_v11_hermetic_scanner_cache.json"
        self._tmp_tax_path = "/tmp/test_v11_hermetic_tax.json"
        for p in (self._tmp_bot_state, self._tmp_scan_cache, self._tmp_tax_path):
            if os.path.exists(p):
                os.remove(p)
        self._p_state = patch.object(daemon, "BOT_STATE_PATH", self._tmp_bot_state)
        self._p_cache = patch.object(daemon, "SCANNER_CACHE_PATH", self._tmp_scan_cache)
        self._p_tax = patch.object(daemon, "TAX_TRACKER_PATH", self._tmp_tax_path)
        self._p_state.start()
        self._p_cache.start()
        self._p_tax.start()

    def tearDown(self):
        self._p_tax.stop()
        self._p_cache.stop()
        self._p_state.stop()
        for p in (self._tmp_bot_state, self._tmp_scan_cache, self._tmp_tax_path):
            if os.path.exists(p):
                os.remove(p)

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

        # Durante Pausa Pranzo (12:15 CET), il Cecchino Mezzogiorno impone max 2 slot e blocca il 100% dei setup ordinari o con RVOL < 2.20x
        lunch_dt = datetime.datetime(2026, 11, 12, 12, 15, 0, tzinfo=daemon.MARKET_TZ)
        reg_lunch = intel.get_intraday_regime(lunch_dt)
        self.assertTrue(reg_lunch["is_midday_sniper_window"])
        self.assertEqual(reg_lunch["max_active_slots"], 2)
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

    def test_19_pre_close_1715_buy_freeze_and_strict_overnight_wave(self):
        """Invariante #19: dalle 17:15 CET stop totale nuovi acquisti (e Switch Stagnazione spento) + Onda USA >= +0,25%."""
        intel = daemon.HybridUncappedIntelligence()
        dt_1714 = datetime.datetime(2026, 11, 12, 17, 14, 0, tzinfo=daemon.MARKET_TZ)
        dt_1715 = datetime.datetime(2026, 11, 12, 17, 15, 0, tzinfo=daemon.MARKET_TZ)
        reg_1714 = intel.get_intraday_regime(dt_1714)
        reg_1715 = intel.get_intraday_regime(dt_1715)
        self.assertTrue(reg_1714["allow_new_buys"])
        self.assertFalse(reg_1715["allow_new_buys"])
        self.assertTrue(reg_1715["is_pre_close_window"])

        elite_cand = {
            "ticker": "ASMLa_EQ", "live_price_eur": 1350.0, "vwap_dist_pct": 0.20,
            "has_fresh_intraday_feed": True, "rvol_ratio": 1.60, "quant_buy_score": 92.0,
            "rsi_5m": 55.0, "green_hook_confirmed": True, "atr_5m_volatility_pct": 0.22,
            "day_range_pct": 1.8, "kaufman_efficiency_ratio": 0.65, "strong_for_overnight": True,
        }
        ov_strong = {
            "allow_overnight_hold": True, "nasdaq_change_pct": 0.80, "sp500_change_pct": 0.60,
            "dax_change_pct": 0.50, "vix_fear_change_pct": -2.0, "vix_level": 15.0,
        }
        self.assertTrue(intel.is_eligible_entry_candidate(elite_cand, reg_1714, ov_strong))
        self.assertFalse(intel.is_eligible_entry_candidate(elite_cand, reg_1715, ov_strong))

        # Switch Stagnazione (#9) NON deve mai vendere per ruotare quando allow_new_buys == False (es. Pausa Pranzo o >= 17:15)
        reg_lunch = intel.get_intraday_regime(datetime.datetime(2026, 11, 12, 12, 0, 0, tzinfo=daemon.MARKET_TZ))
        intel.position_open_time["SAPd_EQ"] = datetime.datetime.now().timestamp() - 3600.0
        intel.peak_pnl_pct["SAPd_EQ"] = 0.0020
        stag_metrics = {
            "atr_5m_volatility_pct": 0.18, "elastic_shield_act_raw": 0.0068, "elastic_shield_pull_raw": 0.0016,
            "fase_onda_sinusoidale": "ONDA_DISCENDENTE_O_DEBOLE", "strong_for_overnight": False,
            "green_hook_confirmed": False, "vwap_dist_pct": -0.12, "rsi_5m": 44.0, "quant_buy_score": 18.0,
        }
        reason_1714 = intel.evaluate_uncapped_exit(
            "SAPd_EQ", 0.0018, reg_1714, 92.0, ov_strong, stag_metrics, 0.0, True, False
        )
        self.assertIn("BLINDATURA #9", reason_1714 or "")
        intel.peak_pnl_pct["SAPd_EQ"] = 0.0020
        reason_lunch = intel.evaluate_uncapped_exit(
            "SAPd_EQ", 0.0018, reg_lunch, 92.0, ov_strong, stag_metrics, 0.0, True, False
        )
        self.assertIsNone(reason_lunch)
        intel.peak_pnl_pct["SAPd_EQ"] = 0.0020
        reason_1715 = intel.evaluate_uncapped_exit(
            "SAPd_EQ", 0.0018, reg_1715, 92.0, ov_strong, stag_metrics, 0.0, True, False
        )
        self.assertIsNone(reason_1715)

        # Verifica selettività Onda Notturna USA (>= +0.25% media ponderata con entrambi gli indici positivi)
        radar = daemon.OvernightWaveRadar()
        lukewarm_map = {"%5EGSPC": (0.12, 5900.0, True), "%5EIXIC": (0.15, 19000.0, True), "%5EGDAXI": (0.10, 19200.0, True), "%5EVIX": (0.2, 16.5, True)}
        with patch.object(radar, "_fetch_index_snapshot", side_effect=lambda s: lukewarm_map[s]):
            res_flat = radar.evaluate_overnight_wave(force=True)
        self.assertFalse(res_flat["allow_overnight_hold"])

        strong_map = {"%5EGSPC": (0.25, 5920.0, True), "%5EIXIC": (0.35, 19100.0, True), "%5EGDAXI": (0.20, 19250.0, True), "%5EVIX": (-1.2, 15.8, True)}
        with patch.object(radar, "_fetch_index_snapshot", side_effect=lambda s: strong_map[s]):
            res_strong = radar.evaluate_overnight_wave(force=True)
        self.assertTrue(res_strong["allow_overnight_hold"])

    def test_20_gettex_0s_streaming_fusion_blocks_stale_peak_and_preserves_xetra_rvol(self):
        """Invariante #20: GETTEX 0s blocca i falsi positivi da picco Yahoo vecchio di 15m senza alterare RVOL XETRA, con priorità T212."""
        real_dt = datetime.datetime
        # Simula esattamente il caso ENRd_EQ delle 11:11 CET (mercato aperto: Giovedì 12 Nov 2026 ore 11:11 CET)
        mkt_dt = real_dt(2026, 11, 12, 11, 11, 10, tzinfo=daemon.MARKET_TZ)
        now_epoch = mkt_dt.timestamp()
        # Yahoo è fermo di 15 minuti (ultima candela alle 10:55 CET in forte salita a 133.60 EUR)
        last_yahoo_bucket = int(real_dt(2026, 11, 12, 10, 55, 0, tzinfo=daemon.MARKET_TZ).timestamp())
        base_ts = last_yahoo_bucket - 19 * 300
        stale_rally_closes = [
            132.0, 132.2, 132.4, 132.3, 132.5, 132.3, 132.1, 132.2, 132.4, 132.2,
            132.0, 132.1, 132.3, 132.1, 131.9, 132.0, 132.1, 132.25, 132.45, 132.65,
        ]
        xetra_vols = [4000.0] * 18 + [6200.0, 6400.0]
        yahoo_raw = _make_yahoo_payload(stale_rally_closes, vols=xetra_vols, base_ts=base_ts)

        # 1) Senza GETTEX (solo Yahoo ritardato di 15m), il titolo appare erroneamente in pieno breakout (Score > 65)
        scanner_stale = daemon.QuantMarketScanner()
        with patch("datetime.datetime") as mock_dt, patch("time.time", return_value=now_epoch), patch(
            "urllib.request.urlopen", return_value=_FakeHTTPResp(yahoo_raw)
        ):
            mock_dt.now.side_effect = lambda tz=None: mkt_dt.astimezone(tz) if tz else mkt_dt.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            m_stale = scanner_stale.fetch_5m_metrics("ENRd_EQ")
        self.assertGreater(m_stale["quant_buy_score"], 65.0)
        self.assertEqual(m_stale["price_feed_source"], "YAHOO_FALLBACK_15M")

        # 2) Con Occhio GETTEX 0s (alle 11:11 il titolo è in realtà già sceso a 131.88 EUR con candela 5m rossa):
        #    - Score crolla a 0.0 (falso positivo bloccato al 100%)
        #    - RVOL istituzionale XETRA resta identico al centesimo (zero distorsione dai volumi locali di Monaco)
        gettex_raw = json.dumps({
            "data": [
                {"s": "GETTEX:ENR", "d": [131.88, 132.20, 132.24, 131.85, 131.88, "streaming"]},
            ]
        }).encode("utf-8")
        scanner_live = daemon.QuantMarketScanner()
        with patch("datetime.datetime") as mock_dt, patch("time.time", return_value=now_epoch):
            mock_dt.now.side_effect = lambda tz=None: mkt_dt.astimezone(tz) if tz else mkt_dt.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(gettex_raw)):
                updated_n = scanner_live.refresh_gettex_live_quotes(force=True)
            self.assertEqual(updated_n, 1)
            with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(yahoo_raw)):
                m_live = scanner_live.fetch_5m_metrics("ENRd_EQ")

        self.assertEqual(m_live["live_price_eur"], 131.88)
        self.assertEqual(m_live["price_feed_source"], "GETTEX_STREAMING_0S")
        self.assertFalse(m_live["green_hook_confirmed"])
        self.assertEqual(m_live["quant_buy_score"], 0.0)
        self.assertEqual(m_live["rvol_ratio"], m_stale["rvol_ratio"])

        # 3) Se il titolo è già in portafoglio su Trading 212, il prezzo esecutivo T212 (0ms) ha priorità assoluta su GETTEX
        with patch("datetime.datetime") as mock_dt, patch("time.time", return_value=now_epoch):
            mock_dt.now.side_effect = lambda tz=None: mkt_dt.astimezone(tz) if tz else mkt_dt.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            scanner_live.update_t212_live_price("ENRd_EQ", 131.95)
            with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(gettex_raw)):
                scanner_live.refresh_gettex_live_quotes(force=True)
            with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(yahoo_raw)):
                m_t212 = scanner_live.fetch_5m_metrics("ENRd_EQ")
        self.assertEqual(m_t212["live_price_eur"], 131.95)
        self.assertEqual(m_t212["price_feed_source"], "T212_LIVE_0MS")

        # 4) Resilienza: un timeout HTTP su GETTEX non solleva mai eccezioni
        with patch("urllib.request.urlopen", side_effect=TimeoutError("GETTEX timeout")):
            self.assertEqual(scanner_live.refresh_gettex_live_quotes(force=True), 0)

    def test_21_us_big_tech_eur_universe_and_markowitz_sector_isolation(self):
        """Invariante #21: 39 Colossi EUR Zero-Fee (32 UE + 7 Big Tech USA in EUR), 100% GETTEX 0s e isolamento Markowitz."""
        daemon.discover_and_verify_eur_giants(None)
        expected_us_eur = {"NVDd_EQ", "MSFd_EQ", "APCd_EQ", "AMZd_EQ", "ABEAd_EQ", "FB2Ad_EQ", "AMDd_EQ"}
        self.assertTrue(expected_us_eur.issubset(set(daemon.ASSET_PROFILES.keys())))
        # FREd_EQ ("" in t212_verified_universe.json) deve essere escluso per evitare ordini HTTP 400 su ticker inesistenti
        self.assertNotIn("FREd_EQ", daemon.ASSET_PROFILES)
        self.assertEqual(len(daemon.ASSET_PROFILES), 39)

        for tkr, prof in daemon.ASSET_PROFILES.items():
            meta = daemon.EUR_ZERO_FEE_UNIVERSE[tkr]
            self.assertEqual(meta["currency"], "EUR", f"Valuta non EUR su {tkr}")
            self.assertEqual(meta["tobin_tax"], "0.00%", f"Tobin tax non zero su {tkr}")
            self.assertTrue(str(prof.get("gettex", "")).startswith("GETTEX:"), f"Simbolo GETTEX mancante su {tkr}")

        # Isolamento settoriale Markowitz sulle Big Tech USA correlate:
        # NVIDIA + AMD condividono CHIP_ACCELERATORI_AI; Alphabet + Meta condividono DIGITAL_ADS_SOCIAL_AI;
        # Microsoft + SAP condividono SOFTWARE_CLOUD; Amazon + Zalando condividono ECOMMERCE_CONSUMER.
        self.assertEqual(daemon.ASSET_PROFILES["NVDd_EQ"]["sector"], daemon.ASSET_PROFILES["AMDd_EQ"]["sector"])
        self.assertEqual(daemon.ASSET_PROFILES["ABEAd_EQ"]["sector"], daemon.ASSET_PROFILES["FB2Ad_EQ"]["sector"])
        self.assertEqual(daemon.ASSET_PROFILES["MSFd_EQ"]["sector"], daemon.ASSET_PROFILES["SAPd_EQ"]["sector"])
        self.assertEqual(daemon.ASSET_PROFILES["AMZd_EQ"]["sector"], daemon.ASSET_PROFILES["ZALd_EQ"]["sector"])

    def test_22_true_green_hook_blocks_post_spike_red_candle_reversals(self):
        """Invariante #22: True Green Hook blocca candele 5m rosse/in discesa post-spike (caso reale AMDd_EQ 14:38) e promuove vere candele verdi (MRKd_EQ)."""
        real_dt = datetime.datetime
        mkt_dt = real_dt(2026, 11, 13, 14, 38, 28, tzinfo=daemon.MARKET_TZ)
        now_epoch = mkt_dt.timestamp()
        # Yahoo fermo alle 14:20 CET; ponte + candela 14:30 esplosiva 519.20 -> 522.10 EUR
        last_yahoo_bucket = int(real_dt(2026, 11, 13, 14, 20, 0, tzinfo=daemon.MARKET_TZ).timestamp())
        base_ts = last_yahoo_bucket - 19 * 300
        closes_amd = [
            518.5, 518.8, 519.0, 518.7, 518.4, 518.6, 518.9, 519.1, 518.8, 518.5,
            518.2, 518.4, 518.0, 517.8, 517.5, 517.2, 516.9, 516.6, 516.5, 517.8,
        ]
        yahoo_amd = _make_yahoo_payload(closes_amd, vols=[4500.0] * 20, base_ts=base_ts)

        scanner = daemon.QuantMarketScanner()
        b_1425 = int(real_dt(2026, 11, 13, 14, 25, 0, tzinfo=daemon.MARKET_TZ).timestamp())
        b_1430 = int(real_dt(2026, 11, 13, 14, 30, 0, tzinfo=daemon.MARKET_TZ).timestamp())
        scanner.realtime_5m_bars["AMDd_EQ"] = {
            b_1430: {"open": 519.20, "high": 522.40, "low": 519.20, "close": 522.10},
        }
        scanner.realtime_5m_bars["MRKd_EQ"] = {
            b_1425: {"open": 149.50, "high": 149.55, "low": 149.30, "close": 149.35, "has_true_open": True},
            b_1430: {"open": 149.35, "high": 149.48, "low": 149.32, "close": 149.42, "has_true_open": True},
        }
        # Alle 14:38:28 la candela 14:35 è ROSSA (open=522.10 -> close=520.80, ma low=520.50 >= 519.20!).
        # Col vecchio `or higher_low` passava erroneamente; col True Green Hook V11.2 DEVE essere bloccata (Score == 0.0)!
        gx_amd_reversal = json.dumps({
            "data": [
                {"s": "GETTEX:AMD", "d": [520.80, 522.10, 522.10, 520.50, 520.80, "streaming"]},
                {"s": "GETTEX:MRK", "d": [149.68, 149.42, 149.72, 149.40, 149.68, "streaming"]},
            ]
        }).encode("utf-8")

        closes_mrk = [
            149.2, 149.3, 149.4, 149.3, 149.5, 149.4, 149.2, 149.3, 149.4, 149.3,
            149.1, 149.2, 149.3, 149.2, 149.1, 149.2, 149.3, 149.4, 149.45, 149.50,
        ]
        yahoo_mrk = _make_yahoo_payload(closes_mrk, vols=[3200.0] * 20, base_ts=base_ts)

        with patch("datetime.datetime") as mock_dt, patch("time.time", return_value=now_epoch):
            mock_dt.now.side_effect = lambda tz=None: mkt_dt.astimezone(tz) if tz else mkt_dt.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(gx_amd_reversal)):
                scanner.refresh_gettex_live_quotes(force=True)
            with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(yahoo_amd)):
                m_amd = scanner.fetch_5m_metrics("AMDd_EQ")
            with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(yahoo_mrk)):
                m_mrk = scanner.fetch_5m_metrics("MRKd_EQ")

        self.assertFalse(m_amd["green_hook_confirmed"])
        self.assertEqual(m_amd["quant_buy_score"], 0.0)
        self.assertTrue(m_mrk["green_hook_confirmed"])
        self.assertGreater(m_mrk["quant_buy_score"], 65.0)

    def test_23_midday_extraordinary_explosion_sniper_max_2_slots_and_0s_gate(self):
        """Invariante #23: tra 11:15 e 08:27 ET ammette solo esplosioni 0s (Breakout o Valle AMD 14:27), vieta Yahoo 15m e blocca a max 2/4 slot."""
        intel = daemon.HybridUncappedIntelligence()
        midday_dt = datetime.datetime(2026, 11, 13, 14, 27, 0, tzinfo=daemon.MARKET_TZ)
        macro_dt = datetime.datetime(2026, 11, 13, 14, 29, 0, tzinfo=daemon.MARKET_TZ)
        reg_mid = intel.get_intraday_regime(midday_dt)
        reg_macro = intel.get_intraday_regime(macro_dt)
        self.assertTrue(reg_mid["allow_new_buys"])
        self.assertTrue(reg_mid["is_midday_sniper_window"])
        self.assertEqual(reg_mid["max_active_slots"], 2)
        # Durante lo shock dati macro USA (14:28-14:35 CET / 08:28-08:35 ET), blocco totale (0 nuovi acquisti)
        self.assertFalse(reg_macro["allow_new_buys"])

        ov_ok = {"allow_overnight_hold": True, "nasdaq_change_pct": 0.2, "sp500_change_pct": 0.2, "dax_change_pct": 0.2, "vix_fear_change_pct": -1.0, "vix_level": 16.0}
        # 1) Caso reale AMDd_EQ ore 14:27:55 (GETTEX 0s, Score 89.9, RVOL 2.40x, RSI 33.3, True Green Hook) -> APPROVATO!
        amd_1427 = {
            "ticker": "AMDd_EQ", "live_price_eur": 517.80, "price_feed_source": "GETTEX_STREAMING_0S",
            "vwap_dist_pct": 0.04, "has_fresh_intraday_feed": True, "rvol_ratio": 2.40,
            "quant_buy_score": 89.9, "rsi_5m": 33.3, "green_hook_confirmed": True, "breakout_5m": False,
            "atr_5m_volatility_pct": 0.294, "day_range_pct": 2.26, "kaufman_efficiency_ratio": 0.25,
            "strong_for_overnight": False,
        }
        self.assertTrue(intel.is_eligible_entry_candidate(amd_1427, reg_mid, ov_ok))
        # Bloccato durante la finestra shock macro 14:28-14:35
        self.assertFalse(intel.is_eligible_entry_candidate(amd_1427, reg_macro, ov_ok))
        # Bloccato al 100% se il feed cadesse in fallback su Yahoo 15m ritardato!
        amd_delayed = dict(amd_1427, price_feed_source="YAHOO_FALLBACK_15M")
        self.assertFalse(intel.is_eligible_entry_candidate(amd_delayed, reg_mid, ov_ok))

        # 2) Breakout 5m puro (GETTEX 0s, Score 84.5, RVOL 2.50x, breakout_5m=True, ER=0.52, VWAP +0.22%) -> APPROVATO!
        brk_mid = {
            "ticker": "NVDd_EQ", "live_price_eur": 153.50, "price_feed_source": "GETTEX_STREAMING_0S",
            "vwap_dist_pct": 0.22, "has_fresh_intraday_feed": True, "rvol_ratio": 2.50,
            "quant_buy_score": 84.5, "rsi_5m": 58.0, "green_hook_confirmed": True, "breakout_5m": True,
            "atr_5m_volatility_pct": 0.28, "day_range_pct": 2.40, "kaufman_efficiency_ratio": 0.52,
            "strong_for_overnight": True,
        }
        self.assertTrue(intel.is_eligible_entry_candidate(brk_mid, reg_mid, ov_ok))
        # Senza breakout_5m a mezzogiorno (con RSI > 38) -> BLOCCATO!
        no_brk_mid = dict(brk_mid, breakout_5m=False)
        self.assertFalse(intel.is_eligible_entry_candidate(no_brk_mid, reg_mid, ov_ok))

    def test_24_anti_dead_cat_micro_tick_sub_vwap_downtrend_and_fresh_rotation_scan(self):
        """Invariante #24: blocca dead-cat tick +0,02% post-candela rossa / rottura sotto VWAP (caso SAP 15:35) senza toccare gli Scudi, e forza scan 0s su rotazione."""
        real_dt = datetime.datetime
        mkt_dt = real_dt(2026, 11, 13, 15, 35, 50, tzinfo=daemon.MARKET_TZ)
        now_epoch = mkt_dt.timestamp()
        last_yahoo_bucket = int(real_dt(2026, 11, 13, 15, 20, 0, tzinfo=daemon.MARKET_TZ).timestamp())
        base_ts = last_yahoo_bucket - 19 * 300
        # Discesa progressiva da 214.55 -> 213.65 su Yahoo + candela 15:30 rossa pesante (214.30 -> 213.05)
        closes_sap = [
            214.2, 214.3, 214.5, 214.45, 214.55, 214.3, 214.05, 213.9, 213.8, 213.55,
            213.65, 213.75, 213.65, 213.7, 213.65, 213.6, 213.65, 213.7, 213.65, 213.65,
        ]
        yahoo_sap = _make_yahoo_payload(closes_sap, vols=[5000.0] * 20, base_ts=base_ts)

        scanner = daemon.QuantMarketScanner()
        b_1525 = int(real_dt(2026, 11, 13, 15, 25, 0, tzinfo=daemon.MARKET_TZ).timestamp())
        b_1530 = int(real_dt(2026, 11, 13, 15, 30, 0, tzinfo=daemon.MARKET_TZ).timestamp())
        scanner.realtime_5m_bars["SAPd_EQ"] = {
            b_1525: {"open": 213.65, "high": 213.80, "low": 213.60, "close": 213.75},
            b_1530: {"open": 214.30, "high": 214.45, "low": 213.05, "close": 213.05},
        }
        # Alle 15:35:50 la nuova candela 15:35 fa solo un micro-tick +0.05 EUR (213.05 -> 213.10) sotto VWAP:
        gx_dead_cat = json.dumps({
            "data": [
                {"s": "GETTEX:SAP", "d": [213.10, 213.05, 213.12, 213.05, 213.10, "streaming"]},
            ]
        }).encode("utf-8")

        with patch("datetime.datetime") as mock_dt, patch("time.time", return_value=now_epoch):
            mock_dt.now.side_effect = lambda tz=None: mkt_dt.astimezone(tz) if tz else mkt_dt.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(gx_dead_cat)):
                scanner.refresh_gettex_live_quotes(force=True)
            with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(yahoo_sap)):
                m_sap_dead = scanner.fetch_5m_metrics("SAPd_EQ")

        # ISOLAMENTO SCUDI vs INGRESSO:
        # 1) green_hook_confirmed resta True (zero alterazione degli Scudi 1A/1B/Airbag sulle posizioni già aperte!)
        self.assertTrue(m_sap_dead["green_hook_confirmed"])
        # 2) entry_hook_confirmed è False e quant_buy_score == 0.0 (zero falsi ingressi su micro-tick / rottura sotto VWAP!)
        self.assertFalse(m_sap_dead["entry_hook_confirmed"])
        self.assertEqual(m_sap_dead["quant_buy_score"], 0.0)

        # Verifica rotazione 4 -> 3 a metà ciclo: DEVE forzare scan_all(force=True) prima del BUY!
        class _RotationBroker:
            def __init__(self):
                self.positions = [
                    {"ticker": "MRKd_EQ", "quantity": 0.16, "averagePrice": 150.0, "currentPrice": 148.5, "ppl": -0.24},
                    {"ticker": "ADYENa_EQ", "quantity": 0.03, "averagePrice": 860.0, "currentPrice": 862.0, "ppl": 0.06},
                    {"ticker": "PRXa_EQ", "quantity": 0.70, "averagePrice": 35.5, "currentPrice": 35.6, "ppl": 0.07},
                    {"ticker": "MUV2d_EQ", "quantity": 0.04, "averagePrice": 592.0, "currentPrice": 593.0, "ppl": 0.04},
                ]
                self.limit_buys = []

            def get_open_positions(self):
                return list(self.positions)

            def get_pending_orders(self):
                return []

            def get_account_cash(self):
                return {"result": 0.0, "free": 25.5}

            def place_market_order(self, ticker: str, quantity: float):
                if quantity < 0:
                    self.positions = [p for p in self.positions if p["ticker"] != ticker]
                return {"id": "SELL_ROT"}

            def place_limit_order(self, ticker: str, quantity: float, limit_price: float, time_validity: str = "DAY"):
                self.limit_buys.append(ticker)
                self.positions.append({"ticker": ticker, "quantity": quantity, "averagePrice": limit_price, "currentPrice": limit_price, "ppl": 0.0})
                return {"id": "BUY_ROT"}

            def cancel_order(self, order_id):
                return None

        rot_broker = _RotationBroker()
        bot = daemon.Trading212AutonomousBot(client=rot_broker, total_budget_eur=100.0, cartridges=4, annual_target_pct=0.30)
        bot.tax_tracker = ItalianTaxTracker730(filepath=self._tmp_tax_path)
        for p_init in rot_broker.positions:
            bot.tax_tracker.record_buy(p_init["ticker"], p_init["quantity"], p_init["averagePrice"])
        bot.tax_tracker.data["lotti_aperti_lifo"]["MRKd_EQ"][0]["timestamp"] = "2026-11-13T15:15:00"
        bot.tax_tracker.save()
        intel = daemon.HybridUncappedIntelligence()
        intel.prev_open_snapshot.clear()
        intel.position_open_time["MRKd_EQ"] = now_epoch - 1200.0  # Aperta da 20m a -1.00% -> scatta Airbag!
        rot_scanner = daemon.QuantMarketScanner()
        scan_force_flags = []

        def _fake_scan_all(**kwargs):
            f_flag = bool(kwargs.get("force", False))
            scan_force_flags.append(f_flag)
            # Alla prima scansione (stantia, force=False) SAP aveva erroneamente score 87;
            # alla scansione fresca 0s post-vendita (force=True) SAP è crollata a 0 e vince EOANd_EQ (78.0)!
            sap_sc = 0.0 if f_flag else 87.0
            sap_eh = False if f_flag else True
            return {
                "MRKd_EQ": {"ticker": "MRKd_EQ", "name": "Merck", "squad": "SQUADRA_1_CECCHINO_GIORNALIERO", "sector": "PHARMA_BIOTECH", "live_price_eur": 148.5, "rsi_5m": 32.0, "vwap_dist_pct": -0.40, "atr_5m_volatility_pct": 0.15, "day_range_pct": 1.6, "rvol_ratio": 1.2, "quant_buy_score": 0.0, "green_hook_confirmed": False, "entry_hook_confirmed": False, "strong_for_overnight": False, "has_fresh_intraday_feed": True, "fase_onda_sinusoidale": "COLTELLO_IN_CADUTA_ATTENDERE_UNCINO_VERDE"},
                "SAPd_EQ": {"ticker": "SAPd_EQ", "name": "SAP", "squad": "SQUADRA_2_CAVALCA_ONDA", "sector": "SOFTWARE_CLOUD", "live_price_eur": 212.7, "rsi_5m": 31.0, "vwap_dist_pct": -0.30, "atr_5m_volatility_pct": 0.20, "day_range_pct": 1.5, "rvol_ratio": 1.8, "quant_buy_score": sap_sc, "green_hook_confirmed": False, "entry_hook_confirmed": sap_eh, "strong_for_overnight": False, "has_fresh_intraday_feed": True, "fase_onda_sinusoidale": "COLTELLO_IN_CADUTA_ATTENDERE_UNCINO_VERDE"},
                "EOANd_EQ": {"ticker": "EOANd_EQ", "name": "E.ON", "squad": "SQUADRA_1_CECCHINO_GIORNALIERO", "sector": "UTILITIES_RETI_ELETTRICHE", "live_price_eur": 19.50, "rsi_5m": 58.0, "vwap_dist_pct": 0.22, "atr_5m_volatility_pct": 0.15, "day_range_pct": 1.6, "rvol_ratio": 1.3, "quant_buy_score": 78.0, "green_hook_confirmed": True, "entry_hook_confirmed": True, "strong_for_overnight": True, "has_fresh_intraday_feed": True, "fase_onda_sinusoidale": "SUPER_TREND_VERO_POSITIVO_BREAKOUT"},
            }

        rot_scanner.scan_all = _fake_scan_all

        class _DummyRadar24:
            def evaluate_overnight_wave(self):
                return {"verdict": "OK", "allow_overnight_hold": True, "nasdaq_change_pct": 0.2, "sp500_change_pct": 0.2, "dax_change_pct": 0.2, "vix_fear_change_pct": -1.0, "vix_level": 16.0}

        with patch.object(daemon, "LIMIT_FILL_POLL_SEC", 0.0), patch("datetime.datetime") as mock_dt, patch("time.time", return_value=now_epoch):
            mock_dt.now.side_effect = lambda tz=None: mkt_dt.astimezone(tz) if tz else mkt_dt.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            mock_dt.fromisoformat.side_effect = real_dt.fromisoformat
            daemon.run_cycle(bot, intel, rot_scanner, _DummyRadar24(), 1)

        self.assertEqual(scan_force_flags, [False, True])
        self.assertEqual(rot_broker.limit_buys, ["EOANd_EQ"])

    def test_25_clean_rvol_no_v0_667x_inflation_no_1300_auction_and_zero_synthetic_bridge(self):
        """Invariante #25: RVOL immune a barra Yahoo v=0 (zero 6,67x), asta XETRA 13:00 esclusa, mediana anti-odd-lot e zero barre sintetiche."""
        real_dt = datetime.datetime
        # 1) Barra finale Yahoo appena aperta da 40s con volume=0 + asta XETRA 13:00 da 380.000 pezzi + odd-lot da 2 pezzi
        b_1300 = int(real_dt(2026, 11, 13, 13, 0, 0, tzinfo=daemon.MARKET_TZ).timestamp())
        base_ts = b_1300 - 10 * 300
        ts_list = [base_ts + i * 300 for i in range(19)] + [base_ts + 19 * 300 + 40]
        closes = [100.0 + i * 0.04 for i in range(20)]
        vols = [10000.0] * 20
        vols[10] = 380000.0  # Asta XETRA 13:00 (Mittagsauktion 38x) -> deve essere esclusa!
        vols[12] = 2.0       # Odd-lot anomalo -> med_anchor evita crollo del denominatore!
        vols[19] = 0.0       # Ultima barra Yahoo parziale con volume=0 -> NON deve moltiplicare vols[18] per 6.67x!
        raw_y = json.dumps({
            "chart": {
                "result": [{
                    "meta": {"regularMarketPrice": closes[-1]},
                    "timestamp": ts_list,
                    "indicators": {"quote": [{
                        "open": closes,
                        "close": closes,
                        "high": [c * 1.0015 for c in closes],
                        "low": [c * 0.9985 for c in closes],
                        "volume": vols,
                    }]},
                }]
            }
        }).encode("utf-8")

        mkt_dt = real_dt(2026, 11, 13, 14, 15, 20, tzinfo=daemon.MARKET_TZ)
        now_epoch = mkt_dt.timestamp()
        scanner = daemon.QuantMarketScanner(cache_path=self._tmp_scan_cache)
        gx_payload = json.dumps({
            "data": [
                {"s": "GETTEX:SAP", "d": [210.42, 210.80, 210.90, 210.35, 210.42, "streaming"]},
            ]
        }).encode("utf-8")

        with patch("datetime.datetime") as mock_dt, patch("time.time", return_value=now_epoch):
            mock_dt.now.side_effect = lambda tz=None: mkt_dt.astimezone(tz) if tz else mkt_dt.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            # Posizione aperta su T212 a metà candela (210.40) mentre il vero open :00 su GETTEX era 210.80 (candela rossa reale!)
            scanner.update_t212_live_price("SAPd_EQ", 210.40)
            with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(gx_payload)):
                scanner.refresh_gettex_live_quotes(force=True)
            with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(raw_y)):
                m = scanner.fetch_5m_metrics("SAPd_EQ")

            # RVOL deve essere ~1.0x..1.2x (MAI 6.67x e MAI contaminato dai 380k delle 13:00!)
            self.assertGreaterEqual(m["rvol_ratio"], 0.95)
            self.assertLessEqual(m["rvol_ratio"], 1.35)
            # Zero candele sintetiche interpolate: solo i 20 bucket Yahoo + 1 bucket reale 14:15 (= 21 barre esatte)
            b_now = int(now_epoch // 300) * 300
            self.assertEqual(scanner.realtime_5m_bars["SAPd_EQ"][b_now]["open"], 210.80)
            self.assertEqual(scanner.realtime_5m_bars["SAPd_EQ"][b_now]["close"], 210.40)  # Priorità 0ms T212 preservata!
            self.assertFalse(m["green_hook_confirmed"])  # Riconosce che 210.40 < vero open 210.80!

            # Persistenza coda real-time 0s in trading212_state.json per nuove VM Cloud
            with open(self._tmp_bot_state, "w", encoding="utf-8") as f_st:
                json.dump({
                    "timestamp": "2026-11-13T14:15:20",
                    "realtime_5m_tail": scanner.export_realtime_tail(max_buckets=8),
                }, f_st)
            fresh_vm_scanner = daemon.QuantMarketScanner(cache_path="/tmp/test_v11_nonexistent_vm_cache.json")
            self.assertIn(b_now, fresh_vm_scanner.realtime_5m_bars["SAPd_EQ"])
            self.assertEqual(fresh_vm_scanner.realtime_5m_bars["SAPd_EQ"][b_now]["open"], 210.80)

    def test_26_atr_proportional_vwap_physics_snail_gate_valley_hook_and_loser_reentry(self):
        """Invariante #26: blocca lumache ATR<0,115% e tetti VWAP sproporzionati (caso E.ON 15:50), ripristina Valley Hook RSI 24..32 e filtra rientri perdenti/rumorosi."""
        daemon.discover_and_verify_eur_giants(None)
        intel = daemon.HybridUncappedIntelligence()
        reg_pm = {"allow_new_buys": True, "is_midday_sniper_window": False, "us_market_live": True}
        ov_ok = {"allow_overnight_hold": True, "nasdaq_change_pct": 0.1, "sp500_change_pct": 0.1, "dax_change_pct": 0.1, "vix_fear_change_pct": -0.5, "vix_level": 16.0}

        # 1) Caso reale EOANd_EQ ore 15:50: ATR 0.098% (< 0.115%), VWAP +0.42% (+4.3x ATR), day_range 1.66% -> BLOCCATO!
        eoan_snail = {
            "ticker": "EOANd_EQ", "live_price_eur": 19.53, "price_feed_source": "GETTEX_STREAMING_0S",
            "vwap_dist_pct": 0.42, "has_fresh_intraday_feed": True, "rvol_ratio": 1.40,
            "quant_buy_score": 81.4, "rsi_5m": 58.6, "green_hook_confirmed": True, "entry_hook_confirmed": True,
            "atr_5m_volatility_pct": 0.098, "day_range_pct": 1.66, "kaufman_efficiency_ratio": 0.56,
            "had_loss_today": False, "strong_for_overnight": True,
        }
        self.assertFalse(intel.is_eligible_entry_candidate(eoan_snail, reg_pm, ov_ok))

        # 2) Caso APCd_EQ ore 16:58: ATR 0.177%, VWAP +0.53% (> max_vwap_entry 0.50%) -> BLOCCATO!
        apc_stretched = dict(eoan_snail, ticker="APCd_EQ", atr_5m_volatility_pct=0.177, vwap_dist_pct=0.53)
        self.assertFalse(intel.is_eligible_entry_candidate(apc_stretched, reg_pm, ov_ok))

        # 3) Caso E.ON sano in vera spinta: ATR 0.145%, VWAP +0.18% (<= 3.5*0.145 = 0.50%) -> APPROVATO!
        eoan_healthy = dict(eoan_snail, atr_5m_volatility_pct=0.145, vwap_dist_pct=0.18)
        self.assertTrue(intel.is_eligible_entry_candidate(eoan_healthy, reg_pm, ov_ok))

        # 4) Caso reale SAPd_EQ ore 16:42: aveva già perso oggi (had_loss_today=True) e tenta rientro con ER=0.04 (<0.30) -> BLOCCATO!
        sap_choppy_reentry = dict(eoan_healthy, ticker="SAPd_EQ", atr_5m_volatility_pct=0.29, had_loss_today=True, kaufman_efficiency_ratio=0.04, vwap_dist_pct=0.12)
        self.assertFalse(intel.is_eligible_entry_candidate(sap_choppy_reentry, reg_pm, ov_ok))
        sap_clean_reclaim = dict(sap_choppy_reentry, kaufman_efficiency_ratio=0.38, vwap_dist_pct=0.12)
        self.assertTrue(intel.is_eligible_entry_candidate(sap_clean_reclaim, reg_pm, ov_ok))

        # 5) Valley Hook ipervenduto genuino (RSI ~ 27.5 in [24, 64] sul supporto VWAP senza crollo 30m) -> Score > 75!
        scanner = daemon.QuantMarketScanner()
        valley_closes = [
            100.0, 100.05, 100.1, 100.12, 100.1, 100.08, 100.05, 100.0, 99.95, 99.90,
            99.85, 99.82, 99.80, 99.78, 99.76, 99.74, 99.72, 99.70, 99.68, 99.84,
        ]
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(_make_yahoo_payload(valley_closes))):
            m_val = scanner.fetch_5m_metrics("SAPd_EQ")
        self.assertLess(m_val["rsi_5m"], 32.0)
        self.assertGreaterEqual(m_val["rsi_5m"], 24.0)
        self.assertGreater(m_val["quant_buy_score"], 75.0)

    def test_27_v114_signed_er_climax_retention_breadth_and_same_cycle_rotation_cash(self):
        """Invariante #27: Signed Kaufman ER contro crolli rettilinei, Climax Retention C0, Breadth < 15%, Rotazione 4->3->4 istantanea e Cache Radar."""
        daemon.discover_and_verify_eur_giants(None)
        scanner = daemon.QuantMarketScanner()

        # 1) Signed Kaufman ER: un crollo rettilineo a 50m (RSI > 34, signed_er <= -0.35) NON riceve il bonus +12pt in score_pullback!
        bear_crash_closes = [
            100.80, 100.75, 100.70, 100.65, 100.60, 100.55, 100.50, 100.45, 100.40,
            100.38, 100.34, 100.30, 100.26, 100.22, 100.18, 100.14, 100.10, 100.06, 100.02, 100.14,
        ]
        # Stesso RSI/VWAP simile ma onda laterale/rialzista (signed_er > 0) -> conserva il bonus direzionale ER
        bull_pullback_closes = [
            99.85, 99.90, 99.95, 100.00, 100.05, 100.10, 100.15, 100.20, 100.25,
            100.02, 100.08, 100.14, 100.20, 100.16, 100.12, 100.18, 100.14, 100.10, 100.08, 100.22,
        ]
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(_make_yahoo_payload(bear_crash_closes))):
            m_bear = scanner.fetch_5m_metrics("SAPd_EQ")
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(_make_yahoo_payload(bull_pullback_closes))):
            m_bull = scanner.fetch_5m_metrics("SAPd_EQ")
        self.assertLessEqual(m_bear["signed_kaufman_er"], -0.35)
        self.assertGreater(m_bear["kaufman_efficiency_ratio"], 0.45)
        self.assertGreater(m_bull["signed_kaufman_er"], 0.0)
        self.assertGreater(m_bull["quant_buy_score"], m_bear["quant_buy_score"])

        # 2) Climax Profit Retention C0-continua e strettamente monotona in compute_profit_protection_floor:
        intel = daemon.HybridUncappedIntelligence()
        s_act, s_pull, atr_r = 0.0080, 0.0020, 0.0020
        st_edge, fl_edge = intel.compute_profit_protection_floor(s_act, s_act, s_pull, atr_r, False)
        self.assertEqual(st_edge, "UNCAPPED_SHIELD_2")
        # Continuità esatta C0 sul bordo peak == shield_act (0.0080 - 0.0020 = 0.0060)
        self.assertAlmostEqual(fl_edge, 0.0060, places=4)
        # Sul climax parabolico (peak = 0.0180 >= 2.2x shield_act), il pullback si stringe del 22% (0.0020 -> 0.0016),
        # trattenendo +0.04% extra rispetto al pullback fisso (0.0164 vs 0.0160)!
        _, fl_climax = intel.compute_profit_protection_floor(0.0180, s_act, s_pull, atr_r, False)
        self.assertGreater(fl_climax, round(0.0180 - s_pull, 4))
        self.assertAlmostEqual(fl_climax, 0.0164, places=4)

        # 3) Ampiezza Trasversale di Mercato (< 15% sopra VWAP -> capitolazione sistemica):
        reg_open = {"allow_new_buys": True, "is_midday_sniper_window": False, "us_market_live": True}
        ov_ok = {"allow_overnight_hold": True, "nasdaq_change_pct": 0.1, "sp500_change_pct": 0.1, "dax_change_pct": 0.1, "vix_fear_change_pct": 0.0, "vix_level": 16.0}
        sub_vwap_laggard = {
            "ticker": "SAPd_EQ", "live_price_eur": 210.0, "price_feed_source": "GETTEX_STREAMING_0S",
            "vwap_dist_pct": -0.08, "has_fresh_intraday_feed": True, "rvol_ratio": 1.30,
            "quant_buy_score": 76.0, "rsi_5m": 45.0, "green_hook_confirmed": True, "entry_hook_confirmed": True,
            "atr_5m_volatility_pct": 0.20, "day_range_pct": 1.80, "kaufman_efficiency_ratio": 0.40,
            "had_loss_today": False, "strong_for_overnight": False,
        }
        rs_leader = dict(sub_vwap_laggard, ticker="NVDd_EQ", vwap_dist_pct=0.14, strong_for_overnight=True)
        deep_washout = dict(sub_vwap_laggard, ticker="ASMLa_EQ", vwap_dist_pct=-0.22, rsi_5m=28.5)
        # In capitolazione (breadth = 0.10 < 0.15): il ritardatario sotto VWAP è bloccato, il Leader >= VWAP e il washout RSI<=30 passano!
        self.assertFalse(intel.is_eligible_entry_candidate(sub_vwap_laggard, reg_open, ov_ok, market_breadth_above_vwap=0.10))
        self.assertTrue(intel.is_eligible_entry_candidate(rs_leader, reg_open, ov_ok, market_breadth_above_vwap=0.10))
        self.assertTrue(intel.is_eligible_entry_candidate(deep_washout, reg_open, ov_ok, market_breadth_above_vwap=0.10))
        # In mercato normale (breadth = 0.50): anche il pullback sano -0.08% passa regolarmente
        self.assertTrue(intel.is_eligible_entry_candidate(sub_vwap_laggard, reg_open, ov_ok, market_breadth_above_vwap=0.50))

        # 4) Sblocco Istantaneo Liquidità di Rotazione 4/4 -> 3/4 -> 4/4 nello stesso ciclo anche con cassa iniziale 0.64 EUR e lag REST!
        class _TightCashRotationBroker:
            def __init__(self):
                self.positions = [
                    {"ticker": "MRKd_EQ", "quantity": 0.1667, "averagePrice": 150.0, "currentPrice": 148.5, "ppl": -0.25},
                    {"ticker": "ADYENa_EQ", "quantity": 0.0290, "averagePrice": 860.0, "currentPrice": 862.0, "ppl": 0.06},
                    {"ticker": "PRXa_EQ", "quantity": 0.7000, "averagePrice": 35.5, "currentPrice": 35.6, "ppl": 0.07},
                    {"ticker": "MUV2d_EQ", "quantity": 0.0420, "averagePrice": 592.0, "currentPrice": 593.0, "ppl": 0.04},
                ]
                self.limit_buys = []

            def get_open_positions(self):
                return list(self.positions)

            def get_pending_orders(self):
                return []

            def get_account_cash(self):
                # Simula conto da 100 EUR pieno (free=0.64 EUR) + lag eventual-consistency (<500ms) subito dopo il Market Sell!
                return {"result": 0.0, "free": 0.64}

            def place_market_order(self, ticker: str, quantity: float):
                if quantity < 0:
                    self.positions = [p for p in self.positions if p["ticker"] != ticker]
                return {"id": "SELL_TIGHT"}

            def place_limit_order(self, ticker: str, quantity: float, limit_price: float, time_validity: str = "DAY"):
                self.limit_buys.append((ticker, quantity, limit_price))
                self.positions.append({"ticker": ticker, "quantity": quantity, "averagePrice": limit_price, "currentPrice": limit_price, "ppl": 0.0})
                return {"id": "BUY_TIGHT"}

            def cancel_order(self, order_id):
                return None

        real_dt = datetime.datetime
        mkt_dt = real_dt(2026, 11, 13, 15, 45, 0, tzinfo=daemon.MARKET_TZ)
        now_epoch = mkt_dt.timestamp()
        tight_broker = _TightCashRotationBroker()
        bot = daemon.Trading212AutonomousBot(client=tight_broker, total_budget_eur=100.0, cartridges=4, annual_target_pct=0.30)
        bot.tax_tracker = ItalianTaxTracker730(filepath=self._tmp_tax_path)
        for p0 in tight_broker.positions:
            bot.tax_tracker.record_buy(p0["ticker"], p0["quantity"], p0["averagePrice"])
        bot.tax_tracker.save()
        intel_rot = daemon.HybridUncappedIntelligence()
        intel_rot.prev_open_snapshot.clear()
        intel_rot.position_open_time["MRKd_EQ"] = now_epoch - 1200.0  # 20m a -1.00% -> Airbag libera ~24.75 EUR!
        rot_scan = daemon.QuantMarketScanner()
        rot_scan.scan_all = lambda **kw: {
            "MRKd_EQ": {"ticker": "MRKd_EQ", "name": "Merck", "squad": "SQUADRA_1_CECCHINO_GIORNALIERO", "sector": "PHARMA_BIOTECH", "live_price_eur": 148.5, "rsi_5m": 32.0, "vwap_dist_pct": -0.40, "atr_5m_volatility_pct": 0.16, "day_range_pct": 1.6, "rvol_ratio": 1.2, "quant_buy_score": 0.0, "green_hook_confirmed": False, "entry_hook_confirmed": False, "strong_for_overnight": False, "has_fresh_intraday_feed": True, "fase_onda_sinusoidale": "COLTELLO_IN_CADUTA_ATTENDERE_UNCINO_VERDE"},
            "ASMLa_EQ": {"ticker": "ASMLa_EQ", "name": "ASML", "squad": "SQUADRA_2_CAVALCA_ONDA", "sector": "CHIP_LITOGRAFIA_WAFER", "live_price_eur": 720.0, "rsi_5m": 56.0, "vwap_dist_pct": 0.18, "atr_5m_volatility_pct": 0.24, "day_range_pct": 2.1, "rvol_ratio": 1.6, "quant_buy_score": 84.0, "green_hook_confirmed": True, "entry_hook_confirmed": True, "strong_for_overnight": True, "has_fresh_intraday_feed": True, "fase_onda_sinusoidale": "SUPER_TREND_VERO_POSITIVO_BREAKOUT"},
        }

        class _DummyRadar27:
            def evaluate_overnight_wave(self):
                return {"verdict": "OK", "allow_overnight_hold": True, "nasdaq_change_pct": 0.3, "sp500_change_pct": 0.2, "dax_change_pct": 0.2, "vix_fear_change_pct": -1.0, "vix_level": 15.5}

        with patch.object(daemon, "LIMIT_FILL_POLL_SEC", 0.0), patch("datetime.datetime") as mock_dt, patch("time.time", return_value=now_epoch):
            mock_dt.now.side_effect = lambda tz=None: mkt_dt.astimezone(tz) if tz else mkt_dt.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            mock_dt.fromisoformat.side_effect = real_dt.fromisoformat
            st_rot = daemon.run_cycle(bot, intel_rot, rot_scan, _DummyRadar27(), 1)

        self.assertEqual(len(tight_broker.limit_buys), 1)
        self.assertEqual(tight_broker.limit_buys[0][0], "ASMLa_EQ")
        self.assertEqual(st_rot["mode"], "INSTITUTIONAL_V11_5_LTS_ZERO_CEROTTI")

        # 5) Persistenza su disco di OvernightWaveRadar attraverso i riavvii batch Cloud:
        tmp_radar_cache = "/tmp/test_v114_radar_cache.json"
        if os.path.exists(tmp_radar_cache):
            os.remove(tmp_radar_cache)
        try:
            r1 = daemon.OvernightWaveRadar(cache_path=tmp_radar_cache)
            snap_map = {"%5EGSPC": (0.40, 5950.0, True), "%5EIXIC": (0.55, 19200.0, True), "%5EGDAXI": (0.30, 19300.0, True), "%5EVIX": (-2.0, 15.2, True)}
            with patch.object(r1, "_fetch_index_snapshot", side_effect=lambda s: snap_map[s]):
                v1 = r1.evaluate_overnight_wave(force=True)
            self.assertTrue(v1["allow_overnight_hold"])
            r2 = daemon.OvernightWaveRadar(cache_path=tmp_radar_cache)
            with patch.object(r2, "_fetch_index_snapshot", side_effect=AssertionError("Non deve rifare HTTP entro 120s!")):
                v2 = r2.evaluate_overnight_wave(force=False)
            self.assertEqual(v2["verdict"], v1["verdict"])
        finally:
            if os.path.exists(tmp_radar_cache):
                os.remove(tmp_radar_cache)

    def test_28_v115_scale_invariant_taper_bilateral_c0_shield_and_execution_purity(self):
        """Invariante #28: Taper VWAP scale-invariant su ATR, continuità C0 bilaterale + scudo senza buchi, retry 5m puro, eventual-consistency fill e guardia GETTEX :00."""
        real_dt = datetime.datetime
        mkt_dt = real_dt(2026, 11, 13, 10, 55, 6, tzinfo=daemon.MARKET_TZ)
        now_ts = mkt_dt.timestamp()
        bucket_now = int(now_ts // 300) * 300

        # 1) Taper VWAP Scale-Invariant proporzionale all'ATR 5m (ATR ~0.13%, esperimento controllato a parità esatta di RSI/ATR/ER):
        #    ultime 15 barre IDENTICHE (stesso RSI ~56, stesso ATR ~0.13%, stesso ER ~0.43), prime 8 barre mattutine diverse solo sul livello VWAP!
        sc_fresh = daemon.QuantMarketScanner()
        sc_stretched = daemon.QuantMarketScanner()
        base_ts = [bucket_now - (23 - i) * 300 for i in range(23)]
        tail_15 = [100.00, 99.96, 100.02, 99.98, 100.04, 99.99, 100.05, 100.01, 100.06, 100.02, 100.07, 100.03, 100.08, 100.06, 100.13]
        c_fresh = [100.02] * 8 + tail_15
        c_str = [99.10] * 8 + tail_15
        h_fresh = [c + 0.065 for c in c_fresh]
        l_fresh = [c - 0.065 for c in c_fresh]
        h_str = [c + 0.065 for c in c_str]
        l_str = [c - 0.065 for c in c_str]
        vols_23 = [4000.0] * 23
        raw_fresh = json.dumps({"chart": {"result": [{"meta": {"regularMarketPrice": c_fresh[-1]}, "timestamp": base_ts, "indicators": {"quote": [{"open": [c - 0.03 for c in c_fresh], "close": c_fresh, "high": h_fresh, "low": l_fresh, "volume": vols_23}]}}]}}).encode("utf-8")
        raw_str = json.dumps({"chart": {"result": [{"meta": {"regularMarketPrice": c_str[-1]}, "timestamp": base_ts, "indicators": {"quote": [{"open": [c - 0.03 for c in c_str], "close": c_str, "high": h_str, "low": l_str, "volume": vols_23}]}}]}}).encode("utf-8")
        sc_fresh.has_gettex_realtime["SAPd_EQ"] = True
        sc_fresh.last_gettex_ts["SAPd_EQ"] = now_ts
        sc_fresh.live_prices["SAPd_EQ"] = c_fresh[-1]
        sc_stretched.has_gettex_realtime["SAPd_EQ"] = True
        sc_stretched.last_gettex_ts["SAPd_EQ"] = now_ts
        sc_stretched.live_prices["SAPd_EQ"] = c_str[-1]
        with patch("datetime.datetime") as mock_dt, patch("time.time", return_value=now_ts):
            mock_dt.now.side_effect = lambda tz=None: mkt_dt.astimezone(tz) if tz else mkt_dt.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            mock_dt.fromisoformat.side_effect = real_dt.fromisoformat
            with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(raw_fresh)):
                m_fresh = sc_fresh.fetch_5m_metrics("SAPd_EQ")
            with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(raw_str)):
                m_str = sc_stretched.fetch_5m_metrics("SAPd_EQ")
        self.assertGreater(m_str["vwap_dist_pct"], 0.30)
        self.assertLess(m_str["vwap_dist_pct"], 0.48)
        self.assertGreater(m_fresh["quant_buy_score"], m_str["quant_buy_score"] + 2.5)

        # 2) Continuità Bilaterale C0 Esatta su peak == shield_act + Monotonicità Universale + Flash-Gap < -0.05% su UNCAPPED_SHIELD_2:
        intel = daemon.HybridUncappedIntelligence()
        for shield_act, shield_pull, atr_raw in [
            (0.0085, 0.0020, 0.0020),
            (0.0112, 0.0028, 0.0026),
            (0.0062, 0.0028, 0.0016),  # Caso critico: shield_act - shield_pull = 0.0034 < 0.0040!
            (0.0060, 0.0045, 0.0018),  # Caso estremo: shield_act - shield_pull < breakeven_floor!
        ]:
            prev_fl = -1.0
            for step in range(35, 240):
                pk = round(step * 0.0001, 4)
                _, fl = intel.compute_profit_protection_floor(pk, shield_act, shield_pull, atr_raw, False)
                if fl is not None:
                    self.assertGreaterEqual(fl, prev_fl, f"Non monotona per ({shield_act}, {shield_pull}) a peak={pk}")
                    prev_fl = fl
            _, fl_left = intel.compute_profit_protection_floor(round(shield_act - 0.0001, 4), shield_act, shield_pull, atr_raw, False)
            _, fl_at = intel.compute_profit_protection_floor(shield_act, shield_act, shield_pull, atr_raw, False)
            self.assertAlmostEqual(fl_left, fl_at, delta=0.0003)

        # Flash-gap violento da picco +0.90% direttamente a -0.14% (< -0.05%) con UNCAPPED_SHIELD_2 armato -> DEVE incassare/uscire subito!
        intel.peak_pnl_pct["SAPd_EQ"] = 0.0090
        reg_open = {"is_morning_gap_harvest": False, "is_pre_close_window": False, "is_friday_pre_weekend": False}
        m_shield = {"atr_5m_volatility_pct": 0.18, "elastic_shield_act_raw": 0.0068, "elastic_shield_pull_raw": 0.0070, "green_hook_confirmed": False, "vwap_dist_pct": -0.15, "rsi_5m": 40.0}
        exit_flash = intel.evaluate_uncapped_exit("SAPd_EQ", -0.0014, reg_open, 0.0, {}, m_shield, 0.0, False)
        self.assertIsNotNone(exit_flash)
        self.assertIn("SCUDO MOBILE", exit_flash)

        # 3) Cooldown Retry 5m Puro: uno stop-loss scaduto (>65m fa) seguito da ordine LIMIT annullato su spike
        #    NON deve riattivare 50 minuti di ban, né sync_from_tax_data deve sovrascrivere una vendita verde recente (<15m)!
        intel_cd = daemon.HybridUncappedIntelligence()
        today_iso = mkt_dt.date().isoformat()
        tx_cd = {
            "v11_clean_epoch_ts": daemon.V11_CLEAN_EPOCH_TS,
            "operazioni_chiuse": [
                {"ticker": "EOANd_EQ", "timestamp": real_dt.fromtimestamp(now_ts - 4000.0, tz=daemon.MARKET_TZ).isoformat(timespec="seconds"), "sell_price_eur": 12.80, "risultato_fiscale_eur": -0.18},
                {"ticker": "SAPd_EQ", "timestamp": real_dt.fromtimestamp(now_ts - 180.0, tz=daemon.MARKET_TZ).isoformat(timespec="seconds"), "sell_price_eur": 200.60, "risultato_fiscale_eur": 0.25},
            ],
        }
        with patch("datetime.datetime") as mock_dt, patch("time.time", return_value=now_ts):
            mock_dt.now.side_effect = lambda tz=None: mkt_dt.astimezone(tz) if tz else mkt_dt.replace(tzinfo=None)
            mock_dt.fromisoformat.side_effect = real_dt.fromisoformat
            intel_cd.sync_from_tax_data(tx_cd)
            self.assertTrue(intel_cd.can_buy_ticker("EOANd_EQ", 13.00))  # 66.7m > 60m -> scaduto!
            intel_cd.register_buy_retry("EOANd_EQ", 13.00)
            intel_cd.register_buy_retry("SAPd_EQ", 200.00)  # Retry dopo dip -0.30% da 200.60
            intel_cd.sync_from_tax_data(tx_cd)
            # Subito dopo il retry, entrambi sono in micro-cooldown a parità di prezzo (zero loop 6s su SAPd_EQ!):
            self.assertFalse(intel_cd.can_buy_ticker("EOANd_EQ", 13.00))
            self.assertFalse(intel_cd.can_buy_ticker("SAPd_EQ", 200.00))
        # Dopo 5m + 5s (305s), EOANd_EQ torna acquistabile (NON bloccato per altri 50 minuti!):
        with patch("time.time", return_value=now_ts + 305.0):
            self.assertTrue(intel_cd.can_buy_ticker("EOANd_EQ", 13.00))

        # 4) Eventual-Consistency Fill Re-Check + Persistenza 4 decimali peak_pnl_pct + Guardia GETTEX barra congelata :00:
        sc_gx = daemon.QuantMarketScanner()
        prev_b5 = bucket_now - 300
        sc_gx.realtime_5m_bars["IFXd_EQ"] = {prev_b5: {"open": 30.00, "high": 30.40, "low": 29.95, "close": 30.35, "has_true_open": True}}
        gx_payload = json.dumps({"data": [{"s": "GETTEX:IFX", "d": [30.35, 30.00, 30.40, 29.95, 100, "streaming"]}]}).encode("utf-8")
        with patch("datetime.datetime") as mock_dt, patch("time.time", return_value=now_ts), patch("urllib.request.urlopen", return_value=_FakeHTTPResp(gx_payload)):
            mock_dt.now.side_effect = lambda tz=None: mkt_dt.astimezone(tz) if tz else mkt_dt.replace(tzinfo=None)
            sc_gx.refresh_gettex_live_quotes(force=True)
        # Poiché GETTEX non ha ancora scambiato nel nuovo bucket (stessa quadrupla o/h/l/c della candela precedente), non clona il corpo verde passato!
        self.assertEqual(sc_gx.realtime_5m_bars["IFXd_EQ"][bucket_now]["open"], 30.35)
        self.assertFalse(sc_gx.realtime_5m_bars["IFXd_EQ"][bucket_now]["has_true_open"])

        class _EventualConsistencyBroker:
            def __init__(self):
                self.pos_calls = 0
                self.filled = False

            def get_open_positions(self):
                self.pos_calls += 1
                # Al primo check dopo place_limit_order simula 250ms di lag eventual-consistency, al re-check espone il fill reale!
                if self.filled and self.pos_calls >= 4:
                    return [{"ticker": "SAPd_EQ", "quantity": 0.1200, "averagePrice": 208.00, "currentPrice": 208.00, "ppl": 0.0}]
                return []

            def get_pending_orders(self):
                return []

            def get_account_cash(self):
                return {"result": 0.0, "free": 100.0}

            def place_limit_order(self, ticker, quantity, limit_price, time_validity="DAY"):
                self.filled = True
                return {"id": "ORD_LAG_OK"}

            def cancel_order(self, order_id):
                raise AssertionError("Non deve cancellare un ordine già eseguito sul book!")

        ec_broker = _EventualConsistencyBroker()
        bot_ec = daemon.Trading212AutonomousBot(client=ec_broker, total_budget_eur=100.0, cartridges=4, annual_target_pct=0.30)
        bot_ec.tax_tracker = ItalianTaxTracker730(filepath=self._tmp_tax_path)
        intel_ec = daemon.HybridUncappedIntelligence()
        intel_ec.prev_open_snapshot.clear()
        sc_ec = daemon.QuantMarketScanner()
        sc_ec.scan_all = lambda **kw: {
            "SAPd_EQ": {"ticker": "SAPd_EQ", "name": "SAP", "squad": "SQUADRA_2_CAVALCA_ONDA", "sector": "SOFTWARE_CLOUD", "live_price_eur": 208.0, "rsi_5m": 54.0, "vwap_dist_pct": 0.10, "atr_5m_volatility_pct": 0.20, "day_range_pct": 1.6, "rvol_ratio": 1.4, "quant_buy_score": 82.0, "green_hook_confirmed": True, "entry_hook_confirmed": True, "strong_for_overnight": True, "has_fresh_intraday_feed": True, "fase_onda_sinusoidale": "SUPER_TREND_VERO_POSITIVO_BREAKOUT"},
        }

        class _DummyRadar28:
            def evaluate_overnight_wave(self):
                return {"verdict": "OK", "allow_overnight_hold": True, "nasdaq_change_pct": 0.3, "sp500_change_pct": 0.2, "dax_change_pct": 0.2, "vix_fear_change_pct": -1.0, "vix_level": 15.5}

        with patch.object(daemon, "LIMIT_FILL_POLL_SEC", 0.0), patch("datetime.datetime") as mock_dt, patch("time.time", return_value=now_ts):
            mock_dt.now.side_effect = lambda tz=None: mkt_dt.astimezone(tz) if tz else mkt_dt.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            mock_dt.fromisoformat.side_effect = real_dt.fromisoformat
            st_ec = daemon.run_cycle(bot_ec, intel_ec, sc_ec, _DummyRadar28(), 1)
        self.assertEqual(len(st_ec["cartucce_4x25_eur"]), 1)
        self.assertEqual(st_ec["cartucce_4x25_eur"][0]["status"], "APPENA_ACQUISTATA_V11_5_LIMIT_PROTETTO")
        self.assertIn("SAPd_EQ", bot_ec.tax_tracker.data.get("lotti_aperti_lifo", {}))


if __name__ == "__main__":
    unittest.main()
