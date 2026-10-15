"""Page text: what each view's data show, the conclusion, and methods and limitations.

Every number in this text is calculated from the bundled data when the page renders.
Statements that come from EIA publications are attributed to them in the sentence.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src import analysis as an

HOME = "home.py"
PAGE_EXPOSURE = "sections/1_exposure.py"
PAGE_DISRUPTIONS = "sections/2_disruptions.py"
PAGE_BALANCE = "sections/3_balance.py"
PAGE_CONCLUSION = "sections/4_conclusion.py"
PAGE_DATA = "sections/5_data.py"

RED_SEA_BASE = ("2023-01-01", "2023-10-31")
RED_SEA_AFTER = ("2024-01-01", "2024-08-31")     # the months EIA compares in Today in Energy (Oct 2024)
HORMUZ_BASE = ("2025-02-28", "2026-02-27")
HORMUZ_AFTER = ("2026-03-01", None)


def page_nav(previous: tuple[str, str] | None = None, following: tuple[str, str] | None = None) -> None:
    left, _, right = st.columns([1, 2, 1])
    if previous:
        left.page_link(previous[0], label=f"← {previous[1]}")
    if following:
        right.page_link(following[0], label=f"{following[1]} →")


def _pct(new: float, old: float) -> float:
    return (new / old - 1) * 100 if old else float("nan")


def _mean(day: pd.DataFrame, name: str, period: tuple[str, str | None], column: str = "n_tanker") -> float:
    last = period[1] or day["date"].max()
    part = day.loc[(day["chokepoint"] == name) & day["date"].between(period[0], last), column]
    return float(part.mean()) if len(part) else float("nan")


def _series(market: pd.DataFrame, indicator: str) -> pd.Series:
    return an.monitor_series(market, indicator)


def _at(series: pd.Series, when: str | None = None) -> tuple[pd.Timestamp, float]:
    part = series if when is None else series.loc[:when]
    return part.index[-1], float(part.iloc[-1])


# ---------------------------------------------------------------- monitor page

def monitor_summary(market: pd.DataFrame) -> None:
    """What the monitor shows now compared with the day before the Hormuz closure."""
    with st.container(key="panel_monitor_summary"):
        _monitor_summary(market)


def _monitor_summary(market: pd.DataFrame) -> None:
    st.markdown("#### What the monitor shows")
    try:
        brent, spread, crack = (_series(market, k) for k in ("brent", "brent_wti", "crack_321"))
        hormuz, spr = _series(market, "hormuz"), _series(market, "us_spr")
    except (KeyError, IndexError):
        st.markdown("Select all indicator groups to see the summary.")
        return
    before = "2026-02-27"
    (b_now_d, b_now), (_, b_then) = _at(brent), _at(brent, before)
    (_, s_now), (_, s_then) = _at(spread), _at(spread, before)
    (_, c_now), (_, c_then) = _at(crack), _at(crack, before)
    (h_now_d, h_now), (_, h_then) = _at(hormuz), _at(hormuz, before)
    (spr_d, spr_now), (_, spr_then) = _at(spr), _at(spr, before)
    peak_d, peak = brent.loc["2026-02-28":].idxmax(), brent.loc["2026-02-28":].max()
    z_spread = an.monitor_row(spread, None, an.WINDOWS["1 month"])["zscore"]
    st.markdown(
        f"- **Prices.** Brent was {b_now:,.2f} US dollars per barrel on {b_now_d:%d %b %Y}, against {b_then:,.2f} on "
        f"27 Feb 2026, the day before the Hormuz closure ({_pct(b_now, b_then):+.0f}%). Its highest daily value since "
        f"then was {peak:,.2f} on {peak_d:%d %b %Y}.\n"
        f"- **Spreads.** Brent's premium over WTI widened from {s_then:,.2f} to {s_now:,.2f} US dollars per barrel "
        f"(z-score {z_spread:+.1f} against the last three years), and the 3-2-1 crack spread from {c_then:,.2f} to "
        f"{c_now:,.2f}: seaborne crude and refined products are both priced far above U.S. inland crude.\n"
        f"- **Chokepoints.** The 7-day mean of tanker transits through the Strait of Hormuz was {h_now:,.1f} per day on "
        f"{h_now_d:%d %b %Y}, against {h_then:,.1f} before the closure.\n"
        f"- **Buffers.** U.S. Strategic Petroleum Reserve stocks were {spr_now:,.1f} million barrels on {spr_d:%d %b %Y}, "
        f"{spr_now - spr_then:+,.1f} million barrels since 27 Feb 2026.\n\n"
        "These are descriptions of the series side by side; the monitor does not estimate how much of any move "
        "each event caused.")


# ---------------------------------------------------------------- exposure page

def exposure_summary(monthly: pd.DataFrame) -> None:
    st.markdown("#### What the ranking shows")
    years = sorted(monthly["year"].unique())
    full = [y for y in years if monthly.loc[monthly["year"] == y, "date"].dt.month.nunique() == 12]
    year = 2025 if 2025 in full else full[-1]
    table = an.yearly_exposure(monthly, year)
    top2 = table.head(2)
    top5 = table.head(5)["volume_share"].sum()
    pre = an.yearly_exposure(monthly, 2023) if 2023 in years else table
    pre_h = pre.loc[pre["chokepoint"] == "Strait of Hormuz", "volume_share"].iloc[0]
    st.markdown(
        f"- In {year}, the last full year before the Hormuz closure, **{top2.iloc[0]['chokepoint']}** and "
        f"**{top2.iloc[1]['chokepoint']}** carried {top2['volume_share'].sum():.0f}% of the estimated tanker trade "
        f"volume counted at all 28 chokepoints, and the top five {top5:.0f}%. Tanker trade is concentrated in a few "
        "passages.\n"
        f"- The Strait of Hormuz alone had {pre_h:.0f}% of the 28-chokepoint tanker volume in 2023. EIA estimates that "
        "oil flows through the strait averaged 20 million barrels per day in 2024, about one-fifth of world "
        "petroleum liquids consumption, and that about 2.6 million barrels per day of Saudi and UAE pipeline "
        "capacity could be available to bypass it (Today in Energy, 16 June 2025).\n"
        "- Choose 2024 to see the Red Sea re-routing (Bab el-Mandeb and Suez red, Cape of Good Hope blue) and 2026 to "
        "see the Strait of Hormuz fall from the top of the ranking.\n\n"
        "PortWatch volumes are estimated cargo weights of all tanker types (crude, products, chemicals and gas), "
        "so they rank chokepoints by tanker traffic, not by barrels of crude oil.")


# ---------------------------------------------------------------- disruptions page

def disruption_summary(day: pd.DataFrame) -> None:
    st.markdown("#### What the transits show")
    names = set(day["chokepoint"])
    needed = {"Bab el-Mandeb Strait", "Cape of Good Hope", "Strait of Hormuz", "Malacca Strait", "Suez Canal"}
    if not needed <= names:
        st.markdown("The summary needs the full daily table.")
        return
    vol = "tanker_volume_t"
    bab = _pct(_mean(day, "Bab el-Mandeb Strait", RED_SEA_AFTER, vol), _mean(day, "Bab el-Mandeb Strait", RED_SEA_BASE, vol))
    suez = _pct(_mean(day, "Suez Canal", RED_SEA_AFTER, vol), _mean(day, "Suez Canal", RED_SEA_BASE, vol))
    cape = _pct(_mean(day, "Cape of Good Hope", RED_SEA_AFTER, vol), _mean(day, "Cape of Good Hope", RED_SEA_BASE, vol))
    h_before, h_after = _mean(day, "Strait of Hormuz", HORMUZ_BASE), _mean(day, "Strait of Hormuz", HORMUZ_AFTER)
    h_vol = _pct(_mean(day, "Strait of Hormuz", HORMUZ_AFTER, vol), _mean(day, "Strait of Hormuz", HORMUZ_BASE, vol))
    h_q2 = _pct(_mean(day, "Strait of Hormuz", ("2026-04-01", "2026-06-30"), vol),
                _mean(day, "Strait of Hormuz", HORMUZ_BASE, vol))
    malacca = _pct(_mean(day, "Malacca Strait", HORMUZ_AFTER, vol), _mean(day, "Malacca Strait", HORMUZ_BASE, vol))
    last = day["date"].max()
    st.markdown(
        f"- **Red Sea (January–August 2024 against January–October 2023).** Estimated tanker volume fell {abs(bab):.0f}% "
        f"through Bab el-Mandeb and {abs(suez):.0f}% through the Suez Canal, and rose {cape:.0f}% around the Cape of Good "
        "Hope: traffic moved to the longer route rather than stopping. EIA's estimates from a different source "
        "(Vortexa) point the same way: oil flows through Bab el-Mandeb fell from 8.7 million barrels per day in 2023 "
        "to 4.0 in January–August 2024, and flows around the Cape rose from 6.0 to 9.2 (Today in Energy, 11 October "
        "2024).\n"
        f"- **Strait of Hormuz (since 1 March 2026 against the 12 months before the closure).** Tanker transits fell "
        f"from {h_before:,.1f} to {h_after:,.1f} per day and estimated tanker volume by {abs(h_vol):.0f}% (data to "
        f"{last:%d %b %Y}). The strait has no alternative sea route; over the same months tanker volume through the "
        f"Malacca Strait, the busiest tanker chokepoint in these data, was {abs(malacca):.0f}% "
        f"{'lower' if malacca < 0 else 'higher'} than its own baseline.\n"
        f"- **Two sources, two sizes.** For April–June 2026 PortWatch shows tanker volume {abs(h_q2):.0f}% below the "
        "pre-closure baseline, while EIA estimates oil flows through the strait at 4.9 million barrels per day, "
        "against 21.6 in the last quarter of 2025, about 77% lower (Short-Term Energy Outlook, August 2026). Both "
        "show a collapse, but its size differs between measures; ship-tracking counts can miss vessels that switch off "
        "their transponders, so the PortWatch fall may be an upper bound.")


# ---------------------------------------------------------------- balance page

def balance_summary(history: pd.DataFrame, forecast: pd.DataFrame) -> None:
    st.markdown("#### What the balance shows")
    wide = an.balance_wide(history)
    if not {"papr_world", "patc_world", "BREPUUS", "t3_stchange_world"} <= set(wide.columns):
        st.markdown("The summary needs every series group.")
        return
    gulf = wide[[c for c in ["papr_sa", "papr_iz", "papr_tc", "papr_ku", "papr_IR", "papr_QA", "papr_ba"]
                 if c in wide]].sum(axis=1)
    feb = pd.Timestamp("2026-02-28")
    after = wide.loc["2026-03":]
    low_month = gulf.loc["2026-03":].idxmin()
    drawn = an.cumulative_draw(history, "2026-03")
    oecd = wide["pasc_oecd_t3"]
    last = wide.index[-1]
    def period_mean(code: str, first: str, last_month: str) -> float:
        return float(wide.loc[first:last_month, code].mean())

    draw_spring, brent_spring = period_mean("t3_stchange_world", "2026-03", "2026-05"), period_mean("BREPUUS", "2026-03", "2026-05")
    draw_summer, brent_summer = period_mean("t3_stchange_world", "2026-06", "2026-07"), period_mean("BREPUUS", "2026-06", "2026-07")
    draw_autumn, brent_autumn = period_mean("t3_stchange_world", "2026-08", "2026-09"), period_mean("BREPUUS", "2026-08", "2026-09")
    future = forecast.loc[forecast["series_id"] == "BREPUUS"].set_index("date")["value"]
    q4 = future.loc["2026-10":"2026-12"].mean() if len(future) else float("nan")
    y27 = future.loc["2027"].mean() if len(future.loc["2027":]) else float("nan")
    st.markdown(
        f"- **Supply.** EIA estimates that the seven Gulf producers inside the strait produced {gulf.loc[feb]:,.1f} "
        f"million barrels per day of liquids in February 2026 and {gulf.loc[low_month]:,.1f} in {low_month:%B %Y}, "
        f"{gulf.loc[low_month] - gulf.loc[feb]:+,.1f}. World production fell from {wide.loc[feb, 'papr_world']:,.1f} "
        f"to a low of {after['papr_world'].min():,.1f} ({after['papr_world'].idxmin():%B %Y}).\n"
        f"- **Demand and stocks.** World consumption fell less, from {wide.loc[feb, 'patc_world']:,.1f} to a low of "
        f"{after['patc_world'].min():,.1f}, so the gap came out of inventories: about {drawn:,.0f} million barrels "
        f"between March and {last:%B %Y}, after stocks had been rising by "
        f"{-wide.loc['2025-10':'2026-02', 't3_stchange_world'].mean():,.1f} million barrels per day in the five months "
        f"before. OECD commercial inventories were {oecd.loc[last]:,.0f} million barrels in {last:%B %Y}, "
        f"{oecd.loc[last] - oecd.loc[feb]:+,.0f} since February.\n"
        f"- **Prices.** Brent averaged {wide.loc[feb, 'BREPUUS']:,.2f} US dollars per barrel in February 2026. "
        f"In March–May, when draws averaged {draw_spring:,.1f} million barrels per day, it averaged {brent_spring:,.2f}; "
        f"in June–July, when draws averaged {draw_summer:,.1f} (EIA reports a US–Iran memorandum of understanding "
        f"in June, Short-Term Energy Outlook, August 2026), {brent_summer:,.2f}; and in August–September, with draws "
        f"of {draw_autumn:,.1f}, {brent_autumn:,.2f}. Higher prices came in the months with larger draws; the data "
        "show the two moving together, not which drove which.\n"
        f"- **Forecast (EIA, October 2026 edition).** Brent averages {q4:,.2f} in October–December 2026 and "
        f"{y27:,.2f} in 2027. EIA's forecast assumes oil flows from the Middle East stay constrained through the "
        "fourth quarter of 2026; it is a scenario from one model, not an observation.")


# ---------------------------------------------------------------- conclusion

def conclusion(day: pd.DataFrame, monthly: pd.DataFrame, history: pd.DataFrame, market: pd.DataFrame) -> None:
    vol = "tanker_volume_t"
    table = an.yearly_exposure(monthly, 2025 if 2025 in set(monthly["year"]) else int(monthly["year"].max()))
    top2 = table.head(2)
    bab = _pct(_mean(day, "Bab el-Mandeb Strait", RED_SEA_AFTER, vol), _mean(day, "Bab el-Mandeb Strait", RED_SEA_BASE, vol))
    cape = _pct(_mean(day, "Cape of Good Hope", RED_SEA_AFTER, vol), _mean(day, "Cape of Good Hope", RED_SEA_BASE, vol))
    hormuz = _pct(_mean(day, "Strait of Hormuz", HORMUZ_AFTER, vol), _mean(day, "Strait of Hormuz", HORMUZ_BASE, vol))
    drawn = an.cumulative_draw(history, "2026-03")
    spread = an.monitor_series(market, "brent_wti")
    brent = an.monitor_series(market, "brent")
    st.markdown("#### What the data show")
    st.markdown(
        f"1. **Exposure is concentrated.** {top2.iloc[0]['chokepoint']} and {top2.iloc[1]['chokepoint']} carried "
        f"{top2['volume_share'].sum():.0f}% of the tanker volume counted at 28 chokepoints in 2025.\n"
        f"2. **A route with an alternative bends; a route without one breaks.** After the Red Sea attacks, tanker volume "
        f"through Bab el-Mandeb fell {abs(bab):.0f}% while the Cape of Good Hope rose {cape:.0f}%: ships re-routed. After "
        f"28 February 2026 tanker volume through the Strait of Hormuz fell {abs(hormuz):.0f}%, and no other chokepoint "
        "rose to match it.\n"
        f"3. **The loss showed up in the balance.** EIA's estimates put the cumulative draw on world inventories at about "
        f"{drawn:,.0f} million barrels from March to September 2026, as Gulf output fell much more than consumption.\n"
        f"4. **Prices and spreads moved with it.** Brent peaked at {brent.loc['2026-02-28':].max():,.2f} US dollars per "
        f"barrel (daily, {brent.loc['2026-02-28':].idxmax():%d %b %Y}) and its premium over WTI reached "
        f"{spread.loc['2026-02-28':].max():,.2f}, far outside its range of the previous three years.")
    st.markdown("#### What the data cannot tell us")
    st.markdown(
        "- **Cause and size of effects.** The dashboard lines up events, flows, balances and prices in time. It does "
        "not separate the closure from other influences on prices (such as stock releases, demand or financial "
        "markets), so it does not estimate how much of any price move the closure caused.\n"
        "- **Barrels.** PortWatch measures ship crossings and estimated cargo weight of all tanker types; it is not a "
        "count of crude oil barrels, and it cannot see ships whose transponders are off.\n"
        "- **Recent months are estimates.** EIA revises its monthly balance estimates; the latest months of the "
        "October 2026 edition will change, and its forecasts are model scenarios.\n"
        "- **Bypass routes.** Pipeline exports that avoid the strait (to the Red Sea and the Gulf of Oman) are not "
        "in the chokepoint counts.")
    st.markdown("#### What this means for energy security analysts")
    st.markdown(
        "- Track the two passages that dominate tanker traffic, Malacca and Hormuz, together: after the Hormuz "
        "closure, tanker volume through Malacca also fell, so a Gulf disruption reaches beyond the Gulf.\n"
        "- For chokepoints with a sea-route alternative (Bab el-Mandeb, Suez), watch the alternative (the Cape) "
        "alongside the chokepoint; a fall at one with a rise at the other is re-routing, not lost supply.\n"
        "- For Hormuz, use the inventory draw and the Brent–WTI spread as the stress gauges: the monitor's z-scores "
        "show when they leave their usual range.\n"
        "- Check ship-tracking counts against barrel estimates (EIA, IEA) before quoting a size of disruption.")
    st.markdown("#### Next steps")
    st.markdown(
        "- Add tanker-type detail (crude versus product versus gas carriers) when PortWatch or another open source "
        "publishes it.\n- Add futures curves (the EIA series used here stopped after April 2024) to show how markets "
        "priced the expected length of the disruption.\n- Refresh monthly with each new STEO edition and compare "
        "EIA's forecasts with what is later observed.")


def methods_and_limitations() -> None:
    st.markdown("#### Methods")
    st.markdown(
        "- **Daily transits.** PortWatch counts a transit call when a ship crosses a chokepoint boundary (a ship is "
        "not counted again within 48 hours) and estimates each ship's cargo from its deadweight tonnage and draught. "
        "The daily table keeps the ten chokepoints with the most tanker volume from January 2019 to October 2023.\n"
        "- **Monthly and yearly means.** Monthly means of the daily values for all 28 chokepoints; yearly means weight "
        "each month by its number of days. Shares divide by the sum over the 28 chokepoints.\n"
        "- **Baselines.** A chokepoint's baseline is its mean daily value over January–October 2023 (before the Red "
        "Sea attacks) or over the 12 months to 27 February 2026 (before the Hormuz closure). The charts divide the "
        "7-day mean by that baseline (100 = baseline).\n"
        "- **Monitor.** Spreads: Brent minus WTI; 3-2-1 crack = (2 × gasoline + diesel − 3 × WTI) ÷ 3 with product "
        "prices converted from gallons to barrels (× 42). Change = latest value minus the last value on or before "
        "the start of the window. z-score = (latest − mean) ÷ standard deviation over the previous three years. "
        "52-week position = (latest − low) ÷ (high − low). Stocks are converted from thousand to million barrels.\n"
        "- **Balance.** EIA's world inventory net withdrawals equal consumption minus production; cumulative draws "
        "multiply each month's rate by its number of days.\n"
        "- **Events.** The dates marked on charts are those reported by EIA in the Short-Term Energy Outlook "
        "(April and August 2026) and Today in Energy (11 October 2024).")
