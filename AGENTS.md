# AGENTS.md — Trading 212 Autonomous Quant Bot (V11.5 LTS "Zero Cerotti")

> **Progetto:** Trading 212 Autonomous Quant Bot — V11.5 LTS Institutional Zero-Latency (30 Invarianti Bloccanti Cross-Model Converged)
> **Broker & Conto:** Trading 212 (`Account ID: 52318994` | Valuta: `EUR` | Modalità: `demo` / `live`)
> **Budget Isolato:** `100,00 €` base (`4 Cartucce × 25,00 €` + Interesse Composto di Kelly sui profitti netti realizzati)
> **Universo Attivo:** `39 Colossi EUR Zero-Fee` (`32 Campioni DAX40/AEX25` + `7 Big Tech USA quotate in EUR su XETRA`, `0,00%` FX, `0,00%` Tobin Tax, Streaming `0s GETTEX` + Esecuzione `0ms T212`)
> **Target Cash-Out:** `130,00 €` (`+30,00%` netto — liquidazione totale automatica del portafoglio e blocco permanente anti-churn)
> **Root Progetto Standalone:** `/Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e`

Questo file fornisce la **memoria architetturale permanente** per **Antigravity IDE** e **Antigravity CLI (`agy`)**. Consulta [`CONSTRAINTS.md`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/CONSTRAINTS.md) per il contratto formale dei **30 Invarianti Matematici Bloccanti** verificati ad ogni deploy tramite `python3 -m unittest discover -s tests -p "test_*.py" -v`.

---

## 1. Comandi Rapidi CLI (`t212-cli.py`)

Il progetto è gestito tramite lo strumento CLI [`t212-cli.py`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/t212-cli.py) situato nella root del progetto:

- **Controlla lo stato in tempo reale del portafoglio (`100 €`), delle 4 cartucce, dello scanner `5m` Zero-Latency, del Radar Onda Notturna e del demone:**
  ```bash
  python3 t212-cli.py status
  ```
- **Visualizza il Registro Fiscale Italiano Modello 730 (Quadro W, Quadro T LIFO, Zainetto Fiscale e storico eseguiti):**
  ```bash
  python3 t212-cli.py tax-730
  ```
- **Genera e aggiorna la Dashboard HTML interattiva (`dashboard_v6_5.html`) con i dati live del portafoglio:**
  ```bash
  python3 t212-cli.py dashboard
  ```
- **Avvia o riavvia il demone autonomo `t212_daemon_100e.py` in background:**
  ```bash
  python3 t212-cli.py start
  ```
- **Ferma in sicurezza il demone in background (senza chiudere le posizioni sul mercato):**
  ```bash
  python3 t212-cli.py stop
  ```
- **Esporta il pacchetto ZIP di backup completo (`dist/trading212-quant-backup.zip` senza segreti):**
  ```bash
  python3 t212-cli.py export
  ```

---

## 2. Architettura dei File del Progetto (`V11.5 LTS Zero Cerotti`)

- **Motore & Demone Quantitativo:**
  - [`t212_daemon_100e.py`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/t212_daemon_100e.py): Demone autonomo principale **V11.5 LTS Zero Cerotti** (ciclo continuo Split-Speed ogni `~6 secondi`). Implementa:
    - [`OvernightWaveRadar`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/t212_daemon_100e.py#L703): Radar predittivo delle `17:15–17:30 Europe/Rome` che incrocia Wall Street live (`^IXIC` Nasdaq, `^GSPC` S&P 500, `^VIX` Volatility, `^GDAXI` DAX) con verifica effettiva di apertura odierna USA (`us_indices_live_today` su `America/New_York`, immune a festività USA e cambi d'ora DST).
    - [`QuantMarketScanner`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/t212_daemon_100e.py#L860): Scanner quantitativo a `5 minuti` con **Streaming Batch `0s` da `GETTEX` (Monaco)** su tutti i 39 Colossi, **Fusione `0ms` T212** sulle posizioni aperte, guardia persistente sulle candele congelate al cambio barra `:00`, peso VWAP proporzionale al tempo, `Signed Kaufman ER` e `RVOL` istituzionale XETRA depurato dalle aste `13:00` e `17:25`.
    - [`HybridUncappedIntelligence`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/t212_daemon_100e.py#L1722): Curva monotona Lipschitz-continua bilaterale $C^0$ (`compute_profit_protection_floor`) condivisa 1:1 tra motore e JSON, Taper VWAP scale-invariant su ATR (`1,30 × ATR`), predicato unico d'ingresso `is_eligible_entry_candidate` e predicato unico anti-crollo `is_macro_crash_shield_active`.
    - [`run_cycle`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/t212_daemon_100e.py#L2394): Esecuzione ingressi esclusivamente tramite **Marketable Limit Orders MiFID II RTS 11 (`+1,00%` cap anti-spike)** con Eventual-Consistency Fill Re-Check, allocazione frazionaria a 4 decimali con Interesse Composto di Kelly, Vincolo di Markowitz su 4 settori distinti e persistenza JSON atomica POSIX.
  - [`trading212_bot.py`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/trading212_bot.py): Libreria core contenente:
    - [`Trading212Client`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/trading212_bot.py#L416): Client REST API v0 (`demo` / `live`) con `snap_mifid_tick_price`, `place_limit_order`, `place_market_order` e gestione rate-limit.
    - [`ItalianTaxTracker730`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/trading212_bot.py#L188): Motore fiscale italiano conforme a **Modello 730 / Redditi PF** (Art. 67-68 TUIR) con contabilità **LIFO multi-tranche**, isolamento per singolo `anno_fiscale` (`baseline_result_inizio_anno_eur`), assorbimento pluriennale dello `zainetto_minusvalenze_pregresse_eur`, **Quadro W (IVAFE `0,20%`)** e **Quadro T (`26%`)**.
    - [`atomic_write_json`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/trading212_bot.py#L44): Scrittura atomica POSIX (`tempfile` + `os.replace`) condivisa su tutti i file JSON di stato, fiscalità e cache.
  - [`.github/workflows/t212_cloud_h24.yml`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/.github/workflows/t212_cloud_h24.yml): Pipeline Cloud GitHub Actions H24 con staffetta automatica delle `12:25 Europe/Rome`, trasferimento cache candele `5m` + radar via `actions/cache@v4` e gate bloccante sui `30` invarianti matematici.
- **Stato Live, Credenziali & Fiscalità (NON SOVRASCRIVERE MANUALMENTE):**
  - [`trading212_state.json`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/trading212_state.json): Stato JSON aggiornato ogni `~6 secondi` dal demone.
  - [`registro_fiscale_730.json`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/registro_fiscale_730.json): Registro fiscale persistente LIFO 730.
  - [`t212_credentials.json`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/t212_credentials.json): Credenziali API locali (escluse da Git e dagli export ZIP).

---

## 3. Regole Operative Inviolabili ("Legge Zero Cerotti")

1. **Zero Cerotti:** Vietato aggiungere toppe condizionali ad-hoc per singoli ticker o orari arbitrari; ogni regola deve essere una legge continua, monotona e scale-invariant sulla volatilità (`ATR 5m`), sul `VWAP` o sul volume relativo (`RVOL`), validata da walk-forward empirico e bloccata in [`tests/test_quant_invariants.py`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/tests/test_quant_invariants.py).
2. **Integrità Dati Live:** Non modificare mai manualmente le posizioni aperte o lo storico eseguiti in `trading212_state.json` e `registro_fiscale_730.json`.
3. **Verifica Obbligatoria Pre-Push:** Prima di ogni commit/push su `origin/main`, eseguire sempre `python3 -m unittest discover -s tests -p "test_*.py" -v` (`30 / 30 OK`).
