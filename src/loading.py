"""Load the dashboard's datasets once and share them across pages."""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from src.data import DATA, OUTPUTS, STRINGS


TITLE = "How exposed is the oil market to chokepoint disruptions?"
QUESTION = (
    "Which maritime chokepoints carry the most tanker trade, and how did the Red Sea attacks (from November 2023) "
    "and the closure of the Strait of Hormuz (from 28 February 2026) show up in tanker transits, the global "
    "supply-demand balance and prices?"
)
AUDIENCE = (
    "Energy security analysts in government agencies, international organisations and energy companies "
    "who monitor oil supply risk"
)


def sample_mode() -> bool:
    return os.getenv("DASHBOARD_SAMPLE_MODE", "0") == "1"


def data_path(dataset: str) -> str:
    """The bundled sample in offline mode (or before the pipeline has run), otherwise the processed file."""
    sample, processed = OUTPUTS[dataset]
    if sample_mode() or not (DATA / processed).exists():
        return str(DATA / sample)
    return str(DATA / processed)


@st.cache_data
def load(path: str, dataset: str) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={c: str for c in STRINGS[dataset]}, keep_default_na=False, na_values=[""],
                        parse_dates=["date"])
    return frame


def get(dataset: str) -> pd.DataFrame:
    return load(data_path(dataset), dataset)
