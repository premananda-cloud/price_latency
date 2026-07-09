"""
src/experiment.py

Experiment tracking layer on top of pipeline.py. Every run gets its own
self-contained, timestamped folder — figures, tables, manifest, and a
short auto-generated report — plus one row appended to a top-level
registry.csv so multiple experiments (different pairs, different
params, re-runs) can be compared without opening each folder.

This module does NOT change fetch/clean/analysis/validation/pipeline —
it calls pipeline.run_pipeline() and analysis.py's existing plotting
functions, then organizes what comes back.

Usage — full default run (Iowa/Ohio corn, same defaults as pipeline.py):
    python experiment.py

Override anything:
    python experiment.py --hub IOWA --local NEBRASKA --rolling-coint

Test the same hub against other local states in the same run (dumped
into this experiment's own folder, not a separate one):
    python experiment.py --robustness-pairs NEBRASKA,ILLINOIS

Everything pipeline.py accepts, experiment.py also accepts and passes
through unchanged; the only new flags are --experiment-name, --notes,
--rolling-coint, --rolling-window, and --robustness-pairs.
"""

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, date
from pathlib import Path

import pandas as pd

try:
    from config import BASE_DIR
except ImportError:
    # Fallback if config.py doesn't export BASE_DIR under this name —
    # assumes this file lives in <project_root>/src/.
    BASE_DIR = Path(__file__).resolve().parent.parent

import analysis
from analysis import (
    plot_tlcc, plot_spread, plot_rolling_cointegration,
    rolling_cointegration,
)
import validation
from validation import run_pair_robustness, print_pair_robustness, plot_pair_robustness
from pipeline import run_pipeline, PipelineError

EXPERIMENTS_DIR = BASE_DIR / "experiments"
REGISTRY_PATH = EXPERIMENTS_DIR / "registry.csv"

REGISTRY_FIELDS = [
    "run_id", "timestamp", "commodity", "hub", "local",
    "year_start", "year_end", "holdout_start", "max_lag",
    "n_months", "k_star", "k_star_ci_low", "k_star_ci_high", "peak_corr",
    "granger_hub_to_local_min_p", "granger_local_to_hub_min_p",
    "cointegration_p_full", "cointegration_p_train",
    "za_break_p", "za_break_date",
    "rolling_coint_pct_windows",
    "robustness_pairs_tested", "robustness_k_star_consistent",
    "git_commit", "notes",
]


def _git_commit() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=BASE_DIR, stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except Exception:
        return "unknown"


def _package_versions() -> dict:
    versions = {}
    for pkg in ["pandas", "numpy", "scipy", "statsmodels", "matplotlib"]:
        try:
            from importlib.metadata import version
            versions[pkg] = version(pkg)
        except Exception:
            versions[pkg] = "unknown"
    return versions


def _panel_fingerprint(panel: pd.DataFrame) -> str:
    """Short hash of the cleaned panel's actual content, so a manifest
    can be checked against the data it claims to have analyzed."""
    payload = panel.to_csv().encode()
    return hashlib.sha256(payload).hexdigest()[:12]


def _make_run_id(params: dict) -> str:
    param_hash = hashlib.sha256(
        json.dumps(params, sort_keys=True, default=str).encode()
    ).hexdigest()[:6]
    today = date.today().isoformat()
    return f"{today}_{params['commodity'].lower()}_{params['hub'].lower()}-{params['local'].lower()}_{param_hash}"


def _setup_experiment_dir(run_id: str) -> dict:
    exp_dir = EXPERIMENTS_DIR / run_id
    if exp_dir.exists():
        raise FileExistsError(
            f"Experiment folder {exp_dir} already exists — this exact "
            "param set has already been run today. Pass --notes or change "
            "a param if you meant to run a genuinely new variant, or "
            "delete the old folder if this was a throwaway."
        )
    subdirs = {
        "root": exp_dir,
        "data": exp_dir / "data",
        "figures": exp_dir / "figures",
        "tables": exp_dir / "tables",
        "logs": exp_dir / "logs",
    }
    for path in subdirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return subdirs


class _Tee:
    """Mirrors stdout to a log file as well as the terminal, so
    pipeline.py's existing print()-based output becomes a saved log
    without touching pipeline.py itself."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            s.write(data)
            s.flush()

    def flush(self):
        for s in self.streams:
            s.flush()


def _save_tables(dirs: dict, result: dict, rolling_df: pd.DataFrame = None,
                  robustness_summary: pd.DataFrame = None):
    report = result["analysis_report"]
    train_report = result["train_report"]
    full_report = result["full_report"]
    break_result = result["structural_break"]

    # --- ADF / stationarity ---
    adf_rows = []
    for key in ["adf_hub_price", "adf_local_price", "adf_hub_returns", "adf_local_returns"]:
        r = report[key]
        adf_rows.append({
            "series": r["label"], "adf_stat": r["adf_stat"],
            "p_value": r["p_value"], "n_obs": r["n_obs"],
            "stationary_at_5pct": r["stationary_at_5pct"],
        })
    pd.DataFrame(adf_rows).to_csv(dirs["tables"] / "stationarity_adf.csv", index=False)

    # --- TLCC summary ---
    pd.DataFrame([{
        "k_star_months": report["k_star"],
        "peak_correlation": report["peak_corr"],
        "ci_low": report["k_star_ci"][0],
        "ci_high": report["k_star_ci"][1],
    }]).to_csv(dirs["tables"] / "tlcc_summary.csv", index=False)

    pd.DataFrame({
        "lag_months": report["tlcc_lags"],
        "cross_correlation": report["tlcc_corr"],
    }).to_csv(dirs["tables"] / "tlcc_full_curve.csv", index=False)

    # --- Granger, both directions ---
    pd.DataFrame([
        {"lag": lag, "p_value": p, "significant_5pct": p < 0.05}
        for lag, p in report["granger_hub_causes_local"].items()
    ]).to_csv(dirs["tables"] / "granger_hub_to_local.csv", index=False)

    pd.DataFrame([
        {"lag": lag, "p_value": p, "significant_5pct": p < 0.05}
        for lag, p in report["granger_local_causes_hub"].items()
    ]).to_csv(dirs["tables"] / "granger_local_to_hub.csv", index=False)

    # --- Cointegration + structural break ---
    c = report["cointegration"]
    pd.DataFrame([{
        "eg_score": c["score"], "p_value": c["p_value"],
        "crit_1pct": c["crit_values"][0], "crit_5pct": c["crit_values"][1],
        "crit_10pct": c["crit_values"][2],
    }]).to_csv(dirs["tables"] / "cointegration_full_period.csv", index=False)

    pd.DataFrame([{
        "za_stat": break_result["za_stat"], "p_value": break_result["p_value"],
        "candidate_break_date": break_result["break_date"],
        "significant_5pct": break_result["p_value"] < 0.05,
    }]).to_csv(dirs["tables"] / "structural_break_zivot_andrews.csv", index=False)

    # --- Backtest comparison (train vs full) ---
    pd.DataFrame([{
        "metric": "k_star_months", "train": train_report["k_star"], "full": full_report["k_star"],
    }, {
        "metric": "peak_correlation", "train": train_report["peak_corr"], "full": full_report["peak_corr"],
    }, {
        "metric": "granger_hub_to_local_min_p",
        "train": min(train_report["granger_hub_causes_local"].values()),
        "full": min(full_report["granger_hub_causes_local"].values()),
    }, {
        "metric": "cointegration_p_value",
        "train": train_report["cointegration"]["p_value"],
        "full": full_report["cointegration"]["p_value"],
    }]).to_csv(dirs["tables"] / "backtest_train_vs_full.csv", index=False)

    # --- Rolling cointegration (optional) ---
    if rolling_df is not None:
        rolling_df.to_csv(dirs["tables"] / "rolling_cointegration.csv")

    # --- Pair robustness (optional): same hub vs. other local states ---
    if robustness_summary is not None:
        robustness_summary.to_csv(dirs["tables"] / "pair_robustness.csv", index=False)


def _save_figures(dirs: dict, result: dict, hub: str, local: str,
                   holdout_start: str, rolling_df: pd.DataFrame = None,
                   robustness_summary: pd.DataFrame = None):
    # Point analysis.py's (and validation.py's) plotting functions at
    # this experiment's figures/ folder instead of the shared global
    # FIGURES_DIR — both modules import their own FIGURES_DIR reference
    # from config, so both need patching.
    original_analysis_figures_dir = analysis.FIGURES_DIR
    original_validation_figures_dir = validation.FIGURES_DIR
    analysis.FIGURES_DIR = dirs["figures"]
    validation.FIGURES_DIR = dirs["figures"]
    try:
        plot_tlcc(result["analysis_report"], hub, local, out_name="tlcc_lag_curve.png")
        plot_spread(result["panel"], hub, local, holdout_start=holdout_start, out_name="spread.png")
        if rolling_df is not None:
            plot_rolling_cointegration(rolling_df, hub, local, out_name="rolling_cointegration.png")
        if robustness_summary is not None:
            plot_pair_robustness(robustness_summary, hub.upper(), out_name="pair_robustness.png")
    finally:
        analysis.FIGURES_DIR = original_analysis_figures_dir
        validation.FIGURES_DIR = original_validation_figures_dir


def _save_data_snapshot(dirs: dict, panel: pd.DataFrame):
    panel.to_csv(dirs["data"] / "panel.csv")


def _write_manifest(dirs: dict, params: dict, run_id: str, runtime_s: float, panel: pd.DataFrame):
    manifest = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "runtime_seconds": round(runtime_s, 1),
        "params": params,
        "git_commit": _git_commit(),
        "package_versions": _package_versions(),
        "python_version": sys.version.split()[0],
        "panel_fingerprint_sha256_12": _panel_fingerprint(panel),
        "n_months": len(panel),
    }
    with open(dirs["root"] / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    return manifest


def _render_report_md(dirs: dict, run_id: str, params: dict, result: dict,
                       rolling_df: pd.DataFrame, manifest: dict, notes: str,
                       robustness_summary: pd.DataFrame = None) -> str:
    report = result["analysis_report"]
    train_report = result["train_report"]
    full_report = result["full_report"]
    brk = result["structural_break"]
    hub, local = params["hub"], params["local"]

    coint = report["cointegration"]
    coint_sig = coint["p_value"] < 0.05
    brk_sig = brk["p_value"] < 0.05

    lines = []
    lines.append(f"# Experiment: {run_id}")
    lines.append("")
    lines.append(f"**{params['commodity']} — {hub} (hub) vs {local} (local)**, "
                  f"{params['year_start']}–{params['year_end']}, "
                  f"holdout from {params['holdout_start']}")
    lines.append("")
    lines.append(f"Run at {manifest['timestamp']} · git `{manifest['git_commit']}` · "
                  f"{manifest['runtime_seconds']}s · {manifest['n_months']} months of data")
    if notes:
        lines.append(f"\n**Notes:** {notes}")
    lines.append("")
    lines.append("## Guide to this folder")
    lines.append("")
    lines.append("| Path | Contents |")
    lines.append("|---|---|")
    lines.append("| `manifest.json` | exact params, git commit, package versions, data fingerprint |")
    lines.append("| `data/panel.csv` | the cleaned monthly panel this run analyzed |")
    lines.append("| `figures/tlcc_lag_curve.png` | cross-correlation vs. lag, k* marked |")
    lines.append("| `figures/spread.png` | local−hub price spread over time, holdout marked |")
    if rolling_df is not None:
        lines.append("| `figures/rolling_cointegration.png` | rolling 60-mo cointegration p-value vs. time |")
    if robustness_summary is not None:
        lines.append("| `figures/pair_robustness.png` | k* (with CI) across every tested local state |")
        lines.append("| `tables/pair_robustness.csv` | full analysis re-run for each tested local state |")
    lines.append("| `tables/*.csv` | every number below, in machine-readable form |")
    lines.append("| `logs/run.log` | full console output of this run |")
    lines.append("")
    lines.append("## Headline results")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| k* (months, + = {hub} leads {local}) | {report['k_star']} |")
    lines.append(f"| k* 95% CI | [{report['k_star_ci'][0]:.1f}, {report['k_star_ci'][1]:.1f}] |")
    lines.append(f"| Peak correlation | {report['peak_corr']:.3f} |")
    lines.append(f"| Cointegration p-value (full period) | {coint['p_value']:.4f} "
                 f"({'cointegrated' if coint_sig else 'not cointegrated'} @ 5%) |")
    lines.append(f"| Structural break (ZA) p-value | {brk['p_value']:.4f} "
                 f"({'SIGNIFICANT' if brk_sig else 'not significant'} @ 5%) |")
    if brk_sig:
        lines.append(f"| Structural break candidate date | {brk['break_date'].date()} |")
    if rolling_df is not None:
        pct = 100 * rolling_df["cointegrated_5pct"].sum() / len(rolling_df)
        lines.append(f"| Rolling cointegration, % windows significant | {pct:.0f}% "
                     f"({rolling_df['cointegrated_5pct'].sum()}/{len(rolling_df)}) |")
    lines.append("")
    lines.append("## Granger causality (minimum p-value across tested lags)")
    lines.append("")
    lines.append("| Direction | min p-value | significant @ 5%? |")
    lines.append("|---|---|---|")
    h2l = min(report["granger_hub_causes_local"].values())
    l2h = min(report["granger_local_causes_hub"].values())
    lines.append(f"| {hub} → {local} | {h2l:.4f} | {'Yes' if h2l < 0.05 else 'No'} |")
    lines.append(f"| {local} → {hub} | {l2h:.4f} | {'Yes' if l2h < 0.05 else 'No'} |")
    lines.append("")
    lines.append("## Backtest stability (train-only vs. full period)")
    lines.append("")
    lines.append("| Metric | Train | Full | Stable? |")
    lines.append("|---|---|---|---|")
    k_stable = train_report["k_star"] == full_report["k_star"]
    train_min_p = min(train_report["granger_hub_causes_local"].values())
    full_min_p = min(full_report["granger_hub_causes_local"].values())
    granger_stable = (train_min_p < 0.05) == (full_min_p < 0.05)
    train_coint_p = train_report["cointegration"]["p_value"]
    full_coint_p = full_report["cointegration"]["p_value"]
    coint_stable = (train_coint_p < 0.05) == (full_coint_p < 0.05)
    lines.append(f"| k* | {train_report['k_star']} | {full_report['k_star']} | "
                 f"{'Yes' if k_stable else 'No'} |")
    lines.append(f"| {hub}→{local} Granger sig. | p={train_min_p:.4f} | p={full_min_p:.4f} | "
                 f"{'Yes' if granger_stable else 'No'} |")
    lines.append(f"| Cointegration sig. | p={train_coint_p:.4f} | p={full_coint_p:.4f} | "
                 f"{'Yes' if coint_stable else 'No'} |")
    lines.append("")

    if robustness_summary is not None:
        lines.append("## Pair robustness (same hub, other local states)")
        lines.append("")
        ok = robustness_summary[robustness_summary["status"] == "ok"]
        skipped = robustness_summary[robustness_summary["status"] != "ok"]
        if len(ok):
            lines.append("| Local state | n months | k* | k* 95% CI | Peak corr | "
                          f"{hub}→local Granger p | Cointegrated (5%)? |")
            lines.append("|---|---|---|---|---|---|---|")
            for _, r in ok.iterrows():
                lines.append(
                    f"| {r['local_state']} | {r['n_months']} | {r['k_star']} | "
                    f"[{r['k_star_ci_low']:.1f}, {r['k_star_ci_high']:.1f}] | "
                    f"{r['peak_corr']:.3f} | {r['granger_hub_to_local_min_p']:.4f} | "
                    f"{'Yes' if r['cointegrated_5pct'] else 'No'} |"
                )
            lines.append("")
            k_stars = ok["k_star"].unique()
            if len(k_stars) == 1:
                lines.append(f"k* is **consistent at {k_stars[0]} months** across all "
                              f"{len(ok)} tested pairs — not specific to {hub}/{local}.")
            else:
                lines.append(f"k* **varies across pairs** "
                              f"({dict(zip(ok['local_state'], ok['k_star']))}) — the lag "
                              f"finding from {hub}/{local} does not generalize as-is.")
        if len(skipped):
            lines.append("")
            lines.append(f"Skipped ({len(skipped)}): " + "; ".join(
                f"{r['local_state']} ({r['status']})" for _, r in skipped.iterrows()
            ))
        lines.append("")

    lines.append("## Figures")
    lines.append("")
    lines.append("![TLCC lag curve](figures/tlcc_lag_curve.png)")
    lines.append("")
    lines.append("![Spread over time](figures/spread.png)")
    if rolling_df is not None:
        lines.append("")
        lines.append("![Rolling cointegration](figures/rolling_cointegration.png)")
    if robustness_summary is not None and (robustness_summary["status"] == "ok").any():
        lines.append("")
        lines.append("![Pair robustness](figures/pair_robustness.png)")
    lines.append("")
    lines.append("---")
    robustness_flag = (
        f" --robustness-pairs {','.join(params['robustness_pairs'])}"
        if params.get("robustness_pairs") else ""
    )
    lines.append(f"Reproduce with: `python experiment.py --experiment-name {run_id} "
                 f"--commodity {params['commodity']} --hub {hub} --local {local} "
                 f"--year-start {params['year_start']} --year-end {params['year_end']} "
                 f"--holdout-start {params['holdout_start']} --max-lag {params['max_lag']}"
                 f"{' --skip-fetch' if params['skip_fetch'] else ''}"
                 f"{' --rolling-coint' if rolling_df is not None else ''}"
                 f"{robustness_flag}`")

    text = "\n".join(lines)
    with open(dirs["root"] / "REPORT.md", "w") as f:
        f.write(text)
    return text


def _append_registry(run_id: str, params: dict, result: dict, rolling_df: pd.DataFrame,
                      manifest: dict, notes: str, robustness_summary: pd.DataFrame = None):
    report = result["analysis_report"]
    train_report = result["train_report"]
    full_report = result["full_report"]
    brk = result["structural_break"]

    if robustness_summary is not None:
        ok = robustness_summary[robustness_summary["status"] == "ok"]
        pairs_tested = ";".join(ok["local_state"]) if len(ok) else ""
        k_star_consistent = bool(len(ok["k_star"].unique()) == 1) if len(ok) else ""
    else:
        pairs_tested = ""
        k_star_consistent = ""

    row = {
        "run_id": run_id,
        "timestamp": manifest["timestamp"],
        "commodity": params["commodity"],
        "hub": params["hub"],
        "local": params["local"],
        "year_start": params["year_start"],
        "year_end": params["year_end"],
        "holdout_start": params["holdout_start"],
        "max_lag": params["max_lag"],
        "n_months": manifest["n_months"],
        "k_star": report["k_star"],
        "k_star_ci_low": report["k_star_ci"][0],
        "k_star_ci_high": report["k_star_ci"][1],
        "peak_corr": round(report["peak_corr"], 4),
        "granger_hub_to_local_min_p": round(min(report["granger_hub_causes_local"].values()), 4),
        "granger_local_to_hub_min_p": round(min(report["granger_local_causes_hub"].values()), 4),
        "cointegration_p_full": round(full_report["cointegration"]["p_value"], 4),
        "cointegration_p_train": round(train_report["cointegration"]["p_value"], 4),
        "za_break_p": round(brk["p_value"], 4),
        "za_break_date": brk["break_date"].date().isoformat() if brk["p_value"] < 0.05 else "n/a (not significant)",
        "rolling_coint_pct_windows": (
            round(100 * rolling_df["cointegrated_5pct"].sum() / len(rolling_df), 1)
            if rolling_df is not None else ""
        ),
        "robustness_pairs_tested": pairs_tested,
        "robustness_k_star_consistent": k_star_consistent,
        "git_commit": manifest["git_commit"],
        "notes": notes,
    }

    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    is_new = not REGISTRY_PATH.exists()
    with open(REGISTRY_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REGISTRY_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def run_experiment(
    commodity: str = "CORN",
    hub: str = "IOWA",
    local: str = "OHIO",
    year_start: int = 2015,
    year_end: int = 2026,
    freq: str = "MONTHLY",
    statisticcat: str = "PRICE RECEIVED",
    agg_level: str = "STATE",
    holdout_start: str = "2024-01-01",
    max_lag: int = 12,
    skip_fetch: bool = False,
    rolling_coint: bool = False,
    rolling_window: int = 60,
    robustness_pairs: list = None,
    experiment_name: str = None,
    notes: str = "",
):
    """
    Runs the full fetch->clean->analysis->validation pipeline (via
    pipeline.run_pipeline, unchanged) and organizes everything it
    produces into experiments/<run_id>/: figures, tables, a manifest,
    a per-run REPORT.md, and one row appended to experiments/registry.csv.

    All arguments have the same defaults as pipeline.py, so calling this
    with no arguments reproduces the primary Iowa/Ohio run. Override any
    subset to run a variant (new pair, new date range, new holdout split).

    robustness_pairs: optional list of additional local states (e.g.
    ["NEBRASKA", "ILLINOIS"]) to test the same hub against, via
    validation.run_pair_robustness. Their panels must already be
    fetched+cleaned (this doesn't fetch); results land in this same
    experiment's tables/figures/REPORT.md, not a separate folder.
    """
    params = {
        "commodity": commodity, "hub": hub, "local": local,
        "year_start": year_start, "year_end": year_end, "freq": freq,
        "statisticcat": statisticcat, "agg_level": agg_level,
        "holdout_start": holdout_start, "max_lag": max_lag,
        "skip_fetch": skip_fetch, "rolling_coint": rolling_coint,
        "rolling_window": rolling_window,
        "robustness_pairs": list(robustness_pairs) if robustness_pairs else None,
    }

    run_id = experiment_name or _make_run_id(params)
    dirs = _setup_experiment_dir(run_id)

    log_path = dirs["logs"] / "run.log"
    start = time.time()
    with open(log_path, "w") as log_file:
        tee = _Tee(sys.stdout, log_file)
        original_stdout = sys.stdout
        sys.stdout = tee
        try:
            result = run_pipeline(
                commodity, hub, local, year_start, year_end,
                freq_desc=freq, statisticcat_desc=statisticcat,
                agg_level_desc=agg_level, holdout_start=holdout_start,
                max_lag=max_lag, skip_fetch=skip_fetch,
            )

            hub_l, local_l = hub.lower(), local.lower()
            rolling_df = None
            if rolling_coint:
                print(f"\n--- Extra: rolling {rolling_window}-month cointegration ---")
                rolling_df = rolling_cointegration(
                    result["panel"][hub_l], result["panel"][local_l], window=rolling_window,
                )
                if len(rolling_df) == 0:
                    print(
                        f"Warning: rolling window ({rolling_window} months) is >= the panel "
                        f"length ({len(result['panel'])} months) — no windows fit. Skipping "
                        "rolling cointegration for this run rather than dividing by zero later."
                    )
                    rolling_df = None

            robustness_summary = None
            if robustness_pairs:
                print(f"\n--- Extra: pair robustness ({hub} vs {robustness_pairs}) ---")
                robustness_summary, _ = run_pair_robustness(
                    commodity_desc=commodity, hub_state=hub,
                    local_states=robustness_pairs, freq_desc=freq, max_lag=max_lag,
                )
                print_pair_robustness(robustness_summary, hub)
        except Exception as exc:
            # Any failure past this point (pipeline stage, analysis-side
            # AnalysisError, bad state name, etc.) should not leave a
            # half-written experiment folder behind.
            print(f"\nEXPERIMENT FAILED: {exc}")
            sys.stdout = original_stdout
            try:
                shutil.rmtree(dirs["root"])
            except OSError as cleanup_exc:
                print(f"(also failed to clean up {dirs['root']}: {cleanup_exc})")
            raise
        finally:
            sys.stdout = original_stdout

    runtime_s = time.time() - start

    _save_data_snapshot(dirs, result["panel"])
    _save_tables(dirs, result, rolling_df=rolling_df, robustness_summary=robustness_summary)
    _save_figures(dirs, result, hub_l, local_l, holdout_start, rolling_df=rolling_df,
                  robustness_summary=robustness_summary)
    manifest = _write_manifest(dirs, params, run_id, runtime_s, result["panel"])
    _render_report_md(dirs, run_id, params, result, rolling_df, manifest, notes,
                       robustness_summary=robustness_summary)
    _append_registry(run_id, params, result, rolling_df, manifest, notes,
                      robustness_summary=robustness_summary)

    print(f"\n=== Experiment saved: experiments/{run_id}/ ===")
    print(f"    See experiments/{run_id}/REPORT.md for the full write-up.")
    print(f"    Registry updated: experiments/registry.csv")

    return {"run_id": run_id, "dir": dirs["root"], **result}


def _parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Run the full pipeline and save it as a tracked experiment "
            "(figures + tables + manifest + report, in its own folder). "
            "Same defaults as pipeline.py — run with no arguments to "
            "reproduce the primary Iowa/Ohio run."
        )
    )
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
    parser.add_argument("--skip-fetch", action="store_true",
                         help="Use already-cached raw data, don't re-hit the API")
    parser.add_argument("--rolling-coint", action="store_true",
                         help="Also run + plot rolling-window cointegration")
    parser.add_argument("--rolling-window", type=int, default=60)
    parser.add_argument(
        "--robustness-pairs", default=None,
        help="Comma-separated list of additional local states to test the same "
             "hub against, e.g. NEBRASKA,ILLINOIS. Results are saved into this "
             "same experiment's tables/figures/REPORT.md. Panels for these "
             "states must already be fetched+cleaned; this doesn't fetch.",
    )
    parser.add_argument("--experiment-name", default=None,
                         help="Override the auto-generated run_id (e.g. for a "
                              "human-readable label). Must be unique.")
    parser.add_argument("--notes", default="",
                         help="Free-text note stored in the manifest, report, and registry row")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    robustness_pairs = (
        [s.strip().upper() for s in args.robustness_pairs.split(",") if s.strip()]
        if args.robustness_pairs else None
    )
    try:
        run_experiment(
            commodity=args.commodity, hub=args.hub, local=args.local,
            year_start=args.year_start, year_end=args.year_end, freq=args.freq,
            statisticcat=args.statisticcat, agg_level=args.agg_level,
            holdout_start=args.holdout_start, max_lag=args.max_lag,
            skip_fetch=args.skip_fetch, rolling_coint=args.rolling_coint,
            rolling_window=args.rolling_window, robustness_pairs=robustness_pairs,
            experiment_name=args.experiment_name, notes=args.notes,
        )
    except (PipelineError, FileExistsError) as exc:
        print(f"\nEXPERIMENT FAILED: {exc}")
        raise SystemExit(1)
    except Exception as exc:
        print(f"\nEXPERIMENT FAILED (unexpected error): {exc}")
        raise SystemExit(1)
