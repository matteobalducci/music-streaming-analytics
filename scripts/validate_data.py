"""
Data-quality gate for the streaming dataset.

Runs the checks an analytics engineer would put in CI before trusting the
data: schema presence, referential integrity (fact -> users/tracks/platform),
null and domain checks, grain uniqueness, temporal integrity, and the key
*behavioural* invariants the dataset is designed to exhibit (e.g. algorithmic
sources are skipped more than editorial ones). Exits non-zero on failure so it
can guard a pipeline.

Every check added on 2026-09-03 corresponds to a defect actually found in
audit, not a theoretical precaution: streams dated before signup, a missing
grain key, and the asymmetric revenue/royalty model the dashboard's Gross
Margin depends on.

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
    calendar = pd.read_csv(os.path.join(args.dir, "D_Time.csv"))

    # --- schema -------------------------------------------------------
    # Exact comparison, not issubset: an extra column means the generator and
    # the load schema have drifted apart, and the BigQuery load would only
    # fail after reading the whole file.
    expected = {"stream_id", "user_id", "track_id", "platform_id", "listen_date",
                "listen_hour", "device_type", "connection_type", "stream_source",
                "is_skipped", "is_liked", "listen_duration_sec", "royalty_cost",
                "revenue_generated"}
    actual = set(streams.columns)
    check(actual == expected,
          "fact schema matches exactly"
          + (f" (extra: {sorted(actual - expected)}, missing: {sorted(expected - actual)})"
             if actual != expected else ""))
    # `bq load` with an explicit schema (scripts/load_bigquery.sh) reads
    # columns by POSITION, not by name: a CSV with the right columns but a
    # different order would pass the set check above and then load every
    # value into the wrong column.
    expected_order = ["stream_id", "user_id", "track_id", "platform_id", "listen_date",
                       "listen_hour", "device_type", "connection_type", "stream_source",
                       "is_skipped", "is_liked", "listen_duration_sec", "royalty_cost",
                       "revenue_generated"]
    if actual == expected:
        check(list(streams.columns) == expected_order,
              f"fact columns are in the order the positional load expects "
              f"(found: {list(streams.columns)})")
    check(len(streams) > 0, f"fact table is non-empty ({len(streams):,} rows)")

    # --- null checks on keys -----------------------------------------
    for col in ("user_id", "track_id", "platform_id", "listen_date"):
        check(streams[col].notna().all(), f"no nulls in key column '{col}'")

    # --- grain: one row = one listen -----------------------------------
    # The grain is the claim every dashboard count rests on. Without this
    # check, a double load doubles every volume metric and no other test
    # notices.
    if "stream_id" in streams.columns:
        # It's REQUIRED in the load schema (scripts/load_bigquery.py): a
        # null would stay "unique" and pass only the check above, but would
        # fail the BigQuery load.
        check(streams["stream_id"].notna().all(),
              f"stream_id has no nulls ({streams['stream_id'].isna().sum():,} rows)")
        check(streams["stream_id"].is_unique,
              f"stream_id is unique ({len(streams) - streams['stream_id'].nunique():,} duplicates)")

    # --- uniqueness and completeness of dimension keys ------------------
    for name, frame, key in (("dim_user", users, "user_id"),
                             ("dim_track", tracks, "track_id"),
                             ("dim_platform", platforms, "platform_id"),
                             ("dim_time", calendar, "time_key")):
        check(frame[key].notna().all(), f"{name}.{key} has no nulls")
        check(frame[key].is_unique, f"{name}.{key} is unique")

    # --- referential integrity ---------------------------------------
    # dim_time was never read here before: Q5 and Q10 do an INNER JOIN
    # against it, so a missing time_key would drop rows from the
    # denominator with no test catching it.
    check(streams["track_id"].isin(tracks["track_id"]).all(), "every fact.track_id exists in dim_track")
    check(streams["platform_id"].isin(platforms["platform_id"]).all(), "every fact.platform_id exists in dim_platform")
    check(streams["user_id"].isin(users["user_id"]).all(), "every fact.user_id exists in dim_user")
    check(streams["listen_date"].isin(calendar["time_key"]).all(),
          "every fact.listen_date exists in dim_time")

    # --- value domains ------------------------------------------------
    check(streams["listen_hour"].between(0, 23).all(), "listen_hour within 0..23")
    check((streams["listen_duration_sec"] >= 0).all(), "listen_duration_sec is non-negative")
    check((streams["revenue_generated"] >= 0).all(), "revenue_generated is non-negative")
    check(set(streams["stream_source"].unique()) <= {"Algorithmic", "Editorial", "Search"},
          "stream_source values are within the known set")
    check(set(users["subscription_plan"].unique()) <= {"Free", "Premium Individual", "Premium Student", "Premium Family"},
          "subscription_plan values are within the known set")

    # --- temporal integrity ----------------------------------------
    # The 09/03 audit found 13.7% of streams BEFORE the user's signup and
    # 2.4% AFTER churn: dates were drawn globally and the user assigned
    # afterward. Nothing failed — only retention and seasonality stopped
    # meaning anything. This check exists so that defect can't come back
    # silently.
    if {"signup_date", "churn_date"}.issubset(users.columns):
        windows = users.set_index("user_id")[["signup_date", "churn_date"]]
        f = streams[["user_id", "listen_date"]].join(windows, on="user_id")
        day = pd.to_datetime(f["listen_date"])
        before = (day < pd.to_datetime(f["signup_date"])).sum()
        # >= not >: the generator defines churn_date as the first day the
        # user is NO LONGER active (scripts/generate_datasets.py), so a
        # stream on that exact day also violates the model. With `>` an
        # external dataset with that off-by-one would pass this gate.
        after = (day >= pd.to_datetime(f["churn_date"])).sum()
        check(before == 0, f"no stream precedes signup ({before:,} rows)")
        check(after == 0, f"no stream follows churn ({after:,} rows)")

    # --- economic coherence -------------------------------------------
    # The model is asymmetric on purpose: revenue accrues on every stream
    # (it comes from the subscription), royalty only on a stream that was
    # actually listened to. That asymmetry is what produces the 52.4% Gross
    # Margin documented in the dashboard — with royalty on every stream it
    # would be a flat 32%. If the generator went back to symmetric, the
    # dashboard figure would stop being reproducible without anything
    # failing.
    skipped = streams["is_skipped"].astype(bool)
    check((streams.loc[skipped, "royalty_cost"] == 0).all(),
          f"no royalty on skipped streams "
          f"({(streams.loc[skipped, 'royalty_cost'] > 0).sum():,} rows)")
    check((streams.loc[~skipped, "royalty_cost"] > 0).all(),
          "every consumed stream pays a royalty")
    margin = 1 - streams["royalty_cost"].sum() / streams["revenue_generated"].sum()
    check(abs(margin - 0.524) < 0.015,
          f"Gross Margin reproduces the dashboard's 52.4% ({margin:.1%})")

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
