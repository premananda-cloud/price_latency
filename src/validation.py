"""
src/validation.py

Backtest: split the cleaned panel into train/holdout, re-run the
analysis on train only, then check whether the same headline findings
(k*, Granger direction, cointegration) hold up against the holdout
period the model never saw. This is the actual validation step v1
never had — a lag number with nothing checking it against real
subsequent data is just an assertion.
"""

import argparse
import pandas as pd

from config import PROCESSED_DATA_DIR
from analysis import load_panel, run_full_analysis, print_report


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
            f"Cointegration result FLIPPED: {'cointegrated' if train_cointegrated else 'not cointegrated'} "
            f"in train (p={train_coint_p:.4f}) vs. {'cointegrated' if full_cointegrated else 'not cointegrated'} "
            f"in full period (p={full_coint_p:.4f}). This suggests a STRUCTURAL BREAK — the long-run "
            "equilibrium relationship held historically but weakened/broke once recent data is included. "
            "Worth investigating when the break occurred rather than treating this as noise."
        )


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
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_backtest(
        commodity_desc=args.commodity, hub_state=args.hub, local_state=args.local,
        freq_desc=args.freq, holdout_start=args.holdout_start, max_lag=args.max_lag,
    )
