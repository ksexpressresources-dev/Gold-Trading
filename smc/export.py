"""Write the JSON files the live dashboard reads (one file per dataset)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def _iso(ts: pd.Timestamp) -> str:
    return ts.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def _r(x, n=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


def write(out: Path, *, symbol, tf, htf_tf, ltf, st, st_htf, signals, atr, price,
          an_ltf, sum_ltf, an_htf, sum_htf, bt_ltf, bt_htf, bt_f=None, data_source: str = "", asset: dict | None = None, bars: int = 120) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    n = len(ltf)
    lo_i = max(0, n - bars)
    win = ltf.iloc[lo_i:]
    near = lambda top, bot: abs((top + bot) / 2 - price) <= 6 * atr

    candles = [{"time": _iso(t), "open": _r(r.open), "high": _r(r.high),
                "low": _r(r.low), "close": _r(r.close)} for t, r in win.iterrows()]

    setups = []
    for s in signals:
        setups.append({
            "side": s["side"], "grade": s["grade"], "score": s["score"],
            "status": ("TRIGGER" if s["trigger"] else
                       "IN TRADE" if s["action"].startswith("IN TRADE") else "WAIT"),
            "action": s["action"],
            "zone_bottom": s["zone"][0], "zone_top": s["zone"][1],
            "entry": s["entry"], "sl": s["sl"], "tp1": s["tp1"], "tp2": s["tp2"],
            "rr_tp2": s["rr_tp2"], "risk_pts": round(abs(s["entry"] - s["sl"]), 2),
            "risk_usd_001": round(abs(s["entry"] - s["sl"]) * (asset or {}).get("lot_mult", 1.0), 2),
            "sweep": s["sweep"], "bos": s["bos"],
            "fvg": bool(s["fvg"]), "htf_aligned": bool(s["htf_aligned"]),
            "expires_in_bars": s["expires_in_bars"], "new": bool(s["new"]),
            "ema200_d": bool(s["ema200_d"]), "adx": s["adx"], "filter_ok": bool(s["filter_ok"]),
        })

    levels = []
    dist = lambda z: abs((z.top + z.bottom) / 2 - price)
    obs = sorted((o for o in st.obs if not o.mitigated and (o.idx >= lo_i or near(o.top, o.bottom))),
                 key=dist)[:5]
    fvgs = sorted((g for g in st.fvgs if not g.filled and (g.idx >= lo_i or near(g.top, g.bottom))),
                  key=dist)[:6]
    for kind, zs in (("OB", obs), ("FVG", fvgs)):
        for z in sorted(zs, key=lambda z: z.idx):
            levels.append({"kind": kind, "side": z.side, "time": _iso(ltf.index[max(z.idx, lo_i)]),
                           "top": _r(z.top), "bottom": _r(z.bottom), "price": None})
    for e in st.events:
        if e.idx >= lo_i:
            levels.append({"kind": e.kind, "side": e.side, "time": _iso(ltf.index[e.idx]),
                           "top": None, "bottom": None, "price": _r(e.price)})

    bt = lambda b, k: _r(b.get(k)) if b.get("trades") else None
    aplus = (bt_ltf.get("by_grade") or {}).get("A+", {})
    summary = [{
        "symbol": symbol, "source": data_source, "asset": (asset or {}).get("key", "XAU"),
        "ticker": (asset or {}).get("ticker", "XAUUSD"), "filter_used": bool((asset or {}).get("swing_filter", True)), "tf": tf, "htf": htf_tf, "time": _iso(ltf.index[-1]),
        "generated": _iso(pd.Timestamp.now(tz="UTC")),
        "price": _r(price), "atr": _r(atr),
        "prev_close": _r(ltf["close"].iloc[-25]) if n > 25 else None,
        "trend_ltf": st.trend, "trend_htf": st_htf.trend,
        "active_setups": len(setups), "trigger": any(s["status"] == "TRIGGER" for s in setups),
        "hist_ltf_bias": sum_ltf.get("bias"), "hist_ltf_pct_up": _r(sum_ltf.get("pct_up"), 0),
        "hist_ltf_median": _r(sum_ltf.get("median_ret")),
        "hist_htf_bias": sum_htf.get("bias"), "hist_htf_pct_up": _r(sum_htf.get("pct_up"), 0),
        "hist_htf_median": _r(sum_htf.get("median_ret")),
        "bt_trades": bt_ltf.get("trades"), "bt_win_rate": bt(bt_ltf, "win_rate"),
        "bt_total_r": bt(bt_ltf, "total_r"), "bt_avg_r": bt(bt_ltf, "avg_r"),
        "bt_max_dd_r": bt(bt_ltf, "max_dd_r"),
        "bt_aplus_trades": aplus.get("trades"), "bt_aplus_win": _r(aplus.get("win_rate"), 0),
        "bt_aplus_r": _r(aplus.get("total_r")),
        "bt_htf_trades": bt_htf.get("trades"), "bt_htf_total_r": bt(bt_htf, "total_r"),
        "bt_htf_win_rate": bt(bt_htf, "win_rate"),
        "bt_f_trades": (bt_f or {}).get("trades"), "bt_f_win": bt(bt_f or {}, "win_rate"),
        "bt_f_r": bt(bt_f or {}, "total_r"), "bt_f_avg": bt(bt_f or {}, "avg_r"), "bt_f_dd": bt(bt_f or {}, "max_dd_r"),
    }]

    analogs = []
    for label, an, hz in ((tf, an_ltf, 32), (htf_tf, an_htf, 24)):
        for i, x in enumerate(an, 1):
            analogs.append({"key": f"{label}-{i}", "tf": label, "rank": i,
                            "start": _iso(x.start), "end": _iso(x.end), "corr": _r(x.corr),
                            "horizon": hz, "fwd_ret": _r(x.fwd_ret), "max_up": _r(x.max_up),
                            "max_down": _r(x.max_down)})

    files = {"candles": candles, "setups": setups, "levels": levels,
             "summary": summary, "analogs": analogs}
    paths = []
    for name, rows in files.items():
        p = out / f"gold_{name}.json"
        p.write_text(json.dumps(rows, separators=(",", ":")))
        paths.append(p)
    return paths
