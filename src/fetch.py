"""
src/fetch.py

Generic USDA NASS QuickStats API client.

One function fetches price data for a commodity/state over a year
range and returns a raw DataFrame. It's deliberately dumb — no
train/test logic here. The pipeline decides *which* year range to
ask for (all-history-minus-holdout vs. the holdout window itself);
this module just knows how to talk to the API.

Note: NASS QuickStats data is MONTHLY, WEEKLY, or ANNUAL, not daily.
There is no true daily granularity in this source — if you ever need
daily/weekly terminal-market prices beyond what's here, that's a
different USDA source (AMS Market News) and would get its own client
module (e.g. fetch_ams.py). Confirmed working commodity/geography
combo: CORN and SOYBEANS give 137 clean MONTHLY records across every
Corn Belt state tested (2015-2026), no gaps. Locked in: CORN.

CLI usage:
    python fetch.py --commodity CORN --states IOWA,OHIO \
        --year-start 2015 --year-end 2026 --freq MONTHLY

    python fetch.py --scan --commodity CORN --states IOWA,OHIO,ILLINOIS
"""

import time
import argparse
from datetime import datetime

import requests
import pandas as pd

from config import USDA_NASS_APIKEY, RAW_DATA_DIR

BASE_URL = "https://quickstats.nass.usda.gov/api/api_GET/"  # trailing slash required
GET_COUNTS_URL = "https://quickstats.nass.usda.gov/api/get_counts/"


class NASSFetchError(Exception):
    """Raised when the NASS API returns an error or an unusable response."""


def fetch_price_data(
    commodity_desc: str,
    state_name: str,
    year_start: int,
    year_end: int,
    freq_desc: str = "MONTHLY",
    statisticcat_desc: str = "PRICE RECEIVED",
    agg_level_desc: str = "STATE",
    save_raw: bool = True,
    max_retries: int = 3,
) -> pd.DataFrame:
    """
    Fetch price data from USDA NASS QuickStats for one commodity/state
    over an inclusive year range.

    Called the same way whether you're pulling historic training data
    or a recent holdout window for validation — just pass different
    year_start/year_end. This is also the function the pipeline calls
    per-state when building a multi-state panel (see fetch_multi_state).

    Parameters
    ----------
    commodity_desc : e.g. "CORN"
    state_name      : e.g. "IOWA"
    year_start, year_end : inclusive year range
    freq_desc       : "MONTHLY" (default), "ANNUAL", or "WEEKLY".
                      NASS has no true daily frequency.
    statisticcat_desc : "PRICE RECEIVED" is the standard price series
    agg_level_desc  : "STATE" collapses county/district breakdowns into
                      one row per state per period — without this,
                      broad queries can exceed NASS's 50,000-record
                      per-request limit ("exceeds limit = 50000")
    save_raw        : cache the raw response to data/raw/ as CSV
    max_retries     : retry attempts on transient failures (network/5xx)

    Returns
    -------
    pd.DataFrame of raw NASS records, unprocessed. Cleaning/alignment
    happens downstream in clean.py.

    Raises
    ------
    NASSFetchError on bad params, empty results, or repeated failures.
    """
    params = {
        "key": USDA_NASS_APIKEY,
        "format": "JSON",
        "commodity_desc": commodity_desc.upper(),
        "state_name": state_name.upper(),
        "year__GE": year_start,
        "year__LE": year_end,
        "freq_desc": freq_desc.upper(),
        "statisticcat_desc": statisticcat_desc.upper(),
        "agg_level_desc": agg_level_desc.upper(),
    }

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(BASE_URL, params=params, timeout=30)
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(2 * attempt)
            continue

        if response.status_code == 200:
            payload = response.json()
            records = payload.get("data", [])
            if not records:
                raise NASSFetchError(
                    f"No records returned for {commodity_desc}/{state_name} "
                    f"({year_start}-{year_end}, {freq_desc}). "
                    "Check spelling/params — NASS is picky about exact "
                    "commodity_desc and state_name values."
                )
            df = pd.DataFrame(records)

            if save_raw:
                _cache_raw(
                    df, commodity_desc, state_name, freq_desc,
                    statisticcat_desc, agg_level_desc, year_start, year_end
                )

            return df

        if response.status_code == 400:
            if "exceeds limit" in response.text.lower():
                raise NASSFetchError(
                    "Query exceeds NASS's 50,000-record limit. Narrow it "
                    "further — e.g. tighten the year range, or add "
                    "unit_desc/class_desc filters.\n"
                    f"Request URL: {response.url}"
                )
            # Bad request — retrying won't help, fail fast
            raise NASSFetchError(
                f"Bad request: {response.text}\nRequest URL: {response.url}"
            )

        last_error = f"HTTP {response.status_code}: {response.text}"
        time.sleep(2 * attempt)

    raise NASSFetchError(f"Failed after {max_retries} attempts: {last_error}")


def fetch_multi_state(
    commodity_desc: str,
    states: list,
    year_start: int,
    year_end: int,
    freq_desc: str = "MONTHLY",
    statisticcat_desc: str = "PRICE RECEIVED",
    agg_level_desc: str = "STATE",
    save_raw: bool = True,
) -> dict:
    """
    Fetch the same commodity for multiple states — this is what the
    pipeline calls to build a hub/local panel (e.g. Iowa + Ohio).

    Returns
    -------
    dict of {state_name: DataFrame}, one fetch_price_data call per state.
    Each state's raw pull is cached separately (see _cache_raw naming).
    """
    return {
        state: fetch_price_data(
            commodity_desc, state, year_start, year_end,
            freq_desc, statisticcat_desc, agg_level_desc, save_raw,
        )
        for state in states
    }


def check_frequency_availability(
    commodity_desc: str,
    state_name: str = None,
    statisticcat_desc: str = "PRICE RECEIVED",
    freqs_to_check: tuple = ("MONTHLY", "WEEKLY", "ANNUAL"),
    agg_level_desc: str = "STATE",
) -> dict:
    """
    Cheaply probe how many records exist for a commodity at each
    frequency, using the real get_counts endpoint (not a query param —
    NASS doesn't support count=true on api_GET, it's a separate URI).

    If state_name is given, checks STATE-level granularity for that
    state specifically — this is the real test for a spatial
    transmission study: MONTHLY + STATE must both be nonzero, or you
    can't measure lag *between* two places.

    Returns
    -------
    dict like {"MONTHLY": 0, "WEEKLY": 0, "ANNUAL": 32}
    """
    results = {}
    for freq in freqs_to_check:
        params = {
            "key": USDA_NASS_APIKEY,
            "commodity_desc": commodity_desc.upper(),
            "statisticcat_desc": statisticcat_desc.upper(),
            "freq_desc": freq.upper(),
        }
        if state_name:
            params["state_name"] = state_name.upper()
            params["agg_level_desc"] = agg_level_desc.upper()
        try:
            response = requests.get(GET_COUNTS_URL, params=params, timeout=15)
            if response.status_code == 200:
                results[freq] = response.json().get("count", 0)
            else:
                results[freq] = f"error: {response.text}"
        except requests.RequestException as exc:
            results[freq] = f"error: {exc}"
    return results


def scan_candidates(commodities: list, states: list, statisticcat_desc: str = "PRICE RECEIVED"):
    """
    Scan multiple commodity/state pairs for MONTHLY + STATE-level
    availability. Prints a summary table so you can pick a viable
    commodity/pair without hand-testing curl commands one at a time.
    """
    print(f"{'commodity':<12} {'state':<14} {'MONTHLY':>8} {'ANNUAL':>8}")
    for commodity in commodities:
        for state in states:
            counts = check_frequency_availability(
                commodity, state_name=state,
                statisticcat_desc=statisticcat_desc,
                freqs_to_check=("MONTHLY", "ANNUAL"),
            )
            print(f"{commodity:<12} {state:<14} {str(counts['MONTHLY']):>8} {str(counts['ANNUAL']):>8}")


def _cache_raw(df, commodity_desc, state_name, freq_desc, statisticcat_desc, agg_level_desc, year_start, year_end):
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    stat_slug = statisticcat_desc.lower().replace(" ", "-")
    fname = (
        f"{commodity_desc.lower()}_{state_name.lower()}_{stat_slug}_"
        f"{freq_desc.lower()}_{agg_level_desc.lower()}_{year_start}_{year_end}.csv"
    )
    path = RAW_DATA_DIR / fname
    df.to_csv(path, index=False)
    print(f"Cached raw data -> {path}")


def _parse_args():
    parser = argparse.ArgumentParser(description="Fetch USDA NASS QuickStats price data")
    parser.add_argument("--commodity", default="CORN")
    parser.add_argument("--states", default="IOWA,OHIO", help="Comma-separated state names")
    parser.add_argument("--year-start", type=int, default=2015)
    parser.add_argument("--year-end", type=int, default=datetime.now().year)
    parser.add_argument("--freq", default="MONTHLY", choices=["MONTHLY", "ANNUAL", "WEEKLY"])
    parser.add_argument("--statisticcat", default="PRICE RECEIVED")
    parser.add_argument("--agg-level", default="STATE")
    parser.add_argument("--scan", action="store_true", help="Run availability scan instead of fetching")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    states = [s.strip().upper() for s in args.states.split(",")]

    if args.scan:
        scan_candidates(commodities=[args.commodity], states=states)
    else:
        results = fetch_multi_state(
            args.commodity, states, args.year_start, args.year_end,
            freq_desc=args.freq, statisticcat_desc=args.statisticcat,
            agg_level_desc=args.agg_level,
        )
        print()
        for state, df in results.items():
            print(f"{state}: {len(df)} records")
