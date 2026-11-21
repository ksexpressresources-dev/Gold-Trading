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
  .embedded .assets { display: none; }
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

# WTI: ocean palette (petrol, aqua, deep blue) and liquid-glass "water drop" tabs
WTI_CSS = """
  .gr.wti {
    --gr-bg: #03121a;
    --gr-bg-img: radial-gradient(900px 480px at 85% -12%, rgba(0,194,209,.30) 0%, transparent 62%), radial-gradient(800px 420px at -8% 108%, rgba(43,89,255,.26) 0%, transparent 58%);
    --gr-card: rgba(255,255,255,.04); --gr-card-solid: #0a1d26; --gr-line: #173441;
    --gr-fg: #f2fbfd; --gr-muted: #8fb3bf; --gr-em: #7ff3e8;
    --gr-accent: #23d5c4; --gr-accent-ink: #00201c;
    --gr-lav: linear-gradient(150deg, #6af0e6 0%, #1fb3d1 55%, #2b6bff 100%); --gr-lav-fg: #00171d; --gr-lav-muted: rgba(0,23,29,.7);
    --gr-lav-bar: rgba(0,23,29,.28); --gr-lav-bar-hi: #00171d;
    --gr-glass: linear-gradient(180deg, #0f3a48 0%, #0a2230 52%, #050e14 100%); --gr-glass-card: rgba(255,255,255,.07); --gr-glass-line: rgba(255,255,255,.16);
    --gr-glass-fg: #ffffff; --gr-glass-muted: rgba(255,255,255,.68); --gr-glass-ok: #5ee7df;
    --gr-up: #2ee59d; --gr-dn: #ff5c7a; --gr-wait: #8fb4ff; --gr-off: #557380;
    --gr-seg: rgba(255,255,255,.06); --gr-seg-on: #23d5c4; --gr-seg-on-fg: #00201c; --gr-cursor: #5ee7df;
  }
  .gr.wti .gr-hello b { background: linear-gradient(90deg, #a6fff6, #23d5c4 45%, #2b8bff); -webkit-background-clip: text; background-clip: text; color: transparent; }
  .gr.wti .gr-island { border-color: rgba(94,231,223,.35); }
  .gr.wti .gr-isl-sym { color: #5ee7df; }
  .gr.wti .gr-score .gr-cardbtn { box-shadow: 0 8px 26px rgba(31,179,209,.45); }

  /* liquid glass tabs with a droplet for the chosen one */
  .gr.wti .gr-seg { position: sticky; top: 62px; z-index: 5; overflow: hidden;
    background: linear-gradient(180deg, rgba(255,255,255,.16), rgba(255,255,255,.05)); border: 1px solid rgba(255,255,255,.26);
    backdrop-filter: blur(24px) saturate(190%) brightness(1.06); -webkit-backdrop-filter: blur(24px) saturate(190%) brightness(1.06);
    box-shadow: inset 0 1.5px 1px rgba(255,255,255,.5), inset 0 -2px 6px rgba(0,0,0,.22), 0 12px 34px rgba(0,0,0,.4); }
  .gr.wti .gr-seg button, .gr.wti .gr-nav button { position: relative; overflow: hidden; color: rgba(255,255,255,.84); }
  .gr.wti .gr-seg button[aria-selected="true"], .gr.wti .gr-nav button[aria-selected="true"] { color: #00171d;
    background: radial-gradient(120% 160% at 28% 18%, rgba(255,255,255,.7) 0%, rgba(255,255,255,.12) 38%, rgba(255,255,255,0) 60%), linear-gradient(135deg, #6af0e6, #1fa6d6);
    box-shadow: inset 0 2px 3px rgba(255,255,255,.8), inset 0 -4px 10px rgba(0,40,60,.3), 0 8px 22px rgba(46,200,220,.45); }
  .gr.wti .gr-seg button[aria-selected="true"].drop-in { animation: grwobble .6s cubic-bezier(.34,1.56,.64,1); }
  @keyframes grwobble { 0% { transform: scale(1, 1); } 30% { transform: scale(1.12, .86); } 60% { transform: scale(.96, 1.05); } 100% { transform: scale(1, 1); } }
  .gr-ripple { position: absolute; border-radius: 50%; pointer-events: none; width: 14px; height: 14px; margin: -7px 0 0 -7px; z-index: 0;
    background: radial-gradient(circle, rgba(255,255,255,.6) 0%, rgba(255,255,255,.18) 45%, rgba(255,255,255,0) 70%);
    box-shadow: 0 0 0 1.5px rgba(255,255,255,.45); animation: grripple .7s ease-out forwards; }
  @keyframes grripple { from { transform: scale(0); opacity: .9; } to { transform: scale(12); opacity: 0; } }
  @media (prefers-reduced-motion: reduce) { .gr.wti .gr-seg button.drop-in { animation: none; } .gr-ripple { display: none; } }

  @media (max-width: 640px) {
    .gr.wti {
      --gr-bg: #e6f2f3; --gr-bg-img: radial-gradient(500px 300px at 100% 0%, rgba(35,213,196,.22), transparent 70%);
      --gr-card: rgba(255,255,255,.8); --gr-card-solid: #ffffff; --gr-line: rgba(10,26,32,.07);
      --gr-fg: #0a1a20; --gr-muted: #5f7a83; --gr-em: #0b7f8c;
      --gr-accent: #12b5a6; --gr-accent-ink: #00201c;
      --gr-lav: linear-gradient(150deg, #c2f6f1 0%, #7fd9ea 60%, #8fb0ff 100%); --gr-lav-fg: #00171d;
      --gr-glass: linear-gradient(180deg, #2c5b6a 0%, #173845 52%, #08161d 100%);
      --gr-up: #0c9a64; --gr-dn: #e23d5d; --gr-wait: #4f6bd6; --gr-off: #98abb1;
      --gr-chart-bg: #f3f9fa; --gr-grid: rgba(10,26,32,.07); --gr-tip: #0a1a20; --gr-tip-fg: #ffffff;
      --gr-seg: rgba(255,255,255,.6); --gr-cursor: #0a1a20;
    }
    .gr.wti .gr-seg { top: 58px; background: linear-gradient(180deg, rgba(255,255,255,.8), rgba(255,255,255,.5)); border-color: rgba(255,255,255,.95);
      box-shadow: inset 0 1.5px 1px #fff, inset 0 -2px 6px rgba(10,26,32,.08), 0 10px 28px rgba(10,26,32,.12); }
    .gr.wti .gr-seg button, .gr.wti .gr-nav button { color: #24383f; }
    .gr.wti .gr-nav { background: linear-gradient(180deg, rgba(255,255,255,.8), rgba(255,255,255,.55));
      backdrop-filter: blur(20px) saturate(180%); -webkit-backdrop-filter: blur(20px) saturate(180%); border: 1px solid rgba(255,255,255,.95); }
    .gr.wti .gr-navlime { color: #00171d; background: radial-gradient(120% 160% at 28% 18%, rgba(255,255,255,.7), rgba(255,255,255,0) 55%), linear-gradient(135deg, #6af0e6, #1fa6d6);
      box-shadow: inset 0 2px 3px rgba(255,255,255,.8), 0 10px 26px rgba(31,166,214,.4); }
    .gr-ripple { background: radial-gradient(circle, rgba(255,255,255,.95) 0%, rgba(120,210,225,.3) 45%, rgba(255,255,255,0) 70%); box-shadow: 0 0 0 1.5px rgba(60,160,185,.35); }
  }
"""

# tap ripple + droplet wobble on the in-page tabs (WTI page)
WTI_JS = """<script>
  (() => {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    document.querySelectorAll('.gr.wti .gr-seg button, .gr.wti .gr-nav button, .gr.wti .gr-navlime').forEach((b) => {
      b.addEventListener('pointerdown', (e) => {
        const r = b.getBoundingClientRect(), dot = document.createElement('span');
        dot.className = 'gr-ripple'; dot.style.left = (e.clientX - r.left) + 'px'; dot.style.top = (e.clientY - r.top) + 'px';
        b.append(dot); dot.addEventListener('animationend', () => dot.remove());
      });
      b.addEventListener('click', () => { b.classList.remove('drop-in'); void b.offsetWidth; b.classList.add('drop-in'); });
    });
  })();
</script>"""

PAGES = {
    "XAU": {
        "file": "gold.html", "data": "data/", "bundle": "reports/bundle.json", "research": "research/scalp_research.json",
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
    "WTI": {
        "file": "wti.html", "data": "data/wti/", "bundle": "reports/wti/bundle.json", "research": "research/wti_model_check.json",
        "title": "WTI Oil SMC Radar", "nav": "WTI · Crude oil",
        "desc": "WTI crude oil Smart Money Concepts radar: H1 swing and M15 scalp signals with a live success tracker. Not financial advice.",
        "theme": "#03121a", "site_bg": "#020c12", "site_bg_m": "#dcebee",
        "pick": "linear-gradient(135deg, #5ee7df, #1f8fd6)", "glow": "rgba(46,200,220,.45)",
        "settings": ("window.GR_EVERY_MIN = 15; window.GR_DATA = 'data/wti/'; window.GR_SYM = 'WTI'; window.GR_TICKER = 'WTI';"
                     " window.GR_PIP = 0.01; window.GR_UNIT = 'pips'; window.GR_FILTER = false;"),
        "css": WTI_CSS, "js": WTI_JS,
        "replace": [
            ('class="gr" lang="en"', 'class="gr wti" lang="en"'),
            ('aria-label="Gold status. Press for details"', 'aria-label="WTI crude oil status. Press for details"'),
            ('<div class="gr-avatar" aria-hidden="true">XAU</div>', '<div class="gr-avatar" aria-hidden="true">WTI</div>'),
            ('Trade smart,<br><b>Gold Radar!</b>', 'Trade fluid,<br><b>WTI Oil Radar!</b>'),
            ('<span class="lab">Hit +100 pips</span>', '<span class="lab">Hit +25 pips</span>'),
            ('Success = +100 pips before SL', 'Success = +25 pips before SL'),
            ('<p class="gr-note">Model: liquidity sweep',
             '<p class="gr-empty" style="border-color: var(--gr-dn); color: var(--gr-dn)">⚠ On WTI this H1 model lost money in testing '
             '(-33.5R over 2 years, both years negative). Treat H1 signals as information only and use the M15 scalp tab instead.</p>\n'
             '      <p class="gr-note">Model: liquidity sweep'),
            ('"Passes filter" = on the right side of the daily EMA 200 and 1H ADX &gt; 20.', 'WTI uses no swing filter.'),
            ('<span class="lab">Passes filter</span>', '<span class="lab">With gold\'s filter</span>'),
            ('The daily EMA 200 + ADX &gt; 20 filter takes fewer trades but raises the average per trade and cuts drawdown.',
             'On WTI this H1 model lost money over 2 years with or without the gold filter (daily EMA 200 + ADX &gt; 20).'),
            ('moved <b>100 pips ($10)</b>', 'moved <b>25 pips ($0.25)</b>'),
            ('+100 pips first', '+25 pips first'),
            ('<h2>Why this strategy</h2>', '<h2>WTI model check</h2>'),
            ('Fixed research · 18 Nov 2026', 'Fixed check · 21 Nov 2026'),
            ('data-field="test_r">Test R', 'data-field="test_r">Total R'),
            ('. 1 pip = $0.10, so 100 pips = $10 of price movement, and $ risk per 0.01 lot = stop distance in points. Updated every hour, not every tick.',
             '. 1 pip = $0.01, so 25 pips = $0.25 of price movement, and $ risk per 0.01 lot (10 barrels) = stop distance × 10. Updated every 15 minutes, not every tick.'),
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


SLUG = {"XAU": "gold", "BTC": "btc", "WTI": "wti"}

ICON_WTI = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
<defs><linearGradient id="w" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6af0e6"/><stop offset="1" stop-color="#2b6bff"/></linearGradient></defs>
<rect width="512" height="512" rx="112" fill="#03121a"/>
<circle cx="256" cy="256" r="150" fill="none" stroke="url(#w)" stroke-width="10" stroke-dasharray="4 22"/>
<path d="M256 120 C 300 190, 350 240, 350 300 A 94 94 0 0 1 162 300 C 162 240, 212 190, 256 120 Z" fill="url(#w)"/>
<text x="256" y="320" text-anchor="middle" font-family="Arial, sans-serif" font-weight="800" font-size="62" fill="#00171d">WTI</text>
</svg>
"""


def page_html(key: str, body: str) -> str:
    p = PAGES[key]
    for a, b in p["replace"]:
        if a not in body:
            raise SystemExit(f"build_site: text to replace not found for {key}: {a[:60]}")
        body = body.replace(a, b)
    cur = ' aria-current="page"'
    # standalone pages link to the combined page; inside it (an iframe) the switcher is hidden
    links = "".join(
        f'<a href="./#{SLUG[k]}" target="_top"{cur if k == key else ""}>{q["nav"]}</a>'
        for k, q in PAGES.items())
    icon = {"XAU": "icon.svg", "BTC": "icon-btc.svg", "WTI": "icon-wti.svg"}[key]
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
<script>{p["settings"]} if (window.top !== window.self) document.documentElement.classList.add("embedded");</script>
<script src="d3.min.js"></script>
<script src="dash.js"></script>
</head>
<body>
<div class="assets"><nav aria-label="Markets">{links}</nav></div>
<div id="dash-root">
{body}
</div>
{p.get("js", "")}
</body>
</html>
"""


SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>SMC Radar</title>
<meta name="description" content="Gold (XAUUSD), Bitcoin (BTCUSD) and WTI crude oil Smart Money Concepts radar: H1 swing and M15 scalp signals with a live success tracker. Not financial advice.">
<meta name="theme-color" content="#0b0616">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="icon.svg">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="SMC Radar">
<style>
  /* Layout: a liquid-glass market bar on top (a water droplet slides to the chosen market and ripples on tap);
     each market is its own full dashboard below, kept loaded for instant switching. */
  :root { --bar-h: 58px; --bg: #0b0616; --pick: linear-gradient(135deg, #f0cd6e, #b98a2c); --glow: rgba(227,187,85,.45); --ink: rgba(255,255,255,.8); }
  :root[data-asset="btc"] { --bg: #040405; --pick: linear-gradient(135deg, #ff9a2e, #ff3d71); --glow: rgba(255,106,43,.5); }
  :root[data-asset="wti"] { --bg: #03121a; --pick: linear-gradient(135deg, #5ee7df, #1f8fd6); --glow: rgba(46,200,220,.5); }
  @media (max-width: 640px) {
    :root { --bg: #e4e4ea; --ink: #34333b; }
    :root[data-asset="btc"] { --bg: #e7e3dc; } :root[data-asset="wti"] { --bg: #dcebee; }
  }
  html, body { margin: 0; height: 100%; background: var(--bg); transition: background .4s; overflow: hidden; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, Arial, sans-serif; }
  .bar { position: fixed; z-index: 10; top: 0; left: 0; right: 0; height: var(--bar-h);
    padding: calc(env(safe-area-inset-top, 0px) + 8px) max(10px, env(safe-area-inset-right)) 8px max(10px, env(safe-area-inset-left));
    display: flex; justify-content: center; align-items: center; box-sizing: content-box; pointer-events: none; }

  /* liquid glass: frosted, a bright rim on top, a darker one underneath, a soft drop shadow */
  .tabs { pointer-events: auto; position: relative; isolation: isolate; display: inline-flex; gap: 2px; padding: 6px; border-radius: 999px; overflow: hidden;
    background: linear-gradient(180deg, rgba(255,255,255,.20), rgba(255,255,255,.06));
    border: 1px solid rgba(255,255,255,.30);
    backdrop-filter: blur(24px) saturate(190%) brightness(1.08); -webkit-backdrop-filter: blur(24px) saturate(190%) brightness(1.08);
    box-shadow: inset 0 1.5px 1px rgba(255,255,255,.55), inset 0 -2px 6px rgba(0,0,0,.20), 0 14px 40px rgba(0,0,0,.38); }
  .tabs::before { content: ""; position: absolute; inset: 1px 12% auto; height: 45%; border-radius: 999px; z-index: 0; pointer-events: none;
    background: linear-gradient(180deg, rgba(255,255,255,.28), rgba(255,255,255,0)); }
  /* the droplet: a lens of colour with a specular highlight, sliding with a springy overshoot */
  .drop { position: absolute; z-index: 1; top: 6px; bottom: 6px; left: 6px; width: 0; border-radius: 999px; pointer-events: none;
    background: radial-gradient(120% 160% at 28% 18%, rgba(255,255,255,.62) 0%, rgba(255,255,255,.10) 38%, rgba(255,255,255,0) 60%), var(--pick);
    box-shadow: inset 0 2px 3px rgba(255,255,255,.75), inset 0 -4px 10px rgba(0,0,0,.28), 0 8px 24px var(--glow);
    transition: left .6s cubic-bezier(.34,1.56,.64,1), width .6s cubic-bezier(.34,1.56,.64,1), background .4s; }
  .drop.wobble { animation: wobble .6s cubic-bezier(.34,1.56,.64,1); }
  @keyframes wobble { 0% { transform: scale(1, 1); } 30% { transform: scale(1.14, .84); } 60% { transform: scale(.95, 1.06); } 100% { transform: scale(1, 1); } }
  .tabs button { position: relative; z-index: 2; font-weight: 600; font-size: 14px; font-family: inherit; color: var(--ink); background: transparent; border: 0; cursor: pointer;
    padding: 11px 18px; border-radius: 999px; white-space: nowrap; transition: color .3s; -webkit-tap-highlight-color: transparent; }
  .tabs button:hover { color: #fff; }
  .tabs button[aria-selected="true"] { color: #fff; text-shadow: 0 1px 2px rgba(0,0,0,.25); }
  .tabs button:focus-visible { outline: 2px solid #fff; outline-offset: -2px; }
  .tabs small { font-weight: 500; opacity: .75; margin-left: 4px; }
  /* water ripple where you tap */
  .ripple { position: absolute; z-index: 1; border-radius: 50%; pointer-events: none; width: 16px; height: 16px; margin: -8px 0 0 -8px;
    background: radial-gradient(circle, rgba(255,255,255,.55) 0%, rgba(255,255,255,.18) 45%, rgba(255,255,255,0) 70%);
    box-shadow: 0 0 0 1.5px rgba(255,255,255,.45); animation: ripple .75s ease-out forwards; }
  @keyframes ripple { from { transform: scale(0); opacity: .9; } to { transform: scale(14); opacity: 0; } }
  @media (max-width: 640px) {
    .tabs { background: linear-gradient(180deg, rgba(255,255,255,.75), rgba(255,255,255,.45)); border-color: rgba(255,255,255,.95);
      box-shadow: inset 0 1.5px 1px #fff, inset 0 -2px 6px rgba(20,19,23,.08), 0 10px 30px rgba(20,19,23,.14); }
    .tabs button { padding: 10px 13px; font-size: 13.5px; }
    .tabs button:hover { color: var(--ink); }
    .tabs button[aria-selected="true"] { color: #fff; }
    .ripple { background: radial-gradient(circle, rgba(255,255,255,.9) 0%, rgba(120,200,220,.25) 45%, rgba(255,255,255,0) 70%); box-shadow: 0 0 0 1.5px rgba(80,160,190,.35); }
  }
  @media (max-width: 400px) { .tabs small { display: none; } }
  @media (prefers-reduced-motion: reduce) { .drop { transition: none; } .drop.wobble, .ripple { animation: none; display: none; } }
  .view { position: fixed; left: 0; right: 0; bottom: 0; top: calc(var(--bar-h) + env(safe-area-inset-top, 0px) + 16px); }
  .view iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; background: transparent; }
  .view iframe[hidden] { display: none; }
</style>
</head>
<body>
<div class="bar">
  <div class="tabs" role="tablist" aria-label="Market">
    <span class="drop" aria-hidden="true"></span>
    <button type="button" role="tab" id="tab-gold" data-asset="gold" aria-selected="true" aria-controls="view-gold">Gold<small>XAUUSD</small></button>
    <button type="button" role="tab" id="tab-btc" data-asset="btc" aria-selected="false" aria-controls="view-btc">Bitcoin<small>BTCUSD</small></button>
    <button type="button" role="tab" id="tab-wti" data-asset="wti" aria-selected="false" aria-controls="view-wti">WTI<small>Crude oil</small></button>
  </div>
</div>
<div class="view">
  <iframe id="view-gold" title="Gold dashboard" src="gold.html"></iframe>
  <iframe id="view-btc" title="Bitcoin dashboard" src="btc.html" hidden></iframe>
  <iframe id="view-wti" title="WTI crude oil dashboard" src="wti.html" hidden></iframe>
</div>
<script>
  (() => {
    const ASSETS = { gold: ['Gold', '#0b0616'], btc: ['Bitcoin', '#060608'], wti: ['WTI crude oil', '#03121a'] };
    const tabs = document.querySelector('.tabs'), drop = tabs.querySelector('.drop');
    const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const place = (btn, wobble) => {
      drop.style.left = btn.offsetLeft + 'px'; drop.style.width = btn.offsetWidth + 'px';
      if (wobble && !calm) { drop.classList.remove('wobble'); void drop.offsetWidth; drop.classList.add('wobble'); }
    };
    const show = (a, wobble) => {
      if (!ASSETS[a]) a = 'gold';
      document.documentElement.dataset.asset = a;
      let cur;
      document.querySelectorAll('[data-asset][role="tab"]').forEach((b) => { const on = b.dataset.asset === a; b.setAttribute('aria-selected', String(on)); if (on) cur = b; });
      place(cur, wobble);
      Object.keys(ASSETS).forEach((k) => { document.getElementById('view-' + k).hidden = k !== a; });
      document.querySelector('meta[name="theme-color"]').content = ASSETS[a][1];
      document.title = ASSETS[a][0] + ' · SMC Radar';
      try { localStorage.setItem('smc-asset', a); } catch (e) { /* private mode */ }
      if (location.hash !== '#' + a) history.replaceState(null, '', '#' + a);
      // a dashboard drawn while hidden needs a resize to size its charts
      try { document.getElementById('view-' + a).contentWindow.dispatchEvent(new Event('resize')); } catch (e) { /* not loaded yet */ }
    };
    tabs.addEventListener('pointerdown', (e) => {
      if (calm) return;
      const r = tabs.getBoundingClientRect(), dot = document.createElement('span');
      dot.className = 'ripple'; dot.style.left = (e.clientX - r.left) + 'px'; dot.style.top = (e.clientY - r.top) + 'px';
      tabs.append(dot); dot.addEventListener('animationend', () => dot.remove());
    });
    document.querySelectorAll('[data-asset][role="tab"]').forEach((b) => b.addEventListener('click', () => show(b.dataset.asset, true)));
    tabs.addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      const list = [...tabs.querySelectorAll('[role="tab"]')], i = list.findIndex((b) => b.getAttribute('aria-selected') === 'true');
      const n = list[(i + (e.key === 'ArrowRight' ? 1 : list.length - 1)) % list.length]; n.focus(); show(n.dataset.asset, true);
    });
    window.addEventListener('hashchange', () => show(location.hash.slice(1), true));
    window.addEventListener('resize', () => place(tabs.querySelector('[aria-selected="true"]'), false));
    let start = location.hash.slice(1);
    if (!ASSETS[start]) { try { start = localStorage.getItem('smc-asset') || 'gold'; } catch (e) { start = 'gold'; } }
    drop.style.transition = 'none'; show(start, false); void drop.offsetWidth; drop.style.transition = '';
    if (document.fonts) document.fonts.ready.then(() => place(tabs.querySelector('[aria-selected="true"]'), false));
  })();
</script>
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
    (out / "icon-wti.svg").write_text(ICON_WTI)
    (out / "index.html").write_text(SHELL)
    (out / ".nojekyll").write_text("")
    print(f"site → {out}")


if __name__ == "__main__":
    main()
