# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
from __future__ import absolute_import

import os

import pytest
from mock import Mock, patch
from sagemaker.s3 import (
    S3DataType,
    S3InputMode,
    S3DownloadMode,
    S3DataDistributionType,
    S3CompressionType,
    S3UploadMode,
)

from sagemaker.processor import FileInput, FileOutput, Processor
from sagemaker.sklearn.processor import SKLearnProcessor
from sagemaker.sparkml.processor import SparkMLJavaProcessor, SparkMLPythonProcessor
from sagemaker.network import NetworkConfig

BUCKET_NAME = "mybucket"
REGION = "us-west-2"
ROLE = "arn:aws:iam::012345678901:role/SageMakerRole"
CUSTOM_IMAGE_URI = "012345678901.dkr.ecr.us-west-2.amazonaws.com/my-custom-image-uri"


@pytest.fixture()
def sagemaker_session():
    boto_mock = Mock(name="boto_session", region_name=REGION)
    session_mock = Mock(
        name="sagemaker_session",
        boto_session=boto_mock,
        boto_region_name=REGION,
        config=None,
        local_mode=False,
    )
    session_mock.default_bucket = Mock(name="default_bucket", return_value=BUCKET_NAME)
    session_mock.upload_data = Mock(
        name="upload_data", return_value="mocked_s3_uri_from_upload_data"
    )
    session_mock.download_data = Mock(name="download_data")
    return session_mock


def test_sklearn(sagemaker_session):
    sklearn_processor = SKLearnProcessor(
        framework_version="0.20.0",
        role=ROLE,
        processing_instance_type="ml.m4.xlarge",
        sagemaker_session=sagemaker_session,
    )

    with patch("os.path.isfile", return_value=True):
        sklearn_processor.run(
            source="/local/path/to/sklearn_transformer.py",
            inputs=[FileInput(source="/local/path/to/my/dataset/census.csv", destination="/data/")],
        )

    expected_args = {
        "inputs": [
            {
                "InputName": "input-1",
                "S3Input": {
                    "S3Uri": "mocked_s3_uri_from_upload_data",
                    "LocalPath": "/data/",
                    "S3DataType": "ManifestFile",
                    "S3InputMode": "File",
                    "S3DownloadMode": "Continuous",
                    "S3DataDistributionType": "FullyReplicated",
                    "S3CompressionType": "None",
                },
            },
            {
                "InputName": "source",
                "S3Input": {
                    "S3Uri": "mocked_s3_uri_from_upload_data",
                    "LocalPath": "/code/source",
                    "S3DataType": "ManifestFile",
                    "S3InputMode": "File",
                    "S3DownloadMode": "Continuous",
                    "S3DataDistributionType": "FullyReplicated",
                    "S3CompressionType": "None",
                },
            },
        ],
        "outputs": [],
        "job_name": sklearn_processor._current_job_name,
        "resources": {
            "ClusterConfig": {
                "InstanceType": "ml.m4.xlarge",
                "InstanceCount": 1,
                "VolumeSizeInGB": 30,
            }
        },
        "stopping_condition": {"MaxRuntimeInSeconds": 24 * 60 * 60},
        "app_specification": {
            "ImageUri": "520713654638.dkr.ecr.us-west-2.amazonaws.com/sagemaker-sklearn:0.20.0-cpu-py3",
            "ContainerEntrypoint": ["python3", "/code/source/sklearn_transformer.py"],
        },
        "environment": None,
        "network_config": None,
        "role_arn": ROLE,
        "tags": None,
    }
    sagemaker_session.process.assert_called_with(**expected_args)


def test_sklearn_with_all_customizations(sagemaker_session):
    sklearn_processor = SKLearnProcessor(
        framework_version="0.20.0",
        role=ROLE,
        processing_instance_type="ml.m4.xlarge",
        py_version="py3",
        arguments=["--drop-columns", "'SelfEmployed'"],
        processing_volume_size_in_gb=100,
        processing_volume_kms_key=None,
        processing_max_runtime_in_seconds=3600,
        base_job_name="my_sklearn_processor",
        env={"my_env_variable": 20},
        tags=[{"Name": "my-tag", "Value": "my-tag-value"}],
        network_config=NetworkConfig(
            subnets=["my_subnet_id"],
            security_group_ids=["my_security_group_id"],
            enable_network_isolation=True,
            encrypt_inter_container_traffic=True,
        ),
        sagemaker_session=sagemaker_session,
    )

    with patch("os.path.isdir", return_value=True):
        sklearn_processor.run(
            source="/local/path/to/code",
            script_name="sklearn_transformer.py",
            inputs=[
                FileInput(
                    source="/local/path/to/my/sklearn_transformer.py",
                    destination="/container/path/",
                ),
                FileInput(
                    source="s3://path/to/my/dataset/census.csv",
                    destination="/container/path/",
                    input_name="my_dataset",
                    s3_data_type=S3DataType.MANIFEST_FILE,
                    s3_input_mode=S3InputMode.FILE,
                    s3_download_mode=S3DownloadMode.CONTINUOUS,
                    s3_data_distribution_type=S3DataDistributionType.FULLY_REPLICATED,
                    s3_compression_type=S3CompressionType.NONE,
                ),
            ],
            outputs=[
                "/data/output",
                FileOutput(
                    source="/container/path/",
                    destination="s3://uri/",
                    output_name="my_output",
                    kms_key_id="arn:aws:kms:us-west-2:012345678901:key/kms-key",
                    s3_upload_mode=S3UploadMode.CONTINUOUS,
                ),
            ],
            wait=True,
            logs=False,
            job_name="my_job_name",
        )

    expected_args = {
        "inputs": [
            {
                "InputName": "input-1",
                "S3Input": {
                    "S3Uri": "mocked_s3_uri_from_upload_data",
                    "LocalPath": "/container/path/",
                    "S3DataType": "ManifestFile",
                    "S3InputMode": "File",
                    "S3DownloadMode": "Continuous",
                    "S3DataDistributionType": "FullyReplicated",
                    "S3CompressionType": "None",
                },
            },
            {
                "InputName": "my_dataset",
                "S3Input": {
                    "S3Uri": "s3://path/to/my/dataset/census.csv",
                    "LocalPath": "/container/path/",
                    "S3DataType": "ManifestFile",
                    "S3InputMode": "File",
                    "S3DownloadMode": "Continuous",
                    "S3DataDistributionType": "FullyReplicated",
                    "S3CompressionType": "None",
                },
            },
            {
                "InputName": "source",
                "S3Input": {
                    "S3Uri": "mocked_s3_uri_from_upload_data",
                    "LocalPath": "/code/source",
                    "S3DataType": "ManifestFile",
                    "S3InputMode": "File",
                    "S3DownloadMode": "Continuous",
                    "S3DataDistributionType": "FullyReplicated",
                    "S3CompressionType": "None",
                },
            },
        ],
        "outputs": [
            {
                "OutputName": "output-1",
                "S3Output": {
                    "S3Uri": os.path.join(
                        "s3://",
                        sagemaker_session.default_bucket(),
                        sklearn_processor._current_job_name,
                        "output",
                    ),
                    "LocalPath": "/data/output",
                    "S3UploadMode": "Continuous",
                },
            },
            {
                "OutputName": "my_output",
                "S3Output": {
                    "S3Uri": "s3://uri/",
                    "LocalPath": "/container/path/",
                    "S3UploadMode": "Continuous",
                    "KmsKeyId": "arn:aws:kms:us-west-2:012345678901:key/kms-key",
                },
            },
        ],
        "job_name": sklearn_processor._current_job_name,
        "resources": {
            "ClusterConfig": {
                "InstanceType": "ml.m4.xlarge",
                "InstanceCount": 1,
                "VolumeSizeInGB": 100,
            }
        },
        "stopping_condition": {"MaxRuntimeInSeconds": 3600},
        "app_specification": {
            "ImageUri": "520713654638.dkr.ecr.us-west-2.amazonaws.com/sagemaker-sklearn:0.20.0-cpu-py3",
            "ContainerArguments": ["--drop-columns", "'SelfEmployed'"],
            "ContainerEntrypoint": ["python3", "/code/source/sklearn_transformer.py"],
        },
        "environment": {"my_env_variable": 20},
        "network_config": {
            "EnableInterContainerTrafficEncryption": True,
            "EnableNetworkIsolation": True,
            "VpcConfig": {
                "SecurityGroupIds": ["my_security_group_id"],
                "Subnets": ["my_subnet_id"],
            },
        },
        "role_arn": ROLE,
        "tags": [{"Name": "my-tag", "Value": "my-tag-value"}],
    }
    sagemaker_session.process.assert_called_with(**expected_args)


def test_byo_container_with_custom_script(sagemaker_session):
    custom_processor = Processor(
        role=ROLE,
        image_uri=CUSTOM_IMAGE_URI,
        processing_instance_count=1,
        processing_instance_type="ml.m4.xlarge",
        entrypoint="sklearn_transformer.py",
        arguments=["CensusTract", "County"],
        sagemaker_session=sagemaker_session,
    )

    custom_processor.run(
        inputs=[FileInput(source="/local/path/to/my/dataset/census.csv", destination="/data/")]
    )

    expected_args = {
        "inputs": [
            {
                "InputName": "input-1",
                "S3Input": {
                    "S3Uri": "mocked_s3_uri_from_upload_data",
                    "LocalPath": "/data/",
                    "S3DataType": "ManifestFile",
                    "S3InputMode": "File",
                    "S3DownloadMode": "Continuous",
                    "S3DataDistributionType": "FullyReplicated",
                    "S3CompressionType": "None",
                },
            }
        ],
        "outputs": [],
        "job_name": custom_processor._current_job_name,
        "resources": {
            "ClusterConfig": {
                "InstanceType": "ml.m4.xlarge",
                "InstanceCount": 1,
                "VolumeSizeInGB": 30,
            }
        },
        "stopping_condition": {"MaxRuntimeInSeconds": 24 * 60 * 60},
        "app_specification": {
            "ImageUri": CUSTOM_IMAGE_URI,
            "ContainerArguments": ["CensusTract", "County"],
            "ContainerEntrypoint": "sklearn_transformer.py",
        },
        "environment": None,
        "network_config": None,
        "role_arn": ROLE,
        "tags": None,
    }
    sagemaker_session.process.assert_called_with(**expected_args)


def test_byo_container_with_baked_in_script(sagemaker_session):
    custom_processor = Processor(
        role=ROLE,
        image_uri=CUSTOM_IMAGE_URI,
        processing_instance_count=1,
        processing_instance_type="ml.m4.xlarge",
        arguments=["CensusTract", "County"],
        sagemaker_session=sagemaker_session,
    )

    custom_processor.run(
        inputs=[FileInput(source="/local/path/to/my/sklearn_transformer", destination="/code/")]
    )

    expected_args = {
        "inputs": [
            {
                "InputName": "input-1",
                "S3Input": {
                    "S3Uri": "mocked_s3_uri_from_upload_data",
                    "LocalPath": "/code/",
                    "S3DataType": "ManifestFile",
                    "S3InputMode": "File",
                    "S3DownloadMode": "Continuous",
                    "S3DataDistributionType": "FullyReplicated",
                    "S3CompressionType": "None",
                },
            }
        ],
        "outputs": [],
        "job_name": custom_processor._current_job_name,
        "resources": {
            "ClusterConfig": {
                "InstanceType": "ml.m4.xlarge",
                "InstanceCount": 1,
                "VolumeSizeInGB": 30,
            }
        },
        "stopping_condition": {"MaxRuntimeInSeconds": 24 * 60 * 60},
        "app_specification": {
            "ImageUri": CUSTOM_IMAGE_URI,
            "ContainerArguments": ["CensusTract", "County"],
        },
        "environment": None,
        "network_config": None,
        "role_arn": ROLE,
        "tags": None,
    }
    sagemaker_session.process.assert_called_with(**expected_args)


def test_sparkml_java(sagemaker_session):
    sparkml_java_processor = SparkMLJavaProcessor(
        framework_version="2.32.0",
        role=ROLE,
        processing_instance_count=1,
        processing_instance_type="ml.m4.xlarge",
        submit_app_class="org.apache.examples.SparkApp",
        sagemaker_session=sagemaker_session,
    )

    sparkml_java_processor.run(submit_app="/local/path", submit_app_jars="s3://uri")

    expected_args = {
        "inputs": [
            {
                "InputName": "submit_app",
                "S3Input": {
                    "S3Uri": "mocked_s3_uri_from_upload_data",
                    "LocalPath": "/code/submit_app",
                    "S3DataType": "ManifestFile",
                    "S3InputMode": "File",
                    "S3DownloadMode": "Continuous",
                    "S3DataDistributionType": "FullyReplicated",
                    "S3CompressionType": "None",
                },
            },
            {
                "InputName": "submit_app_jars",
                "S3Input": {
                    "S3Uri": "s3://uri",
                    "LocalPath": "/code/submit_app_jars",
                    "S3DataType": "ManifestFile",
                    "S3InputMode": "File",
                    "S3DownloadMode": "Continuous",
                    "S3DataDistributionType": "FullyReplicated",
                    "S3CompressionType": "None",
                },
            },
        ],
        "outputs": [],
        "job_name": sparkml_java_processor._current_job_name,
        "resources": {
            "ClusterConfig": {
                "InstanceType": "ml.m4.xlarge",
                "InstanceCount": 1,
                "VolumeSizeInGB": 30,
            }
        },
        "stopping_condition": {"MaxRuntimeInSeconds": 24 * 60 * 60},
        "app_specification": {
            "ImageUri": "520713654638.dkr.ecr.us-west-2.amazonaws.com/sagemaker-sparkml:2.32.0-cpu"
        },
        "environment": {"SUBMIT_APP_CLASS": "org.apache.examples.SparkApp"},
        "network_config": None,
        "role_arn": ROLE,
        "tags": None,
    }
    sagemaker_session.process.assert_called_with(**expected_args)


def test_sparkml_java_with_all_customizations(sagemaker_session):
    sparkml_java_processor = SparkMLJavaProcessor(
        framework_version="2.32.0",
        role=ROLE,
        processing_instance_count=1,
        processing_instance_type="ml.m4.xlarge",
        submit_app_class="org.apache.examples.SparkApp",
        image_uri=CUSTOM_IMAGE_URI,
        arguments=["--drop-columns", "'SelfEmployed'"],
        processing_volume_size_in_gb=100,
        processing_volume_kms_key=None,
        processing_max_runtime_in_seconds=3600,
        base_job_name="my_sparkml_java_processor",
        env={"MY_ENV_VARIABLE": 20},
        tags=[{"Name": "my-tag", "Value": "my-tag-value"}],
        network_config=NetworkConfig(
            subnets=["my_subnet_id"],
            security_group_ids=["my_security_group_id"],
            enable_network_isolation=True,
            encrypt_inter_container_traffic=True,
        ),
        sagemaker_session=sagemaker_session,
    )

    sparkml_java_processor.run(submit_app="s3://uri", submit_app_jars="/local/path")

    expected_args = {
        "inputs": [
            {
                "InputName": "submit_app",
                "S3Input": {
                    "S3Uri": "s3://uri",
                    "LocalPath": "/code/submit_app",
                    "S3DataType": "ManifestFile",
                    "S3InputMode": "File",
                    "S3DownloadMode": "Continuous",
                    "S3DataDistributionType": "FullyReplicated",
                    "S3CompressionType": "None",
                },
            },
            {
                "InputName": "submit_app_jars",
                "S3Input": {
                    "S3Uri": "mocked_s3_uri_from_upload_data",
                    "LocalPath": "/code/submit_app_jars",
                    "S3DataType": "ManifestFile",
                    "S3InputMode": "File",
                    "S3DownloadMode": "Continuous",
                    "S3DataDistributionType": "FullyReplicated",
                    "S3CompressionType": "None",
                },
            },
        ],
        "outputs": [],
        "job_name": sparkml_java_processor._current_job_name,
        "resources": {
            "ClusterConfig": {
                "InstanceType": "ml.m4.xlarge",
                "InstanceCount": 1,
                "VolumeSizeInGB": 100,
            }
        },
        "stopping_condition": {"MaxRuntimeInSeconds": 3600},
        "app_specification": {
            "ImageUri": CUSTOM_IMAGE_URI,
            "ContainerArguments": ["--drop-columns", "'SelfEmployed'"],
        },
        "environment": {"MY_ENV_VARIABLE": 20, "SUBMIT_APP_CLASS": "org.apache.examples.SparkApp"},
        "network_config": {
            "EnableInterContainerTrafficEncryption": True,
            "EnableNetworkIsolation": True,
            "VpcConfig": {
                "SecurityGroupIds": ["my_security_group_id"],
                "Subnets": ["my_subnet_id"],
            },
        },
        "role_arn": ROLE,
        "tags": [{"Name": "my-tag", "Value": "my-tag-value"}],
    }
    sagemaker_session.process.assert_called_with(**expected_args)


def test_sparkml_python(sagemaker_session):
    sparkml_py_processor = SparkMLPythonProcessor(
        framework_version="2.32.0",
        role=ROLE,
        processing_instance_count=1,
        processing_instance_type="ml.m4.xlarge",
        py_version="py3",
        sagemaker_session=sagemaker_session,
    )

    sparkml_py_processor.run(submit_app="/local/path", py_files="s3://uri")

    expected_args = {
        "inputs": [
            {
                "InputName": "submit_app",
                "S3Input": {
                    "S3Uri": "mocked_s3_uri_from_upload_data",
                    "LocalPath": "/code/submit_app",
                    "S3DataType": "ManifestFile",
                    "S3InputMode": "File",
                    "S3DownloadMode": "Continuous",
                    "S3DataDistributionType": "FullyReplicated",
                    "S3CompressionType": "None",
                },
            },
            {
                "InputName": "py_files",
                "S3Input": {
                    "S3Uri": "s3://uri",
                    "LocalPath": "/code/py_files",
                    "S3DataType": "ManifestFile",
                    "S3InputMode": "File",
                    "S3DownloadMode": "Continuous",
                    "S3DataDistributionType": "FullyReplicated",
                    "S3CompressionType": "None",
                },
            },
        ],
        "outputs": [],
        "job_name": sparkml_py_processor._current_job_name,
        "resources": {
            "ClusterConfig": {
                "InstanceType": "ml.m4.xlarge",
                "InstanceCount": 1,
                "VolumeSizeInGB": 30,
            }
        },
        "stopping_condition": {"MaxRuntimeInSeconds": 24 * 60 * 60},
        "app_specification": {
            "ImageUri": "520713654638.dkr.ecr.us-west-2.amazonaws.com/sagemaker-sparkml:2.32.0-cpu-py3"
        },
        "environment": None,
        "network_config": None,
        "role_arn": ROLE,
        "tags": None,
    }
    sagemaker_session.process.assert_called_with(**expected_args)


def test_sparkml_python_with_all_customizations(sagemaker_session):
    sparkml_py_processor = SparkMLPythonProcessor(
        framework_version="2.32.0",
        role=ROLE,
        processing_instance_count=1,
        processing_instance_type="ml.m4.xlarge",
        py_version="py3",
        image_uri=CUSTOM_IMAGE_URI,
        arguments=["--drop-columns", "'SelfEmployed'"],
        processing_volume_size_in_gb=100,
        processing_volume_kms_key=None,
        processing_max_runtime_in_seconds=3600,
        base_job_name="my_sklearn_processor",
        env={"MY_ENV_VARIABLE": 20},
        tags=[{"Name": "my-tag", "Value": "my-tag-value"}],
        network_config=NetworkConfig(
            subnets=["my_subnet_id"],
            security_group_ids=["my_security_group_id"],
            enable_network_isolation=True,
            encrypt_inter_container_traffic=True,
        ),
        sagemaker_session=sagemaker_session,
    )

    sparkml_py_processor.run(submit_app="s3://uri", py_files="/local/path")

    expected_args = {
        "inputs": [
            {
                "InputName": "submit_app",
                "S3Input": {
                    "S3Uri": "s3://uri",
                    "LocalPath": "/code/submit_app",
                    "S3DataType": "ManifestFile",
                    "S3InputMode": "File",
                    "S3DownloadMode": "Continuous",
                    "S3DataDistributionType": "FullyReplicated",
                    "S3CompressionType": "None",
                },
            },
            {
                "InputName": "py_files",
                "S3Input": {
                    "S3Uri": "mocked_s3_uri_from_upload_data",
                    "LocalPath": "/code/py_files",
                    "S3DataType": "ManifestFile",
                    "S3InputMode": "File",
                    "S3DownloadMode": "Continuous",
                    "S3DataDistributionType": "FullyReplicated",
                    "S3CompressionType": "None",
                },
            },
        ],
        "outputs": [],
        "job_name": sparkml_py_processor._current_job_name,
        "resources": {
            "ClusterConfig": {
                "InstanceType": "ml.m4.xlarge",
                "InstanceCount": 1,
                "VolumeSizeInGB": 100,
            }
        },
        "stopping_condition": {"MaxRuntimeInSeconds": 3600},
        "app_specification": {
            "ImageUri": CUSTOM_IMAGE_URI,
            "ContainerArguments": ["--drop-columns", "'SelfEmployed'"],
        },
        "environment": {"MY_ENV_VARIABLE": 20},
        "network_config": {
            "EnableInterContainerTrafficEncryption": True,
            "EnableNetworkIsolation": True,
            "VpcConfig": {
                "SecurityGroupIds": ["my_security_group_id"],
                "Subnets": ["my_subnet_id"],
            },
        },
        "role_arn": ROLE,
        "tags": [{"Name": "my-tag", "Value": "my-tag-value"}],
    }
    sagemaker_session.process.assert_called_with(**expected_args)