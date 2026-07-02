# Interstate Corn Price Concurrency & Transmission Lag

Research sprint measuring how quickly corn price movements transmit between
two U.S. Corn Belt states (Iowa and Ohio), using USDA NASS QuickStats data.

Originally scoped around Indian Agmarknet data (Delhi → Imphal spatial price
transmission); pivoted to USDA NASS after confirming the original data
source and geography didn't support the intended lag analysis. See
`docs/PLAN_v2.md` for the full account of what changed and why.

---

## Research question

When corn prices move in Iowa, how many months does it take for that
movement to show up in Ohio's price-received series — and does the
relationship hold up when tested against data the analysis never saw
during development?

---

## Data source

**USDA NASS QuickStats API** (`https://quickstats.nass.usda.gov/api/`).
Requires a free API key (`USDA_NASS_APIKEY` in `.env`).

Commodity and geography were not assumed — they were empirically verified
before committing. `fetch.py --scan` probes NASS's `get_counts` endpoint
across candidate commodities/states before any real data pull. Verified
result: **CORN** gives 137 clean `MONTHLY` `PRICE RECEIVED` records per
state (2015–2026), no gaps, across all Corn Belt states tested. Fresh
vegetables (the original candidate) are `ANNUAL`-only in this data source
and can't support a sub-annual lag analysis — this is documented as a
dead-end, not silently dropped.

NASS QuickStats has no true daily frequency; `MONTHLY` is the floor. A
higher-frequency source (USDA AMS Market News daily grain bids) was
identified as a possible future addition but is out of scope for this pass
— see Limitations.

---

## Module architecture

```
src/
├── config.py       — env vars, shared paths (BASE_DIR resolved from file
│                      location, not cwd — fixes a real fragility bug)
├── fetch.py         — NASS API client. CLI-drivable, multi-state,
│                       collision-safe raw file caching, availability probe
├── clean.py          — raw per-state CSVs -> one aligned monthly panel
│                        with returns, gap-flagging, suppressed-value handling
├── analysis.py         — TLCC (lag detection), bootstrap CI, Granger
│                          causality (both directions), Engle-Granger
│                          cointegration, diagnostic plots
└── validation.py         — train/holdout backtest: re-runs analysis.py's
                             full analysis on a train slice and compares
                             against the full period to check stability
```

Each module is independently runnable via CLI (`python fetch.py --help`,
etc.) and independently testable — `clean.py` doesn't need network access,
`analysis.py` doesn't need to re-fetch, and so on.

`pipeline.py` (orchestrates all four end-to-end for an arbitrary
commodity/state pair) is **not yet built** — see Status below.

---

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt   # requests, pandas, numpy, scipy, statsmodels, matplotlib
echo "USDA_NASS_APIKEY=your_key_here" > .env
```

Get a free NASS API key at https://quickstats.nass.usda.gov/api.

---

## Usage

```bash
cd src

# 1. Confirm data availability before committing (optional but recommended
#    for any new commodity/state pair)
python fetch.py --scan --commodity CORN --states IOWA,OHIO,ILLINOIS

# 2. Fetch and cache raw data
python fetch.py --commodity CORN --states IOWA,OHIO --year-start 2015 --year-end 2026 --freq MONTHLY

# 3. Clean and align into one panel
python clean.py --commodity CORN --hub IOWA --local OHIO --year-start 2015 --year-end 2026

# 4. Run the core analysis (TLCC, Granger, cointegration)
python analysis.py --plot --spread-plot --holdout-start 2024-01-01

# 5. Backtest: does the finding hold on a train-only slice vs. the full period?
python validation.py --holdout-start 2024-01-01
```

---

## Validated status (as of this document)

Every step below has been run end-to-end against real NASS data, not just
written and assumed correct.

| Step | Status | Notes |
|---|---|---|
| `fetch.py` | ✅ Confirmed working | Trailing-slash bug in NASS's URL found and fixed; 50K record limit handled via `agg_level_desc=STATE`; availability scan confirmed CORN as the right commodity |
| `clean.py` | ✅ Confirmed working | 137-row aligned panel, no missing months, no duplicate-date warnings fired, suppressed-value (`(D)`) handling in place but not yet exercised by this particular pull |
| `analysis.py` | ✅ Confirmed working | Returns pass ADF stationarity (p≈0.0000 both states); prices correctly non-stationary |
| `validation.py` | ✅ Confirmed working | Backtest comparison logic caught a real discrepancy (see Findings) rather than just reporting stable numbers |

### Headline findings (from the full 2015–2026 panel)

- **k\* = 0 months**, bootstrap 95% CI exactly `[0.0, 0.0]` — no detectable
  lag at monthly resolution between Iowa and Ohio corn prices. Peak
  correlation 0.84.
- **Granger causality is asymmetric**: Iowa → Ohio significant (p<0.05) at
  short lags; Ohio → Iowa is not, aside from one isolated hit likely
  attributable to multiple-comparisons noise (12 tests at α=0.05).
- **Engle-Granger cointegration is inconsistent between train (2015–2023,
  p=0.0004, cointegrated) and full period (2015–2026, p=0.1545, not
  cointegrated).** Visual inspection of the spread (see
  `figures/fig_spread_iowa_ohio.png`) shows this is **not** a clean
  structural break at the 2024 holdout boundary — it's a slow, wide,
  multi-year oscillation (peak-to-trough swings of roughly $1.30/bu) that
  predates the holdout window. The honest reading: Engle-Granger's result
  is sensitive to which slice of a slow cycle it's given, not evidence of
  a discrete 2024 event. This needs a rolling-window cointegration test to
  characterize properly — not yet built.

---

## Known limitations / open items

- **Monthly is the coarsest possible unit for detecting "no lag."** A true
  k*=0 at monthly resolution doesn't rule out a lag of days or weeks —
  it just means nothing is detectable at the resolution this data source
  provides. Framed honestly in the discussion, not oversold as "instant
  transmission."
- **Cointegration interpretation is unresolved**, per above — needs a
  rolling-window test before the paper makes any structural-break claim.
- **One isolated spike in the spread series** just before the holdout
  boundary (~0.28, single month, sharp) hasn't been manually verified
  against the raw NASS value — could be a genuine short-lived event or a
  data artifact. Flagged, not yet resolved.
- **`pipeline.py` doesn't exist yet.** Each step currently has to be run
  manually in sequence. Fine for a single commodity/pair; would need
  building out for the "reusable tool" version of this project.
- **Daily-resolution cross-check (USDA AMS Market News) not attempted.**
  Identified as feasible (Iowa and Ohio both publish Daily Grain Bids
  reports) but requires a separate API registration and elevator-level
  data aggregation decisions not yet made.

---

## Reproducibility

Data source is public (USDA NASS QuickStats, free API key, no
authentication beyond the key). All fetch/clean steps are deterministic
given the same date range — raw pulls are cached in `data/raw/` with
filenames encoding every query parameter, so re-running `clean.py`/
`analysis.py` against the same cached data reproduces identical results.
