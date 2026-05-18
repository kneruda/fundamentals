import duckdb

from .multiples import create_views as _multiples_views
from .size import create_views as _size_views
from .technicals import create_views as _technicals_views
from .ttm import create_views as _ttm_views


def setup_views(con: duckdb.DuckDBPyConnection) -> None:
    """Create (or replace) all Phase 4 derived views. Idempotent."""
    _ttm_views(con)  # ttm_eps, ttm_revenue, ttm_ebitda, ttm_fcf
    _multiples_views(con)  # trailing_multiples_daily (depends on ttm_* views)
    _technicals_views(con)  # technicals_daily
    _size_views(con)  # universe_size_latest — mktcap_b + adtv_20d_m
