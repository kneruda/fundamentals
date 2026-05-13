"""Phase 2: prices ingestion + vendor client tests."""

from pathlib import Path
from unittest.mock import patch

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
FUNDAMENTALS = FIXTURES / "AAPL-Fundamentals.json"
PRICES = FIXTURES / "AAPL.json"


@pytest.fixture()
def db():
    from src.schema.runner import open_db

    con = open_db(":memory:")
    yield con
    con.close()


@pytest.fixture()
def loaded_db(db):
    from src.ingest.orchestrator import ingest_ticker

    ingest_ticker(db, FUNDAMENTALS, PRICES)
    return db


# ---------------------------------------------------------------------------
# Prices ingestion
# ---------------------------------------------------------------------------


def test_prices_row_count(loaded_db):
    count = loaded_db.execute("SELECT COUNT(*) FROM prices_daily WHERE ticker='AAPL'").fetchone()[0]
    assert count == 11444


def test_prices_first_row(loaded_db):
    """Earliest AAPL record: IPO date 1980-12-12."""
    from datetime import date

    row = loaded_db.execute(
        "SELECT date, open, close, volume FROM prices_daily"
        " WHERE ticker='AAPL' ORDER BY date ASC LIMIT 1"
    ).fetchone()
    assert row[0] == date(1980, 12, 12)
    assert row[1] == pytest.approx(28.7392, rel=1e-4)
    assert row[3] == 469033600


def test_prices_adjusted_close_differs_from_close(loaded_db):
    """Adjusted close should be heavily split-adjusted for earliest records."""
    row = loaded_db.execute(
        "SELECT close, adjusted_close FROM prices_daily"
        " WHERE ticker='AAPL' ORDER BY date ASC LIMIT 1"
    ).fetchone()
    assert row[0] != pytest.approx(row[1], rel=0.01)


def test_prices_idempotency(db):
    from src.ingest.orchestrator import ingest_ticker

    ingest_ticker(db, FUNDAMENTALS, PRICES)
    count1 = db.execute("SELECT COUNT(*) FROM prices_daily WHERE ticker='AAPL'").fetchone()[0]
    ingest_ticker(db, FUNDAMENTALS, PRICES)
    count2 = db.execute("SELECT COUNT(*) FROM prices_daily WHERE ticker='AAPL'").fetchone()[0]
    assert count1 == count2


def test_adjusted_close_replacement(tmp_path, db):
    """Re-ingesting with modified adjusted_close values updates all rows."""
    import json

    from src.ingest.orchestrator import ingest_ticker

    ingest_ticker(db, FUNDAMENTALS, PRICES)

    with PRICES.open() as f:
        records = json.load(f)

    # Change every adjusted_close to a sentinel value
    sentinel = 999.0
    for r in records:
        r["adjusted_close"] = sentinel

    patched = tmp_path / "AAPL-patched.json"
    patched.write_text(json.dumps(records))
    ingest_ticker(db, FUNDAMENTALS, patched)

    non_sentinel = db.execute(
        "SELECT COUNT(*) FROM prices_daily WHERE ticker='AAPL' AND adjusted_close != ?",
        [sentinel],
    ).fetchone()[0]
    assert non_sentinel == 0


def test_prices_no_data_skipped(db):
    """Calling ingest_prices with no _prices key does nothing."""
    from src.ingest.sections.prices import ingest_prices

    ingest_prices(db, "FAKE", {})
    count = db.execute("SELECT COUNT(*) FROM prices_daily WHERE ticker='FAKE'").fetchone()[0]
    assert count == 0


# ---------------------------------------------------------------------------
# Vendor client
# ---------------------------------------------------------------------------


def test_fetch_fundamentals_uses_token(monkeypatch):
    """fetch_fundamentals passes the API token in query params."""
    monkeypatch.setenv("EODHD_API_TOKEN", "test-token-123")

    captured = {}

    def fake_get(url, params, timeout):
        captured["url"] = url
        captured["params"] = params

        class FakeResp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"General": {"Code": "AAPL"}}

        return FakeResp()

    with patch("httpx.get", fake_get):
        from src.ingest import fetch

        result = fetch.fetch_fundamentals("AAPL")

    assert "AAPL" in captured["url"]
    assert captured["params"]["api_token"] == "test-token-123"
    assert result == {"General": {"Code": "AAPL"}}


def test_fetch_prices_uses_token(monkeypatch):
    """fetch_prices passes the API token and correct query params."""
    monkeypatch.setenv("EODHD_API_TOKEN", "tok-abc")

    captured = {}

    def fake_get(url, params, timeout):
        captured["url"] = url
        captured["params"] = params

        class FakeResp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return []

        return FakeResp()

    with patch("httpx.get", fake_get):
        from src.ingest import fetch

        result = fetch.fetch_prices("AAPL")

    assert "eod" in captured["url"]
    assert captured["params"]["api_token"] == "tok-abc"
    assert captured["params"]["period"] == "d"
    assert result == []


def test_fetch_raises_without_token(monkeypatch):
    monkeypatch.delenv("EODHD_API_TOKEN", raising=False)
    from src.ingest import fetch

    with pytest.raises(EnvironmentError, match="EODHD_API_TOKEN"):
        fetch.fetch_fundamentals("AAPL")


def test_fetch_retries_on_500(monkeypatch):
    """Client retries on 5xx and raises after exhausting attempts."""
    monkeypatch.setenv("EODHD_API_TOKEN", "tok")

    call_count = 0

    def fake_get(url, params, timeout):
        nonlocal call_count
        call_count += 1

        class FakeResp:
            status_code = 503

            def raise_for_status(self):
                pass

            def json(self):
                return {}

        return FakeResp()

    with patch("httpx.get", fake_get), patch("time.sleep"):
        from src.ingest import fetch

        with pytest.raises(RuntimeError, match="attempts failed"):
            fetch.fetch_fundamentals("AAPL")

    assert call_count == 4  # retry_max_attempts default


def test_fetch_appends_exchange_suffix(monkeypatch):
    """Bare ticker gets default_exchange appended."""
    monkeypatch.setenv("EODHD_API_TOKEN", "tok")

    captured = {}

    def fake_get(url, params, timeout):
        captured["url"] = url

        class FakeResp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"General": {"Code": "MSFT", "CurrencyCode": "USD"}}

        return FakeResp()

    with patch("httpx.get", fake_get), patch("time.sleep"):
        from src.ingest import fetch

        fetch.fetch_fundamentals("MSFT")

    assert "MSFT.US" in captured["url"]


# ---------------------------------------------------------------------------
# fetch_and_ingest integration (mocked network)
# ---------------------------------------------------------------------------


def test_fetch_and_ingest_writes_raw_files(tmp_path, db, monkeypatch):
    """fetch_and_ingest writes raw JSON files to disk."""
    import json

    monkeypatch.setenv("EODHD_API_TOKEN", "tok")

    fund_data = FUNDAMENTALS.read_text()
    price_data = PRICES.read_text()

    with (
        patch("src.ingest.orchestrator.fetch_fundamentals", return_value=json.loads(fund_data)),
        patch("src.ingest.orchestrator.fetch_prices", return_value=json.loads(price_data)),
        patch("src.ingest.orchestrator._settings") as mock_cfg,
    ):
        mock_cfg.return_value = {
            "paths": {
                "raw_fundamentals": str(tmp_path / "raw/fundamentals"),
                "raw_prices": str(tmp_path / "raw/prices"),
                "archive": str(tmp_path / "archive"),
            },
            "ingest": {"archive_raw_files": False},
            "vendor": {"default_exchange": "US"},
        }
        from src.ingest.orchestrator import fetch_and_ingest

        fetch_and_ingest(db, "AAPL")

    assert (tmp_path / "raw/fundamentals/AAPL.json").exists()
    assert (tmp_path / "raw/prices/AAPL.json").exists()
    count = db.execute("SELECT COUNT(*) FROM prices_daily WHERE ticker='AAPL'").fetchone()[0]
    assert count > 0


def test_fetch_and_ingest_archives_when_enabled(tmp_path, db, monkeypatch):
    import json
    from datetime import date

    monkeypatch.setenv("EODHD_API_TOKEN", "tok")

    fund_data = json.loads(FUNDAMENTALS.read_text())
    price_data = json.loads(PRICES.read_text())

    today = date.today().isoformat()

    with (
        patch("src.ingest.orchestrator.fetch_fundamentals", return_value=fund_data),
        patch("src.ingest.orchestrator.fetch_prices", return_value=price_data),
        patch("src.ingest.orchestrator._settings") as mock_cfg,
    ):
        mock_cfg.return_value = {
            "paths": {
                "raw_fundamentals": str(tmp_path / "raw/fundamentals"),
                "raw_prices": str(tmp_path / "raw/prices"),
                "archive": str(tmp_path / "archive"),
            },
            "ingest": {"archive_raw_files": True},
            "vendor": {"default_exchange": "US"},
        }
        from src.ingest.orchestrator import fetch_and_ingest

        fetch_and_ingest(db, "AAPL")

    assert (tmp_path / "archive" / today / "AAPL-fundamentals.json").exists()
    assert (tmp_path / "archive" / today / "AAPL-prices.json").exists()


def test_fetch_and_ingest_skips_fetch_if_fresh(tmp_path, db, monkeypatch):
    """If files exist and are fresh (mtime=today), skip the network calls."""
    import json
    from unittest.mock import MagicMock

    monkeypatch.setenv("EODHD_API_TOKEN", "tok")

    raw_fund = tmp_path / "raw/fundamentals"
    raw_price = tmp_path / "raw/prices"
    raw_fund.mkdir(parents=True)
    raw_price.mkdir(parents=True)

    (raw_fund / "AAPL.json").write_text(FUNDAMENTALS.read_text())
    (raw_price / "AAPL.json").write_text(PRICES.read_text())

    mock_fetch_fund = MagicMock(return_value=json.loads(FUNDAMENTALS.read_text()))
    mock_fetch_price = MagicMock(return_value=json.loads(PRICES.read_text()))

    with (
        patch("src.ingest.orchestrator.fetch_fundamentals", mock_fetch_fund),
        patch("src.ingest.orchestrator.fetch_prices", mock_fetch_price),
        patch("src.ingest.orchestrator._settings") as mock_cfg,
    ):
        mock_cfg.return_value = {
            "paths": {
                "raw_fundamentals": str(raw_fund),
                "raw_prices": str(raw_price),
                "archive": str(tmp_path / "archive"),
            },
            "ingest": {"archive_raw_files": False},
            "vendor": {"default_exchange": "US"},
        }
        from src.ingest.orchestrator import fetch_and_ingest

        fetch_and_ingest(db, "AAPL")

    mock_fetch_fund.assert_not_called()
    mock_fetch_price.assert_not_called()
