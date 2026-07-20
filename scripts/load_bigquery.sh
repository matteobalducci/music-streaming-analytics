#!/usr/bin/env bash
# Load the star schema into BigQuery using the bq CLI (alternative to the
# Python loader). Requires the Google Cloud SDK (`gcloud`, `bq`) and auth.
#
# Usage:
#   PROJECT=my-gcp-project ./scripts/load_bigquery.sh
#   PROJECT=my-gcp-project DATASET=streaming LOCATION=EU ./scripts/load_bigquery.sh
set -euo pipefail

PROJECT="${PROJECT:?set PROJECT=your-gcp-project}"
DATASET="${DATASET:-streaming}"
LOCATION="${LOCATION:-EU}"
DIR="$(cd "$(dirname "$0")/../data" && pwd)"

FACT="$DIR/F_Streams.csv"
[[ -f "$FACT" ]] || { echo "! using sample (run generate_datasets.py for full data)"; FACT="$DIR/sample/F_Streams_sample.csv"; }

echo "creating dataset $PROJECT:$DATASET ($LOCATION)"
bq --location="$LOCATION" mk --dataset --force "$PROJECT:$DATASET" || true

echo "loading dimensions"
bq load --replace --source_format=CSV --skip_leading_rows=1 \
  "$PROJECT:$DATASET.dim_track" "$DIR/D_Tracks.csv" \
  track_id:INT64,track_title:STRING,artist_id:INT64,main_genre:STRING,total_duration_sec:INT64,is_frontline:BOOL

bq load --replace --source_format=CSV --skip_leading_rows=1 \
  "$PROJECT:$DATASET.dim_platform" "$DIR/D_Platform.csv" \
  platform_id:INT64,service_name:STRING

bq load --replace --source_format=CSV --skip_leading_rows=1 \
  "$PROJECT:$DATASET.dim_time" "$DIR/D_Time.csv" \
  time_key:DATE,year:INT64,month:INT64,day_of_week:STRING,is_weekend:BOOL

echo "loading fact table (partitioned + clustered)"
bq load --replace --source_format=CSV --skip_leading_rows=1 \
  --time_partitioning_field=listen_date \
  --clustering_fields=track_id,stream_source \
  "$PROJECT:$DATASET.fct_streams" "$FACT" \
  user_id:INT64,track_id:INT64,platform_id:INT64,listen_date:DATE,listen_hour:INT64,stream_source:STRING,listen_duration_sec:INT64,is_skipped:BOOL,is_liked:BOOL,is_subscriber:BOOL

echo "done — try:  bq query --use_legacy_sql=false 'SELECT stream_source, ROUND(AVG(CAST(is_skipped AS INT64))*100,1) skip FROM \`$PROJECT.$DATASET.fct_streams\` GROUP BY 1 ORDER BY 2 DESC'"
