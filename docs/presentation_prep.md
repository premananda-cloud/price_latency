# Presentation Preparation & Adversarial Q&A

**Short-Run Synchronization Without Long-Run Equilibrium:
Price Transmission and Cointegration in U.S. Corn Belt Markets, 2015–2026**

Everything in this document is grounded in confirmed pipeline output.
No answer here speculates beyond what the data actually shows.

---

## Part 1: Your Two-Minute Verbal Summary

Memorise this. It is the answer to "tell me about your paper" and the
anchor for every other question. Every longer answer should circle back
to one of these three sentences.

> "We measured how corn price movements transmit between Iowa and Ohio
> using 11 years of monthly USDA data. The short-run answer is clear:
> both markets move together in the same month, with Iowa leading Ohio
> in a statistically significant and directional way. The long-run
> answer is more interesting: despite that tight synchronisation, Iowa
> and Ohio do not maintain a stable long-run equilibrium — and when we
> compare them to Iowa and Nebraska, which are on the same transport
> corridor, Nebraska does maintain that equilibrium. So corridor
> alignment appears to determine long-run integration even when
> short-run dynamics are similar."

---

## Part 2: Your Core Numbers

Know these cold. Write them on a card if needed. Every quantitative
question is answered from this list.

| What | Number |
|---|---|
| Sample | 137 months, Jan 2015 – May 2026, no gaps |
| k* (Iowa/Ohio) | 0 months |
| Bootstrap CI on k* | [0.0, 0.0] — both bounds exact zero |
| Peak correlation ρ (Iowa/Ohio) | 0.840 |
| Peak correlation ρ (Iowa/Nebraska) | 0.918 |
| Iowa→Ohio Granger sig. lags | 1 through 8 (p range: 0.0089–0.0452) |
| Ohio→Iowa Granger | Not significant (one isolated lag-8 artifact, p=0.047) |
| Iowa→Nebraska Granger sig. lags | All 12 (p range: 0.0000–0.0016) |
| Cointegration p (Iowa/Ohio, full) | 0.1545 — not significant |
| Cointegration p (Iowa/Nebraska, full) | 0.0082 — significant at 1% |
| Rolling coint. windows Iowa/Ohio | 20/78 (26%) — flickering |
| ZA p-value (Iowa/Ohio spread) | 0.8224 — no break |
| ZA p-value (Iowa/Nebraska spread) | 0.0000 — break at Sept 2022 |
| Train/full backtest — k* | Stable at 0 in both pairs |
| Train/full backtest — Granger direction | Stable (Iowa leads) in both |
| Train/full backtest — cointegration Iowa/Ohio | Unstable (0.0004 vs 0.1545) |
| Train/full backtest — cointegration Iowa/Nebraska | Stable (0.0415 vs 0.0082) |

---

## Part 3: Questions by Type

---

### Category A — Data Questions
*These come first, from any audience. They establish whether you
actually understand your own data source.*

---

**Q: Why USDA NASS? Why not futures prices or cash terminal prices?**

A: NASS price-received series is what farmers actually receive for their
corn — it's the appropriate series for a study about inter-state price
transmission at the producer level. Futures prices are the same number
everywhere by construction; using them would measure nothing. AMS Market
News terminal prices would have been a higher-frequency alternative and
are noted as a limitation, but they require a separate API registration
and aggregation decisions not in scope for this study.

---

**Q: Monthly data seems coarse. Can you really measure transmission lag
with monthly prices?**

A: Yes, with an important caveat that the paper states explicitly.
Monthly is the finest resolution NASS provides for price-received data.
Our k*=0 result means no lag is detectable at monthly resolution —
it does not mean transmission is instantaneous in a physical sense.
Any transmission occurring within a calendar month, including within
days or hours, would produce k*=0. We frame this as a resolution
constraint, not a claim about physical speed. The relevant finding at
monthly resolution is not "how fast" but "how stable," which is why
cointegration becomes the more informative test.

---

**Q: 137 months — is that enough data for the methods you're using?**

A: For TLCC and Granger at ±12 months, 137 observations is adequate.
For Engle-Granger cointegration, 137 observations gives reasonable
power. The rolling 60-month windows reduce effective sample size to
60 observations per test — this is a known limitation of rolling
analysis and is why we also run the full-period test as the primary
result. The bootstrap CI on k* uses 1,000 resamples, which is
standard practice. Where sample size limits apply — for instance,
the 29-month holdout is too short for a standalone TLCC — we are
explicit about it rather than running the test anyway.

---

**Q: You only have two state pairs. How do you know the corridor
hypothesis isn't just coincidence?**

A: We don't, and the paper says so. Two pairs is enough to motivate
the hypothesis; it is not enough to confirm it. The paper frames the
corridor interpretation as a plausible explanation that fits both the
cointegration contrast and the structural literature on inter-state
agricultural price differentials. Extending to additional corridor-defined
pairs — Ohio/Indiana as a same-corridor control, or Iowa/Illinois — is
the stated future work.

---

**Q: You started this project with Indian data and switched to US data.
Does that affect the integrity of the study?**

A: The switch is documented transparently in the repo — there is a
`PLAN_v2.md` that explains exactly what changed and why. The reason
for the switch was that the original Indian data source (Agmarknet)
offered only annual frequency for the produce commodities we intended
to study, which cannot support a sub-annual lag analysis. The US NASS
source was selected after empirically verifying availability across
7 states and multiple commodities. The scientific question evolved with
the data, which is normal in empirical research — what matters is that
the final methodology is appropriate for the final data, which it is.

---

### Category B — Methodology Questions
*These come from anyone with quantitative training. The harder ones
come from econometricians.*

---

**Q: Why TLCC and Granger rather than a Vector Autoregression (VAR)
or Error Correction Model (ECM)?**

A: TLCC gives an intuitive, model-free read of the lag structure before
imposing parametric assumptions. Granger causality in a VAR(k) framework
is exactly what statsmodels implements — each lag test fits a VAR of
that order. If the reviewer is asking about a full structural VAR: that
would be the natural next step if we had found cointegration in both
pairs, since an ECM requires cointegration as a precondition. For the
Iowa/Ohio pair, where cointegration is not confirmed, an ECM would be
misspecified. For Iowa/Nebraska, where cointegration holds, an ECM
would be a legitimate extension — and is noted as future work.

---

**Q: Your Granger tests at lag k test a VAR(k) — doesn't that mean each
lag k includes all lags 1 through k? So you can't interpret lag 8 as
"the 8-month effect."**

A: Correct, and the paper says this explicitly. The VAR(k) at lag k
tests whether the first k months of Iowa's price history jointly improve
prediction of Ohio's returns. A sequence of significant results from lag 1
through lag 8 means Iowa's cumulative price history up to 8 months back
carries predictive information — it does not identify which specific month
within that window is doing the work. The Granger results are about
information horizon, not a point estimate of a single lag effect. The TLCC
gives the point estimate (k*=0); the Granger gives the horizon.

---

**Q: Your bootstrap CI on k* is exactly [0, 0]. Isn't that suspicious?
Real bootstrap CIs usually have some spread.**

A: It reflects the strength of the contemporaneous signal. With ρ=0.84
at k=0 and the next highest correlation at roughly 0.40 at k=±1, the
gap between the peak and its neighbors is large enough that even highly
perturbed resamples consistently return k*=0. The bootstrap samples with
replacement from 137 paired observations across 1,000 resamples — a
tight CI in this context means the peak is not sensitive to which
particular months are included. If this is a concern in review, we can
report the k* distribution across bootstrap resamples rather than just
the CI bounds, but [0,0] is an honest output, not a rounding artefact.

---

**Q: Engle-Granger has known low power in small samples. How do you
know your non-cointegration result for Iowa/Ohio isn't just a power
problem?**

A: This is a legitimate concern and the paper acknowledges it as a
limitation. Three things partially address it. First, the rolling-window
test finds cointegration in 26% of windows — if the non-result were
purely a power problem, we would expect either consistent near-significance
or consistent non-significance, not rapid flickering across the threshold.
The flickering pattern is more consistent with a marginally
non-cointegrated relationship than with a power failure. Second, using
the same test on Iowa/Nebraska with the same sample size gives a highly
significant result (p=0.0082), which suggests the test has adequate power
to detect cointegration when it exists in this data. Third, Zivot-Andrews
finds no structural break, which rules out the alternative explanation
that cointegration held in a sub-period too short to detect with
full-period EG.

---

**Q: Why did you run the Zivot-Andrews test on the spread rather than
on price levels?**

A: Because the hypothesis being tested is about the relationship between
the two markets, not about either market individually. A structural break
in Iowa prices alone — say, a harvest shock — would appear in the spread
but would not necessarily imply a break in the long-run Iowa/Ohio
relationship. By running ZA on the spread, we are directly testing
whether the relationship between the two series changed, which is the
relevant question for cointegration instability. Price-level ZA tests
would tell us about individual market behavior, not inter-market structure.

---

**Q: The train-only Iowa/Ohio cointegration is p=0.0004 but the
full-period result is p=0.1545. That's a huge shift. Isn't one of them
wrong?**

A: Neither is wrong — they are answering the same question about
different samples and getting different answers, which is itself a result.
The rolling-window analysis explains it: Engle-Granger is sensitive to
window placement when the underlying relationship is marginal. The
training window (2015–2023) happens to capture a sample configuration
that produces a significant test statistic. Including the holdout period
(2024–2026) changes that configuration enough to push the result across
the threshold. The ZA test (p=0.822) confirms there is no discrete event
that caused this shift — it is window sensitivity, not a structural change.
If we had only the training result, we might claim cointegration. Having
both is more informative.

---

**Q: Iowa/Nebraska has a significant structural break at September 2022.
What caused it?**

A: The paper does not claim to know. September 2022 falls within a
documented period of unusual basis behavior across the Corn Belt — Iowa
Farm Bureau (2022) describes tight corn and soybean supplies keeping cash
prices elevated above futures for extended periods, which is a departure
from pre-2021 norms. But we do not have the data or the tests in this
paper to attribute the break to any specific mechanism. The break is
reported as a finding; the mechanism is identified as future work. Saying
"we don't know" is the correct answer here — the alternative would be
speculation dressed as analysis.

---

**Q: Why didn't you use the Johansen test instead of Engle-Granger for
cointegration?**

A: Engle-Granger is appropriate for a two-variable system, which is what
we have — one hub series, one local series. Johansen's procedure is
designed for systems with more than two variables, where multiple
cointegrating vectors may exist. For a bivariate system, both tests
have the same theoretical basis. Johansen would be the right choice if
we extended this to a multi-state panel simultaneously — for example,
testing whether Iowa, Ohio, and Nebraska share a common stochastic trend
— and is noted as a natural extension.

---

**Q: You describe Iowa as the "hub" or price-setting market. How do you
justify that designation before running the tests?**

A: The hub/local designation is a prior based on Iowa's structural
position — it is the largest U.S. corn-producing state and is treated
as a reference market in the spatial price literature. We then test
whether that designation is supported by the data, and it is: Granger
causality runs Iowa→Ohio and Iowa→Nebraska at conventional significance,
while neither reverse direction is supported. The designation is a
testable hypothesis that the data confirms, not an unfalsifiable
assumption.

---

### Category C — Results Questions
*These probe whether you understand what your own numbers mean.*

---

**Q: k*=0 with ρ=0.84. If the markets move together in the same month,
what exactly is the Granger causality telling you that TLCC doesn't?**

A: TLCC tells you where the contemporaneous correlation peaks. Granger
tells you whether Iowa's past values contain information about Ohio's
future values beyond what Ohio's own past tells you. These are different
questions. A market can be tightly correlated with Iowa today (high ρ at
k=0) while Iowa's history also helps predict Ohio's future (Granger
significant at lags 1–8). The Granger result means: if you are trying
to forecast Ohio corn prices next month, knowing last month's Iowa price
gives you information you cannot get from Ohio's own price history alone.
That is a price leadership finding, not a lag finding.

---

**Q: The Ohio→Iowa Granger has one significant hit at lag 8 (p=0.047).
Why are you dismissing it?**

A: Because it is isolated. Every adjacent lag — lag 7 (p=0.080) and
lag 9 (p=0.052) — is non-significant. With 12 simultaneous tests at
α=0.05, we expect approximately 0.6 false positives by chance alone.
One isolated significant result surrounded by non-significant neighbors
is the textbook profile of a false positive. The Iowa/Nebraska
Ohio→Iowa result, by contrast, has no isolated hits — p-values go as
high as 0.995. The contrast between the two pairs is itself evidence
that the Iowa/Ohio lag-8 result is noise.

---

**Q: Your rolling cointegration finds significance in only 26% of
windows. Isn't 26% actually higher than chance at α=0.05, which
would give 5%?**

A: Yes — 26% is higher than what you would expect from a purely
non-cointegrated series with no structure. This is worth addressing
directly. A random I(1) process tested at α=0.05 with the Engle-Granger
test would produce false positives at roughly the 5% rate, not 26%.
The 26% rate suggests the Iowa/Ohio pair is not completely unrelated in
the long run — there is something there — but the relationship is not
strong or stable enough to maintain significance consistently. The
flickering pattern across adjacent windows confirms this: it is a
marginal relationship, not an absent one.

---

**Q: You say the spread plot shows a "regime shift" from 2020 to 2023.
But the Zivot-Andrews test says there is no structural break. How do
you reconcile those?**

A: The visual appearance of a regime shift and the ZA non-result are
compatible. ZA is designed to detect a single abrupt break — a step
change at a specific date. What the spread plot shows is a gradual,
multi-year drift: the spread narrows and inverts over roughly three years,
then partially recovers. A slow, continuous drift does not produce the
kind of concentrated test statistic ZA needs to reject the null. ZA
finding nothing means there is no single date at which we can say "the
relationship broke here." It does not mean the spread was stable. Those
are different statements.

---

**Q: If Iowa/Nebraska is cointegrated and Iowa/Ohio is not, what does
that tell us about Ohio specifically? Is Ohio just a "bad" market?**

A: Not bad — structurally different. The cointegration difference is
predicted by the corridor hypothesis before looking at the results:
Nebraska and Iowa face similar freight cost structures and sell into
similar end-use markets (Gulf export terminals, western ethanol
facilities). External shocks — a change in Gulf basis, a rail rate
move, a drought affecting river barge capacity — affect both states'
prices similarly and in the same direction, keeping the spread stable.
Ohio sells into eastern feed markets and Great Lakes export routes.
The same external shocks affect Ohio differently from Iowa, so the
spread between them drifts without a systematic correction mechanism.
This is not a quality judgment; it is a structural observation about
market linkages.

---

### Category D — Framing and Scope Questions
*These come from generalist audiences or discussants who want to
challenge the contribution.*

---

**Q: What's the practical implication of this research? Who should care?**

A: Three audiences. First, agricultural economists studying market
integration — the finding that short-run synchronisation and long-run
cointegration can decouple is methodologically important for how
integration is assessed. Using only one of these tests, as many studies
do, would give an incomplete picture. Second, commodity traders and
market analysts — the Granger result means Iowa prices have an ~8-month
predictive horizon for Ohio prices, which has basis trading implications.
Third, agricultural policy researchers — cointegration (or its absence)
determines whether price support interventions in one state are likely
to transmit to neighboring states in the long run.

---

**Q: The title says "without long-run equilibrium." But Iowa/Nebraska
IS cointegrated. So the title is misleading — it only describes one
of your two pairs.**

A: The title refers to the primary pair (Iowa/Ohio), which is the main
analysis and the majority of the paper. The Nebraska comparison is the
robustness check that explains the Iowa/Ohio result by contrast. The
full title is: "Short-Run Synchronization Without Long-Run Equilibrium:
Price Transmission and Cointegration in U.S. Corn Belt Markets,
2015–2026." The subtitle "Corn Belt Markets" is plural — it covers both
pairs. But if a reviewer pushes on this, it is a fair point: a title
like "Short-Run Synchronization Without Robust Long-Run Equilibrium"
would be more precise. That is a revision-worthy note, not a fatal flaw.

---

**Q: Isn't k*=0 an expected, uninteresting result for two US states
that both price off the CME?**

A: In isolation, yes — it is an expected result. What makes it
interesting is the combination with the long-run result. If your prior
is that both states price off CME, you would also expect them to be
cointegrated — anchored to the same long-run signal. Iowa/Ohio
satisfies the first expectation but not the second. That combination
is the contribution: showing that the mechanism producing tight
short-run co-movement (CME price discovery) does not automatically
produce long-run equilibrium when corridor-specific basis dynamics
intervene. The paper is not saying "look, prices are correlated" — it
is saying "correlation and equilibrium are separable, and corridor
structure is the mechanism."

---

**Q: You say Iowa is the price leader. But both states price off CBOT
futures. Isn't CBOT the real price leader?**

A: Yes — and the paper is explicit that k*=0 is consistent with both
states pricing off a shared CME/CBOT reference signal. The Granger
result refines that picture: even though the contemporaneous CBOT signal
hits both states in the same month, Iowa's price history carries
additional information about Ohio's future returns beyond what CBOT
alone would predict. One explanation is that Iowa incorporates local
supply and demand signals (ethanol demand, harvest conditions, storage
economics) into its cash price before those signals show up in Ohio's
cash price. The Granger result is about that additional local
information, not about futures leadership.

---

**Q: You changed your research question midway through from Indian
markets to US markets. How do you know you didn't just keep changing
until you found something that worked?**

A: The question changed because the data did not support the original
design at the required frequency — not because the results were
inconvenient. The change is fully documented in the repository. The
US analysis was then run prospectively with a pre-registered pipeline:
data was downloaded, cleaned, and analysed using code written before
the results were seen, with a train/holdout split that held out data
the model never touched. If we had been searching for a convenient
result, the Iowa/Ohio cointegration non-result would have prompted
another pivot — instead it is the paper's central finding.

---

## Part 4: Things You Should Not Say

These are the specific traps to avoid. Each has a better alternative.

| Do NOT say | Say instead |
|---|---|
| "Iowa prices cause Ohio prices" | "Iowa prices Granger-cause Ohio prices" — Granger is a predictive test, not a causal claim |
| "The Ukraine war caused the spread inversion" | "September 2022 is within a period of documented unusual basis behavior; the specific mechanism is not identified in this analysis" |
| "There is no lag" | "No lag is detectable at monthly resolution" |
| "The markets are efficient" | "The results are consistent with efficient price discovery at monthly resolution" — efficiency is a claim about the process, not just the lag |
| "The model shows..." | "The analysis shows..." — you don't have a model, you have a set of statistical tests |
| "Obviously..." or "Clearly..." | Just state the finding — hedging words signal uncertainty disguised as confidence |
| "The data proves..." | "The results are consistent with..." — statistics never prove, they support or fail to reject |
| Any specific causal claim about September 2022 | "A statistically significant structural break was detected. The mechanism is not identified and is a subject for future research." |

---

## Part 5: The Three Hardest Questions and How to Hold Your Ground

These are the questions most likely to make you stumble. Practise
answering them out loud.

---

**Hard Q1: "Your Iowa/Ohio cointegration result changed dramatically
between your training and full period. How can you trust any of your
other results?"**

Hold your ground: "The cointegration instability is the finding, not a
failure of the analysis. We ran the rolling-window test precisely to
characterise it, and the Zivot-Andrews test to rule out a discrete break.
The short-run results — k*=0 and Granger asymmetry — are stable across
both samples, as shown in the backtest table. We are not claiming that
all results are stable; we are claiming that the specific results we
report as findings are stable, and we are honest about which ones are
not."

---

**Hard Q2: "Two state pairs is not enough to conclude anything about
corridor alignment. This could be coincidence."**

Hold your ground: "Agreed that two pairs is insufficient to confirm the
hypothesis — the paper says exactly that. What two pairs gives us is
enough to motivate and structure the hypothesis clearly, which is the
appropriate scope for a sprint study of this length. The corridor
alignment interpretation fits the data and has a structural basis in
the freight and basis literature. Ruling it out would require a pair
that shares a corridor but is not cointegrated, or that crosses
corridors but is cointegrated. Testing those conditions is the stated
future work."

---

**Hard Q3: "If both markets price off CBOT, what are you actually
measuring? Isn't your 'price transmission' just the same futures price
showing up in two places?"**

Hold your ground: "NASS price-received series are cash prices, not
futures prices. Cash prices deviate from futures by the basis — a
location-specific differential reflecting local storage costs, transport
costs, and local demand conditions. The Granger result captures
information transmission in the basis, not in the futures price. The
question is whether Iowa's basis moves predict Ohio's basis moves.
The answer is yes, directionally and asymmetrically, across an
8-month horizon. That is not trivially explained by a shared futures
signal."

---

## Part 6: Opening and Closing Lines

**Opening (after you introduce the title):**
> "I want to be upfront about one methodological constraint upfront:
> the data is monthly. That means we cannot detect lags shorter than
> a month, and k*=0 is not a claim about instantaneous transmission —
> it means the lag, if there is one, is shorter than our measurement
> resolution. The interesting result in this paper is not the lag
> estimate. It's what happens when you ask whether these well-connected
> markets maintain a stable long-run relationship — and why the answer
> differs between two pairs that look almost identical in the short run."

**Closing (before questions):**
> "To summarise: same-month co-movement is strong and stable across
> both pairs and across the holdout period. Iowa leads predictively
> but not in a physical-lag sense. What separates the pairs is the
> long run: corridor alignment determines whether short-run
> synchronisation produces a stable equilibrium or a drifting one.
> We think that distinction is underappreciated in how market
> integration is typically assessed."
