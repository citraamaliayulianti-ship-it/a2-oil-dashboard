"""Monitor page: the ticker, the question, links to the three questions, then the market monitor."""

import streamlit as st

from src.loading import AUDIENCE, QUESTION, TITLE, get
from src.overview import questions, tape
from src.stories import monitor_summary
from src.theme import footer, hero
from src.views import render_monitor


market = get("market_day")
tape(market)
hero(TITLE, QUESTION, AUDIENCE, "Data: EIA prices, stocks and outlook; IMF PortWatch ship transits, January 2019 to "
     "October 2026.")

questions()

with st.container(key="market_monitor"):
    render_monitor(market, after=lambda: monitor_summary(market))
footer()
