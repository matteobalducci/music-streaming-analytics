.PHONY: help install install-dbt generate sample test validate charts load dbt-deps dbt-build check-project check-dbt-target all deploy clean

PROJECT ?= your-gcp-project
DATASET ?= streaming

help:            ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:         ## Install core Python dependencies (the local, no-cloud-needed path)
	pip install -r requirements.txt

install-dbt:     ## Install BigQuery/dbt dependencies (needed before `make load` / `make deploy` / `make dbt-build`)
	pip install -r requirements-cloud.txt

generate:        ## Regenerate the full dataset (1.2M rows, seeded)
	python scripts/generate_datasets.py --out data/ --users 45000 --seed 42

sample:          ## Rebuild the committed public sample from the full fact table
	python scripts/make_sample.py --dir data --users 4000 --seed 42

test:            ## Assert the README's headline numbers still hold
	python -m pytest tests/ -v

validate:        ## Run the data-quality checks (full table and public sample)
	python scripts/validate_data.py --dir data
	python scripts/validate_data.py --dir data --fact data/sample/F_Streams_sample.csv

charts:          ## Regenerate the README charts from the data
	python scripts/make_charts.py

load:            ## Load the star schema into BigQuery (set PROJECT=..., NO_PARTITION=1 on a no-billing project)
	python scripts/load_bigquery.py --project "$(PROJECT)" --dataset "$(DATASET)" $(if $(NO_PARTITION),--no-partition,)

dbt-deps:        ## Resolve dbt package dependencies (none currently declared; a no-op until one is added)
	cd dbt/streaming && dbt deps

dbt-build: dbt-deps  ## Build + test the dbt models
	cd dbt/streaming && dbt build

all: generate sample validate test  ## Everything that runs locally, no cloud needed

# The check has to be a PREREQUISITE, not the first line of the recipe: as a
# recipe line it ran after `load`, so `make deploy` without PROJECT still
# attempted the load to 'your-gcp-project' before complaining.
check-project:
	@test "$(PROJECT)" != "your-gcp-project" || \
		(echo "Set PROJECT=<your-gcp-project> first" && exit 1)

# `load` writes to the PROJECT/DATASET passed on the command line; `dbt
# build` reads its OWN target from ~/.dbt/profiles.yml, which the Makefile
# never touches. Without this check the two could silently diverge —
# `deploy` would load one place and dbt would build another, and the final
# echo would still claim success. Verified with `make check-project
# PROJECT=<wrong>`: it stops.
check-dbt-target:
	python scripts/check_dbt_target.py --project "$(PROJECT)" --dataset "$(DATASET)" \
		$(if $(ALLOW_UNVERIFIED_TARGET),--allow-unverified-target,)

# Without .NOTPARALLEL, `make -j deploy` could run the sibling prerequisites
# out of order — the load could start before check-dbt-target has approved
# it. Nothing in this repo's own instructions invokes `-j`, but the target
# shouldn't depend on how it's called to stay correct.
.NOTPARALLEL: deploy

deploy: check-project check-dbt-target load dbt-build  ## Load to BigQuery and build dbt (needs PROJECT=...)
	@echo "loaded into $(PROJECT).$(DATASET) and dbt models built"

clean:           ## Remove generated artifacts
	rm -f data/F_Streams.csv
	rm -rf dbt/streaming/target dbt/streaming/logs
