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
