# Walkthrough & Cronistoria Evolutiva — Trading 212 Quant Bot (V1 → V6.5)

> **Conversazione Recuperata:** `6aa33967-d540-4201-8b0a-2fd9ff9458b8`
> **Root Progetto Standalone:** `/Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e`
> **Stato Attuale:** Motore **V6.5 Institutional Zero-Latency (12 Blindature)** attivo in background su conto Trading 212 (`ID: 52318994`).

---

## 1. Riepilogo del Percorso Evolutivo (Dalla Conversazione Originale)

1. **Analisi e Scelta del Broker (Trading 212 vs eToro):**
   - Inizialmente testata una simulazione a 6 bot (`bot_arena.py`) e un'analisi su eToro (`etoro_bot_100e.py`), scartato per via della conversione forzata EUR/USD, delle commissioni fisse da `1 $ – 2 $` per ticket e della leva CFD.
   - Scelto **Trading 212 Invest** con valuta base **EUR**, collegato tramite API ufficiali v0 (`t212_credentials.json`) sul conto `52318994`.
2. **Isolamento Rigoroso del Budget di 100,00 € e Selezione Titoli EUR:**
   - Liquidati tutti i vecchi titoli USA/UK e l'ordine pendente su `GOOGL` che esponevano il conto alla commissione di cambio valuta (`0,15%` FX Fee).
   - Costruito l'universo **`EUR_ZERO_FEE_UNIVERSE`** composto da 6 Blue Chip europee (`SAPd_EQ`, `ASMLa_EQ`, `SIEd_EQ`, `IFXd_EQ`, `ALVd_EQ`, `DTEd_EQ`) a **0,00 € di commissioni**, **0,00% FX Fee** e **100% compensabilità fiscale 730**.
   - Primi profitti netti reali chiusi e contabilizzati nel registro fiscale: **`+1,38 €` netti** su 8 operazioni chiuse.
3. **Passaggio alle 4 Cartucce (Schema 2+2) e Scudo Armonico Senza Tetto (V5.0):**
   - Suddiviso il capitale di `100,00 €` in **4 cartucce da 25,00 €** (2 per la *Squadra 1 — Cecchino Giornaliero* e 2 per la *Squadra 2 — Cavalca-Onda*).
   - Sostituito il Take Profit fisso con lo **Scudo Armonico Dinamico a Ritracciamento sull'Onda Sinusoidale a 5 minuti**.
4. **Radar Onda Notturna & Distinguo Onda Vera vs Falso Positivo (V5.5):**
   - Introdotto `OvernightWaveRadar` per valutare tra le 17:15 e le 17:30 CET se mantenere i titoli in portafoglio durante la notte (catturando il Gap delle 09:00) oppure incassare prima della chiusura in presenza di una **Cresta in Inversione (Falso Positivo)** con tripla conferma (`RSI > 66` + candela rossa + calo volumi).
5. **Upgrades V6.0, V6.2 e V6.5 Institutional Zero-Latency (12 Blindature):**
   - **V6.0 (5 Blindature Tattiche):** Pre-Scudo Salva-Utile (`+0,60%` → pavimento `+0,25%`), Filtro Uncino Verde (`green_hook`), Raccolto Gap Mattutino (`09:00–09:30`), Evacuazione Notturna Totale e Scudo Weekend del Venerdì.
   - **V6.2 (5 Blindature Istituzionali):** Interesse Composto di Kelly (`25,34 €` per cartuccia grazie ai `+1,38 €` già incassati), Vincolo Settoriale di Markowitz (4 settori diversi su 4 cartucce), Scudo Elastico ATR a 5m (`0,80x – 1,30x`), Sblocco Titolo Immobile (>4h sotto VWAP) con Zainetto Fiscale 730 e Cassaforte Giornaliera High-Water Mark (`>= +1,80 €`).
   - **V6.5 (2 Blindature Zero-Latency & Macro):** Fusione Prezzo Zero-Latency a `0ms` dalle API Trading 212 sulle candele a 5m Yahoo Finance (eliminando i 15 minuti di ritardo XETRA) e Scudo Anti-Shock Dati Macro USA (`14:28–14:35 CET`).

---

## 2. Come Aprire e Gestire il Progetto Ad-Hoc in Antigravity IDE

In Antigravity IDE clicca su **`File -> Open Folder...`** (oppure da terminale `agy "/Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e"`) e seleziona la cartella autonoma:

```text
/Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e
```

Comandi CLI disponibili nella cartella:

```bash
# Stato completo del portafoglio, delle 4 cartucce, dello scanner 5m e del demone
python3 t212-cli.py status

# Prospetto fiscale Modello 730 (Quadro W, Quadro T LIFO e storico vendite)
python3 t212-cli.py tax-730

# Rigenera la Dashboard HTML interattiva con i dati live
python3 t212-cli.py dashboard

# Esporta il pacchetto ZIP di backup (dist/trading212-quant-v6.5-backup.zip)
python3 t212-cli.py export
```
