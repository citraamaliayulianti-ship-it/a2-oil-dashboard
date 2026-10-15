"""Measures behind the views: the monitor table, chokepoint exposure, disruption baselines
and the global balance. Pure pandas, no Streamlit, so each function can be tested on its own."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.data import MARKET


# ---------------------------------------------------------------- events
# Dates and wording from EIA publications (see the sources on each page). They are context
# for reading the charts; the dashboard does not estimate the effect of any event.

@dataclass(frozen=True)
class Event:
    date: str
    short: str
    text: str
    source: str


EVENTS = [
    Event("2023-11-01", "Red Sea attacks", "November 2023: attacks on commercial ships in the Red Sea begin",
          "EIA, Today in Energy, 11 October 2024"),
    Event("2026-02-28", "Hormuz closed", "28 February 2026: military action begins; the Strait of Hormuz is "
          "effectively closed to shipping", "EIA, Short-Term Energy Outlook, April 2026"),
    Event("2026-07-07", "Attacks resume", "7 July 2026: strikes on vessels in the Strait of Hormuz resume",
          "EIA, Short-Term Energy Outlook, August 2026"),
]
HORMUZ_CLOSURE = pd.Timestamp("2026-02-28")
RED_SEA_START = pd.Timestamp("2023-11-01")


# ---------------------------------------------------------------- monitor

AS_OF = {  # label -> date (None = each indicator's latest observation)
    "Latest": None,
    "27 Feb 2026 (day before the Hormuz closure)": "2026-02-27",
    "31 Oct 2023 (before the Red Sea attacks)": "2023-10-31",
}
WINDOWS = {
    "1 week": pd.DateOffset(weeks=1),
    "1 month": pd.DateOffset(months=1),
    "3 months": pd.DateOffset(months=3),
    "1 year": pd.DateOffset(years=1),
}
Z_YEARS = 3                  # z-scores compare the latest value with the trailing three years
SMOOTH_DAYS = 7              # tanker transits are shown as 7-day means (daily counts are noisy)


def indicator_label(indicator_id: str) -> str:
    return MARKET[indicator_id][0]


def monitor_series(market: pd.DataFrame, indicator_id: str) -> pd.Series:
    """One indicator as a date-indexed series; transit counts become trailing 7-day means."""
    part = market.loc[market["indicator_id"] == indicator_id].sort_values("date")
    values = part.set_index("date")["value"].astype(float)
    if MARKET[indicator_id][1] == "Chokepoint transits":
        values = values.rolling(SMOOTH_DAYS, min_periods=SMOOTH_DAYS).mean().dropna()
    return values


def _value_at(series: pd.Series, when: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    """The last observation on or before a date."""
    before = series.loc[:when]
    if before.empty:
        return None
    return before.index[-1], float(before.iloc[-1])


def monitor_row(series: pd.Series, as_of: pd.Timestamp | None, window: pd.DateOffset) -> dict | None:
    """Latest value, change over the window, z-score against the trailing three years,
    position in the 52-week range and a one-year trend line."""
    latest = _value_at(series, as_of) if as_of is not None else (series.index[-1], float(series.iloc[-1]))
    if latest is None:
        return None
    when, value = latest
    earlier = _value_at(series, when - window)
    change = value - earlier[1] if earlier else np.nan
    change_pct = change / abs(earlier[1]) * 100 if earlier and earlier[1] not in (0, 0.0) else np.nan
    history = series.loc[when - pd.DateOffset(years=Z_YEARS) + pd.Timedelta(days=1):when]
    spread = history.std(ddof=1)
    zscore = (value - history.mean()) / spread if len(history) > 20 and spread > 0 else np.nan
    year = series.loc[when - pd.DateOffset(years=1) + pd.Timedelta(days=1):when]
    low, high = year.min(), year.max()
    position = (value - low) / (high - low) if high > low else np.nan
    weekly = year.resample("W-FRI").last().dropna()
    return {"date": when, "last": value, "change": change, "change_pct": change_pct, "zscore": zscore,
            "low_52w": low, "high_52w": high, "range_position": position,
            "trend": [round(float(v), 3) for v in weekly]}


def monitor_table(market: pd.DataFrame, as_of_label: str, window_label: str) -> pd.DataFrame:
    as_of = AS_OF[as_of_label]
    as_of = pd.Timestamp(as_of) if as_of else None
    rows = []
    for indicator_id in [i for i in MARKET if i in set(market["indicator_id"])]:
        label, group, unit, frequency, _, _ = MARKET[indicator_id]
        row = monitor_row(monitor_series(market, indicator_id), as_of, WINDOWS[window_label])
        if row is None:
            continue
        rows.append({"indicator_id": indicator_id, "indicator": label, "group": group, "unit": unit,
                     "frequency": frequency, **row})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- chokepoint exposure

PRE_ATTACK = ("2019-01-01", "2023-10-31")     # before the Red Sea attacks began


def yearly_exposure(monthly: pd.DataFrame, year: int) -> pd.DataFrame:
    """Mean daily tanker transits and tanker trade volume per chokepoint in one year
    (weighted by the days each month covers), its share of the 28-chokepoint total
    and its change from the January 2019 - October 2023 mean."""
    def mean_per_day(frame: pd.DataFrame) -> pd.DataFrame:
        weights = frame["days"]
        grouped = frame.assign(w_tr=frame["tanker_transits"] * weights, w_vol=frame["tanker_volume_t"] * weights,
                               w_all=frame["total_transits"] * weights)
        out = grouped.groupby(["portid", "chokepoint", "lat", "lon"], as_index=False)[["w_tr", "w_vol", "w_all", "days"]].sum()
        out["tanker_transits"] = out["w_tr"] / out["days"]
        out["tanker_volume_t"] = out["w_vol"] / out["days"]
        out["total_transits"] = out["w_all"] / out["days"]
        return out[["portid", "chokepoint", "lat", "lon", "days", "tanker_transits", "tanker_volume_t",
                    "total_transits"]]

    dates = pd.to_datetime(monthly["date"])
    current = mean_per_day(monthly.loc[monthly["year"] == year])
    base = mean_per_day(monthly.loc[dates.between(*PRE_ATTACK)])[["portid", "tanker_transits", "tanker_volume_t"]]
    base = base.rename(columns={"tanker_transits": "base_transits", "tanker_volume_t": "base_volume_t"})
    table = current.merge(base, on="portid", how="left")
    table["volume_share"] = table["tanker_volume_t"] / table["tanker_volume_t"].sum() * 100
    table["transit_share"] = table["tanker_transits"] / table["tanker_transits"].sum() * 100
    with np.errstate(divide="ignore", invalid="ignore"):
        table["volume_change"] = (table["tanker_volume_t"] / table["base_volume_t"] - 1) * 100
        table["transit_change"] = (table["tanker_transits"] / table["base_transits"] - 1) * 100
    return table.sort_values("tanker_volume_t", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------- disruptions

BASELINES = {  # label -> (first day, last day)
    "Jan–Oct 2023 (before the Red Sea attacks)": ("2023-01-01", "2023-10-31"),
    "12 months before the Hormuz closure": ("2025-02-28", "2026-02-27"),
}
MEASURES = {  # label -> column in chokepoint_day
    "Tanker transit calls": "n_tanker",
    "Tanker trade volume (metric tons)": "tanker_volume_t",
}


def baseline_means(day: pd.DataFrame, column: str, baseline_label: str) -> pd.Series:
    first, last = BASELINES[baseline_label]
    part = day.loc[day["date"].between(first, last)]
    return part.groupby("chokepoint")[column].mean()


def rolling_means(day: pd.DataFrame, column: str, days: int = SMOOTH_DAYS) -> pd.DataFrame:
    ordered = day.sort_values(["chokepoint", "date"]).copy()
    ordered["rolling"] = ordered.groupby("chokepoint")[column].transform(
        lambda s: s.rolling(days, min_periods=days).mean())
    return ordered


def recent_change(day: pd.DataFrame, column: str, baselines: pd.Series, days: int = 30) -> pd.DataFrame:
    """Mean of the last ``days`` days in the selection against each chokepoint's baseline."""
    rows = []
    for chokepoint, part in day.groupby("chokepoint"):
        last = part["date"].max()
        recent = part.loc[part["date"] > last - pd.Timedelta(days=days), column]
        base = baselines.get(chokepoint, np.nan)
        rows.append({"chokepoint": chokepoint, "end": last, "recent": recent.mean(), "baseline": base,
                     "change": (recent.mean() / base - 1) * 100 if base and base > 0 else np.nan})
    return pd.DataFrame(rows)


def monthly_against_baseline(day: pd.DataFrame, column: str, baselines: pd.Series) -> pd.DataFrame:
    """Monthly mean per chokepoint as a percentage of its baseline (100 = baseline)."""
    work = day.assign(month=day["date"].dt.to_period("M"))
    table = work.groupby(["chokepoint", "month"])[column].mean().reset_index()
    table["index"] = table[column] / table["chokepoint"].map(baselines) * 100
    return table


# ---------------------------------------------------------------- global balance

def balance_wide(steo: pd.DataFrame) -> pd.DataFrame:
    """One row per month, one column per STEO series."""
    return steo.pivot_table(index="date", columns="series_id", values="value").sort_index()


def cumulative_draw(steo: pd.DataFrame, start: str, end: str | None = None) -> float:
    """Million barrels drawn from world inventories between two months (positive = stocks fell)."""
    draws = steo.loc[steo["series_id"] == "t3_stchange_world"].set_index("date")["value"].sort_index()
    draws = draws.loc[start:end] if end else draws.loc[start:]
    return float((draws * draws.index.days_in_month).sum())
