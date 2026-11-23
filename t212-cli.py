#!/usr/bin/env python3
"""
t212-cli.py — CLI Project Manager per Trading 212 Autonomous Quant Bot (V11.5 LTS Zero Cerotti)
========================================================================================================
Progetto Standalone: /Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e

Comandi disponibili:
  python3 t212-cli.py status      -> Stato live portafoglio 100€, 4 cartucce, scanner 5m, radar notturno e demone
  python3 t212-cli.py tax-730     -> Prospetto Fiscale Modello 730 (Quadro W, Quadro T LIFO, lotti e storico)
  python3 t212-cli.py dashboard   -> Genera/aggiorna la Dashboard HTML interattiva (dashboard_v6_5.html)
  python3 t212-cli.py start       -> Avvia il demone autonomo t212_daemon_100e.py in background
  python3 t212-cli.py stop        -> Ferma il demone in background (mantenendo intatte le posizioni a mercato)
  python3 t212-cli.py export      -> Crea il pacchetto ZIP locale senza segreti (dist/trading212-quant-backup.zip)
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import zipfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
STATE_FILE = PROJECT_DIR / "trading212_state.json"
TAX_FILE = PROJECT_DIR / "registro_fiscale_730.json"
LONGTERM_FILE = PROJECT_DIR / "longterm_vault_1000e.json"
CREDS_FILE = PROJECT_DIR / "t212_credentials.json"
DAEMON_SCRIPT = PROJECT_DIR / "t212_daemon_100e.py"
DAEMON_LOG = Path("/tmp/t212_daemon.log")

PROJECT_FILES = [
    "AGENTS.md",
    "CONSTRAINTS.md",
    "GEMINI.md",
    "t212-cli.py",
    "t212_daemon_100e.py",
    "t212_dual_momentum_1000e.py",
    "t212_verified_universe.json",
    "trading212_bot.py",
    "trading212_state.json",
    "longterm_vault_1000e.json",
    "registro_fiscale_730.json",
    "dashboard_v6_5.html",
    "docs/architecture_v6_5.md",
    "docs/walkthrough.md",
]


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"⚠️ Errore lettura {path.name}: {exc}")
        return {}


def get_daemon_pids() -> list[int]:
    try:
        res = subprocess.run(
            ["pgrep", "-f", "t212_daemon_100e.py"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pids = []
        for line in res.stdout.strip().splitlines():
            line = line.strip()
            if line.isdigit() and int(line) != os.getpid():
                pids.append(int(line))
        return pids
    except Exception:
        return []


def fmt_eur(val: float, signed: bool = False) -> str:
    fmt = f"{val:+.2f}" if signed else f"{val:.2f}"
    return fmt.replace(".", ",") + " €"


def fmt_pct(val: float, signed: bool = True) -> str:
    fmt = f"{val:+.2f}%" if signed else f"{val:.2f}%"
    return fmt.replace(".", ",")


def fmt_px(val: float) -> str:
    # Mantiene precisione fino a 4 decimali se presenti sub-centesimi su XETRA/Euronext
    if abs(val - round(val, 2)) > 1e-5:
        return f"{val:.4f}".rstrip("0").rstrip(".").replace(".", ",") + " €"
    return f"{val:.2f}".replace(".", ",") + " €"


def cmd_status() -> None:
    print("\n" + "═" * 90)
    print(" 🛡️  TRADING 212 AUTONOMOUS QUANT BOT — V11.6 LTS ZERO CEROTTI (ANTI-SPREAD)")
    print("═" * 90)

    pids = get_daemon_pids()
    if pids:
        print(f" 🟢 DEMONE BACKGROUND: ATTIVO (PID: {', '.join(map(str, pids))}) | Log: {DAEMON_LOG}")
    else:
        print(" 🔴 DEMONE BACKGROUND: FERMO (avvia con: python3 t212-cli.py start)")

    state = load_json(STATE_FILE)
    if not state:
        print(" ⚠️  File di stato non trovato:", STATE_FILE)
        return

    updated_at = state.get("timestamp", "N/D")
    cycle = state.get("cycle", 0)
    arch = state.get("mode", "INSTITUTIONAL_V11_6_LTS_ZERO_CEROTTI")
    val_100 = float(state.get("valore_totale_portafoglio_100e_eur", 100.0))
    net_profit = float(state.get("guadagno_totale_netto_eur", 0.0))
    realized_net = float(state.get("profitto_realizzato_in_cassa_eur", 0.0))
    open_pnl = float(state.get("profitto_aperto_non_realizzato_eur", 0.0))
    invested = float(state.get("capitale_impegnato_cartucce_eur", 0.0))
    free_cash = float(state.get("liquidita_libera_su_100e_eur", 0.0))
    target_val = float(state.get("target_incasso_automatico_eur", 130.0))
    kelly_budget = float(state.get("budget_composto_attivo_kelly_eur", 100.0))
    dyn_slot = float(state.get("taglia_cartuccia_composta_eur", 25.0))
    daily_vault = bool(state.get("cassaforte_giornaliera_attiva", False))
    regime = state.get("regime_mercato_attivo", {})

    print(f" 📂 Root Progetto:    {PROJECT_DIR}")
    print(f" ⏱️  Ultimo Ciclo:     #{cycle} ({updated_at})")
    print(f" 🏛️  Architettura:     {arch}")
    print(f" 🧭 Regime Attivo:    {regime.get('code', 'N/D')} — {regime.get('description', '')}")
    print("─" * 90)
    print(f" 💰 VALORE PORTAFOGLIO (BASE 100 €): {fmt_eur(val_100)} ({fmt_pct(net_profit)}) -> Target: {fmt_eur(target_val)}")
    print(f"    ├─ Utili Netti Realizzati in Cassa: {fmt_eur(realized_net, signed=True)}")
    print(f"    ├─ PnL Fluttuante Cartucce Aperte:  {fmt_eur(open_pnl, signed=True)}")
    print(f"    ├─ Capitale Investito / Liquidità:  {fmt_eur(invested)} investiti | {fmt_eur(free_cash)} liberi")
    print(f"    ├─ Budget Composto Kelly (2+2):     {fmt_eur(kelly_budget)} ({fmt_eur(dyn_slot)} per cartuccia)")
    print(f"    └─ Cassaforte Mobile (>=+1,60€):    {'🔒 ATTIVA (Giveback Lock)' if daily_vault else '🔓 Corsa Libera Senza Tetto'} | Commissioni: 0,00 €")

    cartridges = state.get("cartucce_4x25_eur", [])
    print("\n" + "─" * 90)
    print(f" 🎯 STATO DELLE 4 CARTUCCE ATTIVE ({len(cartridges)}/4 SLOT OCCUPATI — VINCOLO MARKOWITZ 4 SETTORI)")
    print("─" * 90)
    for pos in cartridges:
        slot = pos.get("slot", 0)
        tk = pos.get("ticker", "")
        squad = "SQ1-Cecchino" if "CECCHINO" in pos.get("squadra", "") else "SQ2-CavalcaOnda"
        sector = pos.get("settore_markowitz", "N/D")
        inv_eur = float(pos.get("invested_eur", 0.0))
        pnl_eur = float(pos.get("pnl_eur", 0.0))
        pnl_pct = float(pos.get("pnl_pct", 0.0))
        peak_pct = float(pos.get("peak_pnl_pct", 0.0))
        act_pct = float(pos.get("scudo_mobile_elastico_atr_si_attiva_a_pct", 1.0))
        pre_active = bool(pos.get("pre_scudo_salva_utile_attivo", False))
        shield_active = bool(pos.get("scudo_mobile_attivo_ora", False))
        floor_pct = pos.get("livello_incasso_protetto_pct")
        cur_price = float(pos.get("current_price_eur", 0.0))

        if shield_active and floor_pct is not None:
            shield_str = f"🛡️ SCUDO ARMONICO ATTIVO (Pavimento: {fmt_pct(float(floor_pct))})"
        elif pre_active and floor_pct is not None:
            shield_str = f"🛡️ CURVA SALVA-UTILE CONTINUA ATTIVA (Pavimento: {fmt_pct(float(floor_pct))})"
        else:
            shield_str = f"⏳ Attesa Scudo ATR a {fmt_pct(act_pct)} (Pre-Scudo Continuo ATR)"

        print(
            f" #{slot} [{tk:<8}] {pos.get('name', tk):<24} | {squad:<15} | Settore: {sector}"
        )
        print(
            f"    Investito: {fmt_eur(inv_eur)} | PnL: {fmt_eur(pnl_eur, True)} ({fmt_pct(pnl_pct)}) | "
            f"Picco: {fmt_pct(peak_pct)} | Prezzo 0ms: {fmt_px(cur_price)}"
        )
        print(f"    Stato Scudo: {shield_str}")

    scanner = state.get("classifica_scanner_quantitativo_5m", [])
    if scanner:
        print("\n" + "─" * 90)
        print(f" 📡 SCANNER V11.5 ZERO CEROTTI ({len(scanner)} COLOSSI EUR • TAPER ATR + SIGNED ER + GETTEX 0s)")
        print("─" * 90)
        for item in scanner:
            tk = item.get("ticker", "")
            price = float(item.get("live_price_eur", 0.0))
            rsi = float(item.get("rsi_5m", 50.0))
            vel_m = float(item.get("profit_velocity_mult", item.get("atr_elastic_scale", 1.0)))
            k_er = float(item.get("kaufman_efficiency_ratio", 0.0))
            hook = "🟢 Hook:SÌ" if item.get("green_hook_confirmed") else "🔴 Hook:NO"
            qscore = float(item.get("quant_buy_score", 0.0))
            phase = item.get("fase_onda_sinusoidale", "N/D")
            print(
                f" • {tk:<8} | {fmt_px(price):>10} | RSI: {rsi:>4.1f} | "
                f"ATR-Sc: {vel_m:.2f}x | ER: {k_er:.2f} | {hook} | Score: {qscore:>4.1f} | {phase}"
            )

    radar = state.get("radar_onda_notturna_wall_street", {})
    if radar:
        print("\n" + "─" * 90)
        print(
            f" 🌙 RADAR MACRO & DECOMPRESSIONE SERALE 4/4 LIBERE (17:00-17:29) — "
            f"Nasdaq: {fmt_pct(float(radar.get('nasdaq_change_pct', 0.0)))} | "
            f"S&P500: {fmt_pct(float(radar.get('sp500_change_pct', 0.0)))} | "
            f"DAX: {fmt_pct(float(radar.get('dax_change_pct', 0.0)))} | "
            f"VIX: {fmt_pct(float(radar.get('vix_fear_change_pct', 0.0)))}"
        )
        print(f"    Verdetto: {radar.get('verdict', 'N/D')}")
        print(f"    Analisi:  {radar.get('spiegazione_strategica', '')}")
    print("═" * 90 + "\n")


def cmd_tax_730() -> None:
    tax = load_json(TAX_FILE)
    state = load_json(STATE_FILE)

    print("\n" + "═" * 90)
    print(" 🇮🇹 REGISTRO FISCALE ITALIANO — MODELLO 730 / REDDITI PF (METODO LIFO)")
    print("═" * 90)
    if not tax:
        print(" ⚠️  Nessun dato fiscale disponibile in:", TAX_FILE)
        return

    riepilogo = state.get("riepilogo_fiscale_730", {})
    q_w = riepilogo.get("QUADRO_W_MONITORAGGIO", {})
    q_t = riepilogo.get("QUADRO_T_PLUSVALENZE_LIFO", {})
    ivafe_val = float(q_w.get("IVAFE_Dovuta_EUR", 0.0))
    imposta_val = float(tax.get("imposta_sostitutiva_26_eur", 0.0))
    nota_f24 = q_t.get(
        "Nota_Versamento",
        "Nessun versamento F24 dovuto (sotto franchigia 12,00 EUR)"
        if imposta_val <= 12.0
        else f"Versamento F24 dovuto: {fmt_eur(imposta_val)}",
    )

    print(f" Anno Fiscale:          {tax.get('anno_fiscale', 2026)}")
    print(f" Broker / Conto:        {tax.get('broker', 'Trading 212')} (ID: {state.get('account_id', 52318994)})")
    print(f" Codice Stato Estero:   {tax.get('stato_estero_codice', '040 / 031')}")
    print("─" * 90)
    print(" 📋 QUADRO W (Monitoraggio Fiscale Attività Finanziarie Estere & IVAFE 0,20%)")
    print(f"    • Valore Iniziale:      {fmt_eur(float(tax.get('valore_iniziale_quadro_w_eur', 100.0)))}")
    print(f"    • Valore Finale Stim.:  {fmt_eur(float(q_w.get('Valore_Finale_31_12_EUR', tax.get('valore_finale_stimato_quadro_w_eur', 101.0))))}")
    print(f"    • Giorni Detenzione:    {tax.get('giorni_detenzione_ivafe', 365)} giorni")
    print(f"    • IVAFE da Versare:     {fmt_eur(ivafe_val)} ({q_w.get('Nota_IVAFE', 'Esente sotto soglia minima 12,00 EUR')})")
    print("─" * 90)
    print(" 📋 QUADRO T (Plusvalenze / Minusvalenze Finanziarie — Imposta Sostitutiva 26% LIFO)")
    closed = tax.get("operazioni_chiuse", [])
    print(f"    • Operazioni Chiuse:    {len(closed)}")
    print(f"    • Totale Corrispettivi: {fmt_eur(float(tax.get('totale_corrispettivi_vendita_eur', 0.0)))}")
    print(f"    • Totale Costi LIFO:    {fmt_eur(float(tax.get('totale_costi_carico_lifo_eur', 0.0)))}")
    print(f"    • Plusvalenze Lorde:    {fmt_eur(float(tax.get('plusvalenze_lorde_eur', 0.0)), True)}")
    print(f"    • Minusvalenze Comp.:   {fmt_eur(float(tax.get('minusvalenze_lorde_eur', 0.0)))}")
    print(f"    • Imponibile Netto:     {fmt_eur(float(tax.get('imponibile_netto_eur', 0.0)), True)}")
    print(f"    • Imposta 26% Teorica:  {fmt_eur(imposta_val)} ({nota_f24})")

    print("─" * 90)
    print(f" 📜 STORICO OPERAZIONI CHIUSE CONTABILIZZATE ({len(closed)})")
    for tr in closed:
        print(
            f"    • [{tr.get('timestamp', '')[:19]}] {tr.get('ticker', ''):<8} | Qty: {float(tr.get('quantity', 0.0)):.4f} | "
            f"Costo LIFO: {fmt_eur(float(tr.get('costo_lifo_eur', 0.0)))} -> Ricavo: {fmt_eur(float(tr.get('corrispettivo_eur', 0.0)))} | "
            f"Risultato: {fmt_eur(float(tr.get('risultato_fiscale_eur', 0.0)), True)}"
        )

    open_lots = tax.get("lotti_aperti_lifo", {})
    print("─" * 90)
    print(" 📦 LOTTI LIFO ATTUALMENTE APERTI IN PORTAFOGLIO")
    for tk, lots in open_lots.items():
        for lot in lots:
            print(
                f"    • {tk:<8} ({lot.get('isin', '')}) | Data: {lot.get('timestamp', '')[:19]} | "
                f"Qty: {float(lot.get('quantity', 0.0)):.4f} @ {fmt_eur(float(lot.get('price_eur', 0.0)))} | "
                f"Totale Carico: {fmt_eur(float(lot.get('total_eur', 0.0)))}"
            )
    print("═" * 90 + "\n")


def generate_dashboard_html(state: dict, tax: dict, longterm: dict | None = None) -> str:
    lt = longterm if isinstance(longterm, dict) else {}
    val_100 = float(state.get("valore_totale_portafoglio_100e_eur", 100.0))
    net_profit = float(state.get("guadagno_totale_netto_eur", 0.0))
    realized_net = float(state.get("profitto_realizzato_in_cassa_eur", 0.0))
    open_pnl = float(state.get("profitto_aperto_non_realizzato_eur", 0.0))
    invested = float(state.get("capitale_impegnato_cartucce_eur", 0.0))
    free_cash = float(state.get("liquidita_libera_su_100e_eur", 0.0))
    dyn_slot = float(state.get("taglia_cartuccia_composta_eur", 25.0))
    kelly_budget = float(state.get("budget_composto_attivo_kelly_eur", 100.0))
    cycle = state.get("cycle", 0)
    updated_at = state.get("timestamp", "N/D")

    cartridges = state.get("cartucce_4x25_eur", [])
    scanner = state.get("classifica_scanner_quantitativo_5m", [])
    radar = state.get("radar_onda_notturna_wall_street", {})
    closed_trades = tax.get("operazioni_chiuse", [])

    # Dati Portafoglio #2 — Dual Momentum + Oro Fisico (900,00 EUR isolati su Conto Totale 1.000,00 EUR)
    lt_init = float(lt.get("initial_budget_eur", 900.0))
    lt_val = float(lt.get("total_portfolio_value_eur", lt_init))
    lt_ret_eur = float(lt.get("total_net_return_eur", 0.0))
    lt_ret_pct = float(lt.get("total_net_return_pct", 0.0))
    lt_inv = float(lt.get("invested_cost_eur", 0.0))
    lt_mkt = float(lt.get("market_value_eur", 0.0))
    lt_cash = float(lt.get("uninvested_cash_eur", lt_init))
    lt_unreal = float(lt.get("unrealized_pnl_eur", 0.0))
    lt_real = float(lt.get("realized_net_pnl_eur", 0.0))
    lt_regime = str(lt.get("regime_dual_momentum", "IN_ATTESA"))
    lt_updated = str(lt.get("timestamp", "N/D"))
    lt_rebal = str(lt.get("last_rebalance_iso") or "N/D")
    lt_positions = lt.get("posizioni_attive", [])
    lt_ranking = lt.get("classifica_dual_momentum_1y", [])
    lt_closed = lt.get("operazioni_chiuse", [])

    cards_html = ""
    if not cartridges:
        cards_html = f"""
        <div class="card" style="grid-column: 1 / -1; border-style: dashed; text-align: center; padding: 26px;">
          <span class="slot-tag">4/4 CARTUCCE LIBERE IN CONTANTI EUR</span>
          <h3 style="margin-top:6px;">Nessuna posizione intraday aperta in questo istante</h3>
          <p style="color: var(--muted); font-size: 0.88rem; margin-top: 6px;">
            Tutte le voci tra 85 € e 210 € visibili sull'app Trading 212 appartengono esclusivamente al Portafoglio #2 da {fmt_eur(lt_init)}.
            Quando il Bot Intraday sparerà una cartuccia (~25 €), comparirà qui in tempo reale.
          </p>
        </div>
        """
    for pos in cartridges:
        slot = pos.get("slot", 0)
        tk = pos.get("ticker", "")
        pnl_eur = float(pos.get("pnl_eur", 0.0))
        pnl_pct = float(pos.get("pnl_pct", 0.0))
        peak_pct = float(pos.get("peak_pnl_pct", 0.0))
        act_pct = float(pos.get("scudo_mobile_elastico_atr_si_attiva_a_pct", 1.0))
        floor_pct = pos.get("livello_incasso_protetto_pct")
        pre_active = bool(pos.get("pre_scudo_salva_utile_attivo", False))
        shield_active = bool(pos.get("scudo_mobile_attivo_ora", False))
        color_cls = "pos" if pnl_pct >= 0 else "neg"
        badge = (
            f"🛡️ Scudo Armonico ({fmt_pct(float(floor_pct))})"
            if shield_active and floor_pct is not None
            else (
                f"🛡️ Pre-Scudo Salva-Utile ({fmt_pct(float(floor_pct))})"
                if pre_active and floor_pct is not None
                else f"⏳ Target Scudo ATR {fmt_pct(act_pct)}"
            )
        )
        cards_html += f"""
        <div class="card">
          <div class="card-head">
            <div>
              <span class="slot-tag">⚡ CARTUCCIA INTRADAY #{slot} • {pos.get('settore_markowitz', '')}</span>
              <h3>{pos.get('name', tk)} <small>({tk})</small></h3>
            </div>
            <div class="price-pill {color_cls}">{fmt_pct(pnl_pct)}</div>
          </div>
          <div class="metrics-grid">
            <div><span>Capitale Investito</span><strong>{fmt_eur(float(pos.get('invested_eur', 0.0)))}</strong></div>
            <div><span>PnL Fluttuante</span><strong class="{color_cls}">{fmt_eur(pnl_eur, True)}</strong></div>
            <div><span>Picco Toccato</span><strong>{fmt_pct(peak_pct)}</strong></div>
            <div><span>Prezzo 0ms Live</span><strong>{fmt_px(float(pos.get('current_price_eur', 0.0)))}</strong></div>
          </div>
          <div class="shield-bar">{badge} • RSI 5m: {float(pos.get('rsi_5m', 50.0)):.1f}</div>
        </div>
        """

    bucket_labels = {
        "ETF_ENGINE": "📈 MOTORE ETF ACC",
        "STOCK_COMPOUNDER": "🏰 AZIONE FORTEZZA",
        "GOLD_SAFE_HAVEN": "🥇 ORO FISICO ETC",
        "CASH_SAFE_HAVEN": "🏦 TASSO BCE XEON",
    }
    lt_cards_html = ""
    if not lt_positions:
        lt_cards_html = f"""
        <div class="card gold-card" style="grid-column: 1 / -1; text-align: center; padding: 24px;">
          <span class="slot-tag gold-tag">VAULT {fmt_eur(lt_init)}</span>
          <h3 style="margin-top:6px;">Nessuna posizione aperta nel Vault {fmt_eur(lt_init)} (100% Contanti EUR pronti per l'apertura XETRA 09:15)</h3>
        </div>
        """
    for lp in lt_positions:
        ltk = lp.get("ticker", "")
        lpnl_e = float(lp.get("pnl_eur", 0.0))
        lpnl_p = float(lp.get("pnl_pct", 0.0))
        lcls = "pos" if lpnl_e >= 0 else "neg"
        bkt = bucket_labels.get(str(lp.get("bucket", "")), str(lp.get("bucket", "")))
        sem_txt = "🟢 TREND BULL (Sopra SMA)" if lp.get("is_bull_trend") else "🟡 QUOTA DIFENSIVA CAUTA"
        sma_d = float(lp.get("sma_150_dist_pct", 0.0))
        lt_cards_html += f"""
        <div class="card gold-card">
          <div class="card-head">
            <div>
              <span class="slot-tag gold-tag">{bkt} • TARGET {float(lp.get('target_weight_pct', 0.0)):.1f}%</span>
              <h3>{lp.get('name', ltk)} <small>({ltk})</small></h3>
            </div>
            <div class="price-pill {lcls}">{fmt_pct(lpnl_p)}</div>
          </div>
          <div class="metrics-grid">
            <div><span>Valore Attuale</span><strong>{fmt_eur(float(lp.get('market_value_eur', 0.0)))}</strong></div>
            <div><span>Costo Carico</span><strong>{fmt_eur(float(lp.get('invested_eur', 0.0)))}</strong></div>
            <div><span>PnL Netto</span><strong class="{lcls}">{fmt_eur(lpnl_e, True)}</strong></div>
            <div><span>Prezzo / Quantità</span><strong>{fmt_px(float(lp.get('current_price_eur', 0.0)))} ({float(lp.get('quantity', 0.0)):g})</strong></div>
          </div>
          <div class="shield-bar">{sem_txt} • Distanza SMA 150gg: {fmt_pct(sma_d)}</div>
        </div>
        """

    lt_rank_rows = ""
    active_lt_tkrs = {p.get("ticker") for p in lt_positions}
    for rk in lt_ranking:
        rtk = rk.get("ticker", "")
        in_port = "🏛️ IN PORTAFOGLIO" if rtk in active_lt_tkrs else "Panchina"
        in_cls = "badge-ok" if rtk in active_lt_tkrs else "badge-wait"
        bull_b = '<span class="badge-ok">🟢 VERDE</span>' if rk.get("is_bull_trend") else '<span class="badge-wait">🔴 SOTTO SMA</span>'
        lt_rank_rows += f"""
        <tr>
          <td><strong>{rtk}</strong> <small>{rk.get('name', '')}</small></td>
          <td>{bucket_labels.get(str(rk.get('bucket', '')), rk.get('bucket', ''))}</td>
          <td>{fmt_px(float(rk.get('live_price_eur', 0.0)))}</td>
          <td class="{'pos' if float(rk.get('ret_1m_pct', 0.0)) >= 0 else 'neg'}">{fmt_pct(float(rk.get('ret_1m_pct', 0.0)))}</td>
          <td class="{'pos' if float(rk.get('ret_3m_pct', 0.0)) >= 0 else 'neg'}">{fmt_pct(float(rk.get('ret_3m_pct', 0.0)))}</td>
          <td class="{'pos' if float(rk.get('ret_6m_pct', 0.0)) >= 0 else 'neg'}">{fmt_pct(float(rk.get('ret_6m_pct', 0.0)))}</td>
          <td><strong>{float(rk.get('dm_sharpe_score', 0.0)):+.2f}</strong></td>
          <td>{fmt_pct(float(rk.get('sma_150_dist_pct', 0.0)))}</td>
          <td>{bull_b}</td>
          <td><span class="{in_cls}">{in_port}</span></td>
        </tr>
        """

    scanner_rows = ""
    for item in scanner:
        hook_badge = '<span class="badge-ok">🟢 SÌ (Verde)</span>' if item.get("green_hook_confirmed") else '<span class="badge-wait">🔴 NO (Attesa)</span>'
        scanner_rows += f"""
        <tr>
          <td><strong>{item.get('ticker', '')}</strong> <small>{item.get('name', '')}</small></td>
          <td>{item.get('sector', '')}</td>
          <td>{fmt_px(float(item.get('live_price_eur', 0.0)))}</td>
          <td>{float(item.get('rsi_5m', 50.0)):.1f}</td>
          <td>{float(item.get('atr_elastic_scale', 1.0)):.2f}x</td>
          <td>{fmt_pct(float(item.get('shield_activation_pct', 1.0)), False)} / -{fmt_pct(float(item.get('shield_pullback_pct', 0.2)), False)}</td>
          <td>{hook_badge}</td>
          <td><strong>{float(item.get('quant_buy_score', 0.0)):.1f}</strong></td>
          <td><small>{item.get('fase_onda_sinusoidale', '')}</small></td>
        </tr>
        """

    closed_rows = ""
    for tr in closed_trades:
        ris = float(tr.get("risultato_fiscale_eur", 0.0))
        cls = "pos" if ris >= 0 else "neg"
        closed_rows += f"""
        <tr>
          <td>{tr.get('timestamp', '')[:19]}</td>
          <td><strong>{tr.get('ticker', '')}</strong></td>
          <td>{float(tr.get('quantity', 0.0)):.4f}</td>
          <td>{fmt_eur(float(tr.get('costo_lifo_eur', 0.0)))}</td>
          <td>{fmt_eur(float(tr.get('corrispettivo_eur', 0.0)))}</td>
          <td class="{cls}"><strong>{fmt_eur(ris, True)}</strong></td>
        </tr>
        """

    lt_closed_rows = ""
    for ltr in lt_closed:
        lris = float(ltr.get("realized_pnl_eur", 0.0))
        lcls = "pos" if lris >= 0 else "neg"
        lt_closed_rows += f"""
        <tr>
          <td>{ltr.get('timestamp', '')[:19]}</td>
          <td><strong>{ltr.get('ticker', '')}</strong> <small>{ltr.get('reason', '')}</small></td>
          <td>{float(ltr.get('quantity', 0.0)):.4f}</td>
          <td>{fmt_eur(float(ltr.get('cost_lifo_eur', 0.0)))}</td>
          <td>{fmt_eur(float(ltr.get('proceeds_eur', 0.0)))}</td>
          <td class="{lcls}"><strong>{fmt_eur(lris, True)}</strong></td>
        </tr>
        """
    if not lt_closed_rows:
        lt_closed_rows = '<tr><td colspan="6" style="color:var(--muted);text-align:center;">Nessuna vendita/rotazione eseguita finora nel Vault 1.000 € (posizioni attive a mercato).</td></tr>'

    progress_pct = max(0.0, min(100.0, ((val_100 - 100.0) / 30.0) * 100.0))

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Trading 212 Dual-Engine Dashboard — 100 € Intraday + 1.000 € Lungo Termine & Oro</title>
  <style>
    :root {{
      --bg: #080b11;
      --panel: #111723;
      --panel-2: #172031;
      --border: #25324a;
      --gold-border: rgba(245, 158, 11, 0.45);
      --text: #f1f5f9;
      --muted: #94a3b8;
      --gold: #f59e0b;
      --gold-soft: #fde68a;
      --green: #10b981;
      --red: #ef4444;
      --blue: #38bdf8;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 28px;
      line-height: 1.5;
    }}
    .container {{ max-width: 1320px; margin: 0 auto; }}
    .header {{
      display: flex; justify-content: space-between; align-items: center;
      flex-wrap: wrap; gap: 16px; padding: 24px;
      background: linear-gradient(135deg, #111827 0%, #0f172a 100%);
      border: 1px solid var(--border); border-radius: 16px; margin-bottom: 20px;
    }}
    .header h1 {{ font-size: 1.45rem; letter-spacing: -0.02em; }}
    .header p {{ color: var(--muted); font-size: 0.9rem; margin-top: 4px; }}
    .status-pill {{
      background: rgba(16, 185, 129, 0.15); border: 1px solid var(--green);
      color: #34d399; padding: 8px 16px; border-radius: 999px; font-weight: 600; font-size: 0.85rem;
    }}
    .split-hero {{
      display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
      gap: 18px; margin-bottom: 20px;
    }}
    .hero-box {{
      background: var(--panel); border-radius: 16px; padding: 22px;
      border: 2px solid var(--border);
    }}
    .hero-intraday {{ border-color: rgba(56, 189, 248, 0.55); background: linear-gradient(160deg, #0f172a 0%, #111827 100%); }}
    .hero-longterm {{ border-color: var(--gold-border); background: linear-gradient(160deg, #1c160c 0%, #111723 100%); }}
    .hero-badge {{
      display: inline-block; padding: 4px 10px; border-radius: 999px;
      font-size: 0.74rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;
    }}
    .badge-blue {{ background: rgba(56, 189, 248, 0.16); color: var(--blue); border: 1px solid rgba(56, 189, 248, 0.4); }}
    .badge-gold {{ background: rgba(245, 158, 11, 0.16); color: var(--gold-soft); border: 1px solid var(--gold-border); }}
    .hero-val {{ font-size: 2.15rem; font-weight: 800; margin: 10px 0 4px; }}
    .hero-sub {{ font-size: 0.86rem; color: var(--muted); display: flex; flex-wrap: wrap; gap: 14px; margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.08); }}
    .tabs-bar {{
      display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 22px;
    }}
    .tab-btn {{
      cursor: pointer; background: var(--panel); color: var(--muted);
      border: 1px solid var(--border); padding: 10px 18px; border-radius: 10px;
      font-weight: 700; font-size: 0.88rem; transition: all 0.15s ease;
    }}
    .tab-btn.active {{ background: #1e293b; color: var(--text); border-color: var(--blue); }}
    .tab-btn.gold-tab.active {{ border-color: var(--gold); color: var(--gold-soft); }}
    .kpi-grid {{
      display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px; margin-bottom: 24px;
    }}
    .kpi {{
      background: var(--panel); border: 1px solid var(--border);
      padding: 20px; border-radius: 14px;
    }}
    .kpi span {{ color: var(--muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }}
    .kpi h2 {{ font-size: 1.8rem; margin-top: 6px; }}
    .kpi small {{ color: var(--muted); font-size: 0.82rem; display: block; margin-top: 4px; }}
    .pos {{ color: var(--green); }}
    .neg {{ color: var(--red); }}
    .progress-wrap {{
      background: var(--panel); border: 1px solid var(--border);
      padding: 18px 22px; border-radius: 14px; margin-bottom: 24px;
    }}
    .progress-bar-bg {{
      height: 10px; background: #1e293b; border-radius: 999px; overflow: hidden; margin-top: 10px;
    }}
    .progress-bar-fill {{
      height: 100%; width: {progress_pct:.1f}%;
      background: linear-gradient(90deg, var(--blue), var(--green));
    }}
    .section-title {{
      font-size: 1.15rem; font-weight: 700; margin: 28px 0 14px;
      display: flex; align-items: center; gap: 8px;
    }}
    .cards-grid {{
      display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 16px;
    }}
    .card {{
      background: var(--panel); border: 1px solid var(--border);
      border-radius: 14px; padding: 18px;
    }}
    .gold-card {{ border-color: var(--gold-border); }}
    .card-head {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }}
    .slot-tag {{ font-size: 0.72rem; color: var(--blue); text-transform: uppercase; font-weight: 700; }}
    .gold-tag {{ color: var(--gold-soft); }}
    .card h3 {{ font-size: 1.05rem; margin-top: 4px; }}
    .card h3 small {{ color: var(--muted); font-weight: 400; }}
    .price-pill {{
      padding: 4px 10px; border-radius: 8px; font-weight: 700; font-size: 0.9rem;
      background: rgba(255,255,255,0.05);
    }}
    .metrics-grid {{
      display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
      margin: 14px 0; padding: 12px; background: var(--panel-2); border-radius: 10px;
    }}
    .metrics-grid span {{ display: block; font-size: 0.75rem; color: var(--muted); }}
    .metrics-grid strong {{ font-size: 0.95rem; }}
    .shield-bar {{
      font-size: 0.8rem; color: #fde68a; background: rgba(245, 158, 11, 0.12);
      border: 1px solid rgba(245, 158, 11, 0.35); padding: 8px 12px; border-radius: 8px;
    }}
    table {{
      width: 100%; border-collapse: collapse; background: var(--panel);
      border: 1px solid var(--border); border-radius: 14px; overflow: hidden; font-size: 0.86rem;
    }}
    th, td {{ padding: 11px 13px; text-align: left; border-bottom: 1px solid var(--border); }}
    th {{ background: var(--panel-2); color: var(--muted); font-size: 0.74rem; text-transform: uppercase; }}
    .badge-ok {{ color: var(--green); font-weight: 700; }}
    .badge-wait {{ color: var(--muted); }}
    .hidden-panel {{ display: none !important; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <h1>🛡️ Trading 212 Dual-Engine Command Center — V11.6 LTS</h1>
        <p>Conto ID: 52318994 (EUR) • Muraglia Cinese Attiva (0% Titoli Sovrapposti) • Aggiornato: {updated_at[:19]} (Ciclo #{cycle})</p>
      </div>
      <div class="status-pill">🟢 DOPPIO MOTORE CLOUD H24 ATTIVO</div>
    </div>

    <div class="split-hero">
      <div class="hero-box hero-intraday">
        <span class="hero-badge badge-blue">⚡ PORTAFOGLIO #1 • BOT INTRADAY (BASE 100,00 €)</span>
        <div class="hero-val {'pos' if net_profit >= 0 else 'neg'}">{fmt_eur(val_100)} <small style="font-size:1rem;">({fmt_eur(net_profit, True)} / {fmt_pct(net_profit)})</small></div>
        <div style="font-size:0.86rem; color:var(--muted);">47 Colossi EUR Zero-Fee (incl. STM, Stellantis, Ferrari) • Cartucce da ~{fmt_eur(dyn_slot)}</div>
        <div class="hero-sub">
          <span>📦 Aperte ora: <strong>{len(cartridges)}/4</strong></span>
          <span>💶 Investiti: <strong>{fmt_eur(invested)}</strong></span>
          <span>🏦 Liquidi: <strong>{fmt_eur(free_cash)}</strong></span>
          <span>💰 Cassa Chiusa: <strong class="{'pos' if realized_net >= 0 else 'neg'}">{fmt_eur(realized_net, True)}</strong></span>
        </div>
      </div>

      <div class="hero-box hero-longterm">
        <span class="hero-badge badge-gold">🏛️ PORTAFOGLIO #2 • DUAL MOMENTUM + ORO (BASE {fmt_eur(lt_init)})</span>
        <div class="hero-val {'pos' if lt_ret_eur >= 0 else 'neg'}">{fmt_eur(lt_val)} <small style="font-size:1rem;">({fmt_eur(lt_ret_eur, True)} / {fmt_pct(lt_ret_pct)})</small></div>
        <div style="font-size:0.86rem; color:var(--muted);">Regime: <strong>{lt_regime}</strong> • Fette da 90 € – 203 € (Agg.: {lt_updated[:19]})</div>
        <div class="hero-sub">
          <span>📦 Strumenti: <strong>{len(lt_positions)} attivi</strong></span>
          <span>💶 A Mercato: <strong>{fmt_eur(lt_mkt)}</strong> (Costo {fmt_eur(lt_inv)})</span>
          <span>🏦 Liquidi Vault: <strong>{fmt_eur(lt_cash)}</strong></span>
          <span>💰 Realizzati: <strong class="{'pos' if lt_real >= 0 else 'neg'}">{fmt_eur(lt_real, True)}</strong></span>
        </div>
      </div>
    </div>

    <div class="tabs-bar">
      <button class="tab-btn active" onclick="switchView('all', this)">👁️ Mostra Entrambi (Totale Base 1.000,00 €)</button>
      <button class="tab-btn" onclick="switchView('intraday', this)">⚡ Solo Bot Intraday (100 €)</button>
      <button class="tab-btn gold-tab" onclick="switchView('longterm', this)">🏛️ Solo Lungo Termine + Oro ({fmt_eur(lt_init)})</button>
    </div>

    <!-- ================= SEZIONE PORTAFOGLIO #2: 900 € DUAL MOMENTUM + ORO ================= -->
    <div id="panel-longterm">
      <div class="section-title" style="color: var(--gold-soft);">🏛️ Portafoglio #2 — Posizioni Attive Lungo Termine + Oro Fisico (Base {fmt_eur(lt_init)} • Ultimo Ribilanciamento: {lt_rebal[:16]})</div>
      <div class="cards-grid">{lt_cards_html}</div>

      <div class="section-title" style="color: var(--gold-soft);">🧭 Classifica Matematica Dual Momentum a 1 Anno (12 Strumenti EUR Zero-Fee • Semaforo SMA 150gg)</div>
      <table>
        <thead>
          <tr>
            <th>Strumento (EUR)</th><th>Categoria</th><th>Prezzo</th>
            <th>1 Mese</th><th>3 Mesi</th><th>6 Mesi</th><th>Score Sharpe</th><th>Dist. SMA150</th><th>Semaforo</th><th>Stato Vault</th>
          </tr>
        </thead>
        <tbody>{lt_rank_rows}</tbody>
      </table>

      <div class="section-title" style="color: var(--gold-soft);">📜 Storico Rotazioni & Incassi Vault {fmt_eur(lt_init)} (Operazioni Chiuse: {len(lt_closed)})</div>
      <table>
        <thead>
          <tr>
            <th>Data/Ora</th><th>Strumento / Motivo</th><th>Quantità</th><th>Costo LIFO</th><th>Ricavo</th><th>Risultato Netto</th>
          </tr>
        </thead>
        <tbody>{lt_closed_rows}</tbody>
      </table>
    </div>

    <!-- ================= SEZIONE PORTAFOGLIO #1: 100 € BOT INTRADAY ================= -->
    <div id="panel-intraday">
      <div class="section-title" style="color: var(--blue);">⚡ Portafoglio #1 — Bot Intraday V11.6 (Base 100,00 € • 4 Cartucce da ~{fmt_eur(dyn_slot)} su 4 Settori Distinti)</div>
      <div class="progress-wrap">
        <div style="display:flex; justify-content:space-between; font-size:0.88rem; flex-wrap:wrap; gap:8px;">
          <strong>🎯 Traguardo Cash-Out Intraday (+30,00%): 130,00 €</strong>
          <span>Avanzamento: {progress_pct:.1f}% ({fmt_eur(val_100)} / 130,00 €) • Radar: {radar.get('verdict', 'N/D')} (Nasdaq {fmt_pct(float(radar.get('nasdaq_change_pct', 0.0)))})</span>
        </div>
        <div class="progress-bar-bg"><div class="progress-bar-fill"></div></div>
      </div>

      <div class="cards-grid">{cards_html}</div>

      <div class="section-title" style="color: var(--blue);">📡 Scanner Intraday a 5 Minuti + Streaming 0s GETTEX ({len(scanner)} Colossi EUR Zero-Fee)</div>
      <table>
        <thead>
          <tr>
            <th>Titolo (EUR)</th><th>Settore Markowitz</th><th>Prezzo 0s</th>
            <th>RSI 5m</th><th>ATR Mult</th><th>Scudo / Ritracc.</th><th>Uncino Verde</th><th>Quant Score</th><th>Fase Onda 5m</th>
          </tr>
        </thead>
        <tbody>{scanner_rows}</tbody>
      </table>

      <div class="section-title" style="color: var(--blue);">🇮🇹 Registro Fiscale Intraday 100 € — Modello 730 LIFO (Operazioni Chiuse: {len(closed_trades)})</div>
      <table>
        <thead>
          <tr>
            <th>Data/Ora</th><th>Titolo</th><th>Quantità</th><th>Costo Carico LIFO</th>
            <th>Ricavo Vendita</th><th>Plus/Minus Netto</th>
          </tr>
        </thead>
        <tbody>{closed_rows}</tbody>
      </table>
    </div>
  </div>

  <script>
    function switchView(mode, btn) {{
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');
      const pIntra = document.getElementById('panel-intraday');
      const pLong = document.getElementById('panel-longterm');
      if (mode === 'intraday') {{
        pIntra.classList.remove('hidden-panel');
        pLong.classList.add('hidden-panel');
      }} else if (mode === 'longterm') {{
        pIntra.classList.add('hidden-panel');
        pLong.classList.remove('hidden-panel');
      }} else {{
        pIntra.classList.remove('hidden-panel');
        pLong.classList.remove('hidden-panel');
      }}
    }}
  </script>
</body>
</html>
"""


def cmd_dashboard() -> None:
    state = load_json(STATE_FILE)
    tax = load_json(TAX_FILE)
    lt = load_json(LONGTERM_FILE)
    html = generate_dashboard_html(state, tax, lt)
    out_path = PROJECT_DIR / "dashboard_v6_5.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"✅ Dashboard HTML Dual-Engine aggiornata in: {out_path}")


def cmd_start() -> None:
    pids = get_daemon_pids()
    if pids:
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
        import time
        time.sleep(1.0)
    with open(DAEMON_LOG, "a", encoding="utf-8") as log_f:
        proc = subprocess.Popen(
            [sys.executable, "-u", str(DAEMON_SCRIPT)],
            cwd=str(PROJECT_DIR),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    print(f"🚀 Demone V11.5 avviato in background (PID: {proc.pid}) | Log: {DAEMON_LOG}")


def cmd_stop() -> None:
    pids = get_daemon_pids()
    if not pids:
        print("ℹ️  Nessun demone attivo da fermare.")
        return
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"🛑 Segnale SIGTERM inviato al demone PID {pid}.")
        except Exception as exc:
            print(f"⚠️ Errore arresto PID {pid}: {exc}")


def cmd_export() -> None:
    cmd_dashboard()
    dist_dir = PROJECT_DIR / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dist_dir / "trading212-quant-backup.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in PROJECT_FILES:
            if "credentials" in rel.lower():
                continue
            fpath = PROJECT_DIR / rel
            if fpath.exists():
                zf.write(fpath, arcname=f"trading212-quant-v115/{rel}")
    print(f"📦 Pacchetto ZIP locale (senza credenziali) esportato in: {zip_path} ({zip_path.stat().st_size:,} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CLI Manager per Trading 212 Autonomous Quant Bot V11.5 LTS Zero Cerotti"
    )
    parser.add_argument(
        "command",
        choices=["status", "tax-730", "dashboard", "start", "stop", "export", "longterm-status", "longterm-cashout", "longterm-profits"],
        help="Comando da eseguire",
    )
    args = parser.parse_args()

    if args.command == "status":
        cmd_status()
        lt_file = PROJECT_DIR / "longterm_vault_1000e.json"
        if lt_file.exists():
            from t212_dual_momentum_1000e import print_vault_summary
            print_vault_summary(load_json(lt_file))
    elif args.command == "longterm-status":
        subprocess.run([sys.executable, str(PROJECT_DIR / "t212_dual_momentum_1000e.py"), "--status-only"], cwd=str(PROJECT_DIR), check=False)
    elif args.command == "longterm-cashout":
        subprocess.run([sys.executable, str(PROJECT_DIR / "t212_dual_momentum_1000e.py"), "--cashout-all"], cwd=str(PROJECT_DIR), check=False)
    elif args.command == "longterm-profits":
        subprocess.run([sys.executable, str(PROJECT_DIR / "t212_dual_momentum_1000e.py"), "--cashout-profits"], cwd=str(PROJECT_DIR), check=False)
    elif args.command == "tax-730":
        cmd_tax_730()
    elif args.command == "dashboard":
        cmd_dashboard()
    elif args.command == "start":
        cmd_start()
    elif args.command == "stop":
        cmd_stop()
    elif args.command == "export":
        cmd_export()


if __name__ == "__main__":
    main()
