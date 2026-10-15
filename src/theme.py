"""The dashboard's look: a dark market-terminal style.

The layout borrows the conventions of trading-platform market monitors (a dark
background, a scrolling ticker of the latest values, a dense monitor table with
green and red changes, and a "cheat sheet" explaining each row) without copying
any platform's graphics. Every value shown in the ticker comes from this
dashboard's own data. Colours: page #131722, panels #1e222d, text #d1d4dc,
accent blue #2962ff; up #089981 and down #f23645 (checked for colour-vision
separation on the panel colour) are always paired with ▲ / ▼ so direction is never
shown by colour alone.
"""

from __future__ import annotations

import html

import altair as alt
import pandas as pd
import streamlit as st

PAGE_BG = "#131722"
PANEL = "#1e222d"
BORDER = "#2a2e39"
TEXT = "#d1d4dc"
MUTED = "#8f929b"           # 5.3:1 on the page, 4.6:1 on panels
BRIGHT = "#f0f3fa"
ACCENT = "#2962ff"
UP = "#089981"
DOWN = "#f23645"
GRID = "#2a2e39"

# Dark categorical slots (validated on the panel colour, adjacent pairs) and the diverging pair.
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9"]
COOL, WARM, NEUTRAL = "#3987e5", "#e66767", "#4a4e59"

PAGES = [  # (url path, label) for the footer
    ("exposure", "1. Exposure"),
    ("disruptions", "2. Disruptions"),
    ("balance", "3. Balance and prices"),
    ("conclusion", "Conclusion"),
    ("data", "Data and methods"),
]

_CSS = f"""
<style>
html, body, [class*="st-"] {{ font-family: -apple-system, BlinkMacSystemFont, "Trebuchet MS", "Segoe UI", Roboto,
  Ubuntu, sans-serif; }}
header[data-testid="stHeader"] {{ background: {PAGE_BG}; border-bottom: 1px solid {BORDER}; height: 3.4rem; }}
header[data-testid="stHeader"] a[data-testid="stTopNavLink"] {{ border-radius: 4px; }}
header[data-testid="stHeader"] a[data-testid="stTopNavLink"] * {{ color: {TEXT} !important; font-size: 0.86rem;
  font-weight: 600; }}
header[data-testid="stHeader"] a[data-testid="stTopNavLink"][aria-current="page"] {{
  background: rgba(41,98,255,0.18) !important; box-shadow: inset 0 -2px 0 {ACCENT}; }}
header[data-testid="stHeader"] a[data-testid="stTopNavLink"][aria-current="page"] * {{ color: {BRIGHT} !important; }}
.stMainBlockContainer {{ padding-top: 4.3rem; padding-bottom: 0; max-width: 1380px; }}
/* ticker tape */
.om-tape {{ overflow: hidden; white-space: nowrap; background: {PANEL}; border: 1px solid {BORDER};
  border-radius: 6px; margin: 0 0 1.1rem; font-variant-numeric: tabular-nums; }}
.om-tape-track {{ display: inline-block; padding: 0.55rem 0; animation: om-scroll 70s linear infinite; }}
.om-tape:hover .om-tape-track {{ animation-play-state: paused; }}
.om-tick {{ display: inline-block; margin: 0 1.6rem; font-size: 0.88rem; color: {TEXT}; }}
.om-tick b {{ color: {BRIGHT}; font-weight: 700; margin-right: 0.45rem; letter-spacing: 0.02em; }}
.om-up {{ color: {UP}; }} .om-down {{ color: {DOWN}; }} .om-flat {{ color: {MUTED}; }}
@keyframes om-scroll {{ from {{ transform: translateX(0); }} to {{ transform: translateX(-50%); }} }}
@media (prefers-reduced-motion: reduce) {{
  .om-tape {{ white-space: normal; }} .om-tape-track {{ animation: none; }}
  .om-tape-track span.om-copy {{ display: none; }}
}}
/* page header */
.om-hero {{ border: 1px solid {BORDER}; border-radius: 8px; padding: 1.4rem 1.6rem 1.2rem; margin-bottom: 1.2rem;
  background: linear-gradient(135deg, #1e222d 0%, #171b26 60%, #131722 100%); }}
.om-hero h1 {{ color: {BRIGHT}; font-size: 2.05rem; line-height: 1.2; margin: 0.15rem 0 0.6rem; padding: 0; }}
.om-hero p {{ color: {TEXT}; font-size: 1.02rem; line-height: 1.55; margin: 0 0 0.5rem; max-width: 980px; }}
.om-hero p.om-for {{ color: {MUTED}; font-size: 0.92rem; }}
.om-kicker {{ color: #5b8cff; text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.76rem;
  font-weight: 700; }}
h2.om-title {{ color: {BRIGHT}; font-size: 1.55rem; line-height: 1.3; margin: 0.2rem 0 0.4rem; padding: 0; }}
p.om-lead {{ color: {TEXT}; max-width: 1000px; line-height: 1.6; margin: 0 0 0.5rem; }}
p.om-meta {{ color: {MUTED}; font-size: 0.85rem; margin: 0; }}
.om-metas {{ margin: 0.2rem 0 0.8rem; }}
p.om-source {{ color: {MUTED}; font-size: 0.8rem; margin: -0.2rem 0 0.9rem; }}
/* panels and metrics */
div[class*="st-key-panel_"] {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px;
  padding: 1rem 1.1rem 0.4rem; margin: 0.25rem 0 0.7rem; }}
div[data-testid="stMetric"] {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px;
  padding: 0.7rem 0.95rem; }}
div[data-testid="stMetricValue"] {{ font-variant-numeric: tabular-nums; color: {BRIGHT}; }}
div[data-testid="stMetricLabel"] p {{ color: {MUTED}; font-size: 0.82rem; }}
div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] {{ height: 100%; }}
div[data-testid="stColumn"] div[data-testid="stLayoutWrapper"]:has(> div[class*="st-key-panel_"]) {{ flex: 1 1 auto; }}
div[data-testid="stColumn"] div[class*="st-key-panel_"] {{ height: 100%; }}
div.stElementContainer:has(> div[data-testid="stDownloadButton"]) {{ align-self: flex-end; }}
div[data-testid="stDownloadButton"] button {{ background: {ACCENT}; color: #ffffff; border: none; border-radius: 4px; }}
div[data-testid="stDownloadButton"] button:hover {{ background: #1e53e5; color: #ffffff; }}
/* cheat sheet and cards */
table.om-cheat {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
table.om-cheat th {{ text-align: left; color: {MUTED}; font-weight: 600; border-bottom: 1px solid {BORDER};
  padding: 0.45rem 0.6rem; }}
table.om-cheat td {{ border-bottom: 1px solid {BORDER}; padding: 0.5rem 0.6rem; vertical-align: top; color: {TEXT}; }}
table.om-cheat td:first-child {{ color: {BRIGHT}; font-weight: 600; white-space: nowrap; }}
.om-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 0.9rem; margin: 0.4rem 0 1rem; }}
.om-card {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; padding: 1rem 1.1rem; }}
.om-card a {{ color: {BRIGHT}; font-weight: 700; text-decoration: none; font-size: 1.02rem; }}
.om-card a:hover {{ color: #5b8cff; }}
.om-card p {{ color: {TEXT}; font-size: 0.9rem; line-height: 1.5; margin: 0.45rem 0 0; }}
.om-card .om-kicker {{ font-size: 0.7rem; }}
.om-footer {{ border-top: 1px solid {BORDER}; color: {MUTED}; text-align: center; padding: 1.2rem 1rem 1.6rem;
  margin-top: 2rem; font-size: 0.88rem; line-height: 2; }}
.om-footer a {{ color: {TEXT}; text-decoration: none; margin: 0 0.9rem; white-space: nowrap; }}
.om-footer a:hover {{ color: {BRIGHT}; }}
.stMainBlockContainer a {{ color: #5b8cff; }}
@media (max-width: 760px) {{
  .om-hero {{ padding: 1.1rem 1rem 0.9rem; }}
  .om-hero h1 {{ font-size: 1.55rem; }}
  h2.om-title {{ font-size: 1.3rem; }}
  div[class*="st-key-panel_"] {{ padding: 0.8rem 0.6rem 0.3rem; }}
  .om-tick {{ margin: 0 1rem; }}
}}
</style>
"""


def apply_style() -> None:
    """Page-wide style; called once from app.py so it applies to every page."""
    st.markdown(_CSS, unsafe_allow_html=True)


def _arrow(change: float) -> tuple[str, str]:
    if pd.isna(change) or abs(change) < 1e-9:
        return "■", "om-flat"
    return ("▲", "om-up") if change > 0 else ("▼", "om-down")


def ticker(items: list[tuple[str, str, float, str]]) -> None:
    """Scrolling tape: (symbol, value text, change, change text). The content is repeated once so
    the loop is seamless; screen readers get the first copy only."""
    cells = []
    for symbol, value, change, change_text in items:
        arrow, cls = _arrow(change)
        cells.append(f'<span class="om-tick"><b>{html.escape(symbol)}</b>{html.escape(value)} '
                     f'<span class="{cls}">{arrow} {html.escape(change_text)}</span></span>')
    body = "".join(cells)
    st.markdown(f'<div class="om-tape" role="marquee" aria-label="Latest values and one-week changes">'
                f'<div class="om-tape-track">{body}<span class="om-copy" aria-hidden="true">{body}</span></div></div>',
                unsafe_allow_html=True)


def hero(title: str, question: str, audience: str, note: str) -> None:
    st.markdown(
        f'<div class="om-hero"><div class="om-kicker">Oil market monitor</div><h1>{html.escape(title)}</h1>'
        f'<p>{html.escape(question)}</p><p class="om-for">For: {html.escape(audience)}. {html.escape(note)}</p></div>',
        unsafe_allow_html=True)


def section_heading(title: str, lead: list[str] | str = (), kicker: str | None = None, meta: list[str] = ()) -> None:
    """Title (a real <h2>), description paragraphs and small meta lines (unit, latest observation)."""
    paragraphs = [lead] if isinstance(lead, str) else list(lead)
    parts = [f'<div class="om-kicker">{html.escape(kicker)}</div>'] if kicker else []
    parts.append(f'<h2 class="om-title">{html.escape(title)}</h2>')
    parts += [f'<p class="om-lead">{html.escape(p)}</p>' for p in paragraphs]
    st.markdown("".join(parts), unsafe_allow_html=True)
    if meta:
        lines = "".join(f'<p class="om-meta">{html.escape(line)}</p>' for line in meta)
        st.markdown(f'<div class="om-metas">{lines}</div>', unsafe_allow_html=True)


def source_line(text: str) -> None:
    """Short source note under a chart."""
    st.markdown(f'<p class="om-source">{html.escape(text)}</p>', unsafe_allow_html=True)


def cards(items: list[tuple[str, str, str, str]]) -> None:
    """Link cards: (kicker, title, url path, description)."""
    body = "".join(
        f'<div class="om-card"><div class="om-kicker">{html.escape(k)}</div>'
        f'<a href="{path}" target="_self">{html.escape(t)}</a><p>{html.escape(d)}</p></div>'
        for k, t, path, d in items)
    st.markdown(f'<div class="om-cards">{body}</div>', unsafe_allow_html=True)


def footer() -> None:
    links = '<a href="./" target="_self">Monitor</a>' + "".join(
        f'<a href="{path}" target="_self">{html.escape(label)}</a>' for path, label in PAGES)
    st.markdown(f'<div class="om-footer">{links}<br>Data: U.S. Energy Information Administration; '
                f'IMF PortWatch (AIS data from the UN Global Platform). Calculations by this dashboard.</div>',
                unsafe_allow_html=True)


def style_chart(chart: alt.Chart) -> alt.Chart:
    """Dark chart chrome: hairline grid, muted axes, transparent background on the panel."""
    return (
        chart.configure_axis(gridColor=GRID, domainColor="#434651", tickColor="#434651", labelColor=MUTED,
                             titleColor=MUTED, titleFontWeight="normal", labelFontSize=11.5, titleFontSize=11.5)
        .configure_view(strokeWidth=0)
        .configure_legend(labelColor=TEXT, titleColor=MUTED, orient="top", labelFontSize=12, titleFontSize=11.5)
        .configure_title(anchor="start", fontSize=14.5, fontWeight=600, color=BRIGHT, offset=10,
                         subtitleColor=MUTED, subtitleFontSize=11.5)
        .configure_header(labelColor=TEXT, titleColor=MUTED, labelFontSize=12.5, labelFontWeight=600)
        .properties(background="transparent")
    )
