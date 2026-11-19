# Gold SMC Scanner

Scanner emas (GC=F) berasaskan **Smart Money Concepts**:

1. **Fair Value Gap (FVG)**: gap 3 candle (`low[t] > high[t-2]` / `high[t] < low[t-2]`)
2. **Liquidity Sweep**: harga ambil swing high/low (stop hunt)
3. **Break of Structure (BOS)** / CHoCH: candle *close* melepasi swing terakhir
4. **Order Block (OB)**: candle lawan arah terakhir sebelum impulse yang buat BOS

## Model entry
**BUY:** sell-side liquidity disweep → BOS bullish → OB bullish (belum mitigated) → limit entry di 50% OB.
SL di bawah titik sweep (+0.25 ATR), TP1 = 2R (tutup separuh, SL ke BE), TP2 = high leg / 3R.
**SELL:** sebaliknya.

Grade: Sweep + BOS + OB = **B** (3/5) · + FVG confluence = +1 · + bias HTF sama arah = +1 → **A+** (5/5).

## Run
```bash
pip install pandas numpy requests
python scan.py              # 1h + bias daily (default, terbaik dalam backtest)
python scan.py --tf 15m     # 15m + bias 1h
python scan.py --aplus      # wajib FVG confluence
```
Output: `reports/latest.md` dan `reports/signal.json`. Exit code `2` = **ENTRY TRIGGER** (harga dalam zone setup aktif).

Laporan juga ada:
- **Banding dengan sejarah**: cari 5 pattern harga paling serupa (korelasi bentuk) dalam 2 tahun / 10 tahun, dan apa yang berlaku selepas itu.
- **Backtest**: prestasi strategi ini atas semua data sejarah yang ada.

## Hasil backtest (Nov 2026)
| TF | Tempoh | Trade | Win | Total | Max DD |
|---|---|---|---|---|---|
| 1h (bias 1d) | 2 tahun | 208 | 41% | **+61.5R** | 8.5R |
| 1h, Grade A+ sahaja | 2 tahun | 39 | 46% | +19.5R | |
| 15m (bias 1h) | 60 hari | 58 | 29% | **-10.5R** | 16R |

Penemuan:
- 15m tiada edge, 1h konsisten.
- SL **mesti** di luar titik sweep. Kalau SL hanya di luar OB, edge hilang (+6R).

> Data: Yahoo Finance GC=F (gold futures), beza beberapa dollar dari spot XAUUSD broker. Ada risiko parameter
> terlebih-suai (overfit) pada data lalu. Bukan nasihat kewangan.

## Scalping M15 (`scalp.py`)
Model: **zone Order Block 1H + pengesahan CHoCH/BOS 15m**. Entry pada tutup candle 15m yang break structure,
SL di luar high/low 15m dalam zone, TP separuh 1.5R, baki 3R.

Kajian walk-forward 7 strategi scalping M15 (60 hari data 15m, kos 0.4 point/trade), skrip dalam `research/`:

| Strategi | Trade (ujian) | R ujian | Keputusan |
|---|---|---|---|
| Zone 1H + CHoCH 15m (sama arah harian) | 11 | +8.4R | Lulus, 24/24 setting untung |
| Asian range sweep | 18 | +7.7R | Gagal atas 2 tahun 1H (3/36 setting untung) |
| SMC 15m + bias 1H | 9 | +0.5R | Tiada edge |
| EMA pullback | 52 | -0.5R | Gagal |
| NY opening range breakout | 22 | -6.0R | Gagal |
| Bollinger mean reversion | 58 | -5.0R | Gagal |
| FVG continuation | 16 | -8.3R | Gagal |

```bash
python scalp.py --dash reports/scalp
```
Exit code `2` = ENTRY segar (CHoCH dalam 4 candle 15m terakhir, harga belum lari >0.5R).

## Penapis indicator (`smc/indicators.py`, kajian: `research/indicator_filters.py`)
Diuji walk-forward (pilih setting tahun 1, nilai tahun 2):

| Penapis | Swing 1H (2 tahun) | Keputusan |
|---|---|---|
| Tiada | 208 trade, +61.5R, avg +0.30, DD 8.5R | asas |
| **EMA200 harian + ADX(1H) > 20** | **78 trade, +46R, avg +0.59, DD 5R, 9/10 suku untung** | **Dipakai (swing)** |
| EMA200 harian sahaja | 124 trade, +61.5R, avg +0.50, DD 14R | Dipakai (scalp: 10 trade, +9.4R) |
| RSI divergence | tidak membantu (scalp: -4.1R) | Ditolak |
| Sesi London/NY | tidak membantu | Ditolak |

## Dashboard gabungan (`radar.py`, `smc/tracking.py`)
`python radar.py` jalankan scan H1 + scalp M15 + tracking, dan tulis **satu** fail `reports/bundle.json`
yang dashboard baca (setiap bahagian = satu dataset). `dashboard.html` = salinan page.

Tracking: setiap signal dibina semula dengan peraturan scanner dan dinilai:
**Berjaya** = entry kena dan harga bergerak **100 pip ($10, 1 pip = $0.10)** sebelum SL ·
**Gagal** = SL dulu atau tamat masa (H1 72 jam, M15 24 jam) · **Berjalan** · **Menunggu** · **Tak execute**.
Jadual: status setiap jam (24 jam), rekod harian (tarikh, signal, entry, berjaya, gagal), log signal.
