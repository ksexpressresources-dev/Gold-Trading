import itertools, pickle, numpy as np, pandas as pd, sys
sys.path.insert(0, '/home/user/Gold-Trading')
from smc import data, engine
import scalp_research as R
m15, h1 = R.m15, R.h1
d1 = data.fetch('GC=F', '1d')
COST = R.COST
cfg = engine.Config()
st1 = engine.run(h1, cfg, engine.trend_series(d1, cfg))
st15 = engine.run(m15, engine.Config(swing_len=2))
a15 = engine.atr(m15)
o, h, l, c = (m15[k].to_numpy() for k in ('open', 'high', 'low', 'close'))
t15 = m15.index
ev = [(e.idx, e.side) for e in st15.events if e.kind in ('BOS', 'CHoCH')]
start = m15.index[0]

def run(rr=3.0, tp_mode='rr', buf=0.1, need_htf=False, max_wait=60):
    trades = []
    for s in st1.setups:
        t_ready = h1.index[s.created] + pd.Timedelta('1h')
        if t_ready < start + pd.Timedelta('2D'):
            continue
        if need_htf and not s.htf_aligned:
            continue
        sd = 1 if s.side == 'BUY' else -1
        side = 'bull' if sd > 0 else 'bear'
        i0 = t15.searchsorted(t_ready)
        end = min(len(m15), i0 + max_wait * 4)
        touch = None; ext = None; entry_i = None
        for j in range(i0, end):
            if touch is None:
                if (sd > 0 and h[j] >= s.tp1) or (sd < 0 and l[j] <= s.tp1):
                    break  # ran away
                if (sd > 0 and l[j] <= s.zone_top) or (sd < 0 and h[j] >= s.zone_bottom):
                    touch = j; ext = l[j] if sd > 0 else h[j]
                continue
            ext = min(ext, l[j]) if sd > 0 else max(ext, h[j])
            if (sd > 0 and ext < s.sl) or (sd < 0 and ext > s.sl):
                break  # 1H idea invalid
            if any(k == j and sside == side for k, sside in ev):
                entry_i = j; break
        if entry_i is None or entry_i + 1 >= len(m15):
            continue
        e = o[entry_i + 1]
        sl = ext - sd * buf * a15[entry_i]
        risk = (e - sl) * sd
        if risk <= 0.5:
            continue
        tp = e + sd * rr * risk if tp_mode == 'rr' else (s.tp1 if (s.tp1 - e) * sd > risk else e + sd * rr * risk)
        res = None
        for k in range(entry_i + 1, min(len(m15), entry_i + 1 + 96)):
            if (sd > 0 and l[k] <= sl) or (sd < 0 and h[k] >= sl):
                res = -1.0; break
            if (sd > 0 and h[k] >= tp) or (sd < 0 and l[k] <= tp):
                res = (tp - e) * sd / risk; break
        if res is None:
            res = (c[min(k, len(m15)-1)] - e) * sd / risk
        trades.append((t15[entry_i], res - COST / risk, risk, s.side))
    return trades

# baseline: plain 1H setups in same window
base = [s for s in st1.setups if s.status in ('WIN','LOSS') and h1.index[s.created] >= start + pd.Timedelta('2D')]
rb = np.array([s.result_r for s in base])
print(f"BASELINE 1H entries same 60d window: n={len(rb)} R={rb.sum():+.1f} avg={rb.mean() if len(rb) else 0:+.2f}  median SL {np.median([s.risk for s in base]) if base else 0:.1f} pts")
split = m15.index[len(m15)//2]
for rr, tpm, buf, htf in itertools.product([2, 3, 4], ['rr', 'tp1'], [0.1, 0.3], [False, True]):
    tr = run(rr, tpm, buf, htf)
    s = R.stats(tr); a = R.stats([t for t in tr if t[0] < split]); b = R.stats([t for t in tr if t[0] >= split])
    print(f"rr={rr} tp={tpm:3s} buf={buf} htf={htf!s:5s} n={s['n']:2d} win={s['win']:3.0f}% R={s['R']:+5.1f} avg={s['avg']:+.2f} pf={s['pf']:.2f} dd={s['dd']:.1f} | 1st half {a['R']:+.1f} ({a['n']}) 2nd half {b['R']:+.1f} ({b['n']}) | medSL {np.median([t[2] for t in tr]) if tr else 0:.1f}")
