"""Compare the current move with history, and backtest the SMC model."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .engine import State


@dataclass
class Analog:
    start: pd.Timestamp
    end: pd.Timestamp
    corr: float
    fwd_ret: float      # % change over horizon after the match
    max_up: float       # % best excursion up within horizon
    max_down: float     # % worst excursion down within horizon


def _windows(x: np.ndarray, w: int) -> np.ndarray:
    return np.lib.stride_tricks.sliding_window_view(x, w)


def analogs(df: pd.DataFrame, window: int = 48, horizon: int = 24, top: int = 5,
            min_corr: float = 0.0) -> tuple[list[Analog], dict]:
    """Find past windows whose price shape best matches the latest `window` bars
    (Pearson correlation of the log-price path) and report what came next."""
    lc = np.log(df["close"].to_numpy())
    hi, lo = df["high"].to_numpy(), df["low"].to_numpy()
    if len(lc) < window * 3 + horizon:
        return [], {}
    cur = lc[-window:]
    cur_z = (cur - cur.mean()) / (cur.std() + 1e-12)

    # candidates must end at least `horizon` bars before now so we know the outcome
    W = _windows(lc[:-(horizon)], window)
    W = W[: len(W) - window]  # don't overlap the current window
    Wz = (W - W.mean(1, keepdims=True)) / (W.std(1, keepdims=True) + 1e-12)
    corr = (Wz @ cur_z) / window
    # also require a similar size of move (not just shape)
    cur_rng = cur.max() - cur.min()
    rng = W.max(1) - W.min(1)
    size_ok = (rng > cur_rng * 0.5) & (rng < cur_rng * 2.0)
    corr = np.where(size_ok, corr, -1)

    picked: list[int] = []
    for i in np.argsort(corr)[::-1]:
        if corr[i] < min_corr or len(picked) >= top:
            break
        if all(abs(i - j) >= window for j in picked):
            picked.append(int(i))

    out = []
    for i in picked:
        end = i + window - 1
        base = np.exp(lc[end])
        f = slice(end + 1, end + 1 + horizon)
        out.append(Analog(
            df.index[i], df.index[end], float(corr[i]),
            float((np.exp(lc[end + horizon]) / base - 1) * 100),
            float((hi[f].max() / base - 1) * 100),
            float((lo[f].min() / base - 1) * 100),
        ))
    if not out:
        return [], {}
    rets = np.array([a.fwd_ret for a in out])
    wts = np.array([max(a.corr, 0.01) for a in out])
    summary = {
        "n": len(out),
        "pct_up": float((rets > 0).mean() * 100),
        "median_ret": float(np.median(rets)),
        "weighted_ret": float((rets * wts).sum() / wts.sum()),
        "avg_corr": float(np.mean([a.corr for a in out])),
        "bias": "BULLISH" if (rets > 0).mean() >= 0.6 else
                "BEARISH" if (rets > 0).mean() <= 0.4 else "NEUTRAL",
    }
    return out, summary


def backtest_stats(st: State) -> dict:
    done = [s for s in st.setups if s.status in ("WIN", "LOSS")]
    res: dict = {"setups": len(st.setups), "trades": len(done)}
    if not done:
        return res
    r = np.array([s.result_r for s in done])
    res.update({
        "win_rate": float((r > 0).mean() * 100),
        "total_r": float(r.sum()),
        "avg_r": float(r.mean()),
        "max_dd_r": float(_max_dd(r)),
    })
    by_grade = {}
    for g in ("A+", "A", "B"):
        rg = np.array([s.result_r for s in done if s.grade == g])
        if len(rg):
            by_grade[g] = {"trades": len(rg), "win_rate": float((rg > 0).mean() * 100),
                           "total_r": float(rg.sum())}
    res["by_grade"] = by_grade
    return res


def _max_dd(r: np.ndarray) -> float:
    eq = np.cumsum(r)
    return float((np.maximum.accumulate(np.concatenate([[0], eq]))[1:] - eq).max())
