"""Per-asset settings. All assets use the same SMC models; only these numbers differ.

XAU (gold): research in research/ and README. Swing filter = daily EMA200 + 1H ADX>20.
BTC (bitcoin, Nov 2026 check on 2 years of 1H / 60 days of 15m from Yahoo BTC-USD):
  H1 swing, no filter        254 trades, +21R, avg +0.08R, max DD 15.5R (year 1 +13.5, year 2 +7.5)
  H1 swing + gold's filter    79 trades,  +3R (year 2 -8R)  -> no swing filter for BTC
  M15 scalp, recommended      12 trades,  +4R (daily EMA200 side; the other 18 lost -10R)
Success target = the same relative move as gold's 100 pips ($10 = ~0.27%): about $150 on BTC.
WTI (crude oil, Yahoo CL=F futures, Nov 2026 check):
  H1 swing, no filter        214 trades, -33.5R (year 1 -25.5, year 2 -8)  -> H1 model does NOT work on oil
  H1 swing + ADX>20          133 trades, +7.5R (year 1 -5, year 2 +12.5)  -> not consistent, not used
  M15 scalp, recommended       9 trades, +4.9R (small sample); against EMA200 5 trades, -1.7R
Success target = 25 pips ($0.25, ~0.3% of price). 0.01 lot = 10 barrels.
"""
from __future__ import annotations

ASSETS = {
    "XAU": {
        "symbol": "XAU/USD", "name": "Gold", "ticker": "XAUUSD",
        "pip": 0.10, "success_pips": 100,     # 100 pips = $10
        "cost": 0.4,                          # spread + slippage per trade, in price points
        "lot_mult": 1.0,                      # $ per 1-point move for 0.01 lot (1 oz)
        "swing_filter": True, "weekend": False,
    },
    "BTC": {
        "symbol": "BTC-USD", "name": "Bitcoin", "ticker": "BTCUSD",
        "pip": 1.0, "success_pips": 150,      # $150 move
        "cost": 25.0,
        "lot_mult": 0.01,                     # 0.01 lot = 0.01 BTC
        "swing_filter": False, "weekend": True,
    },
    "WTI": {
        "symbol": "CL=F", "name": "WTI crude oil", "ticker": "WTI",
        "pip": 0.01, "success_pips": 25,      # $0.25 move
        "cost": 0.04,
        "lot_mult": 10.0,                     # 0.01 lot = 10 barrels
        "swing_filter": False, "weekend": False,
        "swing_warning": True,                # the H1 model lost money on oil in testing
    },
}


def get(key: str) -> dict:
    return {"key": key.upper(), **ASSETS[key.upper()]}
