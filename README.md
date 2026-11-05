# 🛡️ Trading 212 Autonomous Quant Bot — V6.5 Institutional Zero-Latency

Motore quantitativo autonomo per **Trading 212 Invest (EUR)** progettato per operare **H24 in Cloud tramite GitHub Actions** (anche a computer spento) o in locale su macOS, con budget isolato di **100,00 €** suddiviso in **4 Cartucce dinamiche da ~25,00 € (Schema 2+2 Senza Tetto)** e **Registro Fiscale Italiano Modello 730 (LIFO)** integrato.

---

## 🏛️ Architettura V6.5 — Le 12 Blindature Istituzionali

1. **Pre-Scudo Salva-Utile (Break-Even Lock):** Da `+0,60%` blocca un pavimento minimo garantito a `+0,25%` (`+0,42%` → `+0,20%` con Cassaforte Giornaliera attiva).
2. **Filtro Uncino Verde (`green_hook`):** Vietato comprare su candele a 5m rosse in caduta libera; richiede candela verde di rimbalzo o minimo crescente.
3. **Raccolto Gap Mattutino (09:00–09:30 CET):** Stringe il ritracciamento a `0,14%` sui gap di apertura `>= +0,50%` prima del Gap-Fill.
4. **Radar Onda Notturna (17:15–17:30 CET):** Incrocia Wall Street live (`^IXIC` Nasdaq, `^GSPC` S&P 500, `^VIX` Volatility, `^GDAXI` DAX) per mantenere nella notte i titoli forti sopra VWAP e liquidare i **Falsi Positivi** (`CRESTA_IN_INVERSIONE_FALSO_POSITIVO`: `RSI > 66` + candela rossa + volumi `< 0,85x`).
5. **Scudo Weekend del Venerdì (17:15–17:30 CET):** Protegge il capitale dalle 63 ore di mercati chiusi del fine settimana.
6. **Interesse Composto di Kelly:** Reinveste automaticamente gli utili netti realizzati in cassa (`100,00 € + utili_netti`) ricalibrando la taglia delle 4 cartucce.
7. **Vincolo Settoriale di Markowitz:** Impone 4 cartucce su 4 settori industriali distinti (vieta la doppia esposizione simultanea sui semiconduttori `ASMLa_EQ` + `IFXd_EQ`).
8. **Scudo Elastico ATR a 5 Minuti:** Adatta soglia di attivazione e ritracciamento (`0,80x – 1,30x`) alla volatilità reale a 5m.
9. **Sblocco Titolo Immobile (>4h sotto VWAP) + Zainetto Fiscale 730:** Ruota i titoli stagnanti in lieve calo quando appare un'occasione estrema (`Score >= 65` con Uncino Verde), generando una minusvalenza compensabile al 100% nel Quadro T.
10. **Cassaforte Giornaliera High-Water Mark (`>= +1,80 €`):** Quando gli utili realizzati superano `+1,80 €`, attiva la modalità difesa capitale.
11. **Fusione Prezzo Zero-Latency (0ms):** Inietta il prezzo reale a 0 millisecondi dell'API Trading 212 sulle candele a 5 minuti di Yahoo Finance, azzerando i 15 minuti di ritardo XETRA.
12. **Scudo Anti-Shock Dati Macro USA (14:28–14:35 CET):** Sospende i nuovi acquisti nei 7 minuti di rilascio dei dati macro USA (CPI/NFP) lasciando attivi tutti gli scudi di vendita.

---

## ☁️ Operatività H24 a Computer Spento (GitHub Actions Cloud)

Il workflow [`.github/workflows/t212_cloud_h24.yml`](.github/workflows/t212_cloud_h24.yml) esegue automaticamente il bot sui server cloud di GitHub durante l'intero orario di negoziazione europeo (Lun–Ven, fuso orario `Europe/Rome`) e aggiorna dopo ogni sessione:
- [`trading212_state.json`](trading212_state.json) — Stato live del portafoglio e delle 4 cartucce
- [`registro_fiscale_730.json`](registro_fiscale_730.json) — Registro fiscale LIFO (Quadro W & Quadro T)
- [`dashboard_v6_5.html`](dashboard_v6_5.html) — Dashboard visuale del portafoglio

Le credenziali API sono protette tramite **GitHub Encrypted Secrets** (`T212_API_KEY`, `T212_API_SECRET`, `T212_MODE`) e non vengono mai salvate nel codice sorgente.

---

## 🛠️ Comandi Rapidi CLI (`t212-cli.py`)

```bash
# Stato in tempo reale di portafoglio, 4 cartucce, scanner 5m 0ms e Radar Notturno
python3 t212-cli.py status

# Prospetto Fiscale Modello 730 (Quadro W, Quadro T LIFO e storico vendite)
python3 t212-cli.py tax-730

# Rigenera la Dashboard HTML interattiva
python3 t212-cli.py dashboard

# Avvia / Ferma il demone locale in background
python3 t212-cli.py start
python3 t212-cli.py stop
```
