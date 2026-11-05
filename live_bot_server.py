#!/usr/bin/env python3
"""
Bot di Trading Live 1:1 con Prezzi Veri da Binance (SOL/EUR & BTC/EUR).
- Aggiorna i prezzi reali ogni 3 secondi dalle API ufficiali di Binance.
- Salva lo stato reale su disco (live_state.json).
- Aggiorna atomicamente il widget HTML live nella chat (live_binance_inline.html).
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
STATE_PATH = BASE_DIR / "live_state.json"
ARTIFACT_DIR = Path("/Users/antonacim/.gemini/antigravity/brain/6aa33967-d540-4201-8b0a-2fd9ff9458b8")
INLINE_HTML_PATH = ARTIFACT_DIR / "live_binance_inline.html"
FULL_HTML_PATH = ARTIFACT_DIR / "trading_arena_50e.html"

FEE_RATE = 0.001  # 0.1% commissione reale Binance Spot


def fetch_binance_data(symbol: str = "SOLEUR") -> dict:
    """Scarica prezzo live, variazione 24h e ultime 25 candele da 1 minuto da Binance."""
    ticker_url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
    klines_url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit=25"
    btc_url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCEUR"

    req1 = urllib.request.Request(ticker_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req1, timeout=5) as r1:
        ticker = json.loads(r1.read().decode("utf-8"))

    req2 = urllib.request.Request(klines_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req2, timeout=5) as r2:
        klines = json.loads(r2.read().decode("utf-8"))

    req3 = urllib.request.Request(btc_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req3, timeout=5) as r3:
        btc_ticker = json.loads(r3.read().decode("utf-8"))

    closes = [float(k[4]) for k in klines]
    return {
        "price": float(ticker["lastPrice"]),
        "bid": float(ticker["bidPrice"]),
        "ask": float(ticker["askPrice"]),
        "high24h": float(ticker["highPrice"]),
        "low24h": float(ticker["lowPrice"]),
        "changePct24h": float(ticker["priceChangePercent"]),
        "btc_price": float(btc_ticker["price"]),
        "closes_1m": closes,
    }


def compute_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = 0.0, 0.0
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses += abs(diff)
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return round(100.0 - (100.0 / (1.0 + rs)), 1)


def init_state(initial_price: float) -> dict:
    now_str = datetime.now().strftime("%H:%M:%S")
    slot_eur = 12.50
    net_eur = slot_eur * (1.0 - FEE_RATE)
    qty_sol = net_eur / initial_price
    agg_margin = 45.00

    return {
        "started_at": datetime.now().strftime("%H:%M:%S"),
        "last_update": now_str,
        "ticks_count": 1,
        "symbol": "SOL/EUR",
        "live_price": initial_price,
        "btc_price": 0.0,
        "high_24h": initial_price,
        "low_24h": initial_price,
        "change_24h_pct": 0.0,
        "rsi_1m": 50.0,
        "price_history": [{"t": now_str, "p": initial_price}],
        "prudent": {
            "cash_eur": 37.50,
            "slot_size": 12.50,
            "used_slots": 1,
            "qty_sol": qty_sol,
            "avg_entry": initial_price,
            "last_buy_price": initial_price,
            "next_buy_target": round(initial_price * (1.0 - 0.008), 2),
            "take_profit_target": round(initial_price * (1.0 + 0.008), 2),
            "realized_profit_eur": 0.0,
            "trades_won": 0,
            "logs": [
                f"[{now_str}] AVVIO LIVE: Acquistata Cartuccia 1/4 (12.50€) al prezzo vero Binance di {initial_price:.2f}€ (qty: {qty_sol:.4f} SOL). Target vendita: {initial_price*1.008:.2f}€ (+0.8%) | Slot 2 a: {initial_price*0.992:.2f}€ (-0.8%)."
            ],
            "equity_eur": 49.99,
            "unrealized_pnl_eur": -0.01,
        },
        "aggressive": {
            "cash_eur": 5.00,
            "in_position": True,
            "margin_eur": agg_margin,
            "leverage": 3.0,
            "entry_price": initial_price,
            "tp_price": round(initial_price * (1.0 + 0.015), 2),
            "sl_price": round(initial_price * (1.0 - 0.010), 2),
            "realized_profit_eur": 0.0,
            "trades_won": 0,
            "trades_lost": 0,
            "logs": [
                f"[{now_str}] AVVIO LIVE: Aperta posizione Leva 3x con 45.00€ (esposizione 135.00€) a {initial_price:.2f}€. Take Profit: {initial_price*1.015:.2f}€ | Stop Loss: {initial_price*0.99:.2f}€."
            ],
            "unrealized_pnl_eur": -0.27,
            "equity_eur": 49.73,
        },
    }


def step_live_bots(state: dict, market: dict) -> dict:
    price = market["price"]
    now_str = datetime.now().strftime("%H:%M:%S")
    rsi = compute_rsi(market["closes_1m"], period=14)

    state["last_update"] = now_str
    state["ticks_count"] = state.get("ticks_count", 0) + 1
    state["live_price"] = price
    state["btc_price"] = market["btc_price"]
    state["high_24h"] = market["high24h"]
    state["low_24h"] = market["low24h"]
    state["change_24h_pct"] = market["changePct24h"]
    state["rsi_1m"] = rsi
    state["closes_1m"] = market["closes_1m"]

    state["price_history"].append({"t": now_str, "p": price})
    if len(state["price_history"]) > 90:
        state["price_history"].pop(0)

    # --- 1. BOT PRUDENTE ---
    p = state["prudent"]
    if p["used_slots"] > 0 and p["qty_sol"] > 0:
        if price >= p["take_profit_target"]:
            gross = p["qty_sol"] * price
            net = gross * (1.0 - FEE_RATE)
            invested = p["used_slots"] * p["slot_size"]
            profit = round(net - invested, 3)
            p["cash_eur"] = round(p["cash_eur"] + net, 3)
            p["realized_profit_eur"] = round(p["realized_profit_eur"] + profit, 3)
            p["trades_won"] += 1
            p["logs"].insert(
                0,
                f"[{now_str}] VITTORIA REALE: Vendute {p['used_slots']} cartucce a {price:.2f}€ | Netto: +{profit:.2f}€!",
            )
            # Riapre subito la Cartuccia 1 al nuovo prezzo
            spend = p["slot_size"]
            qty_new = (spend * (1.0 - FEE_RATE)) / price
            p["cash_eur"] = round(p["cash_eur"] - spend, 3)
            p["used_slots"] = 1
            p["qty_sol"] = qty_new
            p["avg_entry"] = price
            p["last_buy_price"] = price
            p["next_buy_target"] = round(price * 0.992, 2)
            p["take_profit_target"] = round(price * 1.008, 2)
            p["logs"].insert(
                0,
                f"[{now_str}] NUOVO CICLO: Riaperta Cartuccia 1/4 (12.50€) a {price:.2f}€. Target: {p['take_profit_target']:.2f}€.",
            )

    if p["used_slots"] < 4 and p["cash_eur"] >= p["slot_size"] and price <= p["next_buy_target"]:
        spend = p["slot_size"]
        qty_new = (spend * (1.0 - FEE_RATE)) / price
        prev_cost = p["qty_sol"] * p["avg_entry"]
        p["qty_sol"] += qty_new
        p["used_slots"] += 1
        p["cash_eur"] = round(p["cash_eur"] - spend, 3)
        p["avg_entry"] = round((prev_cost + spend) / p["qty_sol"], 2)
        p["last_buy_price"] = price
        p["next_buy_target"] = round(price * 0.992, 2) if p["used_slots"] < 4 else 0.0
        p["take_profit_target"] = round(p["avg_entry"] * 1.008, 2)
        p["logs"].insert(
            0,
            f"[{now_str}] MEDIAZIONE: Acquistata Cartuccia {p['used_slots']}/4 (12.50€) a {price:.2f}€. Nuovo PMC: {p['avg_entry']:.2f}€!",
        )

    # Valore liquido netto se vendesse ora
    current_val_p = (p["qty_sol"] * price) * (1.0 - FEE_RATE)
    p["equity_eur"] = round(p["cash_eur"] + current_val_p, 2)
    p["unrealized_pnl_eur"] = round(current_val_p - (p["used_slots"] * p["slot_size"]), 2)

    # --- 2. BOT AGGRESSIVO ---
    a = state["aggressive"]
    if a["in_position"]:
        move_pct = (price - a["entry_price"]) / a["entry_price"]
        lev_pnl_pct = (move_pct * a["leverage"]) - (FEE_RATE * 2 * a["leverage"])
        a["unrealized_pnl_eur"] = round(a["margin_eur"] * lev_pnl_pct, 2)
        a["equity_eur"] = round(a["cash_eur"] + a["margin_eur"] + a["unrealized_pnl_eur"], 2)

        if price >= a["tp_price"]:
            pnl = round(a["margin_eur"] * lev_pnl_pct, 2)
            a["cash_eur"] = round(a["cash_eur"] + a["margin_eur"] + pnl, 2)
            a["realized_profit_eur"] = round(a["realized_profit_eur"] + pnl, 2)
            a["trades_won"] += 1
            a["in_position"] = False
            a["margin_eur"] = 0.0
            a["logs"].insert(
                0,
                f"[{now_str}] TAKE PROFIT LEVA 3x: Chiuso a {price:.2f}€ | Guadagno: +{pnl:.2f}€!",
            )
        elif price <= a["sl_price"]:
            pnl = round(a["margin_eur"] * lev_pnl_pct, 2)
            a["cash_eur"] = max(0.0, round(a["cash_eur"] + a["margin_eur"] + pnl, 2))
            a["realized_profit_eur"] = round(a["realized_profit_eur"] + pnl, 2)
            a["trades_lost"] += 1
            a["in_position"] = False
            a["margin_eur"] = 0.0
            a["logs"].insert(
                0,
                f"[{now_str}] STOP LOSS LEVA 3x: Tagliata perdita a {price:.2f}€ | Perdita: {pnl:.2f}€.",
            )
    else:
        a["unrealized_pnl_eur"] = 0.0
        a["equity_eur"] = round(a["cash_eur"], 2)
        if rsi < 46.0 and a["cash_eur"] >= 10.0:
            margin = round(a["cash_eur"] * 0.90, 2)
            a["cash_eur"] = round(a["cash_eur"] - margin, 2)
            a["margin_eur"] = margin
            a["entry_price"] = price
            a["tp_price"] = round(price * 1.015, 2)
            a["sl_price"] = round(price * 0.990, 2)
            a["in_position"] = True
            a["logs"].insert(
                0,
                f"[{now_str}] RIENTRO LEVA 3x: Puntati {margin:.2f}€ a {price:.2f}€ (RSI={rsi}).",
            )

    return state


def render_live_html(state: dict) -> str:
    p = state["prudent"]
    a = state["aggressive"]
    price = state["live_price"]
    p_diff = round(p["equity_eur"] - 50.0, 2)
    p_pct = round((p_diff / 50.0) * 100, 2)
    a_diff = round(a["equity_eur"] - 50.0, 2)
    a_pct = round((a_diff / 50.0) * 100, 2)

    p_color = "text-emerald-400" if p_diff >= 0 else "text-red-400"
    a_color = "text-emerald-400" if a_diff >= 0 else "text-red-400"
    chg_color = "text-emerald-400" if state["change_24h_pct"] >= 0 else "text-red-400"

    slots_html = ""
    for i in range(1, 5):
        active = i <= p["used_slots"]
        cls = (
            "border-emerald-500 bg-emerald-500/20 text-emerald-300 font-bold"
            if active
            else "border-[var(--border)] text-[var(--muted-foreground)]"
        )
        lbl = f"S{i}: 12.5€" if active else f"S{i}: Pronta"
        slots_html += f'<div class="py-1 px-1 rounded border text-center text-xs font-mono {cls}">{lbl}</div>'

    p_logs_html = "".join(
        f'<div class="text-xs font-mono leading-snug">{lg}</div>' for lg in p["logs"][:6]
    )
    a_logs_html = "".join(
        f'<div class="text-xs font-mono leading-snug">{lg}</div>' for lg in a["logs"][:6]
    )

    closes_json = json.dumps(state.get("closes_1m", [price]))

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8" />
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
</head>
<body class="bg-transparent text-[var(--foreground)] antialiased p-2">
  <div class="bg-[var(--card)] text-[var(--foreground)] border border-[var(--border)] rounded-xl p-4 shadow-sm space-y-3">
    <!-- Top Live Status Bar -->
    <div class="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] pb-2.5">
      <div class="flex items-center gap-2">
        <span class="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping"></span>
        <span class="font-bold text-sm">LIVE BINANCE (1:1 Tempo Reale)</span>
        <span class="text-xs font-mono text-[var(--muted-foreground)]">
          | SOL/EUR: <strong class="text-sm text-[var(--foreground)]">{price:.2f} €</strong>
          (<span class="{chg_color}">{state["change_24h_pct"]:+.2f}% 24h</span>)
          | BTC: <strong>{state.get("btc_price", 0):,.0f} €</strong>
          | RSI(1m): <strong>{state["rsi_1m"]}</strong>
        </span>
      </div>
      <div class="text-xs font-mono text-[var(--muted-foreground)]">
        Aggiornato: <strong class="text-[var(--foreground)]">{state["last_update"]}</strong> (Tick #{state.get("ticks_count", 1)})
      </div>
    </div>

    <!-- Due Bot in Gara sui Prezzi Veri -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
      <!-- Bot Prudente -->
      <div class="p-3 rounded-lg border border-emerald-500/40 bg-[var(--secondary)] space-y-2">
        <div class="flex items-center justify-between">
          <span class="text-xs font-bold text-emerald-400">🛡️ BOT PRUDENTE (Smart Grid)</span>
          <span class="text-base font-bold font-mono">{p["equity_eur"]:.2f} €</span>
        </div>
        <div class="flex items-center justify-between text-xs font-mono">
          <span class="{p_color}">PnL Totale: {p_diff:+.2f} € ({p_pct:+.2f}%)</span>
          <span class="text-[var(--muted-foreground)]">Chiuse: <strong class="text-emerald-400">{p["trades_won"]}</strong></span>
        </div>
        <div class="grid grid-cols-4 gap-1">{slots_html}</div>
        <div class="flex justify-between text-xs font-mono text-[var(--muted-foreground)] pt-0.5">
          <span>PMC: <strong class="text-[var(--foreground)]">{p["avg_entry"]:.2f}€</strong></span>
          <span>Vende a: <strong class="text-emerald-400">{p["take_profit_target"]:.2f}€</strong></span>
          <span>Slot {min(4, p["used_slots"]+1)} a: <strong class="text-sky-400">{p["next_buy_target"]:.2f}€</strong></span>
        </div>
        <div class="h-20 overflow-y-auto rounded bg-[var(--card)] border border-[var(--border)] p-1.5 space-y-1">
          {p_logs_html}
        </div>
      </div>

      <!-- Bot Aggressivo -->
      <div class="p-3 rounded-lg border border-amber-500/40 bg-[var(--secondary)] space-y-2">
        <div class="flex items-center justify-between">
          <span class="text-xs font-bold text-amber-400">⚡ BOT AGGRESSIVO (Leva 3x)</span>
          <span class="text-base font-bold font-mono">{a["equity_eur"]:.2f} €</span>
        </div>
        <div class="flex items-center justify-between text-xs font-mono">
          <span class="{a_color}">PnL Totale: {a_diff:+.2f} € ({a_pct:+.2f}%)</span>
          <span class="text-[var(--muted-foreground)]">Vinte: <strong class="text-emerald-400">{a["trades_won"]}</strong> | Stop: <strong class="text-red-400">{a["trades_lost"]}</strong></span>
        </div>
        <div class="py-1 px-2 rounded border border-[var(--border)] text-xs font-mono flex justify-between">
          <span>Ingresso: <strong>{a["entry_price"]:.2f}€</strong></span>
          <span class="text-emerald-400">TP: <strong>{a["tp_price"]:.2f}€</strong></span>
          <span class="text-red-400">SL: <strong>{a["sl_price"]:.2f}€</strong></span>
        </div>
        <div class="flex justify-between text-xs font-mono text-[var(--muted-foreground)] pt-0.5">
          <span>Margine: <strong class="text-[var(--foreground)]">{a["margin_eur"]:.2f}€</strong></span>
          <span>Esposizione 3x: <strong class="text-amber-400">{a["margin_eur"]*3:.2f}€</strong></span>
        </div>
        <div class="h-20 overflow-y-auto rounded bg-[var(--card)] border border-[var(--border)] p-1.5 space-y-1">
          {a_logs_html}
        </div>
      </div>
    </div>

    <!-- Grafico Prezzo Reale SOL/EUR ultimi 25 minuti + livelli Bot -->
    <div>
      <div class="flex justify-between text-xs text-[var(--muted-foreground)] mb-1 font-mono">
        <span>Grafico Reale SOL/EUR (ultimi 25 min da Binance)</span>
        <span>Linea Verde = Target Vendita ({p["take_profit_target"]:.2f}€) | Linea Blu = Acquisto Slot 2 ({p["next_buy_target"]:.2f}€)</span>
      </div>
      <canvas id="kchart" width="720" height="75" class="w-full h-16 rounded border border-[var(--border)]"></canvas>
    </div>
  </div>

  <script>
    const closes = {closes_json};
    const tp = {p["take_profit_target"]};
    const nb = {p["next_buy_target"]};
    const entry = {p["avg_entry"]};

    function drawKlines() {{
      const c = document.getElementById('kchart');
      if (!c) return;
      const ctx = c.getContext('2d'), w = c.width, h = c.height;
      ctx.clearRect(0, 0, w, h);
      const all = [...closes, tp, nb];
      const min = Math.min(...all) - 0.15;
      const max = Math.max(...all) + 0.15;
      const toY = v => h - ((v - min) / (max - min)) * (h - 14) - 7;

      // Target Take Profit (Verde tratteggiato)
      ctx.strokeStyle = 'rgba(16, 185, 129, 0.55)';
      ctx.setLineDash([4, 4]);
      ctx.beginPath(); ctx.moveTo(0, toY(tp)); ctx.lineTo(w, toY(tp)); ctx.stroke();

      // Next Buy Slot 2 (Blu tratteggiato)
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.55)';
      ctx.beginPath(); ctx.moveTo(0, toY(nb)); ctx.lineTo(w, toY(nb)); ctx.stroke();
      ctx.setLineDash([]);

      // Prezzo reale SOL/EUR
      ctx.strokeStyle = '#f8fafc';
      ctx.lineWidth = 2.2;
      ctx.beginPath();
      closes.forEach((v, i) => {{
        const x = (i / Math.max(1, closes.length - 1)) * (w - 20) + 10;
        const y = toY(v);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }});
      ctx.stroke();
    }}
    drawKlines();
    setTimeout(() => window.location.reload(), 4000);
  </script>
</body>
</html>"""


def atomic_write(target: Path, content: str):
    tmp = target.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)


def run_once_and_save():
    market = fetch_binance_data("SOLEUR")
    if STATE_PATH.exists():
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            state = init_state(market["price"])
    else:
        state = init_state(market["price"])

    state = step_live_bots(state, market)
    atomic_write(STATE_PATH, json.dumps(state, indent=2, ensure_ascii=False))

    if ARTIFACT_DIR.exists():
        html = render_live_html(state)
        atomic_write(INLINE_HTML_PATH, html)
        atomic_write(FULL_HTML_PATH, html)

    return state


if __name__ == "__main__":
    if "--reset" in sys.argv and STATE_PATH.exists():
        STATE_PATH.unlink()
    if "--once" in sys.argv:
        st = run_once_and_save()
        print(json.dumps(st, indent=2, ensure_ascii=False))
    else:
        print("Avvio demone in tempo reale 1:1 collegato a Binance (SOL/EUR & BTC/EUR)...")
        while True:
            try:
                run_once_and_save()
            except Exception as e:
                print(f"Errore temporaneo rete: {e}", flush=True)
            time.sleep(3)
