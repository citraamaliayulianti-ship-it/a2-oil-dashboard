from pathlib import Path

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from src import analysis as an
from src.data import DATA, OUTPUTS, read_dataset, validate


ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    "sections/1_exposure.py",
    "sections/2_disruptions.py",
    "sections/3_balance.py",
    "sections/4_conclusion.py",
    "sections/5_data.py",
]


def _app(monkeypatch, page: str | None = None) -> AppTest:
    monkeypatch.setenv("DASHBOARD_SAMPLE_MODE", "1")
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
    if page:
        app.switch_page(page).run()
    return app


def test_monitor_renders(monkeypatch) -> None:
    app = _app(monkeypatch)
    assert not app.exception
    assert any("How exposed is the oil market to chokepoint disruptions?" in item.value for item in app.markdown)


def test_every_page_renders(monkeypatch) -> None:
    for page in PAGES:
        app = _app(monkeypatch, page)
        assert not app.exception, page
        assert any("<h2" in item.value for item in app.markdown), page


def test_empty_selection_shows_message(monkeypatch) -> None:
    app = _app(monkeypatch, PAGES[1])
    app.multiselect(key="disruption_chokepoints").set_value([]).run()
    assert any("No chokepoints match" in item.value for item in app.info)


def test_samples_pass_validation() -> None:
    for dataset, (sample, _) in OUTPUTS.items():
        validate(read_dataset(DATA / sample, dataset), dataset)


def test_monitor_row_on_a_known_series() -> None:
    """A straight line from 0 to 99 over 100 days: change over a week is 7, the last value is the 52-week high."""
    dates = pd.date_range("2025-01-01", periods=100, freq="D")
    series = pd.Series(np.arange(100.0), index=dates)
    row = an.monitor_row(series, None, an.WINDOWS["1 week"])
    assert row["last"] == 99 and row["change"] == 7
    assert row["range_position"] == 1


def test_cumulative_draw_multiplies_by_days() -> None:
    """1 million barrels per day for March (31 days) and April (30 days) is 61 million barrels."""
    steo = pd.DataFrame({"date": pd.to_datetime(["2026-03-31", "2026-04-30"]), "series_id": "t3_stchange_world",
                         "value": [1.0, 1.0]})
    assert an.cumulative_draw(steo, "2026-03") == 61
