#  Copyright 2014 Rackspace Corporation.
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
try:
    from oslo_config import cfg
except ImportError:
    from oslo.config import cfg
from cinder.openstack.common import log as logging
from cinder.db.sqlalchemy.api import model_query
from cinder.db.sqlalchemy.api import backup_get
from cinder.db.sqlalchemy.api import volume_get
from cinder.db.sqlalchemy.api import volume_get_all
from cinder.db.sqlalchemy.api import volume_get_all_by_host
from cinder.db.sqlalchemy.api import volume_get_all_by_project
from cinder.db.sqlalchemy import models
from cinder.api.openstack import wsgi
from cinder.api import extensions
from cinder.quota import QUOTAS
from cinder.volume.driver import VolumeDriver
from cinder import exception
from sqlalchemy import and_
import lunrclient
from lunrclient import client
from lunrclient.client import LunrClient
from lunrclient import LunrHttpError, LunrError
import requests
import sys

lunr_opts = [
    cfg.StrOpt('lunr_api_version', default='v1.0'),
]

CONF = cfg.CONF
CONF.register_opts(lunr_opts)

LOG = logging.getLogger(__name__)
authorize_quota_usage = extensions.extension_authorizer('rax-admin', 'quota-usage')
authorize_top_usage = extensions.extension_authorizer('rax-admin', 'top-usage')
authorize_list_nodes = extensions.extension_authorizer('rax-admin', 'list-nodes')
authorize_list_nodes_out_rotation = extensions.extension_authorizer('rax-admin', 'list-nodes-out-rotation')
authorize_list_volumes = extensions.extension_authorizer('rax-admin', 'list-volumes')
authorize_list_lunr_volumes = extensions.extension_authorizer('rax-admin', 'list-lunr-volumes')
authorize_get_backup = extensions.extension_authorizer('rax-admin', 'get-backup')
authorize_get_node = extensions.extension_authorizer('rax-admin', 'get-node')
authorize_get_volume = extensions.extension_authorizer('rax-admin', 'get-volume')
authorize_status_volumes_all = extensions.extension_authorizer('rax-admin', 'status-volumes-all')


class SafeDict(dict):
    def get(self, key, default=None):
        """ If the value of the get is None, return the default, if the value
        is a dict, always return a SafeDict instead
        """
        value = dict.get(self, key, default)
        if value is None:
            value = default
        if isinstance(value, dict):
            return SafeDict(value)
        return value


class RaxAdminController(wsgi.Controller):
    """
    This controller provides a place to put rackspace stuff that doesn't, or
    can't be put anywhere else. For example, you can execute the method
    self._quota_usage() with the following

    curl -i http://cinder.rackspace.com/v1/{tenant_id}/rax-admin/action \
        -X POST -d '{"quota-usage": null}'

    """
    def __init__(self, *args, **kwargs):
        super(RaxAdminController, self).__init__(*args, **kwargs)

    @wsgi.action('quota-usage')
    def _quota_usage(self, req, body):
        """
        Return a list of all quotas in the db and how
        much of the quota is in use
        """
        # Fetch the context for this request
        context = req.environ['cinder.context']
        # Verify the user accessing this resource is allowed?
        authorize_quota_usage(context)
        rows = model_query(context, models.Quota, models.QuotaUsage,
                           read_deleted="no").\
            filter(models.QuotaUsage.project_id == models.Quota.project_id).\
            filter(models.QuotaUsage.resource == models.Quota.resource).\
            order_by(models.Quota.project_id).all()
        result = [{'project_id': quota.project_id, 'resource': quota.resource,
                   'hard_limit': quota.hard_limit, 'in_use': usage.in_use}
                  for quota, usage in rows]
        return dict(quotas=result)

    @wsgi.action('top-usage')
    def _top_usage(self, req, body):
        """
        Return a list of project_id's with the most usage
        """
        def get_limit(quota, resource_name):
            if quota:
                return quota.hard_limit
            return default_quotas.get(resource_name, 'None')

        # Get the user specified limit, else default to the top 200 projects
        limit = int(SafeDict(body).get('top-usage', {}).get('limit', 200))

        result = []
        # Get the context for this request
        context = req.environ['cinder.context']
        # Verify the user accessing this resource is allowed?
        authorize_top_usage(context)
        # Get all the quota defaults
        default_quotas = QUOTAS.get_defaults(context)
        # Fetch the projects with the most usage
        rows = model_query(context, models.QuotaUsage, read_deleted="no").\
            filter(models.QuotaUsage.resource == "gigabytes").\
            order_by(models.QuotaUsage.in_use.desc()).limit(limit).all()
        for row in rows:
            # For each project, fetch the usage and used
            quotas = model_query(context, models.QuotaUsage, models.Quota,
                                 read_deleted="no").\
                outerjoin(models.Quota, and_(models.QuotaUsage.project_id
                                             == models.Quota.project_id,
                                             models.QuotaUsage.resource
                                             == models.Quota.resource))\
                .filter(models.QuotaUsage.project_id == row.project_id)\
                .all()
            for usage, quota in quotas:
                result.append({
                    'project_id': usage.project_id,
                    'resource': usage.resource,
                    'hard_limit': get_limit(quota, usage.resource),
                    'in_use': usage.in_use})
        return dict(quotas=result)

    @wsgi.action('get-node')
    def _get_node(self, req, body):
        """
        Returns Lunr node information for a specific node
        :param req: python-cinderclient request
        :param body: python-cinderclinet request's body
                    {"get-node": {"id": "<node_id>"}}
        :return: {"node": {<node data>} }
        """
        cinder_context = req.environ['cinder.context']
        authorize_get_node(cinder_context)
        node_id = str(SafeDict(body).get('get-node', {}).get('id'))
        tenant_id = 'admin'
        lunr_client = lunrclient.client.LunrClient(tenant_id)
        node = lunr_except_handler(lambda: lunr_client.nodes.get(node_id), resource='nodes')
        return node

    @wsgi.action('get-backup')
    def _get_backup(self, req, body):
        """

        :param req:
        :param body: python-cinderclient request's body
                    {"get-backup": {"id": "<backup_id>"}}
        :return: {"backups": {<backup data>}
        """
        cinder_context = req.environ['cinder.context']
        authorize_get_backup(cinder_context)
        id = str(SafeDict(body).get('get-backup', {}).get('id'))
        backup_id = id
        backups = {}
        tenant_id = 'admin'
        lunr_client = lunrclient.client.LunrClient(tenant_id)
        lunr_backups = lunr_except_handler(lambda: lunr_client.backups.get(id), resource='backups')
        backups.update(lunr_backups=lunr_backups)
        cinder_backups = cinder_except_handler(lambda: backup_get(cinder_context, backup_id), data_name='backups')
        backups.update(cinder_backups=cinder_backups)
        return backups

    @wsgi.action('get-volume')
    def _get_volume(self, req, body):
        """
        Returns Lunr, Cinder, and storage node GET data for a volume
        :param req: python-cinderclient request
        :param body: python-cinderclinet request's body
                   {"get-volume": {"id": "<volume_id>"}}
        :return: {"volume": {"storage_volumes": {<storage_volumes vol 1>},
                             "storage_backups": [{<storage_backups backup 1>}, {backup 2}, ...],
                             "storage_exports": [{<storage_exports export 1>}, {export 2 ?}, ...],
                             "lunr_nodes": {<lunr_nodes data>},
                             "lunr_backups": [{<lunr_backups data backup 1>}, {backup 2}, ...],
                             "lunr_exports": [{<lunr_exports data export 1>}, {export 2 ?}, ...],
                             "lunr_volumes": {<lunr_volumes data>},
                             "cinder_volumes": {<cinder volume data>} }
        """
        cinder_context = req.environ['cinder.context']
        authorize_get_volume(cinder_context)
        volume_id = str(SafeDict(body).get('get-volume', {}).get('id'))
        kwargs = {"volume_id": volume_id}
        volume = {}
        tenant_id = 'admin'
        volume_resource = 'volumes'
        # Get Lunr specific data for volume
        lunr_client = lunrclient.client.LunrClient(tenant_id)
        lunr_volumes = lunr_except_handler(lambda: lunr_client.volumes.get(volume_id), resource=volume_resource)
        if 'volumes' not in lunr_volumes:
            volume.update(dict(lunr_volumes=lunr_volumes))
            volume.update({"cinder_volumes": volume_get(cinder_context, volume_id)})
            return dict(volume=volume)
        lunr_nodes = lunr_except_handler(lambda: lunr_client.nodes.get(lunr_volumes[volume_resource]['node_id']),
                                         resource='nodes')
        lunr_exports = lunr_except_handler(lambda: lunr_client.exports.get(volume_id), resource='exports')
        lunr_backups = lunr_except_handler(lambda: lunr_client.backups.list(**kwargs), resource='backups')
        # Get Lunr node id information for direct storage node query
        volume.update(dict(lunr_volumes=lunr_volumes))
        volume.update(dict(lunr_exports=lunr_exports))
        volume.update(dict(lunr_nodes=lunr_nodes))
        volume.update(dict(lunr_backups=lunr_backups))
        # Get volume data specific to the storage node resource (direct from storage node)
        url = 'http://' + lunr_nodes['nodes']['cinder_host'] + ':8080/' + CONF.lunr_api_version + '/admin'
        storage_client = lunrclient.client.StorageClient(url)
        storage_volumes = lunr_except_handler(lambda: storage_client.volumes.get(volume_id), resource='volumes')
        storage_exports = lunr_except_handler(lambda: storage_client.exports.get(volume_id), resource='exports')
        storage_backups = lunr_except_handler(lambda: storage_client.backups.list(volume_id), resource='backups')
        # Add storage node response data to volume dictionary
        volume.update(dict(storage_volumes=storage_volumes))
        volume.update(dict(storage_exports=storage_exports))
        volume.update(dict(storage_backups=storage_backups))
        volume.update(cinder_volumes=cinder_except_handler(volume_get(cinder_context, volume_id), data_name='volumes'))
        return volume

    @wsgi.action('list-nodes')
    def _list_nodes(self, req, body):
        """
        Returns Lunr Nodes LIST
        :param req: python-cinderclient request
        :param body: python-cinderclient request's body
                    {"list-nodes": null}
        :return: {"count": <count>, "nodes": [{<Lunr node data 1st node>},
                            {<Lunr node data 2nd node>},
                            {<Lunr node data 3rd node>}]}
        """
        cinder_context = req.environ['cinder.context']
        authorize_list_nodes(cinder_context)
        kwargs = SafeDict(body).get('list-nodes', {})
        tenant_id = 'admin'
        lunr_client = lunrclient.client.LunrClient(tenant_id)
        lunr_nodes = lunr_except_handler(lambda: lunr_client.nodes.list(**kwargs), resource='nodes')
        return lunr_nodes

    @wsgi.action('list-volumes')
    def _list_volumes(self, req, body):
        """
        Returns Cinder volume data for queries with Lunr kwargs filters
        :param req: python-cinderclient request
        :param body: python-cinderclient request's body
                    {"list-volumes": {"node_id": "<node_id>"}}
        :return: {"count": <count>, "volumes": [ {<volume data 1st volume>},
                                       {<volume data 2nd volume>},
                                ...
                                     ]}
        """
        cinder_context = req.environ['cinder.context']
        authorize_list_volumes(cinder_context)
        kwargs = SafeDict(body).get('list-volumes', {})
        tenant_id = 'admin'
        lunr_client = lunrclient.client.LunrClient(tenant_id)
        data_name = "volumes"
        if 'node_id' in kwargs:
            lunr_node = lunr_except_handler(lambda: lunr_client.nodes.get(**kwargs))
            hostname = lunr_node['cinder_host']
            cinder_volumes = cinder_except_handler(volume_get_all_by_host(cinder_context, host=hostname), data_name)
            return cinder_volumes
        if 'restore_of' in kwargs:
            lunr_volumes = lunr_except_handler(lambda: lunr_client.volumes.list(**kwargs))
            cinder_volumes_list = []
            if len(lunr_volumes) > 0:
                for volume in lunr_volumes:
                    if 'id' in volume:
                        cinder_volumes_list.append(volume_get(cinder_context, volume_id=volume['id']))
            if isinstance(cinder_volumes_list, list):
                cinder_volumes = {"count": len(cinder_volumes_list), data_name: cinder_volumes_list}
            else:
                cinder_volumes = {"count": 0, "volumes": cinder_volumes_list}
            return cinder_volumes
        elif 'id' in kwargs:
            cinder_volumes = cinder_except_handler(volume_get(cinder_context, volume_id=kwargs['id']), data_name)
            return cinder_volumes
        elif 'account_id' in kwargs:
            project_id = kwargs['account_id']
            kwargs.clear()
            kwargs.update({'project_id': project_id})
            cinder_volumes = cinder_except_handler(volume_get_all(cinder_context, marker=None, limit=None,
                                                                sort_key='project_id',
                                                                sort_dir='asc', filters=kwargs), data_name)
            return cinder_volumes
        else:
            cinder_volumes = cinder_except_handler(volume_get_all(cinder_context, marker=None, limit=None,
                                                                sort_key='project_id', sort_dir='asc',
                                                                filters=kwargs), data_name)
            return cinder_volumes

    @wsgi.action('list-out-rotation-nodes')
    def _list_out_rotation_nodes(self, req, body):
        """
        Returns Lunr nodes list that contains out of rotation
        Nodes.
        :param req: python cinderclient request
        :param body: python cinderclient body
        :return: {"count": <count>, "nodes": [<node 1>, <node 2]}
        """
        cinder_context = req.environ['cinder.context']
        authorize_list_nodes_out_rotation(cinder_context)
        kwargs = SafeDict(body).get('list-out-rotation-nodes', {})
        tenant_id = 'admin'
        node_list = []
        lunr_client = lunrclient.client.LunrClient(tenant_id)
        lunr_nodes_tmp = lunr_except_handler(lambda: lunr_client.nodes.list(**kwargs), resource='nodes')
        if 'nodes' in lunr_nodes_tmp and len(lunr_nodes_tmp['nodes']) > 0:
            for node in lunr_nodes_tmp['nodes']:
                if 'status' in node.keys() and node['status'] != 'ACTIVE':
                    node_list.append(node)
        else:
            nodes = {"count": len(lunr_nodes_tmp['nodes']), "nodes": lunr_nodes_tmp['nodes']}
            return nodes
        nodes = {"count": len(node_list), "nodes": node_list}
        return nodes

    @wsgi.action('list-lunr-volumes')
    def _list_lunr_volumes(self, req, body):
        """
        Returns list of Lunr volumes
        :param req: python cinderclient request
        :param body: python cinderclient body
        :return: Returns List of Lunr volumes
                {"lunr_volumes": [{<data volume 1>}, {<data volume 2>}, ... ]}
        """
        cinder_context = req.environ['cinder.context']
        authorize_list_lunr_volumes(cinder_context)
        kwargs = SafeDict(body).get('list-lunr-volumes', {})
        tenant_id = 'admin'
        lunr_client = lunrclient.client.LunrClient(tenant_id)
        lunr_volumes = lunr_except_handler(lambda: lunr_client.volumes.list(**kwargs), resource='volumes')
        return lunr_volumes

    @wsgi.action('status-volumes-all')
    def _status_volumes_all(self, req, body):
        """
        Not Completed. Currently returns get-volume data for every volume
        in environment
        :param req:
        :param body:
        :return:
        """
        cinder_context = req.environ['cinder.context']
        authorize_status_volumes_all(cinder_context)
        tenant_id = 'admin'
        kwargs = SafeDict(body).get('status-volumes-all', {})
        list_lunr_volumes_body = {"list-volumes": None}
        lunr_volumes = self._list_lunr_volumes(req, body=list_lunr_volumes_body)
        volumes = []
        for volume in lunr_volumes['lunr_volumes']:
            get_volume_body = {"get-volume": {"id": volume['id']}}
            volume_data = self._get_volume(req, body=get_volume_body)['volume']
            volumes.append(volume_data)
            del volume_data
        # Now compare Cinder/storage data with Lunr data
        # Not completed yet. Needs Cinder sqlalchemy queries
        return dict(compare_volumes=volumes)

class Rax_admin(extensions.ExtensionDescriptor):
    """Enable Rax Admin Extension"""

    name = "Rax_admin"
    alias = "rax-admin"
    namespace = "http://docs.openstack.org/volume/ext/admin-actions/api/v1.1"
    updated = "2014-07-08T00:00:00+00:00"

    def get_resources(self):
        extension = extensions.ResourceExtension(
            "rax-admin", RaxAdminController(),
            collection_actions={'action': 'POST'})
        return [extension]


def lunr_except_handler(client_call, resource='data', **kwargs):
    try:
        return_data = {}
        call_data = client_call()
        call_data_code = call_data.get_code()
        if isinstance(call_data, dict):
            if isinstance(call_data_code, int):
                return_data.update({'code': call_data_code, resource: call_data})
            elif isinstance(call_data_code, dict):
                return_data.update(call_data_code)
                return_data.update({resource: call_data})
        elif isinstance(call_data, list) and len(call_data) > 0:
            return_data.update({'code': call_data_code})
            return_data.update({'count': len(call_data)})
            return_data.update({resource: call_data})
        elif isinstance(call_data, list) and len(call_data) == 0:
            return_data.update({'code': call_data_code})
            return_data.update({'count': len(call_data)})
            return_data.update({resource: call_data})
        return return_data
    except (lunrclient.LunrError, lunrclient.LunrHttpError) as e:
        if isinstance(e.code, int):
            return {'code': e.code}
        elif isinstance(e.code, dict):
            return {'code': e.code}
        return e.code


def cinder_except_handler(client_call, data_name='data'):
    try:
        cinder_return_data = client_call()
        cinder_return_data_list = []
        if isinstance(cinder_return_data, list):
            cinder_data = {"count": len(cinder_return_data), data_name: cinder_return_data}
        elif isinstance(cinder_return_data, dict):
            cinder_return_data_list.append(cinder_return_data)
            cinder_data = {"count": len(cinder_return_data_list), data_name: cinder_return_data_list}
        else:
            cinder_return_data_list.append(cinder_return_data)
            cinder_data = {"count": 0, data_name: cinder_return_data_list}
        return cinder_data
    except exception.BackupNotFound as e:
        code = e.code
        cinder_data = {"code": code, "count": 0, data_name: e.strerror}
        return cinder_data



