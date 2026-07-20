"""
Streaming Ecosystem — synthetic dataset generator (v3.1)

Generates a star-schema dataset simulating one year of listening events on a
music streaming platform. The data is engineered to reflect real industry
dynamics rather than uniform noise:

  * Seasonality        — summer (+40%) and December (+30%) listening peaks
  * Weekend lift       — higher volume on Saturday/Sunday
  * Viral moment       — one track explodes in October (~14x its baseline)
  * Discovery behavior — algorithmic recommendations get skipped far more
                         often (~40%) than user-driven sources (~15%)
  * Catalog strategy   — frontline (new release) vs catalog split

Usage:
    python scripts/generate_datasets.py --out data/ --users 50000 --seed 42

Output: F_Streams.csv, D_Tracks.csv, D_Platform.csv, D_Time.csv
"""

import argparse
import os

import numpy as np
import pandas as pd

GENRES = ["Pop", "Rock", "Hip Hop", "Reggaeton", "Electronic", "Indie", "Classical"]
PLATFORMS = ["Spotify", "Apple Music", "YouTube Music", "SoundCloud"]
SOURCES = ["Algorithmic", "Editorial", "Radio", "Search"]
SOURCE_WEIGHTS = [0.40, 0.20, 0.20, 0.20]
SKIP_RATE_BY_SOURCE = {"Algorithmic": 0.40, "Editorial": 0.15, "Radio": 0.15, "Search": 0.15}

MONTH_MULTIPLIER = {1: 1.0, 2: 0.97, 3: 1.0, 4: 0.97, 5: 1.0,
                    6: 1.38, 7: 1.40, 8: 1.40, 9: 0.98,
                    10: 1.0, 11: 0.98, 12: 1.31}
WEEKEND_LIFT = 1.15
VIRAL_TRACK_ID = 50
VIRAL_MONTH = 10
VIRAL_MULTIPLIER = 14

LIKE_RATE = 0.018
SUBSCRIBER_SHARE = 0.35
FRONTLINE_TRACK_SHARE = 0.35
STREAMS_PER_USER_YEAR = 24


def build_tracks(n_tracks: int, rng: np.random.Generator) -> pd.DataFrame:
    return pd.DataFrame({
        "track_id": np.arange(1, n_tracks + 1),
        "track_title": [f"Track_{i}" for i in range(1, n_tracks + 1)],
        "artist_id": np.arange(1, n_tracks + 1),
        "main_genre": rng.choice(GENRES, size=n_tracks),
        "total_duration_sec": rng.integers(120, 300, size=n_tracks),
        "is_frontline": rng.random(n_tracks) < FRONTLINE_TRACK_SHARE,
    })


def build_time(year: int) -> pd.DataFrame:
    days = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    return pd.DataFrame({
        "time_key": days.strftime("%Y-%m-%d"),
        "year": days.year,
        "month": days.month,
        "day_of_week": days.day_name(),
        "is_weekend": days.dayofweek >= 5,
    })


def build_streams(n_users: int, tracks: pd.DataFrame, time_dim: pd.DataFrame,
                  rng: np.random.Generator) -> pd.DataFrame:
    # Daily volume shaped by seasonality and weekend lift
    days = pd.to_datetime(time_dim["time_key"])
    day_weight = days.dt.month.map(MONTH_MULTIPLIER).to_numpy()
    day_weight *= np.where(days.dt.dayofweek >= 5, WEEKEND_LIFT, 1.0)
    day_weight /= day_weight.sum()

    total_streams = n_users * STREAMS_PER_USER_YEAR
    streams_per_day = rng.multinomial(total_streams, day_weight)

    # Track popularity: zipf-like long tail, then the viral October spike
    popularity = 1.0 / np.arange(1, len(tracks) + 1) ** 0.35
    rng.shuffle(popularity)

    subscriber_lookup = rng.random(n_users) < SUBSCRIBER_SHARE
    track_duration = tracks.set_index("track_id")["total_duration_sec"]

    chunks = []
    for day, n_day in zip(time_dim["time_key"], streams_per_day):
        month = int(day[5:7])
        weights = popularity.copy()
        if month == VIRAL_MONTH:
            weights[VIRAL_TRACK_ID - 1] *= VIRAL_MULTIPLIER
        weights /= weights.sum()

        track_ids = rng.choice(tracks["track_id"].to_numpy(), size=n_day, p=weights)
        sources = rng.choice(SOURCES, size=n_day, p=SOURCE_WEIGHTS)
        skip_p = np.vectorize(SKIP_RATE_BY_SOURCE.get)(sources)
        is_skipped = rng.random(n_day) < skip_p

        durations = track_duration.loc[track_ids].to_numpy()
        listen_sec = np.where(
            is_skipped,
            rng.integers(5, 30, size=n_day),
            (durations * rng.uniform(0.35, 1.0, size=n_day)).astype(int),
        )
        user_ids = rng.integers(1, n_users + 1, size=n_day)

        chunks.append(pd.DataFrame({
            "user_id": user_ids,
            "track_id": track_ids,
            "platform_id": rng.integers(1, len(PLATFORMS) + 1, size=n_day),
            "listen_date": day,
            "listen_hour": rng.integers(0, 24, size=n_day),
            "stream_source": sources,
            "listen_duration_sec": listen_sec,
            "is_skipped": is_skipped,
            "is_liked": ~is_skipped & (rng.random(n_day) < LIKE_RATE / (1 - 0.25)),
            "is_subscriber": subscriber_lookup[user_ids - 1],
        }))

    return pd.concat(chunks, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the Streaming Ecosystem dataset")
    parser.add_argument("--out", default="data/", help="output directory")
    parser.add_argument("--users", type=int, default=50_000)
    parser.add_argument("--tracks", type=int, default=100)
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    os.makedirs(args.out, exist_ok=True)

    tracks = build_tracks(args.tracks, rng)
    time_dim = build_time(args.year)
    streams = build_streams(args.users, tracks, time_dim, rng)

    platforms = pd.DataFrame({
        "platform_id": range(1, len(PLATFORMS) + 1),
        "service_name": PLATFORMS,
    })

    tracks.to_csv(os.path.join(args.out, "D_Tracks.csv"), index=False)
    time_dim.to_csv(os.path.join(args.out, "D_Time.csv"), index=False)
    platforms.to_csv(os.path.join(args.out, "D_Platform.csv"), index=False)
    streams.to_csv(os.path.join(args.out, "F_Streams.csv"), index=False)

    print(f"Generated {len(streams):,} streams for {args.users:,} users "
          f"({args.year}) -> {args.out}")
    print(f"Overall skip rate: {streams['is_skipped'].mean():.1%} | "
          f"algorithmic: {streams.loc[streams.stream_source == 'Algorithmic', 'is_skipped'].mean():.1%}")


if __name__ == "__main__":
    main()
