# Runbook — Observability Lab

Response procedures for the alerts defined in `prometheus/alerts.yml`.
Each section follows the same structure: **what it means → how to confirm → how to mitigate → how to resolve**.

---

## High Error Rate

**Alert:** `HighErrorRate` · **Severity:** critical · **SLO:** availability

### Symptoms
The 5xx response rate is above 5% over the last minute.

### Confirm
1. Open Prometheus (`http://localhost:9090`) and query:
   ```
   job:sli_error_ratio:rate1m
   ```
2. Check the **Error ratio (5xx)** panel in Grafana.
3. Identify the problematic endpoint:
   ```
   sum by (endpoint) (rate(http_requests_total{status=~"5.."}[5m]))
   ```

### Mitigate (immediate action)
- If the application is at fault, restart it or redirect traffic (`docker compose restart app`).
- If the issue followed a recent deployment, **roll back** to the last healthy version.
- If an external dependency is at fault, enable a *circuit breaker* or degrade functionality.

### Resolve
- Write a postmortem (see the template in `sre-runbooks`).
- Fix the root cause and add a regression test.

---

## High Latency P95

**Alert:** `HighLatencyP95` · **Severity:** warning · **SLO:** latency

### Symptoms
The 95th percentile latency is above 300 ms for 5 minutes.

### Confirm
```
job:sli_latency_p95:rate5m
```
Check the **Latency P95** panel in Grafana.

### Mitigate
- Check for CPU or memory saturation in the pod/container.
- Scale out if the load is legitimate.
- Check for slow dependencies, such as databases or external APIs.

### Resolve
- Add indexes or caching, optimize queries, and adjust timeouts.

---

## App Down

**Alert:** `AppDown` · **Severity:** critical

### Symptoms
`up{job="observability-lab-app"} == 0` — Prometheus cannot scrape metrics from the target.

### Confirm
1. `docker compose ps` — is the container running?
2. `curl http://localhost:8000/healthz`
3. Check the logs: `docker compose logs app --tail=100`

### Mitigate
- `docker compose restart app`
- Check memory limits (`OOMKilled`) and ports in use.

### Resolve
- Fix the startup failure and ensure the probes are configured correctly.

---

## References
- [Google SRE Book — Monitoring](https://sre.google/sre-book/monitoring-distributed-systems/)
- [Prometheus — Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
