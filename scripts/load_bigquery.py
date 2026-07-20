"""
Load the star-schema CSVs into BigQuery.

Creates the target dataset (if missing) and loads the four tables with
explicit schemas — partitioning and clustering the fact table the way a
production warehouse would. Idempotent: each load truncates and rewrites,
so you can re-run it safely.

Prerequisites:
    pip install google-cloud-bigquery
    gcloud auth application-default login      # or set GOOGLE_APPLICATION_CREDENTIALS

Usage:
    python scripts/load_bigquery.py --project my-gcp-project --dataset streaming
    python scripts/load_bigquery.py --project my-gcp-project --fact data/F_Streams.csv

By default the fact table is loaded from data/F_Streams.csv; if that file is
absent (it is git-ignored — regenerate it with scripts/generate_datasets.py),
the script falls back to the committed 100k-row sample so it always runs.
"""

import argparse
import os
import sys

from google.cloud import bigquery

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "data"))

# Explicit schemas — never rely on autodetect for a warehouse you trust.
SCHEMAS = {
    "fct_streams": [
        bigquery.SchemaField("user_id", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("track_id", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("platform_id", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("listen_date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("listen_hour", "INT64"),
        bigquery.SchemaField("stream_source", "STRING"),
        bigquery.SchemaField("listen_duration_sec", "INT64"),
        bigquery.SchemaField("is_skipped", "BOOL"),
        bigquery.SchemaField("is_liked", "BOOL"),
        bigquery.SchemaField("is_subscriber", "BOOL"),
    ],
    "dim_track": [
        bigquery.SchemaField("track_id", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("track_title", "STRING"),
        bigquery.SchemaField("artist_id", "INT64"),
        bigquery.SchemaField("main_genre", "STRING"),
        bigquery.SchemaField("total_duration_sec", "INT64"),
        bigquery.SchemaField("is_frontline", "BOOL"),
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


def resolve_fact_path(explicit: str | None) -> str:
    if explicit:
        return explicit
    full = os.path.join(DATA, "F_Streams.csv")
    if os.path.exists(full):
        return full
    sample = os.path.join(DATA, "sample", "F_Streams_sample.csv")
    print("  ! data/F_Streams.csv not found — loading the 100k sample instead.")
    print("    (run `python scripts/generate_datasets.py` for the full 1.2M rows)")
    return sample


def load_table(client: bigquery.Client, dataset: str, table: str, path: str) -> None:
    table_id = f"{client.project}.{dataset}.{table}"
    job_config = bigquery.LoadJobConfig(
        schema=SCHEMAS[table],
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    if table == "fct_streams":
        job_config.time_partitioning = bigquery.TimePartitioning(field="listen_date")
        job_config.clustering_fields = ["track_id", "stream_source"]

    with open(path, "rb") as fh:
        job = client.load_table_from_file(fh, table_id, job_config=job_config)
    job.result()  # wait

    loaded = client.get_table(table_id)
    print(f"  ✓ {table:<13} {loaded.num_rows:>9,} rows  ←  {os.path.basename(path)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the streaming star schema into BigQuery")
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT"),
                        help="GCP project id (or set GOOGLE_CLOUD_PROJECT)")
    parser.add_argument("--dataset", default="streaming")
    parser.add_argument("--location", default="EU")
    parser.add_argument("--fact", default=None, help="path to the fact CSV (default: data/F_Streams.csv)")
    args = parser.parse_args()

    if not args.project:
        sys.exit("error: pass --project or set GOOGLE_CLOUD_PROJECT")

    client = bigquery.Client(project=args.project, location=args.location)

    # Create dataset if needed
    ds_ref = bigquery.Dataset(f"{args.project}.{args.dataset}")
    ds_ref.location = args.location
    client.create_dataset(ds_ref, exists_ok=True)
    print(f"dataset ready: {args.project}.{args.dataset} ({args.location})")

    files = {
        "dim_track": os.path.join(DATA, "D_Tracks.csv"),
        "dim_platform": os.path.join(DATA, "D_Platform.csv"),
        "dim_time": os.path.join(DATA, "D_Time.csv"),
        "fct_streams": resolve_fact_path(args.fact),
    }
    for table, path in files.items():
        load_table(client, args.dataset, table, path)

    print("\ndone — query it, or run `cd dbt/streaming && dbt build`.")


if __name__ == "__main__":
    main()
