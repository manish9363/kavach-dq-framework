"""CDK App entry point - multi-environment deployment."""

import json
import sys
from pathlib import Path

import aws_cdk as cdk

from stacks.storage_stack import StorageStack


# Load environment config
config_path = Path(__file__).parent / "config" / "environments.json"
with open(config_path) as f:
    all_config = json.load(f)

app = cdk.App()

# Get target environment from context: cdk deploy -c env=dev
target_env = app.node.try_get_context("env") or "dev"

if target_env not in all_config:
    print(f"Error: Unknown environment '{target_env}'. Use: dev, beta, or prod")
    sys.exit(1)

config = all_config[target_env]

env = cdk.Environment(
    account=config["account"],
    region=config["region"],
)

# Stack naming: kavach-{env}-{stack}
prefix = f"kavach-{config['environment']}"

# Phase 1: Storage
storage = StorageStack(
    app,
    f"{prefix}-storage",
    env=env,
    config=config,
)

# Phase 2: Lambdas (coming next)
# lambdas = LambdaStack(app, f"{prefix}-lambdas", storage=storage, config=config, env=env)

# Phase 3: Agents (coming next)
# agents = AgentsStack(app, f"{prefix}-agents", lambdas=lambdas, config=config, env=env)

# Phase 4: API (coming next)
# api = ApiStack(app, f"{prefix}-api", agents=agents, config=config, env=env)

# Phase 5: UI (coming next)
# ui = UiStack(app, f"{prefix}-ui", api=api, config=config, env=env)

# Apply tags to all resources
for key, value in config.get("tags", {}).items():
    cdk.Tags.of(app).add(key, value)

app.synth()
