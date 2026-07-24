#!/usr/bin/env bash
# Load the star schema into BigQuery using the bq CLI. Requires gcloud + auth.
#   PROJECT=my-gcp-project ./scripts/load_bigquery.sh
set -euo pipefail
PROJECT="${PROJECT:?set PROJECT=your-gcp-project}"
DATASET="${DATASET:-streaming}"
LOCATION="${LOCATION:-EU}"
DIR="$(cd "$(dirname "$0")/../data" && pwd)"
FACT="$DIR/F_Streams.csv"
[[ -f "$FACT" ]] || { echo "! using sample"; FACT="$DIR/sample/F_Streams_sample.csv"; }

bq --location="$LOCATION" mk --dataset --force "$PROJECT:$DATASET" || true

bq load --replace --source_format=CSV --skip_leading_rows=1 "$PROJECT:$DATASET.dim_user" "$DIR/D_Users.csv" \
  user_id:INT64,country:STRING,signup_date:DATE,subscription_plan:STRING,signup_channel:STRING,churn_date:DATE
bq load --replace --source_format=CSV --skip_leading_rows=1 "$PROJECT:$DATASET.dim_track" "$DIR/D_Tracks.csv" \
  track_id:INT64,track_title:STRING,artist_id:INT64,main_genre:STRING,release_date:DATE,bpm:INT64,energy:FLOAT64,valence:FLOAT64,danceability:FLOAT64,total_duration_sec:INT64
bq load --replace --source_format=CSV --skip_leading_rows=1 "$PROJECT:$DATASET.dim_platform" "$DIR/D_Platform.csv" \
  platform_id:INT64,service_name:STRING
bq load --replace --source_format=CSV --skip_leading_rows=1 "$PROJECT:$DATASET.dim_time" "$DIR/D_Time.csv" \
  time_key:DATE,year:INT64,month:INT64,day_of_week:STRING,is_weekend:BOOL
bq load --replace --source_format=CSV --skip_leading_rows=1 \
  --time_partitioning_field=listen_date --clustering_fields=track_id,stream_source \
  "$PROJECT:$DATASET.fct_streams" "$FACT" \
  user_id:INT64,track_id:INT64,platform_id:INT64,listen_date:DATE,listen_hour:INT64,device_type:STRING,connection_type:STRING,stream_source:STRING,is_skipped:BOOL,is_liked:BOOL,listen_duration_sec:INT64,royalty_cost:FLOAT64,revenue_generated:FLOAT64
echo "done."
