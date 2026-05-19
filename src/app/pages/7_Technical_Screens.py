"""Technical indicator screens — filter the active universe by price-based signals."""

import streamlit as st

from src.app import queries
from src.app import sidebar as app_sidebar
from src.compute.technicals import recompute_technicals
from src.watchlist import create_watchlist

st.set_page_config(page_title="Technical Screens", layout="wide")

_SCREENS = {
    "Confirmed Uptrend": "confirmed_uptrend",
    "Confirmed Downtrend": "confirmed_downtrend",
    "Golden Cross (Recent)": "golden_cross_recent",
    "Death Cross (Recent)": "death_cross_recent",
    "RSI Oversold": "rsi_oversold",
    "RSI Overbought": "rsi_overbought",
    "MACD Bullish Crossover": "macd_bullish_crossover",
    "MACD Bearish Crossover": "macd_bearish_crossover",
    "Near 52W High": "near_52w_high",
    "Near 52W Low": "near_52w_low",
    "BB Squeeze": "bb_squeeze",
    "Volume Spike": "volume_spike",
}

_DESCRIPTIONS = {
    "confirmed_uptrend": "Price > SMA200 and SMA50 > SMA200 — all three aligned bullishly.",
    "confirmed_downtrend": "Price < SMA200 and SMA50 < SMA200 — all three aligned bearishly.",
    "golden_cross_recent": "SMA50 crossed above SMA200 within the lookback window.",
    "death_cross_recent": "SMA50 crossed below SMA200 within the lookback window.",
    "rsi_oversold": "RSI(14) below the oversold threshold — potential mean-reversion setup.",
    "rsi_overbought": "RSI(14) above the overbought threshold — potential exhaustion.",
    "macd_bullish_crossover": "MACD crossed above its signal line within the lookback window.",
    "macd_bearish_crossover": "MACD crossed below its signal line within the lookback window.",
    "near_52w_high": "Price within N% of its 52-week high.",
    "near_52w_low": "Price within N% of its 52-week low.",
    "bb_squeeze": "Bollinger Band width below its own 252-day Nth percentile — low-volatility compression.",
    "volume_spike": "Today's volume is N× the 50-day average — unusual activity.",
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


def _filters_confirmed_uptrend() -> dict:
    return {}


def _filters_confirmed_downtrend() -> dict:
    return {}


def _filters_golden_cross_recent() -> dict:
    days = st.sidebar.slider("Lookback (days)", 5, 90, 30, key="gc_days")
    return {"lookback_days": days}


def _filters_death_cross_recent() -> dict:
    days = st.sidebar.slider("Lookback (days)", 5, 90, 30, key="dc_days")
    return {"lookback_days": days}


def _filters_rsi_oversold() -> dict:
    threshold = st.sidebar.slider("RSI threshold", 10, 50, 30, key="rsi_os_thresh")
    return {"threshold": float(threshold)}


def _filters_rsi_overbought() -> dict:
    threshold = st.sidebar.slider("RSI threshold", 50, 90, 70, key="rsi_ob_thresh")
    return {"threshold": float(threshold)}


def _filters_macd_bullish_crossover() -> dict:
    days = st.sidebar.slider("Lookback (days)", 1, 20, 5, key="macd_bull_days")
    return {"lookback_days": days}


def _filters_macd_bearish_crossover() -> dict:
    days = st.sidebar.slider("Lookback (days)", 1, 20, 5, key="macd_bear_days")
    return {"lookback_days": days}


def _filters_near_52w_high() -> dict:
    pct = st.sidebar.slider("Within % of 52W high", 1, 20, 5, key="n52h_pct")
    return {"pct_threshold": float(pct)}


def _filters_near_52w_low() -> dict:
    pct = st.sidebar.slider("Within % of 52W low", 1, 20, 5, key="n52l_pct")
    return {"pct_threshold": float(pct)}


def _filters_bb_squeeze() -> dict:
    pct = st.sidebar.slider("BB width percentile threshold", 5, 50, 20, key="bb_pct")
    return {"percentile": float(pct)}


def _filters_volume_spike() -> dict:
    thresh = st.sidebar.slider(
        "Volume ratio threshold (×avg)", 1.5, 10.0, 2.0, step=0.5, key="vol_thresh"
    )
    return {"threshold": thresh}


_FILTER_RENDERERS = {
    "confirmed_uptrend": _filters_confirmed_uptrend,
    "confirmed_downtrend": _filters_confirmed_downtrend,
    "golden_cross_recent": _filters_golden_cross_recent,
    "death_cross_recent": _filters_death_cross_recent,
    "rsi_oversold": _filters_rsi_oversold,
    "rsi_overbought": _filters_rsi_overbought,
    "macd_bullish_crossover": _filters_macd_bullish_crossover,
    "macd_bearish_crossover": _filters_macd_bearish_crossover,
    "near_52w_high": _filters_near_52w_high,
    "near_52w_low": _filters_near_52w_low,
    "bb_squeeze": _filters_bb_squeeze,
    "volume_spike": _filters_volume_spike,
}

_COLUMN_LABELS = {
    "ticker": "Ticker",
    "name": "Name",
    "sector": "Sector",
    "adjusted_close": "Price",
    "sma_20": "SMA20",
    "sma_50": "SMA50",
    "sma_200": "SMA200",
    "rsi_14": "RSI14",
    "macd": "MACD",
    "macd_signal": "Signal",
    "macd_histogram": "Histogram",
    "bb_width": "BB Width",
    "pct_from_sma_50": "% from SMA50",
    "pct_from_sma_200": "% from SMA200",
    "pct_from_52w_high": "% from 52W High",
    "pct_from_52w_low": "% from 52W Low",
    "volume_ratio": "Vol Ratio",
    "mktcap_b": "Mkt Cap ($B)",
    "adtv_20d_m": "Avg Daily Vol ($M)",
}


def _fmt_df(df):
    display = df.rename(columns={c: _COLUMN_LABELS.get(c, c) for c in df.columns})
    float_cols = display.select_dtypes(include="float").columns
    fmt = {col: "{:.2f}" for col in float_cols}
    return display.style.format(fmt, na_rep="—")


def main() -> None:
    con = _get_con()

    display_filter = app_sidebar.watchlist_selector(con)

    st.title("Technical Screens")

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Data**")
    st.sidebar.caption("Recompute indicators from stored prices — no EODHD fetch.")
    if st.sidebar.button("Update Technicals", key="tech_recompute_btn"):
        with st.spinner("Recomputing technical indicators..."):
            recompute_technicals(con)
        st.success("Technicals updated.")
        st.rerun()

    screen_name = st.sidebar.selectbox("Screen", list(_SCREENS.keys()), key="tech_screen_sel")
    screen_key = _SCREENS[screen_name]

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Universe Size**")
    size_kwargs: dict = {}
    v = _optional_float("Min Mkt Cap ($B)", "ts_min_mktcap", min_val=0.1, max_val=5000.0, step=1.0)
    if v is not None:
        size_kwargs["min_mktcap_b"] = v
    v = _optional_float(
        "Min Avg Daily Vol ($M)", "ts_min_adtv", min_val=0.1, max_val=500.0, step=1.0
    )
    if v is not None:
        size_kwargs["min_adtv_m"] = v

    st.sidebar.markdown("---")
    st.sidebar.subheader("Filters")
    kwargs = {**size_kwargs, **_FILTER_RENDERERS[screen_key]()}

    st.subheader(screen_name)
    st.caption(_DESCRIPTIONS[screen_key])

    screen_fn = getattr(queries, f"screen_{screen_key}")
    df = screen_fn(con, display_filter=display_filter, **kwargs)

    if df.empty:
        st.info("No tickers match the current filters.")
    else:
        st.dataframe(_fmt_df(df), hide_index=True, width="stretch")

    st.caption(f"{len(df)} ticker(s) match.")

    if not df.empty:
        st.markdown("---")
        with st.expander("Save these results as a watchlist"):
            wl_name = st.text_input("Watchlist name", key="tech_save_wl_name")
            if st.button("Save", key="tech_save_wl_btn"):
                if not wl_name.strip():
                    st.error("Watchlist name is required.")
                else:
                    try:
                        tickers = df["ticker"].tolist()
                        create_watchlist(con, wl_name.strip(), tickers)
                        st.success(f"Saved '{wl_name}' with {len(tickers)} ticker(s).")
                    except Exception as exc:
                        st.error(str(exc))


main()
