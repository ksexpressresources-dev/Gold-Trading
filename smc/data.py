"""Price data loader (Yahoo Finance chart API, no API key needed)."""
from __future__ import annotations

import time

import pandas as pd
import requests

YAHOO_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"

# Max history Yahoo serves per interval
MAX_RANGE = {"5m": "60d", "15m": "60d", "30m": "60d", "1h": "730d", "1d": "10y"}


def fetch(symbol: str = "GC=F", interval: str = "15m", range_: str | None = None,
          retries: int = 3) -> pd.DataFrame:
    """Return OHLC candles indexed by UTC timestamp."""
    range_ = range_ or MAX_RANGE.get(interval, "60d")
    params = {"interval": interval, "range": range_, "includePrePost": "false"}
    headers = {"User-Agent": "Mozilla/5.0"}
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(YAHOO_URL.format(symbol=symbol), params=params,
                             headers=headers, timeout=20)
            r.raise_for_status()
            chart = r.json()["chart"]
            if not chart["result"]:
                raise RuntimeError(f"Yahoo error: {chart['error']}")
            res = chart["result"][0]
            q = res["indicators"]["quote"][0]
            df = pd.DataFrame(
                {"open": q["open"], "high": q["high"], "low": q["low"],
                 "close": q["close"], "volume": q.get("volume")},
                index=pd.to_datetime(res["timestamp"], unit="s", utc=True),
            )
            df = df.dropna(subset=["open", "high", "low", "close"])
            df = df[~df.index.duplicated(keep="last")].sort_index()
            return df
        except Exception as e:  # network hiccup -> retry with backoff
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed to fetch {symbol} {interval}: {last_err}")


def drop_unclosed(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Remove the last candle if it is still forming."""
    step = pd.Timedelta(interval.replace("m", "min"))
    if step < pd.Timedelta("1D"):
        # Yahoo appends a live tick with an off-grid timestamp (e.g. 15:42) - not a candle
        df = df[(df.index - df.index.normalize()) % step == pd.Timedelta(0)]
    if len(df) and df.index[-1] + step > pd.Timestamp.now(tz="UTC"):
        return df.iloc[:-1]
    return df
