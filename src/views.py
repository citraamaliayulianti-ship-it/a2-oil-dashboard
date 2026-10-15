"""The four principal views. Each answers one part of the dashboard question.

Every view keeps its heading, unit, sources, latest-observation date, controls
and outputs inside ``st.container(key=<view id>)`` so it can be checked against
``dashboard.yml``.
"""

from __future__ import annotations

import json

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from src import analysis as an
from src.data import DATA, GROUPS, MARKET, STEO, STEO_GROUPS
from src.theme import (ACCENT, BORDER, BRIGHT, COOL, DOWN, MUTED, PAGE_BG, PANEL, SERIES, TEXT, UP, WARM,
                       section_heading, source_line, style_chart)


DOWNLOAD_LABEL = "Download filtered data (CSV)"
DATE_LABEL = "Latest observation"

SOURCES = {  # id -> (publisher, title); the same text as dashboard.yml
    "eia_spot": ("U.S. Energy Information Administration (EIA)",
                 "Spot Prices for Crude Oil and Petroleum Products, daily (PET_PRI_SPT_S1_D)"),
    "eia_stocks": ("U.S. Energy Information Administration (EIA)",
                   "Weekly U.S. Stocks of Crude Oil and Petroleum Products (PET_STOC_WSTK_DCU_NUS_W)"),
    "eia_cushing": ("U.S. Energy Information Administration (EIA)",
                    "Weekly Cushing, OK Ending Stocks excluding SPR of Crude Oil (W_EPC0_SAX_YCUOK_MBBL)"),
    "eia_steo": ("U.S. Energy Information Administration (EIA)",
                 "Short-Term Energy Outlook, October 2026, monthly data tables (STEO_m.xlsx)"),
    "portwatch_daily": ("International Monetary Fund (IMF PortWatch)",
                        "Daily Chokepoints Data: daily transit calls and estimated trade volumes for 28 chokepoints"),
    "portwatch_list": ("International Monetary Fund (IMF PortWatch)",
                       "PortWatch Chokepoints Database (chokepoint names and coordinates)"),
    "eia_steo_reports": ("U.S. Energy Information Administration (EIA)",
                         "Short-Term Energy Outlook reports, April, August and October 2026 editions"),
    "eia_red_sea": ("U.S. Energy Information Administration (EIA)",
                    "Today in Energy: Fewer tankers transit the Red Sea in 2024 (11 October 2024)"),
    "eia_hormuz": ("U.S. Energy Information Administration (EIA)",
                   "Today in Energy: Amid regional conflict, the Strait of Hormuz remains critical oil chokepoint "
                   "(16 June 2025)"),
    "natural_earth": ("Natural Earth", "Admin 0 – Countries, 1:110m (via world-atlas 2.0.2)"),
}
VIEW_SOURCES = {
    "market_monitor": ["eia_spot", "eia_stocks", "eia_cushing", "portwatch_daily", "eia_steo_reports", "eia_red_sea"],
    "chokepoint_exposure": ["portwatch_daily", "portwatch_list", "eia_hormuz", "eia_red_sea", "natural_earth"],
    "chokepoint_disruption": ["portwatch_daily", "eia_steo_reports", "eia_red_sea"],
    "balance_prices": ["eia_steo", "eia_steo_reports"],
}
TITLES = {  # the same titles as the views in dashboard.yml
    "market_monitor": "Oil market monitor: prices, spreads, U.S. stocks and chokepoint transits",
    "chokepoint_exposure": "Which chokepoints carry the most tanker trade?",
    "chokepoint_disruption": "How did the Red Sea attacks and the Hormuz closure show up in tanker transits?",
    "balance_prices": "How did the global supply-demand balance, inventories and prices respond?",
}
EMPTY = {
    "market_monitor": "No indicators match the selected groups.",
    "chokepoint_disruption": "No chokepoints match the selected filters.",
    "balance_prices": "No series match the selected groups.",
}
PORTWATCH_NOTE = ("Source: UN Global Platform; IMF PortWatch (portwatch.imf.org). Source: International Monetary Fund. "
                  "Calculations (means, shares and changes) by this dashboard.")
EIA_NOTE = "Source: U.S. Energy Information Administration. Calculations by this dashboard."
UNIT_SHORT = {
    "US dollars per barrel": "USD/bbl",
    "US dollars per gallon": "USD/gal",
    "million barrels": "million bbl",
    "tanker transit calls per day": "tankers/day",
}


# ---------------------------------------------------------------- shared pieces

def show_sources(view: str) -> None:
    lines = "  \n".join(f"{SOURCES[s][0]}, {SOURCES[s][1]}" for s in VIEW_SOURCES[view])
    st.caption(f"**Sources:**  \n{lines}")


def _latest_text(frame: pd.DataFrame) -> str:
    return f"{DATE_LABEL}: {frame['date'].max().date().isoformat()}"


def _panel(key: str):
    """Dark panel for charts (styled in src/theme.py through its key)."""
    return st.container(key=f"panel_{key}")


def _download(frame: pd.DataFrame, key: str, name: str) -> None:
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    st.download_button(DOWNLOAD_LABEL, data=out.to_csv(index=False).encode("utf-8"), file_name=name,
                       mime="text/csv", key=key)


def _finish(view: str, selected: pd.DataFrame, name: str, after=None) -> None:
    """End of a view: the download, an optional summary, then the sources at the bottom."""
    _download(selected, f"{view}_download", name)
    if after is not None:
        after()
    st.divider()
    show_sources(view)


def _note(column, label: str, value: str, note: str | None = None, help: str | None = None) -> None:
    """A metric tile whose second line is a note, not a change (no arrow, no colour)."""
    column.metric(label, value, note, delta_color="off", delta_arrow="off", help=help)


def _controls(weights: list[float]) -> list:
    return st.columns(weights, vertical_alignment="bottom")


def _fmt(value: float, unit: str) -> str:
    if pd.isna(value):
        return "–"
    digits = 3 if unit == "US dollars per gallon" else 2 if unit == "US dollars per barrel" else 1
    return f"{value:,.{digits}f}"


def _event_layers(first: pd.Timestamp, last: pd.Timestamp, y_top: float | None = None) -> list[alt.Chart]:
    """Thin vertical rules with short labels for the EIA-dated events inside the x range."""
    events = pd.DataFrame([{"date": pd.Timestamp(e.date), "label": e.short, "text": e.text, "source": e.source}
                           for e in an.EVENTS])
    events = events.loc[events["date"].between(first, last)].reset_index(drop=True)
    events["row"] = [2 + 13 * (i % 2) for i in range(len(events))]   # alternate rows so close labels do not overlap
    if events.empty:
        return []
    rule = alt.Chart(events).mark_rule(color="#787b86", strokeWidth=1).encode(
        x="date:T", tooltip=[alt.Tooltip("text:N", title="Event"), alt.Tooltip("source:N", title="Source")])
    label = alt.Chart(events).mark_text(align="left", baseline="top", dx=4, fontSize=10.5, color=MUTED).encode(
        x="date:T", y=alt.Y("row:Q", scale=None), text="label:N")
    return [rule, label]


# ---------------------------------------------------------------- view 1: market monitor

CHEAT_SHEET = [
    ("Brent", "Spot price of North Sea light sweet crude oil (free on board), the main international benchmark."),
    ("WTI (Cushing)", "Spot price of U.S. inland light sweet crude at Cushing, Oklahoma, the main U.S. benchmark."),
    ("Gasoline, diesel, jet fuel", "Wholesale spot prices of refined products on the U.S. Gulf Coast, in US dollars "
     "per gallon (42 gallons = 1 barrel)."),
    ("Brent minus WTI", "Brent price minus WTI price. A wider spread means seaborne international crude is priced "
     "further above U.S. inland crude."),
    ("3-2-1 crack spread", "(2 × gasoline + 1 × diesel − 3 × WTI) ÷ 3, in US dollars per barrel: a simple gross "
     "margin for turning three barrels of crude into two of gasoline and one of diesel."),
    ("U.S. stocks", "End-of-week inventories: commercial crude (excluding the SPR), the Strategic Petroleum Reserve, "
     "Cushing, total gasoline and distillate fuel oil, in million barrels."),
    ("Tanker transits", "Tanker transit calls per day through a chokepoint, as a 7-day mean, from ship-tracking (AIS) "
     "signals. Near zero means tanker traffic has almost stopped."),
    ("Change, Change %", "Difference from the last value on or before the start of the chosen window. Not shown in "
     "per cent for spreads, which can be close to zero or negative."),
    ("z-score (3y)", "How many standard deviations the latest value sits above (+) or below (−) its mean over the "
     "previous three years. Values beyond ±2 are unusual for that indicator."),
    ("52-week range", "Where the latest value sits between its 52-week low (0%) and high (100%)."),
    ("Colours", "▲ green = higher than at the start of the window, ▼ red = lower. Colour shows direction only, "
     "not whether a move is good or bad."),
]


def _cheat_sheet() -> None:
    rows = "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in CHEAT_SHEET)
    with _panel("cheat_sheet"):
        st.markdown("#### Cheat sheet: how to read the monitor")
        st.markdown(f'<table class="om-cheat"><thead><tr><th>Row or column</th><th>Meaning</th></tr></thead>'
                    f"<tbody>{rows}</tbody></table>", unsafe_allow_html=True)
        st.markdown("")


def _signed(value: float, digits: int = 2, suffix: str = "") -> str:
    if pd.isna(value):
        return "–"
    arrow = "▲" if value > 0 else "▼" if value < 0 else "■"
    return f"{arrow} {abs(value):,.{digits}f}{suffix}"


def _colour_sign(value: float) -> str:
    if pd.isna(value) or value == 0:
        return f"color: {MUTED}"
    return f"color: {UP}" if value > 0 else f"color: {DOWN}"


def _colour_z(value: float) -> str:
    if pd.isna(value):
        return f"color: {MUTED}"
    return f"color: {BRIGHT}; font-weight: 700" if abs(value) >= 2 else f"color: {TEXT}"


def monitor_frame(table: pd.DataFrame) -> pd.DataFrame:
    """The table as displayed: one row per indicator."""
    spreads = table["group"].eq("Spreads")
    return pd.DataFrame({
        "Indicator": table["indicator"],
        "Group": table["group"],
        "Unit": table["unit"].map(UNIT_SHORT),
        "Date": table["date"].dt.strftime("%Y-%m-%d"),
        "Last": table["last"].round(3),
        "Change": table["change"].round(3),
        "Change %": table["change_pct"].where(~spreads).round(2),
        "z-score (3y)": table["zscore"].round(2),
        "52-week range": (table["range_position"] * 100).round(1),
        "1-year trend": table["trend"],
    })


METRIC_NAMES = {"brent": "Brent", "wti": "WTI", "gasoline_usgc": "Gasoline, USGC", "diesel_usgc": "Diesel, USGC",
                "jet_usgc": "Jet fuel, USGC", "brent_wti": "Brent–WTI", "crack_321": "3-2-1 crack",
                "us_crude": "U.S. crude stocks", "us_spr": "U.S. SPR", "cushing": "Cushing stocks",
                "us_gasoline": "U.S. gasoline stocks", "us_distillate": "U.S. distillate stocks",
                "hormuz": "Hormuz tankers", "bab_el_mandeb": "Bab el-Mandeb tankers", "suez": "Suez tankers",
                "cape": "Cape tankers", "malacca": "Malacca tankers"}


def _headline_metrics(table: pd.DataFrame, window: str) -> None:
    """The first indicator of each selected group as a tile: short name and unit, value, change."""
    firsts = table.drop_duplicates("group")
    columns = st.columns(len(firsts))
    for column, (_, row) in zip(columns, firsts.iterrows()):
        unit = UNIT_SHORT[row["unit"]]
        delta = f"{row['change']:+,.2f} ({window})" if pd.notna(row["change"]) else None
        column.metric(f"{METRIC_NAMES[row['indicator_id']]}, {unit}", _fmt(row["last"], row["unit"]), delta,
                      delta_color="normal", help=f"{row['indicator']} on {row['date']:%d %b %Y}")


def _monitor_chart(market: pd.DataFrame, indicator_id: str, as_of: pd.Timestamp | None) -> None:
    series = an.monitor_series(market, indicator_id)
    end = series.index[-1] if as_of is None else series.loc[:as_of].index[-1]
    start = end - pd.DateOffset(years=an.Z_YEARS) + pd.Timedelta(days=1)
    window = series.loc[start:end]
    mean, spread = window.mean(), window.std(ddof=1)
    frame = window.rename("value").reset_index()
    label, _, unit, _, _, _ = MARKET[indicator_id]
    axis_title = f"{label} ({UNIT_SHORT[unit]})"
    band = alt.Chart(pd.DataFrame({"low": [mean - spread], "high": [mean + spread]})).mark_rect(
        color=ACCENT, opacity=0.12).encode(y="low:Q", y2="high:Q")
    centre = alt.Chart(pd.DataFrame({"mean": [mean]})).mark_rule(color="#5b8cff", strokeWidth=1, opacity=0.8).encode(
        y="mean:Q")
    hover = alt.selection_point(on="pointerover", nearest=True, fields=["date"], empty=False)
    line = alt.Chart(frame).mark_line(color=SERIES[0], strokeWidth=2).encode(
        x=alt.X("date:T", title=None, scale=alt.Scale(domain=[start.isoformat(), end.isoformat()])),
        y=alt.Y("value:Q", title=axis_title, scale=alt.Scale(zero=False)))
    points = alt.Chart(frame).mark_point(size=60, filled=True, color=BRIGHT).encode(
        x="date:T", y="value:Q", opacity=alt.when(hover).then(alt.value(1)).otherwise(alt.value(0)),
        tooltip=[alt.Tooltip("date:T", title="Date", format="%d %b %Y"),
                 alt.Tooltip("value:Q", title=UNIT_SHORT[unit], format=",.2f")]).add_params(hover)
    chart = alt.layer(band, centre, line, points, *_event_layers(start, end)).properties(
        height=330, title=alt.TitleParams(label, subtitle=(
            f"Three years to {end:%d %b %Y}. Shaded band: three-year mean ± 1 standard deviation "
            f"(z-score between −1 and +1).")))
    st.altair_chart(style_chart(chart), width="stretch")


def render_monitor(market: pd.DataFrame, after=None) -> None:
    """View 1: a market-monitor table of the latest value, change, z-score and range of each indicator."""
    view = "market_monitor"
    section_heading(
        TITLES[view],
        lead=("Each row is one indicator: its latest value, how far it has moved over the chosen window, how unusual "
              "that level is against the last three years (z-score) and where it sits in its 52-week range. Pick a "
              "date before an event to see what the monitor showed then."),
        kicker="Market monitor",
        meta=["Unit: as listed in each row (US dollars per barrel, US dollars per gallon, million barrels, tanker "
              "transit calls per day).",
              f"{_latest_text(market)} (each row shows the date of its own latest value)."])
    groups_col, asof_col, window_col = _controls([3.2, 2.2, 1.2])
    with groups_col:
        groups = st.multiselect("Indicator groups", GROUPS, default=GROUPS, key="monitor_groups")
    with asof_col:
        as_of_label = st.selectbox("Monitor date", list(an.AS_OF), key="monitor_asof")
    with window_col:
        window = st.selectbox("Change over", list(an.WINDOWS), index=1, key="monitor_window")

    selected = market.loc[market["group"].isin(groups)]
    def closing() -> None:
        if after is not None and not selected.empty:
            after()
        _cheat_sheet()

    if selected.empty:
        st.info(EMPTY[view])
        _finish(view, selected, "oil_monitor_selection.csv", after=closing)
        return

    table = an.monitor_table(selected, as_of_label, window)
    _headline_metrics(table, window)
    numbers = monitor_frame(table)
    # Changes are shown as text with an arrow (so missing per-cent changes read "–", not "None");
    # their colour comes from the numbers behind them.
    shown = numbers.assign(**{"Change": numbers["Change"].map(_signed),
                              "Change %": numbers["Change %"].map(lambda v: _signed(v, 1, "%"))})

    def colours(_: pd.DataFrame) -> pd.DataFrame:
        css = pd.DataFrame("", index=numbers.index, columns=numbers.columns)
        for name in ["Change", "Change %"]:
            css[name] = numbers[name].map(_colour_sign)
        css["z-score (3y)"] = numbers["z-score (3y)"].map(_colour_z)
        return css

    styled = (shown.style.format({"Last": "{:,.2f}", "z-score (3y)": "{:+.1f}", "52-week range": "{:.0f}"},
                                 na_rep="–")
              .apply(colours, axis=None))
    st.dataframe(
        styled, hide_index=True, width="stretch", height=min(38 + 35 * len(shown), 640),
        column_config={
            "Indicator": st.column_config.TextColumn(width=290),
            "Group": st.column_config.TextColumn(width=128),
            "Unit": st.column_config.TextColumn(width=86),
            "Date": st.column_config.TextColumn(width=92),
            "Last": st.column_config.Column(width=74),
            "Change": st.column_config.Column(width=74),
            "Change %": st.column_config.Column(width=78),
            "z-score (3y)": st.column_config.Column(width=82, help="Standard deviations from the three-year mean"),
            "52-week range": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%", width=140,
                                                             help="0% = 52-week low, 100% = 52-week high"),
            "1-year trend": st.column_config.LineChartColumn(width=130, help="Weekly values, past 52 weeks"),
        })
    source_line("Source: U.S. Energy Information Administration; UN Global Platform; IMF PortWatch (portwatch.imf.org). "
                "Changes, z-scores, ranges, spreads and 7-day means calculated by this dashboard.")

    as_of = an.AS_OF[as_of_label]
    as_of = pd.Timestamp(as_of) if as_of else None
    with _panel("monitor_chart"):
        options = list(table["indicator_id"])
        choice = st.selectbox("Chart indicator", options, format_func=an.indicator_label, key="monitor_chart")
        _monitor_chart(selected, choice, as_of)
        source_line("Vertical lines: event dates reported by EIA (hover for the source).")
    _finish(view, selected, "oil_monitor_selection.csv", after=closing)


# ---------------------------------------------------------------- view 2: chokepoint exposure

EXPOSURE_MEASURES = {  # label -> (column, unit text, scale)
    "Tanker trade volume": ("tanker_volume_t", "million metric tons per day", 1e-6),
    "Tanker transit calls": ("tanker_transits", "tanker transit calls per day", 1.0),
}
MAP_FILE = DATA / "geo" / "countries-110m-iso3.json"


@st.cache_data
def _outlines(path: str) -> dict:
    return json.loads(open(path, encoding="utf-8").read())


def _exposure_map(table: pd.DataFrame, column: str, scale: float, unit: str, change: str, year: int) -> None:
    outlines = _outlines(str(MAP_FILE))
    geo = alt.InlineData(values=outlines, format=alt.DataFormat(type="topojson", feature="countries"),
                         name="country_outlines")
    land = alt.Chart(geo).mark_geoshape(fill="#2a2e39", stroke=PAGE_BG, strokeWidth=0.5)
    globe = alt.Chart(alt.sphere()).mark_geoshape(fill="#161a25", stroke=BORDER, strokeWidth=0.8)
    points = table.assign(value=table[column] * scale, change_capped=table[change].clip(-100, 100))
    points["label"] = np.where(points.index < 6, points["chokepoint"], "")
    encode = dict(
        longitude="lon:Q", latitude="lat:Q",
        size=alt.Size("value:Q", scale=alt.Scale(range=[15, 1500], zero=True), legend=None),
        color=alt.Color("change_capped:Q", title="Change from Jan 2019–Oct 2023 (%)",
                        scale=alt.Scale(domain=[-100, -50, 0, 50, 100],
                                        range=[WARM, "#f2a5a5", "#9598a1", "#9cc3f2", COOL], interpolate="lab"),
                        legend=alt.Legend(orient="bottom", direction="horizontal", gradientLength=260,
                                          titleOrient="left")),
        tooltip=[alt.Tooltip("chokepoint:N", title="Chokepoint"),
                 alt.Tooltip("value:Q", title=unit, format=",.2f"),
                 alt.Tooltip(f"{change}:Q", title="Change from Jan 2019–Oct 2023 (%)", format="+.0f")],
    )
    circles = alt.Chart(points).mark_circle(opacity=0.92, stroke=PAGE_BG, strokeWidth=1).encode(**encode)
    labels = alt.Chart(points).mark_text(align="left", dx=9, dy=-6, fontSize=11, color=TEXT).encode(
        longitude="lon:Q", latitude="lat:Q", text="label:N")
    chart = alt.layer(globe, land, circles, labels).project("equalEarth").properties(
        height=430, title=alt.TitleParams(f"Where tanker trade passes, {year}", subtitle=[
            "Circle area: mean per day in the year.",
            "Colour: change from the Jan 2019–Oct 2023 mean (red = lower, blue = higher, capped at ±100%)."]))
    st.altair_chart(style_chart(chart), width="stretch")


def _exposure_bars(table: pd.DataFrame, column: str, scale: float, unit: str, base: str, year: int) -> None:
    top = table.head(15).assign(value=lambda f: f[column] * scale, base=lambda f: f[base] * scale)
    order = list(top["chokepoint"])
    y = alt.Y("chokepoint:N", sort=order, title=None, axis=alt.Axis(labelLimit=180))
    bars = alt.Chart(top).mark_bar(color=SERIES[0], cornerRadiusEnd=3, height={"band": 0.72}).encode(
        y=y, x=alt.X("value:Q", title=unit),
        tooltip=[alt.Tooltip("chokepoint:N", title="Chokepoint"), alt.Tooltip("value:Q", title=str(year), format=",.2f"),
                 alt.Tooltip("base:Q", title="Jan 2019–Oct 2023 mean", format=",.2f")])
    ticks = alt.Chart(top).mark_tick(color=BRIGHT, thickness=2, size=16).encode(y=y, x="base:Q")
    chart = alt.layer(bars, ticks).properties(height=470, title=alt.TitleParams(
        f"Top 15 chokepoints by tanker trade, {year}", subtitle=["Bars: selected year.",
                                                                 "White ticks: Jan 2019–Oct 2023 mean (before the Red Sea attacks)."]))
    st.altair_chart(style_chart(chart), width="stretch")


def render_exposure(monthly: pd.DataFrame, after=None) -> None:
    """View 2: which chokepoints carry the most tanker trade in a chosen year."""
    view = "chokepoint_exposure"
    section_heading(
        TITLES[view],
        lead=("PortWatch counts every vessel crossing 28 chokepoint boundaries from ship-tracking (AIS) signals and "
              "estimates the cargo each one carries. The map and ranking show the mean per day in the chosen year, "
              "compared with the period before the Red Sea attacks (January 2019 to October 2023)."),
        kicker="Question 1 of 3",
        meta=["Unit: million metric tons per day (estimated tanker trade volume) or tanker transit calls per day, "
              "mean of all days in the year.", _latest_text(monthly)])
    years = sorted(monthly["year"].unique().tolist())
    year_col, measure_col = _controls([1.2, 2.4])
    with year_col:
        year = st.selectbox("Year", years, index=years.index(2025) if 2025 in years else len(years) - 1,
                            key="exposure_year")
    with measure_col:
        measure = st.radio("Measure", list(EXPOSURE_MEASURES), horizontal=True, key="exposure_measure")
    selected = monthly.loc[monthly["year"] == year]
    if selected.empty:
        st.info("No chokepoint data for the selected year.")
        _finish(view, selected, "chokepoint_exposure_selection.csv")
        return
    column, unit, scale = EXPOSURE_MEASURES[measure]
    table = an.yearly_exposure(monthly, year)
    table = table.sort_values(column, ascending=False).reset_index(drop=True)
    share = "volume_share" if column == "tanker_volume_t" else "transit_share"
    change = "volume_change" if column == "tanker_volume_t" else "transit_change"
    base = "base_volume_t" if column == "tanker_volume_t" else "base_transits"
    days = int(table["days"].max())
    first_day, last_day = selected["date"].min(), selected["date"].max()

    hormuz = table.loc[table["chokepoint"] == "Strait of Hormuz"].iloc[0]
    short = "million t/day" if column == "tanker_volume_t" else "tankers/day"
    m1, m2, m3, m4 = st.columns(4)
    _note(m1, "Largest chokepoint", table.loc[0, "chokepoint"], f"{table.loc[0, share]:.1f}% of the 28-chokepoint total")
    _note(m2, "Top two, share of total", f"{table.loc[:1, share].sum():.1f}%", " + ".join(table.loc[:1, "chokepoint"]))
    m3.metric(f"Strait of Hormuz, {short}", f"{hormuz[column] * scale:,.2f}",
              f"{hormuz[change]:+.0f}% vs Jan 2019–Oct 2023", delta_color="normal")
    _note(m4, "Days covered", f"{days}", f"{first_day:%b %Y} – {last_day:%b %Y}")

    left, right = st.columns([1.35, 1])
    with left:
        with _panel("exposure_map"):
            _exposure_map(table, column, scale, unit, change, year)
            source_line(PORTWATCH_NOTE + " Outlines: Natural Earth.")
    with right:
        with _panel("exposure_bars"):
            _exposure_bars(table, column, scale, unit, base, year)
            source_line(PORTWATCH_NOTE)

    shown = pd.DataFrame({
        "Rank": np.arange(1, len(table) + 1),
        "Chokepoint": table["chokepoint"],
        f"{year} ({unit})": (table[column] * scale).round(3),
        "Share of 28-chokepoint total (%)": table[share].round(1),
        f"Jan 2019–Oct 2023 mean ({unit})": (table[base] * scale).round(3),
        "Change (%)": table[change].round(1),
    })
    st.dataframe(shown, hide_index=True, width="stretch", height=390)
    st.caption("Shares are of the sum over all 28 chokepoints; a tanker that crosses two chokepoints on one voyage is "
               "counted at both, so shares describe traffic through each chokepoint, not shares of world oil trade. "
               f"{year} covers {first_day:%B %Y} to {last_day:%B %Y}.")
    _finish(view, selected, "chokepoint_exposure_selection.csv", after=after)


# ---------------------------------------------------------------- view 3: disruptions

DEFAULT_CHOKEPOINTS = ["Strait of Hormuz", "Bab el-Mandeb Strait", "Suez Canal", "Cape of Good Hope"]


def _index_chart(part: pd.DataFrame, name: str, base_text: str, unit: str, domain: list, y_max: float) -> None:
    hover = alt.selection_point(on="pointerover", nearest=True, fields=["date"], empty=False)
    x = alt.X("date:T", title=None, scale=alt.Scale(domain=domain))
    line = alt.Chart(part).mark_line(color=SERIES[0], strokeWidth=2).encode(
        x=x, y=alt.Y("index:Q", title="7-day mean, % of baseline", scale=alt.Scale(domain=[0, y_max])))
    baseline = alt.Chart(pd.DataFrame({"y": [100]})).mark_rule(color=BRIGHT, strokeWidth=1, opacity=0.55).encode(y="y:Q")
    points = alt.Chart(part).mark_point(size=55, filled=True, color=BRIGHT).encode(
        x="date:T", y="index:Q", opacity=alt.when(hover).then(alt.value(1)).otherwise(alt.value(0)),
        tooltip=[alt.Tooltip("date:T", title="Date", format="%d %b %Y"),
                 alt.Tooltip("rolling:Q", title=f"7-day mean ({unit})", format=",.1f"),
                 alt.Tooltip("index:Q", title="% of baseline", format=".0f")]).add_params(hover)
    first, last = pd.Timestamp(domain[0]), pd.Timestamp(domain[1])
    chart = alt.layer(baseline, line, points, *_event_layers(first, last)).properties(
        height=230, title=alt.TitleParams(name, subtitle=f"Baseline (100): {base_text}"))
    st.altair_chart(style_chart(chart), width="stretch")


def render_disruption(day: pd.DataFrame, after=None) -> None:
    """View 3: daily tanker transits through selected chokepoints against a pre-event baseline."""
    view = "chokepoint_disruption"
    section_heading(
        TITLES[view],
        lead=("Each panel shows the 7-day mean of daily tanker transits through one chokepoint as a percentage of "
              "its own mean in a baseline period before an event (100 = baseline), so chokepoints of very different "
              "size share one scale. Vertical lines mark the events EIA reports."),
        kicker="Question 2 of 3",
        meta=["Unit: tanker transit calls per day (or metric tons per day), shown as a percentage of the baseline "
              "mean.", _latest_text(day)])
    names = [n for n in day.drop_duplicates("portid")["chokepoint"]]
    first_day, last_day = day["date"].min().date(), day["date"].max().date()
    default_start = max(first_day, pd.Timestamp("2023-01-01").date())
    choke_col, period_col = _controls([2.2, 2])
    with choke_col:
        chosen = st.multiselect("Chokepoints", names, default=[n for n in DEFAULT_CHOKEPOINTS if n in names],
                                key="disruption_chokepoints")
    with period_col:
        period = st.slider("Period", min_value=first_day, max_value=last_day, value=(default_start, last_day),
                           format="YYYY-MM-DD", key="disruption_period")
    measure_col, base_col = _controls([2.2, 2])
    with measure_col:
        measure = st.radio("Measure", list(an.MEASURES), horizontal=True, key="disruption_measure")
    with base_col:
        baseline_label = st.selectbox("Baseline period", list(an.BASELINES), key="disruption_baseline")

    start, end = pd.Timestamp(period[0]), pd.Timestamp(period[1])
    selected = day.loc[day["chokepoint"].isin(chosen) & day["date"].between(start, end)]
    if selected.empty:
        st.info(EMPTY[view])
        _finish(view, selected, "chokepoint_transits_selection.csv")
        return

    column = an.MEASURES[measure]
    unit = "tanker transit calls per day" if column == "n_tanker" else "metric tons per day"
    baselines = an.baseline_means(day, column, baseline_label)
    # Rolling means use the full daily record, so the first days of a selection are not dropped.
    rolled = an.rolling_means(day.loc[day["chokepoint"].isin(chosen)], column)
    rolled = rolled.loc[rolled["date"].between(start, end)].dropna(subset=["rolling"])
    rolled["index"] = rolled["rolling"] / rolled["chokepoint"].map(baselines) * 100
    recent = an.recent_change(selected, column, baselines)

    metric_cols = st.columns(min(len(chosen), 4))
    for i, name in enumerate([n for n in names if n in chosen][:4]):
        row = recent.loc[recent["chokepoint"] == name]
        if row.empty:
            continue
        row = row.iloc[0]
        metric_cols[i].metric(name, f"{row['recent']:,.1f}" if column == "n_tanker" else f"{row['recent'] / 1e6:,.2f}m t",
                              f"{row['change']:+.0f}% vs baseline" if pd.notna(row["change"]) else None,
                              delta_color="normal", help=f"Mean of the 30 days to {row['end']:%d %b %Y}")
    st.caption(f"Metrics: mean per day over the last 30 days of the selection, against the baseline "
               f"({baseline_label}).")

    y_max = float(max(150, min(320, rolled["index"].max() * 1.08))) if not rolled.empty else 150
    domain = [start.isoformat(), end.isoformat()]
    ordered = [n for n in names if n in chosen]
    grid = st.columns(2)
    for i, name in enumerate(ordered):
        part = rolled.loc[rolled["chokepoint"] == name]
        with grid[i % 2]:
            with _panel(f"disruption_{i}"):
                if part.empty:
                    st.caption(f"{name}: fewer than 7 days in the selection.")
                else:
                    base = baselines.get(name, np.nan)
                    base_text = (f"{base:,.1f} tanker transit calls per day" if column == "n_tanker"
                                 else f"{base / 1e6:,.2f} million metric tons per day")
                    _index_chart(part, name, base_text, unit, domain, y_max)
    source_line(PORTWATCH_NOTE + " Event dates: EIA.")

    monthly = an.monthly_against_baseline(selected, column, baselines)
    wide = monthly.pivot(index="month", columns="chokepoint", values="index").reindex(columns=ordered)
    wide = wide.sort_index(ascending=False).round(0)
    wide.index = wide.index.strftime("%b %Y")
    st.markdown("##### Monthly mean as % of baseline (100 = baseline)")
    st.dataframe(wide, width="stretch", height=360)
    _finish(view, selected, "chokepoint_transits_selection.csv", after=after)


# ---------------------------------------------------------------- view 4: balance and prices

GULF = ["papr_sa", "papr_iz", "papr_tc", "papr_ku", "papr_IR", "papr_QA", "papr_ba"]
STEO_NOTE = "Source: U.S. Energy Information Administration, Short-Term Energy Outlook (October 2026). " \
            "Dashed lines and pale bars: EIA forecast."


def _balance_lines(history: pd.DataFrame, forecast: pd.DataFrame, codes: dict[str, str], title: str,
                   subtitle: str, axis: str, domain: list) -> None:
    frame = pd.concat([history, forecast]).loc[lambda f: f["series_id"].isin(codes)]
    if not forecast.empty:  # repeat the last historical month as the first forecast point so the lines join
        bridge = history.loc[history["series_id"].isin(codes)].sort_values("date").groupby("series_id").tail(1)
        frame = pd.concat([frame, bridge.assign(status="Forecast")])
    frame = frame.assign(name=frame["series_id"].map(codes))
    names = list(codes.values())
    colour = alt.Color("name:N", title=None, scale=alt.Scale(domain=names, range=SERIES[:len(names)]),
                       legend=alt.Legend(orient="top"))
    base = alt.Chart(frame).encode(
        x=alt.X("date:T", title=None, scale=alt.Scale(domain=domain)),
        y=alt.Y("value:Q", title=axis, scale=alt.Scale(zero=False)), color=colour,
        strokeDash=alt.StrokeDash("status:N", title=None, scale=alt.Scale(domain=["Historical", "Forecast"],
                                                                          range=[[1, 0], [5, 3]]),
                                  legend=None),
        detail="status:N",
        tooltip=[alt.Tooltip("name:N", title="Series"), alt.Tooltip("date:T", title="Month", format="%b %Y"),
                 alt.Tooltip("value:Q", title=axis, format=",.2f"), alt.Tooltip("status:N", title="Status")])
    lines = base.mark_line(strokeWidth=2)
    points = base.mark_point(size=40, filled=True, opacity=0.0)
    first, last = pd.Timestamp(domain[0]), pd.Timestamp(domain[1])
    chart = alt.layer(lines, points, *_event_layers(first, last)).properties(
        height=300, title=alt.TitleParams(title, subtitle=subtitle))
    st.altair_chart(style_chart(chart), width="stretch")


def _draw_bars(history: pd.DataFrame, forecast: pd.DataFrame, domain: list) -> None:
    frame = pd.concat([history, forecast]).loc[lambda f: f["series_id"] == "t3_stchange_world"]
    frame = frame.assign(direction=np.where(frame["value"] >= 0, "Stocks fall (draw)", "Stocks rise (build)"))
    bars = alt.Chart(frame).mark_bar(width={"band": 0.8}, cornerRadius=2).encode(
        x=alt.X("yearmonth(date):T", title=None, scale=alt.Scale(domain=domain)),
        y=alt.Y("value:Q", title="million barrels per day"), y2=alt.datum(0),
        color=alt.Color("direction:N", title=None, scale=alt.Scale(domain=["Stocks fall (draw)", "Stocks rise (build)"],
                                                                    range=[WARM, COOL]),
                        legend=alt.Legend(orient="top")),
        opacity=alt.Opacity("status:N", scale=alt.Scale(domain=["Historical", "Forecast"], range=[1.0, 0.4]),
                            legend=None),
        tooltip=[alt.Tooltip("date:T", title="Month", format="%b %Y"),
                 alt.Tooltip("value:Q", title="Net withdrawal (million b/d)", format="+.2f"),
                 alt.Tooltip("status:N", title="Status")])
    zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#434651").encode(y="y:Q")
    first, last = pd.Timestamp(domain[0]), pd.Timestamp(domain[1])
    chart = alt.layer(zero, bars, *_event_layers(first, last)).properties(height=260, title=alt.TitleParams(
        "World inventory net withdrawals", subtitle=["Consumption minus production.",
                                                     "Red: stocks fall; blue: stocks rise; pale: EIA forecast."]))
    st.altair_chart(style_chart(chart), width="stretch")


def _gulf_area(history: pd.DataFrame, domain: list) -> None:
    labels = {code: history.loc[history["series_id"] == code, "series"].iloc[0] for code in GULF
              if code in set(history["series_id"])}
    frame = history.loc[history["series_id"].isin(labels)].assign(name=lambda f: f["series_id"].map(labels))
    names = list(labels.values())
    order = {name: i for i, name in enumerate(names)}
    frame = frame.assign(order=frame["name"].map(order))
    area = alt.Chart(frame).mark_area(stroke=PANEL, strokeWidth=1).encode(
        x=alt.X("date:T", title=None, scale=alt.Scale(domain=domain)),
        y=alt.Y("value:Q", title="million barrels per day", stack="zero"),
        color=alt.Color("name:N", title=None, scale=alt.Scale(domain=names, range=SERIES[:len(names)]),
                        legend=alt.Legend(orient="top", columns=4)),
        order=alt.Order("order:Q"),
        tooltip=[alt.Tooltip("name:N", title="Producer"), alt.Tooltip("date:T", title="Month", format="%b %Y"),
                 alt.Tooltip("value:Q", title="million b/d", format=",.2f")])
    first, last = pd.Timestamp(domain[0]), pd.Timestamp(domain[1])
    chart = alt.layer(area, *_event_layers(first, last)).properties(height=300, title=alt.TitleParams(
        "Liquids production of the seven Gulf producers inside the Strait of Hormuz",
        subtitle=["Crude oil and other liquids, EIA historical estimates.",
                  "No forecast: EIA publishes none for four of the seven."]))
    st.altair_chart(style_chart(chart), width="stretch")


def _balance_metrics(history: pd.DataFrame, forecast: pd.DataFrame, groups: list[str], show_forecast: bool) -> None:
    wide = an.balance_wide(history)
    cells = []
    if "World balance" in groups:
        draws = wide["t3_stchange_world"]
        total = float((draws * draws.index.days_in_month).sum())
        word = "fell" if total > 0 else "rose"
        cells.append(("World inventories, million bbl", f"{'−' if total > 0 else '+'}{abs(total):,.0f}",
                      f"{word}, {draws.index[0]:%b %Y}–{draws.index[-1]:%b %Y}", "off"))
    if "Prices" in groups:
        brent = wide["BREPUUS"]
        cells.append(("Brent peak month, USD/bbl", f"{brent.max():,.2f}",
                      f"{brent.idxmax():%b %Y}; lowest {brent.min():,.2f} ({brent.idxmin():%b %Y})", "off"))
        if show_forecast and not forecast.empty:
            future = forecast.loc[forecast["series_id"] == "BREPUUS"].set_index("date")["value"]
            q4 = future.loc["2026-10":"2026-12"]
            if len(q4):
                cells.append(("EIA forecast, Brent Q4 2026", f"{q4.mean():,.2f}",
                              f"Oct 2026 STEO; {future.index[-1]:%b %Y}: {future.iloc[-1]:,.2f}", "off"))
    if "Gulf producers" in groups:
        gulf = wide[[c for c in GULF if c in wide]].sum(axis=1)
        low = gulf.idxmin()
        cells.append(("Gulf producers' low, million b/d", f"{gulf.min():,.1f}",
                      f"{low:%b %Y}; {gulf.min() - gulf.iloc[0]:+.1f} vs {gulf.index[0]:%b %Y}", "off"))
    columns = st.columns(max(len(cells), 1))
    for column, (label, value, note, _) in zip(columns, cells):
        _note(column, label, value, note)


def render_balance(history: pd.DataFrame, forecast: pd.DataFrame, after=None) -> None:
    """View 4: world production, consumption and stock changes, Brent, and Gulf producers' output."""
    view = "balance_prices"
    section_heading(
        TITLES[view],
        lead=("EIA's Short-Term Energy Outlook estimates world supply and demand month by month. When consumption "
              "exceeds production the difference comes out of inventories (a draw). The charts set that balance "
              "beside Brent prices and the output of the Gulf producers whose exports pass the Strait of Hormuz."),
        kicker="Question 3 of 3",
        meta=["Unit: million barrels per day (production, consumption and stock changes); US dollars per barrel "
              "(prices); million barrels (inventories).",
              f"{_latest_text(history)} (last historical month in the {history['edition'].iloc[0]} STEO; "
              f"forecasts run to {forecast['date'].max():%B %Y})."])
    years = sorted(history["year"].unique().tolist())
    period_col, groups_col, forecast_col = _controls([2, 2.6, 1.6])
    with period_col:
        first, last = st.slider("Period", min_value=years[0], max_value=years[-1], value=(years[0], years[-1]),
                                key="balance_period")
    with groups_col:
        groups = st.multiselect("Series groups", STEO_GROUPS, default=STEO_GROUPS, key="balance_groups")
    with forecast_col:
        show_forecast = st.checkbox("Show EIA forecast", value=True, key="balance_forecast")

    selected = history.loc[history["year"].between(first, last) & history["group"].isin(groups)]
    if selected.empty:
        st.info(EMPTY[view])
        _finish(view, selected, "steo_selection.csv")
        return
    future = forecast.loc[forecast["group"].isin(groups)] if show_forecast else forecast.iloc[0:0]
    end = future["date"].max() if not future.empty else selected["date"].max()
    domain = [pd.Timestamp(f"{first}-01-01").isoformat(), (end + pd.Timedelta(days=15)).isoformat()]

    _balance_metrics(selected, future, groups, show_forecast)
    if "World balance" in groups:
        left, right = st.columns(2)
        with left:
            with _panel("balance_lines"):
                _balance_lines(selected, future, {"papr_world": "Production", "patc_world": "Consumption"},
                               "World production and consumption", "Petroleum and other liquids. Solid: EIA "
                               "historical estimates; dashed: EIA forecast.", "million barrels per day", domain)
                source_line(STEO_NOTE)
        with right:
            with _panel("balance_draws"):
                _draw_bars(selected, future, domain)
                source_line(STEO_NOTE)
    if "Prices" in groups or "Gulf producers" in groups:
        left, right = st.columns(2)
        if "Prices" in groups:
            with left:
                with _panel("balance_prices"):
                    _balance_lines(selected, future, {"BREPUUS": "Brent", "WTIPUUS": "WTI"},
                                   "Crude oil spot prices, monthly average", "Solid: historical; dashed: EIA "
                                   "forecast.", "US dollars per barrel", domain)
                    source_line(STEO_NOTE)
        if "Gulf producers" in groups:
            with right if "Prices" in groups else left:
                with _panel("balance_gulf"):
                    _gulf_area(selected, domain)
                    source_line("Source: U.S. Energy Information Administration, Short-Term Energy Outlook "
                                "(October 2026), tables 3b and 3c.")

    wide = selected.pivot_table(index="date", columns="series_id", values="value").sort_index(ascending=False)
    labels = selected.drop_duplicates("series_id").set_index("series_id")["series"]
    wide = wide[[c for c in STEO if c in wide.columns]].rename(columns=labels)
    wide.index = wide.index.strftime("%b %Y")
    st.markdown("##### Monthly values (historical, EIA estimates)")
    st.dataframe(wide.round(2), width="stretch", height=360)
    _finish(view, selected, "steo_selection.csv", after=after)
