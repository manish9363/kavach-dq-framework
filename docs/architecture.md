# Kavach DQ Framework — Architecture

## System Overview

Kavach is an agentic, adaptive data quality framework built on AWS Bedrock with a multi-agent architecture.
The system returns DQ status (PASS / FAIL / ALERT) back to the calling API for downstream consumption.

---

## Key Design Principles

1. **Agent 2 (Rule Generator) is NOT called every time** — only triggered when:
   - New dataset is detected (no prior rules)
   - Schema change detected (columns added/removed/modified)
   - Force re-profiling requested by user

2. **Agent 3 (Rule Executor) is called EVERY time** — evaluates existing rules on every run

3. **Response-driven** — The calling system (Airflow/Step Functions/API) receives a status response:
   - ✅ `PASS` — All DQ rules passed
   - ❌ `FAIL` — Critical rules failed, alerts triggered
   - ⚠️ `ALERT` — Warnings detected, non-critical issues
   - Returns full status payload to the caller

---

## High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL INTEGRATION LAYER                                  │
│                                                                                         │
│   ┌───────────┐    ┌───────────────┐    ┌───────────┐    ┌──────────────────┐          │
│   │  Airflow  │    │Step Functions │    │  Custom   │    │   S3 Event       │          │
│   │  DAGs     │    │  Workflows    │    │  API Call │    │   Notification   │          │
│   └─────┬─────┘    └──────┬────────┘    └─────┬─────┘    └────────┬─────────┘          │
│         │                  │                   │                   │                    │
│         └──────────────────┼───────────────────┘                   │                    │
│                            ▼                                       │                    │
│                  ┌──────────────────┐                              │                    │
│                  │   API Gateway    │                              │                    │
│                  │   (REST/HTTP)    │                              │                    │
│                  └────────┬─────────┘                              │                    │
│                           │                                        │                    │
└───────────────────────────┼────────────────────────────────────────┼────────────────────┘
                            │                                        │
                            ▼                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              ENTRY POINT LAYER                                          │
│                                                                                         │
│                  ┌─────────────────────────────────────────┐                            │
│                  │         λ ORCHESTRATOR LAMBDA            │                            │
│                  │                                         │                            │
│                  │  • Validates request payload             │                            │
│                  │  • Extracts dataset metadata             │                            │
│                  │  • Invokes Supervisor Agent              │                            │
│                  │  • Returns DQ status to caller           │                            │
│                  │    (PASS / FAIL / ALERT)                 │                            │
│                  └────────────────────┬────────────────────┘                            │
│                                       │                                                 │
└───────────────────────────────────────┼─────────────────────────────────────────────────┘
                                        │
                                        ▼
```

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              AGENT LAYER (AWS BEDROCK)                                   │
│                                                                                         │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐ │
│  │                    AGENT 1: SUPERVISOR AGENT (Claude)                               │ │
│  │                                                                                    │ │
│  │  Responsibilities:                                                                 │ │
│  │  • Orchestrates the entire DQ workflow                                             │ │
│  │  • Checks if rules exist for the dataset                                          │ │
│  │  • Detects schema changes (new/modified/deleted columns)                           │ │
│  │  • Routes to Rule Generator ONLY if: no rules / schema change / force reprofile    │ │
│  │  • Routes to Rule Executor on EVERY call (default path)                            │ │
│  │  • Verifies generated rules before execution                                      │ │
│  │  • Returns final status (PASS/FAIL/ALERT) to Orchestrator Lambda                  │ │
│  │                                                                                    │ │
│  │  Helper Lambdas:                                                                   │ │
│  │  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────────┐    │ │
│  │  │ λ metadata-lookup   │  │ λ schema-detector   │  │ λ rule-validator        │    │ │
│  │  │                     │  │                     │  │                         │    │ │
│  │  │ • Query DynamoDB    │  │ • Compare current   │  │ • Validate rule syntax  │    │ │
│  │  │   rules table       │  │   schema vs stored  │  │ • Check rule conflicts  │    │ │
│  │  │ • Check dataset     │  │ • Detect column     │  │ • Verify completeness   │    │ │
│  │  │   registration      │  │   add/remove/modify │  │ • Dry-run validation    │    │ │
│  │  │ • Return rule       │  │ • Flag for          │  │                         │    │ │
│  │  │   status            │  │   re-profiling      │  │                         │    │ │
│  │  └─────────────────────┘  └─────────────────────┘  └─────────────────────────┘    │ │
│  └──────────┬──────────────────────────────────────────────────────┬──────────────────┘ │
│             │                                                      │                    │
│    (No rules / Schema change /                            (Rules exist &               │
│     Force re-profile)                                      no schema change)            │
│             │                                                      │                    │
│             ▼                                                      │                    │
│  ┌────────────────────────────────────────────────────────────┐    │                    │
│  │         AGENT 2: RULE GENERATOR / PROFILER (Claude)        │    │                    │
│  │                                                            │    │                    │
│  │  TRIGGERED ONLY WHEN:                                      │    │                    │
│  │  • New dataset (no existing rules)                         │    │                    │
│  │  • Schema change detected (columns added/removed/changed)  │    │                    │
│  │  • Force re-profiling requested                            │    │                    │
│  │                                                            │    │                    │
│  │  Responsibilities:                                         │    │                    │
│  │  • Profiles data to understand patterns                    │    │                    │
│  │  • Analyzes 30-day historical stats                        │    │                    │
│  │  • Reads Knowledge Base for DQ standards                   │    │                    │
│  │  • Generates executable DQ rules (SQL/queries)             │    │                    │
│  │  • Stores rules + metadata in DynamoDB                     │    │                    │
│  │  • Computes adaptive thresholds                            │    │                    │
│  └────────────────────────────────────────────────────────────┘    │                    │
│             │                                                      │                    │
│             │  (Rules generated & verified by Supervisor)           │                    │
│             ▼                                                      ▼                    │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐ │
│  │         AGENT 3: RULE EXECUTOR (Claude) — CALLED EVERY TIME                        │ │
│  │                                                                                    │ │
│  │  Responsibilities:                                                                 │ │
│  │  • Executes validated DQ rules against live data                                   │ │
│  │  • Evaluates every rule and captures pass/fail per check                           │ │
│  │  • Computes overall DQ score                                                       │ │
│  │  • Determines final status: PASS / FAIL / ALERT                                   │ │
│  │  • Triggers alerts/emails on failures                                              │ │
│  │  • Updates adaptive baseline metrics                                               │ │
│  │  • Returns status response to Supervisor → Lambda → Caller                        │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Agent 2: Rule Generator — Helper Lambdas (Detail)

```
┌────────────────────────────────────────────────────────────────────────────────┐
│  AGENT 2: RULE GENERATOR / PROFILER — Helper Lambdas                           │
│                                                                                │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────────┐       │
│  │ λ data-profiler  │  │ λ stats-aggregator│  │ λ rule-writer          │       │
│  │                  │  │                  │  │                        │       │
│  │ • Trigger        │  │ • Query last     │  │ • Format rules as     │       │
│  │   DataBrew       │  │   30 days data   │  │   executable queries  │       │
│  │   profile job    │  │ • Compute min/   │  │ • Save to DynamoDB    │       │
│  │ • Trigger Glue   │  │   max/median/avg │  │ • Store metadata      │       │
│  │   crawlers       │  │ • Null distrib-  │  │ • Version control     │       │
│  │ • Sample data    │  │   ution analysis │  │   rules               │       │
│  │   extraction     │  │ • Record count   │  │ • Tag with baseline   │       │
│  │ • Pattern        │  │   trends         │  │   period              │       │
│  │   detection      │  │                  │  │                        │       │
│  └──────────────────┘  └──────────────────┘  └────────────────────────┘       │
│                                                                                │
│  ┌──────────────────────┐  ┌─────────────────────────┐                        │
│  │ λ kb-reader          │  │ λ threshold-calculator  │                        │
│  │                      │  │                         │                        │
│  │ • Query Bedrock      │  │ • Compute adaptive      │                        │
│  │   Knowledge Base     │  │   thresholds            │                        │
│  │ • Retrieve DQ        │  │ • Day 1/7/15/30         │                        │
│  │   best practices     │  │   baseline calc         │                        │
│  │ • Domain-specific    │  │ • Growth detection      │                        │
│  │   rules reference    │  │ • Anomaly sensitivity   │                        │
│  │                      │  │   tuning                │                        │
│  └──────────────────────┘  └─────────────────────────┘                        │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## Agent 3: Rule Executor — Helper Lambdas (Detail)

```
┌────────────────────────────────────────────────────────────────────────────────┐
│  AGENT 3: RULE EXECUTOR — Helper Lambdas                                       │
│                                                                                │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────────┐       │
│  │ λ query-executor │  │ λ score-computer │  │ λ alert-dispatcher     │       │
│  │                  │  │                  │  │                        │       │
│  │ • Run SQL/Athena │  │ • Calculate DQ   │  │ • SNS notifications   │       │
│  │   queries        │  │   score per      │  │ • Slack/Teams alerts  │       │
│  │ • Execute Spark  │  │   dimension      │  │ • Email summaries     │       │
│  │   validations    │  │ • Weighted       │  │ • PagerDuty triggers  │       │
│  │ • Timeout        │  │   scoring model  │  │ • Quarantine bad      │       │
│  │   management     │  │ • Trend analysis │  │   records             │       │
│  └──────────────────┘  └──────────────────┘  └────────────────────────┘       │
│                                                                                │
│  ┌──────────────────────┐  ┌─────────────────────────┐                        │
│  │ λ baseline-updater   │  │ λ result-writer         │                        │
│  │                      │  │                         │                        │
│  │ • Update Day 1/7/    │  │ • Write results to      │                        │
│  │   15/30 baselines    │  │   DynamoDB              │                        │
│  │ • Recalculate        │  │ • Store execution       │                        │
│  │   adaptive           │  │   history               │                        │
│  │   thresholds         │  │ • Generate audit        │                        │
│  │ • Persist metrics    │  │   trail                 │                        │
│  │                      │  │ • Status payload for    │                        │
│  │                      │  │   API response          │                        │
│  └──────────────────────┘  └─────────────────────────┘                        │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## Response Flow (Back to Caller)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         RESPONSE PAYLOAD                                 │
│                                                                         │
│  Agent 3 (Executor)                                                     │
│       │                                                                 │
│       ▼                                                                 │
│  Supervisor Agent                                                       │
│       │                                                                 │
│       ▼                                                                 │
│  Orchestrator Lambda                                                    │
│       │                                                                 │
│       ▼                                                                 │
│  API Gateway → Caller (Airflow / Step Functions / External API)         │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────┐      │
│  │  Response Body:                                               │      │
│  │                                                               │      │
│  │  {                                                            │      │
│  │    "status": "PASS | FAIL | ALERT",                           │      │
│  │    "dataset": "s3://bucket/path/to/dataset",                  │      │
│  │    "timestamp": "2026-07-30T10:00:00Z",                       │      │
│  │    "dq_score": 94.5,                                          │      │
│  │    "rules_evaluated": 12,                                     │      │
│  │    "rules_passed": 11,                                        │      │
│  │    "rules_failed": 1,                                         │      │
│  │    "failures": [                                              │      │
│  │      {                                                        │      │
│  │        "rule": "null_check_email",                            │      │
│  │        "expected": "< 2%",                                    │      │
│  │        "actual": "5.3%",                                      │      │
│  │        "severity": "CRITICAL"                                 │      │
│  │      }                                                        │      │
│  │    ],                                                         │      │
│  │    "baseline_period": "day_30",                               │      │
│  │    "adaptive_threshold_applied": true                         │      │
│  │  }                                                            │      │
│  └───────────────────────────────────────────────────────────────┘      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Adaptive Baseline Strategy

```
┌─────────────────────────────────────────────────────────────┐
│                  ADAPTIVE BASELINE WINDOWS                    │
│                                                             │
│  Day 1  ──▶  Immediate snapshot (current run)               │
│  Day 7  ──▶  Weekly rolling average                         │
│  Day 15 ──▶  Biweekly trend detection                       │
│  Day 30 ──▶  Monthly baseline (stability reference)         │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  ADAPTIVE LOGIC:                                    │    │
│  │                                                     │    │
│  │  IF business_growth_detected:                       │    │
│  │     thresholds = recalculate(growth_rate,           │    │
│  │                              historical_trend,      │    │
│  │                              seasonal_pattern)      │    │
│  │                                                     │    │
│  │  IF anomaly_outside_adaptive_range:                 │    │
│  │     status = ALERT or FAIL                          │    │
│  │     trigger_notification()                          │    │
│  │                                                     │    │
│  │  IF consistent_shift_over_7_days:                   │    │
│  │     update_baseline()                               │    │
│  │     notify_stakeholders()                           │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Decision Flow: When is Each Agent Called?

```
┌────────────────────────────────────────────────────────────────────────┐
│                      SUPERVISOR DECISION TREE                           │
│                                                                        │
│  Request arrives at Supervisor                                         │
│       │                                                                │
│       ├── Check: Does dataset have existing rules?                     │
│       │       │                                                        │
│       │       ├── NO  ──────────────────────▶ Call Agent 2 (Profiler)  │
│       │       │                                                        │
│       │       └── YES                                                  │
│       │            │                                                   │
│       │            ├── Check: Schema changed?                          │
│       │            │       │                                           │
│       │            │       ├── YES ──────────▶ Call Agent 2 (Profiler) │
│       │            │       │                                           │
│       │            │       └── NO                                      │
│       │            │            │                                      │
│       │            │            ├── Check: Force re-profile flag?      │
│       │            │            │       │                              │
│       │            │            │       ├── YES ─▶ Call Agent 2        │
│       │            │            │       │                              │
│       │            │            │       └── NO                         │
│       │            │            │            │                         │
│       │            │            │            ▼                         │
│       │            │            │     Skip Agent 2                     │
│       │            │            │                                      │
│       └────────────┴────────────┴─────────────┐                       │
│                                               │                       │
│                                               ▼                       │
│                                    ┌──────────────────┐               │
│                                    │  ALWAYS call     │               │
│                                    │  Agent 3         │               │
│                                    │  (Rule Executor) │               │
│                                    └────────┬─────────┘               │
│                                             │                         │
│                                             ▼                         │
│                                    Return PASS / FAIL / ALERT         │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Data & Storage Layer

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              DATA & STORAGE LAYER                                        │
│                                                                                         │
│  ┌───────────────┐  ┌───────────────────┐  ┌───────────────┐  ┌─────────────────────┐  │
│  │    AWS S3     │  │    DynamoDB       │  │   Bedrock     │  │   CloudWatch /      │  │
│  │               │  │                   │  │  Knowledge    │  │   S3 (Results)      │  │
│  │ • Source data │  │ • Rules table     │  │    Base       │  │                     │  │
│  │ • Profiling   │  │ • Baselines       │  │               │  │ • DQ scores history │  │
│  │   results     │  │   (1/7/15/30 day) │  │ • DQ best     │  │ • Execution logs    │  │
│  │ • Quarantine  │  │ • Execution       │  │   practices   │  │ • Audit trail       │  │
│  │   bucket      │  │   history         │  │ • Domain      │  │ • Metrics &         │  │
│  │               │  │ • Dataset         │  │   rules       │  │   dashboards        │  │
│  │               │  │   metadata        │  │ • Thresholds  │  │                     │  │
│  │               │  │ • Schema versions │  │               │  │                     │  │
│  └───────────────┘  └───────────────────┘  └───────────────┘  └─────────────────────┘  │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Helper Lambda Summary

| Agent | Lambda | Purpose |
|-------|--------|---------|
| Supervisor | `metadata-lookup` | Query DynamoDB for existing rules & dataset info |
| Supervisor | `schema-detector` | Compare current vs stored schema, detect changes |
| Supervisor | `rule-validator` | Validate generated rules before execution |
| Rule Generator | `data-profiler` | Trigger DataBrew/Glue profile jobs, sample data |
| Rule Generator | `stats-aggregator` | Compute 30-day rolling stats (min/max/median/avg/nulls) |
| Rule Generator | `kb-reader` | Query Bedrock Knowledge Base for DQ standards |
| Rule Generator | `threshold-calculator` | Compute adaptive thresholds with growth detection |
| Rule Generator | `rule-writer` | Persist rules + metadata to DynamoDB |
| Rule Executor | `query-executor` | Run DQ queries via Athena/Spark |
| Rule Executor | `score-computer` | Calculate weighted DQ scores per dimension |
| Rule Executor | `alert-dispatcher` | Send alerts (SNS/Slack/Email/PagerDuty) |
| Rule Executor | `baseline-updater` | Update Day 1/7/15/30 adaptive baselines |
| Rule Executor | `result-writer` | Store results, audit trail, build API response |

---

## Data Flow Summary

1. **Trigger** → API Gateway / S3 Event → Orchestrator Lambda
2. **Supervisor** → Checks rules + schema → Routes accordingly
3. **Rule Generator** (conditional) → Profiles → Generates → Stores rules
4. **Supervisor** → Verifies generated rules
5. **Rule Executor** (always) → Executes rules → Scores → Determines status
6. **Response** → PASS / FAIL / ALERT → returned to calling system
