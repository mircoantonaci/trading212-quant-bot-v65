# CONSTRAINTS.md — Contratto Matematico Inviolabile (V11.2 LTS "Zero Cerotti")

Questo documento fissa gli **Invarianti Matematici Obbligatori** della piattaforma autonoma Trading 212 (`100,00 EUR` / `4 × 25,00 EUR` su 32 Colossi EUR Zero-Fee XETRA `.DE` / Euronext `.AS`). Nessuna modifica futura può violare o abbassare queste soglie né introdurre "cerotti" (fallback ciechi, soglie scalinate duplicate o feed sintetici).

## Comandi Ufficiali di Verifica
```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

## I 19 Invarianti Bloccanti (`tests/test_quant_invariants.py`)

1. **Invariante #1 — Zero-Ghost su Timeout HTTP:**
   - Se Yahoo Finance non restituisce candele valide e non esiste cache in memoria (`last_valid_bars`), `quant_buy_score == 0.0`, `green_hook_confirmed == False`, `has_fresh_intraday_feed == False`, `rvol_ratio == 0.0`. È vietato cablare valori di fallback fittizi che generino punteggi > 0.
2. **Invariante #2 — Resilienza Cache Candele 5m (Memoria + Disco tra Batch Cloud):**
   - Se un ticker ha già candele valide in `last_valid_bars[ticker]` e una singola richiesta HTTP va in timeout, il motore conserva `VWAP`, `ATR` e `RSI` reali aggiornando la punta con il prezzo `0ms` di Trading 212, persistendo le candele odierne su `.scanner_5m_cache.json` attraverso i riavvii `BATCH` su GitHub Actions.
3. **Invariante #3 — Monotonicità Lineare del Ranking (Zero Distorsione `1,55x` & Zero Tetto ATR `0,34%`):**
   - Il punteggio è puramente additivo: `Setup_VWAP_RSI (0..86) + Bonus_Velocità_ATR (0..10) + Memoria_Giorno`, con soglia minima d'ingresso `BASE_MIN_BUY_SCORE == 58.0` (impedisce ai titoli penalizzati da `-22.0 pt` di rientrare prematuramente).
4. **Invariante #4 — Filtro Liquidità Variante Prudente (`RVOL >= 0,20x` & Asta Chiusura `17:25` Esclusa):**
   - Nessun ordine di acquisto può essere eseguito su un titolo con volume relativo strutturale `rvol_ratio < 0.20`, e il volume medio di riferimento esclude lo spike distorsivo dell'asta di chiusura (`>= 17:25 Europe/Rome`).
5. **Invariante #5 — Separazione Filiera Semiconduttori (12+ Settori Markowitz):**
   - `ASMLa_EQ` e `ASMa_EQ` appartengono a `CHIP_LITOGRAFIA_WAFER`; `BESIa_EQ`, `IFXd_EQ` e `AIXAd_EQ` appartengono a `CHIP_POTENZA_PACKAGING`. Non possono mai coesistere due titoli della stessa sotto-filiera.
6. **Invariante #6 — Efficienza Capitale a 4 Decimali (`4 × 25,00 EUR`):**
   - Per qualsiasi prezzo azionario compreso tra `10,00 EUR` e `2.000,00 EUR`, il frazionamento a 4 decimali garantisce allocazione uniforme sulle 4 cartucce.
7. **Invariante #7 — Parità Esatta Scudi `Motore == JSON` tramite Funzione Pura Unica:**
   - `scudo_mobile_elastico_atr_si_attiva_a_pct` e `livello_incasso_protetto_pct` salvati in `trading212_state.json` sono prodotti dalla medesima funzione pura `compute_profit_protection_floor()` usata da `evaluate_uncapped_exit()` (zero `if/elif` duplicati).
8. **Invariante #8 — Continuità Senza Buchi della Scala Salva-Utile:**
   - Una posizione che ha raggiunto picco `>= +0,65%` non può scendere fino a `+0,10%` con perdita di VWAP/Uncino senza far scattare almeno uno stadio di incasso.
9. **Invariante #9 — Airbag Simmetrico Elastico (`>= 8m`) + Taglio Catastrofico Istantaneo (`< 8m` a `-1,35%`):**
   - Oltre `8–12 minuti` dall'apertura, nessuna posizione sotto `-0,72%` può restare aperta; nei primi `8 minuti`, un flash-crash `<= -1,35%` viene tagliato istantaneamente. Tutte le penalità antecedenti a `V11_CLEAN_EPOCH_TS` vengono ignorate.
10. **Invariante #10 — Candele 5m Deduped & Fuso Orario Fiscale `Europe/Rome`:**
    - `bar_timestamps` è strettamente crescente a multipli esatti di `300s` e `ItalianTaxTracker730` registra timestamp coerenti col fuso di Borsa `Europe/Rome`.
11. **Invariante #11 — VWAP Typical Price `(H+L+C)/3` & RVOL Completed-Bar:**
    - Il VWAP istituzionale pesa `((High + Low + Close) / 3) * Volume`, e il calcolo `RVOL` normalizza le barre parziali in formazione contro la barra chiusa precedente.
12. **Invariante #12 — Pavimento Gapless `-0,05%` Anti-Salto di Tick:**
    - Se una posizione ha già armato uno stadio protettivo e un salto improvviso di mercato la porta tra `-0,05%` e `+0,04%` senza Uncino Verde, lo scudo incassa immediatamente anziché cadere fino all'Airbag.
13. **Invariante #13 — Blocco Permanente Zero-Churn al Target `+30%` (`130,00 EUR`):**
    - Raggiunto il target `130,00 EUR`, la liquidazione avviene una sola volta a mercato aperto e `target_30pct_raggiunto_blocco_attivo = True` inibisce qualsiasi nuovo ordine di acquisto.
14. **Invariante #14 — Orologio `America/New_York` DST-Safe, Pausa Pranzo Integrale (`11:15–08:35 ET`) & Predicato Unico:**
    - Tra le `11:15 Europe/Rome` e le `08:35 America/New_York` (inclusa la finestra macro USA `08:28–08:35 ET`), `allow_new_buys == False` senza eccezioni, mentre gli scudi di vendita sulle posizioni aperte restano attivi al 100%.
15. **Invariante #15 — Monotonicità Stretta della Curva Continua Salva-Utile:**
    - Per ogni coppia di picchi `p2 > p1`, `compute_profit_protection_floor(p2) >= compute_profit_protection_floor(p1)`, accompagnando il profitto protetto da `+0,40%` (`peak = +0,58%`) fino a `shield_act - shield_pull` senza alcuno scalino piatto.
16. **Invariante #16 — Marketable Limit Orders MiFID II (`+1,00%` Cap) & Zero Fallback Cieco a Market Order:**
    - Ogni nuovo acquisto usa esclusivamente `POST /equity/orders/limit` con prezzo limite calettato alle 6 fasce di tick MiFID II RTS 11 e quantità dimensionata su `limit_price` (4ª cartuccia sempre capiente). È severamente vietato ripiegare su `place_market_order` in ingresso o registrare lotti fiscali fantasma su ordini non eseguiti.
17. **Invariante #17 — Indicatori Intraday Gap-Clean (`ATR` & `Kaufman ER`) & Zero Barre Sintetiche su Panchina Ritardata:**
    - Il salto temporale `> 1800s` (`17:25 -> 09:00`) è escluso dal calcolo di `ATR 5m` e `Kaufman ER`; sui titoli in panchina privi di prezzo `0ms` Trading 212 è vietato fabbricare candele sintetiche `now_bucket` sul prezzo Yahoo ritardato di 15 minuti.
18. **Invariante #18 — Trailing Daily High-Water-Mark Vault & Integrità LIFO / 730 Simmetrica:**
    - La Cassaforte Giornaliera lascia correre senza soffitto le sedute in trend (`>= +1,60 EUR`) e si attiva solo a fronte di un ritracciamento realizzato `>= 0,30 EUR` dal massimo di giornata. Le vendite parziali di ribilanciamento preservano i lotti LIFO residui (`zero lots.clear()`) e la riconciliazione di cassa mantiene sempre `plusvalenze >= 0` e `minusvalenze >= 0`.
19. **Invariante #19 — Blocco Totale Nuovi Acquisti Pre-Chiusura (`>= 17:15 CET`) & Selettività Onda Notturna (`>= +0,25%`):**
    - Tra le `17:15` e le `17:30 Europe/Rome` (`FASE_4_RADAR_SELETTORE_ONDA_NOTTURNA_E_WEEKEND`), `allow_new_buys == False` e lo `Switch Stagnazione (#9)` è disattivato: la liquidità incassata prima della chiusura resta protetta al 100% in EUR fino alle `09:05` del giorno successivo, mentre restano aperte overnight solo le posizioni forti già in portafoglio con spinta direzionale USA genuina (`us_avg_pct >= +0,25%`, Nasdaq e S&P500 entrambi positivi, oppure DAX `>= +0,45%` con VIX ultra-calmo).
