# How exposed is the oil market to chokepoint disruptions?

A Streamlit dashboard for **energy security analysts in government agencies, international organisations and
energy companies who monitor oil supply risk**. It asks:

> Which maritime chokepoints carry the most tanker trade, and how did the Red Sea attacks (from November 2023)
> and the closure of the Strait of Hormuz (from 28 February 2026) show up in tanker transits, the global
> supply-demand balance and prices?

## Pages

| Page | File | What it shows |
|---|---|---|
| Monitor | `home.py` | Ticker of the latest values; view `market_monitor`: a market-monitor table of 17 indicators (crude and product prices, two spreads, U.S. stocks, tanker transits at five chokepoints) with change over a chosen window, three-year z-score, 52-week range and one-year trend, replayable at the day before each event; a chart of any indicator; a cheat sheet; the three questions |
| 1. Exposure | `sections/1_exposure.py` | View `chokepoint_exposure`: map and ranking of the 28 PortWatch chokepoints by tanker trade volume or tanker transits in a chosen year, compared with January 2019–October 2023 |
| 2. Disruptions | `sections/2_disruptions.py` | View `chokepoint_disruption`: daily tanker transits (7-day mean) through selected chokepoints as a percentage of a pre-event baseline, with EIA event dates; monthly table |
| 3. Balance and prices | `sections/3_balance.py` | View `balance_prices`: EIA estimates of world production, consumption and inventory draws, Brent and WTI, and the output of the seven Gulf producers, with the EIA forecast shown separately |
| Conclusion | `sections/4_conclusion.py` | Findings, what the data cannot show, implications for the audience, next steps |
| Data and methods | `sections/5_data.py` | Datasets, every source with its URL and terms, how each table is built, how to rebuild the data |

`app.py` holds the navigation (`st.navigation`, menu at the top).

## Data

| Source | Publisher | Used for | Terms |
|---|---|---|---|
| Spot Prices for Crude Oil and Petroleum Products (daily) | U.S. Energy Information Administration | Brent, WTI, U.S. Gulf Coast gasoline, diesel and jet fuel; two spreads | Public domain |
| Weekly U.S. Stocks of Crude Oil and Petroleum Products | EIA | Commercial crude, SPR, gasoline, distillate | Public domain |
| Weekly Cushing, OK Ending Stocks excluding SPR of Crude Oil | EIA | Cushing stocks | Public domain |
| Short-Term Energy Outlook, October 2026 (`STEO_m.xlsx`) | EIA | World balance, inventories, monthly prices, Gulf producers; forecast to December 2027 | Public domain |
| Daily Chokepoints Data (28 chokepoints, from 1 January 2019) | IMF PortWatch (AIS data from the UN Global Platform) | Daily transit calls and estimated trade volume by vessel type | IMF terms: reuse with attribution and a note of changes |
| PortWatch Chokepoints Database | IMF PortWatch | Coordinates for the map | As above |
| Admin 0 – Countries, 1:110m | Natural Earth (via world-atlas 2.0.2) | Map outlines (`data/geo/`) | Public domain |

Event dates and quoted figures come from EIA's Short-Term Energy Outlook reports (April, August and October 2026)
and two Today in Energy articles (11 October 2024 on the Red Sea; 16 June 2025 on Hormuz). All files were
downloaded on 15 October 2026 (map outlines 13 October). The raw files (about 41 MB, mostly the 80 PortWatch JSON
pages) are not submitted: `python -m src.data --acquire` downloads them into `data/raw/` with the same URLs as
`dashboard.yml`.

Five tables are built (processed output, then offline sample):

| Dataset | One row is | Processed | Sample |
|---|---|---|---|
| `chokepoint_day` | one of the ten chokepoints with the most tanker trade on one day | `data/processed.csv` (from 2019) | `data/sample.csv` (from 1 January 2023) |
| `chokepoint_month` | one of the 28 chokepoints in one month | `data/processed_chokepoint_month.csv` | `data/sample_chokepoint_month.csv` (all rows) |
| `market_day` | one monitor indicator on one observation date | `data/processed_market_day.csv` (from 2019) | `data/sample_market_day.csv` (from 1 January 2020) |
| `steo_history` | one STEO series in one month, January 2022–September 2026 | `data/processed_steo_history.csv` | `data/sample_steo_history.csv` (all rows) |
| `steo_forecast` | one STEO series in one month, October 2026–December 2027 | `data/processed_steo_forecast.csv` | `data/sample_steo_forecast.csv` (all rows) |

Each sample is a faithful subset of its processed table (`--refresh-sample` writes it), large enough to run every
view, control and event comparison offline.

## Running

```bash
python -m venv .venv && source .venv/bin/activate      # Python 3.11
pip install -r requirements.txt
python -m src.data --acquire        # download the EIA workbooks and PortWatch pages into data/raw/
python -m src.data                  # rebuild and validate the five processed tables
streamlit run app.py
```

Offline: `DASHBOARD_SAMPLE_MODE=1 python -m src.data` rebuilds the processed tables from the samples, and
`DASHBOARD_SAMPLE_MODE=1 streamlit run app.py` runs the app from them. `python -m src.data --rank` reprints
the ranking behind the ten daily chokepoints. Tests: `pytest`.

## Code

`src/data.py` holds acquisition (EIA downloads; PortWatch pages of 1,000 rows through the ArcGIS query endpoint,
with timeouts and clear failure messages), one reader per published format, the five transformations and the
validation that stops the pipeline on any broken expectation. `src/analysis.py` holds the calculations (monitor
statistics, yearly exposure, baselines, cumulative stock draws) and the EIA event dates. Presentation lives in
`src/views.py` (the four assessed views), `src/stories.py` (page summaries computed from the data, the
conclusion and methods), `src/overview.py` (ticker, question cards, data documentation), `src/theme.py` (style)
and `src/loading.py` (cached loading).

## Methods in brief

- **Transits.** PortWatch counts a transit call when a ship crosses a chokepoint boundary (not again within 48
  hours) and estimates each ship's cargo from its deadweight tonnage and draught. Tanker volumes cover all
  tanker types and are kept in metric tons, never converted to barrels.
- **Exposure.** Yearly mean per day, weighting each month by its days; shares divide by the sum over 28
  chokepoints (a tanker crossing two chokepoints counts at both).
- **Disruptions.** The 7-day mean divided by the chokepoint's mean in a baseline period: January–October 2023
  (before the Red Sea attacks) or the 12 months to 27 February 2026 (before the Hormuz closure).
- **Monitor.** Brent minus WTI; 3-2-1 crack = (2 × gasoline + diesel − 3 × WTI) ÷ 3 with products converted to
  barrels (× 42). Change over a window, z-score against the trailing three years, position in the 52-week range.
- **Balance.** EIA's world net withdrawals equal consumption minus production; cumulative draws multiply each
  month by its days. Historical estimates and forecasts are separate datasets; forecasts are drawn dashed or pale.
- **No causal estimates.** Events are marked for context only.

## Design

The layout borrows the conventions of trading-platform market monitors and commodity dashboards: a dark page, a
scrolling ticker of the latest values (it stops for readers who prefer reduced motion), a dense monitor table with
green ▲ and red ▼ changes, a chart panel and a cheat sheet explaining each row. No platform graphics are copied;
every value comes from this dashboard's data. Up and down colours were checked for colour-vision separation on
the panel colour, and direction is always also shown by ▲ / ▼. The style lives in `src/theme.py` (CSS injected
once from `app.py`) and the page colours in `.streamlit/config.toml`.
