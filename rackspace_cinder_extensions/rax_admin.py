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
from cinder.db.sqlalchemy import models
from cinder.api.openstack import wsgi
from cinder.api import extensions
from cinder.quota import QUOTAS
from cinder.volume.driver import VolumeDriver
from sqlalchemy import and_
import lunrclient
from lunrclient import client
from lunrclient.client import LunrClient
import requests

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
authorize_list_node_volumes = extensions.extension_authorizer('rax-admin', 'list-node-volumes')
authorize_get_node = extensions.extension_authorizer('rax-admin', 'get-node')
authorize_get_volume = extensions.extension_authorizer('rax-admin', 'get-volume')
authorize_lunr_cinder_compare = extensions.extension_authorizer('rax-admin', 'lunr-cinder-compare')


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
        node = lunr_except_handler(lambda: lunr_client.nodes.get(node_id))
        return dict(node=node)

    @wsgi.action('get-volume')
    def _get_volume(self, req, body):
        """
        Returns Lunr, Cinder, and storage node GET data for a volume
        :param req: python-cinderclient request
        :param body: python-cinderclinet request's body
                   {"get-volume": {"id": "<volume_id>"}}
        :return: {"volume": {"storage_volumes": [{<storage_volumes vol1>}],
                             "storage_backups": [{<storage_backups backup 1>}, {backup 2}, ...],
                             "storage_exports": [{<storage_exports export 1>}, {export 2 ?}, ...],
                             "lunr_nodes": [{<lunr_nodes data>}],
                             "lunr_backups": [{<lunr_backups data backup 1>}, {backup 2}, ...],
                             "lunr_exports": [{<lunr_exports data export 1>}, {export 2 ?}, ...],
                             "lunr_volumes": [{<lunr_volumes data>}] }
        """
        cinder_context = req.environ['cinder.context']
        authorize_get_volume(cinder_context)
        volume_id = str(SafeDict(body).get('get-volume', {}).get('id'))
        volume = {}
        lunr_backups = []
        tenant_id = 'admin'
        # Get Lunr specific data for volume
        lunr_client = lunrclient.client.LunrClient(tenant_id)
        lunr_volumes = lunr_except_handler(lambda: lunr_client.volumes.get(volume_id))
        lunr_exports = lunr_except_handler(lambda: lunr_client.exports.get(volume_id))
        # Get Lunr node id information for direct storage node query
        lunr_nodes = lunr_except_handler(lambda: lunr_client.nodes.get(lunr_volumes['node_id']))
        node_attributes_list = ['id', 'name', 'hostname', 'code']
        node_attribute_keep = {}
        for node in lunr_nodes:
            for item in node_attributes_list:
                if item in lunr_nodes.keys():
                    node_attribute_keep.update({item: lunr_nodes[item]})
        # Add Lunr response data to volume dictionary
        volume.update(dict(lunr_volumes=[lunr_volumes]))
        if lunr_exports['code'] == 200:
            volume.update(dict(lunr_exports=[lunr_exports]))
        volume.update(dict(lunr_nodes=[node_attribute_keep]))
        # Get storage node data
        url = 'http://' + lunr_nodes['hostname'] + ':8080/' + CONF.lunr_api_version + '/admin'
        storage_client = lunrclient.client.StorageClient(url)
        storage_volumes = lunr_except_handler(lambda: storage_client.volumes.get(volume_id))
        storage_exports = lunr_except_handler(lambda: storage_client.exports.get(volume_id))
        storage_backups = lunr_except_handler(lambda: storage_client.backups.list(volume_id))
        # Add storage node response data to volume dictionary
        volume.update(dict(storage_volumes=[storage_volumes]))
        if storage_exports['code'] == 200:
            volume.update(dict(storage_exports=[storage_exports]))
        volume.update(dict(storage_backups=[storage_backups]))
        # Now that storage_backup list has been identified
        # Lunr can be queried specifically for each backup
        if len(storage_backups) > 1:
            for k, v in storage_backups.iteritems():
                if k != 'code':
                    lunr_backups.append(lunr_except_handler(lambda: lunr_client.backups.get(k)))
            volume.update(dict(lunr_backups=lunr_backups))
        else:
            # storage_backup only had a 404 error code
            # No backups to iterate over.
            volume.update(dict(lunr_backups=[storage_backups]))
        return dict(volume=volume)

    @wsgi.action('list-nodes')
    def _list_nodes(self, req, body):
        """
        Returns Lunr Nodes LIST
        :param req: python-cinderclient request
        :param body: python-cinderclient request's body
                    {"list-nodes": null}
        :return: {"nodes": [{"lunr_nodes": {<Lunr node data 1st node>},
                            {"lunr_nodes": {<Lunr node data 2nd node>},
                            {"lunr_nodes": {<Lunr node data 3rd node>}]
        """
        cinder_context = req.environ['cinder.context']
        authorize_get_node(cinder_context)
        kwargs = SafeDict(body).get('list-nodes', {})
        kwargs.update({'status': 'ACTIVE'})
        tenant_id = 'admin'
        nodes = []
        lunr_client = lunrclient.client.LunrClient(tenant_id)
        lunr_nodes_tmp = lunr_except_handler(lambda: lunr_client.nodes.list())
        if len(lunr_nodes_tmp) > 0:
            for node in lunr_nodes_tmp:
                if 'status' in node.keys() and node['status'] == 'ACTIVE':
                    nodes.append({'lunr_nodes': node})
        else:
            return dict(nodes=[lunr_nodes_tmp])
        return dict(nodes=nodes)

    @wsgi.action('list-node-volumes')
    def _list_node_volumes(self, req, body):
        """
        Returns Lunr and storage data for each volume on a specified node.
        :param req: python-cinderclient request
        :param body: python-cinderclient request's body
                    {"list-node-volumes": {"node_id": "<node_id>"}}
        :return: {"volumes": [ {"storage_volumes": {<storage volume data 1st volume>},
                                "lunr_volumes": {<Lunr volume data 1st volume>} },
                               {"storage_volumes": {<storage volume data 2nd volume>},
                                "lunr_volumes": {<Lunr volume data 2nd volume>} },
                                ...
                            ]
        """
        cinder_context = req.environ['cinder.context']
        authorize_list_node_volumes(cinder_context)
        node_id = str(SafeDict(body).get('list-node-volumes', {}).get('node_id'))
        #storage_node_id = node_id
        kwargs = SafeDict(body).get('list-node-volumes', {})
        tenant_id = 'admin'
        lunr_client = lunrclient.client.LunrClient(tenant_id)
        # Get Lunr volume information for the node id
        lunr_volumes = lunr_except_handler(lambda: lunr_client.volumes.list(**kwargs))
        lunr_volumes_tmp = []
        if len(lunr_volumes) > 0:
            for volume in lunr_volumes:
                if 'status' in volume.keys() and volume['status'] == 'ACTIVE':
                    lunr_volumes_tmp.append(volume)
        else:
            pass
        del lunr_volumes
        lunr_volumes = []
        for volume in lunr_volumes_tmp:
            lunr_volumes.append({'lunr_volumes': volume})
        volumes = lunr_volumes
        # Get storage volume information for each volume from the node
        storage_node = lunr_except_handler(lambda: lunr_client.nodes.get(**kwargs))
        kwargs.clear()
        hostname = storage_node['hostname']
        kwargs.update({'hostname': hostname})
        url = 'http://' + hostname + ':8080/' + CONF.lunr_api_version + '/admin'
        storage_client = lunrclient.client.StorageClient(url)
        storage_volumes = lunr_except_handler(lambda: storage_client.volumes.list())
        if len(volumes) > 0:
            for volume in volumes:
                for k,v in volume.items():
                    for storage_volume in storage_volumes:
                        if v['id'] == storage_volume['id']:
                            volume.update({'storage_volumes': storage_volume})
        else:
            pass
        return dict(volumes=volumes)

    @wsgi.action('list-out-rotation-nodes')
    def _list_out_rotation_nodes(self, req, body):
        """
        """
        cinder_context = req.environ['cinder.context']
        authorize_list_nodes_out_rotation(cinder_context)
        kwargs = SafeDict(body).get('list-out-rotation-nodes', {})
        tenant_id = 'admin'
        nodes = []
        lunr_client = lunrclient.client.LunrClient(tenant_id)
        lunr_nodes_tmp = lunr_except_handler(lambda: lunr_client.nodes.list(**kwargs))
        if len(lunr_nodes_tmp) > 0:
            node_list = []
            for node in lunr_nodes_tmp:
                if 'status' in node.keys() and node['status'] != 'ACTIVE':
                    node_list.append({'lunr-nodes': node})
            nodes.append(node_list)
        else:
            return dict(nodes=lunr_nodes_tmp)
        return dict(nodes=nodes)

    @wsgi.action('list-volumes')
    def _list_volumes(self, req, body):
        """
        """
        cinder_context = req.environ['cinder.context']
        authorize_list_volumes(cinder_context)
        kwargs = SafeDict(body).get('list-volumes', {})
        kwargs.update({'status': 'ACTIVE'})
        tenant_id = 'admin'
        lunr_client = lunrclient.client.LunrClient(tenant_id)
        # NEED to ADD storage or status on both Lunr and Cinder
        lunr_volumes = lunr_except_handler(lambda: lunr_client.volumes.list(**kwargs))
        return dict(lunr_volumes=lunr_volumes)

    #@wsgi.action('lunr-cinder-compare')
    #def _lunr_cinder_compare(self, req, body):
    #    """
    #
    #    :param req:
    #    :param body:
    #    :return:
    #    """
    #    cinder_context = req.environ['cinder.context']
    #    authorize_lunr_cinder_compare(cinder_context)
    #    tenant_id = 'admin'
    #    #kwargs = SafeDict(body).get('lunr-cinder-compare', {})
    #    #kwargs.update({'status': 'ACTIVE'})
    #    list_nodes_body = {"list-nodes": None}
    #    list_lunr_volumes_body = {"list-volumes": None}
    #    list_storage_volumes_body = {"list-node-volumes": None}
    #    node_data = self._list_nodes(req, body=list_nodes_body)
    #    lunr_volumes = self._list_volumes(req, body=list_lunr_volumes_body)
    #    storage_volumes = []
    #    for node in node_data['nodes']:
    #        list_node_volumes_body = {"node_id": node['lunr_nodes']['id']}
    #        storage_volumes.append(self._list_node_volumes(req, body=list_node_volumes_body))
    #    return dict(storage_volumes=storage_volumes)

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


def lunr_except_handler(client_call, **kwargs):
    try:
        call_data = client_call(**kwargs)
        call_data_code = call_data.get_code()
        if isinstance(call_data, dict):
            if isinstance(call_data_code, int):
                call_data.update({'code': call_data_code})
            elif isinstance(call_data_code, dict):
                call_data.update(call_data_code)
        elif isinstance(call_data, list) and len(call_data) > 0:
            for item in call_data:
                item.update({'code': call_data_code})
        elif isinstance(call_data, list) and len(call_data) == 0:
            call_data.append({'code': call_data_code})
        return call_data
    except lunrclient.client.LunrError as e:
        if isinstance(e.code, int):
            return {'code': e.code}
        elif isinstance(e.code, dict):
            return {'code': e.code}
        return e.code
        #return e


