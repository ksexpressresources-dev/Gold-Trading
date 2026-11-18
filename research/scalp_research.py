"""Walk-forward research of M15 gold scalping strategies (GC=F, Yahoo).

Train = first half of the 60-day 15m history, test = second half (unseen).
Every trade pays COST points (spread + slippage). One position at a time.
"""
import itertools, os, pickle, sys
import numpy as np
import pandas as pd

sys.path.insert(0, '/home/user/Gold-Trading')
from smc import data, engine

CACHE = os.path.join(os.path.dirname(__file__), '..', 'reports', 'scalp_data.pkl')
COST = 0.4

if os.path.exists(CACHE):
    D = pickle.load(open(CACHE, 'rb'))
else:
    D = {tf: data.fetch('GC=F', tf) for tf in ('15m', '1h')}
    pickle.dump(D, open(CACHE, 'wb'))
m15, h1 = D['15m'], D['1h']


def atr(df, n=14):
    return pd.Series(engine.atr(df, n), index=df.index)


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def h1_bias(df15, kind='ema'):
    """1H bias known at each 15m bar (only closed 1H bars)."""
    if kind == 'ema':
        e = ema(h1['close'], 50)
        b = np.where(h1['close'] > e, 1, -1)
        s = pd.Series(b, index=h1.index + pd.Timedelta('1h'))  # known when bar closes
    else:
        t = engine.trend_series(h1)
        s = t.map({'bull': 1, 'bear': -1, 'none': 0})
        s.index = s.index + pd.Timedelta('1h')
    return s.reindex(df15.index, method='ffill').fillna(0).to_numpy()


def simulate(df, sigs, max_hold=32):
    """sigs: list of (i, side(+1/-1), kind('mkt'|'lmt'), entry, sl, tp, expiry_bars)."""
    o, h, l, c = (df[k].to_numpy() for k in ('open', 'high', 'low', 'close'))
    n = len(df)
    trades, busy_until = [], -1
    for (i, sd, kind, entry, sl, tp, exp) in sorted(sigs, key=lambda s: s[0]):
        if i <= busy_until or i + 1 >= n:
            continue
        j = i + 1
        if kind == 'mkt':
            entry = o[j]
        else:
            while j < n and j <= i + exp:
                if (sd > 0 and l[j] <= entry) or (sd < 0 and h[j] >= entry):
                    break
                # invalidated if TP reached first
                if (sd > 0 and h[j] >= tp) or (sd < 0 and l[j] <= tp):
                    j = n
                    break
                j += 1
            if j >= n or j > i + exp:
                continue
        risk = (entry - sl) * sd
        if risk <= 0:
            continue
        res, k = None, j
        while k < n and k < j + max_hold:
            if (sd > 0 and l[k] <= sl) or (sd < 0 and h[k] >= sl):
                res = -1.0
                break
            if (sd > 0 and h[k] >= tp) or (sd < 0 and l[k] <= tp):
                res = (tp - entry) * sd / risk
                break
            k += 1
        if res is None:
            k = min(k, n - 1)
            res = (c[k] - entry) * sd / risk
        res -= COST / risk
        trades.append((df.index[i], res, risk))
        busy_until = k
    return trades


# ---------------- strategies ----------------
def s_smc(df, rr=2.0, session=True, bias='ema'):
    cfg = engine.Config(setup_expiry=24)
    st = engine.run(df, cfg)
    b = h1_bias(df, bias)
    hr = df.index.hour
    sigs = []
    for s in st.setups:
        sd = 1 if s.side == 'BUY' else -1
        if b[s.created] != sd:
            continue
        if session and not (7 <= hr[s.created] < 17):
            continue
        tp = s.entry + sd * rr * s.risk
        sigs.append((s.created, sd, 'lmt', s.entry, s.sl, tp, 24))
    return sigs


def asian_ranges(df):
    """Asian session = 00:00-07:00 UTC. Returns per-bar (hi, lo) of today's finished Asian range."""
    day = df.index.normalize()
    asia = df[(df.index.hour < 7)]
    rng = asia.groupby(asia.index.normalize()).agg(hi=('high', 'max'), lo=('low', 'min'))
    hi = pd.Series(day).map(rng['hi']).to_numpy()
    lo = pd.Series(day).map(rng['lo']).to_numpy()
    return hi, lo


def s_asian_sweep(df, rr=2.0, win=(7, 16), buf=0.1, tp_mode='rr', bias=None):
    h, l, c = df['high'].to_numpy(), df['low'].to_numpy(), df['close'].to_numpy()
    a = atr(df).to_numpy()
    hi, lo = asian_ranges(df)
    hr = df.index.hour
    bb = h1_bias(df, bias) if bias else None
    day = df.index.normalize()
    sigs, used = [], set()
    for i in range(len(df)):
        if not (win[0] <= hr[i] < win[1]) or np.isnan(hi[i]):
            continue
        key = day[i]
        # sweep of Asian high, close back inside -> sell
        if h[i] > hi[i] and c[i] < hi[i] and (key, -1) not in used and (bb is None or bb[i] <= 0):
            sl = h[i] + buf * a[i]
            risk = sl - c[i]
            tp = c[i] - rr * risk if tp_mode == 'rr' else max(lo[i], c[i] - rr * risk)
            sigs.append((i, -1, 'mkt', c[i], sl, tp, 0)); used.add((key, -1))
        if l[i] < lo[i] and c[i] > lo[i] and (key, 1) not in used and (bb is None or bb[i] >= 0):
            sl = l[i] - buf * a[i]
            risk = c[i] - sl
            tp = c[i] + rr * risk if tp_mode == 'rr' else min(hi[i], c[i] + rr * risk)
            sigs.append((i, 1, 'mkt', c[i], sl, tp, 0)); used.add((key, 1))
    return sigs


def s_fvg_trend(df, rr=2.0, min_gap_atr=0.3, session=True, bias='ema', entry_at='mid'):
    o, h, l, c = (df[k].to_numpy() for k in ('open', 'high', 'low', 'close'))
    a = atr(df).to_numpy()
    b = h1_bias(df, bias)
    hr = df.index.hour
    sigs = []
    for i in range(2, len(df)):
        if session and not (7 <= hr[i] < 17):
            continue
        if b[i] > 0 and l[i] > h[i - 2] and (l[i] - h[i - 2]) >= min_gap_atr * a[i]:
            top, bot = l[i], h[i - 2]
            e = (top + bot) / 2 if entry_at == 'mid' else top
            sl = l[i - 2] - 0.1 * a[i]
            sigs.append((i, 1, 'lmt', e, sl, e + rr * (e - sl), 8))
        if b[i] < 0 and h[i] < l[i - 2] and (l[i - 2] - h[i]) >= min_gap_atr * a[i]:
            top, bot = l[i - 2], h[i]
            e = (top + bot) / 2 if entry_at == 'mid' else bot
            sl = h[i - 2] + 0.1 * a[i]
            sigs.append((i, -1, 'lmt', e, sl, e - rr * (sl - e), 8))
    return sigs


def s_ema_pullback(df, rr=1.5, session=True):
    o, h, l, c = (df[k].to_numpy() for k in ('open', 'high', 'low', 'close'))
    e20, e50 = ema(df['close'], 20).to_numpy(), ema(df['close'], 50).to_numpy()
    a = atr(df).to_numpy()
    b = h1_bias(df, 'ema')
    hr = df.index.hour
    sigs = []
    for i in range(55, len(df)):
        if session and not (7 <= hr[i] < 17):
            continue
        if b[i] > 0 and e20[i] > e50[i] and l[i] <= e20[i] and c[i] > e20[i] and c[i] > o[i]:
            sl = min(l[i - 3:i + 1]) - 0.2 * a[i]
            sigs.append((i, 1, 'mkt', c[i], sl, c[i] + rr * (c[i] - sl), 0))
        if b[i] < 0 and e20[i] < e50[i] and h[i] >= e20[i] and c[i] < e20[i] and c[i] < o[i]:
            sl = max(h[i - 3:i + 1]) + 0.2 * a[i]
            sigs.append((i, -1, 'mkt', c[i], sl, c[i] - rr * (sl - c[i]), 0))
    return sigs


def s_orb(df, rr=1.5, start=13, bars=4, bias=None):
    """NY opening range: first `bars` 15m candles from `start` UTC; trade the first close beyond it."""
    h, l, c = df['high'].to_numpy(), df['low'].to_numpy(), df['close'].to_numpy()
    bb = h1_bias(df, bias) if bias else None
    day = df.index.normalize()
    sigs = []
    for d in np.unique(day):
        idx = np.where(day == d)[0]
        hrs = df.index[idx].hour + df.index[idx].minute / 60
        orr = idx[(hrs >= start) & (hrs < start + bars / 4)]
        if len(orr) < bars:
            continue
        rh, rl = h[orr].max(), l[orr].min()
        after = idx[(hrs >= start + bars / 4) & (hrs < start + 4)]
        for i in after:
            if c[i] > rh and (bb is None or bb[i] >= 0):
                sl = (rh + rl) / 2
                sigs.append((i, 1, 'mkt', c[i], sl, c[i] + rr * (c[i] - sl), 0)); break
            if c[i] < rl and (bb is None or bb[i] <= 0):
                sl = (rh + rl) / 2
                sigs.append((i, -1, 'mkt', c[i], sl, c[i] - rr * (sl - c[i]), 0)); break
    return sigs


def s_bb_revert(df, k=2.5, rr=1.0, hours=(0, 7)):
    o, h, l, c = (df[x].to_numpy() for x in ('open', 'high', 'low', 'close'))
    m = df['close'].rolling(20).mean().to_numpy()
    sd = df['close'].rolling(20).std().to_numpy()
    a = atr(df).to_numpy()
    hr = df.index.hour
    sigs = []
    for i in range(21, len(df)):
        if not (hours[0] <= hr[i] < hours[1]):
            continue
        if c[i] < m[i] - k * sd[i]:
            sl = l[i] - 0.5 * a[i]
            sigs.append((i, 1, 'mkt', c[i], sl, c[i] + rr * (c[i] - sl), 0))
        if c[i] > m[i] + k * sd[i]:
            sl = h[i] + 0.5 * a[i]
            sigs.append((i, -1, 'mkt', c[i], sl, c[i] - rr * (sl - c[i]), 0))
    return sigs


GRIDS = {
    'SMC 15m + bias 1H': (s_smc, dict(rr=[1.5, 2, 3], session=[True, False], bias=['ema', 'smc'])),
    'Asian range sweep': (s_asian_sweep, dict(rr=[1.5, 2, 3], win=[(7, 11), (7, 16), (12, 16)], tp_mode=['rr', 'range'], bias=[None, 'ema'])),
    'FVG trend continuation': (s_fvg_trend, dict(rr=[1.5, 2, 3], min_gap_atr=[0.2, 0.5], session=[True, False], entry_at=['mid', 'edge'])),
    'EMA pullback': (s_ema_pullback, dict(rr=[1, 1.5, 2], session=[True, False])),
    'NY opening range breakout': (s_orb, dict(rr=[1, 1.5, 2], start=[13, 14], bars=[2, 4], bias=[None, 'ema'])),
    'Bollinger revert (Asia)': (s_bb_revert, dict(k=[2, 2.5, 3], rr=[0.8, 1, 1.5])),
}


def stats(tr):
    if not tr:
        return dict(n=0, win=0, R=0, avg=0, dd=0, pf=0)
    r = np.array([t[1] for t in tr])
    eq = np.cumsum(r)
    dd = (np.maximum.accumulate(np.concatenate([[0], eq]))[1:] - eq).max()
    pos, neg = r[r > 0].sum(), -r[r < 0].sum()
    return dict(n=len(r), win=(r > 0).mean() * 100, R=r.sum(), avg=r.mean(), dd=dd, pf=pos / neg if neg else 99)


if __name__ == '__main__':
    split = m15.index[len(m15) // 2]
    print(f'15m bars {len(m15)}  {m15.index[0]} -> {m15.index[-1]}   split {split}   cost {COST} pts')
    rows = []
    for name, (fn, grid) in GRIDS.items():
        keys = list(grid)
        best = None
        allres = []
        for combo in itertools.product(*grid.values()):
            p = dict(zip(keys, combo))
            tr = simulate(m15, fn(m15, **p))
            trn = [t for t in tr if t[0] < split]
            tst = [t for t in tr if t[0] >= split]
            s_tr, s_ts = stats(trn), stats(tst)
            allres.append((p, s_tr, s_ts, stats(tr)))
            if s_tr['n'] >= 8 and (best is None or s_tr['avg'] > best[1]['avg']):
                best = (p, s_tr, s_ts, stats(tr))
        frac_pos = np.mean([r[3]['R'] > 0 for r in allres]) * 100
        if best:
            p, a, b, f = best
            rows.append((name, p, a, b, f, frac_pos))
            print(f"\n== {name}  ({len(allres)} settings, {frac_pos:.0f}% profitable over full period)")
            print(f"   best-on-train {p}")
            print(f"   TRAIN n={a['n']:3d} win={a['win']:3.0f}% R={a['R']:+6.1f} avg={a['avg']:+.2f}")
            print(f"   TEST  n={b['n']:3d} win={b['win']:3.0f}% R={b['R']:+6.1f} avg={b['avg']:+.2f} pf={b['pf']:.2f} dd={b['dd']:.1f}")
    pickle.dump(rows, open(os.path.join(os.path.dirname(__file__), '..', 'reports', 'scalp_rows.pkl'), 'wb'))
