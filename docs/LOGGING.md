# Centralized Logs

The optional `logging` Compose profile adds Nginx, Loki, and Grafana Alloy.
Prometheus continues to scrape the FastAPI app directly on port 8000. Requests
can also enter through Nginx on port 8080, which writes JSON access logs and
forwards an `X-Request-ID` to the app.

## Start the logging stack

```bash
docker compose --profile logging up --build
```

Check Loki readiness:

```bash
curl -fsS http://localhost:3100/ready
```

Generate 200 requests through Nginx with simulated failures:

```bash
for i in $(seq 1 200); do
  curl -s -o /dev/null "http://localhost:8080/work?fail=0.15&delay=0.12"
done
```

In Grafana, open **Explore**, select the **Loki** datasource, and run one of
these LogQL queries:

### App errors with stack traces

```logql
{service="app", level="error"} | json | exception != "" | line_format "{{.exception}}"
```

### Nginx 5xx rate per second

```logql
sum(rate({service="nginx"} | json | status_class="5xx" [1m]))
```

### Nginx P95 request latency in seconds

```logql
quantile_over_time(0.95, {service="nginx"} | json | unwrap request_time | __error__="" [5m])
```

### Follow a request ID across app and Nginx

The app response returns the same request ID that Nginx writes to its access
log. Copy the `X-Request-ID` response header, then use it in this query:

```logql
{service=~"app|nginx"} | json | request_id="PASTE_REQUEST_ID_HERE"
```

Only `service`, `level`, and `status_class` are indexed as Loki labels.
Request IDs, paths, IP addresses, and latency remain JSON fields to avoid
high-cardinality labels. Alloy drops `/healthz` and `/metrics` entries from
both log streams.
