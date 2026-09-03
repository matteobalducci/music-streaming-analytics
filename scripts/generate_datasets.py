"""
Reproducible generator for the music-streaming star schema.

Produces the same 5-table shape as the analysed dataset — a fact table plus
four dimensions (users, tracks, platform, time) — calibrated to realistic
streaming dynamics: seasonality (summer & December lift), weekend lift, an
algorithmic-vs-editorial skip gap, a mobile skip lift, and ~18% user churn.

Output: F_Streams.csv, D_Users.csv, D_Tracks.csv, D_Platform.csv, D_Time.csv

Usage:
    python scripts/generate_datasets.py --out data/ --users 45000 --seed 42
"""

import argparse
import os

import numpy as np
import pandas as pd

YEAR = 2024
COUNTRIES = ["USA", "Italy", "UK", "France", "Brazil", "Germany"]
PLANS = ["Free", "Premium Individual", "Premium Student", "Premium Family"]
PLAN_P = [0.448, 0.299, 0.152, 0.101]
CHANNELS = ["Social Media Ads", "App Store", "Influencer Referral", "Organic Search"]
GENRES = ["Electronic", "Hip Hop", "Pop", "Classical", "Indie", "Rock", "Reggaeton"]
GENRE_P = [0.20, 0.15, 0.14, 0.14, 0.13, 0.12, 0.12]
PLATFORMS = ["Spotify", "Apple Music", "YouTube Music", "SoundCloud"]
DEVICES = ["Mobile iOS", "Mobile Android", "Tablet", "Desktop", "Smart Speaker"]
CONN = ["Wifi", "Cellular", "Offline"]
CONN_P = [0.60, 0.30, 0.10]
SOURCES = ["Algorithmic", "Editorial", "Search"]
SOURCE_P = [0.40, 0.20, 0.40]

# Skip probability by discovery source — the dataset's defining signal.
# BASE skip probabilities, before MOBILE_SKIP_LIFT is added on top. Mobile is
# 2 of 5 device types, so the lift raises each realised rate by 0.4 * 0.05 = 2pp:
#   Algorithmic 0.40 -> 42%   Editorial 0.20 -> 22%   Search 0.20 -> 22%
# which are the figures the README and the dashboard quote.
#
# FIX 2026-09-03: these had been set to the *realised* values (0.42/0.22/0.22),
# which double-counted the lift and produced 44%/24%/24% — silently breaking the
# headline numbers in the README. tests/test_headline_metrics.py now locks them.
SKIP_BY_SOURCE = {"Algorithmic": 0.40, "Editorial": 0.20, "Search": 0.20}
MOBILE_SKIP_LIFT = 0.05          # mobile devices skip a bit more
CHURN_RATE = 0.18
STREAMS_PER_USER = 27
MONTH_MULT = {1: .85, 2: .82, 3: .9, 4: .95, 5: 1.0, 6: 1.15,
              7: 1.25, 8: 1.2, 9: .95, 10: .95, 11: .95, 12: 1.1}  # summer + Dec lift
WEEKEND_LIFT = 1.25

# Average revenue per stream, by plan. Free monetises with ads — a few
# thousandths per listen; Premium plans split the subscription across the
# month's listens, so they earn far more per stream. Without this
# difference Q3 couldn't say anything about which plan drives revenue.
REVENUE_PER_STREAM = {
    "Free": 0.0018,
    "Premium Student": 0.0052,
    "Premium Family": 0.0061,
    "Premium Individual": 0.0079,
}
ROYALTY_SHARE = 0.68   # share of revenue that goes to the labels
# Listening hour is close to uniform in the analysed dataset (no circadian dip) —
# match that rather than inventing a pattern the real data doesn't show.
HOUR_W = np.ones(24)


def build_platform():
    return pd.DataFrame({"platform_id": range(1, 5), "service_name": PLATFORMS})


def build_time(year):
    days = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    return pd.DataFrame({
        "time_key": days.strftime("%Y-%m-%d"),
        "year": days.year, "month": days.month,
        "day_of_week": days.day_name(),
        "is_weekend": days.dayofweek >= 5,
    })


def build_users(n, rng):
    signup = pd.to_datetime(f"{YEAR-1}-08-01") + pd.to_timedelta(rng.integers(0, 400, n), "D")
    # FIX 2026-09-03: `churned` used to be computed and never used — the next
    # line overwrote the series for ALL users, giving everyone a churn date
    # inside the year. The repo's Q4, which measures retention as
    # `churn_date IS NULL OR churn_date > '2024-12-31'`, therefore read 27%
    # instead of the 82% documented and present in the data loaded on BigQuery.
    # No check caught it: the dataset generated fine, the quality checks
    # passed, the SQL ran. Only the finding was false.
    churned = rng.random(n) < CHURN_RATE

    # Whoever churns does so within the analysis window; whoever stays gets a
    # date past the year — matching the loaded dataset, where churn_date is
    # populated for everyone but only 17.7% falls within 2024.
    # Churn is front-loaded: someone who signs up and doesn't take to it
    # leaves within the first weeks, not halfway through the second year. An
    # exponential distribution reproduces that shape — and it also reproduces
    # the loaded data, where 44% of churners do so by April. With a uniform
    # offset, April retention read 96.3% against the dashboard's 92.3%.
    offset = np.clip(rng.exponential(110, n), 20, 500).astype(int)
    churn = (signup + pd.to_timedelta(offset, "D")).to_numpy()
    year_end = np.datetime64(f"{YEAR}-12-31")
    next_year = np.datetime64(f"{YEAR + 1}-01-15")

    churn = np.where(
        churned,
        np.minimum(churn, year_end),                                  # churns: within the year
        np.maximum(churn, next_year) + rng.integers(0, 300, n).astype("timedelta64[D]"),
    )
    churn = pd.DatetimeIndex(churn)

    return pd.DataFrame({
        "user_id": range(1, n + 1),
        "country": rng.choice(COUNTRIES, n),
        "signup_date": signup.strftime("%Y-%m-%d"),
        "subscription_plan": rng.choice(PLANS, n, p=PLAN_P),
        "signup_channel": rng.choice(CHANNELS, n),
        "churn_date": churn.strftime("%Y-%m-%d"),
    }), churned


def build_tracks(n, rng):
    return pd.DataFrame({
        "track_id": range(1, n + 1),
        "track_title": [f"Track {i}" for i in range(1, n + 1)],
        "artist_id": rng.integers(1, 41, n),
        "main_genre": rng.choice(GENRES, n, p=GENRE_P),
        "release_date": (pd.to_datetime("2022-09-01") + pd.to_timedelta(rng.integers(0, 760, n), "D")).strftime("%Y-%m-%d"),
        "bpm": rng.integers(66, 176, n),
        "energy": rng.uniform(0.30, 0.95, n).round(2),
        "valence": rng.uniform(0.10, 0.88, n).round(2),
        "danceability": rng.uniform(0.40, 0.88, n).round(2),
        "total_duration_sec": rng.integers(150, 320, n),
    })


def build_streams(n_users, tracks, time_dim, churned, signup, churn_dates,
                  plans_by_user, rng):
    days = pd.to_datetime(time_dim["time_key"])
    w = days.dt.month.map(MONTH_MULT).to_numpy(dtype=float, copy=True)
    w *= np.where(days.dt.dayofweek >= 5, WEEKEND_LIFT, 1.0)
    w /= w.sum()

    total = n_users * STREAMS_PER_USER

    # FIX 2026-09-03: `churned` was this file's dead third parameter — it
    # arrived in the signature and was never used, so streams were spread
    # uniformly across ALL users and everyone got at least one. The "active /
    # signed-up" KPI therefore read 100%.
    #
    # Q4 builds its whole argument on that number: "the naive KPI reads
    # ~97%, but that's reach, not retention." At 100% the example lost its
    # sharpest contrast, and didn't match the loaded data (97.3%). Someone
    # who churns listens less, and some don't show up at all. A user's
    # weight is the fraction of the year they were active: someone who
    # signs up mid-year, or churns in January, listens less. Someone who had
    # already churned before the year began doesn't show up at all, and
    # that's exactly how the "active / signed-up" KPI drops below 100%.
    year_start = np.datetime64(f"{YEAR}-01-01")
    year_end_np = np.datetime64(f"{YEAR}-12-31")
    span = (year_end_np - year_start).astype(int) + 1

    window_start = np.maximum(signup.to_numpy().astype("datetime64[D]"), year_start)
    # The churn day is the first day NO LONGER active: the window closes the
    # day before, so no stream falls on or after churn.
    window_end = np.minimum(churn_dates.to_numpy().astype("datetime64[D]")
                            - np.timedelta64(1, "D"), year_end_np)
    active_days = np.clip((window_end - window_start).astype(int) + 1, 0, span)

    user_weight = active_days.astype(float)
    if user_weight.sum() == 0:
        user_weight = np.ones(n_users)
    user_weight = user_weight / user_weight.sum()

    # The user is chosen BEFORE the date, because the date has to fall
    # inside their active window.
    #
    # FIX 2026-09-03: dates used to be drawn globally and the user assigned
    # afterward, independently. The result was that 13.7% of streams
    # preceded the user's signup and 2.4% happened after their churn. A fact
    # table where an event precedes the user's existence isn't defensible,
    # and it makes any temporal analysis unreliable — including exactly the
    # retention and seasonality this project documents.
    user_idx = rng.choice(n_users, total, p=user_weight)

    # Allowed window for each stream, as day-of-year indices.
    window_start_idx = np.searchsorted(days.to_numpy(), window_start.astype("datetime64[ns]"))
    window_end_idx = np.searchsorted(days.to_numpy(), window_end.astype("datetime64[ns]"))
    lo, hi = window_start_idx[user_idx], np.maximum(window_end_idx[user_idx], window_start_idx[user_idx])

    # Draw from the seasonal distribution and only re-draw what falls
    # outside the window: after a few passes very few cases remain, which
    # are assigned uniformly inside the window. This keeps seasonality
    # intact for the vast majority of events without building a separate
    # distribution for each of the 45,000 users.
    day_idx = rng.choice(len(days), total, p=w)
    for _ in range(12):
        out_of_window = (day_idx < lo) | (day_idx > hi)
        if not out_of_window.any():
            break
        day_idx[out_of_window] = rng.choice(len(days), int(out_of_window.sum()), p=w)
    out_of_window = (day_idx < lo) | (day_idx > hi)
    if out_of_window.any():
        day_idx[out_of_window] = lo[out_of_window] + (rng.random(int(out_of_window.sum()))
                                      * (hi[out_of_window] - lo[out_of_window] + 1)).astype(int)
    day_idx = np.clip(day_idx, lo, hi)

    listen_date = days.dt.strftime("%Y-%m-%d").to_numpy()[day_idx]
    listen_hour = rng.choice(24, total, p=HOUR_W / HOUR_W.sum())

    # popularity-weighted track choice
    pop = 1.0 / np.arange(1, len(tracks) + 1) ** 0.35
    pop /= pop.sum()
    track_id = rng.choice(tracks["track_id"].to_numpy(), total, p=pop)

    source = rng.choice(SOURCES, total, p=SOURCE_P)
    device = rng.choice(DEVICES, total)
    is_mobile = np.isin(device, ["Mobile iOS", "Mobile Android"])

    skip_p = np.vectorize(SKIP_BY_SOURCE.get)(source) + is_mobile * MOBILE_SKIP_LIFT
    is_skipped = rng.random(total) < skip_p
    is_liked = rng.random(total) < np.where(is_skipped, 0.03, 0.20)

    durations = tracks.set_index("track_id")["total_duration_sec"]
    full = durations.reindex(track_id).to_numpy()
    listen_dur = np.where(is_skipped,
                          (rng.uniform(2, 30, total)).astype(int),
                          (full * rng.uniform(0.6, 1.0, total)).astype(int))

    # FIX 2026-09-03: `revenue_generated` used to be drawn from the same
    # uniform distribution for everyone regardless of plan — so the finding
    # "Premium plans drive revenue" wasn't measurable in the data, and Q3
    # summed the same revenue even for Free users. Now revenue per stream
    # depends on the plan: Free monetises with ads (little per stream),
    # Premium with the subscription split across listens.
    user_plan = plans_by_user[user_idx]
    base = np.vectorize(REVENUE_PER_STREAM.get)(user_plan)
    revenue = (base * rng.uniform(0.75, 1.25, total)).round(5)

    # Royalty is only paid on a real listen, not on a skip.
    royalty = np.where(is_skipped, 0.0, revenue * ROYALTY_SHARE).round(5)
    return pd.DataFrame({
        # ADDED 09/03: without a key, the declared grain — one row per
        # listening event — is neither verifiable nor deduplicable, and a
        # duplicate load would go unnoticed.
        "stream_id": np.arange(1, total + 1),
        "user_id": user_idx + 1,
        "track_id": track_id,
        "platform_id": rng.integers(1, 5, total),
        "listen_date": listen_date,
        "listen_hour": listen_hour,
        "device_type": device,
        "connection_type": rng.choice(CONN, total, p=CONN_P),
        "stream_source": source,
        "is_skipped": is_skipped,
        "is_liked": is_liked,
        "listen_duration_sec": listen_dur,
        "royalty_cost": royalty,
        "revenue_generated": revenue,
    })


def main():
    parser = argparse.ArgumentParser(description="Generate the streaming star schema")
    parser.add_argument("--out", default="data/")
    parser.add_argument("--users", type=int, default=45000)
    parser.add_argument("--tracks", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    # Without these checks `--users 0` produced an empty dataset that the
    # generator reported as successful, and the failure only showed up much
    # later, as a division by zero inside some metric.
    if args.users <= 0:
        parser.error("--users must be positive")
    if args.tracks <= 0:
        parser.error("--tracks must be positive")

    rng = np.random.default_rng(args.seed)
    os.makedirs(args.out, exist_ok=True)

    platform = build_platform()
    time_dim = build_time(YEAR)
    users, churned = build_users(args.users, rng)
    tracks = build_tracks(args.tracks, rng)
    streams = build_streams(args.users, tracks, time_dim, churned,
                            pd.to_datetime(users['signup_date']),
                            pd.to_datetime(users['churn_date']),
                            users['subscription_plan'].to_numpy(), rng)

    platform.to_csv(os.path.join(args.out, "D_Platform.csv"), index=False)
    time_dim.to_csv(os.path.join(args.out, "D_Time.csv"), index=False)
    users.to_csv(os.path.join(args.out, "D_Users.csv"), index=False)
    tracks.to_csv(os.path.join(args.out, "D_Tracks.csv"), index=False)
    streams.to_csv(os.path.join(args.out, "F_Streams.csv"), index=False)

    print(f"Generated {len(streams):,} streams for {args.users:,} users ({YEAR}) -> {args.out}")
    print(f"Overall skip rate: {streams['is_skipped'].mean():.1%} | "
          f"algorithmic: {streams.loc[streams.stream_source=='Algorithmic','is_skipped'].mean():.1%}")


if __name__ == "__main__":
    main()
