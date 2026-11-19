"""M15 scalping model: 1H SMC zone + 15m CHoCH/BOS confirmation.

Research (Nov 2026, 60 days of 15m data, 0.4 pt cost per trade):
  six common M15 scalping methods were tested walk-forward. Only this
  multi-timeframe model stayed profitable across every parameter setting:
  daily-aligned 1H setups, RR 3 -> 11 trades, 45% win, +8.4R, max DD 2.1R.
  Indicator test (research/indicator_filters.py): the daily EMA 200 is a better
  "recommended" filter than daily structure -> 10 trades, 50% win, +9.4R.
  Asian-range sweep, NY opening-range breakout, EMA pullback, FVG
  continuation and Bollinger mean reversion failed out-of-sample or on 2y of 1H.

States per 1H zone:
  WATCH     price has not reached the 1H order block yet
  IN ZONE   price is in the zone, waiting for a 15m break of structure
  ENTRY     15m BOS/CHoCH confirmed -> enter (market), SL beyond the 15m extreme
  IN TRADE  entered earlier, still open
  WIN/LOSS  finished; INVALID (1H SL broken) / MISSED (ran to TP1 without us)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import engine
from .indicators import Filters


@dataclass
class ScalpConfig:
    rr: float = 3.0
    sl_buf_atr: float = 0.1       # SL buffer beyond the 15m extreme, in 15m ATR
    max_wait_h: int = 60          # hours a 1H zone stays tradable
    max_hold: int = 96            # 15m bars to hold a trade (24h)
    min_risk: float = 0.5         # points
    htf_only: bool = False        # True = only daily-aligned zones produce ENTRY
    cost: float = 0.4             # spread + slippage, points


def _sessions(ts: pd.Timestamp) -> str:
    h = ts.hour
    if 12 <= h < 21:
        return "New York" if h >= 13 else "London/NY overlap"
    if 7 <= h < 12:
        return "London"
    if h >= 22 or h < 7:
        return "Asia"
    return "Closed"


def run(m15: pd.DataFrame, h1: pd.DataFrame, d1: pd.DataFrame,
        cfg: ScalpConfig | None = None) -> dict:
    cfg = cfg or ScalpConfig()
    ecfg = engine.Config()
    st1 = engine.run(h1, ecfg, engine.trend_series(d1, ecfg))
    st15 = engine.run(m15, engine.Config(swing_len=2))
    a15 = engine.atr(m15)
    o, h, l, c = (m15[k].to_numpy() for k in ("open", "high", "low", "close"))
    t15 = m15.index
    n = len(m15)
    bos_at = {}
    for e in st15.events:
        if e.kind in ("BOS", "CHoCH"):
            bos_at.setdefault(e.idx, set()).add(e.side)

    filt = Filters(d1, h1)
    rows = []
    for s in st1.setups:
        t_ready = h1.index[s.created] + pd.Timedelta("1h")
        if t_ready < t15[0] + pd.Timedelta("2D"):
            continue
        sd = 1 if s.side == "BUY" else -1
        side = "bull" if sd > 0 else "bear"
        i0 = t15.searchsorted(t_ready)
        end = min(n, i0 + cfg.max_wait_h * 4)
        r = dict(side=s.side, grade=s.grade, htf_aligned=bool(s.htf_aligned),
                 zone_bottom=s.zone_bottom, zone_top=s.zone_top, h1_sl=s.sl, h1_tp1=s.tp1,
                 created=t_ready, state="WATCH", touch=None, ext=None, entry_t=None,
                 entry=None, sl=None, tp=None, tp_half=None, exit_t=None, result_r=None)
        touch_i = ext = entry_i = None
        for j in range(i0, end):
            if touch_i is None:
                if (sd > 0 and h[j] >= s.tp1) or (sd < 0 and l[j] <= s.tp1):
                    r["state"] = "MISSED"; break
                if (sd > 0 and l[j] <= s.zone_top) or (sd < 0 and h[j] >= s.zone_bottom):
                    touch_i, ext = j, (l[j] if sd > 0 else h[j])
                    r["state"], r["touch"] = "IN ZONE", t15[j]
                continue
            ext = min(ext, l[j]) if sd > 0 else max(ext, h[j])
            if (sd > 0 and ext < s.sl) or (sd < 0 and ext > s.sl):
                r["state"] = "INVALID"; break
            if side in bos_at.get(j, ()):
                entry_i = j; break
        else:
            if end < n and r["state"] in ("WATCH", "IN ZONE"):
                r["state"] = "EXPIRED"
        r["ext"] = ext
        if entry_i is not None:
            # enter at the close of the confirming 15m candle (next open in backtest)
            live = entry_i == n - 1
            e = c[entry_i] if live else o[entry_i + 1]
            sl = ext - sd * cfg.sl_buf_atr * a15[entry_i]
            risk = (e - sl) * sd
            if risk >= cfg.min_risk and not (cfg.htf_only and not s.htf_aligned):
                tp = e + sd * cfg.rr * risk
                r.update(entry_t=t15[entry_i], entry=e, sl=sl, tp=tp, tp_half=e + sd * 1.5 * risk,
                         risk=risk, state="ENTRY" if live else "IN TRADE")
                res = None
                for k in range(entry_i + 1, min(n, entry_i + 1 + cfg.max_hold)):
                    if (sd > 0 and l[k] <= sl) or (sd < 0 and h[k] >= sl):
                        res = -1.0; break
                    if (sd > 0 and h[k] >= tp) or (sd < 0 and l[k] <= tp):
                        res = cfg.rr; break
                else:
                    k = None
                if res is not None:
                    r.update(state="WIN" if res > 0 else "LOSS", exit_t=t15[k],
                             result_r=res - cfg.cost / risk)
                elif k is None and entry_i + 1 + cfg.max_hold <= n:
                    kk = entry_i + cfg.max_hold
                    r.update(state="TIME EXIT", exit_t=t15[kk],
                             result_r=(c[kk] - e) * sd / risk - cfg.cost / risk)
            else:
                r["state"] = "SKIP"
        fl = filt.at(r["entry_t"] if r["entry_t"] is not None else t15[-1] + pd.Timedelta("15min"), s.side)
        r["ema200_d"], r["adx"] = fl["ema200_d"], fl["adx"]
        r["reco"] = fl["ema200_d"]          # passed testing: trade only on the daily-EMA200 side
        rows.append(r)

    done = [r for r in rows if r["result_r"] is not None]
    rr = np.array([r["result_r"] for r in done]) if done else np.array([])
    aligned = np.array([r["result_r"] for r in done if r["reco"]]) if done else np.array([])
    eq = np.cumsum(rr) if len(rr) else np.array([0.0])
    stats = {
        "trades": int(len(rr)), "win_rate": float((rr > 0).mean() * 100) if len(rr) else None,
        "total_r": float(rr.sum()) if len(rr) else None, "avg_r": float(rr.mean()) if len(rr) else None,
        "max_dd_r": float((np.maximum.accumulate(np.concatenate([[0], eq]))[1:] - eq).max()) if len(rr) else None,
        "aligned_trades": int(len(aligned)),
        "aligned_win": float((aligned > 0).mean() * 100) if len(aligned) else None,
        "aligned_r": float(aligned.sum()) if len(aligned) else None,
        "median_sl": float(np.median([r["risk"] for r in done])) if done else None,
    }
    return {"rows": rows, "stats": stats, "st15": st15, "atr15": float(a15[-1]),
            "session": _sessions(t15[-1]), "trend15": st15.trend, "trend1h": st1.trend}
