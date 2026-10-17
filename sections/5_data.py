"""Data and methods: every source, how each dataset is built, definitions and limitations."""

import streamlit as st

from src.loading import get
from src.overview import about_the_data, access_data
from src.stories import HOME, PAGE_CONCLUSION, methods_and_limitations, page_nav
from src.theme import footer, section_heading


section_heading("Data and methods", kicker="Documentation", lead=(
    "Where every number comes from, how the five datasets are built from the published files, and how to rebuild "
    "them."))
about_the_data({name: get(name) for name in ["chokepoint_day", "chokepoint_month", "market_day", "steo_history",
                                              "steo_forecast"]})
with st.container(key="panel_methods"):
    methods_and_limitations()
access_data()
page_nav(previous=(PAGE_CONCLUSION, "Conclusion"), following=(HOME, "Monitor"))
footer()
