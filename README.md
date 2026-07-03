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
commodity/state pair) is **built and confirmed working** — see Status
table below. End-to-end run and `--skip-fetch` rerun both produced
bit-identical output.

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

# 2. Run the full pipeline (fetch -> clean -> analysis -> validation) for
#    a commodity/state pair in one command
python pipeline.py --commodity CORN --hub IOWA --local OHIO \
    --year-start 2015 --year-end 2026 --holdout-start 2024-01-01

# Or, rerun against already-cached data without hitting the API again:
python pipeline.py --commodity CORN --hub IOWA --local OHIO \
    --year-start 2015 --year-end 2026 --holdout-start 2024-01-01 --skip-fetch
```

Individual stages (`fetch.py`, `clean.py`, `analysis.py`, `validation.py`)
remain independently runnable via their own CLIs if you need to work on
one step in isolation — see each file's docstring for its own arguments.

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
| `analysis.py` — structural break test | ✅ Confirmed working | Zivot-Andrews correctly distinguished "candidate break date" from "statistically significant break" — result was non-significant, which corrected an initial over-read of the spread plot |
| `pipeline.py` | ✅ Confirmed working | End-to-end run and `--skip-fetch` rerun both produced bit-identical output — confirms reproducibility, not just that it runs |

## Full results, methodology, and interpretation

See **`docs/REPORT.md`** for the complete methodology writeup, all
confirmed numerical results, and paper-writing-ready interpretation —
including the open items that still need resolving before submission.
That document is the reference; results are not duplicated in full here
to avoid the two drifting out of sync.

### Headline findings (full detail in REPORT.md)

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
  are strongly synchronized short-run (k*=0, ρ=0.84) but do **not**
  exhibit a robust long-run equilibrium relationship. See REPORT.md
  Section 3.6/4 for the full result and how to write this up honestly.

---

## Known limitations / open items

- **Monthly is the coarsest possible unit for detecting "no lag."** A true
  k*=0 at monthly resolution doesn't rule out a lag of days or weeks —
  it just means nothing is detectable at the resolution this data source
  provides. Framed honestly in the discussion, not oversold as "instant
  transmission."
- **Cointegration instability (train vs. full period) is now explained**
  by the Zivot-Andrews result above — no further action needed on this
  specific item.
- ~~Spread spike~~ **Resolved.** September 2023: Iowa dropped $5.77→$5.22
  while Ohio held near-flat ($5.56→$5.50), flipping the spread sign for
  one month. Confirmed against raw NASS values — genuine market divergence,
  not a data or cleaning artifact.
- **Only one commodity/state pair has been run through the full
  pipeline** (Iowa/Ohio corn). `pipeline.py` supports arbitrary pairs, but
  a robustness check against a second pair (e.g. Iowa/Nebraska) hasn't
  been run yet.
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
