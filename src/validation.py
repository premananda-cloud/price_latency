"""
src/validation.py

Two kinds of robustness check for the same headline findings (k*,
Granger direction, cointegration):

1. Temporal — split into train/holdout, re-run on train only, compare
   against the full period. (v1's original gap: a lag number with
   nothing checking it against real subsequent data is just an
   assertion.)

2. Spatial/pair — re-run the same hub state against several other
   local states, to check whether the findings are specific to one
   pair (Iowa/Ohio) or hold up more generally. This is the piece the
   README's open items flagged as not yet done ("only one commodity/
   state pair has been run"). It assumes the other pairs' panels have
   already been fetched + cleaned (via pipeline.py or fetch.py/clean.py
   directly) — this module only loads and analyzes, so re-running it
   doesn't re-hit the NASS API.
"""

import argparse
import pandas as pd

from config import PROCESSED_DATA_DIR, FIGURES_DIR
from analysis import load_panel, run_full_analysis, print_report, AnalysisError


def split_panel(df: pd.DataFrame, holdout_start: str):
    """
    Split on a date string (e.g. '2024-01-01'). Train is everything
    strictly before holdout_start; holdout is everything from
    holdout_start onward.
    """
    train = df[df.index < holdout_start].copy()
    holdout = df[df.index >= holdout_start].copy()
    return train, holdout


def compare_reports(train_report: dict, full_report: dict, hub_state: str, local_state: str):
    """
    Print a side-by-side comparison of the headline stats from the
    train-only run vs. the full-period run, so it's obvious at a
    glance whether the finding is stable or falls apart.
    """
    print("=== Backtest comparison: train-only vs. full period ===\n")

    print(f"{'metric':<28} {'train':>15} {'full':>15}")
    print(f"{'k* (months)':<28} {train_report['k_star']:>15} {full_report['k_star']:>15}")
    print(
        f"{'peak correlation':<28} "
        f"{train_report['peak_corr']:>15.3f} {full_report['peak_corr']:>15.3f}"
    )
    print(
        f"{'k* 95% CI':<28} "
        f"{str(train_report['k_star_ci']):>15} {str(full_report['k_star_ci']):>15}"
    )

    train_min_p = min(train_report["granger_hub_causes_local"].values())
    full_min_p = min(full_report["granger_hub_causes_local"].values())
    print(
        f"{'min p, hub->local Granger':<28} "
        f"{train_min_p:>15.4f} {full_min_p:>15.4f}"
    )

    train_coint_p = train_report["cointegration"]["p_value"]
    full_coint_p = full_report["cointegration"]["p_value"]
    print(
        f"{'cointegration p-value':<28} "
        f"{train_coint_p:>15.4f} {full_coint_p:>15.4f}"
    )

    print("\n=== Read ===")
    if train_report["k_star"] == full_report["k_star"]:
        print(f"k* is STABLE at {full_report['k_star']} months across train and full period.")
    else:
        print(
            f"k* CHANGED from {train_report['k_star']} (train) to "
            f"{full_report['k_star']} (full) — the lag estimate is not stable, "
            "report this honestly rather than picking one."
        )

    hub_leads_train = train_min_p < 0.05
    hub_leads_full = full_min_p < 0.05
    if hub_leads_train == hub_leads_full:
        print(
            f"{hub_state}->{local_state} Granger significance is CONSISTENT "
            f"({'significant' if hub_leads_full else 'not significant'} in both)."
        )
    else:
        print(
            f"{hub_state}->{local_state} Granger significance CHANGED between "
            "train and full period — the causality direction is not robust, "
            "note this as a limitation."
        )

    train_cointegrated = train_coint_p < 0.05
    full_cointegrated = full_coint_p < 0.05
    if train_cointegrated == full_cointegrated:
        print(
            f"Cointegration result is CONSISTENT "
            f"({'cointegrated' if full_cointegrated else 'not cointegrated'} in both)."
        )
    else:
        print(
            f"Cointegration result CHANGED: {'cointegrated' if train_cointegrated else 'not cointegrated'} "
            f"in train (p={train_coint_p:.4f}) vs. {'cointegrated' if full_cointegrated else 'not cointegrated'} "
            f"in full period (p={full_coint_p:.4f}). NOTE: a Zivot-Andrews structural break test on the "
            "spread (run separately via `analysis.py --break-test`) found NO statistically significant "
            "single break point — so this instability is better explained as sensitivity to a slow, wide "
            "cyclical pattern in the spread than as evidence of a discrete structural break. Don't call "
            "this a 'structural break' without that caveat."
        )


def run_pair_robustness(
    commodity_desc: str,
    hub_state: str,
    local_states: list,
    freq_desc: str = "MONTHLY",
    max_lag: int = 12,
) -> tuple:
    """
    Re-run the full analysis for the same hub state against several
    other local states, to check whether k*, Granger direction, and
    cointegration are specific to one pair or generalize.

    Each local state's cleaned panel is expected to already exist
    (produced separately via pipeline.py or fetch.py/clean.py for that
    pair) — this function only loads and analyzes, it never fetches.
    A missing or too-small panel for a given local state is recorded
    as a row with status != "ok" rather than raising, so one bad pair
    doesn't take down the whole robustness check.

    Returns (summary_df, reports) where summary_df has one row per
    local state and reports is {local_state: full report dict} for
    the pairs that succeeded.
    """
    hub = hub_state.lower()
    rows = []
    reports = {}

    for local_state in local_states:
        local = local_state.lower()
        row = {"local_state": local_state}
        try:
            df = load_panel(
                commodity_desc=commodity_desc, hub_state=hub_state,
                local_state=local_state, freq_desc=freq_desc,
            )
        except FileNotFoundError:
            row["status"] = "no cleaned panel found — run pipeline.py/clean.py for this pair first"
            rows.append(row)
            continue

        try:
            report = run_full_analysis(df, hub_state=hub, local_state=local, max_lag=max_lag)
        except AnalysisError as exc:
            row["status"] = f"analysis failed: {exc}"
            rows.append(row)
            continue

        reports[local_state] = report
        c = report["cointegration"]
        row.update({
            "status": "ok",
            "n_months": len(df),
            "k_star": report["k_star"],
            "k_star_ci_low": report["k_star_ci"][0],
            "k_star_ci_high": report["k_star_ci"][1],
            "peak_corr": round(report["peak_corr"], 4),
            "granger_hub_to_local_min_p": round(min(report["granger_hub_causes_local"].values()), 4),
            "granger_local_to_hub_min_p": round(min(report["granger_local_causes_hub"].values()), 4),
            "cointegration_p": round(c["p_value"], 4),
            "cointegrated_5pct": c["p_value"] < 0.05,
        })
        rows.append(row)

    summary = pd.DataFrame(rows)
    return summary, reports


def print_pair_robustness(summary: pd.DataFrame, hub_state: str):
    """
    Print the pair-robustness table plus a plain-language read on
    whether each headline finding is a one-pair fluke or holds up.
    """
    print(f"=== Pair robustness: {hub_state} vs. {list(summary['local_state'])} ===\n")
    print(summary.to_string(index=False))

    ok = summary[summary["status"] == "ok"]
    skipped = summary[summary["status"] != "ok"]
    if len(skipped):
        print(f"\n{len(skipped)} pair(s) skipped (see status column above) — read below applies only to the {len(ok)} that ran.")

    print("\n=== Read ===")
    if len(ok) == 0:
        print("No pairs produced a usable report — nothing to compare.")
        return

    k_stars = ok["k_star"].unique()
    if len(k_stars) == 1:
        print(f"k* is CONSISTENT at {k_stars[0]} months across all {len(ok)} tested pairs.")
    else:
        print(
            f"k* VARIES across pairs ({dict(zip(ok['local_state'], ok['k_star']))}) — "
            "the lag finding is pair-specific, not a general property of the hub state."
        )

    granger_sig = ok["granger_hub_to_local_min_p"] < 0.05
    if granger_sig.all():
        print(f"{hub_state}->local Granger significance HOLDS for all tested pairs.")
    elif not granger_sig.any():
        print(f"{hub_state}->local Granger significance does NOT hold for any tested pair.")
    else:
        holds_for = list(ok.loc[granger_sig, "local_state"])
        fails_for = list(ok.loc[~granger_sig, "local_state"])
        print(
            f"{hub_state}->local Granger significance is MIXED: holds for {holds_for}, "
            f"not for {fails_for} — the causality direction found in the original pair "
            "is not a general property of the hub state."
        )

    coint_sig = ok["cointegrated_5pct"]
    if coint_sig.all():
        print("Cointegration HOLDS for all tested pairs.")
    elif not coint_sig.any():
        print("Cointegration does NOT hold for any tested pair (consistent with the weak, "
              "flickering cointegration already found for the original pair).")
    else:
        holds_for = list(ok.loc[coint_sig, "local_state"])
        fails_for = list(ok.loc[~coint_sig, "local_state"])
        print(f"Cointegration is MIXED: holds for {holds_for}, not for {fails_for}.")


def plot_pair_robustness(summary: pd.DataFrame, hub_state: str, out_name: str = None):
    """
    Bar chart of k* (with bootstrap CI) per tested local state, so
    it's visible at a glance whether the lag finding is stable across
    pairs or specific to one. Skipped pairs (no panel / analysis
    failure) are omitted from the plot, not shown as zero.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ok = summary[summary["status"] == "ok"]
    if len(ok) == 0:
        print("No successful pairs to plot — skipping pair-robustness figure.")
        return None

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(max(6, 1.5 * len(ok)), 5))
    x = range(len(ok))
    yerr = [
        ok["k_star"] - ok["k_star_ci_low"],
        ok["k_star_ci_high"] - ok["k_star"],
    ]
    ax.bar(x, ok["k_star"], yerr=yerr, capsize=5)
    ax.set_xticks(list(x))
    ax.set_xticklabels(ok["local_state"])
    ax.axhline(0, color="gray", linewidth=0.8)
    ax.set_ylabel("k* (months, + = hub leads local)")
    ax.set_title(f"k* by local state, hub = {hub_state}")

    if out_name is None:
        out_name = f"fig_pair_robustness_{hub_state.lower()}.png"
    out_path = FIGURES_DIR / out_name
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"Saved pair-robustness plot -> {out_path}")
    return out_path



def run_backtest(
    commodity_desc: str = "CORN",
    hub_state: str = "IOWA",
    local_state: str = "OHIO",
    freq_desc: str = "MONTHLY",
    holdout_start: str = "2024-01-01",
    max_lag: int = 12,
):
    df = load_panel(
        commodity_desc=commodity_desc, hub_state=hub_state,
        local_state=local_state, freq_desc=freq_desc,
    )
    hub, local = hub_state.lower(), local_state.lower()

    train, holdout = split_panel(df, holdout_start)
    print(f"Train: {train.index.min().date()} to {train.index.max().date()} ({len(train)} months)")
    print(f"Holdout: {holdout.index.min().date()} to {holdout.index.max().date()} ({len(holdout)} months)\n")

    if len(holdout) <= max_lag:
        print(
            f"Warning: holdout has only {len(holdout)} months, <= max_lag={max_lag}. "
            "Can't run a standalone TLCC on the holdout alone — comparing train "
            "vs. full period instead, which still tells you if train-derived "
            "findings generalize to the full including-holdout sample."
        )

    train_report = run_full_analysis(train, hub_state=hub, local_state=local, max_lag=max_lag)
    full_report = run_full_analysis(df, hub_state=hub, local_state=local, max_lag=max_lag)

    print("--- TRAIN-ONLY REPORT ---")
    print_report(train_report, hub_state=hub, local_state=local)

    print("\n--- FULL-PERIOD REPORT ---")
    print_report(full_report, hub_state=hub, local_state=local)

    print()
    compare_reports(train_report, full_report, hub, local)

    return train_report, full_report


def _parse_args():
    parser = argparse.ArgumentParser(description="Backtest: train/holdout validation of the lag analysis")
    parser.add_argument("--commodity", default="CORN")
    parser.add_argument("--hub", default="IOWA")
    parser.add_argument("--local", default="OHIO")
    parser.add_argument("--freq", default="MONTHLY")
    parser.add_argument("--holdout-start", default="2024-01-01")
    parser.add_argument("--max-lag", type=int, default=12)
    parser.add_argument(
        "--robustness-pairs", default=None,
        help="Comma-separated list of additional local states to test the same "
             "hub against, e.g. NEBRASKA,ILLINOIS. Panels for these must already "
             "be fetched+cleaned; this only loads and analyzes, it doesn't fetch.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_backtest(
        commodity_desc=args.commodity, hub_state=args.hub, local_state=args.local,
        freq_desc=args.freq, holdout_start=args.holdout_start, max_lag=args.max_lag,
    )

    if args.robustness_pairs:
        local_states = [s.strip().upper() for s in args.robustness_pairs.split(",") if s.strip()]
        print("\n")
        summary, reports = run_pair_robustness(
            commodity_desc=args.commodity, hub_state=args.hub,
            local_states=local_states, freq_desc=args.freq, max_lag=args.max_lag,
        )
        print_pair_robustness(summary, args.hub)
        plot_pair_robustness(summary, args.hub)
