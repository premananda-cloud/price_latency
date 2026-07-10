# Interstate Corn Price Concurrency & Transmission Lag

Research sprint measuring how quickly corn price movements transmit between
two U.S. Corn Belt states, using USDA NASS QuickStats data. Primary pair is
Iowa (hub) → Ohio (local); a second pair, Iowa → Nebraska, has since been
run as a robustness check (see **Known limitations** below).

Originally scoped around Indian Agmarknet data (Delhi → Imphal spatial price
transmission); pivoted to USDA NASS after confirming the original data
source and geography didn't support the intended lag analysis. See
`docs/PLAN_v2.md` for the full account of what changed and why (`docs/PLAN.txt`
is the earlier, superseded version).

This document is meant to be a complete, accurate map of the code and its
outputs — the goal is that writing the paper should mean reading *this*,
not re-reading the source. See **Where to look when writing the paper** at
the bottom for a direct index from "I need X" to the exact file.

---

## Research question

When corn prices move in Iowa, how many months does it take for that
movement to show up in another Corn Belt state's price-received series —
and does the relationship (a) hold up against data the analysis never saw
during development, and (b) generalize beyond one specific pair of states?

---

## Data source

**USDA NASS QuickStats API** (`https://quickstats.nass.usda.gov/api/`).
Requires a free API key (`USDA_NASS_APIKEY` in `.env` at the project root).
`config.py` raises `RuntimeError` immediately on import if this isn't set —
every other module depends on `config.py`, so a missing key fails loudly at
the first line of any script, not deep inside a fetch call.

Commodity and geography were not assumed — they were empirically verified
before committing, via `fetch.py --scan`, which probes NASS's real
`get_counts` endpoint (not a query parameter on the main endpoint — NASS
doesn't support `count=true` there, it's a separate URI) across candidate
commodities/states before any real data pull.

Verified result: **CORN** gives 137 clean `MONTHLY` `PRICE RECEIVED`
records per state (2015–2026), no gaps, across every Corn Belt state
tested (Iowa, Ohio, Nebraska, Illinois). Fresh vegetables (the original
candidate) are `ANNUAL`-only in this data source and can't support a
sub-annual lag analysis — documented as a dead-end, not silently dropped.
See `docs/DATA_SOURCE.md` for the full verification writeup.

NASS QuickStats has no true daily frequency; `MONTHLY` is the floor. A
higher-frequency source (USDA AMS Market News daily grain bids) was
identified as a possible future addition but is out of scope for this pass
— see Limitations.

---

## Repo layout

```
.
├── src/                  — all code (see Module reference below)
├── data/
│   ├── raw/              — per-state cached API pulls (fetch.py's output)
│   └── processed/        — per-pair cleaned panels (clean.py's output)
├── figures/              — standalone plots from running analysis.py/
│                           validation.py directly (not via experiment.py)
├── experiments/          — tracked, self-contained runs (experiment.py's
│                           output) + registry.csv indexing all of them
├── docs/
│   ├── DATA_SOURCE.md    — commodity/geography verification writeup
│   ├── PLAN.txt / PLAN_v2.md — original plan and the pivot to NASS
│   ├── presentation_prep.md
│   ├── journal/          — dated working notes
│   └── Results/REPORT.md — full methodology + confirmed numbers (the
│                           reference doc — see below)
├── paper/                — manuscript drafts and reference papers
├── requirements.txt
└── .env                  — USDA_NASS_APIKEY (not committed)
```

(The repo root also has some non-project material — competition/
presentation admin files — that this README doesn't cover.)

---

## Module reference

Each module in `src/` is independently runnable via its own CLI and
independently testable (`clean.py` doesn't need network access,
`analysis.py` doesn't need to re-fetch, etc.). All of them import shared
paths/config from `config.py`.

### `config.py`
Central config. Resolves `BASE_DIR` from this file's own location (not
`cwd`), so every path works regardless of what directory a script is run
from. Loads `.env`, requires `USDA_NASS_APIKEY` (raises if missing).
Exports `RAW_DATA_DIR`, `PROCESSED_DATA_DIR`, `FIGURES_DIR`, `BASE_DIR`.

### `fetch.py` — NASS API client
- `fetch_price_data(commodity_desc, state_name, year_start, year_end, freq_desc="MONTHLY", statisticcat_desc="PRICE RECEIVED", agg_level_desc="STATE", save_raw=True, max_retries=3)` — one state, one query, with retry on network/5xx errors. Raises `NASSFetchError` on empty results, bad params, or the 50,000-record limit (`agg_level_desc=STATE` is what keeps queries under that limit).
- `fetch_multi_state(commodity_desc, states, year_start, year_end, ...)` — calls the above per state; this is what `pipeline.py` uses to get hub + local in one call.
- `check_frequency_availability(...)` / `scan_candidates(...)` — the availability probe behind `--scan`.
- Raw files are cached to `data/raw/` as: `{commodity}_{state}_{statisticcat-slug}_{freq}_{agglevel}_{year_start}_{year_end}.csv` (all lowercase, spaces in statisticcat become hyphens) — e.g. `corn_iowa_price-received_monthly_state_2015_2026.csv`.

CLI: `python fetch.py --commodity CORN --states IOWA,OHIO --year-start 2015 --year-end 2026 --freq MONTHLY [--scan]`

### `clean.py` — raw → aligned panel
- `load_raw(...)` — loads one state's cached CSV by the exact filename `fetch.py` wrote. If `year_start`/`year_end` aren't given, falls back to the most recent matching file for that commodity/state/freq/statcat/agg_level combo (glob + sort).
- `clean_state_series(df_raw, state_label)` — filters to `class_desc == "ALL CLASSES"` and `domain_desc == "TOTAL"` where present (avoids duplicate-date collisions from other breakdowns), parses `year` + `reference_period_desc` (e.g. "JAN") into a date, converts `Value` to float — suppression codes `(D)`, `(NA)`, `(Z)` become `NaN`. Drops duplicate dates (keeps first) with a printed warning if any occur.
- `build_panel(hub_series, local_series, hub_label, local_label)` — reindexes both series onto a **complete** monthly index (`freq="MS"`) so any missing month becomes an explicit `NaN` row rather than a silent gap, and prints a gap-count warning if any exist. Adds `{label}_returns` (pct change) for each state and a `spread` column (`local - hub`).
- `clean_and_save(...)` — runs the above for a hub/local pair and writes to `data/processed/{commodity}_{hub}_{local}_{freq}.csv` (lowercase) — e.g. `corn_iowa_ohio_monthly.csv`. This exact filename is also what `analysis.py`'s `load_panel()` expects, so `fetch.py`/`clean.py`'s naming and `analysis.py`'s loading are two ends of the same contract — this is the one place in the codebase where a filename convention has to stay in sync across three files.

CLI: `python clean.py --commodity CORN --hub IOWA --local OHIO [--year-start 2015 --year-end 2026]`

### `analysis.py` — the actual statistics
- `adf_test(series, label)` — Augmented Dickey-Fuller stationarity test.
- `tlcc(s1, s2, max_lag=12)` — time-lagged cross-correlation; positive lag k means `s1` leads `s2` by k periods. Raises `AnalysisError` if too few overlapping observations remain after dropping NaNs.
- `bootstrap_k_star_ci(s1, s2, max_lag=12, n_boot=1000, seed=42)` — bootstrap resample (with replacement), recomputes k* each draw, returns the 95% CI. Seed is fixed at 42 — not currently exposed as a CLI/pipeline argument.
- `run_granger(df, cause_col, effect_col, max_lag=12)` — Granger causality, one direction; `run_full_analysis` calls it both ways.
- `run_cointegration(price_a, price_b)` — Engle-Granger cointegration on price **levels** (not returns).
- `run_full_analysis(df, hub_state, local_state, max_lag=12)` — runs all of the above and returns one `report` dict: `adf_hub_price`, `adf_local_price`, `adf_hub_returns`, `adf_local_returns`, `tlcc_lags`, `tlcc_corr`, `k_star`, `peak_corr`, `k_star_ci`, `granger_hub_causes_local`, `granger_local_causes_hub`, `cointegration`. This dict is the shared currency every downstream module (`validation.py`, `pipeline.py`, `experiment.py`) passes around.
- `find_structural_break(series, label)` — Zivot-Andrews test (allows a unit root while searching for one break point). Returns `za_stat`, `p_value`, `break_date`. Deliberately distinguishes "candidate break date" (wherever the test statistic was minimized) from "statistically significant break" (`p_value < 0.05`) — a non-significant result means don't report the candidate date as real.
- `rolling_cointegration(price_a, price_b, window=60, step=1)` — rolls a fixed window across both series, running Engle-Granger at each step; returns a DataFrame indexed by window end date with `eg_score`, `p_value`, `cointegrated_5pct`. This is what characterizes *when* a long-run relationship holds vs. doesn't, rather than the single before/after split validation.py's backtest gives.
- `plot_tlcc`, `plot_spread`, `plot_rolling_cointegration` — save PNGs to `FIGURES_DIR` (patched to a per-experiment folder when called via `experiment.py`; otherwise the top-level `figures/`).

CLI: `python analysis.py --hub IOWA --local OHIO [--plot] [--spread-plot --holdout-start 2024-01-01] [--break-test] [--rolling-coint --rolling-window 60]`

### `validation.py` — two kinds of robustness check
1. **Temporal** — `split_panel`, `compare_reports`, `run_backtest`: splits into train/holdout, re-runs `run_full_analysis` on train only, and prints a stability comparison (k*, Granger direction, cointegration) against the full period. This is the original validation step: a lag number nothing checks against unseen data is just an assertion.
2. **Spatial/pair** — `run_pair_robustness(commodity_desc, hub_state, local_states, ...)`, `print_pair_robustness`, `plot_pair_robustness`: re-runs the same hub against a *list* of other local states, to check whether k*/Granger direction/cointegration are specific to one pair or generalize. A local state whose cleaned panel doesn't exist yet is recorded as a skipped row (`status != "ok"`), not a crash — one missing pair doesn't take down the whole check. This function only loads and analyzes; it never fetches, so re-running it is cheap once the underlying panels exist.

CLI: `python validation.py --hub IOWA --local OHIO --holdout-start 2024-01-01 [--robustness-pairs NEBRASKA,ILLINOIS]`

### `pipeline.py` — orchestration for one pair
`run_pipeline(commodity_desc, hub_state, local_state, year_start, year_end, ..., skip_fetch=False)` runs fetch → clean → analysis → structural break test → backtest validation end-to-end for one commodity/pair, prints one consolidated report, and returns a dict: `panel`, `analysis_report`, `structural_break`, `train_report`, `full_report`. Raises `PipelineError` (wrapping the stage-specific error) if fetch or clean fails.

CLI: `python pipeline.py --commodity CORN --hub IOWA --local OHIO --year-start 2015 --year-end 2026 --holdout-start 2024-01-01 [--skip-fetch]`

### `experiment.py` — experiment tracking on top of `pipeline.py`
Does not modify `pipeline.py`, `analysis.py`, or `validation.py` — calls them and organizes what comes back into `experiments/<run_id>/`. Adds three things pipeline.py alone doesn't have:
- **Isolation**: every run gets its own timestamped folder instead of overwriting shared output.
- **Provenance**: `manifest.json` per run (params, git commit, package versions, a hash of the actual panel analyzed, runtime).
- **Two optional extras**, both saved into the *same* run's folder: `--rolling-coint` (calls `analysis.rolling_cointegration`/`plot_rolling_cointegration`) and `--robustness-pairs NEBRASKA,ILLINOIS,...` (calls `validation.run_pair_robustness`/`print_pair_robustness`/`plot_pair_robustness`).

Any failure at any stage cleans up the partial folder rather than leaving a half-written one behind. See **Experiment tracking** below for the exact folder contents.

CLI: `python experiment.py [--hub IOWA --local OHIO ...same as pipeline.py...] [--rolling-coint] [--rolling-window 60] [--robustness-pairs NEBRASKA] [--experiment-name my_label] [--notes "free text"]`

---

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt   # requests, pandas, numpy, scipy, statsmodels, matplotlib, python-dotenv
echo "USDA_NASS_APIKEY=your_key_here" > .env
```

Get a free NASS API key at https://quickstats.nass.usda.gov/api.

---

## Usage

```bash
cd src

# 1. Confirm data availability before committing to a new commodity/pair
python fetch.py --scan --commodity CORN --states IOWA,OHIO,NEBRASKA

# 2. Run the full pipeline for one pair
python pipeline.py --commodity CORN --hub IOWA --local OHIO \
    --year-start 2015 --year-end 2026 --holdout-start 2024-01-01

# Or rerun against already-cached data without hitting the API:
python pipeline.py --commodity CORN --hub IOWA --local OHIO \
    --year-start 2015 --year-end 2026 --holdout-start 2024-01-01 --skip-fetch
```

Individual stages (`fetch.py`, `clean.py`, `analysis.py`, `validation.py`)
remain independently runnable via their own CLIs — see each module's entry
above, or the file's own docstring, for its arguments.

**Running multiple experiments** (a new pair, a different date range, a
robustness check) — use `experiment.py` instead of calling `pipeline.py`
directly, so each run is saved rather than overwriting the last:

```bash
# Full default run — same defaults as pipeline.py
python experiment.py

# A second pair, with rolling cointegration, saved with a note
python experiment.py --hub IOWA --local NEBRASKA --rolling-coint \
    --notes "robustness check against a second local state"

# Test the primary pair's hub against additional local states, in the
# same run (dumped into that run's own folder, not a separate one)
python experiment.py --robustness-pairs NEBRASKA

# Re-run against cached data under a specific label
python experiment.py --skip-fetch --experiment-name my_relabel_run
```

---

## Experiment tracking

Every argument to `experiment.py` has the same default as `pipeline.py`, so
`python experiment.py` with no arguments reproduces the primary Iowa/Ohio
run. Override only what changes for a variant.

```
experiments/
├── registry.csv                                — one row per run
├── 2026-07-08_corn_iowa-ohio_ae2326/            — primary pair, first run
├── 2026-07-08_corn_iowa-nebraska_dfab18/        — second pair, --rolling-coint
├── 2026-07-09_corn_iowa-ohio_171fb7/            — primary pair, --robustness-pairs
├── my_relabel_run/                              — a --skip-fetch rerun under
│                                                  a custom --experiment-name
└── <date>_<commodity>_<hub>-<local>_<hash>/     — general naming pattern
    ├── manifest.json          — params, git commit, package versions,
    │                            data fingerprint, timestamp, runtime
    ├── data/panel.csv         — cleaned panel this run actually used
    ├── figures/
    │   ├── tlcc_lag_curve.png
    │   ├── spread.png
    │   ├── rolling_cointegration.png     — only with --rolling-coint
    │   └── pair_robustness.png           — only with --robustness-pairs
    ├── tables/
    │   ├── stationarity_adf.csv
    │   ├── tlcc_summary.csv / tlcc_full_curve.csv
    │   ├── granger_hub_to_local.csv / granger_local_to_hub.csv
    │   ├── cointegration_full_period.csv
    │   ├── structural_break_zivot_andrews.csv
    │   ├── backtest_train_vs_full.csv
    │   ├── rolling_cointegration.csv     — only with --rolling-coint
    │   └── pair_robustness.csv           — only with --robustness-pairs
    ├── logs/run.log           — full console output of this run
    └── REPORT.md              — folder guide + headline results +
                                  backtest stability + pair robustness
                                  (if run) + embedded figures
```

`registry.csv` columns: `run_id, timestamp, commodity, hub, local,
year_start, year_end, holdout_start, max_lag, n_months, k_star,
k_star_ci_low, k_star_ci_high, peak_corr, granger_hub_to_local_min_p,
granger_local_to_hub_min_p, cointegration_p_full, cointegration_p_train,
za_break_p, za_break_date, rolling_coint_pct_windows,
robustness_pairs_tested, robustness_k_star_consistent, git_commit, notes`
— one row per run, for cross-experiment comparison without opening each
folder individually.

A run refuses to overwrite an existing folder with the identical param set
from the same day (the hash in the folder name is a hash of the params) —
pass `--experiment-name` for a deliberate rerun, or change a parameter for
a genuine variant.

Note the difference between `figures/` at the repo root and
`experiments/<run>/figures/`: the former is where `analysis.py`/
`validation.py` write plots when run **standalone** (e.g.
`fig_tlcc_iowa_ohio.png`); the latter is where `experiment.py` redirects
those same plotting functions when run **through** it, so each tracked
run's figures stay with that run rather than landing in the shared folder.

---

## Validated status (as of this document)

| Component | Status | Notes |
|---|---|---|
| `fetch.py` | ✅ Confirmed working | Trailing-slash bug in NASS's URL found and fixed; 50K record limit handled via `agg_level_desc=STATE`; availability scan confirmed CORN as the right commodity |
| `clean.py` | ✅ Confirmed working | 137-row aligned panels for both Iowa/Ohio and Iowa/Nebraska, no missing months, no duplicate-date warnings fired |
| `analysis.py` | ✅ Confirmed working | Returns pass ADF stationarity (p≈0.0000 both states); prices correctly non-stationary |
| `analysis.py` — structural break test | ✅ Confirmed working | Zivot-Andrews correctly distinguished "candidate break date" from "statistically significant break" — result was non-significant, correcting an initial over-read of the spread plot |
| `validation.py` — temporal backtest | ✅ Confirmed working | Backtest comparison logic caught a real discrepancy (see Findings) rather than just reporting stable numbers |
| `validation.py` — pair robustness | ✅ Confirmed working (real data) | `experiments/2026-07-09_corn_iowa-ohio_171fb7/tables/pair_robustness.csv` and `figures/pair_robustness.png` exist from a real run against the Iowa/Nebraska panel — the numbers in that CSV still need to be read and folded into the paper's write-up (not yet done as of this doc) |
| `pipeline.py` | ✅ Confirmed working | End-to-end run and `--skip-fetch` rerun both produced bit-identical output |
| `experiment.py` | ✅ Confirmed working (real data) | Three tracked runs exist on disk (`iowa-ohio` ×2, `iowa-nebraska` ×1) plus a custom-named `--experiment-name` rerun, with the expected manifest/figures/tables/REPORT.md/registry row each — this replaces the earlier "syntax-checked only" status |

---

## Full results, methodology, and interpretation

See **`docs/Results/REPORT.md`** for the complete methodology writeup, all
confirmed numerical results for the primary Iowa/Ohio pair, and
paper-writing-ready interpretation — including open items that still need
resolving before submission. That document is the reference for the
primary pair; results aren't duplicated in full here to avoid the two
drifting out of sync.

### Headline findings for Iowa/Ohio (full detail in `docs/Results/REPORT.md`)

- **k\* = 0 months**, bootstrap 95% CI `[0.0, 0.0]` — no detectable lag at
  monthly resolution. Peak correlation 0.84. Stable across train/full
  backtest split.
- **Granger causality asymmetric**: Iowa → Ohio significant; Ohio → Iowa
  is not (aside from one likely false-positive lag).
- **Cointegration is genuinely weak, not just unstable**: a rolling
  60-month Engle-Granger test found significance in only 26% of windows
  (20/78), flickering in and out rather than showing two clean regimes. A
  Zivot-Andrews structural break test found **no significant break**
  (p=0.82) — this isn't a "held, then broke" story. Iowa and Ohio corn
  are strongly synchronized short-run (k\*=0, ρ=0.84) but do **not**
  exhibit a robust long-run equilibrium relationship.

### Iowa/Nebraska pair-robustness check

Now run (see `experiments/2026-07-08_corn_iowa-nebraska_dfab18/` for the
standalone Iowa/Nebraska analysis, and
`experiments/2026-07-09_corn_iowa-ohio_171fb7/tables/pair_robustness.csv`
+ `REPORT.md` for the direct Iowa/Ohio-vs-Iowa/Nebraska comparison). The
actual k*/Granger/cointegration numbers from that comparison haven't yet
been transcribed into this README or into `docs/Results/REPORT.md` — do
that before citing "the finding generalizes" (or doesn't) in the paper.

---

## Known limitations / open items

- **Monthly is the coarsest possible unit for detecting "no lag."** A true
  k*=0 at monthly resolution doesn't rule out a lag of days or weeks — it
  just means nothing is detectable at the resolution this data source
  provides. Framed honestly in the discussion, not oversold as "instant
  transmission."
- **Cointegration instability (train vs. full period) is explained** by
  the Zivot-Andrews result above — no further action needed on this
  specific item.
- ~~Spread spike~~ **Resolved.** September 2023: Iowa dropped $5.77→$5.22
  while Ohio held near-flat ($5.56→$5.50), flipping the spread sign for
  one month. Confirmed against raw NASS values — genuine market
  divergence, not a data or cleaning artifact.
- **Iowa/Nebraska robustness check: data collected and run, interpretation
  pending.** The open item this used to be ("only one pair has been run")
  is now partially closed — `data/processed/corn_iowa_nebraska_monthly.csv`
  exists, and both a standalone experiment and a `--robustness-pairs`
  comparison against Iowa/Ohio have produced real output on disk. What's
  left: actually reading `pair_robustness.csv`/`REPORT.md` and writing up
  whether k*, Granger direction, and cointegration hold for this second
  pair too.
- **A third pair (e.g. Iowa/Illinois) has not been tested.** Availability
  was confirmed via `fetch.py --scan` for Illinois, but it hasn't been
  fetched/cleaned/run yet.
- **Daily-resolution cross-check (USDA AMS Market News) not attempted.**
  Identified as feasible (Iowa, Ohio, and Nebraska all publish Daily Grain
  Bids reports) but requires a separate API registration and
  elevator-level data aggregation decisions not yet made.

---

## Reproducibility

Data source is public (USDA NASS QuickStats, free API key, no
authentication beyond the key). All fetch/clean steps are deterministic
given the same date range — raw pulls are cached in `data/raw/` with
filenames encoding every query parameter, so re-running `clean.py`/
`analysis.py` against the same cached data reproduces identical results.

Runs through `experiment.py` add a second layer of reproducibility: each
run's `manifest.json` records the exact resolved params, git commit,
package versions, and a hash of the actual cleaned panel it analyzed — so
any past experiment folder can be checked against the code and data that
produced it, not just re-run and hoped to match.

---

## Where to look when writing the paper

Instead of reading the code, use this index:

| You need... | Look here |
|---|---|
| The research question, motivation, and what changed from the original plan | This README + `docs/PLAN_v2.md` |
| Confirmed methodology + all numbers for the primary Iowa/Ohio pair | `docs/Results/REPORT.md` |
| Exact commodity/geography verification (why CORN, why these states) | `docs/DATA_SOURCE.md` |
| Figures for the primary pair (standalone runs) | `figures/fig_tlcc_iowa_ohio.png`, `fig_spread_iowa_ohio.png`, `fig_rolling_coint_iowa_ohio.png` |
| Figures/tables for any *tracked* experiment run | `experiments/<run_id>/figures/` and `/tables/` — start from that run's own `REPORT.md` |
| Whether findings hold for a second pair (Iowa/Nebraska) | `experiments/2026-07-09_corn_iowa-ohio_171fb7/tables/pair_robustness.csv` + that run's `REPORT.md` |
| Comparing every run done so far at a glance | `experiments/registry.csv` |
| Exact provenance of a specific number (what code/data produced it) | That run's `experiments/<run_id>/manifest.json` (git commit + panel hash) |
| Raw data provenance (what exact API query produced a given raw file) | The filename itself in `data/raw/` — every query parameter is encoded in it |
| Day-to-day process notes / how a decision was reached | `docs/journal/` |
| Presentation-specific framing | `docs/presentation_prep.md` |
| Manuscript drafts and reference papers | `paper/` |
