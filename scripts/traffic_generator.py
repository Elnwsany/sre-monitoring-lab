#!/usr/bin/env python3
"""Generate bounded traffic against the local observability lab."""

from __future__ import annotations

import argparse
import concurrent.futures
import random
import sys
import threading
import time
from collections import Counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TARGET = "http://localhost:8080/work"
MAX_WORKERS = 32
MAX_DURATION = 600

COLORS = {
    "cyan": "\033[36m",
    "green": "\033[32m",
    "red": "\033[31m",
    "reset": "\033[0m",
}


class Stats:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.counts: Counter[str] = Counter()
        self.started_at = time.monotonic()

    def record(self, status: int | None) -> None:
        if status is None:
            category = "NET"
        else:
            category = f"{status // 100}xx"
        with self.lock:
            self.counts[category] += 1

    def snapshot(self) -> tuple[Counter[str], float]:
        with self.lock:
            return self.counts.copy(), time.monotonic() - self.started_at


def send_request(failure_rate: float, delay: float, stats: Stats) -> None:
    query = urlencode({"fail": f"{failure_rate:.3f}", "delay": f"{delay:.3f}"})
    request = Request(
        f"{TARGET}?{query}",
        headers={"User-Agent": "sre-monitoring-lab-traffic-generator"},
    )
    status: int | None = None
    try:
        with urlopen(request, timeout=8) as response:
            status = response.status
    except HTTPError as error:
        status = error.code
        error.close()
    except (URLError, TimeoutError, OSError):
        status = None
    stats.record(status)


def scenario(mode: str, started_at: float) -> tuple[str, float, float]:
    if mode == "normal":
        return 0.01, random.uniform(0.05, 0.15), random.uniform(0.5, 1.0)
    if mode == "slo-spike":
        return 0.9, random.uniform(0.05, 0.15), 0.0
    if mode == "latency":
        return 0.01, random.uniform(1.5, 3.0), 0.0

    phase = started_at % 60
    if phase < 45:
        return 0.01, random.uniform(0.05, 0.25), random.uniform(1.0, 2.0)
    return random.uniform(0.03, 0.05), random.uniform(0.15, 0.8), random.uniform(0.2, 0.4)


def color(text: str, name: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{COLORS[name]}{text}{COLORS['reset']}"


def render_status(mode: str, stats: Stats, use_color: bool) -> None:
    counts, elapsed = stats.snapshot()
    total = sum(counts.values())
    rate = total / elapsed if elapsed else 0.0
    successes = color(f"2xx {counts['2xx']}", "green", use_color)
    failures = color(f"5xx {counts['5xx']}", "red", use_color)
    line = (
        f"{color(mode.upper(), 'cyan', use_color)} | "
        f"{elapsed:5.1f}s | {total:6d} requests | "
        f"{successes} | "
        f"{failures} | "
        f"other {sum(v for k, v in counts.items() if k not in {'2xx', '5xx'}):d} | "
        f"{rate:.1f} req/s"
    )
    print(f"\r{line:<110}", end="", flush=True)


def positive_duration(value: str) -> float:
    try:
        duration = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("duration must be a number of seconds") from error
    if duration <= 0 or duration > MAX_DURATION:
        raise argparse.ArgumentTypeError(f"duration must be between 0 and {MAX_DURATION} seconds")
    return duration


def worker_count(value: str) -> int:
    try:
        workers = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("workers must be an integer") from error
    if workers < 1 or workers > MAX_WORKERS:
        raise argparse.ArgumentTypeError(f"workers must be between 1 and {MAX_WORKERS}")
    return workers


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate traffic for the local SRE monitoring lab (localhost:8080 only)."
    )
    parser.add_argument(
        "mode",
        choices=("normal", "slo-spike", "chaos", "latency", "realistic"),
        help="normal/realistic/latency run until Ctrl+C; chaos runs for 30 seconds by default",
    )
    parser.add_argument(
        "--duration",
        type=positive_duration,
        help=f"stop after this many seconds (maximum {MAX_DURATION})",
    )
    parser.add_argument(
        "--workers",
        type=worker_count,
        help=f"concurrent requests (1-{MAX_WORKERS}); defaults vary by mode",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mode = "slo-spike" if args.mode == "chaos" else args.mode
    defaults = {"normal": 1, "slo-spike": 16, "latency": 4, "realistic": 8}
    workers = args.workers or defaults[mode]
    duration = args.duration or (30.0 if mode == "slo-spike" else None)
    stop_at = time.monotonic() + duration if duration is not None else None
    stats = Stats()
    use_color = sys.stdout.isatty()
    pending: set[concurrent.futures.Future[None]] = set()
    start = time.monotonic()
    next_request = start
    next_status = start

    print(
        f"Scenario: {color(mode, 'cyan', use_color)} | target: {TARGET} | "
        f"workers: {workers} | duration: {f'{duration:g}s' if duration else 'until Ctrl+C'}"
    )
    print("Press Ctrl+C to stop.")

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            while stop_at is None or time.monotonic() < stop_at:
                now = time.monotonic()
                pending = {future for future in pending if not future.done()}
                if now >= next_request and len(pending) < workers:
                    failure_rate, delay, interval = scenario(mode, now - start)
                    pending.add(executor.submit(send_request, failure_rate, delay, stats))
                    next_request = now + interval
                    if mode == "slo-spike":
                        next_request = now

                if now >= next_status:
                    render_status(mode, stats, use_color)
                    next_status = now + 1.0
                time.sleep(0.02)
    except KeyboardInterrupt:
        print()
    finally:
        for future in pending:
            future.cancel()
        render_status(mode, stats, use_color)
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
