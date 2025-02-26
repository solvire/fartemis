"""
AWS Paramater Store Loader
Author: Steve
Date: 2022-04-11

Assumes at least the SSM_ENVIRONMENT variable of environment is loaded.
- local
- dev
- qa
- prod

These variables are associated to the buckets in SSM "parameter store"

Using onboard EC2 creds
"""
import boto3
import os
from ssm_parameter_store import EC2ParameterStore


def get_default_region() -> str:
    aws_session = boto3.session.Session()
    if "AWS_S3_REGION_NAME" in os.environ and os.environ["AWS_S3_REGION_NAME"]:
        return os.environ["AWS_S3_REGION_NAME"]
    # try to load the region name here
    os.environ["AWS_S3_REGION_NAME"] = aws_session.region_name
    return aws_session.region_name


def get_aws_credentials() -> str:
    aws_session = boto3.session.Session()
    return aws_session.get_credentials()


def load_env_from_ssm(path_prefix, region_name):
    # TODO: remove this
    return
    # Load parameters from SSM Parameter Store starting with path.
    # Populate the config dict using keys from the path after the path_prefix
    store = EC2ParameterStore(region_name=region_name)
    parameters = store.get_parameters_by_path(path_prefix, recursive=True)
    if len(parameters) > 0:
        EC2ParameterStore.set_env(parameters)

    # for the assumed variables lets set these here
    credentials = get_aws_credentials()
    os.environ["AWS_ACCESS_KEY_ID"] = credentials.access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = credentials.secret_key
