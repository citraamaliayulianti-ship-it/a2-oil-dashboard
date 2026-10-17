"""Question 2: how did the Red Sea attacks and the Hormuz closure show up in tanker transits?"""

import streamlit as st

from src.loading import get
from src.stories import PAGE_BALANCE, PAGE_EXPOSURE, disruption_summary, page_nav
from src.theme import footer
from src.views import render_disruption


day = get("chokepoint_day")

with st.container(key="chokepoint_disruption"):
    render_disruption(day, after=lambda: disruption_summary(day))
page_nav(previous=(PAGE_EXPOSURE, "1. Exposure"), following=(PAGE_BALANCE, "3. Balance and prices"))
footer()
