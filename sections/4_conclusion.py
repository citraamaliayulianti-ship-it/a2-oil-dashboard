"""Conclusion: what the evidence shows, what it does not, and what it means for the audience."""

import streamlit as st

from src.loading import QUESTION, get
from src.overview import tape
from src.stories import PAGE_BALANCE, PAGE_DATA, conclusion, page_nav
from src.theme import footer, section_heading


market = get("market_day")
tape(market)
section_heading("Findings, limits and implications", lead=QUESTION, kicker="Conclusion")
with st.container(key="panel_conclusion"):
    conclusion(get("chokepoint_day"), get("chokepoint_month"), get("steo_history"), market)
page_nav(previous=(PAGE_BALANCE, "3. Balance and prices"), following=(PAGE_DATA, "Data and methods"))
footer()
