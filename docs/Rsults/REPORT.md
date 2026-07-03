# Methodology, Data, and Results Report

**Interstate Corn Price Concurrency: Iowa vs. Ohio, 2015–2026**

This document is the reference for paper-writing. All numbers below are
from a confirmed, reproducible pipeline run (`python pipeline.py --commodity
CORN --hub IOWA --local OHIO --year-start 2015 --year-end 2026`). No number
in this document is estimated or placeholder — if you need to verify one,
rerun the pipeline with `--skip-fetch` against the cached data in
`data/raw/` and it will reproduce identically (confirmed: two independent
runs on different dates produced bit-identical output).

---

## 1. Data

**Source:** USDA NASS QuickStats API (`quickstats.nass.usda.gov/api`)

**Query parameters:**
- Commodity: `CORN`
- States: `IOWA` (hub), `OHIO` (local)
- Statistic category: `PRICE RECEIVED`
- Frequency: `MONTHLY`
- Aggregation level: `STATE`
- Date range: 2015–01 through 2026–05 (137 months, complete, no gaps)

**Why corn, why these states, why monthly:** established empirically, not
assumed. NASS QuickStats' `get_counts` endpoint was used to probe multiple
commodity/frequency/geography combinations before committing (see
`fetch.py`'s `scan_candidates`). Fresh produce (originally tomatoes) is
`ANNUAL`-only in this data source — contract-priced commodities aren't
tracked monthly. Exchange-traded commodities (corn, soybeans, wheat,
livestock) are. Corn and soybeans both returned 137 clean monthly records
per state across all 7 Corn Belt states tested (Iowa, Illinois, Indiana,
Nebraska, Minnesota, Ohio, Wisconsin); corn was selected for its deeper
literature base in spatial price transmission research.

**Why Iowa/Ohio as the pair:** Iowa is the largest U.S. corn producer and
commonly treated as a reference/price-setting market in agricultural
economics literature. Ohio is also Corn Belt but sits on a different
transport corridor (eastern feed/export markets vs. Iowa's river/rail
routes west), giving a plausible basis for expecting *some* differential,
even if not necessarily a time lag.

**Data quality notes:**
- No missing months in either state's series (confirmed by `clean.py`'s
  gap-check against a forced complete monthly index)
- No duplicate-date collisions after filtering to `ALL CLASSES`/`TOTAL`
  rows
- NASS suppression codes (`(D)`, `(NA)`) are handled as missing values, not
  zero — not triggered in this particular pull, but the handling exists
  and was tested against the schema
- Known unresolved item: one sharp single-month spike in the spread series
  around late 2023 has not been manually cross-checked against the raw
  NASS value. Flagged, not yet resolved — see Section 5.

---

## 2. Methodology

### 2.1 Panel construction
Raw per-state NASS records are parsed (`year` + `reference_period_desc`
→ date), converted to float (handling suppression codes), aligned onto a
shared complete monthly index, and used to compute:
- `spread` = local price − hub price
- `{state}_returns` = month-over-month % change in price

### 2.2 Stationarity (ADF)
Augmented Dickey-Fuller test run on both price levels and both returns
series. Levels are expected to be non-stationary (normal for price data);
returns are expected to be stationary (required for TLCC/Granger validity).

### 2.3 Time-Lagged Cross-Correlation (TLCC)
Computed on **returns** (not levels — levels are non-stationary and would
produce spurious correlation). Lag window ±12 months (narrower than a
day-scale analysis would use, since the full sample is only 137 months —
a wider window burns degrees of freedom fast). Sign convention: positive
k* means the hub (Iowa) leads the local state (Ohio) by k* months.
95% confidence interval on k* obtained via bootstrap resampling (1,000
resamples, paired, with replacement).

### 2.4 Granger causality
Tested both directions (Iowa→Ohio and Ohio→Iowa) on returns, lags 1–12.
Note on interpretation: `statsmodels.tsa.stattools.grangercausalitytests`
at lag *k* tests a VAR(*k*) model — i.e., whether including up to *k*
months of the cause series' history improves prediction of the effect
series — not whether lag *k* specifically, in isolation, is significant.
Persistent significance across many *k* values reflects cumulative
information content, not *k* independent findings.

### 2.5 Cointegration (Engle-Granger)
Run on **price levels** (not returns) — this tests a fundamentally
different question from TLCC/Granger: whether the two series share a
long-run equilibrium relationship, independent of short-run dynamics.

### 2.6 Structural break test (Zivot-Andrews)
Run on the `spread` series to test for a single statistically significant
structural break point, allowing for a unit root under the null. Reports
a candidate break date regardless of significance — **the p-value, not
the date, determines whether the result means anything.**

### 2.7 Validation (train/holdout backtest)
Full panel split at `2024-01-01`: train = 2015-01 to 2023-12 (108 months),
holdout period included in "full" = 2015-01 to 2026-05 (137 months). The
full analysis (2.2–2.5) is re-run on train-only data and compared against
the full-period run. Because the holdout window (29 months) is too short
to support a standalone ±12-month-lag TLCC on its own, the comparison is
train-only vs. full-period (which includes the holdout), not train vs.
holdout in isolation. Agreement between the two indicates the train-period
finding generalizes; disagreement is reported explicitly, not smoothed
over.

---

## 3. Results

### 3.1 Stationarity

| Series | ADF stat | p-value | Stationary @ 5%? |
|---|---|---|---|
| Iowa price (level) | −1.601 | 0.4829 | No (expected) |
| Ohio price (level) | −1.823 | 0.3691 | No (expected) |
| Iowa returns | −7.532 | 0.0000 | Yes |
| Ohio returns | −8.020 | 0.0000 | Yes |

Returns are cleanly stationary — TLCC/Granger results below are valid on
this basis.

### 3.2 Time-Lagged Cross-Correlation

**k\* = 0 months** (positive = Iowa leads Ohio)
Peak correlation: **0.840**
Bootstrap 95% CI on k*: **[0.0, 0.0]** — exact, no spread in the estimate

No detectable lag at monthly resolution. Secondary correlation peaks at
lag ±1 are nearly symmetric (~0.40 both directions), consistent with
autocorrelation bleed-through rather than a secondary lag signal.

### 3.3 Granger causality

**Iowa → Ohio:** significant (p<0.05) at lags 1 through 8; weakens beyond
lag 8 (lag 9: p=0.054, not significant).

**Ohio → Iowa:** not significant at any lag except lag 8 (p=0.0467),
isolated among non-significant neighbors — consistent with a
multiple-comparisons false positive (12 tests at α=0.05 yields ~0.6
expected false positives), not treated as evidence of reverse causality.

**Reading:** directionally asymmetric — Iowa's price history has
predictive value for Ohio's that isn't matched in the reverse direction.

### 3.4 Cointegration (full period, 2015–2026)

Engle-Granger score = −2.836, p = 0.1545. Does not clear the 10% critical
value (−3.076). **No cointegration detected at conventional significance
over the full period.**

### 3.5 Structural break test

Zivot-Andrews on the spread series: candidate break date 2024-09-01,
za_stat = −3.241, **p = 0.8224 — not significant.** No statistically
confirmed structural break exists in the spread series. The candidate date
should not be reported as a real event.

### 3.6 Backtest: train (2015–2023) vs. full (2015–2026)

| Metric | Train-only | Full period |
|---|---|---|
| k* (months) | 0 | 0 |
| Peak correlation | 0.847 | 0.840 |
| k* 95% CI | (0.0, 0.0) | (0.0, 0.0) |
| Min p, Iowa→Ohio Granger | 0.0045 | 0.0089 |
| Cointegration p-value | **0.0004** | **0.1545** |

k* and the Iowa→Ohio Granger asymmetry are **stable** across train-only
and full-period samples — this finding is not an artifact of one
particular slice of the data.

Cointegration is **not stable** — train-only data shows strong
cointegration (p=0.0004), full-period data does not (p=0.1545). Per
Section 3.5, this is *not* explained by a discrete structural break — the
Zivot-Andrews test found none. A rolling 60-month Engle-Granger test
(`analysis.py --rolling-coint`, 78 windows from 2019-12 through 2026-05)
resolves this more specifically: **the relationship is cointegrated at 5%
in only 20/78 windows (26%)**, and significance flickers in and out
repeatedly rather than holding for extended stretches — many p-values sit
right at the boundary (0.0517, 0.0715, 0.0569, 0.0392...). This is not a
two-regime "held, then broke" story. It's a marginal, noisy relationship
throughout the observed period, tipping across the 5% line on small
perturbations rather than settling into a stable "on" or "off" state. The
honest characterization: Iowa and Ohio corn prices do **not** exhibit a
robust long-run cointegrating relationship over 2015–2026 — what
cointegration appears in any given slice (like the strong train-only
p=0.0004 result) should be read as sensitive to that slice's specific
window placement, not as evidence of an underlying stable equilibrium
that later broke. See `figures/fig_rolling_coint_iowa_ohio.png`.

---

## 4. Interpretation (for Discussion section)

**Headline finding:** Iowa and Ohio corn markets show strong, stable,
same-month price synchronization (k*=0, ρ=0.84, robust across train/full
splits) with an asymmetric information flow favoring Iowa as the
price-leading market. This is consistent with two well-connected,
CME/CBOT-anchored markets pricing off a shared reference signal within
the same reporting month — not evidence of "no transmission," but of
transmission occurring faster than monthly resolution can detect.

**What this is NOT:** this is not a finding about physical logistics or
transport-time friction (that framing fit the original isolated-market
premise, not two integrated Corn Belt states). It's a market-efficiency
finding — the interesting result is the *absence* of a detectable lag
between two major producing regions, not a measured lag value.

**The unresolved piece, now resolved and stated honestly:** short-run
co-movement is strong and stable (k*=0, ρ=0.84, robust across every
sample split tested); long-run equilibrium is not — a rolling-window test
shows the relationship is cointegrated in only 26% of 5-year windows
across 2019–2026, with significance flickering rather than holding in
clean regimes. This should be presented directly in the paper: Iowa and
Ohio corn markets are highly synchronized in the short run but do not
exhibit a robust long-run equilibrium relationship — a genuinely
interesting combination, since it's often assumed that short-run
synchronization and long-run cointegration go together. They don't have
to, and this dataset is a clean example of why.

**A caution from process, worth keeping in mind while writing:** an
earlier draft interpretation (from a source outside this pipeline)
asserted a specific causal story for the spread's 2021–2023 dip — citing
COVID logistics disruption, the Ukraine war grain shock, and Iowa ethanol
demand — without verification against the actual test results. The
Zivot-Andrews test does not support a discrete break in that window, and
that specific dated narrative has not been checked against real market
data or cited sources. **Do not include that dated narrative in the paper
without independently verifying it via search first.**

**What IS verified and citable:** Iowa's heavy in-state ethanol demand is
real, well-documented background for why Iowa and Ohio might structurally
differ in basis behavior — not a story about any specific date. Iowa Farm
Bureau's own economic analysis states that in recent years 50–70% of
Iowa's corn crop is processed for ethanol, compared to roughly 35–40%
nationally (source: Iowa Farm Bureau, "Ethanol Industry in Iowa and the
US," iowafarmbureau.com). Multiple independent sources (Iowa Corn Growers
Association, Iowa Renewable Fuels Association, U.S. Senate office
communications) report Iowa figures in the 52–62% range for individual
recent years, consistent with that band. This is legitimate Discussion
context for *why* a persistent Iowa/Ohio basis differential exists at
all — it does not, on its own, explain any particular year's spread
movement, and should not be stretched to do so without further evidence.

---

## 5. Open items before this is submission-ready

1. ~~Spread spike verification~~ **RESOLVED.** September 2023 checked
   against raw values: Iowa dropped from $5.77 to $5.22 while Ohio held
   near-flat ($5.56 to $5.50), genuinely flipping the spread sign for one
   month. Confirmed real market divergence, not a data or cleaning
   artifact.
2. **Robustness pair.** Only Iowa/Ohio has been run through the full
   pipeline. A second pair (e.g. Iowa/Nebraska) via `pipeline.py` would
   confirm this isn't specific to one arbitrary pairing.
3. **Figures need Day 5 styling pass** (axis labels/titles are functional
   but not publication-polished; see `docs/PLAN_v2.md` Day 5 checklist).
   Now includes `fig_rolling_coint_iowa_ohio.png` in the figure set.
4. ~~Rolling-window cointegration test~~ **RESOLVED.** Run via
   `analysis.py --rolling-coint`; cointegrated in only 26% of 60-month
   windows, flickering rather than regime-based. See Section 3.6 for the
   updated interpretation — this replaces the earlier oscillation
   hypothesis with a more specific, less tidy, and better-supported
   finding.

---

## 6. Reproducing these results

```bash
cd src
python pipeline.py --commodity CORN --hub IOWA --local OHIO \
    --year-start 2015 --year-end 2026 --holdout-start 2024-01-01 \
    --skip-fetch
```

(Omit `--skip-fetch` on a fresh clone without cached `data/raw/` files —
it will re-fetch from NASS, requiring a valid `USDA_NASS_APIKEY` in `.env`.)
Two independent runs against the same cached data have produced identical
output (confirmed), so this section does not need to be re-verified unless
the underlying data or code changes.
