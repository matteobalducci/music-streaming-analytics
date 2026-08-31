# GCP setup notes — things that bit me

Two real snags hit while setting this up on a fresh GCP project, neither obvious from
the error messages. Documented here in case future-me (or anyone else running this)
hits the same wall.

---

## 1. Date-partitioned load jobs silently write zero rows on a no-billing project

**Symptom:** `make load` reports success (`✓ fct_streams  1,227,355 rows`), but
`SELECT COUNT(*)` on the table returns `0`. The load job itself shows `state: DONE`,
`errors: None`, and its own statistics report `outputRows: 1227355` — so nothing in
the job status hints that the write didn't actually land.

**Cause:** `fct_streams` is loaded with `time_partitioning(field="listen_date")`
(intentional — a real warehouse partitions its biggest fact table by date to control
bytes scanned). On a GCP project with **no billing account linked** — BigQuery's free
"sandbox" mode — a date-partitioned load job silently no-ops the write instead of
failing or erroring. Confirmed with a minimal 2-row repro: identical load, partitioned
→ 0 rows persisted; same load without partitioning → 2 rows persisted, immediately
queryable. Clustering alone (no time partitioning) is unaffected.

**Fix:**
- **Enable billing on the project.** The dataset here is ~117 MB — nowhere near
  BigQuery's free tier (10 GB storage / 1 TB queries per month), so this costs nothing
  in practice; billing just needs to be *linked* for partitioned loads to actually
  persist data.
- **Until then:** load `fct_streams` without `time_partitioning` (keep
  `clustering_fields=["track_id", "stream_source"]`, which works fine unbilled). This
  gets you a fully queryable table today, just without partition pruning — the
  partitioning design is still correct and documented in `scripts/load_bigquery.py`;
  re-enable it once billing is linked.

## 2. `pip install google-cloud-bigquery` falls back to compiling `grpcio` from source

**Symptom:** `pip install` hangs for 15-20+ minutes building `grpcio` and its C++
dependencies (`clang` processes chewing CPU), instead of pulling a prebuilt wheel in
seconds.

**Cause:** on an Intel Mac running an older Anaconda Python build, `platform.platform()`
can report a legacy compatibility version (`macOS-10.16-...`) instead of the real OS
version, via macOS's `SYSTEM_VERSION_COMPAT` shim. `pip`'s wheel-tag matching sees
`10.16` and skips wheels built for the actual (newer) OS version, forcing a source
build of anything without an old-macOS wheel — `grpcio` included.

**Fix:**
```bash
SYSTEM_VERSION_COMPAT=0 pip install google-cloud-bigquery
```
This makes Python report the real macOS version, so pip picks the prebuilt wheel
instead of compiling from source. Confirmed: `platform.platform()` went from
`macOS-10.16-x86_64-i386-64bit` to `macOS-14.5-x86_64-i386-64bit` with the variable
set, and the same install went from a 20-minute source build to a few seconds.
