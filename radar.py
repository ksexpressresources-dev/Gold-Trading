#!/usr/bin/env python3
"""Combined gold radar: H1 swing scan + M15 scalp scan + signal tracking in one bundle.

Usage:
    python radar.py                       # writes reports/bundle.json
    python radar.py --out reports/bundle.json

The bundle is one JSON object; each key is one dashboard dataset:
  candles setups levels summary analogs            (H1 swing, from scan.py)
  s_candles s_signals s_levels s_trades s_summary   (M15 scalp, from scalp.py)
  t_log t_hourly t_daily t_summary                  (tracking, smc/tracking.py)
Exit code 2 = a swing ENTRY TRIGGER or a fresh scalp ENTRY.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from smc import data, engine, scalp, tracking
from smc.indicators import Filters

ROOT = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/bundle.json")
    args = ap.parse_args()
    tmp = ROOT / "reports"
    codes = {}
    for script, out in (("scan.py", "dash"), ("scalp.py", "scalp")):
        p = subprocess.run([sys.executable, str(ROOT / script), "--dash", str(tmp / out)],
                           cwd=ROOT, capture_output=True, text=True)
        if p.returncode not in (0, 2):
            print(p.stdout, p.stderr, file=sys.stderr)
            raise SystemExit(f"{script} failed")
        codes[script] = p.returncode
        print(p.stdout)

    bundle = {}
    for k in ("candles", "setups", "levels", "summary", "analogs"):
        bundle[k] = json.loads((tmp / "dash" / f"gold_{k}.json").read_text())
    for k in ("candles", "signals", "levels", "trades", "summary"):
        bundle["s_" + k] = json.loads((tmp / "scalp" / f"scalp_{k}.json").read_text())

    # tracking: rebuild every signal of both models and judge it
    h1 = data.drop_unclosed(data.fetch(data.SPOT, "1h"), "1h")
    d1 = data.drop_unclosed(data.fetch(data.SPOT, "1d"), "1d")
    m15 = data.drop_unclosed(data.fetch(data.SPOT, "15m"), "15m")
    cfg = engine.Config()
    st = engine.run(h1, cfg, engine.trend_series(d1, cfg))
    filt = Filters(d1, h1)
    now = pd.Timestamp.now(tz="UTC")
    since = now - pd.Timedelta(days=15)
    sw = tracking.swing_signals(h1, st, filt, since)
    sc = tracking.scalp_signals(m15, scalp.run(m15, h1, d1)["rows"], since)
    log, hourly, daily = tracking.build(h1, m15, sw, sc, now)
    bundle["t_log"], bundle["t_hourly"], bundle["t_daily"] = log, hourly, daily

    week = now - pd.Timedelta(days=7)
    summ = {"generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "source": data.source(), "success_pips": tracking.SUCCESS_PIPS,
            "pip": tracking.PIP}
    for m, rows in (("h1", sw), ("m15", sc)):
        w = [r for r in rows if r["time"] >= week]
        s_, f_ = sum(r["status"] == "SUCCESS" for r in w), sum(r["status"] == "FAIL" for r in w)
        summ[f"{m}_7d_entries"] = sum(r["status"] in ("SUCCESS", "FAIL", "RUNNING") for r in w)
        summ[f"{m}_7d_success"] = s_
        summ[f"{m}_7d_fail"] = f_
        summ[f"{m}_7d_rate"] = round(100 * s_ / (s_ + f_), 0) if s_ + f_ else None
        summ[f"{m}_running"] = sum(r["status"] == "RUNNING" for r in rows)
        summ[f"{m}_waiting"] = sum(r["status"] == "WAITING" for r in rows)
    all_w = [r for r in sw + sc if r["time"] >= week]
    s_, f_ = sum(r["status"] == "SUCCESS" for r in all_w), sum(r["status"] == "FAIL" for r in all_w)
    summ["all_7d_rate"] = round(100 * s_ / (s_ + f_), 0) if s_ + f_ else None
    summ["all_7d_entries"] = sum(r["status"] in ("SUCCESS", "FAIL", "RUNNING") for r in all_w)
    summ["active"] = summ["h1_running"] + summ["h1_waiting"] + summ["m15_running"] + summ["m15_waiting"]
    last = hourly[0] if hourly else {}
    summ["last_hour"] = last.get("hour")
    summ["last_hour_h1"] = last.get("h1_status")
    summ["last_hour_m15"] = last.get("m15_status")
    bundle["t_summary"] = [summ]

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, separators=(",", ":")))
    print(f"bundle → {out} ({out.stat().st_size // 1024} KB)")
    print(json.dumps(summ, indent=1))
    return 2 if 2 in codes.values() else 0


if __name__ == "__main__":
    sys.exit(main())
