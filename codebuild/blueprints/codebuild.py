#!/usr/bin/env python
"""Module with CodeBuild project."""
from __future__ import print_function

from troposphere import (
    AccountId, Join, Partition, Region, iam, codebuild, Sub
)

import awacs.codebuild

from awacs import (
    logs, cloudformation, dynamodb, s3
)

from awacs.aws import Action, Allow, Deny, PolicyDocument, Statement
from awacs.helpers.trust import make_simple_assume_policy

from stacker.blueprints.base import Blueprint
from stacker.blueprints.variables.types import CFNString

# The github accounts that are allowed to trigger the
# build tests
GITHUB_ACCOUNT_IDS = [627555]


class CodeBuild(Blueprint):
    """Stacker blueprint for CodeBuild project."""

    VARIABLES = {
        'EnvironmentName': {'type': CFNString,
                            'description': 'Name of environment'},
        'GitHubUrl': {'type': CFNString,
                      'description': 'URL to GitHub repository'}
    }

    def create_template(self):
        """Create template (main function called by Stacker)."""
        template = self.template
        variables = self.get_variables()
        template.set_version('2010-09-09')
        template.set_description('Runway CodeBuild Project')

        # Resources
        deploy_name = 'runway-integration-tests'

        # This must match what is in the the Terraform
        # integration tests. This corresponds to the template listed in
        # integration_tests\test_terraform\tf_state.cfn
        test_suite_prefix = 'testsuite-tf-state'
        codebuild_role = template.add_resource(
            iam.Role(
                'CodeBuildRole',
                AssumeRolePolicyDocument=make_simple_assume_policy(
                    'codebuild.amazonaws.com'
                ),
                Policies=[
                    iam.Policy(
                        PolicyName=Join('', [deploy_name, '-policy']),
                        PolicyDocument=PolicyDocument(
                            Version='2012-10-17',
                            Statement=[
                                Statement(
                                    Action=[
                                        awacs.logs.CreateLogGroup,
                                        awacs.logs.CreateLogStream,
                                        awacs.logs.PutLogEvents
                                    ],
                                    Effect=Allow,
                                    Resource=[
                                        Join(
                                            '',
                                            [
                                                'arn:',
                                                Partition,
                                                ':logs:',
                                                Region,
                                                ':',
                                                AccountId,
                                                ':log-group:/aws/codebuild/',
                                                deploy_name,
                                                '*'
                                            ] + x
                                        ) for x in [[':*'], [':*/*']]
                                    ]
                                ),
                                Statement(
                                    Action=[Action('cloudformation', '*')],
                                    Effect=Allow,
                                    Resource=[
                                        Join(':', ['arn', Partition, 'cloudformation',
                                                   Region, AccountId,
                                                   Sub('stack/${prefix}/*',
                                                       {'prefix': test_suite_prefix})])
                                    ]
                                ),
                                Statement(
                                    Action=[Action('cloudformation', '*')],
                                    Effect=Deny,
                                    NotResource=[
                                        Join(':', ['arn', Partition, 'cloudformation',
                                                   Region, AccountId,
                                                   Sub('stack/${prefix}/*',
                                                       {'prefix': test_suite_prefix})])
                                    ]
                                ),
                                Statement(
                                    Action=[Action('dynamodb', '*')],
                                    Effect=Allow,
                                    Resource=[
                                        Join(':', ['arn', Partition, 'dynamodb',
                                                   Region, AccountId,
                                                   Sub('table/${prefix}-*',
                                                       {'prefix': test_suite_prefix})])
                                    ]
                                ),
                                Statement(
                                    Action=[Action('dynamodb', '*')],
                                    Effect=Deny,
                                    NotResource=[
                                        Join(':', ['arn', Partition, 'dynamodb',
                                                   Region, AccountId,
                                                   Sub('table/${prefix}-*',
                                                       {'prefix': test_suite_prefix})])
                                    ]
                                ),
                                Statement(
                                    Action=[Action('s3', '*')],
                                    Effect=Allow,
                                    Resource=[
                                        Join(':', ['arn', Partition,
                                                   Sub('s3:::${prefix}',
                                                       {'prefix': test_suite_prefix})]),
                                        Join(':', ['arn', Partition,
                                                   Sub('s3:::${prefix}/*',
                                                       {'prefix': test_suite_prefix})])
                                    ]
                                ),
                                Statement(
                                    Action=[Action('s3', '*')],
                                    Effect=Deny,
                                    NotResource=[
                                        Join(':', ['arn', Partition,
                                                   Sub('s3:::${prefix}',
                                                       {'prefix': test_suite_prefix})]),
                                        Join(':', ['arn', Partition,
                                                   Sub('s3:::${prefix}/*',
                                                       {'prefix': test_suite_prefix})])
                                    ]
                                ),
                                Statement(
                                    Action=[Action('sqs', '*')],
                                    Effect=Allow,
                                    Resource=[
                                        Join(':', ['arn', Partition, 'sqs', Region, AccountId,
                                                   'terraform-*'])
                                    ]
                                )
                            ]
                        )
                    )
                ]
            )
        )

        template.add_resource(
            codebuild.Project(
                'RunwayIntegrationTests',
                Artifacts=codebuild.Artifacts(
                    Type='NO_ARTIFACTS'
                ),
                Environment=codebuild.Environment(
                    ComputeType='BUILD_GENERAL1_SMALL',
                    EnvironmentVariables=[
                        codebuild.EnvironmentVariable(
                            Name='CI',
                            Type='PLAINTEXT',
                            Value='1'
                        ),
                        codebuild.EnvironmentVariable(
                            Name='DEPLOY_ENVIRONMENT',
                            Type='PLAINTEXT',
                            Value=variables['EnvironmentName'].ref
                        )
                    ],
                    Image='aws/codebuild/standard:2.0',
                    Type='LINUX_CONTAINER'
                ),
                Name=deploy_name,
                ServiceRole=codebuild_role.get_att('Arn'),
                Source=codebuild.Source(
                    Type='GITHUB',
                    Location=variables['GitHubUrl'].ref
                ),
                Triggers=codebuild.ProjectTriggers(
                    Webhook=True,
                    FilterGroups=[
                        [
                            codebuild.WebhookFilter(
                                Type='ACTOR_ACCOUNT_ID',
                                Pattern='|'.join(str(x) for x in GITHUB_ACCOUNT_IDS)
                            ),
                            codebuild.WebhookFilter(
                                Type='EVENT',
                                Pattern='PULL_REQUEST_CREATED,PULL_REQUEST_UPDATED,PULL_REQUEST_REOPENED' # noqa
                            ),
                            codebuild.WebhookFilter(
                                Type='BASE_REF',
                                Pattern='^refs/heads/release$'
                            ),
                            codebuild.WebhookFilter(
                                Type='HEAD_REF',
                                Pattern='^refs/heads/master$'
                            )
                        ]
                    ]
                )
            )
        )


if __name__ == "__main__":
    from stacker.context import Context
    print(CodeBuild('test', Context({"namespace": "test"}), None).to_json())
