"""Do lagging/leading indicator filters improve the SMC models?

Filters (each computed only from data known when the setup forms):
  ADX(14) on 1H        - trend strength must exceed a threshold
  EMA 200              - price on the trade's side of the 1H / daily EMA 200
  Session              - entry between 07:00 and 17:00 UTC (London + New York)
  RSI(14) divergence   - the swept low (high) makes a lower low (higher high)
                         than the previous swing while RSI does not

Swing model (1H, ~2 years): thresholds are chosen on year 1, judged on year 2.
A filter "helps" only if the kept trades beat the baseline in BOTH years.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smc import data, engine, scalp  # noqa: E402


def rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def adx(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    up, dn = h.diff(), -l.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr_ = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(pdm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr_
    ndi = 100 * pd.Series(ndm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr_
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def divergence(df, r, swings_low, swings_high, idx, side):
    """Bullish: low at idx below the previous swing low, RSI above it. Bearish mirrored."""
    lows, highs = df["low"].to_numpy(), df["high"].to_numpy()
    if side == "BUY":
        prev = [i for i, _ in swings_low if i < idx - 2]
        if not prev:
            return False
        p = prev[-1]
        return lows[idx] < lows[p] and r[idx] > r[p]
    prev = [i for i, _ in swings_high if i < idx - 2]
    if not prev:
        return False
    p = prev[-1]
    return highs[idx] > highs[p] and r[idx] < r[p]


def known_at(series_htf, htf_step, ts):
    """Value of a higher-timeframe series from the last bar closed before ts."""
    s = series_htf.copy()
    s.index = s.index + htf_step
    return s.asof(ts)


def features_swing(h1, d1, st):
    r = rsi(h1["close"]).to_numpy()
    ax = adx(h1).to_numpy()
    e200 = h1["close"].ewm(span=200, adjust=False).mean().to_numpy()
    d200 = d1["close"].ewm(span=200, adjust=False).mean()
    dclose = d1["close"]
    c = h1["close"].to_numpy()
    rows = []
    for s in st.setups:
        if s.status not in ("WIN", "LOSS"):
            continue
        i, sd = s.created, (1 if s.side == "BUY" else -1)
        ts = h1.index[i]
        dd = known_at(dclose, pd.Timedelta("1D"), ts) - known_at(d200, pd.Timedelta("1D"), ts)
        rows.append({
            "time": ts, "side": s.side, "r": s.result_r, "grade": s.grade,
            "adx": ax[i],
            "ema200_1h": (c[i] - e200[i]) * sd > 0,
            "ema200_d": dd * sd > 0 if not np.isnan(dd) else False,
            "session": 7 <= h1.index[s.fill_idx].hour < 17,
            "rsi_div": divergence(h1, r, st.swing_lows, st.swing_highs, s.sweep_idx, s.side),
        })
    return pd.DataFrame(rows)


def features_scalp(m15, h1, rows):
    r15 = rsi(m15["close"]).to_numpy()
    st15 = engine.run(m15, engine.Config(swing_len=2))
    ax1 = adx(h1)
    e1 = h1["close"].ewm(span=200, adjust=False).mean()
    out = []
    for x in rows:
        if x["result_r"] is None:
            continue
        ts = x["entry_t"]
        j = m15.index.get_loc(ts)
        sd = 1 if x["side"] == "BUY" else -1
        t0 = m15.index.get_loc(x["touch"])
        seg = m15.iloc[t0:j + 1]
        ext_i = t0 + int(np.argmin(seg["low"].to_numpy()) if sd > 0 else np.argmax(seg["high"].to_numpy()))
        c1 = known_at(h1["close"], pd.Timedelta("1h"), ts)
        out.append({
            "time": ts, "side": x["side"], "r": x["result_r"], "aligned": x["htf_aligned"],
            "adx": known_at(ax1, pd.Timedelta("1h"), ts),
            "ema200_1h": (c1 - known_at(e1, pd.Timedelta("1h"), ts)) * sd > 0,
            "session": 7 <= ts.hour < 17,
            "rsi_div": divergence(m15, r15, st15.swing_lows, st15.swing_highs, ext_i, x["side"]),
        })
    return pd.DataFrame(out)


def judge(df, split, label):
    a, b = df[df.time < split], df[df.time >= split]
    base = (a.r.mean(), b.r.mean())
    print(f"\n### {label}: {len(df)} trades · baseline avg R  year1 {base[0]:+.2f} ({len(a)})  year2 {base[1]:+.2f} ({len(b)})")
    res = []
    # ADX threshold chosen on year 1
    best = max((t for t in (15, 20, 25, 30)), key=lambda t: a[a.adx > t].r.mean() if (a.adx > t).sum() >= 10 else -9)
    filt = {f"ADX > {best} (dipilih di tahun 1)": df.adx > best,
            "EMA200 1H searah": df.ema200_1h, "Sesi London/NY": df.session,
            "RSI divergence": df.rsi_div}
    if "ema200_d" in df:
        filt["EMA200 harian searah"] = df.ema200_d
    for name, m in filt.items():
        ka, kb = df[m & (df.time < split)], df[m & (df.time >= split)]
        da = ka.r.mean() - base[0] if len(ka) else np.nan
        db = kb.r.mean() - base[1] if len(kb) else np.nan
        helps = len(ka) >= 8 and len(kb) >= 8 and da > 0.03 and db > 0.03
        res.append((name, len(ka), ka.r.sum(), ka.r.mean() if len(ka) else np.nan,
                    len(kb), kb.r.sum(), kb.r.mean() if len(kb) else np.nan, helps))
        print(f"  {name:32s} Y1 kept {len(ka):3d} R {ka.r.sum():+6.1f} avg {ka.r.mean() if len(ka) else 0:+.2f} | "
              f"Y2 kept {len(kb):3d} R {kb.r.sum():+6.1f} avg {kb.r.mean() if len(kb) else 0:+.2f} | "
              f"{'MEMBANTU' if helps else 'tidak'}")
    return res, best


if __name__ == "__main__":
    h1 = data.drop_unclosed(data.fetch("GC=F", "1h"), "1h")
    d1 = data.drop_unclosed(data.fetch("GC=F", "1d"), "1d")
    m15 = data.drop_unclosed(data.fetch("GC=F", "15m"), "15m")
    cfg = engine.Config()
    st = engine.run(h1, cfg, engine.trend_series(d1, cfg))
    sw = features_swing(h1, d1, st)
    split = sw.time.iloc[len(sw) // 2]
    print("split", split)
    judge(sw, split, "SWING 1H (2 tahun)")

    res = scalp.run(m15, h1, d1)
    sc = features_scalp(m15, h1, res["rows"])
    judge(sc, sc.time.iloc[len(sc) // 2], "SCALP M15 (60 hari) - sampel kecil")
    print("\nscalp per filter (all trades):")
    for col in ("session", "ema200_1h", "rsi_div", "aligned"):
        for v in (True, False):
            g = sc[sc[col] == v]
            print(f"  {col:10s}={v!s:5s} n={len(g):2d} R={g.r.sum():+5.1f}")
