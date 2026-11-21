"""Price data loader.

Spot gold (XAU/USD) comes from Twelve Data, which matches broker and TradingView
XAUUSD prices. The API key is injected by the session's network proxy, so the code
sends a placeholder header. If Twelve Data fails, we fall back to Yahoo's gold
futures (GC=F), which trade a few dollars above spot; `source()` says which was used.
"""
from __future__ import annotations

import os
import pickle
import time
from pathlib import Path

import pandas as pd
import requests

YAHOO_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
TD_URL = "https://api.twelvedata.com/time_series"
SPOT = "XAU/USD"
FALLBACK = "GC=F"

# Max history Yahoo serves per interval
MAX_RANGE = {"5m": "60d", "15m": "60d", "30m": "60d", "1h": "730d", "1d": "10y"}
# Same history depth from Twelve Data, as days back
TD_DAYS = {"15m": 60, "1h": 730, "1d": 3650}
TD_INTERVAL = {"15m": "15min", "1h": "1h", "1d": "1day"}
CACHE = Path(__file__).resolve().parents[1] / "reports" / "cache"
CACHE_MAX_AGE = 600  # seconds: one scan run reuses candles instead of calling the API again

_used: dict[str, str] = {}


def source() -> str:
    """Human label of the data actually used in this process."""
    vals = set(_used.values())
    if not vals:
        return "unknown"
    if vals == {SPOT}:
        return "XAU/USD spot (Twelve Data)"
    if vals == {FALLBACK}:
        return "GC=F gold futures (Yahoo, fallback)"
    if vals == {"BTC-USD"}:
        return "BTC-USD (Yahoo Finance)"
    if vals == {"CL=F"}:
        return "CL=F WTI crude futures (Yahoo Finance)"
    return "mixed: " + ", ".join(f"{k}={v}" for k, v in sorted(_used.items()))


def _fetch_td(interval: str) -> pd.DataFrame:
    """Page backwards through Twelve Data (max 5000 bars per call)."""
    cache = CACHE / f"td_{interval}.pkl"
    if cache.exists() and time.time() - cache.stat().st_mtime < CACHE_MAX_AGE:
        return pickle.loads(cache.read_bytes())
    start = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=TD_DAYS[interval])
    frames, end = [], None
    # GitHub Actions passes the key as a secret env var; in a Claude session the proxy injects it
    headers = {"Authorization": "apikey " + os.environ.get("TWELVEDATA_API_KEY", "proxy-injected")}
    for _ in range(8):
        params = {"symbol": SPOT, "interval": TD_INTERVAL[interval], "outputsize": 5000,
                  "timezone": "UTC", "order": "ASC"}
        if end is not None:
            params["end_date"] = (end - pd.Timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")
        for attempt in range(3):
            r = requests.get(TD_URL, params=params, headers=headers, timeout=30)
            js = r.json()
            if js.get("code") == 429:          # free plan: 8 calls a minute
                time.sleep(61)
                continue
            break
        if js.get("status") != "ok":
            raise RuntimeError(f"Twelve Data: {js.get('message', js)}")
        v = pd.DataFrame(js["values"])
        if v.empty:
            break
        v.index = pd.to_datetime(v.pop("datetime"), utc=True)
        frames.append(v.astype(float))
        end = v.index.min()
        if end <= start or len(v) < 5000:
            break
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df = df[df.index >= start][["open", "high", "low", "close"]]
    df["volume"] = None
    CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps(df))
    return df


def fetch(symbol: str = SPOT, interval: str = "15m", range_: str | None = None,
          retries: int = 3) -> pd.DataFrame:
    """Return OHLC candles indexed by UTC timestamp (spot first, futures as fallback)."""
    if symbol in (SPOT, "XAUUSD"):
        try:
            df = _fetch_td(interval)
            _used[interval] = SPOT
            return df
        except Exception as e:  # no key, quota or network: keep the scanner alive
            print(f"[data] spot XAU/USD unavailable ({e}); using {FALLBACK}")
            symbol = FALLBACK
    _used[interval] = symbol
    return _fetch_yahoo(symbol, interval, range_, retries)


def _fetch_yahoo(symbol: str, interval: str, range_: str | None, retries: int) -> pd.DataFrame:
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
