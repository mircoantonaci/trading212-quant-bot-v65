# Architettura Quantitativa V6.5 — Institutional Zero-Latency (12 Blindature)

> **Progetto:** Trading 212 Autonomous Quant Bot (`100,00 €` Isolati — `4 Cartucce 2+2`)
> **Conversazione di Origine:** `6aa33967-d540-4201-8b0a-2fd9ff9458b8`
> **Motore Attivo:** [`t212_daemon_100e.py`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/t212_daemon_100e.py) + [`trading212_bot.py`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/trading212_bot.py)

---

## 1. Filosofia Operativa: "Nessun Tetto al Guadagno, Pavimento Blindato"

Il sistema è progettato per operare su un budget rigorosamente isolato di **100,00 €** suddiviso in **4 cartucce dinamiche da ~25,00 €** (con auto-compounding di Kelly), eliminando i due errori strutturali tipici del trading retail su piccoli capitali:

1. **Zero Erosione da Commissioni e Cambio Valuta:** Operando esclusivamente su azioni singole europee quotate in **EUR** su **XETRA** (Francoforte) ed **Euronext Amsterdam**, ogni operazione ha **0,00 € di commissioni di negoziazione**, **0,00% di commissione di conversione valutaria (FX Fee 0,15% azzerata)** e **0,00% di Tobin Tax**.
2. **Scudo Armonico Senza Tetto (Dynamic Trailing Floor):** Il bot non vende mai a un "Take Profit fisso" mentre il titolo sta ancora salendo con forza. Quando il profitto supera la soglia di attivazione (o già da `+0,60%` con il Pre-Scudo Salva-Utile), il bot alza progressivamente un pavimento minimo garantito sotto il prezzo massimo toccato (`peak_pct - effective_pullback_pct`). Finché il titolo sale, lo scudo sale con lui; la vendita scatta solo quando l'onda inverte dal proprio picco.

---

## 2. Architettura a 4 Cartucce (Schema 2+2) e Vincolo di Markowitz

Il capitale operativo (`100,00 € + profitti_netti_incassati`) è ripartito in **4 slot indipendenti**:

- **2 Cartucce — Squadra 1 (`SQUADRA_1_CECCHINO_GIORNALIERO`):**
  - Titoli ad altissima liquidità e oscillazione regolare: **Deutsche Telekom (`DTEd_EQ`)**, **Allianz (`ALVd_EQ`)**, **Siemens (`SIEd_EQ`)**.
  - Soglie Scudo Base più ravvicinate (`+0,55%` / `+0,65%` / `+0,85%`) con ritracciamento stretto (`0,13%` – `0,16%`) per incassare con continuità i cicli intraday.
- **2 Cartucce — Squadra 2 (`SQUADRA_2_CAVALCA_ONDA`):**
  - Titoli tecnologici e semiconduttori ad alto beta: **SAP (`SAPd_EQ`)**, **Infineon (`IFXd_EQ`)**, **ASML (`ASMLa_EQ`)**.
  - Soglie Scudo Base più ampie (`+1,25%` – `+1,45%`) con ritracciamento elastico (`0,24%` – `0,28%`) per cavalcare i rally direzionali senza uscire prematuramente.

### Vincolo Settoriale di Markowitz
Ogni titolo è associato a uno specifico settore industriale (`TELECOMUNICAZIONI`, `ASSICURAZIONI_FINANZA`, `INDUSTRIA_INFRASTRUTTURE`, `SOFTWARE_CLOUD`, `SEMICONDUTTORI_CHIP`). Il bot non apre mai una nuova cartuccia in un settore già presente in portafoglio: in particolare, **`ASMLa_EQ` e `IFXd_EQ` non possono mai essere detenuti contemporaneamente**, dimezzando il rischio sistemico di comparto.

---

## 3. Fusione Zero-Latency (0ms) e Scanner Sinusoidale a 5 Minuti

Le borse europee (XETRA / Euronext) presentano normalmente un ritardo di **15 minuti** sui flussi gratuiti Yahoo Finance (`5m`). La **Blindatura #11 (Zero-Latency Price Fusion)** risolve questo problema alla radice:

1. Ad ogni ciclo di 30 secondi, il bot interroga l'API ufficiale di Trading 212 ottenendo il prezzo di esecuzione reale a **0 millisecondi (`t212_live_price`)**.
2. Se l'ultima candela Yahoo Finance a 5 minuti è in ritardo di oltre 60 secondi, il motore fonde istantaneamente `t212_live_price` come nuova candela live in coda alla serie storica prima di calcolare tutti gli indicatori matematici:
   - **RSI di Wilder a 14 periodi (5m)**
   - **Bande di Bollinger a 20 periodi (`±2σ`)** e posizione percentuale `bb_pos`
   - **VWAP Istituzionale Intraday** (prezzo medio ponderato per i volumi della seduta)
   - **ATR Dinamico a 14 periodi (5m)** e moltiplicatore elastico `0,80x – 1,30x`
   - **Filtro Uncino Verde (`green_hook`):** verifica che la candela corrente sia verde (`close > open`) oppure segni un minimo crescente con rimbalzo di almeno `+0,05%` dal minimo della candela precedente.

---

## 4. Radar Onda Notturna (`OvernightWaveRadar`) — 17:15–17:30 CET

Tra le **17:15 e le 17:30 CET** (ultimi 15 minuti prima della chiusura di XETRA ed Euronext), il bot attiva il **Radar Onda Notturna** che calcola un punteggio composito (`Overnight Score 0–100`) combinando:

1. **Macro Impulso USA in Tempo Reale (`us_impulse`):** Media pesata di **Nasdaq Composite (`^IXIC`, peso 55%)** e **S&P 500 (`^GSPC`, peso 45%)**, corretta per la variazione dell'indice della paura **VIX (`^VIX`)** e del **DAX (`^GDAXI`)**.
2. **Struttura Tecnica del Titolo:** Posizione rispetto al VWAP giornaliero, posizione nel range High-Low di seduta, pendenza del momentum a 30 minuti e fase sinusoidale a 5m.
3. **Rilevatore di Falso Positivo (`CRESTA_IN_INVERSIONE_FALSO_POSITIVO`):** Scatta solo in presenza di **tripla conferma simultanea**:
   - `RSI (5m) > 66` (eccesso di ipercomprato)
   - Candela a 5 minuti rossa (`candle_body < 0`)
   - Volumi in prosciugamento (`vol_ratio < 0,85x`) o momentum a 30m negativo (`mom_6_bars < -0,10%`).
   In caso di Falso Positivo accertato, il bot vende immediatamente tra le 17:15 e le 17:30 per incassare alla cresta ed evitare il gap ribassista del mattino seguente.

---

## 5. Registro Fiscale Italiano Modello 730 (LIFO — Quadro W & Quadro T)

Il modulo [`ItalianTaxTracker730`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/trading212_bot.py) registra automaticamente ogni acquisto e vendita in [`registro_fiscale_730.json`](file:///Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e/registro_fiscale_730.json) secondo la normativa fiscale italiana per conti esteri in regime dichiarativo (Trading 212):

- **Metodo Contabile LIFO (Last-In, First-Out):** Art. 67 comma 1-bis TUIR. Ad ogni vendita, lo scarico avviene partendo dall'ultimo lotto acquistato per quello specifico ISIN/Ticker.
- **Compensazione Totale Plusvalenze / Minusvalenze (Art. 68 TUIR):** Essendo tutte azioni singole (e non ETF OICR), ogni eventuale minusvalenza realizzata (ad esempio tramite la **Blindatura #9 — Rotazione Fiscale**) abbatte al 100% le plusvalenze realizzate nello stesso anno d'imposta e nei 4 anni successivi.
- **Quadro W (Monitoraggio Fiscale & IVAFE 0,20%):** Con un capitale di `100,00 €`, l'IVAFE annua (`0,20%`) è pari a `0,20 €`, **sotto la soglia minima di versamento di `12,00 €`**, risultando quindi **0,00 € da versare**.
- **Quadro T (Imposta Sostitutiva Capital Gain 26%):** Calcolata esclusivamente sull'utile netto eccedente le minusvalenze pregresse; anche qui l'imposta non è dovuta finché resta sotto la soglia minima di `12,00 €` (`~46,15 €` di plusvalenza netta annua).
