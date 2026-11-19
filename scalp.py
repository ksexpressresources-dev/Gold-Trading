#!/usr/bin/env python3
"""Gold M15 scalping scanner: 1H SMC zone + 15m CHoCH/BOS confirmation.

Usage:
    python scalp.py                    # print report
    python scalp.py --dash reports/scalp   # also write dashboard JSON files

Exit code 2 = fresh ENTRY (confirmed on one of the last 4 closed 15m candles and still valid).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from smc import data, scalp

TZ = "Asia/Kuala_Lumpur"


def iso(ts):
    return None if ts is None else pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def r2(x, n=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="GC=F")
    ap.add_argument("--dash", default=None)
    args = ap.parse_args()

    m15 = data.drop_unclosed(data.fetch(args.symbol, "15m"), "15m")
    h1 = data.drop_unclosed(data.fetch(args.symbol, "1h"), "1h")
    d1 = data.drop_unclosed(data.fetch(args.symbol, "1d"), "1d")
    res = scalp.run(m15, h1, d1)
    rows, st = res["rows"], res["stats"]
    price = float(m15["close"].iloc[-1])
    last_t = m15.index[-1]
    n = len(m15)
    a15 = res["atr15"]

    live = []
    for r in rows:
        if r["state"] not in ("WATCH", "IN ZONE", "ENTRY", "IN TRADE"):
            continue
        sd = 1 if r["side"] == "BUY" else -1
        row = {
            "side": r["side"], "grade": r["grade"], "htf_aligned": r["htf_aligned"], "state": r["state"],
            "reco": bool(r["reco"]), "ema200_d": bool(r["ema200_d"]), "adx": r2(r["adx"], 1),
            "zone_bottom": r2(r["zone_bottom"]), "zone_top": r2(r["zone_top"]),
            "h1_sl": r2(r["h1_sl"]), "created": iso(r["created"]),
            "dist": r2((price - r["zone_top"]) if sd > 0 else (r["zone_bottom"] - price)),
            "entry": r2(r["entry"]), "sl": r2(r["sl"]), "tp_half": r2(r["tp_half"]), "tp": r2(r["tp"]),
            "risk": r2(r.get("risk")), "entry_time": iso(r["entry_t"]), "fresh": False,
            "action": "",
        }
        if r["state"] in ("ENTRY", "IN TRADE"):
            bars_ago = n - 1 - m15.index.get_loc(r["entry_t"])
            moved_r = (price - r["entry"]) * sd / r["risk"]
            row["moved_r"] = r2(moved_r)
            row["fresh"] = bars_ago <= 3 and -0.5 < moved_r < 0.5
            row["action"] = ("ENTER NOW" if row["fresh"] else
                             "Running (do not chase)")
        elif r["state"] == "IN ZONE":
            inside = r["zone_bottom"] <= price <= r["zone_top"]
            row["action"] = ("Price is in the 1H zone, wait for a 15m CHoCH" if inside else
                             f"1H zone touched, wait for a 15m CHoCH toward {r['side']}")
        else:
            row["action"] = "Wait for price to reach the 1H zone"
        live.append(row)
    fresh = [x for x in live if x["fresh"]]

    # report
    fmt = lambda ts: pd.Timestamp(ts).tz_convert(TZ).strftime("%d %b %H:%M")
    print(f"# Gold Scalp M15 · {args.symbol} · {fmt(last_t)} MYT · price {price:.2f} · session {res['session']}")
    print(f"Trend 15m {res['trend15'].upper()} · 1H {res['trend1h'].upper()} · ATR15 {a15:.2f}")
    for x in live:
        print(f"- {x['side']} {x['grade']}{' (Recommended: daily EMA200 ✓)' if x['reco'] else ' (against daily EMA200)'} · {x['state']} · "
              f"zone {x['zone_bottom']}–{x['zone_top']} · {x['action']}"
              + (f" · entry {x['entry']} SL {x['sl']} TP {x['tp']} (risk {x['risk']})" if x['entry'] else ""))
    if not live:
        print("- No active 1H zone. Wait.")
    if st["trades"]:
        print(f"Backtest 60 days: {st['trades']} trade · win {st['win_rate']:.0f}% · {st['total_r']:+.1f}R · "
              f"recommended (daily EMA200): {st['aligned_trades']} trade, {st['aligned_r']:+.1f}R")

    if args.dash:
        out = Path(args.dash); out.mkdir(parents=True, exist_ok=True)
        win = m15.iloc[-160:]
        candles = [{"time": iso(t), "open": r2(x.open), "high": r2(x.high), "low": r2(x.low), "close": r2(x.close)}
                   for t, x in win.iterrows()]
        lo_i = n - 160
        levels = []
        near = lambda top, bot: abs((top + bot) / 2 - price) <= 8 * a15
        for kind, zs, alive in (("OB", res["st15"].obs, lambda z: not z.mitigated),
                                ("FVG", res["st15"].fvgs, lambda z: not z.filled)):
            cand = [z for z in zs if alive(z) and z.idx >= lo_i and near(z.top, z.bottom)]
            cand = sorted(cand, key=lambda z: abs((z.top + z.bottom) / 2 - price))[:4]
            for z in sorted(cand, key=lambda z: z.idx):
                levels.append({"kind": kind, "side": z.side, "time": iso(m15.index[z.idx]),
                               "top": r2(z.top), "bottom": r2(z.bottom), "price": None})
        for e in res["st15"].events:
            if e.idx >= lo_i and e.kind in ("BOS", "CHoCH", "SWEEP"):
                levels.append({"kind": e.kind, "side": e.side, "time": iso(m15.index[e.idx]),
                               "top": None, "bottom": None, "price": r2(e.price)})
        trades = []
        for r in sorted((r for r in rows if r["entry_t"] is not None), key=lambda r: r["entry_t"], reverse=True)[:15]:
            trades.append({"key": iso(r["entry_t"]), "time": iso(r["entry_t"]), "side": r["side"],
                           "grade": r["grade"], "htf_aligned": r["htf_aligned"], "reco": bool(r["reco"]), "entry": r2(r["entry"]),
                           "sl": r2(r["sl"]), "tp": r2(r["tp"]), "risk": r2(r.get("risk")),
                           "state": r["state"], "result_r": r2(r["result_r"])})
        summary = [{
            "time": iso(last_t), "generated": iso(pd.Timestamp.now(tz="UTC")), "price": r2(price), "atr15": r2(a15), "session": res["session"],
            "trend15": res["trend15"], "trend1h": res["trend1h"], "fresh_entry": bool(fresh),
            "active": len(live), "bt_trades": st["trades"], "bt_win": r2(st["win_rate"], 0),
            "bt_r": r2(st["total_r"], 1), "bt_avg": r2(st["avg_r"]), "bt_dd": r2(st["max_dd_r"], 1),
            "bt_aligned_trades": st["aligned_trades"], "bt_aligned_win": r2(st["aligned_win"], 0),
            "bt_aligned_r": r2(st["aligned_r"], 1), "bt_median_sl": r2(st["median_sl"], 1),
        }]
        for name, rows_ in (("candles", candles), ("signals", live), ("levels", levels),
                            ("trades", trades), ("summary", summary)):
            (out / f"scalp_{name}.json").write_text(json.dumps(rows_, separators=(",", ":")))
    return 2 if fresh else 0


if __name__ == "__main__":
    sys.exit(main())
