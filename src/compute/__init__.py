import duckdb

from .multiples import create_views as _multiples_views
from .size import create_views as _size_views
from .ttm import create_views as _ttm_views


def setup_views(con: duckdb.DuckDBPyConnection) -> None:
    """Create (or replace) all derived views. Idempotent.

    technicals_daily is a table (migration 007) recomputed from prices_daily;
    it is not a view and is not set up here.
    """
    _ttm_views(con)  # ttm_eps, ttm_revenue, ttm_ebitda, ttm_fcf
    _multiples_views(con)  # trailing_multiples_daily (depends on ttm_* views)
    _size_views(con)  # universe_size_latest — mktcap_b + adtv_20d_m
