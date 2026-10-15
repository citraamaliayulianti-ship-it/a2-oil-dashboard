"""Entry point: page navigation for the dashboard.

Each page is its own file. The monitor opens the dashboard; pages 1-3 each answer one
part of the question; the conclusion draws them together; the last page documents the data.
"""

import streamlit as st

from src.stories import HOME, PAGE_BALANCE, PAGE_CONCLUSION, PAGE_DATA, PAGE_DISRUPTIONS, PAGE_EXPOSURE
from src.theme import apply_style


st.set_page_config(page_title="How exposed is the oil market to chokepoint disruptions?", layout="wide")

navigation = st.navigation(
    [
        st.Page(HOME, title="Monitor", default=True),
        st.Page(PAGE_EXPOSURE, title="1. Exposure", url_path="exposure"),
        st.Page(PAGE_DISRUPTIONS, title="2. Disruptions", url_path="disruptions"),
        st.Page(PAGE_BALANCE, title="3. Balance and prices", url_path="balance"),
        st.Page(PAGE_CONCLUSION, title="Conclusion", url_path="conclusion"),
        st.Page(PAGE_DATA, title="Data and methods", url_path="data"),
    ],
    position="top",
)
apply_style()
navigation.run()
