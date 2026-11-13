#!/usr/bin/env python3
"""
Real-Time Gains & Stop-Cuts Watcher — Trading 212 V11.2 LTS "Zero Cerotti".
Monitora in sola lettura e a impatto zero sui rate-limit del demone Cloud H24:
1. Cassa certificata live Trading 212 (`GET /equity/account/cash` ogni 12s a Borsa aperta 08:59-17:38 Europe/Rome)
2. Registro locale `registro_fiscale_730.json` + sincronizzazione `git pull --ff-only` su evento
Non appena scatta un INCASSO UTILE (>= +0,01 EUR) o un TAGLIO SCUDO/AIRBAG (<= -0,01 EUR),
stampa i dettagli dell'eseguito reale e termina con exit 0 per svegliare l'agente in tempo reale.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

BASE = pathlib.Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from t212_daemon_100e import load_client  # noqa: E402

TAX_FILE = BASE / "registro_fiscale_730.json"
MARKET_TZ = ZoneInfo("Europe/Rome")


def load_local_ops() -> tuple[list[dict], dict]:
    try:
        data = json.loads(TAX_FILE.read_text(encoding="utf-8"))
        return data.get("operazioni_chiuse", []), data
    except Exception:
        return [], {}


def is_live_watch_window(now_rome: datetime.datetime) -> bool:
    if now_rome.weekday() >= 5:
        return False
    hm = now_rome.hour * 60 + now_rome.minute
    return (8 * 60 + 59) <= hm <= (17 * 60 + 38)


def fetch_recent_sell_fills(client) -> list[str]:
    lines: list[str] = []
    try:
        res = client._request("GET", "/equity/history/orders?limit=6")
        items = res.get("items", []) if isinstance(res, dict) else []
        for it in items[:4]:
            order = it.get("order", it) if isinstance(it, dict) else {}
            fill = it.get("fill", {}) if isinstance(it, dict) else {}
            tkr = order.get("ticker", "N/D")
            side = order.get("side") or ("SELL" if float(order.get("filledQuantity") or order.get("quantity") or 0) < 0 else "")
            qty = fill.get("quantity") or order.get("filledQuantity") or order.get("quantity")
            px = fill.get("price") or order.get("fillPrice") or order.get("limitPrice")
            ts = fill.get("filledAt") or order.get("dateExecuted") or order.get("dateModified") or ""
            lines.append(f"   • Storico T212: [{ts}] {side} {tkr} | Qty: {qty} @ {px} EUR")
    except Exception:
        pass
    return lines


def try_fast_git_sync() -> None:
    try:
        subprocess.run(
            ["git", "-C", str(BASE), "pull", "--ff-only", "origin", "main"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except Exception:
        pass


def main() -> None:
    try_fast_git_sync()
    client = load_client()
    initial_ops, init_data = load_local_ops()
    seen_count = len(initial_ops)
    init_plus = float(init_data.get("plusvalenze_lorde_eur", 0.0))
    init_minus = float(init_data.get("minusvalenze_lorde_eur", 0.0))
    seen_local_net = round(init_plus - init_minus, 2)

    seen_t212_net: float | None = None
    try:
        cash = client.get_account_cash()
        if isinstance(cash, dict) and cash.get("result") is not None:
            seen_t212_net = round(float(cash["result"]), 2)
    except Exception as exc:
        if "Errno 8" in str(exc) or "nodename nor servname" in str(exc):
            print(f"[ERRORE RETE AVVIO] Accesso API bloccato dal sandbox: {exc}", flush=True)
            sys.exit(2)
        print(f"[AVVISO] Lettura iniziale cassa T212 differita: {exc}", flush=True)

    now_rome = datetime.datetime.now(MARKET_TZ)
    mode_lbl = "LIVE 12s (Borsa Aperta)" if is_live_watch_window(now_rome) else "STAND-BY NOTTURNO -> Auto-Live 08:59 CET"
    base_net = seen_t212_net if seen_t212_net is not None else seen_local_net

    print(
        f"[WATCHER V11.2 ARMATO] Ora: {now_rome.strftime('%Y-%m-%d %H:%M:%S %Z')} | "
        f"Modalità: {mode_lbl} | Op. 730: {seen_count} | Cassa Certificata T212: {base_net:+.2f} EUR",
        flush=True,
    )

    last_api_poll_ts = time.time()
    last_git_sync_ts = time.time()

    while True:
        now_rome = datetime.datetime.now(MARKET_TZ)
        live_win = is_live_watch_window(now_rome)
        time.sleep(2.0 if live_win else 20.0)

        # 1. Controllo file locale 730 (istantaneo)
        ops, data = load_local_ops()
        if data:
            plus = float(data.get("plusvalenze_lorde_eur", 0.0))
            minus = float(data.get("minusvalenze_lorde_eur", 0.0))
            local_net = round(plus - minus, 2)
            if len(ops) > seen_count or abs(local_net - seen_local_net) >= 0.01:
                # Se la cassa T212 certificata era già allineata a questo saldo (evento già notificato in live 12s), aggiorna solo il puntatore senza eco duplicata
                if seen_t212_net is not None and abs(local_net - seen_t212_net) < 0.01:
                    seen_count = len(ops)
                    seen_local_net = local_net
                    continue
                if len(ops) > seen_count:
                    new_ops = ops[seen_count:]
                    print("\n🔔 OPERAZIONE CHIUSA RILEVATA NEL REGISTRO 730!", flush=True)
                    for op in new_ops:
                        pnl = float(op.get("risultato_fiscale_eur", 0.0))
                        tag = "🟢 INCASSO GUADAGNO" if pnl >= 0 else "🛡️ TAGLIO PROTETTO / AIRBAG"
                        print(
                            f"   -> [{op.get('timestamp')}] {tag}: {op.get('ticker')} | Qty: {op.get('quantity')} | "
                            f"Costo: {float(op.get('costo_lifo_eur', 0.0)):.2f} EUR -> "
                            f"Ricavo: {float(op.get('corrispettivo_eur', 0.0)):.2f} EUR | "
                            f"Risultato: {pnl:+.2f} EUR",
                            flush=True,
                        )
                else:
                    delta_l = round(local_net - seen_local_net, 2)
                    tag = "🟢 INCASSO GUADAGNO" if delta_l >= 0 else "🛡️ TAGLIO PROTETTO / AIRBAG"
                    print(f"\n🔔 VARIAZIONE CASSA 730 RILEVATA ({tag}: {delta_l:+.2f} EUR)", flush=True)
                print(
                    f"💰 NUOVO SALDO CASSA REALIZZATO: {local_net:+.2f} EUR (Plusvalenze Lorde: +{plus:.2f} EUR)",
                    flush=True,
                )
                sys.exit(0)

        if not live_win:
            continue

        # 2. Durante Borsa aperta (08:59-17:38 Europe/Rome): lettura diretta cassa certificata Trading 212 ogni 12s
        now_ts = time.time()
        if (now_ts - last_api_poll_ts) >= 12.0:
            last_api_poll_ts = now_ts
            try:
                cash_live = client.get_account_cash()
                if isinstance(cash_live, dict) and cash_live.get("result") is not None:
                    cur_t212_net = round(float(cash_live["result"]), 2)
                    if seen_t212_net is None:
                        seen_t212_net = cur_t212_net
                    elif abs(cur_t212_net - seen_t212_net) >= 0.01:
                        delta = round(cur_t212_net - seen_t212_net, 2)
                        tag = "🟢 INCASSO GUADAGNO LIVE T212" if delta >= 0 else "🛡️ TAGLIO SCUDO / AIRBAG LIVE T212"
                        try_fast_git_sync()
                        print(
                            f"\n🔔 [{now_rome.strftime('%H:%M:%S')}] {tag}: {delta:+.2f} EUR "
                            f"(Cassa precedente: {seen_t212_net:+.2f} EUR -> Nuova Cassa Certificata: {cur_t212_net:+.2f} EUR)",
                            flush=True,
                        )
                        for fill_line in fetch_recent_sell_fills(client):
                            print(fill_line, flush=True)
                        ops_after, _ = load_local_ops()
                        if len(ops_after) > seen_count:
                            for op in ops_after[seen_count:]:
                                pnl = float(op.get("risultato_fiscale_eur", 0.0))
                                print(
                                    f"   • Dettaglio 730: [{op.get('timestamp')}] {op.get('ticker')} | "
                                    f"Qty: {op.get('quantity')} | Risultato: {pnl:+.2f} EUR",
                                    flush=True,
                                )
                        sys.exit(0)
            except Exception:
                pass

        # 3. Sincronizzazione leggera fast-forward ogni 180s per tenere allineata anche la dashboard locale
        if (now_ts - last_git_sync_ts) >= 180.0:
            last_git_sync_ts = now_ts
            try_fast_git_sync()


if __name__ == "__main__":
    main()
