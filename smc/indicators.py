"""Indicator filters that passed walk-forward testing (Nov 2026, research/indicator_filters.py).

Swing 1H (2 years): taking only setups on the trade's side of the DAILY EMA 200 and with
1H ADX(14) > 20 -> 78 of 208 trades, +46R, avg +0.59R (vs +0.30), max DD 5R (vs 8.5R),
profitable in 9 of 10 quarters. Scalp M15: the daily EMA 200 alone -> 10 of 19 trades, +9.4R.
RSI divergence and a London/NY session filter did not help and are not used.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ADX_MIN = 20.0


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    up, dn = h.diff(), -l.diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    ndm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr_ = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pdm.ewm(alpha=1 / n, adjust=False).mean() / atr_
    ndi = 100 * ndm.ewm(alpha=1 / n, adjust=False).mean() / atr_
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


class Filters:
    """Looks up filter values as known at a timestamp (only closed bars)."""

    def __init__(self, d1: pd.DataFrame, h1: pd.DataFrame):
        ema = d1["close"].ewm(span=200, adjust=False).mean()
        gap = d1["close"] - ema
        gap.index = gap.index + pd.Timedelta("1D")   # a daily bar is known once it closes
        self._gap = gap
        self._ema = ema.copy(); self._ema.index = self._ema.index + pd.Timedelta("1D")
        ax = adx(h1)
        ax.index = ax.index + pd.Timedelta("1h")
        self._adx = ax

    def at(self, ts: pd.Timestamp, side: str) -> dict:
        sd = 1 if side in ("BUY", "bull") else -1
        g = self._gap.asof(ts)
        a = self._adx.asof(ts)
        ema_ok = bool(not np.isnan(g) and g * sd > 0)
        return {"ema200_d": ema_ok, "ema200_d_level": None if np.isnan(g) else float(self._ema.asof(ts)),
                "adx": None if np.isnan(a) else float(a),
                "adx_ok": bool(not np.isnan(a) and a > ADX_MIN)}
