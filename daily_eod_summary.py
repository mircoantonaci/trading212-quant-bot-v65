#!/usr/bin/env python3
"""
daily_eod_summary.py — Breve Riassunto Serale di Fine Giornata (Trading 212 V11.5 LTS)
=======================================================================================
Sostituisce il vecchio watcher intraday per singolo trade (`watch_cash_profit.py`).
Da eseguire una sola volta a fine seduta (es. 17:38 Europe/Rome, dopo la chiusura XETRA
delle 17:30 e il checkpoint finale Cloud delle 17:36):
  1. Allinea opzionalmente lo stato dal Cloud (`--sync` -> `git pull --rebase origin main`)
  2. Stampa un riepilogo sintetico di:
     - Bilancio netto della giornata e valore finale portafoglio (base 100 EUR)
     - Movimenti CHIUSI nella giornata (ora, ticker, risultato EUR / %)
     - Posizioni APERTE a fine giornata (verifica reset 4/4 cartucce libere per le 09:00)
"""
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "trading212_state.json"
TAX_FILE = BASE_DIR / "registro_fiscale_730.json"
LONGTERM_FILE = BASE_DIR / "longterm_vault_1000e.json"
MARKET_TZ = ZoneInfo("Europe/Rome")


def fmt_eur(val: float, signed: bool = False) -> str:
    s = f"{val:+.2f}" if signed else f"{val:.2f}"
    return s.replace(".", ",") + " €"


def sync_from_cloud() -> bool:
    try:
        res = subprocess.run(
            ["git", "-C", str(BASE_DIR), "pull", "--rebase", "origin", "main"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return res.returncode == 0
    except Exception:
        return False


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def print_eod_summary(target_day: str, do_sync: bool = False) -> None:
    if do_sync:
        sync_from_cloud()

    state = load_json(STATE_FILE)
    tax = load_json(TAX_FILE)

    closed_all = tax.get("operazioni_chiuse", [])
    closed_today = [
        op for op in closed_all
        if str(op.get("timestamp", "")).startswith(target_day)
    ]

    wins = [op for op in closed_today if float(op.get("risultato_fiscale_eur", 0.0)) > 0]
    losses = [op for op in closed_today if float(op.get("risultato_fiscale_eur", 0.0)) < 0]
    day_net = round(sum(float(op.get("risultato_fiscale_eur", 0.0)) for op in closed_today), 2)
    wr = (len(wins) / len(closed_today) * 100.0) if closed_today else 0.0

    portfolio_val = float(state.get("valore_totale_portafoglio_100e_eur", 100.0))
    total_realized = float(state.get("profitto_realizzato_in_cassa_eur", 0.0))
    open_pnl = float(state.get("profitto_aperto_non_realizzato_eur", 0.0))
    free_cash = float(state.get("liquidita_libera_su_100e_eur", 0.0))
    updated_at = state.get("timestamp", "N/D")
    cartridges = state.get("cartucce_4x25_eur", [])

    print(f"📊 RIEPILOGO FINE GIORNATA — {target_day} (Stato: {updated_at})")
    print("─" * 74)
    print(
        f"💰 Portafoglio: {fmt_eur(portfolio_val)} | "
        f"Oggi Realizzato: {fmt_eur(day_net, signed=True)} "
        f"({len(closed_today)} chiusure: {len(wins)}V / {len(losses)}P, WR {wr:.0f}%) | "
        f"Cassa Storica: {fmt_eur(total_realized, signed=True)}"
    )
    print(f"💶 Liquidità Libera: {fmt_eur(free_cash)} | PnL Aperto: {fmt_eur(open_pnl, signed=True)}")

    print(f"\n✅ MOVIMENTI CHIUSI OGGI ({len(closed_today)}):")
    if not closed_today:
        print("   • Nessuna operazione chiusa registrata nella data selezionata.")
    else:
        for op in closed_today:
            hhmm = str(op.get("timestamp", ""))[11:16]
            tkr = str(op.get("ticker", "N/D"))
            costo = float(op.get("costo_lifo_eur", 0.0))
            ricavo = float(op.get("corrispettivo_eur", 0.0))
            pnl = float(op.get("risultato_fiscale_eur", 0.0))
            pct = (pnl / costo * 100.0) if costo > 0 else 0.0
            icon = "🟢" if pnl >= 0 else "🔴"
            print(
                f"   {icon} {hhmm} | {tkr:<9s} | {fmt_eur(costo)} -> {fmt_eur(ricavo)} | "
                f"{fmt_eur(pnl, signed=True)} ({pct:+.2f}%)"
            )

    free_slots = max(0, 4 - len(cartridges))
    print(f"\n📂 POSIZIONI APERTE A FINE SEDUTA ({len(cartridges)}/4 in Custodia Notturna C1 — {free_slots}/4 cartucce libere per domani 09:00):")
    if not cartridges:
        print("   • Nessuna posizione aperta (100% Cash EUR — 4/4 cartucce libere per domani alle 09:00).")
    else:
        for c in cartridges:
            tkr = str(c.get("ticker", "N/D"))
            inv = float(c.get("invested_eur", 0.0))
            cpnl = float(c.get("pnl_eur", 0.0))
            cpct = float(c.get("pnl_pct", 0.0))
            icon = "🟢" if cpnl >= 0 else "🟡"
            print(
                f"   {icon} Slot {c.get('slot', '?')}: {tkr:<9s} ({c.get('name', '')}) | "
                f"Investito: {fmt_eur(inv)} | PnL: {fmt_eur(cpnl, signed=True)} ({cpct:+.2f}%) "
                f"[C1: taglio rapido 09:05 se negativa o lenta]"
            )

    lt = load_json(LONGTERM_FILE)
    if lt:
        lt_val = float(lt.get("total_portfolio_value_eur", 1000.0))
        lt_ret_e = float(lt.get("total_net_return_eur", 0.0))
        lt_ret_p = float(lt.get("total_net_return_pct", 0.0))
        lt_inv = float(lt.get("invested_cost_eur", 0.0))
        lt_cash = float(lt.get("uninvested_cash_eur", 0.0))
        lt_pos = lt.get("posizioni_attive", [])
        print("─" * 74)
        print(
            f"🏛️ PORTAFOGLIO #2 LUNGO TERMINE + ORO (Base 1.000,00 €): {fmt_eur(lt_val)} "
            f"({fmt_eur(lt_ret_e, signed=True)} / {lt_ret_p:+.2f}%)"
        )
        print(
            f"   • Investiti: {fmt_eur(lt_inv)} su {len(lt_pos)} strumenti | "
            f"Liquidi Vault: {fmt_eur(lt_cash)} | Regime: {lt.get('regime_dual_momentum', 'N/D')}"
        )
    print("─" * 74)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Riepilogo sintetico di fine giornata T212 V11.5")
    parser.add_argument(
        "--date",
        default=datetime.datetime.now(MARKET_TZ).strftime("%Y-%m-%d"),
        help="Data da riepilogare in formato YYYY-MM-DD (default: oggi Europe/Rome)",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Sincronizza prima lo stato dal repository Cloud (git pull --rebase origin main)",
    )
    args = parser.parse_args()
    print_eod_summary(args.date, do_sync=args.sync)
