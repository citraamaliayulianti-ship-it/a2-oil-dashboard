"""Shared page pieces: the three question cards and the data documentation."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.theme import cards
from src.views import SOURCES

def questions() -> None:
    st.markdown("#### Three questions behind the monitor")
    cards([
        ("Question 1", "Which chokepoints carry the most tanker trade?", "exposure",
         "Map and ranking of 28 chokepoints by tanker transits and estimated tanker trade volume, by year."),
        ("Question 2", "How did the Red Sea attacks and the Hormuz closure show up in transits?", "disruptions",
         "Daily tanker transits through each chokepoint against a pre-event baseline, with EIA event dates."),
        ("Question 3", "How did the balance, inventories and prices respond?", "balance",
         "EIA estimates of world production, consumption and stock draws, Gulf producers' output and Brent."),
        ("Conclusion", "Findings, limits and implications", "conclusion",
         "What the data show, what they cannot show, and what to watch."),
    ])


SOURCE_DETAILS = {  # id -> (URL, licence or reuse terms, retrieved)
    "eia_spot": ("https://www.eia.gov/dnav/pet/pet_pri_spt_s1_d.htm", "U.S. government data, public domain; cite EIA",
                 "2026-10-15"),
    "eia_stocks": ("https://www.eia.gov/dnav/pet/pet_stoc_wstk_dcu_nus_w.htm",
                   "U.S. government data, public domain; cite EIA", "2026-10-15"),
    "eia_cushing": ("https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=W_EPC0_SAX_YCUOK_MBBL&f=W",
                    "U.S. government data, public domain; cite EIA", "2026-10-15"),
    "eia_steo": ("https://www.eia.gov/outlooks/steo/data.php", "U.S. government data, public domain; cite EIA",
                 "2026-10-15"),
    "portwatch_daily": ("https://portwatch.imf.org/", "IMF terms of use: free reuse with attribution "
                        "(\"Source: International Monetary Fund\") and a note of any changes", "2026-10-15"),
    "portwatch_list": ("https://portwatch.imf.org/", "IMF terms of use (as above)", "2026-10-15"),
    "eia_steo_reports": ("https://www.eia.gov/outlooks/steo/archives/", "Public domain; cite EIA", "2026-10-15"),
    "eia_red_sea": ("https://www.eia.gov/todayinenergy/detail.php?id=63446", "Public domain; cite EIA", "2026-10-15"),
    "eia_hormuz": ("https://www.eia.gov/todayinenergy/detail.php?id=65504", "Public domain; cite EIA", "2026-10-15"),
    "natural_earth": ("https://www.naturalearthdata.com/downloads/110m-cultural-vectors/", "Public domain",
                      "2026-10-13"),
}
DATASETS = {  # id -> (what one row is, files)
    "chokepoint_day": ("one chokepoint on one day (ten chokepoints)", "data/processed.csv"),
    "chokepoint_month": ("one chokepoint in one month (all 28)", "data/processed_chokepoint_month.csv"),
    "market_day": ("one monitor indicator on one observation date", "data/processed_market_day.csv"),
    "steo_history": ("one STEO series in one month, historical", "data/processed_steo_history.csv"),
    "steo_forecast": ("one STEO series in one month, forecast", "data/processed_steo_forecast.csv"),
}


def about_the_data(frames: dict[str, pd.DataFrame]) -> None:
    st.markdown("### Datasets")
    rows = [{"Dataset": name, "One row is": what, "Rows": f"{len(frames[name]):,}",
             "From": f"{frames[name]['date'].min():%Y-%m-%d}", "To": f"{frames[name]['date'].max():%Y-%m-%d}",
             "File": path} for name, (what, path) in DATASETS.items()]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.markdown("### Sources")
    table = pd.DataFrame([{"Publisher": SOURCES[k][0], "Title": SOURCES[k][1], "URL": url, "Terms": terms,
                           "Retrieved": when} for k, (url, terms, when) in SOURCE_DETAILS.items()])
    st.dataframe(table, hide_index=True, width="stretch",
                 column_config={"URL": st.column_config.LinkColumn(width="medium")})
    st.markdown(
        "PortWatch data are derived from AIS ship-tracking signals provided by the UN Global Platform "
        "(recommended citation: *Sources: UN Global Platform; IMF PortWatch (portwatch.imf.org)*). Changes made "
        "here: daily rows kept for ten chokepoints, monthly means for all 28, transit counts averaged over 7 days, "
        "and comparisons with baselines. EIA files are used as published, with stocks converted to million "
        "barrels and two spreads calculated from spot prices.")


def access_data() -> None:
    st.markdown("### Rebuild the data")
    st.markdown("Each command runs from the dashboard folder (Python 3.11, packages in `requirements.txt`).")
    st.code("python -m src.data --acquire     # download the EIA workbooks and PortWatch pages into data/raw/\n"
            "python -m src.data               # rebuild and validate the five processed tables\n"
            "DASHBOARD_SAMPLE_MODE=1 python -m src.data   # offline: rebuild from the bundled samples\n"
            "streamlit run app.py", language="bash")
