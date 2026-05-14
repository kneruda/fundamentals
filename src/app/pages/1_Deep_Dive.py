"""
Deep Dive page — single-ticker fundamentals, valuation history, and analyst view.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.app import queries

st.set_page_config(page_title="Deep Dive", layout="wide")


@st.cache_resource
def _get_con():
    return queries.open_warehouse()


@st.cache_data
def _active_tickers(_con, mtime: float) -> list[str]:
    return queries.active_tickers(_con)


@st.cache_data
def _header(_con, ticker: str, mtime: float) -> dict:
    return queries.ticker_header(_con, ticker)


@st.cache_data
def _val_history(_con, ticker: str, years: int, mtime: float) -> pd.DataFrame:
    return queries.valuation_history(_con, ticker, years)


@st.cache_data
def _quarterly_metrics(_con, ticker: str, mtime: float) -> pd.DataFrame:
    return queries.quarterly_metrics(_con, ticker)


@st.cache_data
def _analyst_snap(_con, ticker: str, mtime: float) -> dict | None:
    return queries.latest_analyst_snapshot(_con, ticker)


@st.cache_data
def _earnings(_con, ticker: str, mtime: float) -> pd.DataFrame:
    return queries.earnings_history(_con, ticker)


@st.cache_data
def _dividends_declared(_con, ticker: str, mtime: float) -> dict | None:
    return queries.latest_dividends(_con, ticker)


@st.cache_data
def _dividends_annual(_con, ticker: str, mtime: float) -> pd.DataFrame:
    return queries.dividend_annual_history(_con, ticker)


@st.cache_data
def _statement(_con, ticker: str, stmt_type: str, period_type: str, depth: str, mtime: float) -> pd.DataFrame:
    return queries.statement(_con, ticker, stmt_type, period_type=period_type, depth=depth)


def _fmt(val, fmt: str = "{:.2f}", fallback: str = "—") -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return fallback
    return fmt.format(val)


def _billions(val) -> str:
    return _fmt(val, "${:.1f}B")


def _pct(val) -> str:
    return _fmt(val, "{:+.2f}%")


def _statements_display(df: pd.DataFrame) -> pd.DataFrame:
    """Transpose statement DataFrame so periods are columns and metrics are rows."""
    if df.empty:
        return df
    df = df.copy()
    df["fiscal_period_end"] = df["fiscal_period_end"].astype(str)
    df = df.set_index("fiscal_period_end").T
    df.columns.name = None
    return df


_UNITS: dict[str, tuple[float, str]] = {
    "Billions": (1e9, "B"),
    "Millions": (1e6, "M"),
    "Thousands": (1e3, "K"),
    "Raw": (1.0, ""),
}


def _apply_units(df: pd.DataFrame, divisor: float, suffix: str) -> pd.DataFrame:
    """Divide all numeric cells by divisor and format with suffix."""
    def _fmt(v: object) -> str:
        if pd.isna(v) or not isinstance(v, (int, float)):
            return "—"
        scaled = v / divisor
        return f"${scaled:,.2f}{suffix}" if suffix else f"{scaled:,.0f}"

    return df.map(_fmt)


def main() -> None:
    con = _get_con()
    mtime = queries.warehouse_mtime()

    tickers = _active_tickers(con, mtime)
    if not tickers:
        st.warning("No active tickers. Add tickers on the Universe page.")
        return

    with st.sidebar:
        ticker = st.selectbox("Ticker", tickers)

    header = _header(con, ticker, mtime)
    if not header:
        st.error(f"No data found for {ticker}.")
        return

    # --- Header ---
    name = header.get("name") or ticker
    sector = header.get("sector") or "—"
    price = header.get("price")
    pct_1d = header.get("pct_1d")
    mktcap_b = header.get("mktcap_b")
    next_earnings = header.get("next_period_end")

    st.title(f"{name} ({ticker})")
    st.caption(f"{sector} | {header.get('industry') or '—'}")

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Price", _fmt(price, "${:.2f}"), _pct(pct_1d) if pct_1d is not None else None)
    col2.metric("Market Cap", _billions(mktcap_b))
    col3.metric("Sector", sector)
    col4.metric("Next Period End", str(next_earnings) if next_earnings else "—")
    col5.metric("Currency", header.get("currency") or "—")

    st.divider()

    # --- Tabs ---
    tab_val, tab_prof, tab_analyst, tab_earn, tab_div, tab_stmts = st.tabs(
        [
            "Valuation",
            "Profitability",
            "Analyst",
            "Earnings",
            "Dividends",
            "Statements",
        ]
    )

    # -------------------------------------------------------------------------
    # Valuation tab
    # -------------------------------------------------------------------------
    with tab_val:
        years = st.radio(
            "Period", [1, 3, 5], horizontal=True, index=2, format_func=lambda x: f"{x}Y"
        )

        hist = _val_history(con, ticker, years, mtime)
        stats = queries.valuation_stats(hist)

        if not hist.empty:
            fig = go.Figure()
            multiples = [
                ("pe_trailing", "P/E"),
                ("ps_trailing", "P/S"),
                ("pb_trailing", "P/B"),
                ("ev_ebitda_trailing", "EV/EBITDA"),
            ]
            for col, label in multiples:
                valid = hist.dropna(subset=[col])
                if not valid.empty:
                    fig.add_trace(
                        go.Scatter(
                            x=valid["date"],
                            y=valid[col],
                            name=label,
                            mode="lines",
                        )
                    )
            fig.update_layout(
                title="Trailing Multiples History",
                xaxis_title=None,
                yaxis_title="Multiple",
                legend=dict(orientation="h"),
                height=380,
            )
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No valuation history available for this period.")

        if not stats.empty:
            st.subheader("Current vs. Own History")
            stats_display = stats.copy()
            stats_display["current"] = stats_display["current"].apply(lambda x: _fmt(x, "{:.2f}"))
            stats_display["median"] = stats_display["median"].apply(lambda x: _fmt(x, "{:.2f}"))
            stats_display["pct_rank"] = stats_display["pct_rank"].apply(
                lambda x: _fmt(x, "{:.0f}th percentile") if pd.notna(x) else "—"
            )
            stats_display.columns = ["Multiple", "Current", f"{years}Y Median", "Percentile"]
            st.dataframe(stats_display, hide_index=True, width="stretch")

    # -------------------------------------------------------------------------
    # Profitability tab
    # -------------------------------------------------------------------------
    with tab_prof:
        qm = _quarterly_metrics(con, ticker, mtime)

        if not qm.empty:
            qm = qm.sort_values("fiscal_period_end")

            fig_rev = go.Figure()
            fig_rev.add_trace(
                go.Bar(
                    x=qm["fiscal_period_end"].astype(str),
                    y=qm["revenue_b"],
                    name="Revenue ($B)",
                )
            )
            fig_rev.update_layout(title="Quarterly Revenue ($B)", height=280, showlegend=False)
            st.plotly_chart(fig_rev, width="stretch")

            fig_margins = go.Figure()
            for col, label in [
                ("gross_margin_pct", "Gross"),
                ("operating_margin_pct", "Operating"),
                ("net_margin_pct", "Net"),
                ("fcf_margin_pct", "FCF"),
            ]:
                valid = qm.dropna(subset=[col])
                fig_margins.add_trace(
                    go.Scatter(
                        x=valid["fiscal_period_end"].astype(str),
                        y=valid[col],
                        name=label,
                        mode="lines+markers",
                    )
                )
            fig_margins.update_layout(
                title="Margins (%)",
                height=300,
                yaxis_ticksuffix="%",
                legend=dict(orientation="h"),
            )
            st.plotly_chart(fig_margins, width="stretch")

            fig_roe = go.Figure()
            valid_roe = qm.dropna(subset=["roe_pct"])
            fig_roe.add_trace(
                go.Bar(
                    x=valid_roe["fiscal_period_end"].astype(str),
                    y=valid_roe["roe_pct"],
                    name="ROE %",
                )
            )
            fig_roe.update_layout(title="Return on Equity (%)", height=250, showlegend=False)
            st.plotly_chart(fig_roe, width="stretch")
        else:
            st.info("No quarterly data available.")

    # -------------------------------------------------------------------------
    # Analyst tab
    # -------------------------------------------------------------------------
    with tab_analyst:
        snap = _analyst_snap(con, ticker, mtime)

        if snap:
            col_gauge, col_info = st.columns([1, 1])

            with col_gauge:
                rating = snap.get("consensus_rating")
                if rating is not None:
                    fig_gauge = go.Figure(
                        go.Indicator(
                            mode="gauge+number",
                            value=rating,
                            gauge={
                                "axis": {
                                    "range": [1, 5],
                                    "tickvals": [1, 2, 3, 4, 5],
                                    "ticktext": [
                                        "Strong Buy",
                                        "Buy",
                                        "Hold",
                                        "Sell",
                                        "Strong Sell",
                                    ],
                                },
                                "bar": {"color": "steelblue"},
                                "steps": [
                                    {"range": [1, 2], "color": "#2ecc71"},
                                    {"range": [2, 3], "color": "#a8d8a8"},
                                    {"range": [3, 4], "color": "#f39c12"},
                                    {"range": [4, 5], "color": "#e74c3c"},
                                ],
                            },
                            title={"text": "Consensus Rating"},
                        )
                    )
                    fig_gauge.update_layout(height=300)
                    st.plotly_chart(fig_gauge, width="stretch")

            with col_info:
                latest_price = header.get("price")
                target = snap.get("target_price")
                upside = (target / latest_price - 1) * 100 if target and latest_price else None
                st.metric("Consensus Target", _fmt(target, "${:.2f}"))
                st.metric("Implied Upside", _pct(upside) if upside is not None else "—")
                st.metric("Forward EPS (curr Y)", _fmt(snap.get("eps_est_curr_y"), "${:.2f}"))
                st.metric("Forward EPS (next Y)", _fmt(snap.get("eps_est_next_y"), "${:.2f}"))
                st.caption(f"As of {snap.get('snapshot_date')}")

            # Rating distribution bar
            counts = {
                "Strong Buy": snap.get("n_strong_buy") or 0,
                "Buy": snap.get("n_buy") or 0,
                "Hold": snap.get("n_hold") or 0,
                "Sell": snap.get("n_sell") or 0,
                "Strong Sell": snap.get("n_strong_sell") or 0,
            }
            total = sum(counts.values())
            if total > 0:
                colors = ["#2ecc71", "#a8d8a8", "#f39c12", "#e74c3c", "#c0392b"]
                fig_dist = go.Figure(
                    go.Bar(
                        x=list(counts.keys()),
                        y=list(counts.values()),
                        marker_color=colors,
                    )
                )
                fig_dist.update_layout(
                    title=f"Analyst Rating Distribution (n={total})",
                    height=280,
                    showlegend=False,
                )
                st.plotly_chart(fig_dist, width="stretch")
        else:
            st.info("No analyst snapshot data available.")

    # -------------------------------------------------------------------------
    # Earnings tab
    # -------------------------------------------------------------------------
    with tab_earn:
        earn = _earnings(con, ticker, mtime)

        if not earn.empty:
            earn = earn.sort_values("fiscal_period_end")
            earn["period"] = earn["fiscal_period_end"].astype(str)

            fig_surprise = go.Figure()
            colors = [
                "#2ecc71" if v >= 0 else "#e74c3c" for v in earn["surprise_percent"].fillna(0)
            ]
            fig_surprise.add_trace(
                go.Bar(
                    x=earn["period"],
                    y=earn["surprise_percent"],
                    name="EPS Surprise %",
                    marker_color=colors,
                )
            )
            fig_surprise.update_layout(
                title="EPS Surprise %",
                height=280,
                yaxis_ticksuffix="%",
                showlegend=False,
            )
            st.plotly_chart(fig_surprise, width="stretch")

            fig_react = go.Figure()
            react_colors = [
                "#2ecc71" if v >= 0 else "#e74c3c" for v in earn["next_day_return_pct"].fillna(0)
            ]
            fig_react.add_trace(
                go.Bar(
                    x=earn["period"],
                    y=earn["next_day_return_pct"],
                    name="Next-Day Return %",
                    marker_color=react_colors,
                )
            )
            fig_react.update_layout(
                title="Next-Day Price Reaction %",
                height=280,
                yaxis_ticksuffix="%",
                showlegend=False,
            )
            st.plotly_chart(fig_react, width="stretch")

            display = earn[
                ["period", "eps_estimate", "eps_actual", "surprise_percent", "next_day_return_pct"]
            ].copy()
            display.columns = ["Period", "EPS Est.", "EPS Actual", "Surprise %", "Next-Day %"]
            st.dataframe(
                display.style.format(
                    {
                        "EPS Est.": "${:.2f}",
                        "EPS Actual": "${:.2f}",
                        "Surprise %": "{:.1f}%",
                        "Next-Day %": "{:.2f}%",
                    },
                    na_rep="—",
                ),
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("No earnings history available.")

    # -------------------------------------------------------------------------
    # Dividends tab
    # -------------------------------------------------------------------------
    with tab_div:
        div = _dividends_declared(con, ticker, mtime)
        annual = _dividends_annual(con, ticker, mtime)

        if div:
            col_d1, col_d2, col_d3 = st.columns(3)
            col_d1.metric("Fwd Annual Rate", _fmt(div.get("fwd_div_rate"), "${:.2f}"))
            col_d2.metric("Fwd Yield", _fmt(div.get("fwd_div_yield"), "{:.2f}%"))
            col_d3.metric("Payout Ratio", _fmt(div.get("payout_ratio"), "{:.1f}%"))
            st.caption(
                f"Ex-date: {div.get('ex_date') or '—'} | Pay-date: {div.get('pay_date') or '—'}"
            )
        else:
            st.info("No dividend data available.")

        if not annual.empty:
            annual_sorted = annual.sort_values("year")
            fig_div = go.Figure(
                go.Bar(
                    x=annual_sorted["year"].astype(str),
                    y=annual_sorted["n_dividends"],
                    name="Dividends per Year",
                )
            )
            fig_div.update_layout(
                title="Dividends Paid per Year",
                height=260,
                showlegend=False,
            )
            st.plotly_chart(fig_div, width="stretch")

    # -------------------------------------------------------------------------
    # Statements tab
    # -------------------------------------------------------------------------
    with tab_stmts:
        ctrl1, ctrl2, ctrl3 = st.columns(3)
        with ctrl1:
            period_label = st.radio("Period", ["Quarterly", "Annual"], horizontal=True)
        with ctrl2:
            depth_label = st.radio("Depth", ["Summary", "Full"], horizontal=True)
        with ctrl3:
            units_label = st.radio("Units", list(_UNITS), horizontal=True)

        period_type = "quarterly" if period_label == "Quarterly" else "annual"
        depth = depth_label.lower()
        divisor, suffix = _UNITS[units_label]
        n_periods = 8 if period_type == "quarterly" else 5

        _IS_LABELS = {
            "total_revenue": "Revenue",
            "gross_profit": "Gross Profit",
            "ebitda": "EBITDA",
            "operating_income": "Operating Income",
            "net_income": "Net Income",
            "interest_expense": "Interest Expense",
            "research_development": "R&D",
        }
        _BS_LABELS = {
            "cash_and_short_term_investments": "Cash & ST Investments",
            "total_current_assets": "Total Current Assets",
            "total_assets": "Total Assets",
            "total_current_liabilities": "Total Current Liabilities",
            "long_term_debt_total": "Long-Term Debt",
            "short_term_debt": "Short-Term Debt",
            "total_stockholder_equity": "Stockholder Equity",
            "net_debt": "Net Debt (computed)",
        }
        _CF_LABELS = {
            "total_cash_from_operating_activities": "Operating CF",
            "capital_expenditures": "CapEx",
            "free_cash_flow": "Free Cash Flow",
            "dividends_paid": "Dividends Paid",
            "net_borrowings": "Net Borrowings",
        }

        sub_is, sub_bs, sub_cf = st.tabs(["Income Statement", "Balance Sheet", "Cash Flow"])

        with sub_is:
            is_df = _statement(con, ticker, "income_statement", period_type, depth, mtime)
            if not is_df.empty:
                display = _statements_display(is_df)
                display = _apply_units(display, divisor, suffix)
                if depth == "summary":
                    display.index = [_IS_LABELS.get(i, i) for i in display.index]
                st.dataframe(display, width="stretch")
            else:
                st.info(f"No {period_label.lower()} income statement data.")

        with sub_bs:
            bs_df = _statement(con, ticker, "balance_sheet", period_type, depth, mtime)
            if not bs_df.empty:
                display = _statements_display(bs_df)
                display = _apply_units(display, divisor, suffix)
                if depth == "summary":
                    display.index = [_BS_LABELS.get(i, i) for i in display.index]
                st.dataframe(display, width="stretch")
            else:
                st.info(f"No {period_label.lower()} balance sheet data.")

        with sub_cf:
            cf_df = _statement(con, ticker, "cash_flow", period_type, depth, mtime)
            if not cf_df.empty:
                display = _statements_display(cf_df)
                display = _apply_units(display, divisor, suffix)
                if depth == "summary":
                    display.index = [_CF_LABELS.get(i, i) for i in display.index]
                st.dataframe(display, width="stretch")
            else:
                st.info(f"No {period_label.lower()} cash flow data.")


main()
