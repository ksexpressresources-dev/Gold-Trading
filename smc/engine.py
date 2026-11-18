"""Smart Money Concepts engine.

Processes candles one by one (no look-ahead), detecting:
  1. Fair Value Gaps (FVG)
  2. Liquidity sweeps
  3. Break of Structure (BOS) / Change of Character (CHoCH)
  4. Order Blocks (OB)
and combining them into trade setups:

  BUY  model: sell-side liquidity swept -> bullish BOS -> unmitigated bullish OB
              (+ FVG confluence) -> limit entry on retrace into the OB.
  SELL model: mirror image.

Because it is sequential, the same code powers the live scan and the backtest.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Config:
    swing_len: int = 3            # bars each side to confirm a swing point
    atr_len: int = 14
    sweep_lookback: int = 40      # sweep must happen within N bars before BOS
    setup_expiry: int = 60        # bars a pending setup stays valid
    ob_search: int = 6            # bars to look back for the OB candle
    sl_buffer_atr: float = 0.25   # SL distance beyond sweep extreme, in ATR
    min_rr_tp2: float = 2.0
    require_fvg: bool = False     # True = only A+ setups (all 4 concepts)
    max_zone_atr: float = 3.0     # skip OBs wider than this (too loose)
    sweep_origin_bars: int = 3    # sweep candle must be within N bars of the leg extreme
    max_risk_atr: float = 99.0    # skip setups whose SL is too far (off by default)
    # "take": leg extreme takes out an earlier swing level (wick or close)
    # "wick": sweep candle must close back inside the level (strict)
    # "off" : no sweep needed (BOS + OB only) - for comparison
    # "recent": any sell/buy-side sweep within sweep_lookback bars (best in backtest)
    sweep_mode: str = "recent"
    sl_mode: str = "sweep"        # "sweep": beyond sweep extreme · "ob": beyond the OB only


@dataclass
class FVG:
    side: str            # "bull" | "bear"
    top: float
    bottom: float
    idx: int             # index of the middle (displacement) candle
    filled: bool = False


@dataclass
class OB:
    side: str
    top: float
    bottom: float
    idx: int
    mitigated: bool = False


@dataclass
class Setup:
    side: str                  # "BUY" | "SELL"
    created: int               # bar index of the BOS
    zone_top: float
    zone_bottom: float
    entry: float
    sl: float
    tp1: float
    tp2: float
    sweep_idx: int
    sweep_price: float
    bos_level: float
    has_fvg: bool
    htf_aligned: bool | None = None
    status: str = "PENDING"    # PENDING -> FILLED -> WIN/LOSS/BE ; or EXPIRED/INVALID/MISSED
    fill_idx: int | None = None
    exit_idx: int | None = None
    tp1_hit: bool = False
    result_r: float = 0.0

    @property
    def risk(self) -> float:
        return abs(self.entry - self.sl)

    @property
    def score(self) -> int:
        # sweep + BOS + OB are mandatory -> 3, +1 FVG, +1 HTF bias
        return 3 + int(self.has_fvg) + int(bool(self.htf_aligned))

    @property
    def grade(self) -> str:
        return {5: "A+", 4: "A", 3: "B"}[self.score]


@dataclass
class Event:
    kind: str        # BOS / CHoCH / SWEEP
    side: str        # bull / bear
    idx: int
    price: float


@dataclass
class State:
    trend: str = "none"
    events: list[Event] = field(default_factory=list)
    fvgs: list[FVG] = field(default_factory=list)
    obs: list[OB] = field(default_factory=list)
    setups: list[Setup] = field(default_factory=list)
    swing_highs: list[tuple[int, float]] = field(default_factory=list)
    swing_lows: list[tuple[int, float]] = field(default_factory=list)
    broken: set = field(default_factory=set)   # (side, swing idx) already used for BOS


def atr(df: pd.DataFrame, n: int = 14) -> np.ndarray:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=1).mean().to_numpy()


def run(df: pd.DataFrame, cfg: Config | None = None,
        htf_trend: pd.Series | None = None) -> State:
    """Run the engine over all candles. htf_trend: per-bar 'bull'/'bear' bias."""
    cfg = cfg or Config()
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    a = atr(df, cfg.atr_len)
    n = cfg.swing_len
    st = State()
    # live (unbroken / unswept) liquidity levels
    open_highs: list[list] = []   # [idx, price, swept]
    open_lows: list[list] = []

    for t in range(len(df)):
        # ---- 1. confirm swing point at t-n (needs n bars on the right) ----
        p = t - n
        if p >= n:
            if h[p] == h[p - n:t + 1].max():
                st.swing_highs.append((p, h[p]))
                open_highs.append([p, h[p], False])
            if l[p] == l[p - n:t + 1].min():
                st.swing_lows.append((p, l[p]))
                open_lows.append([p, l[p], False])

        # ---- 2. FVG detection + fill tracking ----
        if t >= 2:
            if l[t] > h[t - 2]:
                st.fvgs.append(FVG("bull", l[t], h[t - 2], t - 1))
            if h[t] < l[t - 2]:
                st.fvgs.append(FVG("bear", l[t - 2], h[t], t - 1))
        for g in st.fvgs:
            if g.filled or g.idx >= t - 1:
                continue
            if g.side == "bull" and l[t] <= g.bottom:
                g.filled = True
            elif g.side == "bear" and h[t] >= g.top:
                g.filled = True

        # ---- 3. OB mitigation (closed through = invalid) ----
        for ob in st.obs:
            if ob.mitigated or ob.idx >= t:
                continue
            if (ob.side == "bull" and c[t] < ob.bottom) or (ob.side == "bear" and c[t] > ob.top):
                ob.mitigated = True

        # ---- 4. Liquidity sweeps: wick through level, close back inside ----
        for lv in open_highs:
            if not lv[2] and lv[0] < t and h[t] > lv[1] and c[t] < lv[1]:
                lv[2] = True
                st.events.append(Event("SWEEP", "bear", t, lv[1]))   # buy-side taken
        for lv in open_lows:
            if not lv[2] and lv[0] < t and l[t] < lv[1] and c[t] > lv[1]:
                lv[2] = True
                st.events.append(Event("SWEEP", "bull", t, lv[1]))   # sell-side taken

        # ---- 5. Break of structure: candle CLOSE beyond latest swing ----
        if st.swing_highs:
            sh_idx, sh_px = st.swing_highs[-1]
            if c[t] > sh_px and not _broken(st, "bull", sh_idx):
                kind = "CHoCH" if st.trend == "bear" else "BOS"
                st.events.append(Event(kind, "bull", t, sh_px))
                st.trend = "bull"
                _mark_broken(st, "bull", sh_idx)
                _new_setup(st, "bull", t, sh_idx, sh_px, o, h, l, c, a, cfg, htf_trend, df)
        if st.swing_lows:
            sl_idx, sl_px = st.swing_lows[-1]
            if c[t] < sl_px and not _broken(st, "bear", sl_idx):
                kind = "CHoCH" if st.trend == "bull" else "BOS"
                st.events.append(Event(kind, "bear", t, sl_px))
                st.trend = "bear"
                _mark_broken(st, "bear", sl_idx)
                _new_setup(st, "bear", t, sl_idx, sl_px, o, h, l, c, a, cfg, htf_trend, df)

        # remove fully consumed liquidity so lists stay small
        open_highs = [lv for lv in open_highs if not lv[2] and h[t] <= lv[1]]
        open_lows = [lv for lv in open_lows if not lv[2] and l[t] >= lv[1]]

        # ---- 6. manage setups ----
        for s in st.setups:
            if s.created < t:
                _manage(s, t, h[t], l[t], c[t], cfg)

    return st


def _broken(st: State, side: str, idx: int) -> bool:
    return (side, idx) in st.broken


def _mark_broken(st: State, side: str, idx: int) -> None:
    st.broken.add((side, idx))


def _new_setup(st, side, t, swing_idx, level, o, h, l, c, a, cfg, htf_trend, df):
    # leg origin = extreme between broken swing and BOS candle
    seg = slice(swing_idx, t + 1)
    if side == "bull":
        origin = swing_idx + int(np.argmin(l[seg]))
        # OB = last bearish candle at/before the origin
        ob_i = next((i for i in range(origin, max(origin - cfg.ob_search, 0) - 1, -1)
                     if c[i] < o[i]), origin)
        top, bot = h[ob_i], min(l[ob_i], l[origin])
    else:
        origin = swing_idx + int(np.argmax(h[seg]))
        ob_i = next((i for i in range(origin, max(origin - cfg.ob_search, 0) - 1, -1)
                     if c[i] > o[i]), origin)
        top, bot = max(h[ob_i], h[origin]), l[ob_i]

    if top - bot > cfg.max_zone_atr * a[t] or top <= bot:
        return
    ob = OB(side, top, bot, ob_i)
    st.obs.append(ob)

    # liquidity sweep that formed the leg origin
    sweep_side = side  # bull setup needs sell-side sweep (event side "bull")
    # liquidity sweep at the leg origin (stop hunt -> displacement -> BOS)
    sw_idx, sw_level = _find_sweep(st, side, origin, t, h, l, cfg)
    if sw_idx is None:
        if cfg.sweep_mode != "off":
            return
        sw_idx, sw_level = origin, (l[origin] if side == "bull" else h[origin])
    ext_i = sw_idx if cfg.sweep_mode == "recent" else origin
    sweep_ext = l[ext_i] if side == "bull" else h[ext_i]

    # FVG confluence: an unfilled FVG created in the impulse leg, near the OB
    fvg_ok = any(g.side == side and not g.filled and origin <= g.idx <= t
                 and g.bottom <= top + a[t] and g.top >= bot - a[t]
                 for g in st.fvgs)
    if cfg.require_fvg and not fvg_ok:
        return

    buf = cfg.sl_buffer_atr * a[t]
    entry = (top + bot) / 2  # 50% of the order block
    if side == "bull":
        sl = (min(bot, sweep_ext) if cfg.sl_mode == "sweep" else bot) - buf
        risk = entry - sl
        leg_high = h[origin:t + 1].max()
        tp1 = entry + 2 * risk
        tp2 = max(leg_high, entry + cfg.min_rr_tp2 * 1.5 * risk)
    else:
        sl = (max(top, sweep_ext) if cfg.sl_mode == "sweep" else top) + buf
        risk = sl - entry
        leg_low = l[origin:t + 1].min()
        tp1 = entry - 2 * risk
        tp2 = min(leg_low, entry - cfg.min_rr_tp2 * 1.5 * risk)
    if risk <= 0 or risk > cfg.max_risk_atr * a[t]:
        return

    htf = None
    if htf_trend is not None:
        b = htf_trend.asof(df.index[t])
        htf = (b == side) if isinstance(b, str) else None

    st.setups.append(Setup("BUY" if side == "bull" else "SELL", t, top, bot, entry, sl,
                           tp1, tp2, sw_idx, sw_level, level, fvg_ok, htf))
    # newer setup on the same side replaces older pending ones
    for s in st.setups[:-1]:
        if s.status == "PENDING" and s.side == st.setups[-1].side:
            s.status = "REPLACED"


def _find_sweep(st, side, origin, t, h, l, cfg):
    """Return (idx, level) of liquidity taken by the leg's origin, else (None, None)."""
    if cfg.sweep_mode == "wick":
        ev = [e for e in st.events if e.kind == "SWEEP" and e.side == side
              and abs(e.idx - origin) <= cfg.sweep_origin_bars]
        return (ev[-1].idx, ev[-1].price) if ev else (None, None)
    if cfg.sweep_mode == "recent":
        ev = [e for e in st.events if e.kind == "SWEEP" and e.side == side
              and t - cfg.sweep_lookback <= e.idx <= t]
        return (ev[-1].idx, ev[-1].price) if ev else (None, None)
    if cfg.sweep_mode == "take":
        pool = st.swing_lows if side == "bull" else st.swing_highs
        for idx, px in reversed(pool):
            if idx >= origin - cfg.swing_len or idx < origin - cfg.sweep_lookback:
                continue
            seg = l[idx + 1:origin] if side == "bull" else h[idx + 1:origin]
            untouched = len(seg) == 0 or (seg.min() >= px if side == "bull" else seg.max() <= px)
            taken = l[origin] < px if side == "bull" else h[origin] > px
            if untouched and taken:
                return origin, px
    return None, None


def _manage(s: Setup, t, hi, lo, cl, cfg: Config) -> None:
    buy = s.side == "BUY"
    if s.status == "PENDING":
        if t - s.created > cfg.setup_expiry:
            s.status = "EXPIRED"
            return
        # price ran to TP1 without retracing -> missed
        if (buy and hi >= s.tp1) or (not buy and lo <= s.tp1):
            s.status = "MISSED"
            return
        touched = lo <= s.entry if buy else hi >= s.entry
        if touched:
            s.status, s.fill_idx = "FILLED", t
            # same-bar stop (conservative)
            if (buy and lo <= s.sl) or (not buy and hi >= s.sl):
                s.status, s.exit_idx, s.result_r = "LOSS", t, -1.0
        return
    if s.status == "FILLED":
        stop = s.entry if s.tp1_hit else s.sl  # move SL to BE after TP1
        if (buy and lo <= stop) or (not buy and hi >= stop):
            s.exit_idx = t
            if s.tp1_hit:
                s.status, s.result_r = "WIN", 1.0   # half closed at 2R, rest BE
            else:
                s.status, s.result_r = "LOSS", -1.0
            return
        if not s.tp1_hit and ((buy and hi >= s.tp1) or (not buy and lo <= s.tp1)):
            s.tp1_hit = True
        if (buy and hi >= s.tp2) or (not buy and lo <= s.tp2):
            s.exit_idx = t
            s.status = "WIN"
            s.result_r = 0.5 * 2.0 + 0.5 * abs(s.tp2 - s.entry) / s.risk


def trend_series(df: pd.DataFrame, cfg: Config | None = None) -> pd.Series:
    """Per-bar structure trend ('bull'/'bear'/'none') for higher-timeframe bias."""
    st = run(df, cfg)
    trend = pd.Series("none", index=df.index, dtype=object)
    for e in st.events:
        if e.kind in ("BOS", "CHoCH"):
            trend.iloc[e.idx:] = e.side
    # a bar's trend is only known once it closes -> shift by one bar
    return trend.shift(1).fillna("none")
