"""
Guards `make deploy` against loading one BigQuery project/dataset and then
building dbt against another.

WHY THIS EXISTS
----------------
`make deploy` runs the loader with `PROJECT`/`DATASET` from the command line,
then runs `dbt build` — which reads its own target from `~/.dbt/profiles.yml`,
a file the Makefile never touches. If the two disagree, `dbt build` either
fails against a dataset that was never loaded, or silently builds against a
project the user forgot they had configured — while the final `deploy` recipe
still echoes a single, confident "loaded and built" message.

This script resolves the same profile dbt itself would use (profiles.yml +
dbt_project.yml, no live connection) and fails loudly on a mismatch, before
`dbt build` runs at all.

Known limitation: profiles.yml is read as plain YAML, not through dbt's own
Jinja context — a profile that uses `{{ env_var(...) }}` for project/dataset
(common in CI setups, not what profiles.example.yml ships) can't be resolved
here without re-implementing dbt's own renderer.

FIX 2026-09-03: the first version, faced with a templated value, printed a
warning and exited SUCCESSFULLY — i.e. it let through exactly the case this
script exists to catch: a profile with `project: "{{ env_var('BQ_PROJECT') }}"`
could resolve to a project different from the one just loaded, and the deploy
would proceed anyway. It now fails CLOSED instead — the same choice
`load_bigquery.py` already makes for a load that lands zero rows: a deploy
into the wrong project costs more than one extra manual check. Anyone who
genuinely runs a templated profile can bypass with `--allow-unverified-target`
after confirming by hand that it targets the right project.

Usage:
    python scripts/check_dbt_target.py --project X --dataset Y
    python scripts/check_dbt_target.py --project X --dataset Y --allow-unverified-target
"""

import argparse
import os
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
DBT_DIR = os.path.normpath(os.path.join(HERE, "..", "dbt", "streaming"))


def is_templated(value) -> bool:
    """True if a profile value is Jinja we can't render without dbt's own context."""
    return isinstance(value, str) and "{{" in value


def resolve_target():
    with open(os.path.join(DBT_DIR, "dbt_project.yml"), encoding="utf-8") as fh:
        profile_name = yaml.safe_load(fh)["profile"]

    profiles_dir = os.environ.get("DBT_PROFILES_DIR", os.path.expanduser("~/.dbt"))
    profiles_path = os.path.join(profiles_dir, "profiles.yml")
    if not os.path.exists(profiles_path):
        print(f"! {profiles_path} not found — copy dbt/streaming/profiles.example.yml "
              f"to ~/.dbt/profiles.yml and fill it in before running `make deploy`.")
        sys.exit(1)

    with open(profiles_path, encoding="utf-8") as fh:
        profiles = yaml.safe_load(fh)

    if profile_name not in profiles:
        print(f"! profile '{profile_name}' required by dbt_project.yml does not exist "
              f"in {profiles_path}")
        sys.exit(1)

    profile = profiles[profile_name]
    target_name = profile.get("target", "default")
    if is_templated(target_name):
        return None, None, profiles_path, True

    outputs = profile.get("outputs", {})
    if target_name not in outputs:
        print(f"! target '{target_name}' not defined under '{profile_name}.outputs' in "
              f"{profiles_path}")
        sys.exit(1)

    output = outputs[target_name]
    project, dataset = output.get("project"), output.get("dataset")
    templated = is_templated(project) or is_templated(dataset)
    return project, dataset, profiles_path, templated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--allow-unverified-target", action="store_true",
                        help="proceed even if the profile can't be resolved (Jinja/env_var) — "
                             "only after checking by hand that it targets the right project")
    args = parser.parse_args()

    dbt_project, dbt_dataset, profiles_path, templated = resolve_target()

    if templated:
        print(f"! {profiles_path} uses a Jinja-templated target/project/dataset "
              f"(e.g. env_var) — can't be rendered without dbt's own context, so it can't "
              f"be verified.")
        if args.allow_unverified_target:
            print("  --allow-unverified-target passed: proceeding without verification. "
                  "You're the one who confirmed by hand that the profile targets the "
                  "right project.")
            return
        print("  `make deploy` stopped: can't rule out dbt building against a project "
              "different from the one just loaded. Check the profile by hand, then rerun "
              "with --allow-unverified-target (or ALLOW_UNVERIFIED_TARGET=1 with "
              "`make deploy`).")
        sys.exit(1)

    mismatch = []
    if dbt_project != args.project:
        mismatch.append(f"project: loaded '{args.project}', dbt would build "
                        f"'{dbt_project}'")
    if dbt_dataset != args.dataset:
        mismatch.append(f"dataset: loaded '{args.dataset}', dbt would build "
                        f"'{dbt_dataset}'")

    if mismatch:
        print("! `make deploy` stopped: PROJECT/DATASET passed don't match the dbt target "
              f"resolved from {profiles_path}:")
        for m in mismatch:
            print(f"    - {m}")
        print("  Align PROJECT=/DATASET= with the profile, or update the profile, before "
              "rerunning.")
        sys.exit(1)

    print(f"✓ PROJECT/DATASET match the dbt target ({dbt_project}.{dbt_dataset})")


if __name__ == "__main__":
    main()
