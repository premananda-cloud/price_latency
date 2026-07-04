# Methodology, Data, and Results Report

**Short-Run Synchronization Without Long-Run Equilibrium:
Price Transmission and Cointegration in U.S. Corn Belt Markets, 2015–2026**

This document is the authoritative reference for the paper of the same title.
All numbers below are from confirmed, reproducible pipeline runs against real
USDA NASS data. No number is estimated or placeholder — if you need to verify
one, rerun the pipeline with `--skip-fetch` against the cached data in
`data/raw/` and it will reproduce identically (confirmed: two independent
runs on different dates produced bit-identical output for the Iowa/Ohio pair;
the Iowa/Nebraska pair has been run once and its output is recorded verbatim
in Section 3.7).

The paper draft (`paper/corn_price_transmission_paper.docx`) was written
directly from this document. If a number in the paper conflicts with a number
here, this document is correct — the paper should be updated, not this file.

---

## 1. Data

**Source:** USDA NASS QuickStats API (`quickstats.nass.usda.gov/api`)

**Primary pair query parameters:**
- Commodity: `CORN`
- States: `IOWA` (hub), `OHIO` (local)
- Statistic category: `PRICE RECEIVED`
- Frequency: `MONTHLY`
- Aggregation level: `STATE`
- Date range: 2015–01 through 2026–05 (137 months, complete, no gaps)

**Robustness pair:** Same parameters, `NEBRASKA` substituted for `OHIO`.
137 months, complete, no gaps — confirmed by the same gap-check logic.

**Why corn, why these states, why monthly:** established empirically, not
assumed. NASS QuickStats' `get_counts` endpoint was used to probe multiple
commodity/frequency/geography combinations before committing (see
`fetch.py`'s `scan_candidates`). Fresh produce (the original candidate
commodity) is `ANNUAL`-only in this data source. Exchange-traded commodities
(corn, soybeans, wheat, livestock) are available monthly. Corn and soybeans
both returned 137 clean monthly records per state across all 7 Corn Belt
states tested (Iowa, Illinois, Indiana, Nebraska, Minnesota, Ohio,
Wisconsin); corn was selected for its deeper literature base in spatial price
transmission research.

**Why Iowa/Ohio as the primary pair:** Iowa is the largest U.S. corn producer
and is commonly treated as a reference/price-setting market in agricultural
economics literature. Ohio is also Corn Belt but sits on a structurally
distinct transport corridor (eastern feed/export markets via truck and Great
Lakes routes, vs. Iowa's western river/rail routes toward Gulf export
terminals and ethanol facilities). This corridor difference gives a plausible
structural basis for the Iowa/Ohio spread, and makes the Iowa/Nebraska
comparison (same corridor, both surplus producers) a natural control.

**Data quality notes:**
- No missing months in any state's series (confirmed by `clean.py`'s
  gap-check against a forced complete monthly index)
- No duplicate-date collisions after filtering to `ALL CLASSES`/`TOTAL` rows
- NASS suppression codes (`(D)`, `(NA)`, `(Z)`) are handled as missing
  values, not zero — not triggered in any of these pulls, but the handling
  exists and was tested against the schema
- ~~Spread spike unverified~~ **RESOLVED:** The sharp single-month spread
  inversion in September 2023 (spread = +$0.28/bu, surrounded by negative
  months) was cross-checked against raw NASS values. Iowa fell from $5.77
  to $5.22/bu (−$0.55) while Ohio held near-flat ($5.56 to $5.50/bu,
  −$0.06). No suppression codes; no implausible values. Confirmed genuine
  market divergence, not a data or cleaning artifact.

---

## 2. Methodology

### 2.1 Panel construction
Raw per-state NASS records are parsed (`year` + `reference_period_desc`
→ date), converted to float (handling suppression codes), aligned onto a
shared complete monthly index, and used to compute:
- `spread` = local price − hub price ($/bu)
- `{state}_returns` = month-over-month % change in price

Returns are the input to TLCC and Granger causality. Levels are the input
to Engle-Granger cointegration. The spread is the input to Zivot-Andrews.
This assignment follows directly from the stationarity requirements of
each method.

### 2.2 Stationarity (ADF)
Augmented Dickey-Fuller test run on both price levels and both returns
series before any lag or causality analysis. Levels are expected to be
non-stationary (I(1) processes, normal for commodity price data); applying
TLCC or Granger tests to non-stationary levels would produce spurious
correlations. Returns are expected to be stationary and are the correct
input for TLCC/Granger.

### 2.3 Time-Lagged Cross-Correlation (TLCC)
Computed on **returns** (not levels). Lag window ±12 months — narrower
than a daily-data analysis would use, because the full sample is only
137 months and a wider window rapidly depletes degrees of freedom.
Sign convention: positive k* means the hub (Iowa) leads the local state
by k* months. 95% confidence interval on k* obtained via bootstrap
resampling (1,000 resamples, paired, with replacement).

### 2.4 Granger causality
Tested both directions on returns, lags 1–12. Note on interpretation:
`statsmodels.tsa.stattools.grangercausalitytests` at lag *k* tests a
VAR(*k*) model — whether including up to *k* months of the candidate
cause series improves prediction of the effect series beyond its own
history — not whether lag *k* in isolation is significant. Persistent
significance across many *k* values reflects cumulative information
content. An isolated significant result at one lag among non-significant
neighbors at α=0.05 is consistent with a multiple-comparisons false
positive (~0.6 expected per 12 tests) and is not treated as causal
evidence.

### 2.5 Cointegration (Engle-Granger)
Run on **price levels** — tests whether the two series share a stable
long-run equilibrium relationship, independent of short-run dynamics. Run
twice: (a) on the full period for a single summary result, and (b) as a
rolling 60-month window stepped monthly to assess whether any
cointegration is stable across sub-periods or localized to particular
windows. The 60-month window gives Engle-Granger reasonable power (5
years of data) while being short enough to detect sub-decade regime
changes.

### 2.6 Structural break test (Zivot-Andrews)
Run on the `spread` series. ZA (1992) searches endogenously for the
most likely single break point, allowing for a unit root under the null,
without requiring a pre-specified break date. Applied to the spread rather
than price levels, since a change in the structural relationship between
two markets should manifest as a level shift or trend change in the
spread. `trim=0.15` (default) excludes the first and last ~20 months from
the candidate search window. **The p-value, not the candidate date,
determines whether the result is meaningful.** The test returns a
candidate date regardless of significance; that date should not be
reported as a real event unless p < 0.05.

### 2.7 Validation (train/holdout backtest)
Full panel split at `2024-01-01`: train = 2015-01 to 2023-12 (108
months), holdout start = 2024-01-01 through 2026-05 (29 months). The full
analysis (2.2–2.6) is rerun on train-only data and compared against the
full-period run. Because the holdout window (29 months) is shorter than
the ±12-month TLCC lag window requires, the comparison is train-only vs.
full-period (which includes holdout), not train vs. holdout in isolation.
Agreement indicates the finding generalizes; disagreements are reported
explicitly, not smoothed over.

### 2.8 Robustness pair (Iowa–Nebraska)
The full pipeline (2.1–2.7) was rerun substituting Nebraska for Ohio.
Nebraska was selected as a structural near-twin of Iowa: a large surplus
corn-producing state on the same western rail/barge transport corridor,
with similar ethanol industry penetration and similar export-terminal
orientation. The Iowa/Nebraska pair tests whether Iowa/Ohio findings are
specific to that pairing or reflect a broader Corn Belt pattern.

---

## 3. Results

### 3.1 Stationarity

| Series | ADF stat | p-value | Stationary @ 5%? |
|---|---|---|---|
| Iowa price (level) | −1.601 | 0.4829 | No (expected) |
| Ohio price (level) | −1.823 | 0.3691 | No (expected) |
| Iowa returns | −7.532 | 0.0000 | Yes |
| Ohio returns | −8.020 | 0.0000 | Yes |

Returns are cleanly stationary — TLCC/Granger results are valid on this
basis. Iowa price levels are the same in both pairs (same series). Nebraska
stationarity results:

| Series | ADF stat | p-value | Stationary @ 5%? |
|---|---|---|---|
| Nebraska price (level) | −1.640 | 0.4623 | No (expected) |
| Nebraska returns | −7.839 | 0.0000 | Yes |

### 3.2 Time-Lagged Cross-Correlation (Iowa–Ohio)

**k\* = 0 months** (positive = Iowa leads Ohio)
Peak correlation: **0.840**
Bootstrap 95% CI on k*: **[0.0, 0.0]** — exact, no spread in the estimate

No detectable lag at monthly resolution. Secondary correlation peaks at
lag ±1 are nearly symmetric (~0.40 both directions), consistent with
autocorrelation bleed-through from the contemporaneous ρ=0.84 signal
rather than a secondary transmission mechanism.

The k*=0 result does not imply instantaneous physical transmission.
Monthly NASS series aggregate all transactions within a calendar month;
any transmission occurring within that month — including within hours or
days — produces k*=0 at this resolution. The correct reading: no lag
detectable at monthly granularity, consistent with both states pricing
off a shared CME/CBOT reference signal within the same reporting period.

### 3.3 Granger causality (Iowa–Ohio)

**Iowa → Ohio:** significant (p<0.05) at lags 1 through 8; weakens at
lags 9–12 (lag 9: p=0.054).

| Lag | p-value | Sig? |
|---|---|---|
| 1 | 0.0089 | * |
| 2 | 0.0100 | * |
| 3 | 0.0216 | * |
| 4 | 0.0166 | * |
| 5 | 0.0319 | * |
| 6 | 0.0199 | * |
| 7 | 0.0324 | * |
| 8 | 0.0452 | * |
| 9 | 0.0541 | |
| 10 | 0.0815 | |
| 11 | 0.0849 | |
| 12 | 0.1616 | |

**Ohio → Iowa:** not significant at any lag except lag 8 (p=0.0467),
isolated among non-significant neighbors (lag 7: p=0.080, lag 9:
p=0.052). Treated as a multiple-comparisons false positive, not evidence
of reverse causality.

**Reading:** directionally asymmetric. Iowa's price history carries
predictive information for Ohio's returns across approximately an
8-month window. The reverse is not supported. This asymmetry does not
contradict k*=0: TLCC finds where contemporaneous correlation peaks;
Granger tests whether lagged values add predictive power beyond a
series' own history. Both can simultaneously be true.

### 3.4 Cointegration (Iowa–Ohio, full period 2015–2026)

Engle-Granger score = −2.836, p = 0.1545. Does not clear the 10%
critical value (−3.076). **No cointegration detected at conventional
significance over the full period.**

### 3.5 Structural break test (Iowa–Ohio spread)

Zivot-Andrews on the Iowa–Ohio spread: candidate break date 2024-09-01,
ZA stat = −3.241, **p = 0.8224 — not significant.** No statistically
confirmed structural break in the Iowa–Ohio spread. The candidate date
(September 2024) is an artefact of the search and should not be reported.

### 3.6 Backtest: train (2015–2023) vs. full (2015–2026) — Iowa–Ohio

| Metric | Train-only | Full period |
|---|---|---|
| k* (months) | 0 | 0 |
| Peak correlation | 0.847 | 0.840 |
| k* 95% CI | (0.0, 0.0) | (0.0, 0.0) |
| Min p, Iowa→Ohio Granger | 0.0045 | 0.0089 |
| Cointegration p-value | **0.0004** | **0.1545** |

k* and the Iowa→Ohio Granger asymmetry are **stable**. Cointegration is
**not stable** — train-only p=0.0004, full-period p=0.1545.

The cointegration instability is not explained by a discrete structural
break (Section 3.5, ZA p=0.822). A rolling 60-month Engle-Granger test
(`analysis.py --rolling-coint`, 78 windows, 2019-12 through 2026-05)
characterises it more precisely: **significance appears in only 20/78
windows (26%)**, and flickers in and out repeatedly rather than holding
for extended stretches. Many p-values sit right at the boundary
(0.0517, 0.0715, 0.0569, 0.0392). This is not a two-regime "held, then
broke" story — it is a marginally non-cointegrated relationship whose
test statistic is sensitive to window placement. The strong train-only
result (p=0.0004) reflects a particular window configuration, not a
genuinely cointegrated regime that subsequently broke.

**Correct characterisation:** Iowa and Ohio corn prices do not exhibit a
robust long-run cointegrating relationship over 2015–2026. See
`figures/fig_rolling_coint_iowa_ohio.png`.

### 3.7 Robustness: Iowa–Nebraska full pipeline results

All results below are from a single confirmed pipeline run:
`python pipeline.py --commodity CORN --hub IOWA --local NEBRASKA
--year-start 2015 --year-end 2026 --holdout-start 2024-01-01`

**TLCC:**
k* = 0 months. Peak correlation: **0.918** (higher than Iowa/Ohio's
0.840). Bootstrap 95% CI: **[0.0, 0.0]**.

**Granger causality — Iowa → Nebraska:**
Significant at all 12 tested lags (minimum p=0.0000 at lag 1, maximum
p=0.0016 at lag 12). Notably stronger and more consistent than
Iowa→Ohio (which lost significance at lag 9).

| Lag | p-value | Sig? |
|---|---|---|
| 1 | 0.0000 | * |
| 2 | 0.0001 | * |
| 3 | 0.0001 | * |
| 4 | 0.0003 | * |
| 5 | 0.0009 | * |
| 6 | 0.0002 | * |
| 7 | 0.0002 | * |
| 8 | 0.0002 | * |
| 9 | 0.0004 | * |
| 10 | 0.0008 | * |
| 11 | 0.0005 | * |
| 12 | 0.0016 | * |

**Granger causality — Nebraska → Iowa:**
Not significant at any lag. p-values range from 0.129 to 0.995 —
definitively non-significant, no isolated artifacts.

**Cointegration (full period):**
EG score = −3.958, **p = 0.0082** — significant at 1%. Critical values:
1%=−3.979, 5%=−3.381, 10%=−3.076. Iowa/Nebraska clears the 1% threshold;
Iowa/Ohio did not clear 10%.

**Structural break (Iowa–Nebraska spread):**
ZA stat = −7.124, **p = 0.0000** — highly significant. Candidate break
date: **September 2022**. Unlike the Iowa/Ohio non-result (p=0.822),
this is a genuine finding. The Iowa/Nebraska spread underwent a
statistically confirmed structural change around September 2022. The
mechanism is not determined by this analysis (see Section 4, caution
note on causal claims).

**Backtest — Iowa/Nebraska:**

| Metric | Train-only | Full period |
|---|---|---|
| k* (months) | 0 | 0 |
| Peak correlation | 0.925 | 0.918 |
| k* 95% CI | (0.0, 0.0) | (0.0, 0.0) |
| Min p, Iowa→Nebraska Granger | 0.0022 | 0.0000 |
| Cointegration p-value | **0.0415** | **0.0082** |

Backtest read (from pipeline output): k* stable at 0; Iowa→Nebraska
Granger significant in both; cointegration consistent (significant in
both train and full). The Nebraska pair passes all three stability checks
where Iowa/Ohio passed only two.

**Cross-pair summary:**

| Metric | Iowa–Ohio | Iowa–Nebraska |
|---|---|---|
| k* (months) | 0 | 0 |
| Peak correlation (ρ) | 0.840 | 0.918 |
| k* 95% CI | [0.0, 0.0] | [0.0, 0.0] |
| Iowa→ Granger sig. lags | 1–8 | 1–12 |
| ←Iowa Granger (reverse) | Not sig. (1 artifact) | Definitively not sig. |
| Cointegration p (full period) | 0.1545 | 0.0082 |
| Cointegration stable in backtest? | No | Yes |
| ZA break p-value | 0.822 | <0.001 |
| ZA candidate break date | n.s. (not reported) | September 2022 |

---

## 4. Interpretation (reference for Discussion section)

**Headline short-run finding:** Both pairs show k*=0, CI=[0,0], with
Iowa Granger-causing the other state but not vice versa. These findings
are stable across train/full splits and replicate across both pairs.
Iowa's price history carries forward-looking information for other Corn
Belt states across a window of approximately 8–12 months, even though
contemporaneous co-movement is already very high. This is consistent
with a market microstructure in which Iowa — as the largest, most liquid
Corn Belt market — incorporates new supply and demand signals slightly
ahead of smaller or less liquid markets.

**Headline long-run finding:** Short-run synchronization and long-run
cointegration do not travel together in this dataset. Iowa/Ohio is
strongly synchronised short-run but not robustly cointegrated long-run.
Iowa/Nebraska is equally synchronised short-run and is robustly
cointegrated. The difference maps directly onto transport corridor
alignment: Nebraska shares Iowa's western corridor, end-use markets, and
freight cost structure; Ohio does not. States on the same corridor face
the same external shocks symmetrically and maintain a stable spread;
states on different corridors face corridor-specific shocks that drive
the spread without a reliable self-correcting mechanism.

**The September 2022 Nebraska break:** This is a statistically confirmed
finding (ZA p<0.001). What it means economically is not determined here.
September 2022 falls within a documented period of unusual basis behavior
across the Corn Belt — Iowa Farm Bureau's analysis (2022) describes tight
corn and soybean supplies keeping cash prices elevated above futures for
extended periods, a departure from pre-2021 norms — but "within the
window" is not the same as "caused by." Report the break date as a
finding and note the coincidence with documented unusual basis conditions.
Do not assert a specific mechanism without a dedicated search or citation.

**What is verified and citable as structural background:**
Iowa Farm Bureau (2023) states that 50–70% of Iowa's corn crop is
processed for ethanol, compared to roughly 35–40% nationally. Multiple
corroborating sources (Iowa Corn Growers Association, Iowa Renewable
Fuels Association) report Iowa figures in the 52–62% range for individual
recent years. This is legitimate context for why Iowa and Ohio have a
structural basis differential — it does not, on its own, explain any
specific year's spread movement and should not be stretched to do so.

**What the paper does NOT claim:**
- That k*=0 means instantaneous physical transmission (the data cannot
  resolve sub-monthly dynamics)
- That the September 2022 Nebraska break was caused by any specific
  named event (not tested)
- That the Iowa/Ohio rolling cointegration result reflects a structural
  regime change (ZA rules this out)
- That Granger causality implies economic causation in a structural sense
  (it is a predictive, not causal, test)

---

## 5. Open items

1. ~~Spread spike verification~~ **RESOLVED.** See Section 1, Data
   quality notes.

2. ~~Robustness pair (Iowa/Nebraska)~~ **RESOLVED.** See Section 3.7.
   Short-run findings replicate; long-run findings differ in a
   structurally interpretable way. Both outcomes are reported in the paper.

3. **Figure styling pass still required.** Current figures
   (`fig_spread_iowa_ohio.png`, `fig_tlcc_iowa_ohio.png`,
   `fig_rolling_coint_iowa_ohio.png`) have functional labels but are not
   publication-polished. Before submission: standardise axis label fonts
   and sizes, add units to all axis labels ($/bu, months, p-value),
   ensure all figures are 300 DPI, add a horizontal reference line at
   p=0.05 to the rolling cointegration plot.

4. ~~Rolling-window cointegration test~~ **RESOLVED.** See Section 3.6.

5. **Figures need to be inserted into the paper.** The .docx draft
   references figures conceptually but the image files are not embedded.
   Insert `fig_tlcc_iowa_ohio.png` after Section 5.2, `fig_spread_iowa_ohio.png`
   and `fig_rolling_coint_iowa_ohio.png` after Section 5.4.

6. **Iowa/Nebraska rolling cointegration not yet run.** The September
   2022 ZA break raises a natural follow-on question: does rolling
   cointegration show a clear before/after pattern around that date?
   Running `analysis.py --rolling-coint` for the Nebraska pair would
   either confirm a clean two-regime structure (cointegrated pre-Sept 2022,
   then not — or vice versa) or show something more complex. Not required
   for submission but would strengthen Section 6.3 of the paper.

7. **GitHub repo URL placeholder.** The title page of the paper
   currently reads `github.com/[your-repo]`. Fill in before sharing
   externally.

---

## 6. Reproducing these results

**Iowa–Ohio (primary pair):**
```bash
cd src
python pipeline.py --commodity CORN --hub IOWA --local OHIO \
    --year-start 2015 --year-end 2026 --holdout-start 2024-01-01 \
    --skip-fetch
```

**Iowa–Nebraska (robustness pair):**
```bash
cd src
python pipeline.py --commodity CORN --hub IOWA --local NEBRASKA \
    --year-start 2015 --year-end 2026 --holdout-start 2024-01-01
```
(No `--skip-fetch` needed if Nebraska raw files are not yet cached —
the pipeline will fetch and cache them automatically, then proceed.)

**Rolling cointegration (Iowa–Ohio):**
```bash
cd src
python analysis.py --commodity CORN --hub IOWA --local OHIO \
    --freq MONTHLY --rolling-coint
```

**Structural break test:**
```bash
cd src
python analysis.py --commodity CORN --hub IOWA --local OHIO \
    --freq MONTHLY --break-test
```

Two independent runs of the Iowa/Ohio pipeline against the same cached
data produced bit-identical output (confirmed). The Nebraska run has been
executed once; re-running from the cached raw files will reproduce
identically.
