# AGENTS.md — Trading 212 Autonomous Quant Bot (V11.5 LTS "Zero Cerotti")

> **Progetto:** Trading 212 Autonomous Quant Bot — V11.5 LTS Institutional Zero-Latency (28 Invarianti Bloccanti)
> **Broker & Conto:** Trading 212 (`Account ID: 52318994` | Valuta: `EUR` | Modalità: `demo` / `live`)
> **Budget Isolato:** `100,00 €` base (`4 Cartucce × 25,00 €` + Interesse Composto di Kelly sui profitti netti realizzati)
> **Universo Attivo:** `39 Colossi EUR Zero-Fee` (`32 Campioni DAX40/AEX25` + `7 Big Tech USA quotate in EUR su XETRA`, `0,00%` FX, `0,00%` Tobin Tax, Streaming `0s GETTEX` + Esecuzione `0ms T212`)
> **Target Cash-Out:** `130,00 €` (`+30,00%` netto — liquidazione totale automatica del portafoglio e blocco permanente anti-churn)
> **Root Progetto Standalone:** `/Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e`

Questo file fornisce la **memoria architetturale permanente** per **Antigravity IDE** e **Antigravity CLI (`agy`)**. Consulta [`CONSTRAINTS.md`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/CONSTRAINTS.md) per il contratto formale dei **28 Invarianti Matematici Bloccanti** verificati ad ogni deploy tramite `python3 -m unittest discover -s tests -p "test_*.py" -v`.

---

## 1. Comandi Rapidi CLI (`t212-cli.py`)

Il progetto è gestito tramite lo strumento CLI [`t212-cli.py`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/t212-cli.py) situato nella root del progetto:

- **Controlla lo stato in tempo reale del portafoglio (100 €), delle 4 cartucce, dello scanner 5m Zero-Latency, del Radar Onda Notturna e del demone:**
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
- **Esporta il pacchetto ZIP di backup completo (`dist/trading212-quant-v6.5-backup.zip`) ed esegue snapshot Git:**
  ```bash
  python3 t212-cli.py export
  ```

---

## 2. Architettura dei File del Progetto

- **Motore & Demone Quantitativo:**
  - [`t212_daemon_100e.py`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/t212_daemon_100e.py): Demone autonomo principale **V6.5 Institutional Zero-Latency** (ciclo continuo ogni 30 secondi). Implementa:
    - `OvernightWaveRadar`: Radar predittivo delle 17:15–17:30 CET che incrocia Wall Street live (`^IXIC` Nasdaq, `^GSPC` S&P500, `^VIX` Volatility, `^GDAXI` DAX) con la struttura a 5m del titolo per distinguere tra `ONDA_RIALZISTA_VERA_TIENI_NOTTE` e `CRESTA_IN_INVERSIONE_FALSO_POSITIVO`.
    - `scan_intraday_5m_sine_wave`: Scanner armonico a 5 minuti con **Fusione Zero-Latency (0ms)** dei prezzi live di Trading 212 sulle candele storiche Yahoo Finance, filtro **Uncino Verde (Green Hook)**, **ATR dinamico** e calcolo dello **Scudo Armonico Senza Tetto**.
    - `run_cycle`: Gestione completa delle 4 cartucce (2+2), delle **12 Blindature Istituzionali**, del **Vincolo Settoriale di Markowitz** e della **Rotazione Fiscale 730**.
  - [`trading212_bot.py`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/trading212_bot.py): Libreria core contenente:
    - `Trading212Client`: Client REST API v0 (`https://demo.trading212.com/api/v0` / `https://live.trading212.com/api/v0`) con autenticazione HTTP Basic (`API_KEY:API_SECRET`) e fallback per ordini frazionari.
    - `ItalianTaxTracker730`: Motore fiscale italiano conforme a **Modello 730 / Redditi PF** con contabilità **LIFO**, **Quadro W (IVAFE 0,20%)** e **Quadro T (Capital Gain 26% con compensazione minusvalenze)**.
    - `EUR_ZERO_FEE_UNIVERSE`: Universo selezionato di 6 Blue Chip europee in **EUR nativo** (XETRA & Euronext Amsterdam) con **0,00% FX Fee**, **0,00% Tobin Tax** e **100% compensabilità fiscale**.
  - [`t212-cli.py`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/t212-cli.py): Interfaccia a riga di comando per monitoraggio, fiscalità 730, generazione dashboard HTML, controllo demone ed esportazione.
- **Stato Live, Credenziali & Fiscalità (NON SOVRASCRIVERE MANUALMENTE):**
  - [`trading212_state.json`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/trading212_state.json): Stato JSON aggiornato ogni 30 secondi dal demone (valore portafoglio su base 100 €, stato delle 4 cartucce, massimi raggiunti `peaks`, livelli scudo, verdetti radar notturno e log decisionale).
  - [`registro_fiscale_730.json`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/registro_fiscale_730.json): Registro fiscale persistente con lotti LIFO aperti, storico vendite chiuse, plusvalenze/minusvalenze nette e prospetto precompilato per il Commercialista / CAF.
  - [`t212_credentials.json`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/t212_credentials.json): Credenziali API Trading 212 (`api_key`, `api_secret`, `mode`, `account_id: 52318994`, `currency: EUR`).
- **Dashboard & Documentazione:**
  - [`dashboard_v6_5.html`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/dashboard_v6_5.html): Dashboard interattiva standalone del portafoglio V6.5.
  - [`docs/architecture_v6_5.md`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/docs/architecture_v6_5.md): Manuale tecnico completo delle 12 Blindature Istituzionali, della matematica sinusoidale a 5m e delle regole fiscali.
  - [`docs/walkthrough.md`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/docs/walkthrough.md): Cronistoria evolutiva completa (da V1 a V6.5) e guida operativa.

---

## 3. Universo Titoli EUR Zero-Commissioni (`EUR_ZERO_FEE_UNIVERSE`)

Tutti i titoli sono **Azioni Singole Europee in Euro (`EUR`)**, scelte per garantire **0,00 € di commissioni**, **0,00% di tassa sul cambio valuta (FX fee)**, **0,00% di Tobin Tax** (Germania e Paesi Bassi non applicano FTT) e **piena compensabilità fiscale tra minusvalenze e plusvalenze** (a differenza degli ETF):

### Squadra 1 — Cecchino Giornaliero (2 Cartucce, oscillazioni rapide e costanti)
| Ticker T212 | Ticker Yahoo | Nome Azienda | Borsa | ISIN | Settore Markowitz | Scudo Base | Ritracciamento |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: | :---: |
| `DTEd_EQ` | `DTE.DE` | Deutsche Telekom AG | XETRA | `DE0005557508` | `TELECOMUNICAZIONI` | `+0,55%` | `0,13%` |
| `ALVd_EQ` | `ALV.DE` | Allianz SE | XETRA | `DE0008404005` | `ASSICURAZIONI_FINANZA` | `+0,65%` | `0,14%` |
| `SIEd_EQ` | `SIE.DE` | Siemens AG | XETRA | `DE0007236101` | `INDUSTRIA_INFRASTRUTTURE` | `+0,85%` | `0,16%` |

### Squadra 2 — Cavalca-Onda (2 Cartucce, forti escursioni direzionali)
| Ticker T212 | Ticker Yahoo | Nome Azienda | Borsa | ISIN | Settore Markowitz | Scudo Base | Ritracciamento |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: | :---: |
| `SAPd_EQ` | `SAP.DE` | SAP SE | XETRA | `DE0007164600` | `SOFTWARE_CLOUD` | `+1,25%` | `0,24%` |
| `IFXd_EQ` | `IFX.DE` | Infineon Technologies AG | XETRA | `DE0006231004` | `SEMICONDUTTORI_CHIP` | `+1,35%` | `0,25%` |
| `ASMLa_EQ` | `ASML.AS` | ASML Holding NV | Euronext AMS | `NL0010273215` | `SEMICONDUTTORI_CHIP` | `+1,45%` | `0,28%` |

---

## 4. Le 12 Blindature Istituzionali (Architettura V6.5)

1. **Pre-Scudo Salva-Utile (Break-Even Lock):** Appena una cartuccia tocca `>= +0,60%` (`+0,42%` con Cassaforte Giornaliera attiva), il bot blinda un pavimento minimo garantito a **`+0,25%`** (`+0,20%` in modalità Cassaforte), impedendo che un'operazione in guadagno torni in rosso prima dell'attivazione dello Scudo Armonico principale.
2. **Filtro Uncino Verde (Anti-Coltello che Cade):** Vietato comprare su candele rosse consecutive a 5 minuti anche se l'RSI è ipervenduto. L'acquisto scatta solo quando appare una candela verde di rimbalzo (`close > open`) o un minimo crescente con recupero del prezzo (`green_hook == True`).
3. **Raccolto Gap Mattutino (09:00–09:30 Anti-Gap-Fill):** Nei primi 30 minuti di apertura XETRA/Euronext, se una cartuccia apre in gap rialzista `>= +0,50%`, il margine di ritracciamento viene stretto a **`0,14%`** per incassare il picco prima delle prese di beneficio delle 09:15–09:30.
4. **Radar Onda Notturna ed Evacuazione Intelligente (17:15–17:30):** Alle 17:15 CET il `OvernightWaveRadar` analizza Nasdaq (`^IXIC`), S&P 500 (`^GSPC`), VIX (`^VIX`) e la struttura del titolo:
   - Se Wall Street è solida e il titolo è sopra VWAP con impulso sano (`Overnight Score >= 55`), **mantiene la posizione nella notte** per catturare il Gap di apertura delle 09:00.
   - Se rileva una **Cresta in Inversione (Falso Positivo)** con tripla prova (`RSI > 66` + candela rossa d'inversione + volumi in prosciugamento `< 0,85x`), oppure se Wall Street è pesantemente negativa, liquida la posizione prima delle 17:30.
5. **Scudo Weekend del Venerdì (17:15–17:30):** Il venerdì pomeriggio la soglia per restare aperti durante le 63 ore di mercati chiusi sale a `Overnight Score >= 78`, richiedendo profitto `>= +0,35%`, Nasdaq `> +0,50%` e VIX negativo.
6. **Interesse Composto di Kelly (Auto-Compounding):** Ogni profitto netto incassato in cassa viene sommato al capitale operativo (`active_budget_100 = 100,00 € + realized_net_eur`), aumentando automaticamente la taglia delle 4 cartucce (`dynamic_slot_eur = active_budget_100 / 4`).
7. **Vincolo Settoriale di Markowitz (Anti-Correlazione):** Impedisce di avere più di 1 cartuccia nello stesso settore industriale (es. vieta di detenere contemporaneamente `ASMLa_EQ` e `IFXd_EQ`, entrambi nel settore `SEMICONDUTTORI_CHIP`).
8. **Scudo Elastico sulla Volatilità ATR a 5 Minuti:** Adatta dinamicamente la soglia dello scudo e il margine di ritracciamento tramite un moltiplicatore `0,80x – 1,30x` calcolato sull'ATR a 14 periodi a 5m.
9. **Sblocco Titolo Immobile (>4h sotto VWAP) + Zainetto Fiscale 730:** Se tutte le 4 cartucce sono occupate e in panchina appare un'occasione estrema (`Quant Score >= 75` con Uncino Verde), il bot può ruotare un titolo bloccato da oltre 4 ore sotto VWAP in lieve calo (`-1,80% <= PnL < -0,15%`) se gli utili già incassati coprono la perdita, generando una **minusvalenza compensabile al 100% nel Quadro T**.
10. **Cassaforte Giornaliera High-Water Mark (`>= +1,80 €`):** Quando gli utili netti incassati raggiungono `+1,80 €`, il bot entra in modalità **Difesa Capitale**, anticipando i Pre-Scudi a `+0,42%` e stringendo del `15%` i margini di ritracciamento.
11. **Fusione Prezzo Zero-Latency (0ms) su Candele 5m:** Inietta all'istante il prezzo reale a 0 millisecondi dell'API Trading 212 come candela corrente della serie storica a 5 minuti di Yahoo Finance, azzerando il ritardo di 15 minuti di XETRA sul calcolo di RSI, Bande di Bollinger, VWAP e Fase Sinusoidale.
12. **Scudo Anti-Shock Dati Macro USA (14:28–14:35 CET):** Sospende i nuovi acquisti nei 7 minuti a cavallo delle 14:30 CET (rilascio dati macro USA CPI/NFP/disoccupazione) per evitare gli spike algoritmici di caccia agli stop, lasciando invece attivi tutti gli scudi di presa di profitto.
