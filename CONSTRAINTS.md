# CONSTRAINTS.md — Contratto Matematico Inviolabile (V11.0 LTS "Zero Cerotti" Prudente)

Questo documento fissa gli **Invarianti Matematici Obbligatori** della piattaforma autonoma Trading 212 (`100,00 EUR` / `4 × 25,00 EUR`). Nessuna modifica futura può violare o abbassare queste soglie.

## Comandi Ufficiali di Verifica
```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

## I 10 Invarianti Bloccanti (`tests/test_quant_invariants.py`)

1. **Invariante #1 — Zero-Ghost su Timeout HTTP:**
   - Se Yahoo Finance non restituisce candele valide e non esiste cache in memoria (`last_valid_bars`), `quant_buy_score == 0.0`, `green_hook_confirmed == False`, `has_fresh_intraday_feed == False`, `rvol_ratio == 0.0`. È vietato cablare valori di fallback fittizi che generino punteggi > 0.
2. **Invariante #2 — Resilienza Cache Candele 5m:**
   - Se un ticker ha già candele valide in `last_valid_bars[ticker]` e una singola richiesta HTTP va in timeout, il motore conserva `VWAP`, `ATR` e `RSI` reali aggiornando la punta con il prezzo `0ms` di Trading 212.
3. **Invariante #3 — Monotonicità Lineare del Ranking (Zero Distorsione `1,55x`):**
   - Il punteggio è puramente additivo: `Setup_VWAP_RSI (0..86) + Bonus_Velocità_ATR (0..10) + Memoria_Giorno`. Nessun moltiplicatore può far scavalcare un setup sporco sopra un setup istituzionale pulito né schiacciare candidati diversi contro `100,0`.
4. **Invariante #4 — Filtro Liquidità Variante Prudente (`RVOL >= 0,20x`):**
   - Nessun ordine di acquisto ordinario può essere eseguito su un titolo con volume relativo `rvol_ratio < 0.20` (esclusione automatica dei book illiquidi/deserti).
5. **Invariante #5 — Separazione Filiera Semiconduttori (12+ Settori Markowitz):**
   - `ASMLa_EQ` e `ASMa_EQ` appartengono a `CHIP_LITOGRAFIA_WAFER`; `BESIa_EQ`, `IFXd_EQ` e `AIXAd_EQ` appartengono a `CHIP_POTENZA_PACKAGING`. Non possono mai coesistere due titoli della stessa sotto-filiera.
6. **Invariante #6 — Efficienza Capitale a 4 Decimali (`4 × 25,00 EUR`):**
   - Per qualsiasi prezzo azionario compreso tra `10,00 EUR` e `2.000,00 EUR`, `round(25.00 / price, 4) * price` deve cadere nell'intervallo `[24,85 EUR, 25,05 EUR]`.
7. **Invariante #7 — Parità Esatta Scudi `Motore == JSON`:**
   - `scudo_mobile_elastico_atr_si_attiva_a_pct` e `livello_incasso_protetto_pct` salvati in `trading212_state.json` coincidono al centesimo con le soglie usate da `evaluate_uncapped_exit()`.
8. **Invariante #8 — Continuità Senza Buchi della Scala Salva-Utile:**
   - Una posizione che ha raggiunto picco `>= +0,65%` non può scendere fino a `+0,10%` con perdita di VWAP/Uncino senza far scattare almeno uno stadio di incasso (`Stadio 2`, `Stadio 1B` o `Stadio 1A`).
9. **Invariante #9 — Airbag Economico & Isolamento Dati Sporchi (`V11_CLEAN_EPOCH_TS`):**
   - Oltre `8–12 minuti` dall'apertura, nessuna posizione sotto `-0,72%` può restare aperta. Tutte le penalità/stop antecedenti a `V11_CLEAN_EPOCH_TS` e tutti i lotti LIFO orfani non presenti sul broker vengono ignorati/ripuliti automaticamente.
10. **Invariante #10 — Candele 5m Deduped & Fuso Orario Fiscale `Europe/Rome`:**
    - `bar_timestamps` è strettamente crescente a multipli esatti di `300s` (zero candele duplicate nello stesso bucket da 5m) e `ItalianTaxTracker730` registra timestamp coerenti col fuso di Borsa `Europe/Rome`.
