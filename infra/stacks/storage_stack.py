"""Storage Stack - S3 buckets and DynamoDB tables for Kavach DQ Framework.

S3 Bucket Structure:
  kavach-{env}-dq/
  ├── raw/{team_id}/{dataset}/         # Source data landing zone per team
  ├── profiling/{team_id}/{dataset}/   # DataBrew/Glue profile outputs per team
  ├── quarantine/{team_id}/{dataset}/  # Failed/bad records per team
  ├── results/{team_id}/{dataset}/     # DQ execution results per team
  ├── baselines/{team_id}/{dataset}/   # Baseline snapshots per team
  ├── reports/{team_id}/{dataset}/     # Generated DQ reports per team
  ├── knowledge-base/{team_id}/        # DQ rules reference docs per team (for Bedrock KB)
  └── customer-feedback/{team_id}/     # Customer feedback data per team

DynamoDB Tables:
  1. Master Table       - Dataset registry (enabled/disabled, baseline config)
  2. Rules Table        - DQ rules with queries per dataset
  3. Execution Table    - Run stats (pass/fail/score per execution)
  4. Feedback Table     - User feedback on rules and results
"""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
)
from constructs import Construct


class StorageStack(Stack):
    """All persistent storage resources for Kavach DQ Framework."""

    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        env_name = config["environment"]
        removal = (
            RemovalPolicy.DESTROY if config.get("removal_policy") == "DESTROY"
            else RemovalPolicy.RETAIN
        )

        # ============================================================
        # S3 BUCKET (single bucket with prefixes for DQ operations)
        # ============================================================

        self.dq_bucket = s3.Bucket(
            self,
            "DqBucket",
            bucket_name=f"kavach-{env_name}-dq-{config['account']}",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=removal,
            auto_delete_objects=(removal == RemovalPolicy.DESTROY),
            lifecycle_rules=[
                # Move profiling results to IA after 30 days
                s3.LifecycleRule(
                    id="profiling-to-ia",
                    prefix="profiling/",
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after_creation=Duration.days(30),
                        )
                    ],
                    expiration=Duration.days(180),
                ),
                # Quarantine expires after 90 days
                s3.LifecycleRule(
                    id="quarantine-expiry",
                    prefix="quarantine/",
                    expiration=Duration.days(90),
                ),
                # Results kept for 1 year then archived
                s3.LifecycleRule(
                    id="results-archive",
                    prefix="results/",
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after_creation=Duration.days(365),
                        )
                    ],
                ),
            ],
        )

        # ============================================================
        # DYNAMODB TABLE 1: MASTER TABLE (Dataset Registry)
        # ============================================================
        # Tracks all registered datasets, whether DQ is enabled,
        # baseline configuration, owner, schedule, etc.
        #
        # Example item:
        # {
        #   "dataset_id": "s3://bucket/path/to/dataset",
        #   "dataset_name": "customer_orders",
        #   "dq_enabled": true,
        #   "baseline_days": [1, 7, 15, 30],
        #   "team_id": "data-engineering",
        #   "team_name": "Data Engineering",
        #   "owner": "manish@company.com",
        #   "business_unit": "finance",
        #   "domain": "orders",
        #   "priority": "P1",                        # P1/P2/P3
        #   "notification_channels": ["slack:#dq-alerts", "email:team@co.com"],
        #   "schedule": "daily",
        #   "schedule_cron": "0 6 * * *",
        #   "sla_minutes": 30,
        #   "last_profiled_at": "2026-07-30T10:00:00Z",
        #   "last_schema_hash": "abc123",
        #   "schema_columns": ["id", "email", "amount", "created_at"],
        #   "tags": {"compliance": "pii", "source": "postgres"},
        #   "created_by": "manish@company.com",
        #   "created_at": "2026-06-01T00:00:00Z",
        #   "updated_at": "2026-07-30T10:00:00Z"
        # }

        self.master_table = dynamodb.Table(
            self,
            "MasterTable",
            table_name=f"kavach-{env_name}-master",
            partition_key=dynamodb.Attribute(
                name="dataset_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal,
            point_in_time_recovery=True,
        )

        # GSI: lookup by owner
        self.master_table.add_global_secondary_index(
            index_name="owner-index",
            partition_key=dynamodb.Attribute(
                name="owner", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="dataset_name", type=dynamodb.AttributeType.STRING
            ),
        )

        # GSI: lookup by team
        self.master_table.add_global_secondary_index(
            index_name="team-index",
            partition_key=dynamodb.Attribute(
                name="team_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="dataset_name", type=dynamodb.AttributeType.STRING
            ),
        )

        # GSI: lookup by business unit
        self.master_table.add_global_secondary_index(
            index_name="business-unit-index",
            partition_key=dynamodb.Attribute(
                name="business_unit", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="updated_at", type=dynamodb.AttributeType.STRING
            ),
        )

        # GSI: lookup by domain
        self.master_table.add_global_secondary_index(
            index_name="domain-index",
            partition_key=dynamodb.Attribute(
                name="domain", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="dataset_name", type=dynamodb.AttributeType.STRING
            ),
        )

        # GSI: lookup by dq_enabled status
        self.master_table.add_global_secondary_index(
            index_name="enabled-index",
            partition_key=dynamodb.Attribute(
                name="dq_enabled_str", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="updated_at", type=dynamodb.AttributeType.STRING
            ),
        )

        # ============================================================
        # DYNAMODB TABLE 2: RULES TABLE
        # ============================================================
        # Stores all generated DQ rules with their executable queries.
        #
        # Example item:
        # {
        #   "dataset_id": "s3://bucket/path/to/dataset",
        #   "rule_id": "rule_001_null_check_email",
        #   "rule_name": "Email Null Check",
        #   "rule_type": "completeness",         # completeness/accuracy/consistency/timeliness/uniqueness/validity
        #   "column": "email",
        #   "query": "SELECT COUNT(*) FROM dataset WHERE email IS NULL",
        #   "threshold": "< 2%",
        #   "severity": "CRITICAL",              # CRITICAL / WARNING / INFO
        #   "status": "active",                  # active / inactive / draft
        #   "version": 3,
        #   "baseline_reference": "day_30",
        #   "adaptive_threshold": 2.5,
        #   "team_id": "data-engineering",
        #   "created_by": "agent",               # agent / manual / user_email
        #   "approved_by": "manish@company.com",
        #   "tags": {"domain": "orders", "compliance": "soc2"},
        #   "created_at": "2026-07-01T00:00:00Z",
        #   "updated_at": "2026-07-30T10:00:00Z"
        # }

        self.rules_table = dynamodb.Table(
            self,
            "RulesTable",
            table_name=f"kavach-{env_name}-rules",
            partition_key=dynamodb.Attribute(
                name="dataset_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="rule_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal,
            point_in_time_recovery=True,
        )

        # GSI: filter rules by type
        self.rules_table.add_global_secondary_index(
            index_name="type-index",
            partition_key=dynamodb.Attribute(
                name="rule_type", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at", type=dynamodb.AttributeType.STRING
            ),
        )

        # GSI: filter rules by status
        self.rules_table.add_global_secondary_index(
            index_name="status-index",
            partition_key=dynamodb.Attribute(
                name="status", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="updated_at", type=dynamodb.AttributeType.STRING
            ),
        )

        # ============================================================
        # DYNAMODB TABLE 3: EXECUTION TABLE (Run Stats)
        # ============================================================
        # Stores results of every DQ execution run.
        #
        # Example item:
        # {
        #   "dataset_id": "s3://bucket/path/to/dataset",
        #   "execution_id": "exec_2026-07-30_001",
        #   "status": "FAIL",                    # PASS / FAIL / ALERT
        #   "dq_score": 87.5,
        #   "rules_evaluated": 12,
        #   "rules_passed": 10,
        #   "rules_failed": 2,
        #   "failures": [...],
        #   "team_id": "data-engineering",
        #   "triggered_by": "airflow",           # airflow / step-function / api / s3-event
        #   "triggered_by_user": "manish@company.com",
        #   "baseline_period": "day_30",
        #   "adaptive_threshold_applied": true,
        #   "record_count": 1500000,
        #   "execution_duration_ms": 4500,
        #   "executed_at": "2026-07-30T10:05:00Z",
        #   "ttl": 1753920000
        # }

        self.execution_table = dynamodb.Table(
            self,
            "ExecutionTable",
            table_name=f"kavach-{env_name}-executions",
            partition_key=dynamodb.Attribute(
                name="dataset_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="execution_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal,
            time_to_live_attribute="ttl",
        )

        # GSI: query by execution timestamp for trending
        self.execution_table.add_global_secondary_index(
            index_name="timestamp-index",
            partition_key=dynamodb.Attribute(
                name="dataset_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="executed_at", type=dynamodb.AttributeType.STRING
            ),
        )

        # GSI: query by status across all datasets
        self.execution_table.add_global_secondary_index(
            index_name="status-index",
            partition_key=dynamodb.Attribute(
                name="status", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="executed_at", type=dynamodb.AttributeType.STRING
            ),
        )

        # GSI: query executions by team
        self.execution_table.add_global_secondary_index(
            index_name="team-index",
            partition_key=dynamodb.Attribute(
                name="team_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="executed_at", type=dynamodb.AttributeType.STRING
            ),
        )

        # ============================================================
        # DYNAMODB TABLE 4: FEEDBACK TABLE (User Feedback)
        # ============================================================
        # Stores user feedback on rules and DQ results.
        # Used to improve rule generation over time (reinforcement).
        #
        # Example item:
        # {
        #   "feedback_id": "fb_2026-07-30_001",
        #   "dataset_id": "s3://bucket/path/to/dataset",
        #   "rule_id": "rule_001_null_check_email",
        #   "execution_id": "exec_2026-07-30_001",
        #   "feedback_type": "false_positive",   # false_positive / false_negative / threshold_adjust / rule_approve / rule_reject
        #   "team_id": "data-engineering",
        #   "user_id": "manish@company.com",
        #   "user_role": "data_engineer",        # data_engineer / analyst / manager / admin
        #   "comment": "This threshold is too strict for marketing emails",
        #   "suggested_threshold": "< 5%",
        #   "action_taken": "threshold_updated", # threshold_updated / rule_disabled / rule_modified / no_action
        #   "resolved_by": "system",             # system / user_email
        #   "created_at": "2026-07-30T11:00:00Z"
        # }

        self.feedback_table = dynamodb.Table(
            self,
            "FeedbackTable",
            table_name=f"kavach-{env_name}-feedback",
            partition_key=dynamodb.Attribute(
                name="feedback_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal,
            point_in_time_recovery=True,
        )

        # GSI: lookup feedback by dataset
        self.feedback_table.add_global_secondary_index(
            index_name="dataset-index",
            partition_key=dynamodb.Attribute(
                name="dataset_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at", type=dynamodb.AttributeType.STRING
            ),
        )

        # GSI: lookup feedback by rule
        self.feedback_table.add_global_secondary_index(
            index_name="rule-index",
            partition_key=dynamodb.Attribute(
                name="rule_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at", type=dynamodb.AttributeType.STRING
            ),
        )

        # GSI: lookup by feedback type (to find all false positives, etc.)
        self.feedback_table.add_global_secondary_index(
            index_name="type-index",
            partition_key=dynamodb.Attribute(
                name="feedback_type", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at", type=dynamodb.AttributeType.STRING
            ),
        )

        # GSI: lookup feedback by team
        self.feedback_table.add_global_secondary_index(
            index_name="team-index",
            partition_key=dynamodb.Attribute(
                name="team_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at", type=dynamodb.AttributeType.STRING
            ),
        )

        # ============================================================
        # S3 PREFIX INITIALIZATION (Custom Resource)
        # ============================================================
        # S3 doesn't have real "folders" — prefixes are created by
        # placing a zero-byte object. This ensures the prefix structure
        # is visible in the console and ready for use.

        from aws_cdk import (
            CustomResource,
            custom_resources as cr,
            aws_lambda as _lambda,
            aws_iam as iam,
        )

        # Lambda that creates prefix markers in S3
        prefix_init_fn = _lambda.Function(
            self,
            "PrefixInitFunction",
            function_name=f"kavach-{env_name}-s3-prefix-init",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=_lambda.Code.from_inline(
                """
import boto3
import cfnresponse

def handler(event, context):
    if event['RequestType'] in ['Create', 'Update']:
        s3 = boto3.client('s3')
        bucket = event['ResourceProperties']['BucketName']
        prefixes = event['ResourceProperties']['Prefixes']
        for prefix in prefixes:
            s3.put_object(Bucket=bucket, Key=f"{prefix}/.keep", Body=b'')
    cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
"""
            ),
            timeout=Duration.seconds(30),
        )

        # Grant the lambda permission to write to the bucket
        self.dq_bucket.grant_write(prefix_init_fn)

        # Custom resource provider
        provider = cr.Provider(
            self,
            "PrefixInitProvider",
            on_event_handler=prefix_init_fn,
        )

        # Create the prefixes (top-level only; team subfolders created dynamically)
        # Convention: {prefix}/{team_id}/{dataset_name}/
        # Example: profiling/data-engineering/customer_orders/
        CustomResource(
            self,
            "PrefixInit",
            service_token=provider.service_token,
            properties={
                "BucketName": self.dq_bucket.bucket_name,
                "Prefixes": [
                    "raw",
                    "profiling",
                    "quarantine",
                    "results",
                    "baselines",
                    "reports",
                    "knowledge-base",
                    "customer-feedback",
                ],
            },
        )
