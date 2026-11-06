#!/usr/bin/env python3
"""
Real-Time Cash Profit Watcher for Trading 212 V7.0 Bot.
Monitors registro_fiscale_730.json and exits immediately when a new PROFITABLE trade
(risultato_fiscale_eur > 0) is closed in cash, waking up the agent in real time.
"""
import json
import pathlib
import sys
import time

BASE = pathlib.Path(__file__).resolve().parent
TAX_FILE = BASE / "registro_fiscale_730.json"


def load_ops():
    try:
        data = json.loads(TAX_FILE.read_text(encoding="utf-8"))
        return data.get("operazioni_chiuse", []), data
    except Exception:
        return [], {}


def main():
    initial_ops, _ = load_ops()
    seen_count = len(initial_ops)
    print(
        f"[WATCHER UTILI ATTIVO] In ascolto per nuovi GUADAGNI IN CASSA (operazioni attuali: {seen_count})...",
        flush=True,
    )

    while True:
        time.sleep(3)
        ops, data = load_ops()
        if len(ops) > seen_count:
            new_ops = ops[seen_count:]
            seen_count = len(ops)
            winning_ops = [op for op in new_ops if float(op.get("risultato_fiscale_eur", 0.0)) > 0]
            if winning_ops:
                plus = float(data.get("plusvalenze_lorde_eur", 0.0))
                minus = float(data.get("minusvalenze_lorde_eur", 0.0))
                net_cassa = round(plus - minus, 2)
                print("\n🔔 NUOVO GUADAGNO IN CASSA RILEVATO!", flush=True)
                for op in winning_ops:
                    print(
                        f"   -> [{op.get('timestamp')}] {op.get('ticker')} | Qty: {op.get('quantity')} | "
                        f"Costo: {op.get('costo_lifo_eur'):.2f} EUR -> Ricavo: {op.get('corrispettivo_eur'):.2f} EUR | "
                        f"Guadagno Netto: +{op.get('risultato_fiscale_eur'):.2f} EUR",
                        flush=True,
                    )
                print(
                    f"💰 NUOVO SALDO CASSA REALIZZATO: {net_cassa:+.2f} EUR (Plusvalenze Lorde: +{plus:.2f} EUR)",
                    flush=True,
                )
                sys.exit(0)


if __name__ == "__main__":
    main()
