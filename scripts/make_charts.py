"""
Regenerate the README charts from the dataset (reproducible artifacts).

Reads the fact table (full file if present, else the committed sample) and
writes four PNGs to docs/screenshots/.

Usage:
    python scripts/make_charts.py
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
OUT = os.path.join(ROOT, "docs", "screenshots")

GREEN, GREY, RED = "#1DB954", "#B3B3B3", "#E22134"
plt.rcParams.update({"figure.dpi": 120, "font.size": 11})


def load():
    data = os.path.join(ROOT, "data")
    full = os.path.join(data, "F_Streams.csv")
    fact = full if os.path.exists(full) else os.path.join(data, "sample", "F_Streams_sample.csv")
    f = pd.read_csv(fact)
    t = pd.read_csv(os.path.join(data, "D_Tracks.csv"))
    f["month"] = pd.to_datetime(f["listen_date"]).dt.month
    return f, t


def bare(ax):
    ax.spines[["top", "right"]].set_visible(False)


def main():
    os.makedirs(OUT, exist_ok=True)
    f, t = load()

    # 1. skip rate by source
    s = (f.groupby("stream_source")["is_skipped"].mean() * 100).sort_values()
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(s.index, s.values, color=[GREEN if v < 25 else RED for v in s.values])
    ax.set_title("Skip rate by discovery source", fontweight="bold")
    ax.set_ylabel("Skip rate (%)"); ax.set_ylim(0, 45)
    for b, v in zip(bars, s.values):
        ax.text(b.get_x() + b.get_width() / 2, v + 1, f"{v:.0f}%", ha="center", fontweight="bold")
    bare(ax); plt.tight_layout(); plt.savefig(os.path.join(OUT, "skip_rate_by_source.png")); plt.close()

    # 2. monthly seasonality
    m = f.groupby("month").size()
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(m.index, m.values, marker="o", color=GREEN, linewidth=2.5)
    ax.fill_between(m.index, m.values, alpha=0.1, color=GREEN)
    ax.set_title("Monthly streams — summer & December peaks", fontweight="bold")
    ax.set_xlabel("Month"); ax.set_ylabel("Streams"); ax.set_xticks(range(1, 13))
    bare(ax); plt.tight_layout(); plt.savefig(os.path.join(OUT, "monthly_seasonality.png")); plt.close()

    # 3. viral track 50
    v = f[f["track_id"] == 50].groupby("month").size()
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(v.index, v.values, color=[GREEN if mo == 10 else GREY for mo in v.index])
    ax.set_title("Track 50 — viral breakout in October (~14x baseline)", fontweight="bold")
    ax.set_xlabel("Month"); ax.set_ylabel("Streams"); ax.set_xticks(range(1, 13))
    bare(ax); plt.tight_layout(); plt.savefig(os.path.join(OUT, "viral_track.png")); plt.close()

    # 4. frontline vs catalog
    fl = f.merge(t[["track_id", "is_frontline"]], on="track_id")
    share = fl["is_frontline"].value_counts(normalize=True) * 100
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.pie([share.get(True, 0), share.get(False, 0)],
           labels=["Frontline\n(new releases)", "Catalog"], colors=[GREEN, GREY],
           autopct="%.0f%%", startangle=90, textprops={"fontweight": "bold"})
    ax.set_title("Frontline vs Catalog — share of streams", fontweight="bold")
    plt.tight_layout(); plt.savefig(os.path.join(OUT, "frontline_catalog.png")); plt.close()

    print("charts written to", OUT)


if __name__ == "__main__":
    main()
