# FastAPI + React migration: Phase 1 audit and plan

## Scope and compatibility boundary

This is a presentation-layer migration.  The DuckDB schema, migrations,
ingestion pipeline, `src/compute`, and `src/screens` remain authoritative and
are not changed.  Streamlit remains a supported UI through the extraction and
backend phases.  FastAPI routes are adapters: they validate input, open a
connection through the existing warehouse helper, call an application service,
and serialize the result.  They do not contain SQL, calculation, or ingestion
logic.

The new frontend will live in `frontend/`, be built with React + TypeScript and
Vite, use AG Grid for tabular results, ECharts for charts, and consume a
generated OpenAPI type client.

## Current Streamlit surface

The common sidebar contains a watchlist selector.  It uses
`src.app.queries.list_watchlists()` and `get_watchlist_membership()`, stores
the selected ID in `st.session_state["active_watchlist_id"]`, and returns the
member tickers as the display filter.  It applies to Home, Screens, Sectors,
Forward Screens, and Technical Screens.  Sector medians intentionally remain
full-universe even when this display filter is active.

| Page | Controls and actions | Tables, charts, and data source |
| --- | --- | --- |
| Home (`Home.py`) | Common watchlist selector. | Warehouse timestamp; universe summary table with conditional colour scales. `queries.universe_summary()` supplies prices, multiples, growth, dividends, consensus, and target upside. |
| Deep Dive (`1_Deep_Dive.py`) | Active-ticker selector; valuation period (1/3/5 years); statements period (quarterly/annual), depth (summary/full), units; technical range, candlestick, and Bollinger Band toggles. | Header metrics from `ticker_header`. Valuation multi-line chart plus current/median/percentile table from `valuation_history` and `valuation_stats`. Revenue bar, margins line, and ROE bar charts from `quarterly_metrics`. Consensus gauge, target/EPS metrics, and rating-distribution bar from `latest_analyst_snapshot`. EPS-surprise and next-day-reaction bars plus earnings table from `earnings_history`. Dividend metrics and annual-count bar from `latest_dividends` / `dividend_annual_history`. Three statement tables from `statement`. Four-panel price/volume/RSI/MACD chart plus signal metrics from `deep_dive_technicals`. News expanders from `fetch_news`. |
| Universe (`2_Universe.py`) | Add ticker + notes; bulk paste/upload; refresh all; per-ticker drill/remove/refresh; re-add inactive tickers. Drill dialog has price page size, date bounds, page number, and quarterly/annual statement controls. | Current universe table from `universe_management_list`; analyst-coverage table from `snapshot_coverage`; price table and total from `prices_page` / `prices_count`; three recent-fundamentals tables from `fundamentals_recent`. Mutations call `universe.add_ticker`, `remove_ticker`, and `refresh_universe_threaded`. |
| Fundamental Screens (`3_Screens.py`) | Screen selector; optional market-cap and liquidity floors; screen-specific numeric/boolean filters; save-result-as-watchlist form. | One sortable result table from one of six `queries.screen_*` wrappers: absolute valuation, relative history, growth, quality, balance sheet strength, or income. Each delegates to `src/screens/trailing.py`. |
| Watchlists (`4_Watchlists.py`) | Create with name/description/paste/upload; edit-members dialog with paste/upload; delete; common active-watchlist selector. | Watchlist cards/expanders and member list from `list_watchlists` / `get_membership`; mutations call `create_watchlist`, `replace_membership`, and `delete_watchlist`. |
| Sectors (`5_Sectors.py`) | Common watchlist selector; sector expanders. | Full-universe sector-median table from `sector_summary`; per-sector constituent tables from `sector_constituents`, display-filtered client-side by active watchlist. |
| Forward Screens (`6_Forward_Screens.py`) | Vendor screen selector; EPS-revision lookback/delta/period, net-revision lookback/minimum/period, or beat-and-raise thresholds. Snapshot-history screen selector; rating-shift or target-price lookback/threshold. Each result can be saved as a watchlist. | Five result tables: `screen_eps_revised_up`, `screen_net_upward_eps_revisions`, `screen_beat_and_revise` in `src/screens/forward_vendor.py`; `screen_consensus_rating_shift` and `screen_target_price_raised` in `src/screens/forward_history.py`, including excluded-count metadata. |
| Technical Screens (`7_Technical_Screens.py`) | Recompute technicals; screen selector; optional market-cap/liquidity floors; per-screen lookback/threshold controls; save-result-as-watchlist. | One result table from one of twelve `queries.screen_*` wrappers over `src/screens/technicals.py`: up/downtrend, golden/death cross, RSI overbought/oversold, MACD bull/bear crossover, near 52-week high/low, BB squeeze, or volume spike. Recompute calls existing `recompute_technicals()`. |

## Streamlit coupling and extraction plan

The core calculation modules are already Streamlit-free: `src/screens/*`,
`src/compute/*`, `src/universe.py`, `src/watchlist.py`, and ingestion modules.
The remaining coupling is localized but important:

| Coupling | Current location | Phase 2 extraction |
| --- | --- | --- |
| Warehouse path/connection and query facade | `src/app/queries.py` | Move the non-UI query functions to `src/services/queries.py` (or retain an import-compatible forwarding module); add one Streamlit-free `warehouse` dependency factory. Both UIs call it. |
| Page-level query composition | Home, Deep Dive, Universe, Sectors | Create service functions per resource (`dashboard`, `company`, `universe`, `sectors`) that return plain dicts/dataframes; retain `queries.py` as a compatibility facade for Streamlit. |
| Filter dictionaries built by `st.sidebar` | Screens and Technical Screens | Define dataclass/Pydantic-independent filter models and default constants in `src/services/screen_filters.py`; each UI maps controls into those models. Service dispatch validates the screen/filter combination before calling existing screen functions. |
| Watchlist state | `src/app/sidebar.py` | Replace with a Streamlit-free `resolve_display_filter(con, watchlist_id)` helper. The React URL/store owns selected `watchlistId`; Streamlit keeps its existing session-state adapter. |
| Cache decorators and invalidation | Every page | Keep cache wrappers only in Streamlit adapters. The shared services have no cache or Streamlit import. FastAPI gets request-scoped DuckDB connections; HTTP cache headers/React Query handle read caching later. |
| Display formatting and Plotly construction | Home and Deep Dive; screen pages | Keep presentation formatting in each UI. Extract only reusable display-neutral transformations, such as statement orientation/unit scaling and technical signal summary, into `src/services/presentation.py`. React/ECharts owns chart options. |
| Progress callbacks and `st.rerun` | Universe refresh/bulk workflows | Add a Streamlit-free job service around existing calls. Phase 3 exposes job creation/status; Streamlit continues to use a callback adapter until it can optionally adopt the same job service. |

`Deep_Dive.py` currently calls `fetch_news()` directly, an exception to the
project rule that UI reads DuckDB only.  For feature parity FastAPI can expose
that existing call behind `/api/v1/companies/{ticker}/news`, but it remains a
vendor-network call and should be clearly marked non-warehouse data.  An
alternative is to omit the News tab until news ingestion exists; that would not
be strict feature parity.  This is the only policy decision requiring explicit
approval before Phase 3.

## Proposed API

All routes are versioned under `/api/v1`. Dates are ISO-8601 strings, monetary
and percentage values are JSON numbers or `null`, and a table response uses
`{ "columns": ColumnMeta[], "rows": Record<string, JsonValue>[], "total"?:
int }`. `ColumnMeta` contains stable field name, label, and optional semantic
format (`currency`, `percent`, `number`, `date`). This avoids leaking pandas
objects or UI-formatted strings over the boundary. Route-specific Pydantic
models provide stronger schemas for headers, cards, time series, and mutation
results.

| Method and path | Parameters / body | Response |
| --- | --- | --- |
| `GET /health` | — | service and warehouse availability/version. |
| `GET /dashboard` | `watchlist_id?` | `DashboardResponse`: warehouse timestamp and universe-summary rows. |
| `GET /watchlists` | — | `WatchlistListResponse`. |
| `POST /watchlists` | `WatchlistCreateRequest {name, tickers, description?}` | created `Watchlist`. |
| `GET /watchlists/{id}` | — | `WatchlistDetail` with ordered tickers. |
| `PUT /watchlists/{id}` | `WatchlistReplaceRequest {tickers}` | updated `WatchlistDetail`. |
| `PATCH /watchlists/{id}` | `WatchlistRenameRequest {name}` | updated `Watchlist`. |
| `DELETE /watchlists/{id}` | — | `204 No Content`. |
| `GET /companies` | `active?=true` | ticker/name/sector choices for selectors. |
| `GET /companies/{ticker}/overview` | — | `CompanyOverviewResponse` header metrics. |
| `GET /companies/{ticker}/valuation` | `years=1|3|5` | valuation series and own-history statistics. |
| `GET /companies/{ticker}/profitability` | `periods=12` | quarterly metric series. |
| `GET /companies/{ticker}/analyst` | — | snapshot, derived target upside, and rating counts. |
| `GET /companies/{ticker}/earnings` | `limit=16` | earnings rows (including next-day return). |
| `GET /companies/{ticker}/dividends` | `years=10` | current dividend card plus annual-count series. |
| `GET /companies/{ticker}/statements/{statement_type}` | `period_type=quarterly|annual`, `depth=summary|full`, `limit=8` | schema-aware statement table. |
| `GET /companies/{ticker}/technicals` | `lookback_days?` | technical series plus derived current signals. |
| `GET /companies/{ticker}/prices` | `limit=100`, `offset=0`, `date_from?`, `date_to?` | paginated price table and total. |
| `GET /companies/{ticker}/news` | `limit=50` | `NewsResponse`; wraps existing `fetch_news` only if approved. |
| `GET /universe` | `active?` | universe-management table. |
| `GET /universe/snapshot-coverage` | — | analyst snapshot coverage table. |
| `POST /universe/tickers` | `TickerCreateRequest {ticker, notes?}` | `202 JobAcceptedResponse` (full backfill may be slow). |
| `POST /universe/tickers/bulk` | `BulkTickerCreateRequest {tickers, notes?}` | `202 JobAcceptedResponse`. File upload is parsed in React then sends tickers; shared `parse_ticker_input` remains server-side for pasted raw text if a `raw_text` alternative is added. |
| `DELETE /universe/tickers/{ticker}` | — | `204 No Content` soft delete. |
| `POST /universe/tickers/{ticker}/refresh` | — | `202 JobAcceptedResponse`. |
| `POST /universe/refresh` | — | `202 JobAcceptedResponse`. |
| `GET /jobs/{job_id}` | — | `JobStatusResponse` with queued/running/completed/failed per-ticker outcomes and progress counts. |
| `GET /sectors` | — | full-universe sector summary. |
| `GET /sectors/{sector}/constituents` | `watchlist_id?` | constituent table; server applies only the display filter. |
| `POST /screens/fundamental/{screen}` | `FundamentalScreenRequest {watchlist_id?, filters}` | `ScreenResultResponse` with screen metadata and rows. Screen enum: six existing fundamental screens. |
| `POST /screens/forward/{screen}` | `ForwardScreenRequest {watchlist_id?, filters}` | `ScreenResultResponse`, plus `excluded_count` for history screens. Screen enum: five existing forward screens. |
| `POST /screens/technical/{screen}` | `TechnicalScreenRequest {watchlist_id?, filters}` | `ScreenResultResponse`. Screen enum: twelve existing technical screens. |
| `POST /technicals/recompute` | — | `202 JobAcceptedResponse` wrapping existing deterministic recomputation. |

Screen filter schemas mirror existing function parameters exactly; omitted
optional values mean no filter. Common fields are `watchlist_id`,
`min_mktcap_b`, and `min_adtv_m`. Fundamental filter fields are the named
arguments already used in `3_Screens.py` (for example `max_pe`,
`min_fcf_yield`, `years`, `min_history_days`, `require_acceleration`,
`min_roe`, `max_net_debt_ebitda`, and `min_div_years`). Forward fields are
`lookback_days`, relevant min-delta/revision/surprise/shift thresholds,
`period_filter`, and `min_history_days`. Technical fields are
`lookback_days`, `threshold`, `pct_threshold`, or `percentile`, according to
the selected screen. FastAPI uses discriminated Pydantic models per screen so
invalid combinations are rejected before any screen function runs.

## Frontend structure

```
frontend/
  src/
    api/                 # generated OpenAPI types/client; handwritten query hooks only
    app/                 # router, providers, layout, navigation
    components/
      grid/              # AG Grid defaults, column formatting, server/client pagination
      charts/            # ECharts wrappers: time series, bar, gauge, technical multi-grid
      filters/           # typed filter controls and watchlist selector
      jobs/              # mutation status/progress polling
    features/
      dashboard/
      company/           # overview and eight Deep Dive tabs
      universe/
      screeners/         # fundamental, forward, technical screeners
      watchlists/
      sectors/
    pages/
      DashboardPage.tsx
      CompanyPage.tsx
      UniversePage.tsx
      FundamentalScreenerPage.tsx
      ForwardScreenerPage.tsx
      TechnicalScreenerPage.tsx
      WatchlistsPage.tsx
      SectorsPage.tsx
```

Routes: `/`, `/companies/:ticker`, `/universe`, `/screens/fundamental`,
`/screens/forward`, `/screens/technical`, `/watchlists`, and `/sectors`.
`watchlistId` belongs in a small client store and URL query parameter so a
view is shareable/reload-safe; the API remains stateless.  The first frontend
vertical slice is the fundamental screener: typed filter form ->
`POST /screens/fundamental/{screen}` -> AG Grid results -> save visible result
tickers as a watchlist.  It exercises the shared watchlist/filter/table/API
patterns before the more chart-heavy pages.

## Delivery sequence and acceptance checks

1. **Phase 1 (this document):** audit and API/frontend plan. No application
   behavior changes.
2. **Phase 2:** add Streamlit-free services/filter models and migrate pages to
   call them without changing rendered output. Run the existing full test suite
   and a Streamlit smoke launch. Commit: `refactor: extract UI-free dashboard services`.
3. **Phase 3:** add FastAPI, Pydantic models, OpenAPI generation script, route
   and API-contract tests, and local-run README instructions. Exercise every
   route against the fixture warehouse; retain Streamlit. Commit: `feat(api):
   expose dashboard services through FastAPI`.
4. **Phase 4:** scaffold Vite/React and generated client, then deliver one
   screen at a time: fundamental screener first, then shared dashboard/
   watchlist/universe/sector surfaces, Deep Dive, forward screens, and
   technical screens. Each vertical slice has component tests and an API-backed
   browser smoke test. Separate commits per screen.

The README update will land in Phase 3, when commands are executable:
`uv run uvicorn src.api.main:app --reload` for the backend; `npm install` and
`npm run dev` in `frontend/` for Vite; and the existing Streamlit command stays
documented until parity is accepted.

## Phase 4 parity checklist (remaining after the initial screener slice)

The following workflows remain required before Streamlit can be retired. This
checklist is intentionally interaction-level so a route that merely renders a
table does not count as parity.

- [ ] Dashboard: shared active-watchlist selection, formatted/conditional
  universe table, and links into a ticker drill-down.
- [x] Deep Dive: ticker lookup/navigation; header metrics; valuation,
  profitability, analyst, earnings, dividend, statement, news, and technical
  tabs; all period/depth/unit/range controls; ECharts equivalents for every
  existing Plotly chart. Vendor news has a visible, safe unavailable state
  when its optional upstream service cannot be reached.
- [ ] Universe: add with notes; paste/upload bulk add; per-ticker refresh,
  remove, re-add; refresh-all progress/results; snapshot coverage; price and
  fundamentals drill-down with server pagination/date range.
- [ ] Watchlists: create, rename, edit/replace membership, delete, paste/text
  file import, active selection, and saving every screen result as a list.
- [ ] Fundamental, forward, and technical screeners: every current filter,
  watchlist display filtering, count/empty state, and save-result action.
- [ ] Sectors: summary plus expandable/clickable constituent drill-down,
  retaining full-universe medians while filtering displayed constituents.
- [ ] Technical maintenance: recompute action with meaningful in-progress,
  success, and failure feedback.
- [ ] UX verification: accessible keyboard paths, mobile/desktop layouts,
  API error states, and browser smoke coverage for every route above.
