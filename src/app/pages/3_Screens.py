"""Trailing fundamental screens — filter the active universe by configurable criteria."""

import streamlit as st

from src.app import queries

st.set_page_config(page_title="Screens", layout="wide")

_SCREENS = {
    "Absolute Valuation": "absolute_valuation",
    "Relative to Own History": "relative_history",
    "Growth": "growth",
    "Quality": "quality",
    "Balance Sheet Strength": "balance_sheet",
    "Income": "income",
}

_DESCRIPTIONS = {
    "absolute_valuation": "Filter by absolute multiple ceilings and FCF yield floor.",
    "relative_history": (
        "Filter by how cheap each ticker is vs. its own historical multiple distribution. "
        "Rank 0 = historical low, 100 = historical high."
    ),
    "growth": "Filter by revenue/EPS growth thresholds, with optional acceleration check.",
    "quality": "Filter by returns, margins, and FCF conversion.",
    "balance_sheet": "Filter by leverage, interest coverage, and current ratio.",
    "income": "Filter by dividend yield, payout ratio, and years of dividend history.",
}


@st.cache_resource
def _get_con():
    return queries.open_warehouse()


def _optional_float(
    label: str, key: str, *, min_val: float, max_val: float, step: float, fmt: str = "%.1f"
) -> float | None:
    enabled = st.sidebar.checkbox(label, key=f"chk_{key}")
    if enabled:
        return st.sidebar.number_input(
            label,
            min_value=min_val,
            max_value=max_val,
            step=step,
            format=fmt,
            key=f"val_{key}",
            label_visibility="collapsed",
        )
    return None


def _filters_absolute_valuation() -> dict:
    st.sidebar.markdown("**Multiple ceilings**")
    kwargs: dict = {}
    v = _optional_float("Max P/E", "max_pe", min_val=1.0, max_val=200.0, step=1.0)
    if v is not None:
        kwargs["max_pe"] = v
    v = _optional_float("Max P/S", "max_ps", min_val=0.1, max_val=50.0, step=0.5)
    if v is not None:
        kwargs["max_ps"] = v
    v = _optional_float("Max P/B", "max_pb", min_val=0.1, max_val=50.0, step=0.5)
    if v is not None:
        kwargs["max_pb"] = v
    v = _optional_float("Max EV/EBITDA", "max_ev", min_val=1.0, max_val=100.0, step=1.0)
    if v is not None:
        kwargs["max_ev_ebitda"] = v
    st.sidebar.markdown("**FCF yield floor (%)**")
    v = _optional_float("Min FCF Yield %", "min_fcf", min_val=0.1, max_val=20.0, step=0.5)
    if v is not None:
        kwargs["min_fcf_yield"] = v
    return kwargs


def _filters_relative_history() -> dict:
    kwargs: dict = {}
    kwargs["years"] = st.sidebar.slider("History window (years)", 1, 10, 5, key="rel_years")
    st.sidebar.markdown("**Max percentile rank (lower = historically cheap)**")
    v = _optional_float("Max P/E rank %", "max_pe_rank", min_val=1.0, max_val=99.0, step=5.0)
    if v is not None:
        kwargs["max_pe_rank"] = v
    v = _optional_float("Max EV/EBITDA rank %", "max_ev_rank", min_val=1.0, max_val=99.0, step=5.0)
    if v is not None:
        kwargs["max_ev_rank"] = v
    v = _optional_float("Max P/S rank %", "max_ps_rank", min_val=1.0, max_val=99.0, step=5.0)
    if v is not None:
        kwargs["max_ps_rank"] = v
    min_days = st.sidebar.number_input(
        "Min history days", min_value=0, max_value=2000, value=252, step=63, key="min_hist"
    )
    if min_days > 0:
        kwargs["min_history_days"] = int(min_days)
    return kwargs


def _filters_growth() -> dict:
    kwargs: dict = {}
    st.sidebar.markdown("**YoY growth floors (%)**")
    v = _optional_float("Min revenue YoY %", "min_rev", min_val=-50.0, max_val=200.0, step=5.0)
    if v is not None:
        kwargs["min_rev_yoy"] = v
    v = _optional_float("Min EPS YoY %", "min_eps", min_val=-50.0, max_val=200.0, step=5.0)
    if v is not None:
        kwargs["min_eps_yoy"] = v
    if st.sidebar.checkbox(
        "Require revenue acceleration (4 consecutive quarters)", key="chk_accel"
    ):
        kwargs["require_acceleration"] = True
    return kwargs


def _filters_quality() -> dict:
    kwargs: dict = {}
    st.sidebar.markdown("**Return thresholds (%)**")
    v = _optional_float("Min ROE %", "min_roe", min_val=0.0, max_val=200.0, step=5.0)
    if v is not None:
        kwargs["min_roe"] = v
    v = _optional_float("Min ROIC %", "min_roic", min_val=0.0, max_val=100.0, step=5.0)
    if v is not None:
        kwargs["min_roic"] = v
    st.sidebar.markdown("**Margin floors (%)**")
    v = _optional_float("Min Gross Margin %", "min_gm", min_val=0.0, max_val=100.0, step=5.0)
    if v is not None:
        kwargs["min_gross_margin"] = v
    st.sidebar.markdown("**FCF conversion floor (%)**")
    v = _optional_float(
        "Min FCF Conversion %", "min_fcf_conv", min_val=0.0, max_val=300.0, step=10.0
    )
    if v is not None:
        kwargs["min_fcf_conversion"] = v
    if st.sidebar.checkbox("Require gross margin expansion (vs. 4Q ago)", key="chk_mexp"):
        kwargs["require_margin_expansion"] = True
    return kwargs


def _filters_balance_sheet() -> dict:
    kwargs: dict = {}
    v = _optional_float(
        "Max Net Debt / EBITDA", "max_nd_ebi", min_val=-10.0, max_val=20.0, step=0.5
    )
    if v is not None:
        kwargs["max_net_debt_ebitda"] = v
    v = _optional_float("Min Interest Coverage", "min_ic", min_val=0.0, max_val=100.0, step=1.0)
    if v is not None:
        kwargs["min_interest_coverage"] = v
    v = _optional_float(
        "Min Current Ratio", "min_cr", min_val=0.0, max_val=10.0, step=0.25, fmt="%.2f"
    )
    if v is not None:
        kwargs["min_current_ratio"] = v
    return kwargs


def _filters_income() -> dict:
    kwargs: dict = {}
    v = _optional_float("Min Dividend Yield %", "min_yield", min_val=0.1, max_val=20.0, step=0.5)
    if v is not None:
        kwargs["min_yield"] = v
    v = _optional_float("Max Payout Ratio %", "max_payout", min_val=1.0, max_val=200.0, step=5.0)
    if v is not None:
        kwargs["max_payout"] = v
    if st.sidebar.checkbox("Min years of dividend history", key="chk_dyrs"):
        n = st.sidebar.number_input("Years", min_value=1, max_value=50, value=5, key="val_dyrs")
        kwargs["min_div_years"] = int(n)
    return kwargs


_FILTER_RENDERERS = {
    "absolute_valuation": _filters_absolute_valuation,
    "relative_history": _filters_relative_history,
    "growth": _filters_growth,
    "quality": _filters_quality,
    "balance_sheet": _filters_balance_sheet,
    "income": _filters_income,
}

_COLUMN_LABELS = {
    "ticker": "Ticker",
    "name": "Name",
    "sector": "Sector",
    "pe_trailing": "P/E",
    "ps_trailing": "P/S",
    "pb_trailing": "P/B",
    "ev_ebitda_trailing": "EV/EBITDA",
    "fcf_yield_pct": "FCF Yield %",
    "pe_pct_rank": "P/E Rank %",
    "ev_pct_rank": "EV Rank %",
    "ps_pct_rank": "P/S Rank %",
    "history_days": "History Days",
    "rev_yoy_pct": "Rev YoY %",
    "eps_yoy_pct": "EPS YoY %",
    "g1_pct": "Q-1 Rev YoY %",
    "g2_pct": "Q-2 Rev YoY %",
    "g3_pct": "Q-3 Rev YoY %",
    "g4_pct": "Q-4 Rev YoY %",
    "is_accelerating": "Accelerating",
    "roe_pct": "ROE %",
    "roic_pct": "ROIC %",
    "gross_margin_pct": "Gross Margin %",
    "op_margin_pct": "Op Margin %",
    "fcf_conversion_pct": "FCF Conv %",
    "margin_expanding": "Margin Expanding",
    "net_debt_b": "Net Debt ($B)",
    "net_debt_ebitda": "ND/EBITDA",
    "interest_coverage": "Int Coverage",
    "current_ratio": "Current Ratio",
    "div_yield_pct": "Yield %",
    "payout_ratio_pct": "Payout %",
    "n_div_years": "Div Years",
}


def _fmt_df(df):
    display = df.rename(columns={c: _COLUMN_LABELS.get(c, c) for c in df.columns})
    float_cols = display.select_dtypes(include="float").columns
    for col in float_cols:
        display[col] = display[col].map(lambda x: f"{x:.1f}" if x == x else "")
    return display


def main() -> None:
    con = _get_con()

    st.title("Screens")

    screen_name = st.sidebar.selectbox("Screen", list(_SCREENS.keys()), key="screen_sel")
    screen_key = _SCREENS[screen_name]

    st.sidebar.markdown("---")
    st.sidebar.subheader("Filters")
    kwargs = _FILTER_RENDERERS[screen_key]()

    st.subheader(screen_name)
    st.caption(_DESCRIPTIONS[screen_key])

    screen_fn = getattr(queries, f"screen_{screen_key}")
    df = screen_fn(con, **kwargs)

    if df.empty:
        st.info("No tickers match the current filters.")
    else:
        st.dataframe(_fmt_df(df), hide_index=True, width="stretch")

    st.caption(f"{len(df)} ticker(s) match.")


main()
