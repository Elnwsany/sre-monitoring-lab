"""Tests for the observability-lab application."""

import json

from fastapi.testclient import TestClient

from src.app.main import JsonFormatter, app

client = TestClient(app)


def test_root() -> None:
    body = client.get("/").json()
    assert body["service"] == "observability-lab"


def test_healthz() -> None:
    assert client.get("/healthz").json() == {"status": "healthy"}


def test_work_ok() -> None:
    assert client.get("/work").json() == {"status": "ok"}


def test_work_simulates_failure() -> None:
    # fail=1.0 => always fails
    assert client.get("/work?fail=1.0").status_code == 500


def test_metrics_endpoint_exposes_prometheus_format() -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text
    assert "# HELP" in response.text


def test_metrics_records_requests() -> None:
    client.get("/healthz")
    text = client.get("/metrics").text
    assert 'endpoint="/healthz"' in text


def test_request_logs_are_json_and_include_request_id(caplog) -> None:
    caplog.set_level("INFO", logger="src.app.main")

    response = client.get("/work", headers={"X-Request-ID": "test-request-id"})

    assert response.headers["X-Request-ID"] == "test-request-id"
    record = next(
        record for record in caplog.records if record.getMessage() == "request completed"
    )
    entry = json.loads(JsonFormatter().format(record))
    assert entry["request_id"] == "test-request-id"
    assert entry["path"] == "/work"
    assert entry["status_class"] == "2xx"


def test_health_and_metrics_requests_are_not_logged(caplog) -> None:
    caplog.set_level("INFO", logger="src.app.main")

    client.get("/healthz")
    client.get("/metrics")

    assert not any(
        record.getMessage() == "request completed" for record in caplog.records
    )


def test_simulated_failure_logs_stack_trace_in_one_json_field(caplog) -> None:
    caplog.set_level("ERROR", logger="src.app.main")

    response = client.get("/work?fail=1", headers={"X-Request-ID": "failed-request"})

    assert response.status_code == 500
    record = next(
        record for record in caplog.records if record.getMessage() == "simulated work failure"
    )
    entry = json.loads(JsonFormatter().format(record))
    assert entry["request_id"] == "failed-request"
    assert "Traceback" in entry["exception"]
