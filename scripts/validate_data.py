"""
Data-quality gate for the streaming dataset.

Runs the checks an analytics engineer would put in CI before trusting the
data: schema presence, referential integrity, null checks, and the key
*behavioural* invariants the dataset is designed to exhibit (e.g. algorithmic
sources must be skipped more than editorial ones). Exits non-zero on failure
so it can guard a pipeline.

Usage:
    python scripts/validate_data.py --dir data
    python scripts/validate_data.py --dir data --fact data/sample/F_Streams_sample.csv
"""

import argparse
import os
import sys

import pandas as pd

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    status = "✓" if condition else "✗"
    print(f"  {status} {message}")
    if not condition:
        FAILURES.append(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="data")
    parser.add_argument("--fact", default=None, help="fact CSV (default: <dir>/F_Streams.csv or the sample)")
    args = parser.parse_args()

    fact_path = args.fact
    if not fact_path:
        full = os.path.join(args.dir, "F_Streams.csv")
        fact_path = full if os.path.exists(full) else os.path.join(args.dir, "sample", "F_Streams_sample.csv")

    print(f"validating {fact_path} against dimensions in {args.dir}/\n")
    streams = pd.read_csv(fact_path)
    tracks = pd.read_csv(os.path.join(args.dir, "D_Tracks.csv"))
    platforms = pd.read_csv(os.path.join(args.dir, "D_Platform.csv"))

    # --- schema -------------------------------------------------------
    expected = {"user_id", "track_id", "platform_id", "listen_date", "listen_hour",
                "stream_source", "listen_duration_sec", "is_skipped", "is_liked", "is_subscriber"}
    check(expected.issubset(streams.columns), "fact table has all expected columns")

    # --- non-empty ----------------------------------------------------
    check(len(streams) > 0, f"fact table is non-empty ({len(streams):,} rows)")

    # --- null checks on keys -----------------------------------------
    for col in ("user_id", "track_id", "platform_id", "listen_date"):
        check(streams[col].notna().all(), f"no nulls in key column '{col}'")

    # --- referential integrity ---------------------------------------
    check(streams["track_id"].isin(tracks["track_id"]).all(),
          "every fact.track_id exists in dim_track")
    check(streams["platform_id"].isin(platforms["platform_id"]).all(),
          "every fact.platform_id exists in dim_platform")

    # --- value domains ------------------------------------------------
    check(streams["listen_hour"].between(0, 23).all(), "listen_hour within 0..23")
    check((streams["listen_duration_sec"] >= 0).all(), "listen_duration_sec is non-negative")
    check(set(streams["stream_source"].unique()) <= {"Algorithmic", "Editorial", "Radio", "Search"},
          "stream_source values are within the known set")

    # --- behavioural invariants (the whole point of the dataset) ------
    skip_overall = streams["is_skipped"].mean()
    check(0.15 <= skip_overall <= 0.45, f"overall skip rate is plausible ({skip_overall:.1%})")

    by_source = streams.groupby("stream_source")["is_skipped"].mean()
    if {"Algorithmic", "Editorial"}.issubset(by_source.index):
        check(by_source["Algorithmic"] > by_source["Editorial"],
              f"algorithmic skip ({by_source['Algorithmic']:.1%}) > editorial ({by_source['Editorial']:.1%})")

    print()
    if FAILURES:
        print(f"FAILED — {len(FAILURES)} check(s) did not pass")
        sys.exit(1)
    print("all data-quality checks passed")


if __name__ == "__main__":
    main()
