#!/usr/bin/env python3
"""Build the public website from dashboard.html (the same page the claude.ai dashboard uses).

    python tools/build_site.py --out _site

Pages:
  index.html  Gold (XAUUSD)    data in data/      (reports/bundle.json, research/scalp_research.json)
  btc.html    Bitcoin (BTCUSD) data in data/btc/  (reports/btc/bundle.json, research/btc_model_check.json)
Both pages are dashboard.html wrapped in a full HTML document with the runtime shim (site/dash.js),
per-asset settings (window.GR_*), and for Bitcoin a bolder palette with glass tabs.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BASE_CSS = """
  :root {
    --cds-gap-xs: 4px; --cds-gap-sm: 8px; --cds-gap-md: 16px; --cds-gap-lg: 24px; --cds-gap-xl: 32px;
    --cds-pad-sm: 8px; --cds-pad-md: 14px; --cds-pad-lg: 20px; --cds-radius: 10px;
    --cds-font-size-caption: 12px; --cds-font-size-body: 15px; --cds-font-size-heading: 17px; --cds-font-size-title: 28px;
    --cds-font-weight-medium: 500;
    --font-anthropic-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, "Helvetica Neue", Arial, sans-serif;
    --font-anthropic-serif: Georgia, "Times New Roman", serif;
    color-scheme: dark;
  }
  html, body { margin: 0; background: var(--site-bg); }
  body { padding: max(12px, env(safe-area-inset-top)) max(12px, env(safe-area-inset-right)) max(12px, env(safe-area-inset-bottom)) max(12px, env(safe-area-inset-left)); }
  #dash-root { max-width: 1180px; margin: 0 auto; }
  @media (max-width: 640px) { html, body { background: var(--site-bg-m); } body { padding: 8px; } :root { color-scheme: light; } }

  /* market switcher: frosted glass pill above the dashboard */
  .assets { max-width: 1180px; margin: 0 auto 12px; display: flex; justify-content: center; }
  .assets nav { display: inline-flex; gap: 4px; padding: 5px; border-radius: 999px; background: rgba(255,255,255,.07);
    border: 1px solid rgba(255,255,255,.16); backdrop-filter: blur(18px) saturate(160%); -webkit-backdrop-filter: blur(18px) saturate(160%);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.15), 0 8px 28px rgba(0,0,0,.35); }
  .assets a { font: 600 13px var(--font-anthropic-sans); color: rgba(255,255,255,.78); text-decoration: none; padding: 9px 16px; border-radius: 999px; white-space: nowrap; }
  .assets a:hover { color: #fff; }
  .assets a[aria-current="page"] { color: #fff; background: var(--site-pick); box-shadow: 0 6px 20px var(--site-glow), inset 0 1px 0 rgba(255,255,255,.35); }
  .assets a:focus-visible { outline: 2px solid #fff; outline-offset: 2px; }
  @media (max-width: 640px) {
    .assets nav { background: rgba(255,255,255,.55); border-color: rgba(255,255,255,.85); box-shadow: inset 0 1px 0 #fff, 0 8px 24px rgba(20,19,23,.10); }
    .assets a { color: #3a3942; padding: 9px 13px; }
    .assets a[aria-current="page"] { color: #fff; }
  }
"""

# Bitcoin: bold black/orange/magenta palette and glass tabs (overrides the .gr tokens of dashboard.html)
BTC_CSS = """
  .gr.btc {
    --gr-bg: #060608;
    --gr-bg-img: radial-gradient(900px 480px at 88% -12%, rgba(255,122,26,.34) 0%, transparent 62%), radial-gradient(800px 420px at -8% 108%, rgba(255,46,126,.26) 0%, transparent 58%);
    --gr-card: rgba(255,255,255,.035); --gr-card-solid: #111115; --gr-line: #26262f;
    --gr-fg: #fbfbfd; --gr-muted: #a2a2b3; --gr-em: #ffb35c;
    --gr-accent: #ff8a1f; --gr-accent-ink: #160800;
    --gr-lav: linear-gradient(150deg, #ff9a2e 0%, #ff4f5e 62%, #e0328f 100%); --gr-lav-fg: #170700; --gr-lav-muted: rgba(23,7,0,.72);
    --gr-lav-bar: rgba(23,7,0,.28); --gr-lav-bar-hi: #170700;
    --gr-glass: linear-gradient(180deg, #2c1a10 0%, #17110f 52%, #09090b 100%); --gr-glass-card: rgba(255,255,255,.06); --gr-glass-line: rgba(255,255,255,.15);
    --gr-glass-fg: #ffffff; --gr-glass-muted: rgba(255,255,255,.65); --gr-glass-ok: #ff8a1f;
    --gr-up: #00e2a0; --gr-dn: #ff3d71; --gr-wait: #9aa4ff; --gr-off: #5e5e6c;
    --gr-seg: rgba(255,255,255,.06); --gr-seg-on: #ff8a1f; --gr-seg-on-fg: #160800; --gr-cursor: #ff8a1f;
  }
  .gr.btc .gr-hello b { background: linear-gradient(90deg, #ffb35c, #ff7a1a 45%, #ff3d71); -webkit-background-clip: text; background-clip: text; color: transparent; }
  .gr.btc .gr-island { border-color: rgba(255,138,31,.35); }
  .gr.btc .gr-isl-sym { color: #ff8a1f; }

  /* glass tabs */
  .gr.btc .gr-seg { position: sticky; top: 62px; z-index: 5; background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.14);
    backdrop-filter: blur(18px) saturate(170%); -webkit-backdrop-filter: blur(18px) saturate(170%);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.14), 0 12px 34px rgba(0,0,0,.45); }
  .gr.btc .gr-seg button { color: rgba(255,255,255,.82); }
  .gr.btc .gr-seg button:hover { background: rgba(255,255,255,.07); }
  .gr.btc .gr-seg button[aria-selected="true"] { color: #fff; background: linear-gradient(135deg, rgba(255,138,31,.95), rgba(255,61,113,.92));
    box-shadow: 0 6px 22px rgba(255,106,43,.45), inset 0 1px 0 rgba(255,255,255,.4); }
  .gr.btc .gr-panel, .gr.btc .gr-vital:not(.lav) { backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); }
  .gr.btc .gr-score .gr-cardbtn { box-shadow: 0 8px 26px rgba(255,79,94,.45); }

  @media (max-width: 640px) {
    .gr.btc {
      --gr-bg: #eeebe5; --gr-bg-img: radial-gradient(500px 300px at 100% 0%, rgba(255,138,31,.22), transparent 70%);
      --gr-card: rgba(255,255,255,.78); --gr-card-solid: #ffffff; --gr-line: rgba(14,14,16,.07);
      --gr-fg: #0e0e10; --gr-muted: #72707a; --gr-em: #e2550a;
      --gr-accent: #ff7a1a; --gr-accent-ink: #160800;
      --gr-glass: linear-gradient(180deg, #3b2a20 0%, #1d1715 52%, #0b0a0c 100%); --gr-glass-ok: #ff8a1f;
      --gr-up: #0f9b69; --gr-dn: #e5334f; --gr-wait: #5b5fd6; --gr-off: #a3a1aa;
      --gr-chart-bg: #f7f6f3; --gr-grid: rgba(14,14,16,.07); --gr-tip: #0e0e10; --gr-tip-fg: #ffffff;
      --gr-seg: rgba(255,255,255,.55); --gr-seg-on: #0e0e10; --gr-seg-on-fg: #ffffff; --gr-cursor: #0e0e10;
    }
    .gr.btc .gr-seg { top: 58px; background: rgba(255,255,255,.55); border-color: rgba(255,255,255,.9);
      box-shadow: inset 0 1px 0 #fff, 0 10px 28px rgba(14,14,16,.10); }
    .gr.btc .gr-seg button { color: #2c2b31; }
    .gr.btc .gr-seg button[aria-selected="true"] { color: #fff; }
    .gr.btc .gr-nav { background: rgba(255,255,255,.62); backdrop-filter: blur(18px) saturate(170%); -webkit-backdrop-filter: blur(18px) saturate(170%);
      border: 1px solid rgba(255,255,255,.9); }
    .gr.btc .gr-nav button[aria-selected="true"] { background: linear-gradient(135deg, #ff8a1f, #ff3d71); color: #fff; }
    .gr.btc .gr-navlime { background: linear-gradient(135deg, #ff8a1f, #ff3d71); color: #fff; box-shadow: 0 10px 28px rgba(255,79,94,.4); }
  }
"""

PAGES = {
    "XAU": {
        "file": "index.html", "data": "data/", "bundle": "reports/bundle.json", "research": "research/scalp_research.json",
        "title": "Gold SMC Radar", "nav": "Gold · XAUUSD",
        "desc": "Gold (XAUUSD) Smart Money Concepts radar: H1 swing and M15 scalp signals with a live success tracker. Not financial advice.",
        "theme": "#120a22", "site_bg": "#0b0616", "site_bg_m": "#e4e4ea",
        "pick": "linear-gradient(135deg, #e3bb55, #b98a2c)", "glow": "rgba(227,187,85,.35)",
        "settings": "window.GR_EVERY_MIN = 15; window.GR_DATA = 'data/';",
        "css": "", "replace": [("Updated every hour, not every tick.", "Updated every 15 minutes, not every tick.")],
    },
    "BTC": {
        "file": "btc.html", "data": "data/btc/", "bundle": "reports/btc/bundle.json", "research": "research/btc_model_check.json",
        "title": "Bitcoin SMC Radar", "nav": "Bitcoin · BTCUSD",
        "desc": "Bitcoin (BTCUSD) Smart Money Concepts radar: H1 swing and M15 scalp signals with a live success tracker. Not financial advice.",
        "theme": "#060608", "site_bg": "#040405", "site_bg_m": "#e7e3dc",
        "pick": "linear-gradient(135deg, #ff8a1f, #ff3d71)", "glow": "rgba(255,106,43,.45)",
        "settings": ("window.GR_EVERY_MIN = 15; window.GR_DATA = 'data/btc/'; window.GR_SYM = 'BTC'; window.GR_TICKER = 'BTCUSD';"
                     " window.GR_PIP = 1; window.GR_UNIT = 'USD'; window.GR_FILTER = false; window.GR_WEEKEND = true;"),
        "css": BTC_CSS,
        "replace": [
            ('class="gr" lang="en"', 'class="gr btc" lang="en"'),
            ('aria-label="Gold status. Press for details"', 'aria-label="Bitcoin status. Press for details"'),
            ('<div class="gr-avatar" aria-hidden="true">XAU</div>', '<div class="gr-avatar" aria-hidden="true">BTC</div>'),
            ('Trade smart,<br><b>Gold Radar!</b>', 'Trade bold,<br><b>Bitcoin Radar!</b>'),
            ('<span class="lab">Hit +100 pips</span>', '<span class="lab">Hit +$150</span>'),
            ('24-hour price moves (pips)', '24-hour price moves ($)'),
            ('Success = +100 pips before SL', 'Success = +$150 before SL'),
            ('"Passes filter" = on the right side of the daily EMA 200 and 1H ADX &gt; 20.',
             'Bitcoin uses no swing filter: none of the tested filters improved its 2-year results.'),
            ('<span class="lab">Passes filter</span>', '<span class="lab">With gold\'s filter</span>'),
            ('The daily EMA 200 + ADX &gt; 20 filter takes fewer trades but raises the average per trade and cuts drawdown.',
             'On Bitcoin the gold filter (daily EMA 200 + ADX &gt; 20) made results worse, so it is shown only for comparison.'),
            ('moved <b>100 pips ($10)</b>', 'moved <b>$150</b>'),
            ('+100 pips first', '+$150 first'),
            ('data-field="chg_pips">Move (pips)', 'data-field="chg_pips">Move ($)'),
            ('data-field="best_pips">Best pips', 'data-field="best_pips">Best move ($)'),
            ('<h2>Why this strategy</h2>', '<h2>Bitcoin model check</h2>'),
            ('Fixed research · 18 Nov 2026', 'Fixed check · 21 Nov 2026'),
            ('data-field="test_r">Test R', 'data-field="test_r">Total R'),
            ('. 1 pip = $0.10, so 100 pips = $10 of price movement, and $ risk per 0.01 lot = stop distance in points. Updated every hour, not every tick.',
             '. Success = a $150 move in the trade\'s favour. $ risk per 0.01 lot = stop distance × 0.01 (0.01 BTC). Bitcoin trades 24/7, so this page also updates at weekends, every 15 minutes.'),
        ],
    },
}

MANIFEST = """{
  "name": "SMC Radar",
  "short_name": "SMC Radar",
  "start_url": "./",
  "display": "standalone",
  "background_color": "#120a22",
  "theme_color": "#120a22",
  "icons": [{ "src": "icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable" }]
}
"""

ICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
<rect width="512" height="512" rx="112" fill="#120a22"/>
<circle cx="256" cy="256" r="150" fill="none" stroke="#e3bb55" stroke-width="10" stroke-dasharray="4 22"/>
<circle cx="256" cy="256" r="104" fill="#3b2a6e"/>
<circle cx="362" cy="150" r="22" fill="#dcf24b"/>
<text x="256" y="282" text-anchor="middle" font-family="Arial, sans-serif" font-weight="700" font-size="74" fill="#f6dc92">XAU</text>
</svg>
"""
ICON_BTC = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ff9a2e"/><stop offset="1" stop-color="#ff3d71"/></linearGradient></defs>
<rect width="512" height="512" rx="112" fill="#060608"/>
<circle cx="256" cy="256" r="150" fill="none" stroke="url(#g)" stroke-width="10" stroke-dasharray="4 22"/>
<circle cx="256" cy="256" r="104" fill="url(#g)"/>
<text x="256" y="282" text-anchor="middle" font-family="Arial, sans-serif" font-weight="800" font-size="74" fill="#160800">BTC</text>
</svg>
"""


def page_html(key: str, body: str) -> str:
    p = PAGES[key]
    for a, b in p["replace"]:
        if a not in body:
            raise SystemExit(f"build_site: text to replace not found for {key}: {a[:60]}")
        body = body.replace(a, b)
    cur = ' aria-current="page"'
    links = "".join(
        f'<a href="{"./" if q["file"] == "index.html" else q["file"]}"{cur if k == key else ""}>{q["nav"]}</a>'
        for k, q in PAGES.items())
    icon = "icon.svg" if key == "XAU" else "icon-btc.svg"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{p["title"]}</title>
<meta name="description" content="{p["desc"]}">
<meta name="theme-color" content="{p["theme"]}">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="{icon}" type="image/svg+xml">
<link rel="apple-touch-icon" href="{icon}">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="{p["title"].replace(" SMC", "")}">
<style>
  :root {{ --site-bg: {p["site_bg"]}; --site-bg-m: {p["site_bg_m"]}; --site-pick: {p["pick"]}; --site-glow: {p["glow"]}; }}
{BASE_CSS}
{p["css"]}
</style>
<script>{p["settings"]}</script>
<script src="d3.min.js"></script>
<script src="dash.js"></script>
</head>
<body>
<div class="assets"><nav aria-label="Markets">{links}</nav></div>
<div id="dash-root">
{body}
</div>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_site")
    args = ap.parse_args()
    out = ROOT / args.out
    page = (ROOT / "dashboard.html").read_text()
    for key, p in PAGES.items():
        (out / p["data"]).mkdir(parents=True, exist_ok=True)
        (out / p["file"]).write_text(page_html(key, page))
        shutil.copy(ROOT / p["research"], out / p["data"] / "research.json")
        bundle = ROOT / p["bundle"]
        if bundle.exists():
            shutil.copy(bundle, out / p["data"] / "bundle.json")
        else:
            print(f"warning: {bundle} missing, {p['file']} will show 'failed to load' until the next scan")
    shutil.copy(ROOT / "site" / "dash.js", out / "dash.js")
    shutil.copy(ROOT / "vendor" / "lwc.js", out / "lwc.js")
    shutil.copy(ROOT / "vendor" / "d3.min.js", out / "d3.min.js")
    (out / "manifest.webmanifest").write_text(MANIFEST)
    (out / "icon.svg").write_text(ICON)
    (out / "icon-btc.svg").write_text(ICON_BTC)
    (out / ".nojekyll").write_text("")
    print(f"site → {out}")


if __name__ == "__main__":
    main()
