"""
Manager and serializer for cloud-based storages.
"""

import datetime
import logging

from galaxy.exceptions import (
    AuthenticationFailed,
    ItemAccessibilityException,
    ObjectNotFound,
    RequestParameterInvalidException,
    RequestParameterMissingException
)
from galaxy.managers import sharable
from galaxy.util import Params

try:
    from cloudbridge.cloud.factory import CloudProviderFactory, ProviderList
    from cloudbridge.cloud.interfaces.exceptions import ProviderConnectionException
except ImportError:
    CloudProviderFactory = None
    ProviderList = None

log = logging.getLogger(__name__)

NO_CLOUDBRIDGE_ERROR_MESSAGE = (
    "Cloud ObjectStore is configured, but no CloudBridge dependency available."
    "Please install CloudBridge or modify ObjectStore configuration."
)

SUPPORTED_PROVIDERS = "{aws, azure, openstack}"

# TODO: this configuration should be set in a config file.
SINGED_URL_TTL = 3600


class CloudManager(sharable.SharableModelManager):

    def __init__(self, app, *args, **kwargs):
        super(CloudManager, self).__init__(app, *args, **kwargs)

    def _configure_provider(self, provider, credentials):
        """
        Given a provider name and required credentials, it configures and returns a cloudbridge
        connection to the provider.

        :type  provider: string
        :param provider: the name of cloud-based resource provided. A list of supported providers is given in
        `SUPPORTED_PROVIDERS` variable.

        :type  credentials: dict
        :param credentials: a dictionary containing all the credentials required to authenticated to the
        specified provider.

        :rtype: provider specific, e.g., `cloudbridge.cloud.providers.aws.provider.AWSCloudProvider` for AWS.
        :return: a cloudbridge connection to the specified provider.
        """
        missing_credentials = []
        if provider == 'aws':
            access = credentials.get('access_key', None)
            if access is None:
                missing_credentials.append('access_key')
            secret = credentials.get('secret_key', None)
            if secret is None:
                missing_credentials.append('secret_key')
            if len(missing_credentials) > 0:
                raise RequestParameterMissingException("The following required key(s) are missing from the provided "
                                                       "credentials object: {}".format(missing_credentials))

            config = {'aws_access_key': access,
                      'aws_secret_key': secret}
            connection = CloudProviderFactory().create_provider(ProviderList.AWS, config)
        elif provider == "azure":
            subscription = credentials.get('subscription_id', None)
            if subscription is None:
                missing_credentials.append('subscription_id')
            client = credentials.get('client_id', None)
            if client is None:
                missing_credentials.append('client_id')
            secret = credentials.get('secret', None)
            if secret is None:
                missing_credentials.append('secret')
            tenant = credentials.get('tenant', None)
            if tenant is None:
                missing_credentials.append('tenant')
            if len(missing_credentials) > 0:
                raise RequestParameterMissingException("The following required key(s) are missing from the provided "
                                                       "credentials object: {}".format(missing_credentials))

            config = {'azure_subscription_id': subscription,
                      'azure_client_id': client,
                      'azure_secret': secret,
                      'azure_tenant': tenant}
            connection = CloudProviderFactory().create_provider(ProviderList.AZURE, config)
        elif provider == "openstack":
            username = credentials.get('username', None)
            if username is None:
                missing_credentials.append('username')
            password = credentials.get('password', None)
            if password is None:
                missing_credentials.append('password')
            auth_url = credentials.get('auth_url', None)
            if auth_url is None:
                missing_credentials.append('auth_url')
            prj_name = credentials.get('project_name', None)
            if prj_name is None:
                missing_credentials.append('project_name')
            prj_domain_name = credentials.get('project_domain_name', None)
            if prj_domain_name is None:
                missing_credentials.append('project_domain_name')
            user_domain_name = credentials.get('user_domain_name', None)
            if user_domain_name is None:
                missing_credentials.append('user_domain_name')
            if len(missing_credentials) > 0:
                raise RequestParameterMissingException("The following required key(s) are missing from the provided "
                                                       "credentials object: {}".format(missing_credentials))
            config = {'os_username': username,
                      'os_password': password,
                      'os_auth_url': auth_url,
                      'os_project_name': prj_name,
                      'os_project_domain_name': prj_domain_name,
                      'os_user_domain_name': user_domain_name}
            connection = CloudProviderFactory().create_provider(ProviderList.OPENSTACK, config)
        else:
            raise RequestParameterInvalidException("Unrecognized provider '{}'; the following are the supported "
                                                   "providers: {}.".format(provider, SUPPORTED_PROVIDERS))

        try:
            if connection.authenticate():
                return connection
        except ProviderConnectionException as e:
            raise AuthenticationFailed("Could not authenticate to the '{}' provider. {}".format(provider, e))

    def upload(self, trans, history_id, provider, bucket, objects, credentials):
        """
        Implements the logic of uploading a file from a cloud-based storage (e.g., Amazon S3)
        and persisting it as a Galaxy dataset.

        :type  trans: galaxy.web.framework.webapp.GalaxyWebTransaction
        :param trans: Galaxy web transaction

        :type  history_id: string
        :param history_id: the (encoded) id of history to which the object should be uploaded to.

        :type  provider: string
        :param provider: the name of cloud-based resource provided. A list of supported providers is given in
        `SUPPORTED_PROVIDERS` variable.

        :type  bucket: string
        :param bucket: the name of a bucket from which data should be uploaded (e.g., a bucket name on AWS S3).

        :type  objects: list of string
        :param objects: the name of objects to be uploaded.

        :type  credentials: dict
        :param credentials: a dictionary containing all the credentials required to authenticated to the
        specified provider (e.g., {"secret_key": YOUR_AWS_SECRET_TOKEN, "access_key": YOUR_AWS_ACCESS_TOKEN}).

        :rtype:  list of galaxy.model.Dataset
        :return: a list of datasets created for the uploaded files.
        """
        if CloudProviderFactory is None:
            raise Exception(NO_CLOUDBRIDGE_ERROR_MESSAGE)

        connection = self._configure_provider(provider, credentials)
        try:
            bucket_obj = connection.object_store.get(bucket)
            if bucket_obj is None:
                raise RequestParameterInvalidException("The bucket `{}` not found.".format(bucket))
        except Exception as e:
            raise ItemAccessibilityException("Could not get the bucket `{}`: {}".format(bucket, str(e)))

        datasets = []
        for obj in objects:
            key = bucket_obj.get(obj)
            if key is None:
                raise ObjectNotFound("Could not get the object `{}`.".format(obj))

            inputs = {
                'dbkey': '?',
                'file_type': 'auto',
                'files_0|type': 'upload_dataset',
                'files_0|space_to_tab': None,
                'files_0|to_posix_lines': 'Yes',
                'files_0|NAME': obj,
                'files_0|url_paste': key.generate_url(expires_in=SINGED_URL_TTL),
            }

            params = Params(inputs, sanitize=False)
            incoming = params.__dict__
            upload_tool = trans.app.toolbox.get_tool('upload1')
            history = trans.sa_session.query(trans.app.model.History).get(history_id)
            output = upload_tool.handle_input(trans, incoming, history=history)

            job_errors = output.get('job_errors', [])
            if job_errors:
                raise ValueError('Following error occurred while uploading the given object(s) from {}: {}'.format(
                    provider, job_errors))
            else:
                for d in output['out_data']:
                    datasets.append(d[1].dataset)

        return datasets

    def download(self, trans, history_id, provider, bucket, credentials, dataset_ids=None, overwrite_existing=False):
        """
        Implements the logic of downloading dataset(s) from a given history to a given cloud-based storage
        (e.g., Amazon S3).

        :type  trans: galaxy.web.framework.webapp.GalaxyWebTransaction
        :param trans: Galaxy web transaction

        :type  history_id: string
        :param history_id: the (encoded) id of history from which the object should be downloaded.

        :type  provider: string
        :param provider: the name of cloud-based resource provided. A list of supported providers
                         is given in `SUPPORTED_PROVIDERS` variable.

        :type  bucket: string
        :param bucket: the name of a bucket to which data should be downloaded (e.g., a bucket
                       name on AWS S3).

        :type  credentials: dict
        :param credentials: a dictionary containing all the credentials required to authenticated
                            to the specified provider (e.g., {"secret_key": YOUR_AWS_SECRET_TOKEN,
                            "access_key": YOUR_AWS_ACCESS_TOKEN}).

        :type  dataset_ids: set
        :param dataset_ids: [Optional] The list of (decoded) dataset ID(s) belonging to the given
                            history which should be downloaded to the given provider. If not provided,
                            Galaxy downloads all the datasets belonging to the given history.

        :type  overwrite_existing: boolean
        :param overwrite_existing: [Optional] If set to "True", and an object with same name of the
                                   dataset to be downloaded already exist in the bucket, Galaxy replaces
                                   the existing object with the dataset to be downloaded. If set to
                                   "False", Galaxy appends datetime to the dataset name to prevent
                                   overwriting the existing object.

        :rtype:  list
        :return: A list of labels for the objects that were uploaded.
        """
        if CloudProviderFactory is None:
            raise Exception(NO_CLOUDBRIDGE_ERROR_MESSAGE)
        connection = self._configure_provider(provider, credentials)

        bucket_obj = connection.object_store.get(bucket)
        if bucket_obj is None:
            raise ObjectNotFound("Could not find the specified bucket `{}`.".format(bucket))

        history = trans.sa_session.query(trans.app.model.History).get(history_id)
        downloaded = []
        for hda in history.datasets:
            if dataset_ids is None or hda.dataset.id in dataset_ids:
                object_label = hda.name
                if overwrite_existing is False and bucket_obj.get(object_label) is not None:
                    object_label += "-" + datetime.datetime.now().strftime("%y-%m-%d-%H-%M-%S")
                created_obj = bucket_obj.create_object(object_label)
                created_obj.upload_from_file(hda.dataset.get_file_name())
                downloaded.append(object_label)
        return downloaded
