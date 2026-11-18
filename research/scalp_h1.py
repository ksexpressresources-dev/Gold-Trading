import itertools, numpy as np, pandas as pd
import scalp_research as R
h1 = R.h1
print('1h bars', len(h1), h1.index[0], '->', h1.index[-1])
res = []
for rr, win, tpm, bias in itertools.product([1.5, 2, 3], [(7, 11), (7, 16), (12, 16)], ['rr', 'range'], [None, 'ema']):
    tr = R.simulate(h1, R.s_asian_sweep(h1, rr=rr, win=win, tp_mode=tpm, bias=bias), max_hold=8)
    s = R.stats(tr)
    # stability: R per half-year block
    blocks = pd.Series([t[1] for t in tr], index=[t[0] for t in tr]).resample('6MS').sum() if tr else pd.Series()
    res.append((rr, win, tpm, bias, s, (blocks > 0).sum(), len(blocks)))
for r in sorted(res, key=lambda r: -r[4]['avg']):
    s = r[4]
    print(f"rr={r[0]} win={r[1]} tp={r[2]:5s} bias={str(r[3]):4s}  n={s['n']:3d} win={s['win']:3.0f}% R={s['R']:+6.1f} avg={s['avg']:+.2f} pf={s['pf']:.2f} dd={s['dd']:.1f}  +halves {r[5]}/{r[6]}")
print('profitable settings:', sum(r[4]['R'] > 0 for r in res), '/', len(res))
