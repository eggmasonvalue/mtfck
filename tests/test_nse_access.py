import importlib
import subprocess
import sys
from datetime import date
from unittest.mock import Mock

import httpx
import pytest
from exchange_access import NSEClient
from nse import NSEFileUnavailableError


def test_module_imports_do_not_construct_upstream(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", """
from unittest.mock import patch
from exchange_access import NSEClient
with patch('exchange_access.nse.NSE', side_effect=AssertionError('network at import')) as upstream:
    import mtfck.ingestion
    import mtfck.mtfck
    for module in (mtfck.ingestion, mtfck.mtfck):
        assert isinstance(module.nse, NSEClient)
        assert 'nse' not in module.nse.__dict__
        module.nse.close()
    upstream.assert_not_called()
"""],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_download_discards_cached_zip_before_fetch(tmp_path, monkeypatch):
    ingestion = importlib.import_module("mtfck.ingestion")
    report_date = date(2026, 10, 30)
    cached_zip = tmp_path / "mrg_trading_301026.zip"
    cached_zip.write_bytes(b"incomplete old download")
    csv_path = tmp_path / "report.csv"

    def download(*, url, folder):
        assert url.endswith(cached_zip.name)
        assert folder == tmp_path
        assert not cached_zip.exists()
        csv_path.write_text("report")
        return csv_path

    upstream = Mock(spec=["download_document"])
    upstream.download_document.side_effect = download
    client = NSEClient(str(tmp_path), retry_profile="bulk")
    client.__dict__["nse"] = upstream
    parser = Mock()
    monkeypatch.setattr(ingestion, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ingestion, "nse", client)
    monkeypatch.setattr(ingestion, "parse_and_insert", parser)

    ingestion._download_for_date(report_date)

    upstream.download_document.assert_called_once()
    parser.assert_called_once_with(str(csv_path), "2026-10-30")


def test_history_remains_unadjusted(tmp_path, monkeypatch):
    analytics = importlib.import_module("mtfck.mtfck")
    upstream = Mock(spec=["fetch_equity_historical_data", "actions"])
    upstream.fetch_equity_historical_data.return_value = [{"CH_CLOSING_PRICE": 123.5}]
    client = NSEClient(str(tmp_path), retry_profile="bulk")
    client.__dict__["nse"] = upstream
    monkeypatch.setattr(analytics, "nse", client)
    d = date(2026, 10, 30)

    assert analytics.get_next_trading_close("TEST", d) == 123.5
    upstream.fetch_equity_historical_data.assert_called_once_with(
        "TEST", from_date=d, to_date=d, series="EQ"
    )
    upstream.actions.assert_not_called()


@pytest.mark.parametrize("error", [
    httpx.ReadTimeout("timeout"),
    httpx.ConnectError("connection"),
    httpx.HTTPStatusError(
        "forbidden",
        request=httpx.Request("GET", "https://www.nseindia.com/api/quote-equity"),
        response=httpx.Response(403),
    ),
])
def test_analytics_handles_httpx_failures(tmp_path, monkeypatch, error):
    analytics = importlib.import_module("mtfck.mtfck")
    upstream = Mock(spec=["fetch_equity_historical_data", "quote"])
    upstream.fetch_equity_historical_data.side_effect = error
    upstream.quote.side_effect = error
    client = NSEClient(str(tmp_path), retry_profile="bulk")
    client.__dict__["nse"] = upstream
    # Exercise final-failure handling without sleeping through shared retries.
    client._retry = lambda fn: fn
    monkeypatch.setattr(analytics, "nse", client)

    assert analytics.get_next_trading_close("TEST", date(2026, 10, 30)) is None
    assert analytics.get_ffmc_and_exposure({"symbol": "TEST", "amt": 100}, "amt") == (None, None)
    upstream.fetch_equity_historical_data.assert_called_once()


@pytest.mark.parametrize("error", [
    NSEFileUnavailableError("404"),
    httpx.ReadTimeout("timeout"),
    httpx.ConnectError("connection"),
])
def test_ingestion_continues_after_upstream_failure(monkeypatch, capsys, error):
    ingestion = importlib.import_module("mtfck.ingestion")
    conn = Mock()
    conn.sql.return_value.fetchall.return_value = []
    download = Mock(side_effect=[error, None])
    monkeypatch.setattr(ingestion, "create_table", Mock())
    monkeypatch.setattr(ingestion, "get_connection", lambda: conn)
    monkeypatch.setattr(ingestion, "_download_for_date", download)

    ingestion.download_and_store_range(date(2026, 10, 29), date(2026, 10, 30))

    assert download.call_count == 2
    assert "Failed for 2026-10-29" in capsys.readouterr().out
