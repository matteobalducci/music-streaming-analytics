.PHONY: help install generate validate charts load dbt-build all clean

PROJECT ?= your-gcp-project
DATASET ?= streaming

help:            ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:         ## Install Python dependencies
	pip install -r requirements.txt

generate:        ## Regenerate the full dataset (1.2M rows, seeded)
	python scripts/generate_datasets.py --out data/ --users 50000 --seed 42

validate:        ## Run the data-quality checks
	python scripts/validate_data.py --dir data

charts:          ## Regenerate the README charts from the data
	python scripts/make_charts.py

load:            ## Load the star schema into BigQuery (set PROJECT=...)
	python scripts/load_bigquery.py --project $(PROJECT) --dataset $(DATASET)

dbt-build:       ## Build + test the dbt models
	cd dbt/streaming && dbt build

all: validate load dbt-build   ## Validate, load to BigQuery, build dbt

clean:           ## Remove generated artifacts
	rm -f data/F_Streams.csv
	rm -rf dbt/streaming/target dbt/streaming/logs
