"""
Load the CSVs into BigQuery.

Creates the target dataset (if missing) and loads five tables with explicit schemas —
partitioning and clustering the fact table the way a production warehouse would.
Idempotent: each load truncates and rewrites.

The four dimensions load directly under their final star-schema names (dim_user,
dim_track, dim_platform, dim_time) — nothing downstream rebuilds a table under those
names, so there's no raw/final split needed for them. The fact table is the exception:
it loads into a raw landing table (`F_Streams`), because `dbt build` (dbt/streaming)
reads it and *rebuilds* it as the enriched final `fct_streams` mart (adds
completion_ratio, is_engaged_stream) — raw and final need different names, or the dbt
build becomes self-referential. Run `cd dbt/streaming && dbt build` after this script
to get `fct_streams`; the four dimensions are usable immediately.

Prerequisites:
    pip install google-cloud-bigquery
    gcloud auth application-default login      # or set GOOGLE_APPLICATION_CREDENTIALS

Usage:
    python scripts/load_bigquery.py --project my-gcp-project --dataset streaming
"""

import argparse
import os
import sys

from google.cloud import bigquery

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "data"))

SCHEMAS = {
    "F_Streams": [
        bigquery.SchemaField("stream_id", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("user_id", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("track_id", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("platform_id", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("listen_date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("listen_hour", "INT64"),
        bigquery.SchemaField("device_type", "STRING"),
        bigquery.SchemaField("connection_type", "STRING"),
        bigquery.SchemaField("stream_source", "STRING"),
        bigquery.SchemaField("is_skipped", "BOOL"),
        bigquery.SchemaField("is_liked", "BOOL"),
        bigquery.SchemaField("listen_duration_sec", "INT64"),
        bigquery.SchemaField("royalty_cost", "NUMERIC"),
        bigquery.SchemaField("revenue_generated", "NUMERIC"),
    ],
    "dim_user": [
        bigquery.SchemaField("user_id", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("country", "STRING"),
        bigquery.SchemaField("signup_date", "DATE"),
        bigquery.SchemaField("subscription_plan", "STRING"),
        bigquery.SchemaField("signup_channel", "STRING"),
        bigquery.SchemaField("churn_date", "DATE"),
    ],
    "dim_track": [
        bigquery.SchemaField("track_id", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("track_title", "STRING"),
        bigquery.SchemaField("artist_id", "INT64"),
        bigquery.SchemaField("main_genre", "STRING"),
        bigquery.SchemaField("release_date", "DATE"),
        bigquery.SchemaField("bpm", "INT64"),
        bigquery.SchemaField("energy", "FLOAT64"),
        bigquery.SchemaField("valence", "FLOAT64"),
        bigquery.SchemaField("danceability", "FLOAT64"),
        bigquery.SchemaField("total_duration_sec", "INT64"),
    ],
    "dim_platform": [
        bigquery.SchemaField("platform_id", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("service_name", "STRING"),
    ],
    "dim_time": [
        bigquery.SchemaField("time_key", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("year", "INT64"),
        bigquery.SchemaField("month", "INT64"),
        bigquery.SchemaField("day_of_week", "STRING"),
        bigquery.SchemaField("is_weekend", "BOOL"),
    ],
}

# table -> csv file (F_Streams is the raw landing name; the rest load direct-to-final)
FILES = {
    "dim_user": "D_Users.csv",
    "dim_track": "D_Tracks.csv",
    "dim_platform": "D_Platform.csv",
    "dim_time": "D_Time.csv",
    "F_Streams": "F_Streams.csv",
}


def resolve_fact_path() -> str:
    full = os.path.join(DATA, "F_Streams.csv")
    if os.path.exists(full):
        return full
    print("  ! data/F_Streams.csv not found — loading the committed sample instead.")
    print("    (run `python scripts/generate_datasets.py` for the full dataset)")
    return os.path.join(DATA, "sample", "F_Streams_sample.csv")


def load_table(client, dataset, table, path, partition=True):
    table_id = f"{client.project}.{dataset}.{table}"
    job_config = bigquery.LoadJobConfig(
        schema=SCHEMAS[table],
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    if table == "F_Streams":
        # WRITE_TRUNCATE reloads data into whatever table already exists; it
        # does not change that table's partitioning. If a prior load created
        # F_Streams unpartitioned (the --no-partition path below, taken on a
        # no-billing project per docs/gcp_setup_notes.md#1) and this run asks
        # for partitioning, BigQuery rejects the job outright with a clear
        # "Incompatible table partitioning specification" error — confirmed
        # live against a real no-billing project on 2026-09-03. That is the
        # good failure mode; the bad one (silent zero rows) is what happens if
        # partitioning is requested while billing is still unlinked, which is
        # exactly why this flag exists.
        if partition:
            job_config.time_partitioning = bigquery.TimePartitioning(field="listen_date")
        job_config.clustering_fields = ["track_id", "stream_source"]
    with open(path, "rb") as fh:
        client.load_table_from_file(fh, table_id, job_config=job_config).result()
    loaded = client.get_table(table_id)
    print(f"  ✓ {table:<13} {loaded.num_rows:>9,} rows  ←  {os.path.basename(path)}")
    if loaded.num_rows == 0:
        # A date-partitioned load silently writes zero rows on a no-billing
        # project (docs/gcp_setup_notes.md#1) — the job reports DONE/no
        # errors, `get_table` is the only place this is visible. Without this
        # check `make deploy` echoes success, `dbt build` builds an empty
        # (but schema-valid) mart, and every not_null/unique/relationships
        # test passes vacuously on zero rows.
        sys.exit(f"error: {table_id} loaded with 0 rows — on a no-billing project this usually "
                 f"means a date-partitioned load silently no-op'd; retry with --no-partition "
                 f"(see docs/gcp_setup_notes.md#1)")


def main():
    parser = argparse.ArgumentParser(description="Load the streaming star schema into BigQuery")
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    parser.add_argument("--dataset", default="streaming")
    parser.add_argument("--location", default="EU")
    parser.add_argument("--no-partition", action="store_true",
                        help="skip time partitioning on F_Streams — needed on a "
                             "no-billing project (see docs/gcp_setup_notes.md#1), "
                             "and required if F_Streams already exists unpartitioned")
    args = parser.parse_args()
    if not args.project:
        sys.exit("error: pass --project or set GOOGLE_CLOUD_PROJECT")

    client = bigquery.Client(project=args.project, location=args.location)
    ds = bigquery.Dataset(f"{args.project}.{args.dataset}")
    ds.location = args.location
    client.create_dataset(ds, exists_ok=True)
    print(f"dataset ready: {args.project}.{args.dataset} ({args.location})")

    for table, fname in FILES.items():
        path = resolve_fact_path() if table == "F_Streams" else os.path.join(DATA, fname)
        load_table(client, args.dataset, table, path, partition=not args.no_partition)

    print("\nraw tables loaded — now run `cd dbt/streaming && dbt build` to build the "
          "star schema (fct_streams, dim_user, dim_track, dim_platform, dim_time).")


if __name__ == "__main__":
    main()
