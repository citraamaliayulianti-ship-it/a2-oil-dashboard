"""Question 1: which chokepoints carry the most tanker trade?"""

import streamlit as st

from src.loading import get
from src.overview import tape
from src.stories import HOME, PAGE_DISRUPTIONS, exposure_summary, page_nav
from src.theme import footer
from src.views import render_exposure


monthly = get("chokepoint_month")
tape(get("market_day"))

with st.container(key="chokepoint_exposure"):
    render_exposure(monthly, after=lambda: exposure_summary(monthly))
page_nav(previous=(HOME, "Monitor"), following=(PAGE_DISRUPTIONS, "2. Disruptions"))
footer()
