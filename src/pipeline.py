"""
src/pipeline.py

Orchestrates fetch -> clean -> analysis -> validation for a given
commodity/hub/local state pair, and prints a single consolidated
report. This is the "reusable tool" version of the project — built
last, on top of modules already proven individually (see README.md
validated-status table), not built first and hoped to work.

Usage:
    python pipeline.py --commodity CORN --hub IOWA --local OHIO \
        --year-start 2015 --year-end 2026 --holdout-start 2024-01-01
"""

import argparse

from fetch import fetch_multi_state, NASSFetchError
from clean import clean_and_save, CleaningError
from analysis import run_full_analysis, print_report, find_structural_break
from validation import run_backtest


class PipelineError(Exception):
    """Raised when any pipeline stage fails in a way that should stop the run."""


def run_pipeline(
    commodity_desc: str,
    hub_state: str,
    local_state: str,
    year_start: int,
    year_end: int,
    freq_desc: str = "MONTHLY",
    statisticcat_desc: str = "PRICE RECEIVED",
    agg_level_desc: str = "STATE",
    holdout_start: str = "2024-01-01",
    max_lag: int = 12,
    skip_fetch: bool = False,
):
    """
    Full pipeline: fetch (unless skipped, e.g. re-running against
    already-cached data) -> clean -> analysis -> backtest validation ->
    structural break test on the spread. Prints one consolidated
    report and returns the key results as a dict for programmatic use.
    """
    hub, local = hub_state.lower(), local_state.lower()

    print(f"=== PIPELINE: {commodity_desc} — {hub_state} (hub) vs {local_state} (local) ===\n")

    # --- Stage 1: fetch ---
    if not skip_fetch:
        print("--- Stage 1/4: fetch ---")
        try:
            fetch_multi_state(
                commodity_desc, [hub_state, local_state], year_start, year_end,
                freq_desc=freq_desc, statisticcat_desc=statisticcat_desc,
                agg_level_desc=agg_level_desc,
            )
        except NASSFetchError as exc:
            raise PipelineError(f"Fetch stage failed: {exc}") from exc
    else:
        print("--- Stage 1/4: fetch (skipped, using cached data) ---")

    # --- Stage 2: clean ---
    print("\n--- Stage 2/4: clean ---")
    try:
        panel = clean_and_save(
            commodity_desc, hub_state, local_state,
            freq_desc=freq_desc, statisticcat_desc=statisticcat_desc,
            agg_level_desc=agg_level_desc,
            year_start=year_start, year_end=year_end,
        )
    except CleaningError as exc:
        raise PipelineError(f"Clean stage failed: {exc}") from exc

    # --- Stage 3: analysis ---
    print("\n--- Stage 3/4: analysis ---")
    report = run_full_analysis(panel, hub_state=hub, local_state=local, max_lag=max_lag)
    print_report(report, hub_state=hub, local_state=local)

    break_result = find_structural_break(panel["spread"], "spread")
    significant = break_result["p_value"] < 0.05
    print("\n=== Zivot-Andrews structural break test (on spread) ===")
    print(f"candidate break_date = {break_result['break_date'].date()}")
    print(f"za_stat = {break_result['za_stat']:.3f}  p = {break_result['p_value']:.4f}")
    print(f"significant at 5%: {significant}")
    if not significant:
        print("No confirmed structural break — do not report the candidate date as real.")

    # --- Stage 4: validation ---
    print("\n--- Stage 4/4: validation (train/holdout backtest) ---")
    train_report, full_report = run_backtest(
        commodity_desc=commodity_desc, hub_state=hub_state, local_state=local_state,
        freq_desc=freq_desc, holdout_start=holdout_start, max_lag=max_lag,
    )

    print(f"\n=== PIPELINE COMPLETE: {commodity_desc} — {hub_state} vs {local_state} ===")

    return {
        "panel": panel,
        "analysis_report": report,
        "structural_break": break_result,
        "train_report": train_report,
        "full_report": full_report,
    }


def _parse_args():
    parser = argparse.ArgumentParser(description="Run the full fetch->clean->analysis->validation pipeline")
    parser.add_argument("--commodity", default="CORN")
    parser.add_argument("--hub", default="IOWA")
    parser.add_argument("--local", default="OHIO")
    parser.add_argument("--year-start", type=int, default=2015)
    parser.add_argument("--year-end", type=int, default=2026)
    parser.add_argument("--freq", default="MONTHLY")
    parser.add_argument("--statisticcat", default="PRICE RECEIVED")
    parser.add_argument("--agg-level", default="STATE")
    parser.add_argument("--holdout-start", default="2024-01-01")
    parser.add_argument("--max-lag", type=int, default=12)
    parser.add_argument("--skip-fetch", action="store_true", help="Use already-cached raw data, don't re-hit the API")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    try:
        run_pipeline(
            args.commodity, args.hub, args.local,
            args.year_start, args.year_end,
            freq_desc=args.freq, statisticcat_desc=args.statisticcat,
            agg_level_desc=args.agg_level, holdout_start=args.holdout_start,
            max_lag=args.max_lag, skip_fetch=args.skip_fetch,
        )
    except PipelineError as exc:
        print(f"\nPIPELINE FAILED: {exc}")
        raise SystemExit(1)
