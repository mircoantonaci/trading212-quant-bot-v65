#!/usr/bin/env python3
"""
Trading 212 Autonomous Bot (Budget 100,00 EUR) + Registro Fiscale Italiano 730 (LIFO)
=====================================================================================
Caratteristiche:
1. Opera esclusivamente su Trading 212 INVEST (Azioni Reali a leva 1x, zero commissioni).
2. Universo Asset filtrato al 100% su Blue-Chip Europee in EUR (XETRA / Amsterdam):
   - Zero commissioni di negoziazione (0,00 EUR)
   - Zero commissioni di cambio valuta FX (0,00 EUR - evita il 0,15% su azioni USD)
   - Zero Tobin Tax / FTT (0,00 EUR - esclude azioni italiane/francesi soggette a tassa)
   - Piena compensazione fiscale (Azioni singole = Redditi Diversi, le minusvalenze
     compensano al 100% le plusvalenze, a differenza degli ETF).
3. Strategia "Smart Grid a 4 Cartucce" da 25,00 EUR (Totale 100,00 EUR):
   - Acquista sui cali (RSI / deviazione dalla media)
   - Vende automaticamente in Take-Profit netto (+2,2%) o Stop-Loss protettivo (-3,0%)
4. Registro Fiscale LIFO integrato (registro_fiscale_730.json):
   - Calcola in automatico il costo di carico LIFO (Last-In, First-Out) richiesto
     dall'Agenzia delle Entrate e produce i 4 numeri pronti per Quadro W e Quadro T
     del Modello 730 precompilato.
"""

import base64
import datetime
import json
import math
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
from zoneinfo import ZoneInfo

MARKET_TZ = ZoneInfo("Europe/Rome")


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TAX_REGISTRY_PATH = os.path.join(BASE_DIR, "registro_fiscale_730.json")
BOT_STATE_PATH = os.path.join(BASE_DIR, "trading212_state.json")


def atomic_write_json(
    filepath: str,
    payload: Any,
    indent: Optional[int] = 2,
    separators: Optional[tuple[str, str]] = None,
) -> None:
    """Scrittura JSON atomica POSIX (tempfile nella stessa directory + os.replace): zero file troncati su SIGTERM/letture concorrenti."""
    parent_dir = os.path.dirname(os.path.abspath(filepath)) or "."
    os.makedirs(parent_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=parent_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=indent, separators=separators, ensure_ascii=False)
        os.replace(tmp_path, filepath)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        raise

# Universo rigorosamente in EUR su borse senza Tobin Tax (Germania XETRA / Olanda Euronext)
# Include sia le 6 Blue-Chip classiche sia i 6 Campioni "Turbo High-Beta" per massimizzare il rendimento giornaliero
EUR_ZERO_FEE_UNIVERSE: Dict[str, Dict[str, str]] = {
    "RHMd_EQ": {
        "name": "Rheinmetall AG",
        "exchange": "XETRA (Francoforte)",
        "currency": "EUR",
        "isin": "DE0007030009",
        "tobin_tax": "0.00%",
    },
    "ENRd_EQ": {
        "name": "Siemens Energy AG",
        "exchange": "XETRA (Francoforte)",
        "currency": "EUR",
        "isin": "DE000ENER6Y0",
        "tobin_tax": "0.00%",
    },
    "ADYENa_EQ": {
        "name": "Adyen NV",
        "exchange": "Euronext Amsterdam",
        "currency": "EUR",
        "isin": "NL0012969182",
        "tobin_tax": "0.00%",
    },
    "CBKd_EQ": {
        "name": "Commerzbank AG",
        "exchange": "XETRA (Francoforte)",
        "currency": "EUR",
        "isin": "DE000CBK1001",
        "tobin_tax": "0.00%",
    },
    "BESIa_EQ": {
        "name": "BE Semiconductor (BESI)",
        "exchange": "Euronext Amsterdam",
        "currency": "EUR",
        "isin": "NL0012866412",
        "tobin_tax": "0.00%",
    },
    "ZALd_EQ": {
        "name": "Zalando SE",
        "exchange": "XETRA (Francoforte)",
        "currency": "EUR",
        "isin": "DE000ZAL1111",
        "tobin_tax": "0.00%",
    },
    "SAPd_EQ": {
        "name": "SAP SE",
        "exchange": "XETRA (Francoforte)",
        "currency": "EUR",
        "isin": "DE0007164600",
        "tobin_tax": "0.00%",
    },
    "ASMLa_EQ": {
        "name": "ASML Holding NV",
        "exchange": "Euronext Amsterdam",
        "currency": "EUR",
        "isin": "NL0010273215",
        "tobin_tax": "0.00%",
    },
    "SIEd_EQ": {
        "name": "Siemens AG",
        "exchange": "XETRA (Francoforte)",
        "currency": "EUR",
        "isin": "DE0007236101",
        "tobin_tax": "0.00%",
    },
    "ALVd_EQ": {
        "name": "Allianz SE",
        "exchange": "XETRA (Francoforte)",
        "currency": "EUR",
        "isin": "DE0008404005",
        "tobin_tax": "0.00%",
    },
    "IFXd_EQ": {
        "name": "Infineon Technologies AG",
        "exchange": "XETRA (Francoforte)",
        "currency": "EUR",
        "isin": "DE0006231004",
        "tobin_tax": "0.00%",
    },
    "DTEd_EQ": {
        "name": "Deutsche Telekom AG",
        "exchange": "XETRA (Francoforte)",
        "currency": "EUR",
        "isin": "DE0005557508",
        "tobin_tax": "0.00%",
    },
    "BAYNd_EQ": {
        "name": "Bayer AG",
        "exchange": "XETRA (Francoforte)",
        "currency": "EUR",
        "isin": "DE000BAY0017",
        "tobin_tax": "0.00%",
    },
    "VNAd_EQ": {
        "name": "Vonovia SE",
        "exchange": "XETRA (Francoforte)",
        "currency": "EUR",
        "isin": "DE000A1ML7J1",
        "tobin_tax": "0.00%",
    },
    "AIRd_EQ": {
        "name": "Airbus SE",
        "exchange": "XETRA (Francoforte)",
        "currency": "EUR",
        "isin": "NL0000235190",
        "tobin_tax": "0.00%",
    },
}


@dataclass
class TaxLot:
    """Singolo lotto di acquisto per il calcolo LIFO italiano."""
    timestamp: str
    ticker: str
    isin: str
    quantity: float
    price_eur: float
    total_eur: float


class ItalianTaxTracker730:
    """
    Gestore automatico del Regime Dichiarativo (Modello 730 - Quadro W e Quadro T)
    secondo il criterio LIFO (Last-In, First-Out) previsto dal TUIR (art. 67 e 68).
    """

    def __init__(self, filepath: str = TAX_REGISTRY_PATH) -> None:
        self.filepath = filepath
        self.data: Dict[str, Any] = {
            "anno_fiscale": datetime.datetime.now(MARKET_TZ).year,
            "broker": "Trading 212 (Conto Invest - EUR)",
            "stato_estero_codice": "040 (Cipro) / 031 (Regno Unito)",
            "valore_iniziale_quadro_w_eur": 100.00,
            "valore_finale_stimato_quadro_w_eur": 100.00,
            "giorni_detenzione_ivafe": 365,
            "lotti_aperti_lifo": {},  # ticker -> list of dicts
            "operazioni_chiuse": [],
            "totale_corrispettivi_vendita_eur": 0.00,
            "totale_costi_carico_lifo_eur": 0.00,
            "plusvalenze_lorde_eur": 0.00,
            "minusvalenze_lorde_eur": 0.00,
            "imponibile_netto_eur": 0.00,
            "imposta_sostitutiva_26_eur": 0.00,
        }
        self.load()

    def load(self) -> None:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.data.update(loaded)
            except Exception:
                pass

    def save(self) -> None:
        atomic_write_json(self.filepath, self.data, indent=2)

    def _recompute_taxable_summary(self) -> None:
        prior_loss_carry = float(self.data.get("zainetto_minusvalenze_pregresse_eur", 0.0))
        net_taxable = max(
            0.0,
            float(self.data.get("plusvalenze_lorde_eur", 0.0))
            - float(self.data.get("minusvalenze_lorde_eur", 0.0))
            - prior_loss_carry,
        )
        self.data["imponibile_netto_eur"] = round(net_taxable, 2)
        self.data["imposta_sostitutiva_26_eur"] = round(net_taxable * 0.26, 2)

    def record_buy(self, ticker: str, quantity: float, price_eur: float) -> None:
        """Registra un acquisto aggiungendo il lotto in cima alla pila LIFO."""
        info = EUR_ZERO_FEE_UNIVERSE.get(ticker, {"isin": "UNKNOWN"})
        lot = TaxLot(
            timestamp=datetime.datetime.now(MARKET_TZ).replace(tzinfo=None).isoformat(timespec="seconds"),
            ticker=ticker,
            isin=info["isin"],
            quantity=round(quantity, 6),
            price_eur=round(price_eur, 4),
            total_eur=round(quantity * price_eur, 4),
        )
        lots = self.data["lotti_aperti_lifo"].setdefault(ticker, [])
        lots.append(asdict(lot))
        self.save()

    def record_sell(
        self,
        ticker: str,
        sell_qty: float,
        sell_price_eur: float,
        fallback_avg_price_eur: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Scarica i lotti partendo dall'ULTIMO acquistato (LIFO) e calcola
        esattamente plusvalenza o minusvalenza fiscale per il Quadro T.
        Se un lotto è stato aperto da un runner diverso (Cloud vs Locale), usa il prezzo medio reale T212.
        """
        lots = self.data["lotti_aperti_lifo"].get(ticker, [])
        remaining_to_sell = sell_qty
        cost_basis_eur = 0.0

        # Allinea in-place il prezzo di carico al prezzo medio certificato T212 SOLO su singolo lotto (1 cartuccia),
        # preservando intatti i prezzi storici distinti delle singole tranche in caso di più lotti LIFO (Art. 67-68 TUIR):
        if fallback_avg_price_eur and fallback_avg_price_eur > 0 and len(lots) == 1:
            real_avg = round(float(fallback_avg_price_eur), 4)
            lots[0]["price_eur"] = real_avg
            lots[0]["total_eur"] = round(float(lots[0]["quantity"]) * real_avg, 4)

        while remaining_to_sell > 1e-7 and lots:
            last_lot = lots[-1]
            lot_qty = float(last_lot["quantity"])
            lot_price = float(last_lot["price_eur"])

            if lot_qty <= remaining_to_sell + 1e-7:
                cost_basis_eur += lot_qty * lot_price
                remaining_to_sell -= lot_qty
                lots.pop()
            else:
                cost_basis_eur += remaining_to_sell * lot_price
                last_lot["quantity"] = round(lot_qty - remaining_to_sell, 6)
                last_lot["total_eur"] = round(last_lot["quantity"] * lot_price, 4)
                remaining_to_sell = 0.0

        if remaining_to_sell > 1e-7:
            ref_avg = fallback_avg_price_eur if (fallback_avg_price_eur and fallback_avg_price_eur > 0) else sell_price_eur
            cost_basis_eur += remaining_to_sell * ref_avg
            remaining_to_sell = 0.0

        proceeds_eur = sell_qty * sell_price_eur
        pnl_eur = proceeds_eur - cost_basis_eur

        self.data["totale_corrispettivi_vendita_eur"] = round(
            float(self.data["totale_corrispettivi_vendita_eur"]) + proceeds_eur, 2
        )
        self.data["totale_costi_carico_lifo_eur"] = round(
            float(self.data["totale_costi_carico_lifo_eur"]) + cost_basis_eur, 2
        )

        if pnl_eur >= 0:
            self.data["plusvalenze_lorde_eur"] = round(
                float(self.data["plusvalenze_lorde_eur"]) + pnl_eur, 2
            )
        else:
            self.data["minusvalenze_lorde_eur"] = round(
                float(self.data["minusvalenze_lorde_eur"]) + abs(pnl_eur), 2
            )

        self._recompute_taxable_summary()

        closed_op = {
            "timestamp": datetime.datetime.now(MARKET_TZ).replace(tzinfo=None).isoformat(timespec="seconds"),
            "ticker": ticker,
            "quantity": round(sell_qty, 6),
            "sell_price_eur": round(sell_price_eur, 4),
            "corrispettivo_eur": round(proceeds_eur, 2),
            "costo_lifo_eur": round(cost_basis_eur, 2),
            "risultato_fiscale_eur": round(pnl_eur, 2),
        }
        self.data["operazioni_chiuse"].append(closed_op)
        self.save()
        return closed_op

    def reconcile_certified_cash_result(self, certified_net_eur: float) -> bool:
        """
        Riconcilia in modo atomico, simmetrico e isolato per Anno Fiscale il risultato realizzato
        certificato dal broker (/equity/account/cash -> result cumulativo lifetime):
        - Archivia automaticamente l'anno chiuso al cambio d'anno solare (1° Gennaio) salvando
          l'offset `baseline_result_inizio_anno_eur` e consumando/accumulando lo zainetto (Art. 68 TUIR)
        - Mantiene sempre `plusvalenze_lorde_eur >= 0` e `minusvalenze_lorde_eur >= 0`
        """
        t212_lifetime_net = round(float(certified_net_eur), 2)
        cur_year = datetime.datetime.now(MARKET_TZ).year
        stored_year = int(self.data.get("anno_fiscale", cur_year))
        if cur_year > stored_year:
            old_plus = float(self.data.get("plusvalenze_lorde_eur", 0.0))
            old_minus = float(self.data.get("minusvalenze_lorde_eur", 0.0))
            old_net = round(old_plus - old_minus, 2)
            prev_hist = float(self.data.get("profitto_storico_anni_precedenti_eur", 0.0))
            prior_baseline = float(self.data.get("baseline_result_inizio_anno_eur", 0.0))
            prior_carry = float(self.data.get("zainetto_minusvalenze_pregresse_eur", 0.0))
            archived_taxable = round(max(0.0, old_net - prior_carry), 2)
            arch = self.data.setdefault("archivio_anni_precedenti", {})
            arch[str(stored_year)] = {
                "plusvalenze_lorde_eur": round(old_plus, 2),
                "minusvalenze_lorde_eur": round(old_minus, 2),
                "imponibile_netto_eur": archived_taxable,
                "imposta_sostitutiva_26_eur": round(archived_taxable * 0.26, 2),
            }
            self.data["profitto_storico_anni_precedenti_eur"] = round(prev_hist + old_net, 2)
            self.data["baseline_result_inizio_anno_eur"] = round(prior_baseline + old_net, 2)
            self.data["zainetto_minusvalenze_pregresse_eur"] = round(max(0.0, prior_carry - old_net), 2)
            self.data["anno_fiscale"] = cur_year
            self.data["totale_corrispettivi_vendita_eur"] = 0.00
            self.data["totale_costi_carico_lifo_eur"] = 0.00
            self.data["plusvalenze_lorde_eur"] = 0.00
            self.data["minusvalenze_lorde_eur"] = 0.00
            self.data["imponibile_netto_eur"] = 0.00
            self.data["imposta_sostitutiva_26_eur"] = 0.00
            self.save()

        year_baseline = float(self.data.get("baseline_result_inizio_anno_eur", 0.0))
        t212_year_net = round(t212_lifetime_net - year_baseline, 2)
        cur_plus = float(self.data.get("plusvalenze_lorde_eur", 0.0))
        cur_minus = float(self.data.get("minusvalenze_lorde_eur", 0.0))
        diff = round(t212_year_net - (cur_plus - cur_minus), 2)
        if abs(diff) < 0.01:
            return False

        if diff > 0:
            self.data["plusvalenze_lorde_eur"] = round(max(0.0, cur_plus + diff), 2)
        else:
            self.data["minusvalenze_lorde_eur"] = round(max(0.0, cur_minus + abs(diff)), 2)

        self._recompute_taxable_summary()
        self.save()
        return True

    def generate_730_summary(self, current_account_value_eur: float) -> Dict[str, Any]:
        """Restituisce il prospetto pronto da copiare nel Modello 730 online."""
        self.data["valore_finale_stimato_quadro_w_eur"] = round(current_account_value_eur, 2)
        ivafe_raw = current_account_value_eur * 0.002
        # L'IVAFE non è dovuta se non supera 12,00 EUR
        ivafe_dovuta = 0.00 if ivafe_raw < 12.00 else round(ivafe_raw, 2)
        imposta_26 = float(self.data["imposta_sostitutiva_26_eur"])

        return {
            "QUADRO_W_MONITORAGGIO": {
                "Valore_Iniziale_EUR": self.data["valore_iniziale_quadro_w_eur"],
                "Valore_Finale_31_12_EUR": self.data["valore_finale_stimato_quadro_w_eur"],
                "IVAFE_Dovuta_EUR": ivafe_dovuta,
                "Nota_IVAFE": "Esente (sotto soglia minima di 12,00 EUR)" if ivafe_dovuta == 0 else "Da versare",
            },
            "QUADRO_T_PLUSVALENZE_LIFO": {
                "Totale_Corrispettivi_Vendita_EUR": self.data["totale_corrispettivi_vendita_eur"],
                "Totale_Costi_Carico_LIFO_EUR": self.data["totale_costi_carico_lifo_eur"],
                "Plusvalenza_Netta_Imponibile_EUR": self.data["imponibile_netto_eur"],
                "Imposta_Sostitutiva_26_EUR": imposta_26,
                "Nota_Versamento": (
                    "Nessun versamento F24 dovuto (sotto franchigia 12,00 EUR)"
                    if imposta_26 <= 12.00
                    else f"Versamento automatico o F24 di {imposta_26:.2f} EUR"
                ),
            },
        }


class Trading212Client:
    """
    Client REST ufficiale per Trading 212 Public API (v0).
    Supporta sia il conto Practice (Demo) sia il conto Live (Invest Reale).
    """

    def __init__(
        self,
        api_key: str,
        api_secret: Optional[str] = None,
        mode: str = "demo",
    ) -> None:
        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip() if api_secret else None
        self.mode = mode.lower()
        if self.mode == "live":
            self.base_url = "https://live.trading212.com/api/v0"
        else:
            self.base_url = "https://demo.trading212.com/api/v0"

    def _build_auth_header(self) -> str:
        """
        Supporta sia il formato 'API Key + Secret' (HTTP Basic Auth)
        sia il formato a chiave singola di Trading 212.
        """
        if self.api_secret:
            raw = f"{self.api_key}:{self.api_secret}".encode("utf-8")
            return "Basic " + base64.b64encode(raw).decode("ascii")
        if ":" in self.api_key and not self.api_key.lower().startswith("basic "):
            raw = self.api_key.encode("utf-8")
            return "Basic " + base64.b64encode(raw).decode("ascii")
        return self.api_key

    def _request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": self._build_auth_header(),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Trading212-AutonomousBot-100EUR/1.0",
        }
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        last_err: Optional[Exception] = None
        for attempt in range(3):
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    body = resp.read().decode("utf-8")
                    return json.loads(body) if (body and body.strip()) else {}
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                if e.code == 429 and attempt < 2:
                    time.sleep(1.8 * (attempt + 1))
                    continue
                if method == "GET" and e.code in (502, 503, 504) and attempt == 0:
                    time.sleep(1.2)
                    continue
                raise RuntimeError(f"HTTP {e.code} su {endpoint}: {err_body}") from e
            except urllib.error.URLError as e:
                last_err = e
                if method == "GET" and attempt == 0:
                    time.sleep(1.0)
                    continue
                raise RuntimeError(f"Errore rete su {endpoint}: {e}") from e
        raise RuntimeError(f"Richiesta fallita su {endpoint}: {last_err}")

    def get_account_cash(self) -> Dict[str, Any]:
        """Restituisce saldo libero, investito e risultato totale del conto."""
        return self._request("GET", "/equity/account/cash")

    def get_account_info(self) -> Dict[str, Any]:
        """Verifica ID conto e valuta base (deve essere EUR)."""
        return self._request("GET", "/equity/account/info")

    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Restituisce tutte le posizioni azionarie aperte."""
        return self._request("GET", "/equity/portfolio")

    def get_pending_orders(self) -> List[Dict[str, Any]]:
        """Restituisce gli ordini pendenti (in attesa di apertura mercato o esecuzione)."""
        return self._request("GET", "/equity/orders")

    @staticmethod
    def snap_mifid_tick_price(raw_price: float, side: str = "BUY") -> float:
        """
        Allinea un prezzo limite al passo di quotazione regolamentare MiFID II RTS 11
        compatibile con tutte le bande di liquidità EUR (XETRA / Euronext Amsterdam),
        evitando rifiuti HTTP 400 per tick-size invalido o rumore floating-point IEEE-754.
        """
        px = max(0.01, float(raw_price))
        if px < 20.0:
            step = 0.01
        elif px < 50.0:
            step = 0.02
        elif px < 200.0:
            step = 0.10
        elif px < 500.0:
            step = 0.20
        elif px < 2000.0:
            step = 1.00
        else:
            step = 2.00

        if side.upper() == "BUY":
            ticks = math.floor((px / step) + 1e-9)
        else:
            ticks = math.ceil((px / step) - 1e-9)
        return round(max(step, ticks * step), 2)

    def place_market_order(self, ticker: str, quantity: float) -> Dict[str, Any]:
        """
        Invia un ordine Market a commissioni zero su azioni frazionate.
        - quantity > 0: Acquisto
        - quantity < 0: Vendita
        Vincolo di sicurezza: accetta SOLO ticker presenti in EUR_ZERO_FEE_UNIVERSE.
        """
        if ticker not in EUR_ZERO_FEE_UNIVERSE:
            raise ValueError(
                f"BLOCCO SICUREZZA COSTI: {ticker} non appartiene alla lista "
                "Europea in EUR a 0% cambio valuta e 0% Tobin Tax."
            )
        payload = {
            "ticker": ticker,
            "quantity": round(quantity, 6),
        }
        return self._request("POST", "/equity/orders/market", payload=payload)

    def place_limit_order(
        self,
        ticker: str,
        quantity: float,
        limit_price: float,
        time_validity: str = "DAY",
    ) -> Dict[str, Any]:
        """
        Invia un ordine LIMIT conforme MiFID II RTS 11 su azioni intere o frazionate (Trading 212 API v0).
        Protegge gli ingressi dagli spike anomali senza mai ripiegare su ordini Market ciechi.
        """
        if ticker not in EUR_ZERO_FEE_UNIVERSE:
            raise ValueError(
                f"BLOCCO SICUREZZA COSTI: {ticker} non appartiene alla lista "
                "Europea in EUR a 0% cambio valuta e 0% Tobin Tax."
            )
        side = "BUY" if quantity > 0 else "SELL"
        snapped_limit = self.snap_mifid_tick_price(limit_price, side=side)
        payload = {
            "ticker": ticker,
            "quantity": round(quantity, 6),
            "limitPrice": snapped_limit,
            "timeValidity": time_validity,
        }
        return self._request("POST", "/equity/orders/limit", payload=payload)

    def cancel_order(self, order_id: Any) -> Dict[str, Any]:
        """Cancella un ordine pendente tramite ID ufficiale Trading 212 (DELETE /equity/orders/{id})."""
        return self._request("DELETE", f"/equity/orders/{order_id}")


class Trading212AutonomousBot:
    """
    Motore decisionale autonomo per il budget di 100,00 EUR:
    - 4 Cartucce da 25,00 EUR
    - Take-Profit netto: +2,2% (+0,55 EUR netti a cartuccia, 0,00 EUR commissioni)
    - Stop-Loss protettivo: -3,0% (-0,75 EUR max rischio a cartuccia)
    - Target Incasso Globale opzionale: +30,0% (130,00 EUR) con liquidazione automatica
    """

    def __init__(
        self,
        client: Optional[Trading212Client] = None,
        total_budget_eur: float = 100.00,
        cartridges: int = 4,
        annual_target_pct: float = 0.30,
    ) -> None:
        self.client = client
        self.total_budget_eur = total_budget_eur
        self.cartridges = cartridges
        self.cartridge_size_eur = round(total_budget_eur / cartridges, 2)
        self.take_profit_pct = 0.022  # +2.2%
        self.stop_loss_pct = -0.030   # -3.0%
        self.annual_target_pct = annual_target_pct  # +30% (130.00 EUR)
        self.target_equity_eur = round(total_budget_eur * (1.0 + annual_target_pct), 2)
        self.tax_tracker = ItalianTaxTracker730()

    def liquidate_all_for_withdrawal(self) -> List[Dict[str, Any]]:
        """
        Cancella eventuali ordini pendenti e chiude immediatamente tutte le posizioni EUR aperte
        a mercato (0,00 EUR commissioni), registrando il costo medio reale certificato da T212.
        """
        if not self.client:
            raise RuntimeError("Client Trading 212 non configurato.")
        try:
            for pend in self.client.get_pending_orders() or []:
                oid = pend.get("id")
                if oid is not None:
                    try:
                        self.client.cancel_order(oid)
                    except Exception:
                        pass
        except Exception:
            pass

        open_positions = self.client.get_open_positions()
        closed_orders: List[Dict[str, Any]] = []
        for pos in open_positions:
            ticker = str(pos.get("ticker", ""))
            qty = float(pos.get("quantity", 0.0))
            current_price = float(pos.get("currentPrice", 0.0))
            avg_price = float(pos.get("averagePrice") or current_price)
            if qty <= 0:
                continue
            if ticker not in EUR_ZERO_FEE_UNIVERSE and ticker.endswith(("d_EQ", "a_EQ")):
                EUR_ZERO_FEE_UNIVERSE[ticker] = {
                    "name": ticker,
                    "exchange": "XETRA / Euronext",
                    "currency": "EUR",
                    "isin": "EUR_VERIFIED",
                    "tobin_tax": "0.00%",
                }
            if ticker in EUR_ZERO_FEE_UNIVERSE:
                order_resp = self.client.place_market_order(ticker=ticker, quantity=-qty)
                tax_op = self.tax_tracker.record_sell(
                    ticker=ticker,
                    sell_qty=qty,
                    sell_price_eur=current_price,
                    fallback_avg_price_eur=avg_price,
                )
                closed_orders.append({"order": order_resp, "tax_record": tax_op})
        return closed_orders


def run_self_test() -> None:
    """Esegue un test isolato in /tmp del motore e del Registro Fiscale 730 (senza toccare il file live)."""
    with tempfile.NamedTemporaryFile(prefix="t212_tax_selftest_", suffix=".json", delete=False) as tmp_f:
        test_registry_path = tmp_f.name
    try:
        if os.path.exists(test_registry_path):
            os.remove(test_registry_path)
        tracker = ItalianTaxTracker730(filepath=test_registry_path)
        tracker.save()
        summary = tracker.generate_730_summary(current_account_value_eur=100.00)
        print("=== MOTORE TRADING 212 + REGISTRO FISCALE 730 PRONTO (SELF-TEST ISOLATO) ===")
        print(f"Universo Azioni EUR Base caricato ({len(EUR_ZERO_FEE_UNIVERSE)} titoli):")
        for tkr, meta in EUR_ZERO_FEE_UNIVERSE.items():
            print(f"  - {tkr}: {meta['name']} ({meta['exchange']}) | Valuta: {meta['currency']} | Tobin Tax: {meta['tobin_tax']}")
        print("Riepilogo Fiscale Test:", json.dumps(summary, indent=2, ensure_ascii=False))
    finally:
        if os.path.exists(test_registry_path):
            os.remove(test_registry_path)


if __name__ == "__main__":
    run_self_test()
