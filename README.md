# Gold SMC Radar

A gold (GC=F) scanner built on **Smart Money Concepts**, with one combined dashboard
(H1 swing, M15 scalp and signal tracking) refreshed every hour.

1. **Fair Value Gap (FVG)**: 3-candle gap (`low[t] > high[t-2]` / `high[t] < low[t-2]`)
2. **Liquidity sweep**: price takes out a swing high/low (stop hunt)
3. **Break of Structure (BOS)** / CHoCH: a candle *closes* beyond the last swing
4. **Order Block (OB)**: the last opposite candle before the impulse that made the BOS

## H1 swing model (`scan.py`)
**BUY:** sell-side liquidity swept → bullish BOS → unmitigated bullish OB → limit entry at 50% of the OB.
SL beyond the sweep (+0.25 ATR), TP1 = 2R (close half, move SL to break-even), TP2 = leg high / 3R.
**SELL:** mirror image. Grade: sweep + BOS + OB = **B** (3/5), +1 with FVG confluence, +1 with the daily bias → **A+**.

## M15 scalping model (`scalp.py`)
**1H Order Block zone + 15m CHoCH/BOS confirmation.** Enter at the close of the 15m candle that breaks
structure, SL beyond the 15m high/low inside the zone, take half at 1.5R and the rest at 3R.

## Indicator filters (`smc/indicators.py`)
| Filter | H1 swing (2 years) | Decision |
|---|---|---|
| None | 208 trades, +61.5R, avg +0.30R, max DD 8.5R | baseline |
| **Daily EMA200 + 1H ADX(14) > 20** | **78 trades, +46R, avg +0.59R, max DD 5R, 9/10 quarters profitable** | **Used (swing)** |
| Daily EMA200 only | 124 trades, +61.5R, avg +0.50R, max DD 14R | Used for scalp (10 trades, +9.4R) |
| RSI divergence | did not help (scalp: -4.1R) | Rejected |
| London/NY session | did not help | Rejected |

## Scalping research (`research/`)
Seven M15 methods were tested walk-forward on 60 days of 15m data with 0.4 points of cost per trade
(`research/scalp_research.json`). Only the 1H zone + 15m CHoCH model held up:

| Strategy | Test trades | Test R | Verdict |
|---|---|---|---|
| 1H zone + 15m CHoCH (daily-aligned) | 11 | +8.4R | Passed, 24/24 settings profitable |
| Asian range sweep | 18 | +7.7R | Failed on 2 years of 1H (3/36 settings profitable) |
| SMC 15m + 1H bias | 9 | +0.5R | No edge |
| EMA pullback | 52 | -0.5R | Failed |
| NY opening range breakout | 22 | -6.0R | Failed |
| Bollinger mean reversion | 58 | -5.0R | Failed |
| FVG continuation | 16 | -8.3R | Failed |

## Combined dashboard (`radar.py`, `smc/tracking.py`)
`python radar.py` runs the H1 scan, the M15 scan and the tracking, and writes **one** file,
`reports/bundle.json`, which the dashboard reads (each key is one dataset). `dashboard.html` is a copy of the page.

Tracking rebuilds every signal with the scanner's rules and judges it:
**Success** = entry hit, then price moves **100 pips ($10; 1 pip = $0.10)** in our favour before the stop ·
**Fail** = stop first, or out of time (H1 72 hours, M15 24 hours) · **Running** · **Waiting** · **Not executed**.
Tables: status per hour (24 hours), daily record (date, signals, entries, success, fail), signal log.

## Run
```bash
pip install pandas numpy requests
python radar.py             # everything, writes reports/bundle.json
python scan.py              # H1 swing report only
python scalp.py             # M15 scalp report only
```
Exit code `2` = a swing ENTRY TRIGGER or a fresh scalp ENTRY.

> Data: Yahoo Finance GC=F (gold futures), a few dollars off broker spot XAUUSD. Settings were chosen on
> the same history they are tested on, so live results may be weaker. Not financial advice.

## Public website (GitHub Pages)
`.github/workflows/radar.yml` runs `radar.py` for gold and bitcoin every 15 minutes,
builds the site with `tools/build_site.py` (dashboard.html + `site/dash.js` runtime + `vendor/` libraries)
and publishes it to **https://ksexpressresources-dev.github.io/Gold-Trading/**. The page refreshes itself every 5 minutes
and can be installed on a phone with "Add to Home Screen".

One-time setup in GitHub:
1. **Settings → Pages → Build and deployment → Source: GitHub Actions**
2. Optional, for spot XAU/USD prices: **Settings → Secrets and variables → Actions → New repository secret**
   `TWELVEDATA_API_KEY` = your Twelve Data key (without it the scanner uses GC=F futures).

## Bitcoin (BTCUSD)
The same two models run on Bitcoin (`python radar.py --asset BTC`, settings in `smc/instruments.py`), published at
**https://ksexpressresources-dev.github.io/Gold-Trading/btc.html** with a bolder palette and glass tabs.

| BTC check (Yahoo BTC-USD) | Trades | Total R | Decision |
|---|---|---|---|
| H1 swing, no filter (2 years) | 254 | +21R | Used, thin edge (+0.08R/trade) |
| H1 swing + gold's filter | 79 | +3R (year 2 -8R) | Rejected |
| M15 scalp, recommended (daily EMA200 side) | 12 | +4R | Used |
| M15 scalp, against daily EMA200 | 18 | -10R | Avoid |

Success target on BTC = a **$150** move (about the same 0.27% as gold's 100 pips). Cost per scalp trade: $25.
$ risk per 0.01 lot = stop distance × 0.01. Bitcoin trades 24/7, so the workflow now runs every 15 minutes every day.
