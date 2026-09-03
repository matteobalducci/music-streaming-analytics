"""
Builds the public sample of the fact table.

WHY THIS EXISTS
---------------
`data/sample/F_Streams_sample.csv` is the first thing anyone cloning this repo
looks at — the full fact table is ~100 MB and is not committed. Until now the
sample was cut by hand, which made it the one file in the project nobody could
regenerate: when the fact table gained a `stream_id` column, the sample silently
kept the old schema and the data-quality gate started failing on it.

Sampling is by whole user, not by row. A random slice of rows would break every
user-grain claim in the repo — retention, active users, revenue per user — since
each sampled user would be missing most of their listening history. Taking all
the rows of a subset of users keeps those metrics meaningful on the sample.

Usage:
    python scripts/make_sample.py --dir data --users 4000 --seed 42
"""

import argparse
import os

import numpy as np
import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="data")
    parser.add_argument("--users", type=int, default=4000,
                        help="how many whole users to include in the sample")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.users <= 0:
        parser.error("--users must be positive")

    fact = os.path.join(args.dir, "F_Streams.csv")
    if not os.path.exists(fact):
        parser.error(f"{fact} does not exist: run scripts/generate_datasets.py first")

    streams = pd.read_csv(fact)
    rng = np.random.default_rng(args.seed)
    chosen = rng.choice(streams["user_id"].unique(), size=min(args.users,
                        streams["user_id"].nunique()), replace=False)
    sample = streams[streams["user_id"].isin(chosen)]

    out_dir = os.path.join(args.dir, "sample")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "F_Streams_sample.csv")
    sample.to_csv(out, index=False)

    mb = os.path.getsize(out) / 1024 / 1024
    print(f"{out}: {len(sample):,} rows · {len(chosen):,} whole users · {mb:.1f} MB")
    print(f"skip rate {sample['is_skipped'].mean():.1%} "
          f"(full fact table: {streams['is_skipped'].mean():.1%})")


if __name__ == "__main__":
    main()
