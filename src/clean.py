"""
src/clean.py

Raw NASS QuickStats CSVs (per-state, written by fetch.py) -> one
aligned monthly panel with returns, ready for analysis.py.
"""

import argparse
import numpy as np
import pandas as pd

from config import RAW_DATA_DIR, PROCESSED_DATA_DIR

MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


class CleaningError(Exception):
    """Raised when raw data can't be found or doesn't parse as expected."""


def load_raw(
    commodity_desc: str,
    state_name: str,
    freq_desc: str = "MONTHLY",
    statisticcat_desc: str = "PRICE RECEIVED",
    agg_level_desc: str = "STATE",
    year_start: int = None,
    year_end: int = None,
) -> pd.DataFrame:
    """
    Load one state's raw cached CSV, matching fetch.py's _cache_raw
    naming convention. If year_start/year_end aren't given, falls
    back to the most recent matching file for that commodity/state/
    freq/statcat/agg_level combination.
    """
    stat_slug = statisticcat_desc.lower().replace(" ", "-")
    prefix = (
        f"{commodity_desc.lower()}_{state_name.lower()}_{stat_slug}_"
        f"{freq_desc.lower()}_{agg_level_desc.lower()}_"
    )

    if year_start is not None and year_end is not None:
        path = RAW_DATA_DIR / f"{prefix}{year_start}_{year_end}.csv"
        if not path.exists():
            raise CleaningError(
                f"Expected raw file not found: {path}\n"
                "Run fetch.py with matching args first."
            )
        return pd.read_csv(path)

    matches = sorted(RAW_DATA_DIR.glob(f"{prefix}*.csv"))
    if not matches:
        raise CleaningError(
            f"No raw files found matching prefix: {prefix}*\n"
            f"Looked in {RAW_DATA_DIR}. Run fetch.py first."
        )
    return pd.read_csv(matches[-1])


def _parse_date(row) -> pd.Timestamp:
    """Build a date from year + reference_period_desc (e.g. 'JAN')."""
    month_str = str(row["reference_period_desc"]).strip().upper()
    month = MONTH_MAP.get(month_str)
    if month is None:
        return pd.NaT
    return pd.Timestamp(year=int(row["year"]), month=month, day=1)


def _clean_value(raw_value):
    """
    NASS 'Value' is a string that can contain commas, leading
    whitespace, or suppression codes like '(D)' (withheld to avoid
    disclosure) or '(NA)'. Convert to float, or NaN if suppressed.
    """
    if pd.isna(raw_value):
        return np.nan
    s = str(raw_value).strip()
    if s in ("(D)", "(NA)", "(Z)", ""):
        return np.nan
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return np.nan


def clean_state_series(df_raw: pd.DataFrame, state_label: str) -> pd.Series:
    """
    Convert one state's raw NASS dataframe into a clean, date-indexed,
    deduplicated price Series.
    """
    df = df_raw.copy()

    # A raw pull can contain multiple rows per date if NASS reports
    # more than one class/domain breakdown (e.g. by marketing class).
    # For a single price series we keep only the aggregate rows —
    # narrowing here prevents silent duplicate-date collisions later.
    if "class_desc" in df.columns:
        df = df[df["class_desc"].astype(str).str.upper() == "ALL CLASSES"]
    if "domain_desc" in df.columns:
        domains = df["domain_desc"].astype(str).str.upper()
        if "TOTAL" in domains.unique():
            df = df[domains == "TOTAL"]

    df["date"] = df.apply(_parse_date, axis=1)
    df["price"] = df["Value"].apply(_clean_value)
    df = df.dropna(subset=["date"]).sort_values("date")

    n_dupes = df["date"].duplicated().sum()
    if n_dupes:
        print(
            f"Warning: {state_label} has {n_dupes} duplicate date rows "
            "after class/domain filtering — keeping first occurrence. "
            "Worth checking manually if this number looks large."
        )
        df = df.drop_duplicates(subset="date", keep="first")

    series = df.set_index("date")["price"]
    series.name = state_label
    return series


def build_panel(
    hub_series: pd.Series,
    local_series: pd.Series,
    hub_label: str = "hub",
    local_label: str = "local",
) -> pd.DataFrame:
    """
    Align hub and local series onto a shared, complete monthly index,
    surface any gaps explicitly, and compute month-over-month %
    returns for each — the input TLCC/Granger in analysis.py will need.
    """
    hub_series = hub_series.rename(hub_label)
    local_series = local_series.rename(local_label)

    panel = pd.concat([hub_series, local_series], axis=1)

    # Force a complete monthly index across the observed range so any
    # missing month becomes an explicit NaN row, not a silent gap.
    full_index = pd.date_range(panel.index.min(), panel.index.max(), freq="MS")
    panel = panel.reindex(full_index)
    panel.index.name = "date"

    n_missing_hub = panel[hub_label].isna().sum()
    n_missing_local = panel[local_label].isna().sum()
    if n_missing_hub or n_missing_local:
        print(
            f"Gap check: {hub_label} missing {n_missing_hub}/{len(panel)} months, "
            f"{local_label} missing {n_missing_local}/{len(panel)} months."
        )

    panel[f"{hub_label}_returns"] = panel[hub_label].pct_change()
    panel[f"{local_label}_returns"] = panel[local_label].pct_change()
    panel["spread"] = panel[local_label] - panel[hub_label]

    return panel


def clean_and_save(
    commodity_desc: str,
    hub_state: str,
    local_state: str,
    freq_desc: str = "MONTHLY",
    statisticcat_desc: str = "PRICE RECEIVED",
    agg_level_desc: str = "STATE",
    year_start: int = None,
    year_end: int = None,
    output_name: str = None,
) -> pd.DataFrame:
    """
    Full pipeline step: load both states' raw CSVs, clean, align, save
    the merged panel to data/processed/. This is what pipeline.py will
    call later; also runnable standalone via CLI below.
    """
    hub_raw = load_raw(commodity_desc, hub_state, freq_desc, statisticcat_desc,
                        agg_level_desc, year_start, year_end)
    local_raw = load_raw(commodity_desc, local_state, freq_desc, statisticcat_desc,
                          agg_level_desc, year_start, year_end)

    hub_series = clean_state_series(hub_raw, hub_state.lower())
    local_series = clean_state_series(local_raw, local_state.lower())

    panel = build_panel(hub_series, local_series, hub_state.lower(), local_state.lower())

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if output_name is None:
        output_name = (
            f"{commodity_desc.lower()}_{hub_state.lower()}_"
            f"{local_state.lower()}_{freq_desc.lower()}.csv"
        )
    out_path = PROCESSED_DATA_DIR / output_name
    panel.to_csv(out_path)
    print(f"Saved cleaned panel -> {out_path} ({len(panel)} rows)")

    return panel


def _parse_args():
    parser = argparse.ArgumentParser(description="Clean and align NASS price data")
    parser.add_argument("--commodity", default="CORN")
    parser.add_argument("--hub", default="IOWA")
    parser.add_argument("--local", default="OHIO")
    parser.add_argument("--freq", default="MONTHLY")
    parser.add_argument("--statisticcat", default="PRICE RECEIVED")
    parser.add_argument("--agg-level", default="STATE")
    parser.add_argument("--year-start", type=int, default=None)
    parser.add_argument("--year-end", type=int, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    panel = clean_and_save(
        args.commodity, args.hub, args.local,
        freq_desc=args.freq, statisticcat_desc=args.statisticcat,
        agg_level_desc=args.agg_level,
        year_start=args.year_start, year_end=args.year_end,
    )
    print("\nHead:")
    print(panel.head())
    print("\nTail:")
    print(panel.tail())
