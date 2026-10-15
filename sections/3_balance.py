"""Question 3: how did the global supply-demand balance, inventories and prices respond?"""

import streamlit as st

from src.loading import get
from src.overview import tape
from src.stories import PAGE_CONCLUSION, PAGE_DISRUPTIONS, balance_summary, page_nav
from src.theme import footer
from src.views import render_balance


history, forecast = get("steo_history"), get("steo_forecast")
tape(get("market_day"))

with st.container(key="balance_prices"):
    render_balance(history, forecast, after=lambda: balance_summary(history, forecast))
page_nav(previous=(PAGE_DISRUPTIONS, "2. Disruptions"), following=(PAGE_CONCLUSION, "Conclusion"))
footer()
