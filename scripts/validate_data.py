"""
Data-quality gate for the streaming dataset.

Runs the checks an analytics engineer would put in CI before trusting the
data: schema presence, referential integrity (fact -> users/tracks/platform),
null and domain checks, and the key *behavioural* invariants the dataset is
designed to exhibit (e.g. algorithmic sources are skipped more than editorial
ones). Exits non-zero on failure so it can guard a pipeline.

Usage:
    python scripts/validate_data.py --dir data
"""

import argparse
import os
import sys

import pandas as pd

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    print(f"  {'✓' if condition else '✗'} {message}")
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
    users = pd.read_csv(os.path.join(args.dir, "D_Users.csv"))

    # --- schema -------------------------------------------------------
    expected = {"user_id", "track_id", "platform_id", "listen_date", "listen_hour",
                "device_type", "connection_type", "stream_source", "is_skipped",
                "is_liked", "listen_duration_sec", "royalty_cost", "revenue_generated"}
    check(expected.issubset(streams.columns), "fact table has all expected columns")
    check(len(streams) > 0, f"fact table is non-empty ({len(streams):,} rows)")

    # --- null checks on keys -----------------------------------------
    for col in ("user_id", "track_id", "platform_id", "listen_date"):
        check(streams[col].notna().all(), f"no nulls in key column '{col}'")

    # --- referential integrity ---------------------------------------
    check(streams["track_id"].isin(tracks["track_id"]).all(), "every fact.track_id exists in dim_track")
    check(streams["platform_id"].isin(platforms["platform_id"]).all(), "every fact.platform_id exists in dim_platform")
    check(streams["user_id"].isin(users["user_id"]).all(), "every fact.user_id exists in dim_user")

    # --- value domains ------------------------------------------------
    check(streams["listen_hour"].between(0, 23).all(), "listen_hour within 0..23")
    check((streams["listen_duration_sec"] >= 0).all(), "listen_duration_sec is non-negative")
    check((streams["revenue_generated"] >= 0).all(), "revenue_generated is non-negative")
    check(set(streams["stream_source"].unique()) <= {"Algorithmic", "Editorial", "Search"},
          "stream_source values are within the known set")
    check(set(users["subscription_plan"].unique()) <= {"Free", "Premium Individual", "Premium Student", "Premium Family"},
          "subscription_plan values are within the known set")

    # --- behavioural invariants (the whole point of the dataset) ------
    skip_overall = streams["is_skipped"].mean()
    check(0.25 <= skip_overall <= 0.40, f"overall skip rate is plausible ({skip_overall:.1%})")

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
