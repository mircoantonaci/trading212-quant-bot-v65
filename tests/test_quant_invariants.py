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
        self._tmp_lt_path = "/tmp/test_v11_hermetic_longterm_1000e.json"
        for p in (self._tmp_bot_state, self._tmp_scan_cache, self._tmp_tax_path, self._tmp_lt_path):
            if os.path.exists(p):
                os.remove(p)
        self._p_state = patch.object(daemon, "BOT_STATE_PATH", self._tmp_bot_state)
        self._p_cache = patch.object(daemon, "SCANNER_CACHE_PATH", self._tmp_scan_cache)
        self._p_tax = patch.object(daemon, "TAX_TRACKER_PATH", self._tmp_tax_path)
        self._p_lt = patch.object(daemon, "LONGTERM_VAULT_STATE_PATH", self._tmp_lt_path)
        self._p_state.start()
        self._p_cache.start()
        self._p_tax.start()
        self._p_lt.start()

    def tearDown(self):
        self._p_lt.stop()
        self._p_tax.stop()
        self._p_cache.stop()
        self._p_state.stop()
        for p in (self._tmp_bot_state, self._tmp_scan_cache, self._tmp_tax_path, self._tmp_lt_path):
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
        """Invariante #9: Airbag Anti-Rumore V11.6 attivo <= -1.75% e vecchi stop pre-V11 ignorati al 100%."""
        intel = daemon.HybridUncappedIntelligence()
        intel.peak_pnl_pct["SAPd_EQ"] = 0.0
        intel.position_open_time["SAPd_EQ"] = datetime.datetime.now().timestamp() - 600  # 10 min
        regime = {"is_morning_gap_harvest": False, "is_pre_close_window": False}
        metrics = {"atr_5m_volatility_pct": 0.18, "green_hook_confirmed": True, "vwap_dist_pct": 0.0, "rsi_5m": 50.0}
        reason = intel.evaluate_uncapped_exit("SAPd_EQ", -0.0176, regime, 0.0, {}, metrics, 0.0, False)
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

        # V11.6 Fix #6: Alle 14:40 CET (08:40 ET, Pre-Bell USA) lo Scudo Whipsaw Pre-Bell blocca i setup ordinari;
        # alle 15:36 CET (09:36 ET, dopo la prima candela 5m NYSE) si apre l'onda Wall Street e i candidati idonei (>= 58 pt) passano!
        pre_us_dt = datetime.datetime(2026, 11, 12, 14, 40, 0, tzinfo=daemon.MARKET_TZ)
        reg_pre_us = intel.get_intraday_regime(pre_us_dt)
        self.assertTrue(reg_pre_us["is_midday_sniper_window"])
        self.assertEqual(reg_pre_us["max_active_slots"], 2)
        self.assertFalse(intel.is_eligible_entry_candidate(ordinary_cand, reg_pre_us, ov_ok))

        post_bell_dt = datetime.datetime(2026, 11, 12, 15, 36, 0, tzinfo=daemon.MARKET_TZ)
        reg_post_bell = intel.get_intraday_regime(post_bell_dt)
        self.assertTrue(reg_post_bell["allow_new_buys"])
        self.assertFalse(reg_post_bell["is_midday_sniper_window"])
        self.assertTrue(intel.is_eligible_entry_candidate(ordinary_cand, reg_post_bell, ov_ok))
        low_score_cand = dict(ordinary_cand, quant_buy_score=55.0)  # < BASE_MIN_BUY_SCORE (58.0)
        self.assertFalse(intel.is_eligible_entry_candidate(low_score_cand, reg_post_bell, ov_ok))

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

    def test_19_pre_close_runway_1700_buy_freeze_and_continuous_evening_flat(self):
        """Invariante #19: Rampa selettività 16:00-17:00, stop nuovi acquisti >= 17:00, Decompressione C0 17:00-17:25 e Chiusura Integrale 17:25-17:29."""
        intel = daemon.HybridUncappedIntelligence()
        dt_1659 = datetime.datetime(2026, 11, 12, 16, 59, 0, tzinfo=daemon.MARKET_TZ)
        dt_1700 = datetime.datetime(2026, 11, 12, 17, 0, 0, tzinfo=daemon.MARKET_TZ)
        dt_1715 = datetime.datetime(2026, 11, 12, 17, 15, 0, tzinfo=daemon.MARKET_TZ)
        dt_1725 = datetime.datetime(2026, 11, 12, 17, 25, 0, tzinfo=daemon.MARKET_TZ)
        reg_1659 = intel.get_intraday_regime(dt_1659)
        reg_1700 = intel.get_intraday_regime(dt_1700)
        reg_1715 = intel.get_intraday_regime(dt_1715)
        reg_1725 = intel.get_intraday_regime(dt_1725)
        self.assertTrue(reg_1659["allow_new_buys"])
        self.assertGreater(reg_1659["evening_runway_progress"], 0.95)
        self.assertFalse(reg_1700["allow_new_buys"])
        self.assertTrue(reg_1700["is_pre_close_window"])
        self.assertFalse(reg_1700["is_hard_flat_window"])
        self.assertTrue(reg_1725["is_hard_flat_window"])

        elite_cand = {
            "ticker": "ASMLa_EQ", "live_price_eur": 1350.0, "vwap_dist_pct": 0.20,
            "has_fresh_intraday_feed": True, "rvol_ratio": 1.60, "quant_buy_score": 92.0,
            "rsi_5m": 55.0, "green_hook_confirmed": True, "atr_5m_volatility_pct": 0.22,
            "day_range_pct": 1.8, "kaufman_efficiency_ratio": 0.65, "strong_for_overnight": True,
        }
        mediocre_late_cand = dict(elite_cand, quant_buy_score=64.0, atr_5m_volatility_pct=0.125)
        ov_strong = {
            "allow_overnight_hold": True, "nasdaq_change_pct": 0.80, "sp500_change_pct": 0.60,
            "dax_change_pct": 0.50, "vix_fear_change_pct": -2.0, "vix_level": 15.0,
        }
        # Alle 16:59 il razzo elite (Score 92, ATR 0.22%) passa, mentre il titolo lento/mediocre (Score 64, ATR 0.125%) è bloccato dalla rampa!
        self.assertTrue(intel.is_eligible_entry_candidate(elite_cand, reg_1659, ov_strong))
        self.assertFalse(intel.is_eligible_entry_candidate(mediocre_late_cand, reg_1659, ov_strong))
        # Dalle 17:00 stop totale nuovi ingressi anche per Score 92!
        self.assertFalse(intel.is_eligible_entry_candidate(elite_cand, reg_1700, ov_strong))

        # Switch Stagnazione (#9) attivo alle 16:59 ma spento durante Pausa Pranzo, mentre alle 17:15 scatta la Decompressione Serale Continua!
        reg_lunch = intel.get_intraday_regime(datetime.datetime(2026, 11, 12, 12, 0, 0, tzinfo=daemon.MARKET_TZ))
        intel.position_open_time["SAPd_EQ"] = datetime.datetime.now().timestamp() - 3600.0
        intel.peak_pnl_pct["SAPd_EQ"] = 0.0020
        stag_metrics = {
            "atr_5m_volatility_pct": 0.18, "elastic_shield_act_raw": 0.0068, "elastic_shield_pull_raw": 0.0016,
            "fase_onda_sinusoidale": "ONDA_DISCENDENTE_O_DEBOLE", "strong_for_overnight": False,
            "green_hook_confirmed": False, "vwap_dist_pct": -0.12, "rsi_5m": 44.0, "quant_buy_score": 18.0,
        }
        reason_1659 = intel.evaluate_uncapped_exit(
            "SAPd_EQ", 0.0018, reg_1659, 92.0, ov_strong, stag_metrics, 0.0, True, False
        )
        self.assertIn("BLINDATURA #9", reason_1659 or "")
        intel.peak_pnl_pct["SAPd_EQ"] = 0.0020
        reason_lunch = intel.evaluate_uncapped_exit(
            "SAPd_EQ", 0.0018, reg_lunch, 92.0, ov_strong, stag_metrics, 0.0, True, False
        )
        self.assertIsNone(reason_lunch)
        intel.peak_pnl_pct["SAPd_EQ"] = 0.0020
        reason_1715_stall = intel.evaluate_uncapped_exit(
            "SAPd_EQ", 0.0018, reg_1715, 92.0, ov_strong, stag_metrics, 0.0, True, False
        )
        self.assertIn("DECOMPRESSIONE SERALE", reason_1715_stall or "")

        # Ma se alle 17:15 l'onda verde è ancora in piena spinta (green_hook=True, vwap >= 0), lascia correre fino allo stallo o alle 17:25!
        riding_metrics = dict(stag_metrics, green_hook_confirmed=True, vwap_dist_pct=0.14, rsi_5m=56.0, strong_for_overnight=True)
        intel.peak_pnl_pct["SAPd_EQ"] = 0.0018
        reason_1715_ride = intel.evaluate_uncapped_exit(
            "SAPd_EQ", 0.0018, reg_1715, 0.0, ov_strong, riding_metrics, 0.0, False, False
        )
        self.assertIsNone(reason_1715_ride)

        # E alle 17:25 (Lun-Gio C1): taglia deterministicamente i rossi/deboli mentre custodisce nella notte il vincitore sano >= VWAP!
        reason_1725_red = intel.evaluate_uncapped_exit(
            "SAPd_EQ", -0.0020, reg_1725, 0.0, ov_strong, riding_metrics, 0.0, False, False
        )
        self.assertIn("CHIUSURA SERALE SELETTIVA C1 17:25", reason_1725_red or "")
        reason_1725_green_keep = intel.evaluate_uncapped_exit(
            "SAPd_EQ", 0.0018, reg_1725, 0.0, ov_strong, riding_metrics, 0.0, False, False
        )
        self.assertIsNone(reason_1725_green_keep)

        # Verifica telemetria macro USA (>= +0.25% media ponderata con entrambi gli indici positivi)
        radar = daemon.OvernightWaveRadar()
        lukewarm_map = {"%5EGSPC": (0.12, 5900.0, True), "%5EGDAXI": (0.10, 19200.0, True), "%5EIXIC": (0.15, 19000.0, True), "%5EVIX": (0.2, 16.5, True)}
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
        """Invariante #21: 47 Colossi EUR Zero-Fee (40 UE incl. 5 Green & 3 Campioni IT-NL 0% FTT + 7 Big Tech USA in EUR), 100% GETTEX 0s e isolamento Markowitz."""
        daemon.discover_and_verify_eur_giants(None)
        expected_us_eur = {"NVDd_EQ", "MSFd_EQ", "APCd_EQ", "AMZd_EQ", "ABEAd_EQ", "FB2Ad_EQ", "AMDd_EQ"}
        expected_green_eur = {"HEId_EQ", "NDX1d_EQ", "NDAd_EQ", "LIGHTa_EQ", "AALBa_EQ"}
        expected_it_nl_eur = {"STMpp_EQ", "STLAPp_EQ", "2FEd_EQ"}
        self.assertTrue(expected_us_eur.issubset(set(daemon.ASSET_PROFILES.keys())))
        self.assertTrue(expected_green_eur.issubset(set(daemon.ASSET_PROFILES.keys())))
        self.assertTrue(expected_it_nl_eur.issubset(set(daemon.ASSET_PROFILES.keys())))
        # FREd_EQ ("" in t212_verified_universe.json) deve essere escluso per evitare ordini HTTP 400 su ticker inesistenti
        self.assertNotIn("FREd_EQ", daemon.ASSET_PROFILES)
        self.assertEqual(len(daemon.ASSET_PROFILES), 47)

        for tkr, prof in daemon.ASSET_PROFILES.items():
            meta = daemon.EUR_ZERO_FEE_UNIVERSE[tkr]
            self.assertEqual(meta["currency"], "EUR", f"Valuta non EUR su {tkr}")
            self.assertEqual(meta["tobin_tax"], "0.00%", f"Tobin tax non zero su {tkr}")
            self.assertTrue(str(prof.get("gettex", "")).startswith("GETTEX:"), f"Simbolo GETTEX mancante su {tkr}")

        # Isolamento settoriale Markowitz sulle Big Tech USA correlate, Rinnovabili e Campioni IT-NL:
        self.assertEqual(daemon.ASSET_PROFILES["NVDd_EQ"]["sector"], daemon.ASSET_PROFILES["AMDd_EQ"]["sector"])
        self.assertEqual(daemon.ASSET_PROFILES["ABEAd_EQ"]["sector"], daemon.ASSET_PROFILES["FB2Ad_EQ"]["sector"])
        self.assertEqual(daemon.ASSET_PROFILES["MSFd_EQ"]["sector"], daemon.ASSET_PROFILES["SAPd_EQ"]["sector"])
        self.assertEqual(daemon.ASSET_PROFILES["AMZd_EQ"]["sector"], daemon.ASSET_PROFILES["ZALd_EQ"]["sector"])
        self.assertEqual(daemon.ASSET_PROFILES["NDX1d_EQ"]["sector"], daemon.ASSET_PROFILES["RWEd_EQ"]["sector"])
        self.assertEqual(daemon.ASSET_PROFILES["STMpp_EQ"]["sector"], daemon.ASSET_PROFILES["IFXd_EQ"]["sector"])
        self.assertEqual(daemon.ASSET_PROFILES["STLAPp_EQ"]["sector"], daemon.ASSET_PROFILES["BMWd_EQ"]["sector"])
        self.assertEqual(daemon.ASSET_PROFILES["2FEd_EQ"]["sector"], "LUXURY_SUPERCARS")
        self.assertEqual(
            len({
                daemon.ASSET_PROFILES["HEId_EQ"]["sector"],
                daemon.ASSET_PROFILES["NDX1d_EQ"]["sector"],
                daemon.ASSET_PROFILES["NDAd_EQ"]["sector"],
                daemon.ASSET_PROFILES["LIGHTa_EQ"]["sector"],
                daemon.ASSET_PROFILES["AALBa_EQ"]["sector"],
            }),
            5,
        )

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
                    {"ticker": "MRKd_EQ", "quantity": 0.16, "averagePrice": 150.0, "currentPrice": 147.20, "ppl": -0.45},
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
                "MRKd_EQ": {"ticker": "MRKd_EQ", "name": "Merck", "squad": "SQUADRA_1_CECCHINO_GIORNALIERO", "sector": "PHARMA_BIOTECH", "live_price_eur": 147.20, "rsi_5m": 32.0, "vwap_dist_pct": -0.40, "atr_5m_volatility_pct": 0.15, "day_range_pct": 1.6, "rvol_ratio": 1.2, "quant_buy_score": 0.0, "green_hook_confirmed": False, "entry_hook_confirmed": False, "strong_for_overnight": False, "has_fresh_intraday_feed": True, "fase_onda_sinusoidale": "COLTELLO_IN_CADUTA_ATTENDERE_UNCINO_VERDE"},
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
        # V11.6 Fix #4: In capitolazione (breadth = 0.10 <= 0.15 -> min_vwap_by_breadth = 0.00%):
        # sia il ritardatario sia il washout RSI<=30 sotto VWAP sono BLOCCATI senza eccezioni, mentre il Leader >= VWAP passa!
        self.assertFalse(intel.is_eligible_entry_candidate(sub_vwap_laggard, reg_open, ov_ok, market_breadth_above_vwap=0.10))
        self.assertTrue(intel.is_eligible_entry_candidate(rs_leader, reg_open, ov_ok, market_breadth_above_vwap=0.10))
        self.assertFalse(intel.is_eligible_entry_candidate(deep_washout, reg_open, ov_ok, market_breadth_above_vwap=0.10))
        # In mercato ampio (breadth = 0.50 >= 0.35 -> min_vwap_by_breadth = -0.35%): anche pullback/washout sano passano regolarmente
        self.assertTrue(intel.is_eligible_entry_candidate(sub_vwap_laggard, reg_open, ov_ok, market_breadth_above_vwap=0.50))
        self.assertTrue(intel.is_eligible_entry_candidate(deep_washout, reg_open, ov_ok, market_breadth_above_vwap=0.50))

        # 4) Sblocco Istantaneo Liquidità di Rotazione 4/4 -> 3/4 -> 4/4 nello stesso ciclo anche con cassa iniziale 0.64 EUR e lag REST!
        class _TightCashRotationBroker:
            def __init__(self):
                self.positions = [
                    {"ticker": "MRKd_EQ", "quantity": 0.1667, "averagePrice": 150.0, "currentPrice": 147.20, "ppl": -0.47},
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
        intel_rot.position_open_time["MRKd_EQ"] = now_epoch - 1200.0  # 20m a -1.87% -> Airbag V11.6 libera ~24.54 EUR!
        rot_scan = daemon.QuantMarketScanner()
        rot_scan.scan_all = lambda **kw: {
            "MRKd_EQ": {"ticker": "MRKd_EQ", "name": "Merck", "squad": "SQUADRA_1_CECCHINO_GIORNALIERO", "sector": "PHARMA_BIOTECH", "live_price_eur": 147.20, "rsi_5m": 32.0, "vwap_dist_pct": -0.40, "atr_5m_volatility_pct": 0.16, "day_range_pct": 1.6, "rvol_ratio": 1.2, "quant_buy_score": 0.0, "green_hook_confirmed": False, "entry_hook_confirmed": False, "strong_for_overnight": False, "has_fresh_intraday_feed": True, "fase_onda_sinusoidale": "COLTELLO_IN_CADUTA_ATTENDERE_UNCINO_VERDE"},
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
        self.assertEqual(st_rot["mode"], "INSTITUTIONAL_V11_6_LTS_ZERO_CEROTTI")

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

    def test_29_cross_model_defensive_c0_onset_multi_tranche_lifo_and_annual_tax_isolation(self):
        """Invariante #29: C0 bilaterale anche per shield_act < 0.58% (DTE/EOAN), flash-drop 1B, LIFO multi-tranche TUIR, isolamento anno fiscale 730 e guardia ordini orfani."""
        intel = daemon.HybridUncappedIntelligence()
        # 1) Titolo difensivo con shield_act = 0.0048 (< 0.0058): continuità C0 senza salto da +0.18% a +0.36% sul bordo 0.0048!
        prev_fl = -1.0
        for step in range(40, 60):
            pk = round(step * 0.0001, 4)
            _, fl = intel.compute_profit_protection_floor(pk, 0.0048, 0.0012, 0.0014, False)
            if fl is not None:
                self.assertGreaterEqual(fl, prev_fl)
                prev_fl = fl
        _, fl_47 = intel.compute_profit_protection_floor(0.0047, 0.0048, 0.0012, 0.0014, False)
        _, fl_48 = intel.compute_profit_protection_floor(0.0048, 0.0048, 0.0012, 0.0014, False)
        self.assertLessEqual(abs(fl_48 - fl_47), 0.0007)  # rampa lineare continua (non salto secco di +18 bps!)

        # Curva 1B (peak = +0.64%, shield_act = +0.95%) intercetta anche un flash-drop istantaneo a -0.10% (< -0.05%)!
        intel.peak_pnl_pct["EOANd_EQ"] = 0.0064
        reg_open = {"is_morning_gap_harvest": False, "is_pre_close_window": False, "is_friday_pre_weekend": False}
        m_1b = {"atr_5m_volatility_pct": 0.16, "elastic_shield_act_raw": 0.0095, "elastic_shield_pull_raw": 0.0020, "green_hook_confirmed": False, "vwap_dist_pct": -0.12, "rsi_5m": 41.0}
        exit_1b = intel.evaluate_uncapped_exit("EOANd_EQ", -0.0010, reg_open, 0.0, {}, m_1b, 0.0, False)
        self.assertIsNotNone(exit_1b)
        self.assertIn("BLINDATURA #1B", exit_1b)

        # 2) Integrità LIFO Multi-Tranche (Art. 67-68 TUIR): 10 az @ 10€ + 10 az @ 20€ (avg 15€), vendita 10 az @ 22€ -> utile LIFO = +20.00€, residuo 10 az @ 10.00€!
        tmp_lifo = "/tmp/test_v115_multitranche_lifo.json"
        if os.path.exists(tmp_lifo):
            os.remove(tmp_lifo)
        try:
            tr = ItalianTaxTracker730(filepath=tmp_lifo)
            tr.record_buy("SAPd_EQ", 10.0, 10.00)
            tr.record_buy("SAPd_EQ", 10.0, 20.00)
            op_lifo = tr.record_sell("SAPd_EQ", 10.0, 22.00, fallback_avg_price_eur=15.00)
            self.assertAlmostEqual(op_lifo["risultato_fiscale_eur"], 20.00, places=2)
            rem = tr.data["lotti_aperti_lifo"]["SAPd_EQ"]
            self.assertEqual(len(rem), 1)
            self.assertAlmostEqual(rem[0]["price_eur"], 10.00, places=4)

            # 3) Isolamento Anno Fiscale al 1° Gennaio (Rollover 2026 -> 2027 senza doppia tassazione sugli utili 2026!):
            tr.data["anno_fiscale"] = 2026
            tr.data["plusvalenze_lorde_eur"] = 1000.00
            tr.data["minusvalenze_lorde_eur"] = 0.00
            tr.save()
            real_dt = datetime.datetime
            jan_2027 = real_dt(2027, 1, 4, 10, 0, 0, tzinfo=daemon.MARKET_TZ)
            with patch("trading212_bot.datetime.datetime") as mock_bot_dt:
                mock_bot_dt.now.side_effect = lambda tz=None: jan_2027.astimezone(tz) if tz else jan_2027.replace(tzinfo=None)
                tr.reconcile_certified_cash_result(1100.00)  # 1000€ del 2026 + 100€ realizzati nel 2027!
            self.assertEqual(tr.data["anno_fiscale"], 2027)
            self.assertAlmostEqual(tr.data["baseline_result_inizio_anno_eur"], 1000.00, places=2)
            self.assertAlmostEqual(tr.data["plusvalenze_lorde_eur"], 100.00, places=2)
            self.assertAlmostEqual(tr.data["profitto_storico_anni_precedenti_eur"], 1000.00, places=2)
        finally:
            if os.path.exists(tmp_lifo):
                os.remove(tmp_lifo)

        # 4) Seed cross-VM di OvernightWaveRadar da BOT_STATE_PATH quando .radar_wave_cache.json è assente nella staffetta 12:25:
        tmp_st_radar = "/tmp/test_v115_state_radar_seed.json"
        now_dt = datetime.datetime.now(daemon.MARKET_TZ)
        with open(tmp_st_radar, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": now_dt.replace(tzinfo=None).isoformat(timespec="seconds"),
                "radar_onda_notturna_wall_street": {"verdict": "ONDA_POSITIVA_STAFFETTA", "allow_overnight_hold": True, "nasdaq_change_pct": 0.5, "sp500_change_pct": 0.4, "dax_change_pct": 0.3, "vix_fear_change_pct": -1.5, "vix_level": 15.0},
            }, f)
        try:
            with patch.object(daemon, "BOT_STATE_PATH", tmp_st_radar):
                r_relay = daemon.OvernightWaveRadar(cache_path="/tmp/nonexistent_radar_cache_v115.json")
                with patch.object(r_relay, "_fetch_index_snapshot", side_effect=AssertionError("Deve riusare il seed fresco <120s da BOT_STATE_PATH!")):
                    v_rel = r_relay.evaluate_overnight_wave(force=False)
                self.assertEqual(v_rel["verdict"], "ONDA_POSITIVA_STAFFETTA")
        finally:
            if os.path.exists(tmp_st_radar):
                os.remove(tmp_st_radar)

    def test_30_convergence_multipoll_frozen_bar_us_holiday_atomic_io_and_zainetto(self):
        """Invariante #30: Guardia barra congelata :00 persistente su poll multipli, festività USA senza falsi crash/overnight, uscita atomica singola su posizione >1.24x e zainetto multi-anno TUIR."""
        real_dt = datetime.datetime
        mkt_dt = real_dt(2026, 11, 16, 16, 10, 8, tzinfo=daemon.MARKET_TZ)
        now_ts = mkt_dt.timestamp()
        bucket_now = int(now_ts // 300) * 300
        prev_b5 = bucket_now - 300

        # 1) Multi-poll su barra GETTEX congelata a :00: né il 1° poll (:00:02) né il 2° poll (:00:08) devono clonare il corpo passato!
        sc_mp = daemon.QuantMarketScanner()
        sc_mp.realtime_5m_bars["IFXd_EQ"] = {prev_b5: {"open": 30.00, "high": 30.40, "low": 29.95, "close": 30.35, "has_true_open": True}}
        gx_frozen = json.dumps({"data": [{"s": "GETTEX:IFX", "d": [30.35, 30.00, 30.40, 29.95, 100, "streaming"]}]}).encode("utf-8")
        gx_unfrozen = json.dumps({"data": [{"s": "GETTEX:IFX", "d": [30.38, 30.36, 30.42, 30.35, 100, "streaming"]}]}).encode("utf-8")
        with patch("datetime.datetime") as mock_dt:
            mock_dt.now.side_effect = lambda tz=None: mkt_dt.astimezone(tz) if tz else mkt_dt.replace(tzinfo=None)
            with patch("time.time", return_value=float(bucket_now + 2)), patch("urllib.request.urlopen", return_value=_FakeHTTPResp(gx_frozen)):
                sc_mp.refresh_gettex_live_quotes(force=True)
            self.assertFalse(sc_mp.realtime_5m_bars["IFXd_EQ"][bucket_now]["has_true_open"])
            self.assertEqual(sc_mp.realtime_5m_bars["IFXd_EQ"][bucket_now]["open"], 30.35)
            # Secondo poll 6s dopo (:00:08) ancora senza scambi su GETTEX -> DEVE restare protetta (non sovrascrivere con 30.00!):
            with patch("time.time", return_value=float(bucket_now + 8)), patch("urllib.request.urlopen", return_value=_FakeHTTPResp(gx_frozen)):
                sc_mp.refresh_gettex_live_quotes(force=True)
            self.assertFalse(sc_mp.realtime_5m_bars["IFXd_EQ"][bucket_now]["has_true_open"])
            self.assertEqual(sc_mp.realtime_5m_bars["IFXd_EQ"][bucket_now]["open"], 30.35)
            # Terzo poll (:00:14) con primo vero scambio nel nuovo bucket -> adotta il vero open 30.36!
            with patch("time.time", return_value=float(bucket_now + 14)), patch("urllib.request.urlopen", return_value=_FakeHTTPResp(gx_unfrozen)):
                sc_mp.refresh_gettex_live_quotes(force=True)
            self.assertTrue(sc_mp.realtime_5m_bars["IFXd_EQ"][bucket_now]["has_true_open"])
            self.assertEqual(sc_mp.realtime_5m_bars["IFXd_EQ"][bucket_now]["open"], 30.36)

        # 2) Festività USA (XETRA aperta alle 16:10 CET, ma NYSE chiusa con barre USA ferme a ieri -1.50%):
        #    is_macro_crash_shield_active NON deve attivare falsi crash USA su dati vecchi di 24h!
        intel = daemon.HybridUncappedIntelligence()
        reg_afternoon = {"us_market_live": True, "allow_new_buys": True}
        ov_us_holiday = {"us_indices_live_today": False, "nasdaq_change_pct": -1.50, "sp500_change_pct": -1.30, "dax_change_pct": 0.25, "vix_fear_change_pct": 0.5, "vix_level": 15.5}
        self.assertFalse(intel.is_macro_crash_shield_active(reg_afternoon, ov_us_holiday))
        ov_us_live_crash = dict(ov_us_holiday, us_indices_live_today=True)
        self.assertTrue(intel.is_macro_crash_shield_active(reg_afternoon, ov_us_live_crash))

        # 3) Consumo algebrico pluriennale dello Zainetto Minusvalenze (Art. 68 TUIR) + record_sell coerente:
        tmp_z = "/tmp/test_v115_zainetto_tuir.json"
        if os.path.exists(tmp_z):
            os.remove(tmp_z)
        try:
            trz = ItalianTaxTracker730(filepath=tmp_z)
            trz.data["anno_fiscale"] = 2026
            trz.data["plusvalenze_lorde_eur"] = 1.00
            trz.data["minusvalenze_lorde_eur"] = 5.00  # Netto 2026 = -4.00€ -> Zainetto 4.00€ nel 2027
            trz.save()
            with patch("trading212_bot.datetime.datetime") as mb_dt:
                d27 = real_dt(2027, 1, 5, 10, 0, 0, tzinfo=daemon.MARKET_TZ)
                mb_dt.now.side_effect = lambda tz=None: d27.astimezone(tz) if tz else d27.replace(tzinfo=None)
                trz.reconcile_certified_cash_result(-4.00)
                self.assertAlmostEqual(trz.data["zainetto_minusvalenze_pregresse_eur"], 4.00, places=2)
                # Vendita in utile di +10.00€ nel 2027 via record_sell -> imponibile = 10 - 4 = 6.00€!
                trz.record_buy("SAPd_EQ", 1.0, 100.00)
                trz.record_sell("SAPd_EQ", 1.0, 110.00)
                self.assertAlmostEqual(trz.data["imponibile_netto_eur"], 6.00, places=2)
                # Rollover al 2028: lo zainetto da 4.00€ è stato integralmente assorbito dai +10.00€ del 2027 (-> 0.00€ nel 2028)!
                d28 = real_dt(2028, 1, 5, 10, 0, 0, tzinfo=daemon.MARKET_TZ)
                mb_dt.now.side_effect = lambda tz=None: d28.astimezone(tz) if tz else d28.replace(tzinfo=None)
                trz.reconcile_certified_cash_result(6.00)
                self.assertAlmostEqual(trz.data["zainetto_minusvalenze_pregresse_eur"], 0.00, places=2)
                self.assertAlmostEqual(trz.data["archivio_anni_precedenti"]["2027"]["imponibile_netto_eur"], 6.00, places=2)
        finally:
            if os.path.exists(tmp_z):
                os.remove(tmp_z)

    def test_31_intelligent_evening_flat_by_close_4x4_morning_reset(self):
        """Invariante #31: Decompressione C0 17:00-17:25 (onda verde corre, stallo/rimbalzo incassa), isolamento guasti multi-posizione 17:26 e 4/4 cartucce libere alle 09:00."""
        daemon.discover_and_verify_eur_giants(None)
        real_dt = datetime.datetime

        class _EveningFlatBroker:
            def __init__(self):
                self.positions = [
                    {"ticker": "NVDd_EQ", "quantity": 0.16, "averagePrice": 150.00, "currentPrice": 150.25, "ppl": 0.04},   # +0.17% in piena onda verde -> corre alle 17:08!
                    {"ticker": "SAPd_EQ", "quantity": 0.12, "averagePrice": 200.00, "currentPrice": 200.22, "ppl": 0.03},   # +0.11% in stallo -> incassa alle 17:08!
                    {"ticker": "APCd_EQ", "quantity": 0.08, "averagePrice": 300.00, "currentPrice": 299.25, "ppl": -0.06},  # -0.25% -> attende rimbalzo fino alle 17:21!
                ]
                self.pending = [{"id": "PEND_LATE_1", "ticker": "SIEd_EQ", "quantity": 0.09, "type": "LIMIT"}]
                self.cancelled = []
                self.sells = []
                self.fail_once_tkr = None

            def get_open_positions(self):
                return list(self.positions)

            def get_pending_orders(self):
                return list(self.pending)

            def get_account_cash(self):
                return {"result": 0.0, "free": 25.0}

            def cancel_order(self, order_id):
                self.cancelled.append(order_id)
                self.pending = [o for o in self.pending if o["id"] != order_id]

            def place_market_order(self, ticker: str, quantity: float):
                if self.fail_once_tkr == ticker:
                    self.fail_once_tkr = None
                    raise RuntimeError("Transient 502 on first close attempt")
                self.sells.append((ticker, quantity))
                self.positions = [p for p in self.positions if p["ticker"] != ticker]
                return {"id": f"SELL_{ticker}"}

        broker = _EveningFlatBroker()
        bot = daemon.Trading212AutonomousBot(client=broker, total_budget_eur=100.0, cartridges=4, annual_target_pct=0.30)
        bot.tax_tracker = ItalianTaxTracker730(filepath=self._tmp_tax_path)
        dt_open_1615 = real_dt(2026, 11, 16, 16, 15, 0, tzinfo=daemon.MARKET_TZ)
        with patch("datetime.datetime") as mock_dt, patch("time.time", return_value=dt_open_1615.timestamp()):
            mock_dt.now.side_effect = lambda tz=None: dt_open_1615.astimezone(tz) if tz else dt_open_1615.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            mock_dt.fromisoformat.side_effect = real_dt.fromisoformat
            for p0 in broker.positions:
                bot.tax_tracker.record_buy(p0["ticker"], p0["quantity"], p0["averagePrice"])
            bot.tax_tracker.save()
            intel = daemon.HybridUncappedIntelligence()
        intel.prev_open_snapshot.clear()
        sc = daemon.QuantMarketScanner()

        def _metrics_evening():
            px_map = {p["ticker"]: p["currentPrice"] for p in broker.positions}
            return {
                "NVDd_EQ": {"ticker": "NVDd_EQ", "name": "NVIDIA", "squad": "SQUADRA_2_CAVALCA_ONDA", "sector": "CHIP_ACCELERATORI_AI", "live_price_eur": px_map.get("NVDd_EQ", 150.25), "rsi_5m": 58.0, "vwap_dist_pct": 0.16, "atr_5m_volatility_pct": 0.24, "day_range_pct": 2.0, "rvol_ratio": 1.5, "quant_buy_score": 85.0, "green_hook_confirmed": True, "entry_hook_confirmed": True, "strong_for_overnight": True, "has_fresh_intraday_feed": True, "fase_onda_sinusoidale": "SUPER_TREND_VERO_POSITIVO_BREAKOUT"},
                "SAPd_EQ": {"ticker": "SAPd_EQ", "name": "SAP", "squad": "SQUADRA_2_CAVALCA_ONDA", "sector": "SOFTWARE_CLOUD", "live_price_eur": px_map.get("SAPd_EQ", 200.22), "rsi_5m": 46.0, "vwap_dist_pct": -0.05, "atr_5m_volatility_pct": 0.18, "day_range_pct": 1.5, "rvol_ratio": 1.1, "quant_buy_score": 0.0, "green_hook_confirmed": False, "entry_hook_confirmed": False, "strong_for_overnight": False, "has_fresh_intraday_feed": True, "fase_onda_sinusoidale": "ONDA_DISCENDENTE_O_DEBOLE"},
                "APCd_EQ": {"ticker": "APCd_EQ", "name": "Apple", "squad": "SQUADRA_2_CAVALCA_ONDA", "sector": "ECOSISTEMA_MOBILE_HARDWARE", "live_price_eur": px_map.get("APCd_EQ", 299.25), "rsi_5m": 44.0, "vwap_dist_pct": -0.08, "atr_5m_volatility_pct": 0.17, "day_range_pct": 1.4, "rvol_ratio": 1.0, "quant_buy_score": 0.0, "green_hook_confirmed": False, "entry_hook_confirmed": False, "strong_for_overnight": False, "has_fresh_intraday_feed": True, "fase_onda_sinusoidale": "ONDA_DISCENDENTE_O_DEBOLE"},
            }

        sc.scan_all = lambda **kw: _metrics_evening()

        class _DummyRadar31:
            def evaluate_overnight_wave(self):
                return {"verdict": "OK", "allow_overnight_hold": True, "nasdaq_change_pct": 0.4, "sp500_change_pct": 0.3, "dax_change_pct": 0.2, "vix_fear_change_pct": -1.0, "vix_level": 15.5, "us_indices_live_today": True}

        # Passo 1 (17:08 CET, tau=0.32 -> harvest_floor = +0.069%):
        # - Cancella subito PEND_LATE_1
        # - Incassa SAPd_EQ (+0.11% in stallo)
        # - Lascia correre NVDd_EQ (+0.17% in onda verde) e concede tempo di recupero ad APCd_EQ (-0.25%)!
        dt_1708 = real_dt(2026, 11, 16, 17, 8, 0, tzinfo=daemon.MARKET_TZ)
        with patch("datetime.datetime") as mock_dt, patch("time.time", return_value=dt_1708.timestamp()):
            mock_dt.now.side_effect = lambda tz=None: dt_1708.astimezone(tz) if tz else dt_1708.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            mock_dt.fromisoformat.side_effect = real_dt.fromisoformat
            daemon.run_cycle(bot, intel, sc, _DummyRadar31(), 1)
        self.assertEqual(broker.cancelled, ["PEND_LATE_1"])
        self.assertEqual([t for t, _ in broker.sells], ["SAPd_EQ"])

        # Passo 2 (17:21 CET, tau=0.84 -> harvest_floor = -0.014%):
        # APCd_EQ rimbalza quasi a pareggio (299.97 EUR = -0.01%) e stalla -> uscita intelligente su rimbalzo!
        broker.positions[1]["currentPrice"] = 299.97
        dt_1721 = real_dt(2026, 11, 16, 17, 21, 0, tzinfo=daemon.MARKET_TZ)
        with patch("datetime.datetime") as mock_dt, patch("time.time", return_value=dt_1721.timestamp()):
            mock_dt.now.side_effect = lambda tz=None: dt_1721.astimezone(tz) if tz else dt_1721.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            mock_dt.fromisoformat.side_effect = real_dt.fromisoformat
            daemon.run_cycle(bot, intel, sc, _DummyRadar31(), 2)
        self.assertIn("APCd_EQ", [t for t, _ in broker.sells])

        # Passo 3 (17:26 CET Lun-Gio, Selezione Asimmetrica C1):
        # Aggiunge 2 posizioni in rosso (EOANd_EQ e SIEd_EQ) e simula errore HTTP transitorio su EOANd_EQ:
        # - SIEd_EQ viene chiusa subito (isolamento guasti!), EOANd_EQ viene chiusa 6s dopo;
        # - NVDd_EQ (+0.17%, VWAP +0.16%, RSI 58) resta APERTA in Custodia Notturna C1 con eod_ref_price_eur salvato!
        broker.positions.append({"ticker": "EOANd_EQ", "quantity": 1.25, "averagePrice": 20.00, "currentPrice": 19.92, "ppl": -0.10})
        broker.positions.append({"ticker": "SIEd_EQ", "quantity": 0.10, "averagePrice": 250.00, "currentPrice": 249.50, "ppl": -0.05})
        broker.fail_once_tkr = "EOANd_EQ"
        dt_1726 = real_dt(2026, 11, 16, 17, 26, 0, tzinfo=daemon.MARKET_TZ)
        with patch("datetime.datetime") as mock_dt, patch("time.time", return_value=dt_1726.timestamp()):
            mock_dt.now.side_effect = lambda tz=None: dt_1726.astimezone(tz) if tz else dt_1726.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            mock_dt.fromisoformat.side_effect = real_dt.fromisoformat
            bot.tax_tracker.record_buy("EOANd_EQ", 1.25, 20.00)
            bot.tax_tracker.record_buy("SIEd_EQ", 0.10, 250.00)
            daemon.run_cycle(bot, intel, sc, _DummyRadar31(), 3)
            self.assertEqual([p["ticker"] for p in broker.positions], ["NVDd_EQ", "EOANd_EQ"])  # SIEd_EQ chiusa subito nonostante errore su EOANd_EQ!
            st_eod = daemon.run_cycle(bot, intel, sc, _DummyRadar31(), 4)
        self.assertEqual([p["ticker"] for p in broker.positions], ["NVDd_EQ"])
        self.assertEqual(len(st_eod["cartucce_4x25_eur"]), 1)
        self.assertEqual(st_eod["cartucce_4x25_eur"][0]["ticker"], "NVDd_EQ")
        self.assertEqual(st_eod["cartucce_4x25_eur"][0]["eod_ref_price_eur"], 150.25)

        # Passo 4 (Mattino successivo ore 09:06 CET): ZERO blocchi residui sui titoli chiusi ieri sera,
        # e se NVDd_EQ portata dalla notte rallenta (+0.05% < +0.12%), il Taglio Mattutino C1 libera subito la 4ª cartuccia!
        broker.positions[0]["currentPrice"] = 150.08
        dt_next_0906 = real_dt(2026, 11, 17, 9, 6, 0, tzinfo=daemon.MARKET_TZ)
        with patch("datetime.datetime") as mock_dt, patch("time.time", return_value=dt_next_0906.timestamp()):
            mock_dt.now.side_effect = lambda tz=None: dt_next_0906.astimezone(tz) if tz else dt_next_0906.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            mock_dt.fromisoformat.side_effect = real_dt.fromisoformat
            intel.sync_from_tax_data(bot.tax_tracker.data)
            self.assertTrue(intel.can_buy_ticker("EOANd_EQ", 19.95))
            self.assertTrue(intel.can_buy_ticker("APCd_EQ", 300.10))
            st_morn = daemon.run_cycle(bot, intel, sc, _DummyRadar31(), 5)
        self.assertEqual(broker.positions, [])
        self.assertEqual(st_morn["cartucce_4x25_eur"], [])

    def test_32_vectorial_sign_congruence_blocks_falling_knives_and_macro_crash_bypass(self):
        """Invariante #32: Congruenza vettoriale di segno sull'origine 0.0 blocca cascate ribassiste su VWAP e falsi bypass del Macro Crash Shield (caso reale 16/11)."""
        daemon.discover_and_verify_eur_giants(None)
        scanner = daemon.QuantMarketScanner()
        intel = daemon.HybridUncappedIntelligence()

        # 1) Caso Reale Pomeriggio 16/11 (es. IFXd_EQ / ADYENa_EQ / DBKd_EQ):
        # Mattina bassa + picco di metà giornata alzano/ancorano il VWAP attorno a ~100.04, poi nel pomeriggio il titolo
        # precipita dall'alto (100.90 -> 99.96) con pendenza 15m/30m negativa e Signed ER < 0, stampando una singola
        # micro-candela verde fino a 100.03 (proprio sul VWAP: vwap_dist_pct >= -0.05%, RSI ~ 45..52, entry_hook_confirmed=True).
        falling_through_vwap_closes = [
            98.60, 98.75, 98.90, 99.05, 99.25, 99.50, 99.80, 100.10, 100.45, 100.80,
            100.68, 100.56, 100.45, 100.35, 100.25, 100.16, 100.08, 100.00, 99.93, 100.02,
        ]
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(_make_yahoo_payload(falling_through_vwap_closes))):
            m_knife = scanner.fetch_5m_metrics("IFXd_EQ")
        self.assertTrue(m_knife["entry_hook_confirmed"])
        self.assertGreaterEqual(m_knife["vwap_dist_pct"], -0.05)
        self.assertGreaterEqual(m_knife["rsi_5m"], 40.0)
        self.assertLess(m_knife["slope_15m_pct"], 0.0)
        self.assertLess(m_knife["slope_30m_pct"], 0.0)
        self.assertLess(m_knife["signed_kaufman_er"], 0.0)
        # Né score_momentum né score_pullback né strong_for_overnight possono attivarsi su un vettore in caduta!
        self.assertEqual(m_knife["quant_buy_score"], 0.0)
        self.assertFalse(m_knife["strong_for_overnight"])

        # 2) Caso V-Reversal Fresco a 15m dopo discesa a 50m (signed_kaufman_er < 0 ma slope_15m > 0):
        # Non viene bloccato in mercato calmo, ma NON riceve bonus ER positivo fittizio né può forzare il Macro Crash Shield!
        v_reversal_closes = [
            100.60, 100.55, 100.50, 100.45, 100.40, 100.35, 100.30, 100.25, 100.20, 100.30,
            100.24, 100.18, 100.12, 100.06, 100.00, 99.96, 100.02, 100.08, 100.14, 100.22,
        ]
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(_make_yahoo_payload(v_reversal_closes))):
            m_vrev = scanner.fetch_5m_metrics("SAPd_EQ")
            m_vrev["price_feed_source"] = "GETTEX_STREAMING_0S"
        self.assertLess(m_vrev["signed_kaufman_er"], 0.0)
        self.assertGreater(m_vrev["slope_15m_pct"], 0.0)
        self.assertGreater(m_vrev["quant_buy_score"], 65.0)
        self.assertFalse(m_vrev["strong_for_overnight"])

        reg_us_open = {"allow_new_buys": True, "is_midday_sniper_window": False, "us_market_live": True}
        ov_calm = {"allow_overnight_hold": True, "nasdaq_change_pct": 0.15, "sp500_change_pct": 0.10, "dax_change_pct": 0.20, "vix_fear_change_pct": -1.0, "vix_level": 15.5}
        ov_crash_16nov = {"allow_overnight_hold": False, "nasdaq_change_pct": -1.90, "sp500_change_pct": -1.35, "dax_change_pct": -1.18, "vix_fear_change_pct": 9.5, "vix_level": 20.4}
        self.assertTrue(intel.is_macro_crash_shield_active(reg_us_open, ov_crash_16nov))
        self.assertTrue(intel.is_eligible_entry_candidate(m_vrev, reg_us_open, ov_calm))
        self.assertFalse(intel.is_eligible_entry_candidate(m_vrev, reg_us_open, ov_crash_16nov))

        # 3) Valley Hook in ipervenduto profondo (RSI <= 34): preservato al 100% in regime normale, bloccato sotto Crash USA:
        valley_closes = [
            100.0, 100.05, 100.1, 100.12, 100.1, 100.08, 100.05, 100.0, 99.95, 99.90,
            99.85, 99.82, 99.80, 99.78, 99.76, 99.74, 99.72, 99.70, 99.68, 99.84,
        ]
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(_make_yahoo_payload(valley_closes))):
            m_valley = scanner.fetch_5m_metrics("ASMLa_EQ")
            m_valley["price_feed_source"] = "GETTEX_STREAMING_0S"
        self.assertLessEqual(m_valley["rsi_5m"], 34.0)
        self.assertGreater(m_valley["quant_buy_score"], 75.0)
        self.assertFalse(m_valley["strong_for_overnight"])
        self.assertTrue(intel.is_eligible_entry_candidate(m_valley, reg_us_open, ov_calm))
        self.assertFalse(intel.is_eligible_entry_candidate(m_valley, reg_us_open, ov_crash_16nov))

        # 4) Autentico Leader in Forza Relativa Contro-Mercato (vwap >= +0.10%, signed_er >= +0.20, 15m/30m > 0, vicino ai massimi):
        # Supera legittimamente lo Scudo Anti-Crollo Macro anche durante Nasdaq -1,90%!
        rs_leader_closes = [
            98.90, 99.10, 99.30, 99.55, 99.80, 100.05, 100.25, 100.40, 100.28, 100.18,
            100.32, 100.22, 100.36, 100.24, 100.38, 100.26, 100.40, 100.32, 100.26, 100.44,
        ]
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResp(_make_yahoo_payload(rs_leader_closes))):
            m_leader = scanner.fetch_5m_metrics("DTGd_EQ")
            m_leader["price_feed_source"] = "GETTEX_STREAMING_0S"
        self.assertGreaterEqual(m_leader["vwap_dist_pct"], 0.10)
        self.assertGreaterEqual(m_leader["signed_kaufman_er"], 0.20)
        self.assertGreater(m_leader["slope_15m_pct"], 0.0)
        self.assertGreater(m_leader["slope_30m_pct"], 0.0)
        self.assertTrue(m_leader["strong_for_overnight"])
        self.assertGreater(m_leader["quant_buy_score"], 75.0)
        self.assertTrue(intel.is_eligible_entry_candidate(m_leader, reg_us_open, ov_crash_16nov))

    def test_33_c1_asymmetric_overnight_carry_and_0905_morning_cull(self):
        """Invariante #33: Soluzione C1 (Sera Lun-Gio custodisce solo verdi >= VWAP, Venerdì/Crash 100% flat; Mattina 09:05 taglia negativi/lenti senza penalità -22pt o ban 60m)."""
        daemon.discover_and_verify_eur_giants(None)
        real_dt = datetime.datetime

        intel = daemon.HybridUncappedIntelligence()
        ov_ok = {
            "allow_overnight_hold": True,
            "nasdaq_change_pct": 0.35,
            "sp500_change_pct": 0.25,
            "dax_change_pct": 0.20,
            "vix_fear_change_pct": -1.2,
            "vix_level": 15.6,
            "us_indices_live_today": True,
        }
        ov_crash = dict(ov_ok, nasdaq_change_pct=-1.85, sp500_change_pct=-1.30, vix_fear_change_pct=9.5, vix_level=20.4)

        m_green_vwap = {
            "atr_5m_volatility_pct": 0.20,
            "elastic_shield_act_raw": 0.0068,
            "elastic_shield_pull_raw": 0.0016,
            "fase_onda_sinusoidale": "SUPER_TREND_VERO_POSITIVO_BREAKOUT",
            "strong_for_overnight": True,
            "green_hook_confirmed": True,
            "has_fresh_intraday_feed": True,
            "vwap_dist_pct": 0.14,
            "rsi_5m": 56.0,
            "live_price_eur": 100.22,
            "quant_buy_score": 82.0,
        }
        m_sub_vwap = dict(m_green_vwap, vwap_dist_pct=-0.08, green_hook_confirmed=False, strong_for_overnight=False)

        # 1) Sera Lunedì-Giovedì (17:26 CET): taglia rossi e sotto-VWAP, custodisce solo vincitore sano >= VWAP;
        #    sotto Crash Macro USA o di Venerdì sera chiude il 100% anche dei vincitori!
        dt_thu_1726 = real_dt(2026, 11, 19, 17, 26, 0, tzinfo=daemon.MARKET_TZ)  # Giovedì
        dt_fri_1726 = real_dt(2026, 11, 20, 17, 26, 0, tzinfo=daemon.MARKET_TZ)  # Venerdì
        reg_thu_1726 = intel.get_intraday_regime(dt_thu_1726)
        reg_fri_1726 = intel.get_intraday_regime(dt_fri_1726)

        intel.position_open_time["SAPd_EQ"] = (dt_thu_1726 - datetime.timedelta(hours=1)).timestamp()
        self.assertIn(
            "CHIUSURA SERALE SELETTIVA C1 17:25",
            intel.evaluate_uncapped_exit("SAPd_EQ", -0.0015, reg_thu_1726, 0.0, ov_ok, m_green_vwap) or "",
        )
        self.assertIn(
            "CHIUSURA SERALE SELETTIVA C1 17:25",
            intel.evaluate_uncapped_exit("SAPd_EQ", 0.0015, reg_thu_1726, 0.0, ov_ok, m_sub_vwap) or "",
        )
        self.assertIsNone(
            intel.evaluate_uncapped_exit("SAPd_EQ", 0.0022, reg_thu_1726, 0.0, ov_ok, m_green_vwap)
        )
        self.assertIn(
            "CHIUSURA SERALE C1 ANTI-CROLLO MACRO 17:25",
            intel.evaluate_uncapped_exit("SAPd_EQ", 0.0022, reg_thu_1726, 0.0, ov_crash, m_green_vwap) or "",
        )
        self.assertIn(
            "CHIUSURA INTEGRALE PRE-WEEKEND 17:25",
            intel.evaluate_uncapped_exit("SAPd_EQ", 0.0022, reg_fri_1726, 0.0, ov_ok, m_green_vwap) or "",
        )

        # 2) Persistenza notturna su disco (08:50 CET boot VM) + Taglio Mattutino 09:02 vs 09:06:
        #    Anche se giovedì il picco era +0.46% (PRE_SHIELD_1A armato), alle 09:02 un lieve -0.06% attende le 09:05
        #    (evitando lo spread d'asta XETRA), mentre un gap-down profondo -0.35% taglia subito alle 09:02!
        state_payload = {
            "timestamp": "2026-11-19T17:35:00+01:00",
            "cartucce_4x25_eur": [
                {
                    "slot": 1,
                    "ticker": "SAPd_EQ",
                    "status": "ESEGUITA_IN_PORTAFOGLIO",
                    "avg_price_eur": 100.00,
                    "current_price_eur": 100.12,
                    "peak_pnl_pct": 0.46,
                    "opened_at_ts": real_dt(2026, 11, 19, 16, 10, 0, tzinfo=daemon.MARKET_TZ).timestamp(),
                    "eod_ref_price_eur": 100.12,
                }
            ],
        }
        with open(self._tmp_bot_state, "w", encoding="utf-8") as f:
            json.dump(state_payload, f)

        dt_fri_0902 = real_dt(2026, 11, 20, 9, 2, 0, tzinfo=daemon.MARKET_TZ)
        dt_fri_0906 = real_dt(2026, 11, 20, 9, 6, 0, tzinfo=daemon.MARKET_TZ)
        intel_reloaded = daemon.HybridUncappedIntelligence()
        self.assertAlmostEqual(intel_reloaded.eod_ref_price.get("SAPd_EQ", 0.0), 100.12, places=2)

        reg_0902 = intel_reloaded.get_intraday_regime(dt_fri_0902)
        reg_0906 = intel_reloaded.get_intraday_regime(dt_fri_0906)

        m_open_mild_red = dict(m_sub_vwap, live_price_eur=99.94)
        self.assertIsNone(
            intel_reloaded.evaluate_uncapped_exit("SAPd_EQ", -0.0006, reg_0902, 0.0, ov_ok, m_open_mild_red)
        )
        m_open_deep_gap = dict(m_sub_vwap, live_price_eur=99.65)
        self.assertIn(
            "TAGLIO MATTUTINO C1 - GAP-DOWN PROFONDO APERTURA",
            intel_reloaded.evaluate_uncapped_exit("SAPd_EQ", -0.0035, reg_0902, 0.0, ov_ok, m_open_deep_gap) or "",
        )

        # Alle 09:06 CET (candela 5m chiusa):
        # - Negativa in totale (-0.06%) -> taglio istantaneo!
        self.assertIn(
            "TAGLIO MATTUTINO C1 - NEGATIVA IN APERTURA",
            intel_reloaded.evaluate_uncapped_exit("SAPd_EQ", -0.0006, reg_0906, 0.0, ov_ok, m_open_mild_red) or "",
        )
        # - Ancora positiva sul prezzo medio (+0.16% = 100.16), ma scesa nella notte da 100.46 (-0.30% notturno) senza rimbalzo -> taglio istantaneo!
        intel_reloaded.eod_ref_price["SAPd_EQ"] = 100.46
        m_overnight_drop = dict(m_sub_vwap, live_price_eur=100.16)
        self.assertIn(
            "TAGLIO MATTUTINO C1 - NEGATIVA IN APERTURA",
            intel_reloaded.evaluate_uncapped_exit("SAPd_EQ", 0.0016, reg_0906, 0.0, ov_ok, m_overnight_drop) or "",
        )
        # - Positiva ma lenta (+0.08% < +0.12%) oppure +0.24% senza uncino verde -> taglio immediato per liberare la cartuccia!
        m_slow_green = dict(m_green_vwap, live_price_eur=100.08)
        self.assertIn(
            "TAGLIO MATTUTINO C1 - POSIZIONE NOTTURNA LENTA/STALLO",
            intel_reloaded.evaluate_uncapped_exit("SAPd_EQ", 0.0008, reg_0906, 0.0, ov_ok, m_slow_green) or "",
        )
        m_stalled_plus = dict(m_sub_vwap, live_price_eur=100.55)
        self.assertIn(
            "TAGLIO MATTUTINO C1 - POSIZIONE NOTTURNA LENTA/STALLO",
            intel_reloaded.evaluate_uncapped_exit("SAPd_EQ", 0.0055, reg_0906, 0.0, ov_ok, m_stalled_plus) or "",
        )
        # - Gap-Up veloce con spinta verde sopra VWAP (+0.62%, green_hook=True, vwap=+0.18%, 100.46 -> 100.62) -> CORRE SENZA TETTO!
        m_fast_gap_up = dict(m_green_vwap, live_price_eur=100.62, vwap_dist_pct=0.18)
        self.assertIsNone(
            intel_reloaded.evaluate_uncapped_exit("SAPd_EQ", 0.0062, reg_0906, 0.0, ov_ok, m_fast_gap_up)
        )
        # - Nuova posizione intraday aperta stamattina alle 09:03 (+0.04%): NON è portata dalla notte -> mai toccata dal taglio C1!
        intel_reloaded.position_open_time["NVDd_EQ"] = real_dt(2026, 11, 20, 9, 3, 0, tzinfo=daemon.MARKET_TZ).timestamp()
        self.assertIsNone(
            intel_reloaded.evaluate_uncapped_exit("NVDd_EQ", 0.0004, reg_0906, 0.0, ov_ok, m_slow_green)
        )

        # 3) Verifica ciclo completo: un taglio mattutino C1 in rosso (-0.18%) registra la minusvalenza LIFO esatta
        #    con overnight_carry_cleanup=True, ZERO penalità -22pt nello scanner e ZERO ban da 60m!
        class _MorningCullBroker:
            def __init__(self):
                self.positions = [{"ticker": "SAPd_EQ", "quantity": 0.25, "averagePrice": 100.00, "currentPrice": 99.82, "ppl": -0.05}]
                self.sells = []

            def get_open_positions(self):
                return list(self.positions)

            def get_pending_orders(self):
                return []

            def get_account_cash(self):
                return {"result": 0.0, "free": 75.0}

            def place_market_order(self, ticker: str, quantity: float):
                self.sells.append((ticker, quantity))
                self.positions = []
                return {"id": "CULL_SAP"}

        cull_broker = _MorningCullBroker()
        cull_bot = daemon.Trading212AutonomousBot(client=cull_broker, total_budget_eur=100.0, cartridges=4, annual_target_pct=0.30)
        cull_bot.tax_tracker = ItalianTaxTracker730(filepath=self._tmp_tax_path)
        cull_bot.tax_tracker.data["lotti_aperti_lifo"]["SAPd_EQ"] = [{
            "timestamp": "2026-11-19T16:10:00+01:00",
            "ticker": "SAPd_EQ",
            "isin": "DE0007164600",
            "quantity": 0.25,
            "price_eur": 100.00,
            "total_eur": 25.00,
        }]
        cull_bot.tax_tracker.save()
        cull_sc = daemon.QuantMarketScanner()
        cull_sc.scan_all = lambda **kw: {"SAPd_EQ": dict(m_open_mild_red, ticker="SAPd_EQ", name="SAP", squad="SQUADRA_2_CAVALCA_ONDA", sector="SOFTWARE_CLOUD", day_range_pct=1.2, rvol_ratio=1.1, entry_hook_confirmed=False)}

        class _DummyRadar33:
            def evaluate_overnight_wave(self):
                return ov_ok

        with patch("datetime.datetime") as mock_dt, patch("time.time", return_value=dt_fri_0906.timestamp()):
            mock_dt.now.side_effect = lambda tz=None: dt_fri_0906.astimezone(tz) if tz else dt_fri_0906.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            mock_dt.fromisoformat.side_effect = real_dt.fromisoformat
            intel_cull = daemon.HybridUncappedIntelligence()
            daemon.run_cycle(cull_bot, intel_cull, cull_sc, _DummyRadar33(), 1)

        self.assertEqual(len(cull_broker.sells), 1)
        last_op = cull_bot.tax_tracker.data["operazioni_chiuse"][-1]
        self.assertTrue(last_op.get("overnight_carry_cleanup"))
        self.assertLess(last_op["risultato_fiscale_eur"], 0.0)
        self.assertFalse(intel_cull.last_sell_was_loss.get("SAPd_EQ", False))

        # Dopo i soli 15 minuti fisiologici (09:22 CET = +16m, ben prima dei 60m di uno stop intraday!), SAPd_EQ è già riacquistabile senza penalità -22pt!
        dt_fri_0922 = real_dt(2026, 11, 20, 9, 22, 0, tzinfo=daemon.MARKET_TZ)
        rally_closes = [99.70 + i * 0.04 for i in range(20)]
        with patch("datetime.datetime") as mock_dt, patch("time.time", return_value=dt_fri_0922.timestamp()), patch(
            "urllib.request.urlopen", return_value=_FakeHTTPResp(_make_yahoo_payload(rally_closes))
        ):
            mock_dt.now.side_effect = lambda tz=None: dt_fri_0922.astimezone(tz) if tz else dt_fri_0922.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            mock_dt.fromisoformat.side_effect = real_dt.fromisoformat
            intel_cull.sync_from_tax_data(cull_bot.tax_tracker.data)
            self.assertTrue(intel_cull.can_buy_ticker("SAPd_EQ", 100.46, 0.15))
            m_clean = daemon.QuantMarketScanner().fetch_5m_metrics("SAPd_EQ", tax_data=cull_bot.tax_tracker.data)
        self.assertFalse(m_clean["had_loss_today"])

    def test_34_v116_anti_spread_8_of_8_blindatura_and_cash_regime_leader_rs(self):
        """Invariante #34: Blindatura Completa V11.6 Opzione A (8/8 bug risolti + Cash-Regime Leader RS + 4/4 Cartucce su 4 Settori Distinti Zero Ping-Pong)."""
        daemon.discover_and_verify_eur_giants(None)
        real_dt = datetime.datetime

        # FIX #1: Cartucce Simmetriche 4/4 proporzionali al capitale effettivo (94.36 EUR -> 4 x 23.59 EUR, 112.00 EUR -> 4 x 28.00 EUR)
        eff_94, slot_94, min_94 = daemon._compute_effective_budget_and_cartridge(100.0, -5.64, 4)
        self.assertAlmostEqual(eff_94, 94.36, places=2)
        self.assertAlmostEqual(slot_94, 23.59, places=2)
        self.assertAlmostEqual(slot_94 * 4, eff_94, places=2)
        self.assertAlmostEqual(min_94, 16.98, places=2)

        eff_112, slot_112, _ = daemon._compute_effective_budget_and_cartridge(100.0, 12.0, 4)
        self.assertAlmostEqual(eff_112, 112.0, places=2)
        self.assertAlmostEqual(slot_112, 28.0, places=2)

        # FIX #2: Quantizzazione monotona math.floor (zero sforamento cassa per round-half-even) + pacing >= 2.05s su Limit BUY
        for alloc_eur in [23.59, 18.87, 25.00]:
            for px in [17.83, 148.55, 212.75, 720.40, 862.50]:
                q4 = Trading212Client.quantize_buy_quantity_floor(alloc_eur, px, decimals=4)
                q2 = Trading212Client.quantize_buy_quantity_floor(alloc_eur, px, decimals=2)
                self.assertGreater(q4, 0.0)
                self.assertLessEqual(round(q4 * px, 8), alloc_eur + 1e-9)
                self.assertLessEqual(round(q2 * px, 8), alloc_eur + 1e-9)

        dummy_client = Trading212Client(api_key="k", api_secret="s", mode="demo")
        dummy_client._last_limit_order_ts = 1000.0
        slept_calls = []
        with patch("time.monotonic", side_effect=[1000.5, 1002.1]), patch(
            "time.sleep", side_effect=lambda s: slept_calls.append(s)
        ), patch.object(dummy_client, "_request", return_value={"id": "LIM_OK"}):
            dummy_client.place_limit_order("SAPd_EQ", 0.11, 210.0)
        self.assertEqual(len(slept_calls), 1)
        self.assertAlmostEqual(slept_calls[0], 1.55, places=2)

        # FIX #3: Continuità C0 bilaterale della curva salva-utile V11.6 (shield_act >= 0.0145) + chiusura gap PRE_SHIELD_1A (< -0.05%)
        intel = daemon.HybridUncappedIntelligence()
        st_below, fl_below = intel.compute_profit_protection_floor(0.0099, 0.0160, 0.0045, 0.0020, False)
        self.assertEqual(st_below, "NONE")
        self.assertIsNone(fl_below)

        st_be, fl_be = intel.compute_profit_protection_floor(0.0100, 0.0160, 0.0045, 0.0020, False)
        self.assertEqual(st_be, "PRE_SHIELD_1A")
        self.assertAlmostEqual(fl_be, 0.0030, places=4)

        _, fl_1299 = intel.compute_profit_protection_floor(0.01299, 0.0160, 0.0045, 0.0020, False)
        _, fl_1300 = intel.compute_profit_protection_floor(0.0130, 0.0160, 0.0045, 0.0020, False)
        _, fl_1599 = intel.compute_profit_protection_floor(0.01599, 0.0160, 0.0045, 0.0020, False)
        st_trail, fl_1600 = intel.compute_profit_protection_floor(0.0160, 0.0160, 0.0045, 0.0020, False)
        self.assertAlmostEqual(fl_1299, fl_1300, places=3)  # C0 a +1.30%
        self.assertAlmostEqual(fl_1599, fl_1600, places=3)  # C0 a +1.60%
        self.assertEqual(st_trail, "UNCAPPED_SHIELD_2")
        self.assertAlmostEqual(fl_1600, 0.0115, places=4)

        # Flash-drop da picco +1.05% direttamente a -0.22% con rottura VWAP: PRE_SHIELD_1A scatta senza buchi!
        t_open_flash = real_dt(2026, 11, 18, 10, 0, 0, tzinfo=daemon.MARKET_TZ).timestamp()
        intel.peak_pnl_pct["SAPd_EQ"] = 0.0105
        intel.position_open_time["SAPd_EQ"] = t_open_flash
        reg_open = {"allow_new_buys": True, "is_midday_sniper_window": False, "is_morning_gap_harvest": False, "is_pre_close_window": False, "us_market_live": True, "hm": 620, "ny_hm": 600, "now_date_iso": "2026-11-18"}
        m_broken = {
            "atr_5m_volatility_pct": 0.20, "elastic_shield_act_raw": 0.0160, "elastic_shield_pull_raw": 0.0045,
            "green_hook_confirmed": False, "vwap_dist_pct": -0.18, "rsi_5m": 41.0,
        }
        with patch("time.time", return_value=t_open_flash + 900.0):
            exit_flash = intel.evaluate_uncapped_exit("SAPd_EQ", -0.0022, reg_open, 0.0, {}, m_broken, 0.0, False)
        self.assertIsNotNone(exit_flash)
        self.assertIn("BLINDATURA #1A", exit_flash)

        # FIX #5: VIX alto ma in crollo (VIX=28.5, vix_chg=-11.0% = VIX-Crush Rally) NON attiva falso crash shield;
        #         mentre un vero tape crash 0s GETTEX (EU32/US7) lo attiva istantaneamente anche con Yahoo ritardato!
        ov_vix_crush = {
            "allow_overnight_hold": True, "nasdaq_change_pct": 0.85, "sp500_change_pct": 0.70,
            "dax_change_pct": 0.65, "vix_fear_change_pct": -11.0, "vix_level": 28.5,
        }
        calm_tape = {"cash_regime_enforced": True, "breadth_above_vwap": 0.65, "eu_from_open_pct": 0.35, "eu_slope_30m_pct": 0.14, "us_from_ny_open_pct": 0.40, "us_slope_30m_pct": 0.18}
        crash_tape_0s = {"cash_regime_enforced": True, "breadth_above_vwap": 0.12, "eu_from_open_pct": -0.95, "eu_slope_30m_pct": -0.32, "us_from_ny_open_pct": -1.05, "us_slope_30m_pct": -0.35}
        self.assertFalse(intel.is_macro_crash_shield_active(reg_open, ov_vix_crush, calm_tape))
        self.assertTrue(intel.is_macro_crash_shield_active(reg_open, ov_vix_crush, crash_tape_0s))

        # FIX #6: Scudo Whipsaw Pre-Bell & Prima Candela 5m NYSE (08:36-09:34 ET bloccata, 09:35 ET aperta)
        dt_0932_et = real_dt(2026, 11, 18, 15, 32, 0, tzinfo=daemon.MARKET_TZ)  # 09:32 ET
        dt_0935_et = real_dt(2026, 11, 18, 15, 35, 0, tzinfo=daemon.MARKET_TZ)  # 09:35 ET
        self.assertTrue(intel.get_intraday_regime(dt_0932_et)["is_midday_sniper_window"])
        self.assertFalse(intel.get_intraday_regime(dt_0935_et)["is_midday_sniper_window"])
        self.assertEqual(intel.get_intraday_regime(dt_0935_et)["code"], "FASE_3_ONDA_WALL_STREET_SENZA_TETTO")

        # FIX #7: Orizzonte Anti-Rumore +/-1.40%..1.60% (oscillazione fisiologica -0.95% tenuta senza stop suicida; invalidazione -1.45% tagliata)
        intel.peak_pnl_pct["NVDd_EQ"] = 0.0010
        intel.position_open_time["NVDd_EQ"] = t_open_flash
        with patch("time.time", return_value=t_open_flash + 900.0):  # +15 min
            self.assertIsNone(intel.evaluate_uncapped_exit("NVDd_EQ", -0.0095, reg_open, 0.0, {}, m_broken, 0.0, False))
            cut_145 = intel.evaluate_uncapped_exit("NVDd_EQ", -0.0145, reg_open, 0.0, {}, m_broken, 0.0, False)
        self.assertIsNotNone(cut_145)
        self.assertIn("TAGLIO CHIRURGICO TESI INVALIDATA", cut_145)

        # FIX #8: Selettore Cash-Regime Leader RS (sample >= 8) + 4/4 Cartucce su 4 Settori Markowitz Distinti + Zero Ping-Pong (max 1 sparo/cartuccia/giorno)!
        def _mk_tape_stock(
            tkr: str,
            vwap: float,
            open_chg: float,
            sl30: float,
            score: float = 82.0,
            us: bool = False,
            sector: str = "",
        ) -> dict:
            sec = sector or daemon.ASSET_PROFILES.get(tkr, {}).get("sector", f"SEC_{tkr}")
            return {
                "ticker": tkr, "name": tkr, "squad": "SQUADRA_2_CAVALCA_ONDA", "sector": sec,
                "is_us_giant": us, "price_feed_source": "GETTEX_STREAMING_0S", "live_price_eur": 100.0,
                "vwap_dist_pct": vwap, "intraday_open_chg_pct": open_chg, "ny_open_chg_pct": open_chg if us else 0.0,
                "slope_15m_pct": 0.18, "slope_30m_pct": sl30, "signed_kaufman_er": 0.42, "kaufman_efficiency_ratio": 0.42,
                "rsi_5m": 56.0, "rvol_ratio": 1.45, "atr_5m_volatility_pct": 0.22, "day_range_pct": 1.60,
                "elastic_shield_act_raw": 0.0160, "elastic_shield_pull_raw": 0.0045,
                "score_momentum": max(0.0, score - 4.0), "score_pullback": 0.0, "velocity_bonus": 4.0 if score > 0 else 0.0, "quant_buy_score": score,
                "true_relative_strength": vwap >= 0.05 and sl30 > 0, "strong_for_overnight": vwap >= 0.05 and sl30 > 0,
                "green_hook_confirmed": vwap >= 0.0, "entry_hook_confirmed": vwap >= 0.0, "had_loss_today": False,
                "has_fresh_intraday_feed": True, "fase_onda_sinusoidale": "SUPER_TREND_VERO_POSITIVO_BREAKOUT",
            }

        # (8a) Mercato laterale/choppy (breadth 3/10 = 0.30 < 0.58): 0 ingressi autorizzati in Cash-Regime!
        choppy_universe = {f"T{i}d_EQ": _mk_tape_stock(f"T{i}d_EQ", 0.18 if i < 3 else -0.15, 0.20 if i < 3 else -0.25, 0.12 if i < 3 else -0.10) for i in range(10)}
        tape_choppy = daemon._compute_intraday_0s_tape(choppy_universe)
        self.assertTrue(tape_choppy["cash_regime_enforced"])
        self.assertFalse(
            intel.is_eligible_entry_candidate(
                choppy_universe["T0d_EQ"], reg_open, ov_vix_crush,
                market_breadth_above_vwap=tape_choppy["breadth_above_vwap"], intraday_0s_tape=tape_choppy,
            )
        )

        # (8a-bis) Migrazione seamless hot-reload (es. BMWd_EQ acquistata alle 09:19 prima di daily_entries_sectors):
        #          ricostruisce automaticamente AUTOMOTIVE_PREMIUM da lotti_aperti_lifo senza perdere il vincolo settoriale!
        intel_legacy = daemon.HybridUncappedIntelligence()
        legacy_tx = {
            "daily_entries_date": "2026-11-19",
            "daily_entries_count": 1,
            "lotti_aperti_lifo": {
                "BMWd_EQ": [{"timestamp": "2026-11-19T09:19:52", "ticker": "BMWd_EQ", "quantity": 0.47, "price_eur": 54.8723}],
            },
            "operazioni_chiuse": [],
        }
        self.assertEqual(
            intel_legacy.get_today_used_sectors("2026-11-19", legacy_tx),
            {daemon.ASSET_PROFILES["BMWd_EQ"]["sector"]},
        )
        self.assertEqual(legacy_tx.get("daily_entries_sectors"), [daemon.ASSET_PROFILES["BMWd_EQ"]["sector"]])

        # (8b) Mercato rialzista sano (breadth 8/10 = 0.80 >= 0.58, EU open +0.28%):
        #      - Ciclo 1 (09:45 CET): 3 Leader partono su 3 settori distinti (SAPd_EQ, NVDd_EQ, ASMLa_EQ), mentre AMDd_EQ (84.5 pt, stesso settore di NVDd_EQ) viene saltata!
        #      - Ciclo 2 (10:15 CET): NVDd_EQ viene venduta in profitto liberando cassa e slot; partono AMDd_EQ (84.5 pt, stesso settore già usato oggi!),
        #        SIEd_EQ (80.0 pt, 4° settore distinto) e DTGd_EQ (78.0 pt, 5° settore).
        #        Il motore DEVE:
        #          1) bloccare AMDd_EQ (settore SEMICONDUTTORI_AI già usato oggi anche se NVDd_EQ è ormai chiusa -> Zero Ping-Pong settoriale!);
        #          2) acquistare SIEd_EQ come 4ª cartuccia sul 4° settore distinto;
        #          3) bloccare DTGd_EQ nonostante ci sia uno slot libero (4/4 spari giornalieri raggiunti -> max 1 sparo/cartuccia/giorno!);
        #          4) mantenere il blocco 4/4 anche dopo un riavvio completo della VM Cloud (Ciclo 3).
        bull_wave_1 = {
            "BMWd_EQ": _mk_tape_stock("BMWd_EQ", 0.12, -0.20, 0.24, score=88.0),  # Falso Leader rosso dall'apertura (-0.20% < eu_open_c): VIETATO!
            "SAPd_EQ": _mk_tape_stock("SAPd_EQ", 0.20, 0.35, 0.22, score=86.0),
            "NVDd_EQ": _mk_tape_stock("NVDd_EQ", 0.22, 0.40, 0.25, score=85.0, us=True),
            "AMDd_EQ": _mk_tape_stock("AMDd_EQ", 0.21, 0.38, 0.24, score=84.5, us=True),  # Stesso settore di NVDd_EQ!
            "ASMLa_EQ": _mk_tape_stock("ASMLa_EQ", 0.18, 0.32, 0.20, score=84.0),
            "SIEd_EQ": _mk_tape_stock("SIEd_EQ", 0.03, 0.20, 0.08, score=52.0),  # Non ancora in breakout nel Ciclo 1
            "DTGd_EQ": _mk_tape_stock("DTGd_EQ", 0.03, 0.18, 0.07, score=51.0),
            "IFXd_EQ": _mk_tape_stock("IFXd_EQ", 0.04, 0.22, 0.08, score=53.0),
            "EOANd_EQ": _mk_tape_stock("EOANd_EQ", 0.04, 0.20, 0.06, score=50.0),
            "MRKd_EQ": _mk_tape_stock("MRKd_EQ", -0.10, -0.05, -0.04, score=0.0),
            "DBKd_EQ": _mk_tape_stock("DBKd_EQ", -0.08, -0.04, -0.03, score=0.0),
        }

        class _V116CashBroker:
            def __init__(self):
                self.positions = []
                self.free_cash = 94.36
                self.realized_res = -5.64
                self.buys = []
                self.sells = []

            def get_open_positions(self):
                return list(self.positions)

            def get_pending_orders(self):
                return []

            def get_account_cash(self):
                return {"result": round(self.realized_res, 2), "free": round(self.free_cash, 2)}

            def place_limit_order(self, ticker: str, quantity: float, limit_price: float, time_validity: str = "DAY"):
                assert quantity > 0.0
                cost = round(quantity * limit_price, 4)
                self.free_cash -= cost
                self.buys.append((ticker, quantity, limit_price, cost))
                self.positions.append({"ticker": ticker, "quantity": quantity, "averagePrice": limit_price, "currentPrice": limit_price, "ppl": 0.0})
                return {"id": f"BUY_{ticker}"}

            def cancel_order(self, order_id):
                return None

            def place_market_order(self, ticker: str, quantity: float):
                if quantity < 0:
                    matched = next((p for p in self.positions if p["ticker"] == ticker), None)
                    if matched is not None:
                        proceeds = round(abs(quantity) * float(matched["currentPrice"]), 4)
                        pnl = round((float(matched["currentPrice"]) - float(matched["averagePrice"])) * abs(quantity), 4)
                        self.free_cash += proceeds
                        self.realized_res += pnl
                        self.positions = [p for p in self.positions if p["ticker"] != ticker]
                        self.sells.append((ticker, abs(quantity), float(matched["currentPrice"])))
                return {"id": f"MKT_{ticker}"}

        v116_broker = _V116CashBroker()
        v116_bot = daemon.Trading212AutonomousBot(client=v116_broker, total_budget_eur=100.0, cartridges=4, annual_target_pct=0.30)
        v116_bot.tax_tracker = ItalianTaxTracker730(filepath=self._tmp_tax_path)
        v116_bot.tax_tracker.reconcile_certified_cash_result(-5.64)

        active_wave = [bull_wave_1]
        v116_scanner = daemon.QuantMarketScanner()
        v116_scanner.scan_all = lambda **kw: active_wave[0]

        class _DummyRadar34:
            def evaluate_overnight_wave(self):
                # Simula anche il caso reale di lunedì mattina (us_indices_live_today=False, vix_fear_change_pct congelato a +8.58% da venerdì):
                # con borsa USA ancora chiusa, un VIX congelato da venerdì NON deve accecare il relief-rally europeo (Breadth >= 58%, eu_open >= +0.12%)!
                return {
                    "verdict": "OK", "allow_overnight_hold": False, "us_indices_live_today": False,
                    "nasdaq_change_pct": -5.28, "sp500_change_pct": -3.70, "dax_change_pct": 0.62,
                    "vix_fear_change_pct": 8.58, "vix_level": 30.9,
                }

        dt_morn_drive = real_dt(2026, 11, 18, 9, 45, 0, tzinfo=daemon.MARKET_TZ)
        with patch.object(daemon, "LIMIT_FILL_POLL_SEC", 0.0), patch("datetime.datetime") as mock_dt, patch("time.time", return_value=dt_morn_drive.timestamp()):
            mock_dt.now.side_effect = lambda tz=None: dt_morn_drive.astimezone(tz) if tz else dt_morn_drive.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            mock_dt.fromisoformat.side_effect = real_dt.fromisoformat
            intel_v116 = daemon.HybridUncappedIntelligence()
            st1 = daemon.run_cycle(v116_bot, intel_v116, v116_scanner, _DummyRadar34(), 1)

        self.assertEqual([b[0] for b in v116_broker.buys], ["SAPd_EQ", "NVDd_EQ", "ASMLa_EQ"])
        self.assertEqual(st1["daily_entries_count"], 3)
        self.assertEqual(len(st1["daily_entries_sectors"]), 3)

        # Ora alle 10:15 CET: NVDd_EQ è salita a +1.95% e ritraccia a +1.35% (Scudo Mobile incassa in utile e libera slot + cassa!),
        # mentre in panchina accelerano AMDd_EQ (84.5 pt, stesso settore SEMICONDUTTORI_AI già usato oggi!), SIEd_EQ (80.0 pt, 4° settore) e DTGd_EQ (78.0 pt, 5° settore):
        for p_open in v116_broker.positions:
            if p_open["ticker"] == "NVDd_EQ":
                p_open["currentPrice"] = round(float(p_open["averagePrice"]) * 1.0135, 4)
                p_open["ppl"] = round((p_open["currentPrice"] - float(p_open["averagePrice"])) * float(p_open["quantity"]), 2)
        intel_v116.peak_pnl_pct["NVDd_EQ"] = 0.0195

        bull_wave_2 = dict(bull_wave_1)
        bull_wave_2["NVDd_EQ"] = dict(bull_wave_1["NVDd_EQ"], live_price_eur=101.35, green_hook_confirmed=False, entry_hook_confirmed=False)
        bull_wave_2["SIEd_EQ"] = _mk_tape_stock("SIEd_EQ", 0.16, 0.30, 0.18, score=80.0)
        bull_wave_2["DTGd_EQ"] = _mk_tape_stock("DTGd_EQ", 0.15, 0.28, 0.16, score=78.0)
        active_wave[0] = bull_wave_2

        dt_mid_morn = real_dt(2026, 11, 18, 10, 15, 0, tzinfo=daemon.MARKET_TZ)
        with patch.object(daemon, "LIMIT_FILL_POLL_SEC", 0.0), patch("datetime.datetime") as mock_dt, patch("time.time", return_value=dt_mid_morn.timestamp()):
            mock_dt.now.side_effect = lambda tz=None: dt_mid_morn.astimezone(tz) if tz else dt_mid_morn.replace(tzinfo=None)
            mock_dt.fromtimestamp.side_effect = real_dt.fromtimestamp
            mock_dt.fromisoformat.side_effect = real_dt.fromisoformat
            st2 = daemon.run_cycle(v116_bot, intel_v116, v116_scanner, _DummyRadar34(), 2)
            # Simula riavvio completo VM Cloud a metà giornata: deve leggere 4/4 ingressi e i 4 settori già usati oggi da disco e NON sparare un 5° ordine (DTGd_EQ)!
            intel_rebooted = daemon.HybridUncappedIntelligence()
            intel_rebooted.sync_from_tax_data(v116_bot.tax_tracker.data)
            st3 = daemon.run_cycle(v116_bot, intel_rebooted, v116_scanner, _DummyRadar34(), 3)

        self.assertEqual([s[0] for s in v116_broker.sells], ["NVDd_EQ"])
        self.assertEqual([b[0] for b in v116_broker.buys], ["SAPd_EQ", "NVDd_EQ", "ASMLa_EQ", "SIEd_EQ"])
        self.assertNotIn("BMWd_EQ", [b[0] for b in v116_broker.buys])  # Falso Leader rosso dall'apertura (-0.20%) bloccato anche con Score 88!
        self.assertNotIn("AMDd_EQ", [b[0] for b in v116_broker.buys])  # Stesso settore di NVDd_EQ vietato anche dopo chiusura!
        self.assertNotIn("DTGd_EQ", [b[0] for b in v116_broker.buys])  # 5° sparo giornaliero vietato (Zero Ping-Pong)!
        used_sectors_4 = {daemon.ASSET_PROFILES[b[0]]["sector"] for b in v116_broker.buys}
        self.assertEqual(len(used_sectors_4), 4)
        for _, _, _, cost in v116_broker.buys[:3]:
            self.assertLessEqual(cost, 23.59 + 1e-6)
            self.assertGreaterEqual(cost, 23.40)
        self.assertEqual(st2["daily_entries_count"], 4)
        self.assertEqual(st3["daily_entries_count"], 4)
        self.assertEqual(st3["max_daily_new_entries"], 4)
        self.assertEqual(set(st3["daily_entries_sectors"]), used_sectors_4)

    def test_35_dual_momentum_1000e_chinese_wall_bear_shield_and_instant_cashout(self):
        """Invariante #35: Motore #2 Dual Momentum + Oro (1.000 EUR) — Muraglia Cinese 0% overlap, Scudo Bear Market Oro/XEON e Cashout istantaneo."""
        import t212_dual_momentum_1000e as dm

        daemon.discover_and_verify_eur_giants(None)
        # 1) Muraglia Cinese sui ticker: 0 sovrapposizioni tra i 47 Colossi intraday e i 12 strumenti Dual Momentum + Oro
        self.assertTrue(dm.verify_zero_intraday_overlap(set(daemon.EUR_ZERO_FEE_UNIVERSE.keys())))
        self.assertEqual(len(set(dm.DUAL_MOMENTUM_UNIVERSE.keys()) & set(daemon.EUR_ZERO_FEE_UNIVERSE.keys())), 0)

        # 2) Regime Bull: seleziona Top 2 ETF distinti (45%), Top 2 Azioni distinte (30%), Oro (20%), XEON (5%) -> somma = 1.0000
        bull_series = {
            "DBXTd_EQ": [146.0 + i * 0.02 for i in range(252)],
            "4GLDd_EQ": [88.0 + i * 0.08 for i in range(252)],
            "SXRVd_EQ": [1050.0 + i * 1.40 for i in range(252)],
            "QDVEd_EQ": [31.0 + i * 0.035 for i in range(252)],  # stesso sub_group US_TECH_GROWTH di SXRV -> diversifica sul 2° ETF!
            "IS3Rd_EQ": [70.0 + i * 0.08 for i in range(252)],
            "XDEQQd_EQ": [68.0 + i * 0.05 for i in range(252)],
            "IQQ0d_EQ": [66.0 + i * 0.03 for i in range(252)],
            "BRYNd_EQ": [420.0 + i * 0.45 for i in range(252)],
            "LINd_EQ": [410.0 + i * 0.25 for i in range(252)],
            "RENa_EQ": [30.0 + i * 0.03 for i in range(252)],
            "WKLa_EQ": [78.0 + i * 0.02 for i in range(252)],
            "ADa_EQ": [33.0 + i * 0.01 for i in range(252)],
        }
        xeon_m = dm.compute_instrument_momentum_metrics("DBXTd_EQ", bull_series["DBXTd_EQ"], 0.0)
        rf_h = xeon_m["composite_mom_pct"]
        bull_metrics = {t: dm.compute_instrument_momentum_metrics(t, s, rf_h) for t, s in bull_series.items()}
        w_bull, lbl_bull, _ = dm.compute_dual_momentum_target_weights(bull_metrics)
        self.assertAlmostEqual(sum(w_bull.values()), 1.0, places=4)
        self.assertEqual(lbl_bull, "FULL_BULL_MOMENTUM_4_SU_4_ATTIVI")
        self.assertAlmostEqual(w_bull["4GLDd_EQ"], 0.20, places=4)
        self.assertAlmostEqual(w_bull["DBXTd_EQ"], 0.05, places=4)
        # Non deve mai prendere insieme SXRVd_EQ e QDVEd_EQ (stesso sub_group US_TECH_GROWTH)
        self.assertFalse("SXRVd_EQ" in w_bull and "QDVEd_EQ" in w_bull)

        # 3) Regime Bear (tutte le azioni ed ETF sotto SMA_150): 100% protetto in Oro Fisico (35%) + Monetario BCE XEON (65%)!
        bear_series = dict(bull_series)
        for eq_tkr in ("SXRVd_EQ", "QDVEd_EQ", "IS3Rd_EQ", "XDEQQd_EQ", "IQQ0d_EQ", "BRYNd_EQ", "LINd_EQ", "RENa_EQ", "WKLa_EQ", "ADa_EQ"):
            bear_series[eq_tkr] = [100.0 - i * 0.15 for i in range(252)]
        bear_metrics = {t: dm.compute_instrument_momentum_metrics(t, s, rf_h) for t, s in bear_series.items()}
        w_bear, lbl_bear, _ = dm.compute_dual_momentum_target_weights(bear_metrics)
        self.assertAlmostEqual(sum(w_bear.values()), 1.0, places=4)
        self.assertEqual(lbl_bear, "SCUDO_DIFENSIVO_BEAR_MARKET_ORO_E_XEON")
        self.assertEqual(set(w_bear.keys()), {"4GLDd_EQ", "DBXTd_EQ"})
        self.assertAlmostEqual(w_bear["4GLDd_EQ"], 0.35, places=4)
        self.assertAlmostEqual(w_bear["DBXTd_EQ"], 0.65, places=4)

        # 4) Esecuzione reale simulata + Muraglia Cinese contabile + Incasso Immediato 100% (`cashout`)
        class _SharedAccountBroker:
            def __init__(self):
                self.positions = []
                self.free = 4999.71
                self.result = -0.29

            def get_open_positions(self):
                return list(self.positions)

            def get_pending_orders(self):
                return []

            def get_account_cash(self):
                return {"free": round(self.free, 2), "result": round(self.result, 2)}

            def place_limit_order(self, ticker: str, quantity: float, limit_price: float, time_validity: str = "DAY"):
                cost = round(quantity * limit_price, 4)
                self.free -= cost
                existing = next((p for p in self.positions if p["ticker"] == ticker), None)
                if existing:
                    tot_q = round(existing["quantity"] + quantity, 6)
                    existing["averagePrice"] = round((existing["quantity"] * existing["averagePrice"] + cost) / tot_q, 4)
                    existing["quantity"] = tot_q
                    existing["currentPrice"] = limit_price
                else:
                    self.positions.append({"ticker": ticker, "quantity": quantity, "averagePrice": limit_price, "currentPrice": limit_price, "ppl": 0.0})
                return {"id": f"LT_BUY_{ticker}"}

            def cancel_order(self, order_id):
                return None

            def place_market_order(self, ticker: str, quantity: float):
                if quantity < 0:
                    matched = next((p for p in self.positions if p["ticker"] == ticker), None)
                    if matched:
                        sell_q = abs(quantity)
                        cur_px = float(matched["currentPrice"])
                        avg_px = float(matched["averagePrice"])
                        pnl = round((cur_px - avg_px) * sell_q, 2)
                        self.free += round(sell_q * cur_px, 4)
                        self.result = round(self.result + pnl, 2)
                        rem_q = round(float(matched["quantity"]) - sell_q, 6)
                        if rem_q <= 1e-6:
                            self.positions = [p for p in self.positions if p["ticker"] != ticker]
                        else:
                            matched["quantity"] = rem_q
                return {"id": f"LT_SELL_{ticker}"}

        shared_broker = _SharedAccountBroker()
        vault = dm.DualMomentumVault1000E(client=shared_broker, state_path=self._tmp_lt_path, initial_budget_eur=1000.0)
        dt_open = datetime.datetime(2026, 11, 23, 14, 45, 0, tzinfo=daemon.MARKET_TZ)
        with patch.object(dm, "fetch_daily_series_1y", side_effect=lambda t: bull_series[t]):
            st_init = vault.run_rebalance_cycle(now=dt_open, poll_sec=0.0)
        self.assertGreaterEqual(st_init["invested_cost_eur"], 970.0)
        self.assertLessEqual(st_init["invested_cost_eur"], 1000.01)
        self.assertEqual(len(st_init["posizioni_attive"]), 6)

        # Simula apprezzamento +50 EUR sul Vault e incasso integrale 100% su richiesta utente:
        for p_lt in shared_broker.positions:
            p_lt["currentPrice"] = round(float(p_lt["averagePrice"]) * 1.05, 4)
        with patch.object(dm, "fetch_daily_series_1y", side_effect=lambda t: bull_series[t]):
            acts_cashout = vault.cashout(profits_only=False)
        self.assertTrue(len(acts_cashout) >= 6)
        self.assertTrue(vault.state["paused_by_user_cashout"])
        self.assertEqual(len(shared_broker.positions), 0)
        lt_realized = vault.state["realized_net_pnl_eur"]
        self.assertGreater(lt_realized, 40.0)

        # Verifica Muraglia Cinese: il conto condiviso ora espone result = -0.29 + lt_realized,
        # ma il bot intraday da 100 EUR sottrae esattamente lt_realized mantenendo il suo PnL a -0.29 EUR!
        intraday_bot = daemon.Trading212AutonomousBot(client=shared_broker, total_budget_eur=100.0, cartridges=4, annual_target_pct=0.30)
        intraday_bot.tax_tracker = ItalianTaxTracker730(filepath=self._tmp_tax_path)
        intraday_bot.tax_tracker.data["minusvalenze_lorde_eur"] = 0.29
        intraday_bot.tax_tracker._recompute_taxable_summary()
        daemon._sync_certified_cash_safe(intraday_bot, min_interval_sec=0.0)
        net_intraday = round(
            float(intraday_bot.tax_tracker.data["plusvalenze_lorde_eur"])
            - float(intraday_bot.tax_tracker.data["minusvalenze_lorde_eur"]),
            2,
        )
        self.assertAlmostEqual(net_intraday, -0.29, places=2)


if __name__ == "__main__":
    unittest.main()
