"""
Deep Dive page — single-ticker fundamentals, valuation history, and analyst view.
"""

import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from plotly.subplots import make_subplots

from src.app import queries
from src.ingest.fetch import fetch_news

load_dotenv()

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
def _statement(
    _con, ticker: str, stmt_type: str, period_type: str, depth: str, mtime: float
) -> pd.DataFrame:
    return queries.statement(_con, ticker, stmt_type, period_type=period_type, depth=depth)


@st.cache_data
def _news(ticker: str, hour_bucket: int) -> list:
    return fetch_news(ticker, limit=50)


@st.cache_data
def _technicals(_con, ticker: str, lookback_days: int | None, mtime: float) -> pd.DataFrame:
    return queries.deep_dive_technicals(_con, ticker, lookback_days)


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

_LOOKBACK_OPTIONS: dict[str, int | None] = {
    "6M": 182,
    "1Y": 365,
    "3Y": 1095,
    "5Y": 1825,
    "Max": None,
}

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
    tab_val, tab_prof, tab_analyst, tab_earn, tab_div, tab_stmts, tab_news, tab_tech = st.tabs(
        [
            "Valuation",
            "Profitability",
            "Analyst",
            "Earnings",
            "Dividends",
            "Statements",
            "News",
            "Technicals",
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

    # -------------------------------------------------------------------------
    # Technicals tab
    # -------------------------------------------------------------------------
    with tab_tech:
        range_key = st.radio(
            "Range", list(_LOOKBACK_OPTIONS.keys()), horizontal=True, index=1, key="tech_range"
        )
        lookback = _LOOKBACK_OPTIONS[range_key]

        tech = _technicals(con, ticker, lookback, mtime)

        if tech.empty:
            st.info("No technicals data available. Run rebuild.py to compute indicators.")
        else:
            latest = tech.iloc[-1]

            # --- Current signals summary ---
            rsi = latest.get("rsi_14")
            macd_hist = latest.get("macd_histogram")
            pct_sma200 = latest.get("pct_from_sma_200")
            pct_52h = latest.get("pct_from_52w_high")
            vol_ratio = latest.get("volume_ratio")
            ac = latest.get("adjusted_close")
            bb_mid = latest.get("bb_middle")
            bb_up = latest.get("bb_upper")
            bb_low_val = latest.get("bb_lower")

            def _bb_position(price, low_b, mid_b, high_b):
                if any(
                    v is None or (isinstance(v, float) and pd.isna(v))
                    for v in [price, low_b, mid_b, high_b]
                ):
                    return "—", "off"
                if price < mid_b:
                    return "Lower band", "inverse"
                if price > mid_b:
                    return "Upper band", "normal"
                return "Middle band", "off"

            bb_pos_label, bb_delta_color = _bb_position(ac, bb_low_val, bb_mid, bb_up)

            sig_c1, sig_c2, sig_c3, sig_c4, sig_c5, sig_c6 = st.columns(6)
            sig_c1.metric(
                "RSI(14)",
                _fmt(rsi, "{:.1f}"),
                (
                    "Oversold"
                    if rsi is not None and not pd.isna(rsi) and rsi < 30
                    else (
                        "Overbought"
                        if rsi is not None and not pd.isna(rsi) and rsi > 70
                        else "Neutral"
                    )
                ),
                delta_color=(
                    "inverse" if rsi is not None and not pd.isna(rsi) and rsi > 70 else "normal"
                ),
            )
            sig_c2.metric(
                "MACD Histogram",
                _fmt(macd_hist, "{:+.3f}"),
                (
                    "Bullish"
                    if macd_hist is not None and not pd.isna(macd_hist) and macd_hist > 0
                    else "Bearish"
                ),
                delta_color=(
                    "normal"
                    if macd_hist is not None and not pd.isna(macd_hist) and macd_hist > 0
                    else "inverse"
                ),
            )
            sig_c3.metric("BB Position", bb_pos_label, delta_color=bb_delta_color)
            sig_c4.metric("% from SMA200", _fmt(pct_sma200, "{:+.1%}"))
            sig_c5.metric("% from 52W High", _fmt(pct_52h, "{:+.1%}"))
            sig_c6.metric(
                "Vol Ratio",
                _fmt(vol_ratio, "{:.2f}×"),
                (
                    "Spike"
                    if vol_ratio is not None and not pd.isna(vol_ratio) and vol_ratio > 2.0
                    else None
                ),
                delta_color="normal",
            )

            st.divider()

            # --- Chart controls ---
            ctrl1, ctrl2 = st.columns(2)
            show_candles = ctrl1.checkbox("Candlestick", value=False, key="tech_candles")
            show_bb = ctrl2.checkbox("Bollinger Bands", value=False, key="tech_bb")

            # --- Plotly subplot chart ---
            fig = make_subplots(
                rows=4,
                cols=1,
                shared_xaxes=True,
                row_heights=[0.50, 0.15, 0.17, 0.18],
                vertical_spacing=0.02,
                subplot_titles=("Price", "Volume", "RSI(14)", "MACD"),
            )

            dates = tech["date"].astype(str)

            # Row 1: Price
            if show_candles and all(c in tech.columns for c in ["open", "high", "low", "close"]):
                fig.add_trace(
                    go.Candlestick(
                        x=dates,
                        open=tech["open"],
                        high=tech["high"],
                        low=tech["low"],
                        close=tech["close"],
                        name="Price",
                        showlegend=False,
                    ),
                    row=1,
                    col=1,
                )
            else:
                fig.add_trace(
                    go.Scatter(
                        x=dates,
                        y=tech["adjusted_close"],
                        name="Price",
                        mode="lines",
                        line=dict(color="#4a90e2", width=1.5),
                    ),
                    row=1,
                    col=1,
                )

            for col, label, color in [
                ("sma_20", "SMA20", "#f39c12"),
                ("sma_50", "SMA50", "#e74c3c"),
                ("sma_200", "SMA200", "#9b59b6"),
            ]:
                valid = tech.dropna(subset=[col])
                if not valid.empty:
                    fig.add_trace(
                        go.Scatter(
                            x=valid["date"].astype(str),
                            y=valid[col],
                            name=label,
                            mode="lines",
                            line=dict(color=color, width=1, dash="dot"),
                        ),
                        row=1,
                        col=1,
                    )

            if show_bb:
                for col, label, color in [
                    ("bb_upper", "BB Upper", "#95a5a6"),
                    ("bb_middle", "BB Middle", "#bdc3c7"),
                    ("bb_lower", "BB Lower", "#95a5a6"),
                ]:
                    valid = tech.dropna(subset=[col])
                    if not valid.empty:
                        fig.add_trace(
                            go.Scatter(
                                x=valid["date"].astype(str),
                                y=valid[col],
                                name=label,
                                mode="lines",
                                line=dict(color=color, width=1, dash="dash"),
                                showlegend=False,
                            ),
                            row=1,
                            col=1,
                        )

            # Row 2: Volume
            vol_colors = [
                "#2ecc71" if (c2 >= o2) else "#e74c3c"
                for c2, o2 in zip(
                    tech["close"].fillna(tech["adjusted_close"]),
                    tech["open"].fillna(tech["adjusted_close"]),
                    strict=True,
                )
            ]
            fig.add_trace(
                go.Bar(
                    x=dates,
                    y=tech["volume"],
                    name="Volume",
                    marker_color=vol_colors,
                    showlegend=False,
                ),
                row=2,
                col=1,
            )
            vol_sma_valid = tech.dropna(subset=["volume_sma_50"])
            if not vol_sma_valid.empty:
                fig.add_trace(
                    go.Scatter(
                        x=vol_sma_valid["date"].astype(str),
                        y=vol_sma_valid["volume_sma_50"],
                        name="Vol SMA50",
                        mode="lines",
                        line=dict(color="#f39c12", width=1),
                    ),
                    row=2,
                    col=1,
                )

            # Row 3: RSI
            rsi_valid = tech.dropna(subset=["rsi_14"])
            if not rsi_valid.empty:
                fig.add_trace(
                    go.Scatter(
                        x=rsi_valid["date"].astype(str),
                        y=rsi_valid["rsi_14"],
                        name="RSI(14)",
                        mode="lines",
                        line=dict(color="#3498db", width=1.5),
                    ),
                    row=3,
                    col=1,
                )
            fig.add_hline(y=70, line=dict(color="#e74c3c", width=1, dash="dash"), row=3, col=1)
            fig.add_hline(y=30, line=dict(color="#2ecc71", width=1, dash="dash"), row=3, col=1)
            fig.add_hrect(y0=70, y1=100, fillcolor="#e74c3c", opacity=0.05, row=3, col=1)
            fig.add_hrect(y0=0, y1=30, fillcolor="#2ecc71", opacity=0.05, row=3, col=1)

            # Row 4: MACD
            macd_valid = tech.dropna(subset=["macd", "macd_signal"])
            if not macd_valid.empty:
                fig.add_trace(
                    go.Scatter(
                        x=macd_valid["date"].astype(str),
                        y=macd_valid["macd"],
                        name="MACD",
                        mode="lines",
                        line=dict(color="#3498db", width=1.5),
                    ),
                    row=4,
                    col=1,
                )
                fig.add_trace(
                    go.Scatter(
                        x=macd_valid["date"].astype(str),
                        y=macd_valid["macd_signal"],
                        name="Signal",
                        mode="lines",
                        line=dict(color="#e74c3c", width=1),
                    ),
                    row=4,
                    col=1,
                )
            hist_valid = tech.dropna(subset=["macd_histogram"])
            if not hist_valid.empty:
                hist_colors = [
                    "#2ecc71" if v >= 0 else "#e74c3c" for v in hist_valid["macd_histogram"]
                ]
                fig.add_trace(
                    go.Bar(
                        x=hist_valid["date"].astype(str),
                        y=hist_valid["macd_histogram"],
                        name="Histogram",
                        marker_color=hist_colors,
                        showlegend=False,
                    ),
                    row=4,
                    col=1,
                )

            fig.update_layout(
                height=700,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis_rangeslider_visible=False,
                margin=dict(t=40, b=20),
            )
            fig.update_yaxes(fixedrange=False)
            st.plotly_chart(fig, width="stretch")

    # -------------------------------------------------------------------------
    # News tab
    # -------------------------------------------------------------------------
    with tab_news:
        hour_bucket = int(time.time() // 3600)
        try:
            articles = _news(ticker, hour_bucket)
        except Exception as exc:
            st.error(f"Could not load news: {exc}")
            articles = []

        if articles:
            for article in articles:
                title = article.get("title") or "Untitled"
                link = article.get("link", "")
                raw_date = article.get("date", "")
                date = raw_date[:10] if raw_date else ""
                content = article.get("content", "")
                snippet = (content[:400] + "...") if len(content) > 400 else content

                label = f"**{date}** — {title}" if date else title
                with st.expander(label):
                    if link:
                        st.markdown(f"[Read full article]({link})")
                    if snippet:
                        st.write(snippet)
        else:
            st.info("No recent news available.")


main()
