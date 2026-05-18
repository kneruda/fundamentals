import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

log = logging.getLogger(__name__)

_settings_path = Path(__file__).parent.parent.parent / "config" / "settings.yml"


def _settings() -> dict:
    with _settings_path.open() as f:
        return yaml.safe_load(f)


def _token() -> str:
    token = os.environ.get("EODHD_API_TOKEN", "")
    if not token:
        raise OSError("EODHD_API_TOKEN is not set")
    return token


def _get(url: str, params: dict, cfg: dict) -> Any:
    max_attempts = cfg.get("retry_max_attempts", 4)
    base_sleep = cfg.get("retry_base_seconds", 1)
    rps = cfg.get("requests_per_second", 5)

    last_status: int | None = None
    last_error: str | None = None
    for attempt in range(max_attempts):
        try:
            resp = httpx.get(url, params=params, timeout=30)
            if resp.status_code == 429 or resp.status_code >= 500:
                last_status = resp.status_code
                last_error = f"HTTP {resp.status_code}"
                wait = base_sleep * (2**attempt)
                log.warning("HTTP %s from %s; retrying in %.1fs", resp.status_code, url, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            time.sleep(1.0 / rps)
            return resp.json()
        except httpx.TransportError as exc:
            last_error = f"transport error: {exc}"
            wait = base_sleep * (2**attempt)
            log.warning("Transport error (%s); retrying in %.1fs", exc, wait)
            time.sleep(wait)

    raise RuntimeError(
        f"All {max_attempts} attempts failed for {url} "
        f"(last_status={last_status}, last_error={last_error})"
    )


def fetch_fundamentals(ticker: str) -> dict:
    cfg = _settings()
    vendor = cfg.get("vendor", {})
    base_url = vendor.get("base_url", "https://eodhd.com/api")
    exchange = vendor.get("default_exchange", "US")
    if "." not in ticker:
        ticker = f"{ticker}.{exchange}"
    url = f"{base_url}/fundamentals/{ticker}"
    data = _get(url, {"api_token": _token(), "fmt": "json"}, vendor)
    if isinstance(data, dict) and "Error" in data:
        raise ValueError(f"EODHD rejected ticker: {data['Error']}")
    if not isinstance(data, dict) or not data.get("General", {}).get("Code"):
        raise ValueError(f"No valid General.Code in EODHD response for {ticker!r}")
    return data


def fetch_prices(ticker: str) -> list:
    cfg = _settings()
    vendor = cfg.get("vendor", {})
    base_url = vendor.get("base_url", "https://eodhd.com/api")
    exchange = vendor.get("default_exchange", "US")
    if "." not in ticker:
        ticker = f"{ticker}.{exchange}"
    url = f"{base_url}/eod/{ticker}"
    data = _get(url, {"api_token": _token(), "fmt": "json", "period": "d"}, vendor)
    if isinstance(data, dict) and "Error" in data:
        raise ValueError(f"EODHD prices error for {ticker!r}: {data['Error']}")
    if not isinstance(data, list):
        raise ValueError(f"Unexpected price data format for {ticker!r}")
    return data


def fetch_news(ticker: str, limit: int = 50) -> list:
    cfg = _settings()
    vendor = cfg.get("vendor", {})
    base_url = vendor.get("base_url", "https://eodhd.com/api")
    exchange = vendor.get("default_exchange", "US")
    if "." not in ticker:
        ticker = f"{ticker}.{exchange}"
    url = f"{base_url}/news"
    data = _get(url, {"api_token": _token(), "s": ticker, "limit": limit, "fmt": "json"}, vendor)
    if isinstance(data, dict) and "Error" in data:
        raise ValueError(f"EODHD news error for {ticker!r}: {data['Error']}")
    if not isinstance(data, list):
        raise ValueError(f"Unexpected news response for {ticker!r}")
    return data
