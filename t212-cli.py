#!/usr/bin/env python3
"""
t212-cli.py — CLI Project Manager per Trading 212 Autonomous Quant Bot (V6.5 Institutional Zero-Latency)
========================================================================================================
Progetto Standalone: /Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e

Comandi disponibili:
  python3 t212-cli.py status      -> Stato live portafoglio 100€, 4 cartucce, scanner 5m, radar notturno e demone
  python3 t212-cli.py tax-730     -> Prospetto Fiscale Modello 730 (Quadro W, Quadro T LIFO, lotti e storico)
  python3 t212-cli.py dashboard   -> Genera/aggiorna la Dashboard HTML interattiva (dashboard_v6_5.html)
  python3 t212-cli.py start       -> Avvia il demone autonomo t212_daemon_100e.py in background
  python3 t212-cli.py stop        -> Ferma il demone in background (mantenendo intatte le posizioni a mercato)
  python3 t212-cli.py export      -> Crea il pacchetto ZIP di backup (dist/trading212-quant-v6.5-backup.zip)
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
CREDS_FILE = PROJECT_DIR / "t212_credentials.json"
DAEMON_SCRIPT = PROJECT_DIR / "t212_daemon_100e.py"
DAEMON_LOG = Path("/tmp/t212_daemon.log")

PROJECT_FILES = [
    "AGENTS.md",
    "GEMINI.md",
    "t212-cli.py",
    "t212_daemon_100e.py",
    "trading212_bot.py",
    "trading212_state.json",
    "registro_fiscale_730.json",
    "t212_credentials.json",
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


def cmd_status() -> None:
    print("\n" + "═" * 90)
    print(" 🛡️  TRADING 212 AUTONOMOUS QUANT BOT — V6.5 INSTITUTIONAL ZERO-LATENCY (12 BLINDATURE)")
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
    arch = state.get("mode", "INSTITUTIONAL_ZERO_LATENCY_V6_5_12_SHIELDS")
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
    print(f"    └─ Cassaforte Giornaliera (+1,80€): {'🔒 ATTIVA' if daily_vault else '🔓 In attesa'} | Commissioni: 0,00 €")

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
            shield_str = f"🛡️ PRE-SCUDO SALVA-UTILE ATTIVO (Pavimento: {fmt_pct(float(floor_pct))})"
        else:
            shield_str = f"⏳ Attesa Scudo ATR a {fmt_pct(act_pct)} (Pre-Scudo a +0,60%)"

        print(
            f" #{slot} [{tk:<8}] {pos.get('name', tk):<24} | {squad:<15} | Settore: {sector}"
        )
        print(
            f"    Investito: {fmt_eur(inv_eur)} | PnL: {fmt_eur(pnl_eur, True)} ({fmt_pct(pnl_pct)}) | "
            f"Picco: {fmt_pct(peak_pct)} | Prezzo 0ms: {cur_price:.2f} €"
        )
        print(f"    Stato Scudo: {shield_str}")

    scanner = state.get("classifica_scanner_quantitativo_5m", [])
    if scanner:
        print("\n" + "─" * 90)
        print(" 📡 SCANNER V7.0 HIGH-BETA (12 TITOLI EUR • PROFIT-VELOCITY + KAUFMAN ER + 0ms)")
        print("─" * 90)
        for item in scanner:
            tk = item.get("ticker", "")
            price = float(item.get("live_price_eur", 0.0))
            rsi = float(item.get("rsi_5m", 50.0))
            vel_m = float(item.get("profit_velocity_mult", item.get("atr_elastic_scale", 1.0)))
            k_er = float(item.get("kaufman_efficiency_ratio", 0.35))
            hook = "🟢 Hook:SÌ" if item.get("green_hook_confirmed") else "🔴 Hook:NO"
            qscore = float(item.get("quant_buy_score", 0.0))
            phase = item.get("fase_onda_sinusoidale", "N/D")
            print(
                f" • {tk:<8} | {price:>7.2f} € | RSI: {rsi:>4.1f} | "
                f"Vel: {vel_m:.2f}x | ER: {k_er:.2f} | {hook} | Score: {qscore:>4.1f} | {phase}"
            )

    radar = state.get("radar_onda_notturna_wall_street", {})
    if radar:
        print("\n" + "─" * 90)
        print(
            f" 🌙 RADAR ONDA NOTTURNA (17:15-17:30) — "
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

    print(f" Anno Fiscale:          {tax.get('anno_fiscale', 2026)}")
    print(f" Broker / Conto:        {tax.get('broker', 'Trading 212')} (ID: {state.get('account_id', 52318994)})")
    print(f" Codice Stato Estero:   {tax.get('stato_estero_codice', '040 / 031')}")
    print("─" * 90)
    print(" 📋 QUADRO W (Monitoraggio Fiscale Attività Finanziarie Estere & IVAFE 0,20%)")
    print(f"    • Valore Iniziale:      {fmt_eur(float(tax.get('valore_iniziale_quadro_w_eur', 100.0)))}")
    print(f"    • Valore Finale Stim.:  {fmt_eur(float(q_w.get('Valore_Finale_31_12_EUR', tax.get('valore_finale_stimato_quadro_w_eur', 101.0))))}")
    print(f"    • Giorni Detenzione:    {tax.get('giorni_detenzione_ivafe', 365)} giorni")
    print(f"    • IVAFE da Versare:     0,00 € ({q_w.get('Nota_IVAFE', 'Esente sotto soglia minima 12,00 EUR')})")
    print("─" * 90)
    print(" 📋 QUADRO T (Plusvalenze / Minusvalenze Finanziarie — Imposta Sostitutiva 26% LIFO)")
    closed = tax.get("operazioni_chiuse", [])
    print(f"    • Operazioni Chiuse:    {len(closed)}")
    print(f"    • Totale Corrispettivi: {fmt_eur(float(tax.get('totale_corrispettivi_vendita_eur', 0.0)))}")
    print(f"    • Totale Costi LIFO:    {fmt_eur(float(tax.get('totale_costi_carico_lifo_eur', 0.0)))}")
    print(f"    • Plusvalenze Lorde:    {fmt_eur(float(tax.get('plusvalenze_lorde_eur', 0.0)), True)}")
    print(f"    • Minusvalenze Comp.:   {fmt_eur(float(tax.get('minusvalenze_lorde_eur', 0.0)))}")
    print(f"    • Imponibile Netto:     {fmt_eur(float(tax.get('imponibile_netto_eur', 0.0)), True)}")
    print(f"    • Imposta 26% Teorica:  {fmt_eur(float(tax.get('imposta_sostitutiva_26_eur', 0.0)))} (0,00 € F24 sotto franchigia 12,00 €)")

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


def generate_dashboard_html(state: dict, tax: dict) -> str:
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

    cards_html = ""
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
              <span class="slot-tag">CARTUCCIA #{slot} • {pos.get('settore_markowitz', '')}</span>
              <h3>{pos.get('name', tk)} <small>({tk})</small></h3>
            </div>
            <div class="price-pill {color_cls}">{fmt_pct(pnl_pct)}</div>
          </div>
          <div class="metrics-grid">
            <div><span>Capitale Investito</span><strong>{fmt_eur(float(pos.get('invested_eur', 0.0)))}</strong></div>
            <div><span>PnL Fluttuante</span><strong class="{color_cls}">{fmt_eur(pnl_eur, True)}</strong></div>
            <div><span>Picco Toccato</span><strong>{fmt_pct(peak_pct)}</strong></div>
            <div><span>Prezzo 0ms Live</span><strong>{float(pos.get('current_price_eur', 0.0)):.2f} €</strong></div>
          </div>
          <div class="shield-bar">{badge} • RSI 5m: {float(pos.get('rsi_5m', 50.0)):.1f}</div>
        </div>
        """

    scanner_rows = ""
    for item in scanner:
        hook_badge = '<span class="badge-ok">🟢 SÌ (Verde)</span>' if item.get("green_hook_confirmed") else '<span class="badge-wait">🔴 NO (Attesa)</span>'
        scanner_rows += f"""
        <tr>
          <td><strong>{item.get('ticker', '')}</strong> <small>{item.get('name', '')}</small></td>
          <td>{item.get('sector', '')}</td>
          <td>{float(item.get('live_price_eur', 0.0)):.2f} €</td>
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

    progress_pct = max(0.0, min(100.0, ((val_100 - 100.0) / 30.0) * 100.0))

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Trading 212 Autonomous Quant Bot — V6.5 Institutional Zero-Latency</title>
  <style>
    :root {{
      --bg: #080b11;
      --panel: #111723;
      --panel-2: #172031;
      --border: #25324a;
      --text: #f1f5f9;
      --muted: #94a3b8;
      --gold: #f59e0b;
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
    .container {{ max-width: 1280px; margin: 0 auto; }}
    .header {{
      display: flex; justify-content: space-between; align-items: center;
      flex-wrap: wrap; gap: 16px; padding: 24px;
      background: linear-gradient(135deg, #111827 0%, #0f172a 100%);
      border: 1px solid var(--border); border-radius: 16px; margin-bottom: 24px;
    }}
    .header h1 {{ font-size: 1.45rem; letter-spacing: -0.02em; }}
    .header p {{ color: var(--muted); font-size: 0.9rem; margin-top: 4px; }}
    .status-pill {{
      background: rgba(16, 185, 129, 0.15); border: 1px solid var(--green);
      color: #34d399; padding: 8px 16px; border-radius: 999px; font-weight: 600; font-size: 0.85rem;
    }}
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
      font-size: 1.1rem; font-weight: 700; margin: 26px 0 14px;
      display: flex; align-items: center; gap: 8px;
    }}
    .cards-grid {{
      display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr));
      gap: 16px;
    }}
    .card {{
      background: var(--panel); border: 1px solid var(--border);
      border-radius: 14px; padding: 18px;
    }}
    .card-head {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }}
    .slot-tag {{ font-size: 0.72rem; color: var(--blue); text-transform: uppercase; font-weight: 700; }}
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
      border: 1px solid var(--border); border-radius: 14px; overflow: hidden; font-size: 0.88rem;
    }}
    th, td {{ padding: 12px 14px; text-align: left; border-bottom: 1px solid var(--border); }}
    th {{ background: var(--panel-2); color: var(--muted); font-size: 0.76rem; text-transform: uppercase; }}
    .badge-ok {{ color: var(--green); font-weight: 700; }}
    .badge-wait {{ color: var(--muted); }}
    .shields-grid {{
      display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px;
    }}
    .shield-item {{
      background: var(--panel); border: 1px solid var(--border);
      padding: 14px; border-radius: 12px; font-size: 0.85rem;
    }}
    .shield-item strong {{ color: var(--blue); display: block; margin-bottom: 4px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <h1>🛡️ Trading 212 Autonomous Quant Bot — V6.5 Institutional Zero-Latency</h1>
        <p>Conto ID: 52318994 (EUR) • 4 Cartucce 2+2 Senza Tetto • 12 Blindature Istituzionali • Ciclo #{cycle} ({updated_at[:19]})</p>
      </div>
      <div class="status-pill">🟢 MOTORE V6.5 ATTIVO (0ms Zero-Latency)</div>
    </div>

    <div class="kpi-grid">
      <div class="kpi">
        <span>Valore Portafoglio (Base 100 €)</span>
        <h2 class="{'pos' if net_profit >= 0 else 'neg'}">{fmt_eur(val_100)}</h2>
        <small>Profitto Totale: {fmt_eur(net_profit, True)} ({fmt_pct(net_profit)})</small>
      </div>
      <div class="kpi">
        <span>Utili Realizzati in Cassa</span>
        <h2 class="pos">{fmt_eur(realized_net, True)}</h2>
        <small>Già contabilizzati nel Registro 730 LIFO</small>
      </div>
      <div class="kpi">
        <span>PnL Aperto (4 Cartucce)</span>
        <h2 class="{'pos' if open_pnl >= 0 else 'neg'}">{fmt_eur(open_pnl, True)}</h2>
        <small>Investiti: {fmt_eur(invested)} • Cassa: {fmt_eur(free_cash)}</small>
      </div>
      <div class="kpi">
        <span>Taglia Cartuccia Kelly</span>
        <h2>{fmt_eur(dyn_slot)}</h2>
        <small>Auto-Compounding su {fmt_eur(kelly_budget)} attivi</small>
      </div>
    </div>

    <div class="progress-wrap">
      <div style="display:flex; justify-content:space-between; font-size:0.88rem; flex-wrap:wrap; gap:8px;">
        <strong>🎯 Traguardo Cash-Out Automatico (+30,00%): 130,00 €</strong>
        <span>Avanzamento: {progress_pct:.1f}% ({fmt_eur(val_100)} / 130,00 €) • Radar 17:15: {radar.get('verdict', 'N/D')} (Nasdaq {fmt_pct(float(radar.get('nasdaq_change_pct', 0.0)))})</span>
      </div>
      <div class="progress-bar-bg"><div class="progress-bar-fill"></div></div>
    </div>

    <div class="section-title">🎯 Le 4 Cartucce Attive (Schema 2+2 • Vincolo Markowitz 4 Settori)</div>
    <div class="cards-grid">{cards_html}</div>

    <div class="section-title">📡 Scanner Sinusoidale a 5 Minuti + Fusione Zero-Latency (0ms)</div>
    <table>
      <thead>
        <tr>
          <th>Titolo (EUR)</th><th>Settore Markowitz</th><th>Prezzo 0ms</th>
          <th>RSI 5m</th><th>ATR Mult</th><th>Scudo / Ritracc.</th><th>Uncino Verde</th><th>Quant Score</th><th>Fase Onda 5m</th>
        </tr>
      </thead>
      <tbody>{scanner_rows}</tbody>
    </table>

    <div class="section-title">🇮🇹 Registro Fiscale Modello 730 (Quadro T LIFO — Operazioni Chiuse: {len(closed_trades)})</div>
    <table>
      <thead>
        <tr>
          <th>Data/Ora</th><th>Titolo</th><th>Quantità</th><th>Costo Carico LIFO</th>
          <th>Ricavo Vendita</th><th>Plus/Minus Netto</th>
        </tr>
      </thead>
      <tbody>{closed_rows}</tbody>
    </table>

    <div class="section-title">🏛️ Le 12 Blindature Istituzionali Attive (V6.5)</div>
    <div class="shields-grid">
      <div class="shield-item"><strong>1. Pre-Scudo Salva-Utile</strong>Da +0,60% blocca un pavimento garantito a +0,25% (+0,42% → +0,20% con Cassaforte attiva).</div>
      <div class="shield-item"><strong>2. Filtro Uncino Verde</strong>Vietato comprare su candele rosse in caduta libera: richiede candela verde o minimo crescente.</div>
      <div class="shield-item"><strong>3. Raccolto Gap 09:00–09:30</strong>Stringe il ritracciamento a 0,14% sui gap di apertura mattutini >= +0,50%.</div>
      <div class="shield-item"><strong>4. Radar Onda Notturna 17:15</strong>Incrocia Nasdaq, S&P500 e VIX per tenere le onde vere e liquidare le creste in inversione.</div>
      <div class="shield-item"><strong>5. Scudo Weekend Venerdì</strong>Protegge il capitale dalle 63 ore di chiusura mercati del fine settimana.</div>
      <div class="shield-item"><strong>6. Interesse Composto Kelly</strong>Reinveste gli utili netti aumentando ogni cartuccia a {fmt_eur(dyn_slot)}.</div>
      <div class="shield-item"><strong>7. Vincolo Markowitz</strong>4 cartucce su 4 settori industriali diversi (mai ASML + Infineon insieme).</div>
      <div class="shield-item"><strong>8. Scudo Elastico ATR 5m</strong>Adatta attivazione e ritracciamento (0,80x–1,30x) alla volatilità reale a 5 minuti.</div>
      <div class="shield-item"><strong>9. Rotazione Fiscale 730</strong>Sblocca i titoli fermi >4h sotto VWAP compensando al 100% la minusvalenza.</div>
      <div class="shield-item"><strong>10. Cassaforte Giornaliera</strong>A +1,80 € di utile giornaliero blinda i parametri in modalità difesa capitale.</div>
      <div class="shield-item"><strong>11. Fusione Zero-Latency 0ms</strong>Inietta i prezzi live Trading 212 sulle candele 5m eliminando i 15m di ritardo XETRA.</div>
      <div class="shield-item"><strong>12. Scudo Macro USA 14:30</strong>Congela i nuovi acquisti tra le 14:28 e le 14:35 CET durante i dati CPI/NFP USA.</div>
    </div>
  </div>
</body>
</html>
"""


def cmd_dashboard() -> None:
    state = load_json(STATE_FILE)
    tax = load_json(TAX_FILE)
    html = generate_dashboard_html(state, tax)
    out_path = PROJECT_DIR / "dashboard_v6_5.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"✅ Dashboard HTML aggiornata in: {out_path}")


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
    print(f"🚀 Demone V6.5 avviato in background (PID: {proc.pid}) | Log: {DAEMON_LOG}")


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
    zip_path = dist_dir / "trading212-quant-v6.5-backup.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in PROJECT_FILES:
            fpath = PROJECT_DIR / rel
            if fpath.exists():
                zf.write(fpath, arcname=f"trading212-quant-v65/{rel}")
    print(f"📦 Pacchetto ZIP esportato in: {zip_path} ({zip_path.stat().st_size:,} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CLI Manager per Trading 212 Autonomous Quant Bot V6.5"
    )
    parser.add_argument(
        "command",
        choices=["status", "tax-730", "dashboard", "start", "stop", "export"],
        help="Comando da eseguire",
    )
    args = parser.parse_args()

    if args.command == "status":
        cmd_status()
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
