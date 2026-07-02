# Research Sprint v2: Interstate Corn Price Concurrency & Transmission Lag

Supersedes `docs/PLAN.txt`. Same spirit — one-week sprint to a short research
paper — but data source, commodity, and methodology have changed based on
what's actually available.

---

## What changed from v1, and why

| v1 (original) | v2 (current) | Reason |
|---|---|---|
| Agmarknet, India | USDA NASS QuickStats | Data source switch (your call) |
| Azadpur (Delhi) → Imphal | Iowa → Ohio | Need genuine state-level *monthly* coverage; confirmed via `scan_candidates` |
| Tomatoes/Onions | Corn | Fresh produce is ANNUAL-only in NASS (contract-priced); corn is exchange-traded and MONTHLY at state level — confirmed 137 clean records/state, 2015–2026, no gaps |
| Daily price ticks, k* in **days** | Monthly price series, k* in **months** | NASS has no daily frequency — floor is MONTHLY |
| "Logistical isolation" framing (NH-37 flood risk, road transit time) | "Interstate concurrency" framing (market integration, information transmission speed) | Iowa/Ohio are both well-connected Corn Belt states — isolation doesn't apply. The interesting question is now market efficiency, not infrastructure friction |
| TLCC only | TLCC + Granger causality + optional cointegration | Added because monthly price *levels* raise a genuine question TLCC alone doesn't answer: do these two markets share a long-run equilibrium (cointegration), separate from how fast a shock passes between them (TLCC/Granger) |
| No validation step | Explicit backtest/holdout validation | This is the actual scientific contribution — a lag number with nothing checking it against real subsequent data is just an assertion |

**Headline research question (v2):** When corn prices move in Iowa, how many
months does it take for that movement to show up in Ohio's price-received
series — and does the relationship hold up when tested against data the
model never saw?

---

## Module architecture

```
src/
├── config.py        # env vars, paths — DONE
├── fetch.py          # NASS client, CLI-drivable, multi-state — DONE
├── clean.py           # raw → aligned monthly panel, returns, gap handling — NEXT
├── analysis.py         # TLCC, Granger causality, (optional) cointegration
├── validation.py       # train/holdout split, backtest scoring
└── pipeline.py           # orchestrates fetch → clean → analysis → validation → report
```

Each module is independently testable and CLI-runnable where it makes sense
(`fetch.py` already is). `pipeline.py` is the thin script that ties them
together for a given commodity/state-pair — built last, once the pieces it's
orchestrating are proven individually.

---

## Day-by-day (adjusted — you're partway through Day 1 already)

### Day 1 — Data pipeline foundation (in progress)
**Status: mostly done.**
- [x] Repo structure, venv, `.env`, config
- [x] `fetch.py`: parameterized by commodity/state/year-range/frequency, CLI args, multi-state fetch, raw caching with collision-safe filenames
- [x] Confirmed CORN + IOWA/OHIO (and other Corn Belt states) have clean MONTHLY coverage via `scan_candidates`
- [ ] **Remaining today:** run `python fetch.py --commodity CORN --states IOWA,OHIO --year-start 2015 --year-end 2026 --freq MONTHLY` to pull and cache both raw CSVs

### Day 2 — `clean.py`
**Goal:** raw NASS JSON-derived CSVs → one aligned monthly panel.
- Parse `year` + `reference_period_desc` (e.g. "JAN") into a proper `datetime` index
- Merge Iowa and Ohio into a single frame: `date | price_iowa | price_ohio`
- Handle any missing months (NASS occasionally withholds values — watch for `(D)` in `Value`, which means suppressed, not zero)
- Compute month-over-month % returns for both series (needed for TLCC/Granger; cointegration will use the raw price levels instead)
- Sanity-check plot: both series on one chart — do they visibly track each other?
- **Output:** `data/processed/corn_iowa_ohio_monthly.csv`, `fig_01_raw_prices.png`

### Day 3 — `analysis.py`
**Goal:** headline lag number(s) + statistical grounding.
- TLCC over returns, lag range realistically ±12 months (not ±30 — you only have ~137 months total, wide lag windows eat degrees of freedom fast)
- Bootstrap CI on k* (same approach as v1, just fewer max-lag steps)
- Granger causality test (Iowa → Ohio direction) on returns
- Engle-Granger cointegration test on price *levels* — answers a genuinely different question (long-run co-movement) worth having alongside the lag result
- **Output:** `fig_02_tlcc_curve.png`, k* + CI, Granger p-values, cointegration test result

### Day 4 — `validation.py`
**Goal:** the part v1 didn't have. Does the relationship hold up?
- Split the panel: train on 2015–2023, hold out 2024–2026
- Re-run the Day 3 analysis on train only, get k*_train
- Check: does the lag relationship observed in train actually predict/describe the holdout period, or does it fall apart?
- Report an honest error/consistency metric, not just "yes it matches" — e.g. does the same-direction Granger result replicate on the holdout, does k* stay in a similar range
- **Output:** backtest comparison table, one paragraph of honest discussion if it *doesn't* hold up cleanly (that's a legitimate finding too)

### Day 5 — `pipeline.py` + robustness
**Goal:** tie it together, stress-test the finding.
- `pipeline.py`: given `--commodity` and `--states`, runs fetch → clean → analysis → validation → prints a report. This is the reusable tool from our earlier discussion — but built *last*, against modules already proven correct individually, not built first and hoped to work
- Robustness pass: repeat the whole analysis for a second state pair (e.g. Iowa vs. Nebraska — shorter expected lag, both major producers) as a control comparison
- Optional if time allows: repeat for soybeans as a second commodity (same availability profile as corn, cheap to add)

### Day 6 — Paper writing
Same structure as v1's Day 6 table, with updated content:
| Section | Content | Length |
|---|---|---|
| Abstract | Question, method, k* (in months), cointegration result | 200w |
| Introduction | Market integration/efficiency in interstate ag commodity markets — replaces the infrastructure-friction framing | 400w |
| Literature Review | Law of One Price, spatial market integration lit (still relevant — same theoretical base as v1, different empirical setting) | 400w |
| Data & Study Area | NASS QuickStats, why corn (exchange-traded → monthly coverage), why Iowa/Ohio | 300w |
| Methodology | Returns/TLCC, Granger, cointegration, train/holdout design | 500w |
| Results | k*, Granger result, cointegration result, backtest outcome | 600w |
| Discussion | What k* means for two well-connected Corn Belt states (contrast with what it would've meant for a genuinely isolated market) | 500w |
| Conclusion | Summary, future work (extend to more state pairs, other exchange-traded commodities) | 200w |

### Day 7 — Review, polish, package
Same as v1: reproducibility check, repo cleanup, final push.

```
/data/raw          → cached NASS pulls (per commodity/state/freq)
/data/processed    → cleaned merged panel
/src               → fetch.py, clean.py, analysis.py, validation.py, pipeline.py, config.py
/figures           → all PNGs, 300 DPI
/paper             → final PDF + source
/docs/journal      → your daily logs (already doing this — keep it up)
README.md
```

---

## One number to keep in mind (updated)

Your original plan anchored k* against NH-37 road transit time as a physical
sanity check. Iowa–Ohio doesn't have an equivalent single physical benchmark
— corn moves by truck, rail, and barge on varying schedules, and a lot of
the "lag" you'll measure is really about **information and contracting
speed**, not literal transit time. If k* comes out at 1 month, that's
consistent with efficient, tightly-integrated markets. If it's 3+ months,
that's the actual finding worth discussing — slower information transmission
than you'd expect between two major producers in the same broad region.
That reframing — physical logistics vs. market efficiency — is the new
version of the "triangulation" moment from v1.
