"""Signal tracking for the combined dashboard.

Every signal both models produced is rebuilt from the candle history with the
same rules the live scanner uses (sequential, no look-ahead), then judged:

  SUCCESS       entry was hit and price then moved SUCCESS_PIPS in our favour
               before the stop loss
  FAIL          entry was hit and the stop loss came first, or the target was not
               reached within the holding window
  RUNNING       entry hit, neither target nor stop reached yet
  WAITING       signal still waiting for its entry
  NOT EXECUTED  signal expired / was cancelled without an entry

Gold pip convention: 1 pip = $0.10, so 100 pips = $10.00 of price movement.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PIP = 0.10
SUCCESS_PIPS = 100


def configure(pip: float, success_pips: float) -> None:
    """Switch the pip size and success target (per asset, see smc/instruments.py)."""
    global PIP, SUCCESS_PIPS
    PIP, SUCCESS_PIPS = pip, success_pips
TZ = "Asia/Kuala_Lumpur"
HOLD = {"H1": 72, "M15": 96}           # bars a trade is given to reach the target

STATUS_ORDER = ["SUCCESS", "FAIL", "RUNNING", "WAITING", "NOT EXECUTED"]


def _judge(df, start, sd, entry, sl, hold, same_bar_sl=None):
    """Walk forward from bar `start`. Returns (status, bar index or None, best pips)."""
    h, l = df["high"].to_numpy(), df["low"].to_numpy()
    n = len(df)
    target = entry + sd * SUCCESS_PIPS * PIP
    best = 0.0
    if same_bar_sl is not None:  # the fill candle: only the stop counts (we cannot know the order)
        if (sd > 0 and l[same_bar_sl] <= sl) or (sd < 0 and h[same_bar_sl] >= sl):
            return "FAIL", same_bar_sl, 0.0
    for k in range(start, min(n, start + hold)):
        if (sd > 0 and l[k] <= sl) or (sd < 0 and h[k] >= sl):
            return "FAIL", k, best
        fav = ((h[k] - entry) if sd > 0 else (entry - l[k])) / PIP
        best = max(best, fav)
        if (sd > 0 and h[k] >= target) or (sd < 0 and l[k] <= target):
            return "SUCCESS", k, SUCCESS_PIPS
    if start + hold <= n:
        return "FAIL", start + hold - 1, best        # ran out of time
    return "RUNNING", None, best


def swing_signals(h1, st, filt, since, use_filter=True):
    out = []
    step = pd.Timedelta("1h")
    for s in st.setups:
        t = h1.index[s.created] + step
        if t < since:
            continue
        sd = 1 if s.side == "BUY" else -1
        fl = filt.at(t, s.side)
        row = {"model": "H1", "time": t, "side": s.side, "grade": s.grade,
               "filter_ok": bool(fl["ema200_d"] and fl["adx_ok"]) if use_filter else True,
               "entry": s.entry, "sl": s.sl, "exec_time": None, "done_time": None, "best_pips": 0.0}
        if s.fill_idx is not None:
            status, k, best = _judge(h1, s.fill_idx + 1, sd, s.entry, s.sl, HOLD["H1"], same_bar_sl=s.fill_idx)
            row.update(status=status, exec_time=h1.index[s.fill_idx],
                       done_time=None if k is None else h1.index[k] + step, best_pips=best)
        elif s.status == "PENDING":
            row["status"] = "WAITING"
        else:
            row["status"] = "NOT EXECUTED"
        out.append(row)
    return out


def scalp_signals(m15, rows, since):
    out = []
    step = pd.Timedelta("15min")
    idx = m15.index
    for r in rows:
        executed = r["entry_t"] is not None and r["entry"] is not None
        t = (r["entry_t"] + step) if executed else r["created"]
        if t < since:
            continue
        sd = 1 if r["side"] == "BUY" else -1
        row = {"model": "M15", "time": t, "side": r["side"], "grade": r["grade"],
               "filter_ok": bool(r.get("reco")), "entry": r["entry"], "sl": r["sl"],
               "exec_time": r["entry_t"], "done_time": None, "best_pips": 0.0}
        if executed:
            j = idx.get_loc(r["entry_t"])
            status, k, best = _judge(m15, j + 1, sd, r["entry"], r["sl"], HOLD["M15"])
            row.update(status=status, done_time=None if k is None else idx[k] + step, best_pips=best)
        elif r["state"] in ("WATCH", "IN ZONE"):
            row["status"] = "WAITING"
        else:
            row["status"] = "NOT EXECUTED"
        out.append(row)
    return out


def _iso(ts):
    return None if ts is None else pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def build(h1, m15, swing, scalp, now=None, days=14):
    """Return (log, hourly, daily) row lists for the dashboard."""
    now = now or pd.Timestamp.now(tz="UTC")
    sig = sorted(swing + scalp, key=lambda r: r["time"])

    log = []
    for r in reversed(sig[-60:]):
        log.append({"key": f"{r['model']}-{_iso(r['time'])}-{r['side']}", "model": r["model"],
                    "time": _iso(r["time"]), "side": r["side"], "grade": r["grade"],
                    "filter_ok": r["filter_ok"],
                    "entry": None if r["entry"] is None else round(float(r["entry"]), 2),
                    "sl": None if r["sl"] is None else round(float(r["sl"]), 2),
                    "status": r["status"], "exec_time": _iso(r["exec_time"]),
                    "done_time": _iso(r["done_time"]), "best_pips": round(float(r["best_pips"]), 0)})

    # last 24 completed hours (UTC hour slots)
    end = now.floor("h")
    hourly = []
    closes = h1["close"]
    for i in range(24):
        a = end - pd.Timedelta(hours=i + 1)
        b = a + pd.Timedelta("1h")
        bar = closes[(closes.index >= a) & (closes.index < b)]
        row = {"key": _iso(a), "hour": _iso(a),
               "close": None if bar.empty else round(float(bar.iloc[-1]), 2),
               "chg_pips": None}
        if not bar.empty:
            o = h1["open"][(h1.index >= a) & (h1.index < b)].iloc[0]
            row["chg_pips"] = round(float((bar.iloc[-1] - o) / PIP), 0)
        for m in ("H1", "M15"):
            here = [r for r in sig if r["model"] == m and a <= r["time"] < b]
            row[f"{m.lower()}_n"] = len(here)
            row[f"{m.lower()}_status"] = ", ".join(f"{r['side']} {r['status']}" for r in here) if here else "NO SIGNAL"
        hourly.append(row)

    # one row per MYT day per model
    daily = []
    today = now.tz_convert(TZ).normalize()
    for d in range(days):
        day = today - pd.Timedelta(days=d)
        for m in ("H1", "M15"):
            here = [r for r in sig if r["model"] == m and r["time"].tz_convert(TZ).normalize() == day]
            c = {s: sum(r["status"] == s for r in here) for s in STATUS_ORDER}
            ent = c["SUCCESS"] + c["FAIL"] + c["RUNNING"]
            done = c["SUCCESS"] + c["FAIL"]
            daily.append({"key": f"{day.strftime('%Y-%m-%d')}-{m}", "date": day.strftime("%Y-%m-%d"),
                          "model": m, "complete": d > 0, "signals": len(here), "entries": ent,
                          "success": c["SUCCESS"], "fail": c["FAIL"], "running": c["RUNNING"],
                          "waiting": c["WAITING"], "not_executed": c["NOT EXECUTED"],
                          "success_rate": round(100 * c["SUCCESS"] / done, 0) if done else None})
    return log, hourly, daily
