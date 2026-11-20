#!/usr/bin/env python3
"""Build the public website from dashboard.html (the same page the claude.ai dashboard uses).

    python tools/build_site.py --out _site

Writes _site/index.html (the page wrapped in a full HTML document with the runtime shim),
dash.js, lwc.js, the PWA manifest and icon, and copies reports/bundle.json and
research/scalp_research.json into _site/data/.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Gold SMC Radar</title>
<meta name="description" content="Gold (XAUUSD) Smart Money Concepts radar: H1 swing and M15 scalp signals with a live success tracker. Not financial advice.">
<meta name="theme-color" content="#120a22">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="icon.svg">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Gold Radar">
<style>
  :root {
    --cds-gap-xs: 4px; --cds-gap-sm: 8px; --cds-gap-md: 16px; --cds-gap-lg: 24px; --cds-gap-xl: 32px;
    --cds-pad-sm: 8px; --cds-pad-md: 14px; --cds-pad-lg: 20px; --cds-radius: 10px;
    --cds-font-size-caption: 12px; --cds-font-size-body: 15px; --cds-font-size-heading: 17px; --cds-font-size-title: 28px;
    --cds-font-weight-medium: 500;
    --font-anthropic-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, "Helvetica Neue", Arial, sans-serif;
    --font-anthropic-serif: Georgia, "Times New Roman", serif;
    color-scheme: dark;
  }
  html, body { margin: 0; background: #0b0616; }
  body { padding: max(12px, env(safe-area-inset-top)) max(12px, env(safe-area-inset-right)) max(12px, env(safe-area-inset-bottom)) max(12px, env(safe-area-inset-left)); }
  #dash-root { max-width: 1180px; margin: 0 auto; }
  @media (max-width: 640px) { html, body { background: #e4e4ea; } body { padding: 8px; } :root { color-scheme: light; } }
</style>
<script>window.GR_EVERY_MIN = 15;</script>
<script src="d3.min.js"></script>
<script src="dash.js"></script>
</head>
<body>
<div id="dash-root">
"""

TAIL = """
</div>
</body>
</html>
"""

MANIFEST = """{
  "name": "Gold SMC Radar",
  "short_name": "Gold Radar",
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_site")
    args = ap.parse_args()
    out = ROOT / args.out
    (out / "data").mkdir(parents=True, exist_ok=True)
    page = (ROOT / "dashboard.html").read_text()
    (out / "index.html").write_text(HEAD + page + TAIL)
    shutil.copy(ROOT / "site" / "dash.js", out / "dash.js")
    shutil.copy(ROOT / "vendor" / "lwc.js", out / "lwc.js")
    shutil.copy(ROOT / "vendor" / "d3.min.js", out / "d3.min.js")
    (out / "manifest.webmanifest").write_text(MANIFEST)
    (out / "icon.svg").write_text(ICON)
    shutil.copy(ROOT / "research" / "scalp_research.json", out / "data" / "research.json")
    bundle = ROOT / "reports" / "bundle.json"
    if bundle.exists():
        shutil.copy(bundle, out / "data" / "bundle.json")
    (out / ".nojekyll").write_text("")
    print(f"site → {out}")


if __name__ == "__main__":
    main()
