#!/usr/bin/env bash
# Load the CSVs into BigQuery using the bq CLI. Requires gcloud + auth.
# The four dimensions load direct-to-final (dim_user, dim_track, dim_platform,
# dim_time) — nothing downstream rebuilds a table under those names. F_Streams is
# the exception: it's a raw landing table that `dbt build` (dbt/streaming) reads and
# rebuilds as the enriched final `fct_streams` mart, so raw and final need different
# names. Run `cd dbt/streaming && dbt build` afterward to get `fct_streams`.
#   PROJECT=my-gcp-project ./scripts/load_bigquery.sh
#   NO_PARTITION=1 PROJECT=my-gcp-project ./scripts/load_bigquery.sh   # no-billing project — see docs/gcp_setup_notes.md#1
set -euo pipefail
PROJECT="${PROJECT:?set PROJECT=your-gcp-project}"
DATASET="${DATASET:-streaming}"
LOCATION="${LOCATION:-EU}"
DIR="$(cd "$(dirname "$0")/../data" && pwd)"
FACT="$DIR/F_Streams.csv"
[[ -f "$FACT" ]] || { echo "! using sample"; FACT="$DIR/sample/F_Streams_sample.csv"; }

# A date-partitioned load silently writes zero rows on a no-billing project
# (docs/gcp_setup_notes.md#1), and `bq load --replace` fails loudly instead if
# F_Streams already exists WITHOUT partitioning from an earlier no-billing
# load — the two partitioning specs can't be reconciled by a load job.
PARTITION_FLAG="--time_partitioning_field=listen_date"
[[ -n "${NO_PARTITION:-}" ]] && PARTITION_FLAG=""

bq --location="$LOCATION" mk --dataset --force "$PROJECT:$DATASET" || { bq show "$PROJECT:$DATASET" >/dev/null 2>&1 || { echo "error: dataset creation failed" >&2; exit 1; }; }

# Mirrors the check in load_bigquery.py: a date-partitioned load reports
# state DONE / errors None while silently writing zero rows on a no-billing
# project (docs/gcp_setup_notes.md#1) — `bq load`'s own exit code does not
# see this, so it has to be checked separately via table metadata.
#
# FIX 03/09 (self-review round 2): the first version piped `bq show` straight
# into grep. `bq` writes its OWN error text (e.g. "Project ... is not found")
# to stdout, not stderr — confirmed live. Piped into grep, that text matches
# nothing, the pipeline fails, and under `set -euo pipefail` the assignment
# aborts the script immediately, before the 0-rows check is ever reached and
# before bq's own error is ever printed: a `bq show` failure of ANY kind
# (wrong project, permission hiccup, transient API error) died completely
# silently — worse than not checking at all. Now bq's exit status is checked
# on its own, outside any pipe, so its error text is never swallowed.
check_nonempty() {
  local table="$1" json rows
  if ! json="$(bq show --format=json "$PROJECT:$DATASET.$table" 2>&1)"; then
    echo "error: bq show failed for $PROJECT:$DATASET.$table:" >&2
    echo "$json" >&2
    exit 1
  fi
  rows="$(echo "$json" | grep -o '"numRows":"[0-9]*"' | grep -o '[0-9]*')"
  if [[ "${rows:-0}" == "0" ]]; then
    echo "error: $PROJECT:$DATASET.$table loaded with 0 rows — on a no-billing project this usually means a date-partitioned load silently no-op'd; retry with NO_PARTITION=1 (see docs/gcp_setup_notes.md#1)" >&2
    exit 1
  fi
}

# FIX 03/09 (self-review round 18): `bq load`'s inline text-schema shorthand
# (name:type,name:type,...) has no way to express a column's `mode` — only a
# JSON schema file can set REQUIRED. This script used to load every table
# through that shorthand, so all five primary/foreign keys ended up NULLABLE
# in BigQuery here even though load_bigquery.py sets them REQUIRED and
# sql/ddl/star_schema.sql documents them as NOT NULL — the two loaders
# silently diverged despite being presented as interchangeable. JSON schema
# files (written to a temp dir, cleaned up on exit) now give this script the
# exact same schema, key-for-key, as the Python loader.
SCHEMA_DIR="$(mktemp -d)"
trap 'rm -rf "$SCHEMA_DIR"' EXIT

cat > "$SCHEMA_DIR/dim_user.json" <<'JSON'
[
  {"name": "user_id", "type": "INT64", "mode": "REQUIRED"},
  {"name": "country", "type": "STRING"},
  {"name": "signup_date", "type": "DATE"},
  {"name": "subscription_plan", "type": "STRING"},
  {"name": "signup_channel", "type": "STRING"},
  {"name": "churn_date", "type": "DATE"}
]
JSON

cat > "$SCHEMA_DIR/dim_track.json" <<'JSON'
[
  {"name": "track_id", "type": "INT64", "mode": "REQUIRED"},
  {"name": "track_title", "type": "STRING"},
  {"name": "artist_id", "type": "INT64"},
  {"name": "main_genre", "type": "STRING"},
  {"name": "release_date", "type": "DATE"},
  {"name": "bpm", "type": "INT64"},
  {"name": "energy", "type": "FLOAT64"},
  {"name": "valence", "type": "FLOAT64"},
  {"name": "danceability", "type": "FLOAT64"},
  {"name": "total_duration_sec", "type": "INT64"}
]
JSON

cat > "$SCHEMA_DIR/dim_platform.json" <<'JSON'
[
  {"name": "platform_id", "type": "INT64", "mode": "REQUIRED"},
  {"name": "service_name", "type": "STRING"}
]
JSON

cat > "$SCHEMA_DIR/dim_time.json" <<'JSON'
[
  {"name": "time_key", "type": "DATE", "mode": "REQUIRED"},
  {"name": "year", "type": "INT64"},
  {"name": "month", "type": "INT64"},
  {"name": "day_of_week", "type": "STRING"},
  {"name": "is_weekend", "type": "BOOL"}
]
JSON

cat > "$SCHEMA_DIR/F_Streams.json" <<'JSON'
[
  {"name": "stream_id", "type": "INT64", "mode": "REQUIRED"},
  {"name": "user_id", "type": "INT64", "mode": "REQUIRED"},
  {"name": "track_id", "type": "INT64", "mode": "REQUIRED"},
  {"name": "platform_id", "type": "INT64", "mode": "REQUIRED"},
  {"name": "listen_date", "type": "DATE", "mode": "REQUIRED"},
  {"name": "listen_hour", "type": "INT64"},
  {"name": "device_type", "type": "STRING"},
  {"name": "connection_type", "type": "STRING"},
  {"name": "stream_source", "type": "STRING"},
  {"name": "is_skipped", "type": "BOOL"},
  {"name": "is_liked", "type": "BOOL"},
  {"name": "listen_duration_sec", "type": "INT64"},
  {"name": "royalty_cost", "type": "NUMERIC"},
  {"name": "revenue_generated", "type": "NUMERIC"}
]
JSON

bq load --replace --source_format=CSV --skip_leading_rows=1 "$PROJECT:$DATASET.dim_user" "$DIR/D_Users.csv" \
  "$SCHEMA_DIR/dim_user.json"
check_nonempty dim_user
bq load --replace --source_format=CSV --skip_leading_rows=1 "$PROJECT:$DATASET.dim_track" "$DIR/D_Tracks.csv" \
  "$SCHEMA_DIR/dim_track.json"
check_nonempty dim_track
bq load --replace --source_format=CSV --skip_leading_rows=1 "$PROJECT:$DATASET.dim_platform" "$DIR/D_Platform.csv" \
  "$SCHEMA_DIR/dim_platform.json"
check_nonempty dim_platform
bq load --replace --source_format=CSV --skip_leading_rows=1 "$PROJECT:$DATASET.dim_time" "$DIR/D_Time.csv" \
  "$SCHEMA_DIR/dim_time.json"
check_nonempty dim_time
bq load --replace --source_format=CSV --skip_leading_rows=1 \
  $PARTITION_FLAG --clustering_fields=track_id,stream_source \
  "$PROJECT:$DATASET.F_Streams" "$FACT" \
  "$SCHEMA_DIR/F_Streams.json"
check_nonempty F_Streams
echo "dimensions ready, F_Streams (raw) loaded — now run: cd dbt/streaming && dbt build"
