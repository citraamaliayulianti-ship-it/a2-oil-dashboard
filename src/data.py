"""Acquire, transform and validate the dashboard's five datasets.

One module holds the whole data pipeline so its lineage is inspectable:

* ``acquire()`` downloads the raw files into ``data/raw/``: four EIA workbooks
  (daily spot prices, weekly U.S. stocks, weekly Cushing stocks and the monthly
  Short-Term Energy Outlook tables) and the IMF PortWatch chokepoint tables
  (one JSON page per 1,000 daily rows, plus the list of chokepoints).
* ``transform()`` reads each file in its published format and builds five tidy tables:

  - ``chokepoint_day``: daily tanker and all-vessel transits through the ten
    chokepoints with the most tanker trade (data/processed.csv);
  - ``chokepoint_month``: monthly means for all 28 PortWatch chokepoints, with
    their coordinates (data/processed_chokepoint_month.csv);
  - ``market_day``: the monitor panel, one row per indicator per observation date:
    spot prices, two spreads derived from them, U.S. stocks and tanker transits
    at five chokepoints (data/processed_market_day.csv). Indicator names and
    frequencies are kept once, in ``MARKET`` below, rather than on every row;
  - ``steo_history`` and ``steo_forecast``: selected rows of the EIA Short-Term
    Energy Outlook, split at EIA's last historical month so that observations and
    forecasts are never mixed in one table (data/processed_steo_*.csv).

* ``validate()`` stops the pipeline if a table breaks a documented expectation.
* ``main()`` runs the steps. With ``DASHBOARD_SAMPLE_MODE=1`` it works offline:
  it rebuilds every processed file from the matching bundled sample.

Measures computed from these tables live in ``analysis.py``; presentation in ``views.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
EIA_DIR = RAW / "eia"
PORTWATCH_DIR = RAW / "portwatch"

FIRST_DATE = pd.Timestamp("2019-01-01")     # PortWatch daily data begin here
BARRELS_PER_GALLON = 42                      # 1 barrel = 42 U.S. gallons

# ---------------------------------------------------------------- sources

EIA_FILES = {
    "spot": ("PET_PRI_SPT_S1_D.xls", "https://www.eia.gov/dnav/pet/xls/PET_PRI_SPT_S1_D.xls"),
    "stocks": ("PET_STOC_WSTK_DCU_NUS_W.xls", "https://www.eia.gov/dnav/pet/xls/PET_STOC_WSTK_DCU_NUS_W.xls"),
    "cushing": ("W_EPC0_SAX_YCUOK_MBBLw.xls", "https://www.eia.gov/dnav/pet/hist_xls/W_EPC0_SAX_YCUOK_MBBLw.xls"),
    "steo": ("STEO_m.xlsx", "https://www.eia.gov/outlooks/steo/xls/STEO_m.xlsx"),
}
PORTWATCH = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
PORTWATCH_DAILY = f"{PORTWATCH}/Daily_Chokepoints_Data/FeatureServer/0/query"
PORTWATCH_LIST = f"{PORTWATCH}/PortWatch_chokepoints_database/FeatureServer/0/query"
PAGE_ROWS = 1000                              # the service returns at most 1,000 rows per request

# ---------------------------------------------------------------- dataset definitions

# The ten chokepoints with the largest estimated tanker trade volume, January 2019 to
# October 2023 (before the Red Sea attacks), in that order. ``--rank`` reprints the ranking.
TOP_TANKER = [
    "chokepoint5",   # Malacca Strait
    "chokepoint6",   # Strait of Hormuz
    "chokepoint14",  # Luzon Strait
    "chokepoint9",   # Dover Strait
    "chokepoint8",   # Gibraltar Strait
    "chokepoint4",   # Bab el-Mandeb Strait
    "chokepoint1",   # Suez Canal
    "chokepoint11",  # Taiwan Strait
    "chokepoint7",   # Cape of Good Hope
    "chokepoint12",  # Korea Strait
]
RANK_PERIOD = ("2019-01-01", "2023-10-31")

USD_BBL = "US dollars per barrel"
USD_GAL = "US dollars per gallon"
MBBL = "million barrels"
TRANSITS = "tanker transit calls per day"
MBD = "million barrels per day"

# Monitor indicators: id -> (label, group, unit, frequency, where the value comes from, plausible range)
MARKET = {
    "brent": ("Brent crude oil spot price", "Crude prices", USD_BBL, "Daily", ("spot", "RBRTE"), (5, 250)),
    "wti": ("WTI crude oil spot price (Cushing)", "Crude prices", USD_BBL, "Daily", ("spot", "RWTC"), (-50, 250)),
    "gasoline_usgc": ("Gasoline spot price, U.S. Gulf Coast", "Product prices", USD_GAL, "Daily",
                      ("spot", "EER_EPMRU_PF4_RGC_DPG"), (0.2, 10)),
    "diesel_usgc": ("Ultra-low sulfur diesel spot price, U.S. Gulf Coast", "Product prices", USD_GAL, "Daily",
                    ("spot", "EER_EPD2DXL0_PF4_RGC_DPG"), (0.2, 12)),
    "jet_usgc": ("Jet fuel spot price, U.S. Gulf Coast", "Product prices", USD_GAL, "Daily",
                 ("spot", "EER_EPJK_PF4_RGC_DPG"), (0.2, 12)),
    "brent_wti": ("Brent minus WTI spread", "Spreads", USD_BBL, "Daily", ("derived", "brent_wti"), (-20, 60)),
    "crack_321": ("3-2-1 crack spread, U.S. Gulf Coast products minus WTI", "Spreads", USD_BBL, "Daily",
                  ("derived", "crack_321"), (-40, 150)),
    "us_crude": ("U.S. commercial crude oil stocks (excluding SPR)", "U.S. inventories", MBBL, "Weekly",
                 ("stocks", "WCESTUS1"), (250, 650)),
    "us_spr": ("U.S. Strategic Petroleum Reserve crude oil stocks", "U.S. inventories", MBBL, "Weekly",
               ("stocks", "WCSSTUS1"), (150, 750)),
    "cushing": ("Cushing, Oklahoma crude oil stocks", "U.S. inventories", MBBL, "Weekly",
                ("cushing", "W_EPC0_SAX_YCUOK_MBBL"), (5, 100)),
    "us_gasoline": ("U.S. total gasoline stocks", "U.S. inventories", MBBL, "Weekly", ("stocks", "WGTSTUS1"),
                    (150, 300)),
    "us_distillate": ("U.S. distillate fuel oil stocks", "U.S. inventories", MBBL, "Weekly",
                      ("stocks", "WDISTUS1"), (60, 200)),
    "hormuz": ("Strait of Hormuz tanker transits", "Chokepoint transits", TRANSITS, "Daily",
               ("portwatch", "chokepoint6"), (0, 250)),
    "bab_el_mandeb": ("Bab el-Mandeb Strait tanker transits", "Chokepoint transits", TRANSITS, "Daily",
                      ("portwatch", "chokepoint4"), (0, 250)),
    "suez": ("Suez Canal tanker transits", "Chokepoint transits", TRANSITS, "Daily",
             ("portwatch", "chokepoint1"), (0, 250)),
    "cape": ("Cape of Good Hope tanker transits", "Chokepoint transits", TRANSITS, "Daily",
             ("portwatch", "chokepoint7"), (0, 250)),
    "malacca": ("Malacca Strait tanker transits", "Chokepoint transits", TRANSITS, "Daily",
                ("portwatch", "chokepoint5"), (0, 250)),
}
GROUPS = ["Crude prices", "Product prices", "Spreads", "U.S. inventories", "Chokepoint transits"]

# Short-Term Energy Outlook rows: code -> (sheet, label, group, unit, plausible range)
STEO = {
    "papr_world": ("3atab", "World production of petroleum and other liquids", "World balance", MBD, (80, 115)),
    "patc_world": ("3atab", "World consumption of petroleum and other liquids", "World balance", MBD, (80, 115)),
    "t3_stchange_world": ("3atab", "World inventory net withdrawals (positive = stocks fall)", "World balance", MBD,
                          (-15, 15)),
    "pasc_oecd_t3": ("3atab", "OECD commercial inventories, end of month", "World balance", MBBL, (2000, 3500)),
    "BREPUUS": ("2tab", "Brent spot price, monthly average", "Prices", USD_BBL, (10, 250)),
    "WTIPUUS": ("2tab", "WTI spot price, monthly average", "Prices", USD_BBL, (10, 250)),
    "papr_sa": ("3ctab", "Saudi Arabia", "Gulf producers", MBD, (0, 15)),
    "papr_iz": ("3ctab", "Iraq", "Gulf producers", MBD, (0, 8)),
    "papr_tc": ("3btab", "United Arab Emirates", "Gulf producers", MBD, (0, 8)),
    "papr_ku": ("3ctab", "Kuwait", "Gulf producers", MBD, (0, 5)),
    "papr_IR": ("3ctab", "Iran", "Gulf producers", MBD, (0, 7)),
    "papr_QA": ("3btab", "Qatar", "Gulf producers", MBD, (0, 4)),
    "papr_ba": ("3ctab", "Bahrain", "Gulf producers", MBD, (0, 1)),
}
STEO_GROUPS = ["World balance", "Prices", "Gulf producers"]

# File locations of each dataset: id -> (sample, processed output)
OUTPUTS = {
    "chokepoint_day": ("sample.csv", "processed.csv"),
    "chokepoint_month": ("sample_chokepoint_month.csv", "processed_chokepoint_month.csv"),
    "market_day": ("sample_market_day.csv", "processed_market_day.csv"),
    "steo_history": ("sample_steo_history.csv", "processed_steo_history.csv"),
    "steo_forecast": ("sample_steo_forecast.csv", "processed_steo_forecast.csv"),
}

COLUMNS = {
    "chokepoint_day": ["date", "year", "portid", "chokepoint", "n_tanker", "tanker_volume_t", "n_total",
                       "total_volume_t"],
    "chokepoint_month": ["date", "year", "month", "portid", "chokepoint", "lat", "lon", "days",
                         "tanker_transits", "tanker_volume_t", "total_transits", "total_volume_t"],
    "market_day": ["date", "indicator_id", "group", "unit", "value"],
    "steo_history": ["date", "year", "month", "series_id", "series", "group", "unit", "value", "status", "edition"],
    "steo_forecast": ["date", "year", "month", "series_id", "series", "group", "unit", "value", "status",
                      "edition"],
}
KEYS = {
    "chokepoint_day": ["date", "portid"],
    "chokepoint_month": ["date", "portid"],
    "market_day": ["date", "indicator_id"],
    "steo_history": ["date", "series_id"],
    "steo_forecast": ["date", "series_id"],
}
STRINGS = {
    "chokepoint_day": ["portid", "chokepoint"],
    "chokepoint_month": ["portid", "chokepoint"],
    "market_day": ["indicator_id", "group", "unit"],
    "steo_history": ["series_id", "series", "group", "unit", "status", "edition"],
    "steo_forecast": ["series_id", "series", "group", "unit", "status", "edition"],
}
INTEGERS = {
    "chokepoint_day": ["year", "n_tanker", "tanker_volume_t", "n_total", "total_volume_t"],
    "chokepoint_month": ["year", "month", "days"],
    "market_day": [],
    "steo_history": ["year", "month"],
    "steo_forecast": ["year", "month"],
}

# Sample rules (documented in README): the offline sample is a faithful subset of each table.
SAMPLE_FROM = {"chokepoint_day": "2023-01-01", "market_day": "2020-01-01"}


def read_dataset(path: Path, dataset: str) -> pd.DataFrame:
    """Read a dataset CSV keeping identifiers as text; only empty fields are missing."""
    return pd.read_csv(path, dtype={c: str for c in STRINGS[dataset]}, keep_default_na=False, na_values=[""])


# ---------------------------------------------------------------- acquisition

def _fetch(url: str, minimum: int = 200) -> bytes:
    try:
        with urlopen(url, timeout=60) as response:
            payload = response.read()
    except (URLError, TimeoutError) as error:
        sys.exit(
            f"Could not fetch {url}: {error}. Check your connection or download the file in a browser "
            f"(see README.md). To work offline, rerun with DASHBOARD_SAMPLE_MODE=1 to use the bundled samples."
        )
    if len(payload) < minimum:
        sys.exit(f"Unexpectedly short response from {url}: {payload[:200]!r}")
    return payload


def _portwatch_page(url: str, offset: int) -> dict:
    query = {"where": "1=1", "outFields": "*", "orderByFields": "ObjectId", "returnGeometry": "false",
             "resultOffset": offset, "resultRecordCount": PAGE_ROWS, "f": "json"}
    page = json.loads(_fetch(f"{url}?{urlencode(query)}"))
    if "error" in page:
        sys.exit(f"PortWatch returned an error at offset {offset}: {page['error']}")
    return page


def acquire() -> None:
    """Download every raw file to data/raw/ (live mode only)."""
    EIA_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in EIA_FILES.values():
        payload = _fetch(url, minimum=10_000)   # a failed EIA download is a short HTML page
        (EIA_DIR / name).write_bytes(payload)
        print(f"Wrote {EIA_DIR / name} ({len(payload):,} bytes)")
    daily = PORTWATCH_DIR / "daily"
    daily.mkdir(parents=True, exist_ok=True)
    for old in daily.glob("daily_*.json"):
        old.unlink()
    offset = 0
    while True:
        page = _portwatch_page(PORTWATCH_DAILY, offset)
        (daily / f"daily_{offset}.json").write_text(json.dumps(page))
        if not page.get("exceededTransferLimit"):
            break
        offset += PAGE_ROWS
    print(f"Wrote {offset // PAGE_ROWS + 1} PortWatch daily pages to {daily}")
    (PORTWATCH_DIR / "chokepoints.json").write_text(json.dumps(_portwatch_page(PORTWATCH_LIST, 0)))


# ---------------------------------------------------------------- readers

def _eia_sheets(path: Path) -> pd.DataFrame:
    """All 'Data n' sheets of an EIA history workbook, joined on date, one column per source key."""
    workbook = pd.ExcelFile(path)
    frames = []
    for sheet in workbook.sheet_names:
        if not sheet.startswith("Data"):
            continue
        raw = pd.read_excel(workbook, sheet, header=None)
        keys = raw.iloc[1, 1:].tolist()              # row 2 holds EIA's source keys
        body = raw.iloc[3:].copy()
        body.columns = ["date", *keys]
        body["date"] = pd.to_datetime(body["date"], errors="raise")
        frames.append(body.set_index("date").apply(pd.to_numeric, errors="raise"))
    return pd.concat(frames, axis=1, sort=True)


def read_portwatch(directory: Path) -> pd.DataFrame:
    """Every daily row of every chokepoint from the saved JSON pages."""
    rows = []
    for path in sorted((directory / "daily").glob("daily_*.json")):
        page = json.loads(path.read_text())
        if "error" in page:
            raise ValueError(f"{path.name} holds an error response, not data")
        rows += [feature["attributes"] for feature in page["features"]]
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    if frame.duplicated(["date", "portid"]).any():
        raise ValueError("PortWatch pages overlap: duplicate chokepoint-days")
    return frame


def read_chokepoint_list(directory: Path) -> pd.DataFrame:
    page = json.loads((directory / "chokepoints.json").read_text())
    table = pd.DataFrame([feature["attributes"] for feature in page["features"]])
    return table[["portid", "portname", "lat", "lon"]]


def _steo_frame(path: Path) -> tuple[pd.DataFrame, pd.Timestamp, str]:
    """Selected STEO rows in long form, the last historical month and the edition name."""
    workbook = pd.ExcelFile(path)
    dates = pd.read_excel(workbook, "Dates", header=None)
    labels = dates.iloc[:, 0].astype(str)
    edition = str(dates.iloc[0, 3]).strip()                           # e.g. "October 2026"
    last_text = str(int(dates.loc[labels.str.startswith("Last Historical Month"), 3].iloc[0]))
    last_historical = pd.Timestamp(f"{last_text[:4]}-{last_text[4:]}-01") + pd.offsets.MonthEnd(0)
    parts = []
    for sheet in sorted({spec[0] for spec in STEO.values()}):
        table = pd.read_excel(workbook, sheet, header=None)
        years = table.iloc[2, 2:].ffill()
        months = table.iloc[3, 2:]
        when = pd.to_datetime(years.astype(int).astype(str) + "-" + months.astype(str), format="%Y-%b")
        when = when + pd.offsets.MonthEnd(0)
        for code, (where, label, group, unit, _) in STEO.items():
            if where != sheet:
                continue
            row = table.loc[table.iloc[:, 0] == code]
            if row.empty:
                raise ValueError(f"STEO row {code} not found in {sheet}")
            values = pd.to_numeric(row.iloc[0, 2:], errors="coerce")
            parts.append(pd.DataFrame({"date": when.to_numpy(), "series_id": code, "series": label,
                                       "group": group, "unit": unit, "value": values.to_numpy()}))
    return pd.concat(parts, ignore_index=True), last_historical, edition


# ---------------------------------------------------------------- transformation

def build_chokepoint_day(daily: pd.DataFrame) -> pd.DataFrame:
    part = daily.loc[daily["portid"].isin(TOP_TANKER) & (daily["date"] >= FIRST_DATE)]
    return pd.DataFrame({
        "date": part["date"],
        "year": part["date"].dt.year,
        "portid": part["portid"],
        "chokepoint": part["portname"],
        "n_tanker": part["n_tanker"],
        "tanker_volume_t": part["capacity_tanker"],
        "n_total": part["n_total"],
        "total_volume_t": part["capacity"],
    })


def build_chokepoint_month(daily: pd.DataFrame, places: pd.DataFrame) -> pd.DataFrame:
    """Mean daily transits and volumes per chokepoint and calendar month. Each row is dated by the last day
    with data in its month: the month end, or the latest day for the current, partial month."""
    work = daily.loc[daily["date"] >= FIRST_DATE].copy()
    work["period"] = work["date"].dt.to_period("M")
    monthly = (work.groupby(["period", "portid", "portname"])
               .agg(date=("date", "max"), days=("n_tanker", "size"), tanker_transits=("n_tanker", "mean"),
                    tanker_volume_t=("capacity_tanker", "mean"), total_transits=("n_total", "mean"),
                    total_volume_t=("capacity", "mean"))
               .reset_index().drop(columns="period").rename(columns={"portname": "chokepoint"}))
    monthly = monthly.merge(places[["portid", "lat", "lon"]], on="portid", how="left", validate="many_to_one")
    monthly["year"] = monthly["date"].dt.year
    monthly["month"] = monthly["date"].dt.month
    for column in ["tanker_transits", "total_transits"]:
        monthly[column] = monthly[column].round(3)
    for column in ["tanker_volume_t", "total_volume_t"]:
        monthly[column] = monthly[column].round(1)
    for column in ["lat", "lon"]:
        monthly[column] = monthly[column].round(4)
    return monthly


def build_market_day(spot: pd.DataFrame, stocks: pd.DataFrame, cushing: pd.DataFrame,
                     daily: pd.DataFrame) -> pd.DataFrame:
    """Long table of the monitor indicators; stocks converted from thousand to million barrels."""
    series = {}
    for indicator, (_, _, _, _, (origin, key), _) in MARKET.items():
        if origin == "spot":
            series[indicator] = spot[key]
        elif origin == "stocks":
            series[indicator] = stocks[key] / 1000
        elif origin == "cushing":
            series[indicator] = cushing[key] / 1000
        elif origin == "portwatch":
            part = daily.loc[daily["portid"] == key].set_index("date")["n_tanker"]
            series[indicator] = part.astype(float)
    # Spreads only on days when every price in them is published.
    series["brent_wti"] = spot["RBRTE"] - spot["RWTC"]
    gasoline = spot["EER_EPMRU_PF4_RGC_DPG"] * BARRELS_PER_GALLON
    diesel = spot["EER_EPD2DXL0_PF4_RGC_DPG"] * BARRELS_PER_GALLON
    series["crack_321"] = (2 * gasoline + diesel - 3 * spot["RWTC"]) / 3
    parts = []
    for indicator, (_, group, unit, _, _, _) in MARKET.items():
        values = series[indicator].dropna()
        values = values.loc[values.index >= FIRST_DATE]
        parts.append(pd.DataFrame({"date": values.index, "indicator_id": indicator, "group": group,
                                   "unit": unit, "value": values.to_numpy().round(4)}))
    return pd.concat(parts, ignore_index=True)


def build_steo(long: pd.DataFrame, last_historical: pd.Timestamp, edition: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    long = long.assign(year=long["date"].dt.year, month=long["date"].dt.month, edition=edition,
                       value=long["value"].round(4))
    history = long.loc[long["date"] <= last_historical].assign(status="Historical")
    forecast = long.loc[long["date"] > last_historical].assign(status="Forecast")
    if history["value"].isna().any():
        missing = history.loc[history["value"].isna(), ["series_id", "date"]].head().to_dict("records")
        raise ValueError(f"STEO historical values missing or not numeric, for example {missing}")
    # EIA publishes no country-level forecast for some producers ("-" in the workbook); those
    # series simply have no forecast rows. Any other gap stops the pipeline.
    blank = forecast.groupby("series_id")["value"].apply(lambda v: v.isna().all())
    partial = forecast.groupby("series_id")["value"].apply(lambda v: v.isna().any() and not v.isna().all())
    if partial.any():
        raise ValueError(f"STEO forecasts partly missing for {sorted(partial[partial].index)}")
    if blank.any():
        print(f"STEO has no forecast for {sorted(blank[blank].index)}")
    return history, forecast.dropna(subset=["value"])


def transform(raw: Path = RAW) -> dict[str, pd.DataFrame]:
    """Read every raw file and build the five tables used by the app."""
    daily = read_portwatch(raw / "portwatch")
    places = read_chokepoint_list(raw / "portwatch")
    spot = _eia_sheets(raw / "eia" / EIA_FILES["spot"][0])
    stocks = _eia_sheets(raw / "eia" / EIA_FILES["stocks"][0])
    cushing = _eia_sheets(raw / "eia" / EIA_FILES["cushing"][0])
    steo, last_historical, edition = _steo_frame(raw / "eia" / EIA_FILES["steo"][0])
    history, forecast = build_steo(steo, last_historical, edition)
    tables = {
        "chokepoint_day": build_chokepoint_day(daily),
        "chokepoint_month": build_chokepoint_month(daily, places),
        "market_day": build_market_day(spot, stocks, cushing, daily),
        "steo_history": history,
        "steo_forecast": forecast,
    }
    print(f"PortWatch: {len(daily):,} chokepoint-days, {daily['date'].min():%Y-%m-%d} to {daily['date'].max():%Y-%m-%d}")
    print(f"EIA STEO {edition}: last historical month {last_historical:%Y-%m}")
    return tables


def finalise(frame: pd.DataFrame, dataset: str) -> pd.DataFrame:
    """Column order, types, ISO dates and a stable row order."""
    frame = frame.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.strftime("%Y-%m-%d")
    for column in INTEGERS[dataset]:
        frame[column] = frame[column].astype("int64")
    for column in STRINGS[dataset]:
        frame[column] = frame[column].astype(str)
    order = {
        "chokepoint_day": lambda f: f.assign(_k=f["portid"].map({p: i for i, p in enumerate(TOP_TANKER)})),
        "chokepoint_month": lambda f: f.assign(_k=f["portid"].str.replace("chokepoint", "").astype(int)),
        "market_day": lambda f: f.assign(_k=f["indicator_id"].map({k: i for i, k in enumerate(MARKET)})),
        "steo_history": lambda f: f.assign(_k=f["series_id"].map({k: i for i, k in enumerate(STEO)})),
        "steo_forecast": lambda f: f.assign(_k=f["series_id"].map({k: i for i, k in enumerate(STEO)})),
    }[dataset]
    frame = order(frame).sort_values(["_k", "date"]).drop(columns="_k")
    return frame[COLUMNS[dataset]].reset_index(drop=True)


# ---------------------------------------------------------------- validation

def _check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _common(frame: pd.DataFrame, dataset: str) -> pd.Series:
    """Checks shared by every table; returns the parsed dates."""
    missing = set(COLUMNS[dataset]).difference(frame.columns)
    _check(not missing, f"{dataset}: missing columns {sorted(missing)}")
    _check(not frame.duplicated(KEYS[dataset]).any(), f"{dataset}: duplicate {KEYS[dataset]} keys")
    _check(not frame[COLUMNS[dataset]].isna().any().any(), f"{dataset}: unexpected missing values")
    dates = pd.to_datetime(frame["date"], errors="raise")
    _check(dataset.startswith("steo") or dates.min() >= FIRST_DATE, f"{dataset}: dates before {FIRST_DATE:%Y-%m-%d}")
    if "year" in frame:
        _check((dates.dt.year == frame["year"]).all(), f"{dataset}: year does not match date")
    if "month" in frame:
        _check((dates.dt.month == frame["month"]).all(), f"{dataset}: month does not match date")
    for column in frame.columns:
        if column in INTEGERS[dataset] or column == "value" or column.endswith(("_t", "_transits")):
            values = pd.to_numeric(frame[column], errors="raise")
            _check(np.isfinite(values).all(), f"{dataset}: {column} has non-finite values")
    return dates


def validate(frame: pd.DataFrame, dataset: str) -> None:
    """Stop the pipeline if a table breaks a documented expectation."""
    dates = _common(frame, dataset)
    today = pd.Timestamp.today().normalize()
    if dataset == "chokepoint_day":
        _check(set(frame["portid"]) <= set(TOP_TANKER), "chokepoint_day: unexpected chokepoint")
        _check(frame.groupby("portid")["chokepoint"].nunique().max() == 1, "chokepoint_day: name changes")
        for column in ["n_tanker", "tanker_volume_t", "n_total", "total_volume_t"]:
            _check((frame[column] >= 0).all(), f"chokepoint_day: negative {column}")
        _check((frame["n_tanker"] <= frame["n_total"]).all(), "chokepoint_day: more tankers than vessels")
        _check((frame["tanker_volume_t"] <= frame["total_volume_t"]).all(),
               "chokepoint_day: tanker volume above total volume")
        _check(frame["n_total"].max() <= 1000, "chokepoint_day: implausible vessel count")
        _check(dates.max() <= today, "chokepoint_day: dates in the future")
        for portid, days in dates.groupby(frame["portid"]):
            gaps = days.sort_values().diff().dropna()
            _check((gaps == pd.Timedelta(days=1)).all(), f"chokepoint_day: gaps in the days of {portid}")
    elif dataset == "chokepoint_month":
        _check(frame["portid"].nunique() <= 28 and frame["portid"].str.match(r"^chokepoint\d+$").all(),
               "chokepoint_month: unexpected chokepoint identifiers")
        _check(frame["days"].between(1, 31).all(), "chokepoint_month: days outside 1-31")
        _check((dates.dt.day == frame["days"]).all(),
               "chokepoint_month: each month must run without gaps from its first day to its date")
        complete = dates < dates.max().to_period("M").start_time
        _check(dates[complete].dt.is_month_end.all(), "chokepoint_month: a complete month must end on its last day")
        _check(frame["lat"].between(-90, 90).all() and frame["lon"].between(-180, 180).all(),
               "chokepoint_month: coordinates out of range")
        for column in ["tanker_transits", "tanker_volume_t", "total_transits", "total_volume_t"]:
            _check((frame[column] >= 0).all(), f"chokepoint_month: negative {column}")
        _check((frame["tanker_transits"] <= frame["total_transits"] + 1e-9).all(),
               "chokepoint_month: more tankers than vessels")
    elif dataset == "market_day":
        _check(set(frame["indicator_id"]) <= set(MARKET), "market_day: unexpected indicator")
        _check(set(frame["group"]) <= set(GROUPS), "market_day: unexpected group")
        for indicator, part in frame.groupby("indicator_id"):
            _, group, unit, frequency, _, (low, high) = MARKET[indicator]
            _check(part["group"].eq(group).all() and part["unit"].eq(unit).all(),
                   f"market_day: group or unit of {indicator} does not match its definition")
            _check(part["value"].between(low, high).all(), f"market_day: {indicator} outside {low} to {high} {unit}")
            if frequency == "Weekly":
                _check((pd.to_datetime(part["date"]).dt.dayofweek == 4).all(),
                       f"market_day: {indicator} is weekly and must be dated on Fridays")
        _check(dates.max() <= today, "market_day: dates in the future")
    else:  # STEO history or forecast
        status = "Historical" if dataset == "steo_history" else "Forecast"
        _check(frame["status"].eq(status).all(), f"{dataset}: every row must be {status}")
        _check(frame["edition"].nunique() == 1, f"{dataset}: more than one STEO edition")
        _check(set(frame["series_id"]) <= set(STEO), f"{dataset}: unexpected series")
        _check(dates.dt.is_month_end.all(), f"{dataset}: dates must be month ends")
        for code, part in frame.groupby("series_id"):
            _, label, group, unit, (low, high) = STEO[code]
            _check(part["series"].eq(label).all() and part["group"].eq(group).all() and part["unit"].eq(unit).all(),
                   f"{dataset}: labels of {code} do not match its definition")
            _check(part["value"].between(low, high).all(), f"{dataset}: {code} outside {low} to {high}")
            steps = (part["year"] * 12 + part["month"]).sort_values().diff().dropna()
            _check((steps == 1).all(), f"{dataset}: gaps in the months of {code}")


def validate_pair(history: pd.DataFrame, forecast: pd.DataFrame) -> None:
    """History ends where the forecast starts, and both come from one edition."""
    _check(set(history["edition"]) == set(forecast["edition"]), "STEO history and forecast editions differ")
    last, first = pd.to_datetime(history["date"]).max(), pd.to_datetime(forecast["date"]).min()
    _check(first == last + pd.offsets.MonthEnd(1), "STEO forecast does not start the month after the history")


# ---------------------------------------------------------------- run

def sample_of(frame: pd.DataFrame, dataset: str) -> pd.DataFrame:
    start = SAMPLE_FROM.get(dataset)
    if start is None:
        return frame
    return frame.loc[pd.to_datetime(frame["date"]) >= pd.Timestamp(start)].reset_index(drop=True)


def rank_chokepoints(daily: pd.DataFrame) -> pd.Series:
    period = daily.loc[daily["date"].between(*RANK_PERIOD)]
    return period.groupby("portid")["capacity_tanker"].mean().sort_values(ascending=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--acquire", action="store_true", help="Refresh data/raw/ from EIA and PortWatch and stop")
    parser.add_argument("--validate", action="store_true", help="Validate the processed files and stop")
    parser.add_argument("--rank", action="store_true", help="Print the tanker-volume ranking behind TOP_TANKER")
    parser.add_argument("--refresh-sample", action="store_true",
                        help="Live mode only: also rewrite the samples from the new processed tables")
    args = parser.parse_args()
    sample_mode = os.getenv("DASHBOARD_SAMPLE_MODE", "0") == "1"
    if args.acquire:
        if sample_mode:
            parser.error("Unset DASHBOARD_SAMPLE_MODE before acquiring live data")
        acquire()
        return
    if args.rank:
        print(rank_chokepoints(read_portwatch(PORTWATCH_DIR)).head(12).to_string())
        return
    if args.validate:
        frames = {d: read_dataset(DATA / out, d) for d, (_, out) in OUTPUTS.items()}
        for dataset, frame in frames.items():
            validate(frame, dataset)
        validate_pair(frames["steo_history"], frames["steo_forecast"])
        print("Processed data valid")
        return
    if sample_mode:
        if args.refresh_sample:
            parser.error("--refresh-sample needs live mode; unset DASHBOARD_SAMPLE_MODE")
        # Each sample is already in its final shape, so offline mode re-checks and rewrites it.
        tables = {d: finalise(read_dataset(DATA / sample, d), d) for d, (sample, _) in OUTPUTS.items()}
    else:
        needed = [EIA_DIR / name for name, _ in EIA_FILES.values()] + [PORTWATCH_DIR / "chokepoints.json"]
        if not all(path.exists() for path in needed) or not any((PORTWATCH_DIR / "daily").glob("daily_*.json")):
            acquire()
        tables = {d: finalise(frame, d) for d, frame in transform().items()}
    for dataset, frame in tables.items():
        validate(frame, dataset)
    validate_pair(tables["steo_history"], tables["steo_forecast"])
    for dataset, frame in tables.items():
        path = DATA / OUTPUTS[dataset][1]
        frame.to_csv(path, index=False)
        print(f"Validated and wrote {len(frame):,} rows to {path.relative_to(ROOT)}")
    if args.refresh_sample:
        for dataset, frame in tables.items():
            subset = sample_of(frame, dataset)
            validate(subset, dataset)
            path = DATA / OUTPUTS[dataset][0]
            subset.to_csv(path, index=False)
            print(f"Wrote {len(subset):,} sample rows to {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
