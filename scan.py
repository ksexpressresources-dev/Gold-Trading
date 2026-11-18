#!/usr/bin/env python3
"""Gold SMC scanner.

Usage:
    python scan.py                 # scan GC=F on 1h with daily bias (best backtest)
    python scan.py --tf 15m        # faster entries, 1h bias (weaker in backtest)
    python scan.py --aplus         # only setups with all 4 concepts (FVG required)

Writes reports/latest.md and reports/signal.json.
Exit code 2 = ENTRY TRIGGER (price is in an active setup zone), 0 otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from smc import data, engine, history

TZ = "Asia/Kuala_Lumpur"
HTF_FOR = {"5m": "1h", "15m": "1h", "30m": "1h", "1h": "1d"}


def fmt_t(ts: pd.Timestamp) -> str:
    return ts.tz_convert(TZ).strftime("%d %b %H:%M")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="GC=F")
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--htf", default=None)
    ap.add_argument("--aplus", action="store_true", help="require FVG confluence")
    ap.add_argument("--out", default="reports")
    args = ap.parse_args()
    htf_tf = args.htf or HTF_FOR.get(args.tf, "1d")
    cfg = engine.Config(require_fvg=args.aplus)

    ltf = data.drop_unclosed(data.fetch(args.symbol, args.tf), args.tf)
    htf = data.drop_unclosed(data.fetch(args.symbol, htf_tf), htf_tf)
    htf_trend = engine.trend_series(htf, cfg)
    st = engine.run(ltf, cfg, htf_trend)
    st_htf = engine.run(htf, cfg)

    a = engine.atr(ltf, cfg.atr_len)[-1]
    price = float(ltf["close"].iloc[-1])
    last_t = ltf.index[-1]
    n = len(ltf)

    # ---------- active setups ----------
    signals = []
    for s in st.setups:
        if s.status == "PENDING" or (s.status == "FILLED" and n - 1 - s.fill_idx <= 8):
            in_zone = s.zone_bottom - 0.1 * a <= price <= s.zone_top + 0.1 * a
            dist = (price - s.entry) if s.side == "BUY" else (s.entry - price)
            if s.status == "FILLED":
                action = "IN TRADE (entry already hit)"
            elif in_zone:
                action = "ENTRY TRIGGER - price in zone"
            else:
                action = f"WAIT - limit at entry ({dist:+.2f} away)"
            signals.append({
                "side": s.side, "grade": s.grade, "score": s.score, "action": action,
                "trigger": in_zone and s.status == "PENDING",
                "zone": [round(s.zone_bottom, 2), round(s.zone_top, 2)],
                "entry": round(s.entry, 2), "sl": round(s.sl, 2),
                "tp1": round(s.tp1, 2), "tp2": round(s.tp2, 2),
                "rr_tp2": round(abs(s.tp2 - s.entry) / s.risk, 2),
                "sweep": f"{fmt_t(ltf.index[s.sweep_idx])} @ {s.sweep_price:.2f}",
                "bos": f"{fmt_t(ltf.index[s.created])} @ {s.bos_level:.2f}",
                "fvg": s.has_fvg, "htf_aligned": s.htf_aligned,
                "expires_in_bars": cfg.setup_expiry - (n - 1 - s.created),
                "new": n - 1 - s.created == 0,  # created on the latest closed candle
            })

    # ---------- history comparison ----------
    an_ltf, sum_ltf = history.analogs(ltf, window=64, horizon=32)
    an_htf, sum_htf = history.analogs(htf, window=48, horizon=24)
    bt_ltf = history.backtest_stats(st)
    bt_htf = history.backtest_stats(engine.run(htf, cfg, None))

    # ---------- report ----------
    L = []
    w = L.append
    w(f"# Gold SMC Scan: {args.symbol} {args.tf} (bias {htf_tf})")
    w(f"_Candle terakhir: {fmt_t(last_t)} (MYT) · Harga: **{price:.2f}** · ATR({args.tf}): {a:.2f}_\n")
    w(f"**Trend {args.tf}:** {st.trend.upper()} · **Trend {htf_tf}:** {st_htf.trend.upper()}\n")

    triggers = [s for s in signals if s["trigger"]]
    if triggers:
        w("## 🚨 ENTRY TRIGGER")
    elif signals:
        w("## 👀 Setup aktif (tunggu harga masuk zone)")
    else:
        w("## 😴 Tiada setup aktif. Jangan entry, tunggu.")
    for s in signals:
        w(f"### {s['side']} · Grade {s['grade']} ({s['score']}/5) · {s['action']}")
        w(f"- **Zone (OB):** {s['zone'][0]} – {s['zone'][1]}")
        w(f"- **Entry (50% OB):** {s['entry']}  ·  **SL:** {s['sl']}")
        w(f"- **TP1 (2R):** {s['tp1']}  ·  **TP2:** {s['tp2']} (RR {s['rr_tp2']})")
        w(f"- Risiko: {abs(s['entry'] - s['sl']):.2f} point = **${abs(s['entry'] - s['sl']):.2f} per 0.01 lot**"
          f" (TP1 separuh posisi, SL ke BE)")
        w(f"- Liquidity sweep: {s['sweep']} · BOS: {s['bos']}")
        w(f"- FVG confluence: {'✅' if s['fvg'] else '❌'} · HTF bias sama arah: "
          f"{'✅' if s['htf_aligned'] else '❌'} · Luput dalam {s['expires_in_bars']} candle\n")

    w("## Struktur terkini")
    for e in st.events[-8:]:
        w(f"- {fmt_t(ltf.index[e.idx])} · {e.kind} {e.side} @ {e.price:.2f}")
    w("")
    near = lambda top, bot: abs((top + bot) / 2 - price) <= 4 * a
    obs = [o for o in st.obs if not o.mitigated and near(o.top, o.bottom)][-4:]
    fvgs = [g for g in st.fvgs if not g.filled and near(g.top, g.bottom)][-4:]
    if obs or fvgs:
        w("## Zone berdekatan (belum mitigated)")
        for o in obs:
            w(f"- OB {o.side}: {o.bottom:.2f} – {o.top:.2f} ({fmt_t(ltf.index[o.idx])})")
        for g in fvgs:
            w(f"- FVG {g.side}: {g.bottom:.2f} – {g.top:.2f} ({fmt_t(ltf.index[g.idx])})")
        w("")

    w("## Banding dengan sejarah (pattern serupa)")
    for label, an, sm, hz, tf in (("LTF", an_ltf, sum_ltf, 32, args.tf),
                                  ("HTF", an_htf, sum_htf, 24, htf_tf)):
        if not sm:
            continue
        w(f"**{tf}:** {sm['n']} pattern paling serupa → {sm['pct_up']:.0f}% naik selepas {hz} candle, "
          f"median {sm['median_ret']:+.2f}% → bias **{sm['bias']}** (avg corr {sm['avg_corr']:.2f})")
        for x in an:
            w(f"- {fmt_t(x.start)} → {fmt_t(x.end)} · corr {x.corr:.2f} · selepas itu {x.fwd_ret:+.2f}% "
              f"(max +{x.max_up:.2f}% / {x.max_down:.2f}%)")
        w("")

    w("## Prestasi strategi ni dalam sejarah (backtest)")
    span_of = {"5m": "60 hari", "15m": "60 hari", "30m": "60 hari", "1h": "2 tahun", "1d": "10 tahun"}
    for tf, bt, span in ((args.tf, bt_ltf, span_of[args.tf]), (htf_tf, bt_htf, span_of[htf_tf])):
        if bt.get("trades"):
            w(f"- **{tf} ({span}):** {bt['trades']} trade · win rate {bt['win_rate']:.0f}% · "
              f"total {bt['total_r']:+.1f}R · avg {bt['avg_r']:+.2f}R/trade · max DD {bt['max_dd_r']:.1f}R")
            for g, v in bt["by_grade"].items():
                w(f"  - Grade {g}: {v['trades']} trade, win {v['win_rate']:.0f}%, {v['total_r']:+.1f}R")
        else:
            w(f"- **{tf}:** tiada trade selesai")
    w("\n_Data: Yahoo Finance GC=F (gold futures, beza sikit dari spot XAUUSD). "
      "Bukan nasihat kewangan. Sentiasa guna SL & risk management._")

    report = "\n".join(L)
    out = Path(args.out)
    out.mkdir(exist_ok=True)
    (out / "latest.md").write_text(report)
    (out / "signal.json").write_text(json.dumps({
        "symbol": args.symbol, "tf": args.tf, "time": last_t.isoformat(), "price": price,
        "trend": st.trend, "htf_trend": st_htf.trend, "trigger": bool(triggers),
        "new_setup": any(x["new"] for x in signals),
        "signals": signals, "history_ltf": sum_ltf, "history_htf": sum_htf,
        "backtest_ltf": bt_ltf, "backtest_htf": bt_htf,
    }, indent=2, default=lambda x: bool(x) if isinstance(x, np.bool_) else str(x)))
    print(report)
    return 2 if triggers else 0


if __name__ == "__main__":
    sys.exit(main())
