"""
Regenerate the README charts from the dataset (reproducible artifacts).

Reads the fact table (full file if present, else the committed sample) plus the
user dimension, and writes four PNGs to docs/screenshots/ — the same views the
Power BI dashboard tells its story with.

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
    users = pd.read_csv(os.path.join(data, "D_Users.csv"))
    f["month"] = pd.to_datetime(f["listen_date"]).dt.month
    return f, users


def bare(ax):
    ax.spines[["top", "right"]].set_visible(False)


def main():
    os.makedirs(OUT, exist_ok=True)
    f, users = load()

    # 1. skip rate by discovery source (the headline)
    s = (f.groupby("stream_source")["is_skipped"].mean() * 100).sort_values()
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(s.index, s.values, color=[GREEN if v < 30 else RED for v in s.values])
    ax.set_title("Skip rate by discovery source", fontweight="bold")
    ax.set_ylabel("Skip rate (%)"); ax.set_ylim(0, 50)
    for b, v in zip(bars, s.values):
        ax.text(b.get_x() + b.get_width() / 2, v + 1, f"{v:.0f}%", ha="center", fontweight="bold")
    bare(ax); plt.tight_layout(); plt.savefig(os.path.join(OUT, "skip_rate_by_source.png")); plt.close()

    # 2. skip rate by device (mobile lift)
    d = (f.groupby("device_type")["is_skipped"].mean() * 100).sort_values()
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.barh(d.index, d.values, color=[RED if v > 31 else GREEN for v in d.values])
    ax.set_title("Skip rate by device — mobile skips more", fontweight="bold")
    ax.set_xlabel("Skip rate (%)"); ax.set_xlim(0, 45)
    for b, v in zip(bars, d.values):
        ax.text(v + 0.5, b.get_y() + b.get_height() / 2, f"{v:.0f}%", va="center", fontweight="bold")
    bare(ax); plt.tight_layout(); plt.savefig(os.path.join(OUT, "skip_rate_by_device.png")); plt.close()

    # 3. monthly seasonality
    m = f.groupby("month").size()
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(m.index, m.values, marker="o", color=GREEN, linewidth=2.5)
    ax.fill_between(m.index, m.values, alpha=0.1, color=GREEN)
    ax.set_title("Monthly streams — summer & December peaks", fontweight="bold")
    ax.set_xlabel("Month"); ax.set_ylabel("Streams"); ax.set_xticks(range(1, 13)); ax.set_ylim(bottom=0)
    bare(ax); plt.tight_layout(); plt.savefig(os.path.join(OUT, "monthly_seasonality.png")); plt.close()

    # 4. subscription-plan mix (of active users)
    active = users[users["user_id"].isin(f["user_id"].unique())]
    mix = active["subscription_plan"].value_counts()
    order = ["Free", "Premium Individual", "Premium Student", "Premium Family"]
    mix = mix.reindex([o for o in order if o in mix.index])
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.pie(mix.values, labels=mix.index, colors=[GREY, GREEN, "#17a34a", "#0e7a37"],
           autopct="%.0f%%", startangle=90, textprops={"fontweight": "bold", "fontsize": 9})
    ax.set_title("Subscription mix — Free vs Premium (active users)", fontweight="bold")
    plt.tight_layout(); plt.savefig(os.path.join(OUT, "subscription_mix.png")); plt.close()

    print("charts written to", OUT)


if __name__ == "__main__":
    main()
