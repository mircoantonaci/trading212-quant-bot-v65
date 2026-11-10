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
    initial_ops, init_data = load_ops()
    seen_count = len(initial_ops)
    init_plus = float(init_data.get("plusvalenze_lorde_eur", 0.0))
    init_minus = float(init_data.get("minusvalenze_lorde_eur", 0.0))
    seen_net_cassa = round(init_plus - init_minus, 2)
    print(
        f"[WATCHER UTILI ATTIVO] In ascolto 1s per operazioni/cassa (op: {seen_count}, cassa: {seen_net_cassa:+.2f} EUR)...",
        flush=True,
    )

    while True:
        time.sleep(1)
        ops, data = load_ops()
        if not data:
            continue
        plus = float(data.get("plusvalenze_lorde_eur", 0.0))
        minus = float(data.get("minusvalenze_lorde_eur", 0.0))
        net_cassa = round(plus - minus, 2)
        if len(ops) > seen_count or abs(net_cassa - seen_net_cassa) >= 0.01:
            if len(ops) > seen_count:
                new_ops = ops[seen_count:]
                seen_count = len(ops)
                print("\n🔔 NUOVA OPERAZIONE CHIUSA IN TEMPO REALE!", flush=True)
                for op in new_ops:
                    pnl = float(op.get("risultato_fiscale_eur", 0.0))
                    tag = "INCASSO UTILE" if pnl >= 0 else "TAGLIO STOP/ROTAZIONE"
                    print(
                        f"   -> [{op.get('timestamp')}] {tag}: {op.get('ticker')} | Qty: {op.get('quantity')} | "
                        f"Costo: {op.get('costo_lifo_eur'):.2f} EUR -> Ricavo: {op.get('corrispettivo_eur'):.2f} EUR | "
                        f"Risultato: {pnl:+.2f} EUR",
                        flush=True,
                    )
            else:
                delta = round(net_cassa - seen_net_cassa, 2)
                tag = "INCASSO UTILE CLOUD/T212" if delta >= 0 else "ROTAZIONE CLOUD/T212"
                print(
                    f"\n🔔 VARIAZIONE CASSA CERTIFICATA T212 IN TEMPO REALE! ({tag}: {delta:+.2f} EUR)",
                    flush=True,
                )
            print(
                f"💰 NUOVO SALDO CASSA REALIZZATO: {net_cassa:+.2f} EUR (Plusvalenze Lorde: +{plus:.2f} EUR)",
                flush=True,
            )
            sys.exit(0)


if __name__ == "__main__":
    main()
