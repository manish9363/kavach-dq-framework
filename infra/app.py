"""CDK App entry point."""

import aws_cdk as cdk

from stacks.api_stack import ApiStack
from stacks.agents_stack import AgentsStack
from stacks.storage_stack import StorageStack
from stacks.lambda_stack import LambdaStack
from stacks.ui_stack import UiStack

app = cdk.App()

env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "us-east-1",
)

storage = StorageStack(app, "KavachStorageStack", env=env)
lambdas = LambdaStack(app, "KavachLambdaStack", storage=storage, env=env)
agents = AgentsStack(app, "KavachAgentsStack", lambdas=lambdas, env=env)
api = ApiStack(app, "KavachApiStack", agents=agents, env=env)
ui = UiStack(app, "KavachUiStack", api=api, env=env)

app.synth()
