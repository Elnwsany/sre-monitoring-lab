"""Observability Lab — a small instrumented service.

Exposes Prometheus metrics so the rest of the stack (Prometheus, Alertmanager,
Grafana) has something real to collect, alert on and visualise.
"""

from __future__ import annotations

import json
import logging
import os
import random
import sys
import time
import uuid

from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
ENVIRONMENT = os.getenv("ENVIRONMENT", "local")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        exception = (
            self.formatException(record.exc_info)
            if record.exc_info
            else getattr(record, "exception", None)
        )
        entry = {
            "level": record.levelname.lower(),
            "message": record.getMessage(),
            "logger": record.name,
            "request_id": getattr(record, "request_id", None),
            "exception": exception,
        }
        for field in ("method", "path", "status", "status_class", "duration_ms"):
            value = getattr(record, field, None)
            if value is not None:
                entry[field] = value
        return json.dumps(entry, ensure_ascii=False)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    handlers=[handler],
    force=True,
)
LOGGER = logging.getLogger(__name__)

app = FastAPI(
    title="Observability Lab",
    version=APP_VERSION,
    description="Instrumented service for a Prometheus/Grafana/Alertmanager demo.",
    contact={"name": "Hesham Elnwsany", "url": "https://github.com/Elnwsany"},
)

REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 5),
)
INFLIGHT = Gauge("http_inflight_requests", "In-flight HTTP requests")


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Record count and latency for every request (except /metrics itself)."""
    if request.url.path == "/metrics":
        return await call_next(request)

    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = request_id
    INFLIGHT.inc()
    start = time.perf_counter()
    status_code = "500"
    try:
        response = await call_next(request)
        status_code = str(response.status_code)
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        if request.url.path != "/healthz":
            LOGGER.exception(
                "unhandled request exception",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "status_class": "5xx",
                },
            )
        raise
    finally:
        INFLIGHT.dec()
        route = request.scope.get("route")
        endpoint = route.path if route else request.url.path
        duration = time.perf_counter() - start
        LATENCY.labels(endpoint).observe(duration)
        REQUESTS.labels(request.method, endpoint, status_code).inc()
        status = int(status_code)
        if request.url.path != "/healthz":
            LOGGER.log(
                logging.ERROR if status >= 500 else logging.INFO,
                "request completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "status_class": f"{status // 100}xx",
                    "duration_ms": round(duration * 1000, 3),
                },
            )


@app.get("/", tags=["info"], summary="Service metadata")
def root() -> dict:
    return {"service": "observability-lab", "version": APP_VERSION, "environment": ENVIRONMENT}


@app.get("/healthz", tags=["health"], summary="Liveness probe")
def healthz() -> dict:
    return {"status": "healthy"}


@app.get("/work", tags=["work"], summary="Simulate work with optional failures/latency")
def work(request: Request, fail: float = 0.0, delay: float = 0.0) -> dict:
    """Simulate work.

    - `fail`: probability (0..1) of returning HTTP 500.
    - `delay`: seconds to sleep before responding.
    """
    if delay > 0:
        time.sleep(min(delay, 5.0))
    if fail > 0 and random.random() < fail:
        try:
            raise RuntimeError("simulated failure")
        except RuntimeError:
            LOGGER.exception(
                "simulated work failure",
                extra={
                    "request_id": request.state.request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "status_class": "5xx",
                },
            )
        raise HTTPException(status_code=500, detail="simulated failure")
    return {"status": "ok"}


@app.get("/metrics", tags=["observability"], summary="Prometheus metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
