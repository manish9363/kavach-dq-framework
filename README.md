# Kavach DQ Framework

Agentic Data Quality tool powered by AWS Bedrock with multi-agent architecture and adaptive baselines.

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full system design.

## Project Structure

```
kavach-dq-framework/
├── kavach/                  # Core Python package
│   ├── agents/             # Bedrock Agent definitions
│   └── lambdas/            # Lambda function handlers
│       ├── orchestrator.py # Entry point Lambda
│       ├── supervisor/     # Agent 1 helper lambdas
│       ├── rule_generator/ # Agent 2 helper lambdas
│       └── rule_executor/  # Agent 3 helper lambdas
├── infra/                  # AWS CDK infrastructure
│   ├── app.py             # CDK entry point
│   └── stacks/            # CDK stack definitions
├── ui/                     # React + Vite dashboard
│   └── src/
├── tests/                  # Unit and integration tests
├── docs/                   # Documentation
└── pyproject.toml          # Python project config
```

## Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- AWS CDK CLI
- AWS account with Bedrock access

### Setup
```bash
# Backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# UI
cd ui && npm install

# Infrastructure
cd infra && cdk synth
```

## License

MIT

## Schema Change Detection

The supervisor schema helper accepts column-name-to-type mappings and reports added,
removed, and type-modified columns. A missing baseline always requests initial profiling;
an unchanged baseline skips re-profiling. Column order is ignored, while column names
and type strings are compared exactly.

```python
from kavach.lambdas.supervisor.schema_detector import detect_schema_changes

result = detect_schema_changes(
    current_schema={"id": "bigint", "email": "string"},
    stored_schema={"id": "int"},
)
assert result["requires_reprofiling"] is True
assert result["added_columns"] == ["email"]
assert result["modified_columns"]["id"]["previous_type"] == "int"
```

For direct Lambda invocation, use `schema_detector.handler` with an event containing
`current_schema` and optional `stored_schema`. The caller supplies the baseline; the
helper does not retrieve or persist metadata. Deployment and supervisor wiring remain
part of the future Lambda/agent stacks. Invalid schemas raise `TypeError` or `ValueError`.

Run the unit tests locally with `python -m pytest tests/unit` after installing the
development dependencies.
