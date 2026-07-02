"""
src/analysis.py

Core statistical analysis on the cleaned Iowa/Ohio corn panel:
- Stationarity (ADF) on price levels and returns
- Time-Lagged Cross-Correlation (TLCC) to find k*, the peak lag
- Bootstrap 95% CI on k*
- Granger causality (both directions)
- Engle-Granger cointegration test on price LEVELS

Positive k* means the hub state leads the local state by k* months.
Sign convention matches the original TLCC formulation: tlcc(hub, local)
with correlate(local, hub) internally, so a positive peak lag means
hub moves first.
"""

import argparse
import numpy as np
import pandas as pd
from scipy.signal import correlate
from statsmodels.tsa.stattools import adfuller, grangercausalitytests, coint

from config import PROCESSED_DATA_DIR, FIGURES_DIR


class AnalysisError(Exception):
    """Raised when the data can't support the requested analysis (e.g. too few obs)."""


def load_panel(
    path=None,
    commodity_desc: str = "CORN",
    hub_state: str = "IOWA",
    local_state: str = "OHIO",
    freq_desc: str = "MONTHLY",
) -> pd.DataFrame:
    if path is None:
        fname = (
            f"{commodity_desc.lower()}_{hub_state.lower()}_"
            f"{local_state.lower()}_{freq_desc.lower()}.csv"
        )
        path = PROCESSED_DATA_DIR / fname
    return pd.read_csv(path, parse_dates=["date"], index_col="date")


def adf_test(series: pd.Series, label: str) -> dict:
    """Augmented Dickey-Fuller stationarity test. Drops NaNs first."""
    clean = series.dropna()
    result = adfuller(clean)
    return {
        "label": label,
        "adf_stat": result[0],
        "p_value": result[1],
        "n_obs": result[3],
        "stationary_at_5pct": result[1] < 0.05,
    }


def tlcc(s1: pd.Series, s2: pd.Series, max_lag: int = 12):
    """
    Time-lagged cross-correlation. Positive lag k means s1 leads s2
    by k periods. Drops NaNs from the paired series before computing.
    """
    df = pd.concat([s1, s2], axis=1).dropna()
    a = (df.iloc[:, 0] - df.iloc[:, 0].mean()) / df.iloc[:, 0].std()
    b = (df.iloc[:, 1] - df.iloc[:, 1].mean()) / df.iloc[:, 1].std()

    n = len(a)
    if n <= max_lag:
        raise AnalysisError(
            f"Only {n} overlapping observations after dropping NaNs — "
            f"not enough for max_lag={max_lag}. Reduce max_lag or check "
            "for gaps in the panel."
        )

    corr = correlate(b, a, mode="full") / n
    lags = np.arange(-(n - 1), n)
    mask = (lags >= -max_lag) & (lags <= max_lag)
    return lags[mask], corr[mask]


def bootstrap_k_star_ci(
    s1: pd.Series, s2: pd.Series, max_lag: int = 12, n_boot: int = 1000, seed: int = 42
):
    """
    Bootstrap resample (with replacement) the paired series and
    recompute k* each time to get a 95% CI on the peak lag.
    """
    df = pd.concat([s1, s2], axis=1).dropna()
    n = len(df)
    rng = np.random.default_rng(seed)

    k_stars = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        sample = df.iloc[idx]
        try:
            lags, corr = tlcc(sample.iloc[:, 0], sample.iloc[:, 1], max_lag=max_lag)
            k_stars.append(lags[np.argmax(corr)])
        except AnalysisError:
            continue

    k_stars = np.array(k_stars)
    ci_low, ci_high = np.percentile(k_stars, [2.5, 97.5])
    return float(ci_low), float(ci_high), k_stars


def run_granger(df: pd.DataFrame, cause_col: str, effect_col: str, max_lag: int = 12):
    """
    Does `cause_col` Granger-cause `effect_col`? statsmodels expects
    column order [effect, cause].
    """
    data = df[[effect_col, cause_col]].dropna()
    results = grangercausalitytests(data, maxlag=max_lag, verbose=False)
    return {lag: res[0]["ssr_ftest"][1] for lag, res in results.items()}


def run_cointegration(price_a: pd.Series, price_b: pd.Series) -> dict:
    """Engle-Granger cointegration test on raw price LEVELS (not returns)."""
    df = pd.concat([price_a, price_b], axis=1).dropna()
    score, p_value, crit_values = coint(df.iloc[:, 0], df.iloc[:, 1])
    return {"score": float(score), "p_value": float(p_value), "crit_values": crit_values}


def run_full_analysis(df: pd.DataFrame, hub_state: str = "iowa", local_state: str = "ohio", max_lag: int = 12) -> dict:
    report = {}

    report["adf_hub_price"] = adf_test(df[hub_state], f"{hub_state}_price")
    report["adf_local_price"] = adf_test(df[local_state], f"{local_state}_price")
    report["adf_hub_returns"] = adf_test(df[f"{hub_state}_returns"], f"{hub_state}_returns")
    report["adf_local_returns"] = adf_test(df[f"{local_state}_returns"], f"{local_state}_returns")

    lags, corr = tlcc(df[f"{hub_state}_returns"], df[f"{local_state}_returns"], max_lag=max_lag)
    k_star = int(lags[np.argmax(corr)])
    report["tlcc_lags"] = lags
    report["tlcc_corr"] = corr
    report["k_star"] = k_star
    report["peak_corr"] = float(corr.max())

    ci_low, ci_high, _ = bootstrap_k_star_ci(
        df[f"{hub_state}_returns"], df[f"{local_state}_returns"], max_lag=max_lag
    )
    report["k_star_ci"] = (ci_low, ci_high)

    report["granger_hub_causes_local"] = run_granger(
        df, cause_col=f"{hub_state}_returns", effect_col=f"{local_state}_returns", max_lag=max_lag
    )
    report["granger_local_causes_hub"] = run_granger(
        df, cause_col=f"{local_state}_returns", effect_col=f"{hub_state}_returns", max_lag=max_lag
    )

    report["cointegration"] = run_cointegration(df[hub_state], df[local_state])

    return report


def print_report(report: dict, hub_state: str = "iowa", local_state: str = "ohio"):
    print("=== Stationarity (ADF test) ===")
    for key in ["adf_hub_price", "adf_local_price", "adf_hub_returns", "adf_local_returns"]:
        r = report[key]
        print(f"{r['label']:<18} ADF={r['adf_stat']:.3f}  p={r['p_value']:.4f}  stationary@5%={r['stationary_at_5pct']}")

    print("\n=== TLCC ===")
    print(f"k* = {report['k_star']} months (positive = {hub_state} leads {local_state})")
    print(f"peak correlation = {report['peak_corr']:.3f}")
    print(f"95% bootstrap CI on k*: [{report['k_star_ci'][0]:.1f}, {report['k_star_ci'][1]:.1f}]")

    print(f"\n=== Granger causality ({hub_state} -> {local_state}) ===")
    for lag, p in report["granger_hub_causes_local"].items():
        flag = " *" if p < 0.05 else ""
        print(f"  lag={lag}: p={p:.4f}{flag}")

    print(f"\n=== Granger causality ({local_state} -> {hub_state}) ===")
    for lag, p in report["granger_local_causes_hub"].items():
        flag = " *" if p < 0.05 else ""
        print(f"  lag={lag}: p={p:.4f}{flag}")

    print("\n=== Cointegration (Engle-Granger, on price levels) ===")
    c = report["cointegration"]
    print(f"score={c['score']:.3f}  p={c['p_value']:.4f}")
    print(f"critical values (1%, 5%, 10%): {c['crit_values']}")


def plot_tlcc(report: dict, hub_state: str, local_state: str, out_name: str = None):
    """Quick sanity-check plot — full styling pass happens on Day 5."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.stem(report["tlcc_lags"], report["tlcc_corr"])
    ax.axvline(report["k_star"], color="red", linestyle="--", label=f"k* = {report['k_star']}")
    ax.set_xlabel("Lag (months)")
    ax.set_ylabel("Cross-correlation")
    ax.set_title(f"TLCC: {hub_state} -> {local_state}")
    ax.legend()

    if out_name is None:
        out_name = f"fig_tlcc_{hub_state}_{local_state}.png"
    out_path = FIGURES_DIR / out_name
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"Saved TLCC plot -> {out_path}")


def plot_spread(df: pd.DataFrame, hub_state: str, local_state: str, holdout_start: str = None, out_name: str = None):
    """
    Plot the local-minus-hub price spread over the full observed range,
    with an optional marker for where the holdout period starts. This
    is the diagnostic for spotting *when* a structural break (like the
    cointegration flip) happened, not just that it happened.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(df.index, df["spread"])
    if holdout_start is not None:
        ax.axvline(pd.Timestamp(holdout_start), color="red", linestyle="--", label="holdout start")
        ax.legend()
    ax.set_xlabel("date")
    ax.set_ylabel("spread ($/bu)")
    ax.set_title(f"{local_state.capitalize()} - {hub_state.capitalize()} corn price spread")

    if out_name is None:
        out_name = f"fig_spread_{hub_state}_{local_state}.png"
    out_path = FIGURES_DIR / out_name
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"Saved spread plot -> {out_path}")


def _parse_args():
    parser = argparse.ArgumentParser(description="Run TLCC/Granger/cointegration analysis on cleaned panel")
    parser.add_argument("--commodity", default="CORN")
    parser.add_argument("--hub", default="IOWA")
    parser.add_argument("--local", default="OHIO")
    parser.add_argument("--freq", default="MONTHLY")
    parser.add_argument("--max-lag", type=int, default=12)
    parser.add_argument("--plot", action="store_true", help="Save a quick TLCC sanity-check plot")
    parser.add_argument("--spread-plot", action="store_true", help="Save the hub/local spread over time")
    parser.add_argument("--holdout-start", default=None, help="Marks a vertical line on the spread plot, e.g. 2024-01-01")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    df = load_panel(
        commodity_desc=args.commodity, hub_state=args.hub,
        local_state=args.local, freq_desc=args.freq,
    )
    hub, local = args.hub.lower(), args.local.lower()
    report = run_full_analysis(df, hub_state=hub, local_state=local, max_lag=args.max_lag)
    print_report(report, hub_state=hub, local_state=local)

    if args.plot:
        plot_tlcc(report, hub, local)

    if args.spread_plot:
        plot_spread(df, hub, local, holdout_start=args.holdout_start)
