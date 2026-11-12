# SLI / SLO — Observability Lab

This document defines the **Service Level Indicators (SLIs)**, **Service Level Objectives (SLOs)**, and **error budget** used in this lab. The same principles apply to production systems.

## 1. Definitions

| Term              | Meaning                                                                  |
|-------------------|--------------------------------------------------------------------------|
| **SLI**           | A metric that measures an aspect of a service (e.g., success rate)       |
| **SLO**           | A target for an SLI over a time window (e.g., 99.9% over 30 days)        |
| **SLA**           | A contractual agreement with a customer, including consequences if the SLO is missed |
| **Error budget**  | The amount of failure allowed by the SLO (100% − SLO)                    |

## 2. SLIs in Use

### 2.1 Availability

The proportion of successful (non-5xx) requests out of all requests.

```
sli_error_ratio = sum(rate(http_requests_total{status=~"5.."}[5m]))
                  / sum(rate(http_requests_total[5m]))

availability = 1 - sli_error_ratio
```

### 2.2 Latency

The 95th percentile of response time, measured by the `http_request_duration_seconds` histogram.

```
sli_latency_p95 = histogram_quantile(
  0.95,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
)
```

## 3. SLO Targets

| SLI              | SLO target | Window | Error budget          |
|------------------|------------|--------|-----------------------|
| Availability     | 99.9%      | 30 days| 0.1% → ~43 min/month  |
| P95 latency      | < 300 ms   | 30 days| 5% of periods         |

### Calculating the Error Budget

For 30 days (~43,200 minutes) and a 99.9% SLO:

```
budget = (1 - 0.999) * 43200 min = 43.2 min
```

This means the service can be in violation for **up to ~43 minutes per month** before the SLO is breached.

## 4. Alerting Policy

- Alerts **prioritize symptoms** (error rate, latency) over **causes** (CPU, memory).
- `critical` alerts fire on **SLO violations**, not on every fluctuation.
- Each alert links to a **runbook** ([RUNBOOK.md](RUNBOOK.md)).

| Alert            | Expression                                             | `for` | Severity |
|------------------|--------------------------------------------------------|-------|----------|
| `HighErrorRate`  | `job:sli_error_ratio:rate1m > 0.05`                    | 30s   | critical |
| `HighLatencyP95` | `job:sli_latency_p95:rate5m > 0.3`                     | 5m    | warning  |
| `AppDown`        | `up{job="observability-lab-app"} == 0`                 | 1m    | critical |

## 5. Error Budget Policy (Burn Rate)

When the error budget is consumed too quickly (a high "*burn rate*"), the recommended actions are:

1. **Freeze** releases that change behavior (feature freeze).
2. Prioritize **reliability** work (fixes and technical debt).
3. Require a post-incident review.

Example burn rates (industry reference):

| Long window | Short window | Budget burn | Action  |
|-------------|--------------|-------------|---------|
| 1h          | 5m           | 14.4x       | Page    |
| 6h          | 30m          | 6x          | Ticket  |
| 3d          | 6h           | 1x          | Monitor |
