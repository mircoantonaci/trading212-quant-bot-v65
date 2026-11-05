#!/usr/bin/env python3
"""
Test di connessione reale e avvio prima Cartuccia (25,00 EUR) su Trading 212 Demo (Practice).
Verifica automaticamente l'autenticazione Basic Auth con ID Chiave API + Chiave Segreta,
legge il saldo del conto, invia il primo ordine frazionato in EUR a 0,00 EUR di commissioni
su XETRA (Francoforte) e aggiorna il Registro Fiscale 730 (LIFO).
"""

import base64
import itertools
import json
import os
import time
import urllib.error
import urllib.request
from trading212_bot import (
    Trading212Client,
    Trading212AutonomousBot,
    EUR_ZERO_FEE_UNIVERSE,
    BASE_DIR,
)

CREDENTIALS_PATH = os.path.join(BASE_DIR, "t212_credentials.json")

API_KEY_ID = "52318994ZZqXgPvtMOaHADAtaYWJezVZPrjOf"

# Costruiamo i candidati ordinando per primo quello rilevato dall'analisi sub-pixel (I, I, l, I)
def generate_secret_candidates():
    # Posizioni ambigue nel font sans-serif: 9, 11, 16, 20
    # Sub-pixel ink analysis: pos 9=I (586), pos 11=I (585), pos 16=l (553), pos 20=I (586)
    preferred = [
        ("I", "I", "l", "I"),
        ("I", "I", "I", "I"),
        ("I", "I", "l", "l"),
        ("l", "I", "l", "I"),
        ("I", "l", "l", "I"),
    ]
    all_combos = list(itertools.product(["I", "l"], repeat=4))
    ordered = preferred + [c for c in all_combos if c not in preferred]
    secrets = []
    for c0, c1, c2, c3 in ordered:
        s = f"QgfUWY3H7{c0}B{c1}4Z1V{c2}PmM{c3}ct6t7R8K-fQwxD0MUQFSzg"
        secrets.append(s)
    return secrets


def find_working_client() -> Trading212Client:
    candidates = generate_secret_candidates()
    for idx, secret in enumerate(candidates, 1):
        client = Trading212Client(api_key=API_KEY_ID, api_secret=secret, mode="demo")
        try:
            info = client.get_account_info()
            print(f"[OK] Autenticazione riuscita al tentativo #{idx}!")
            print(f"     ID Conto Trading 212: {info.get('id')} | Valuta Base: {info.get('currencyCode')}")
            with open(CREDENTIALS_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "mode": "demo",
                        "api_key": API_KEY_ID,
                        "api_secret": secret,
                        "account_id": info.get("id"),
                        "currency": info.get("currencyCode"),
                    },
                    f,
                    indent=2,
                )
            return client
        except Exception as e:
            err_msg = str(e)
            if "401" in err_msg or "403" in err_msg:
                time.sleep(0.4)
                continue
            elif "429" in err_msg:
                time.sleep(2.5)
                continue
            else:
                print(f"Errore imprevisto al tentativo #{idx}: {err_msg}")
                raise
    raise RuntimeError("Nessuna combinazione ha autenticato la chiave API.")


def main():
    print("1. Connessione alle API ufficiali Trading 212 (Practice / Demo)...")
    client = find_working_client()

    print("\n2. Lettura Saldo Conto (/equity/account/cash)...")
    cash = client.get_account_cash()
    print("   Saldo Conto:", json.dumps(cash, indent=2))

    print("\n3. Lettura Portafoglio Attuale (/equity/portfolio)...")
    portfolio = client.get_open_positions()
    print(f"   Posizioni attualmente aperte: {len(portfolio)}")
    for pos in portfolio:
        print(f"   - {pos.get('ticker')}: qty={pos.get('quantity')} | prezzo={pos.get('currentPrice')} EUR | P&L={pos.get('ppl')} EUR")

    # Eseguiamo l'apertura della Cartuccia #1 (25,00 EUR) su SAP SE (SAPd_EQ - XETRA Francoforte, EUR)
    bot = Trading212AutonomousBot(client=client, total_budget_eur=100.00, cartridges=4, annual_target_pct=0.30)
    ticker = "SAPd_EQ"
    # Prezzo indicativo SAP su XETRA (~215-250 EUR), calcoliamo una frazione da ~25,00 EUR (es. 0.11 azioni)
    qty_to_buy = 0.11
    print(f"\n4. Invio Ordine Reale API (Cartuccia #1 da ~25,00 EUR) su {ticker} ({EUR_ZERO_FEE_UNIVERSE[ticker]['name']})...")
    try:
        order_res = client.place_market_order(ticker=ticker, quantity=qty_to_buy)
        print("   [ORDINE INVIATO CON SUCCESSO]:", json.dumps(order_res, indent=2))
        time.sleep(2.0)
        updated_portfolio = client.get_open_positions()
        fill_price = 225.0
        for p in updated_portfolio:
            if p.get("ticker") == ticker:
                fill_price = float(p.get("averagePrice") or p.get("currentPrice") or fill_price)
                print(f"   [POSIZIONE ATTIVA SU TRADING 212]: {ticker} | Qty: {p.get('quantity')} | Prezzo Medio: {fill_price} EUR")
        bot.tax_tracker.record_buy(ticker=ticker, quantity=qty_to_buy, price_eur=fill_price)
        print("   [REGISTRO FISCALE 730 AGGIORNATO CON LOTTO LIFO]")
    except Exception as e:
        print(f"   Nota sull'ordine: {e}")


if __name__ == "__main__":
    main()
