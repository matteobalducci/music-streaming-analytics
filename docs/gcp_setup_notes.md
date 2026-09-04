# GCP setup notes — things that bit me

Three real snags hit while setting this up on a fresh GCP project, none obvious from
the error messages. Documented here in case future-me (or anyone else running this)
hits the same wall.

---

## 1. Date-partitioned load jobs silently write zero rows on a no-billing project

**Symptom:** `make load` reports success (`✓ F_Streams  1,215,000 rows`), but
`SELECT COUNT(*)` on the table returns `0`. The load job itself shows `state: DONE`,
`errors: None`, and its own statistics report `outputRows: 1215000` — so nothing in
the job status hints that the write didn't actually land.

**Cause:** the fact table is loaded with `time_partitioning(field="listen_date")`
(intentional — a real warehouse partitions its biggest fact table by date to control
bytes scanned). On a GCP project with **no billing account linked** — BigQuery's free
"sandbox" mode — a date-partitioned load job silently no-ops the write instead of
failing or erroring. Confirmed with a minimal 2-row repro: identical load, partitioned
→ 0 rows persisted; same load without partitioning → 2 rows persisted, immediately
queryable. Clustering alone (no time partitioning) is unaffected.

**Fix:**
- **Enable billing on the project.** The dataset here is ~102 MB — nowhere near
  BigQuery's free tier (10 GB storage / 1 TB queries per month), so this costs nothing
  in practice; billing just needs to be *linked* for partitioned loads to actually
  persist data.
- **Until then:** load the raw `F_Streams` landing table (`fct_streams` is what dbt
  *builds* from it, not what this script loads) without `time_partitioning` — keep
  `clustering_fields=["track_id", "stream_source"]`, which works fine unbilled:
  ```bash
  NO_PARTITION=1 make deploy PROJECT=your-gcp-project     # or: make load NO_PARTITION=1 PROJECT=...
  NO_PARTITION=1 PROJECT=your-gcp-project ./scripts/load_bigquery.sh   # bq CLI variant
  ```
  This gets you a fully queryable table today, just without partition pruning — the
  partitioning design is still correct and documented in `scripts/load_bigquery.py`;
  re-enable it (drop `NO_PARTITION`) once billing is linked. `load_bigquery.py` now
  refuses to proceed silently if a load lands zero rows — the exact failure mode this
  section describes — so a partitioned load attempted here fails loudly instead of
  looking like success.

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

## 3. `pip install google-cloud-bigquery` fails outright on an x86_64-Python macOS setup

**Symptom:** not a slow build like #2 above — a hard failure. `pip install` tries to
compile `cryptography` from source and dies with something like
`Failed to build a native library through cargo … Could not find directory of OpenSSL
installation`, because a Rust/`cargo` + OpenSSL toolchain isn't installed (and
shouldn't need to be, for a dependency three levels removed from anything this repo
does directly).

**Cause:** `google-cloud-bigquery` pulls in `google-auth[pyopenssl]`, which depends on
`cryptography`. `cryptography` stopped publishing macOS **x86_64** wheels starting at
**49.0.0** — every release from 49.0.0 on ships only `macosx_11_0_arm64` (Apple
Silicon). The last release with an x86_64-capable wheel is **48.0.1** (a
`macosx_10_9_universal2` build, covering both architectures). Left unpinned, pip
resolves the newest `cryptography` release, finds no wheel for an x86_64 Python on
macOS — Intel Macs, and Apple Silicon Macs running an x86_64 Python build (e.g. an
older Anaconda install under Rosetta) both hit this — and falls back to a source
build that fails without the Rust toolchain. `SYSTEM_VERSION_COMPAT=0` (the fix for
\#2) does **not** help here: that fixes a wheel-tag *mismatch*, this is a wheel that
genuinely doesn't exist for this platform at the newer version.

**Fix:** `requirements-cloud.txt` pins `cryptography<49`, so pip resolves 48.0.1 (or
whichever pre-49 release satisfies everything else) and gets a real wheel instead of
trying to build from source. Confirmed: without the pin, `pip download --no-deps
cryptography` on this machine (x86_64 Python) only offers a `.tar.gz`; with the pin,
it resolves straight to a `macosx_10_9_universal2` wheel.
