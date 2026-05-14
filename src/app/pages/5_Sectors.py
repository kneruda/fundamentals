"""Sector aggregate view — median multiples, growth, and margins per sector with drill-down."""

import streamlit as st

from src.app import queries
from src.app import sidebar as app_sidebar

st.set_page_config(page_title="Sectors", layout="wide")

_SUMMARY_LABELS = {
    "sector": "Sector",
    "n_tickers": "# Tickers",
    "median_pe": "Med P/E",
    "median_ps": "Med P/S",
    "median_pb": "Med P/B",
    "median_ev_ebitda": "Med EV/EBITDA",
    "median_fcf_yield_pct": "Med FCF Yield %",
    "median_rev_yoy_pct": "Med Rev YoY %",
    "median_eps_yoy_pct": "Med EPS YoY %",
    "median_div_yield_pct": "Med Div Yield %",
}

_CONSTITUENT_LABELS = {
    "ticker": "Ticker",
    "name": "Name",
    "sub_industry": "Sub-Industry",
    "price": "Price",
    "mktcap_b": "Mkt Cap ($B)",
    "pe_trailing": "P/E",
    "ps_trailing": "P/S",
    "pb_trailing": "P/B",
    "ev_ebitda_trailing": "EV/EBITDA",
    "fcf_yield_pct": "FCF Yield %",
    "rev_yoy_pct": "Rev YoY %",
    "eps_yoy_pct": "EPS YoY %",
    "div_yield_pct": "Div Yield %",
}


@st.cache_resource
def _get_con():
    return queries.open_warehouse()


@st.cache_data
def _sector_summary(_con, mtime: float):
    return queries.sector_summary(_con)


@st.cache_data
def _sector_constituents(_con, sector: str, mtime: float):
    return queries.sector_constituents(_con, sector)


def _fmt_float(df, exclude: list[str] | None = None):
    exclude = exclude or []
    display = df.copy()
    float_cols = display.select_dtypes(include="float").columns
    for col in float_cols:
        if col not in exclude:
            display[col] = display[col].map(lambda x: f"{x:.1f}" if x == x else "")
    return display


def main() -> None:
    con = _get_con()
    mtime = queries.warehouse_mtime()

    display_filter = app_sidebar.watchlist_selector(con)

    st.title("Sectors")
    st.caption(
        "Median trailing metrics by GIC sector (full universe). "
        "Drill-down constituents are filtered by active watchlist."
    )

    summary = _sector_summary(con, mtime)

    if summary.empty:
        st.info("No active tickers in the universe yet.")
        return

    # Summary table — always full universe medians
    summary_display = summary.rename(columns=_SUMMARY_LABELS)
    float_cols = summary_display.select_dtypes(include="float").columns
    for col in float_cols:
        summary_display[col] = summary_display[col].map(lambda x: f"{x:.1f}" if x == x else "")
    st.dataframe(summary_display, hide_index=True, width="stretch")

    st.markdown("---")
    st.subheader("Sector Drill-Down")

    sectors = summary["sector"].tolist()
    for sector in sectors:
        with st.expander(sector):
            constituents = _sector_constituents(con, sector, mtime)
            if display_filter is not None:
                constituents = constituents[constituents["ticker"].isin(display_filter)]
            if constituents.empty:
                st.info("No tickers in this sector.")
                continue
            display = constituents.rename(
                columns={c: _CONSTITUENT_LABELS.get(c, c) for c in constituents.columns}
            )
            float_cols = display.select_dtypes(include="float").columns
            for col in float_cols:
                display[col] = display[col].map(lambda x: f"{x:.1f}" if x == x else "")
            st.dataframe(display, hide_index=True, width="stretch")


main()
