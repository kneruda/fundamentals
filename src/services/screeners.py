"""UI-neutral dispatch for the existing fundamental, forward, and technical screens."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import duckdb
import pandas as pd

from src.screens import forward_history, forward_vendor, technicals, trailing

FundamentalScreen = Literal[
    "absolute_valuation", "relative_history", "growth", "quality", "balance_sheet", "income"
]
ForwardScreen = Literal[
    "eps_revised_up",
    "net_upward_eps_revisions",
    "beat_and_revise",
    "consensus_rating_shift",
    "target_price_raised",
]
TechnicalScreen = Literal[
    "confirmed_uptrend",
    "confirmed_downtrend",
    "golden_cross_recent",
    "death_cross_recent",
    "rsi_oversold",
    "rsi_overbought",
    "macd_bullish_crossover",
    "macd_bearish_crossover",
    "near_52w_high",
    "near_52w_low",
    "bb_squeeze",
    "volume_spike",
]


@dataclass(frozen=True)
class ScreenResult:
    """A screen result independent of the transport and rendering layer."""

    rows: pd.DataFrame
    excluded_count: int = 0


_FUNDAMENTAL_SCREENS: dict[str, Callable[..., pd.DataFrame]] = {
    "absolute_valuation": trailing.screen_absolute_valuation,
    "relative_history": trailing.screen_relative_history,
    "growth": trailing.screen_growth,
    "quality": trailing.screen_quality,
    "balance_sheet": trailing.screen_balance_sheet,
    "income": trailing.screen_income,
}

_FORWARD_SCREENS: dict[str, Callable[..., Any]] = {
    "eps_revised_up": forward_vendor.screen_eps_revised_up,
    "net_upward_eps_revisions": forward_vendor.screen_net_upward_eps_revisions,
    "beat_and_revise": forward_vendor.screen_beat_and_revise,
    "consensus_rating_shift": forward_history.screen_consensus_rating_shift,
    "target_price_raised": forward_history.screen_target_price_raised,
}

_TECHNICAL_SCREENS: dict[str, Callable[..., pd.DataFrame]] = {
    "confirmed_uptrend": technicals.screen_confirmed_uptrend,
    "confirmed_downtrend": technicals.screen_confirmed_downtrend,
    "golden_cross_recent": technicals.screen_golden_cross_recent,
    "death_cross_recent": technicals.screen_death_cross_recent,
    "rsi_oversold": technicals.screen_rsi_oversold,
    "rsi_overbought": technicals.screen_rsi_overbought,
    "macd_bullish_crossover": technicals.screen_macd_bullish_crossover,
    "macd_bearish_crossover": technicals.screen_macd_bearish_crossover,
    "near_52w_high": technicals.screen_near_52w_high,
    "near_52w_low": technicals.screen_near_52w_low,
    "bb_squeeze": technicals.screen_bb_squeeze,
    "volume_spike": technicals.screen_volume_spike,
}


def _run_dataframe_screen(
    screens: dict[str, Callable[..., pd.DataFrame]],
    screen: str,
    con: duckdb.DuckDBPyConnection,
    display_filter: list[str] | None,
    filters: dict[str, Any],
) -> ScreenResult:
    try:
        fn = screens[screen]
    except KeyError as exc:
        raise ValueError(f"Unsupported screen: {screen}") from exc
    return ScreenResult(rows=fn(con, display_filter=display_filter, **filters))


def run_fundamental_screen(
    con: duckdb.DuckDBPyConnection,
    screen: FundamentalScreen,
    *,
    display_filter: list[str] | None = None,
    filters: dict[str, Any] | None = None,
) -> ScreenResult:
    return _run_dataframe_screen(_FUNDAMENTAL_SCREENS, screen, con, display_filter, filters or {})


def run_forward_screen(
    con: duckdb.DuckDBPyConnection,
    screen: ForwardScreen,
    *,
    display_filter: list[str] | None = None,
    filters: dict[str, Any] | None = None,
) -> ScreenResult:
    try:
        result = _FORWARD_SCREENS[screen](con, display_filter=display_filter, **(filters or {}))
    except KeyError as exc:
        raise ValueError(f"Unsupported screen: {screen}") from exc
    if isinstance(result, tuple):
        rows, excluded_count = result
        return ScreenResult(rows=rows, excluded_count=excluded_count)
    return ScreenResult(rows=result)


def run_technical_screen(
    con: duckdb.DuckDBPyConnection,
    screen: TechnicalScreen,
    *,
    display_filter: list[str] | None = None,
    filters: dict[str, Any] | None = None,
) -> ScreenResult:
    return _run_dataframe_screen(_TECHNICAL_SCREENS, screen, con, display_filter, filters or {})
