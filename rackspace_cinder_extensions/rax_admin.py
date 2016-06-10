#  Copyright 2014-2016 Rackspace US, Inc.
#
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
try:
    from oslo_log import log as logging
except ImportError:
    from cinder.openstack.common import log as logging

import cinder.context
from cinder.db.sqlalchemy.api import model_query
from cinder.db.sqlalchemy.api import volume_get
from cinder.db.sqlalchemy.api import volume_get_all
from cinder.db.sqlalchemy.api import volume_get_all_by_host
from cinder.db.sqlalchemy.api import volume_get_all_by_project
from cinder.db.sqlalchemy import models
from cinder.api.openstack import wsgi
from cinder.api import extensions
from cinder.i18n import _
from cinder.quota import QUOTAS
from cinder.volume.driver import VolumeDriver
from sqlalchemy import and_
import lunrclient
from lunrclient import client
from lunrclient.client import LunrClient
import requests
from webob import exc


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
        node = lunr_except_handler(lambda: lunr_client.nodes.get(node_id))
        return dict(node=node)

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
        volume = {}
        lunr_backups = []
        tenant_id = 'admin'
        # Get Lunr specific data for volume
        lunr_client = lunrclient.client.LunrClient(tenant_id)
        lunr_volumes = lunr_except_handler(lambda: lunr_client.volumes.get(volume_id))
        lunr_exports = lunr_except_handler(lambda: lunr_client.exports.get(volume_id))
        # Get Lunr node id information for direct storage node query
        lunr_nodes = lunr_except_handler(lambda: lunr_client.nodes.get(lunr_volumes['node_id']))
        volume.update(dict(lunr_volumes=lunr_volumes))
        if lunr_exports['code'] == 200:
            volume.update(dict(lunr_exports=[lunr_exports]))
        volume.update(dict(lunr_nodes=lunr_nodes))
        # Get volume data specific to the storage node resource (direct from storage node)
        url = 'http://' + lunr_nodes['hostname'] + ':8080/' + CONF.lunr_api_version + '/admin'
        storage_client = lunrclient.client.StorageClient(url)
        storage_volumes = lunr_except_handler(lambda: storage_client.volumes.get(volume_id))
        storage_exports = lunr_except_handler(lambda: storage_client.exports.get(volume_id))
        storage_backups = lunr_except_handler(lambda: storage_client.backups.list(volume_id))
        # Add storage node response data to volume dictionary
        volume.update(dict(storage_volumes=storage_volumes))
        if storage_exports['code'] == 200:
            volume.update(dict(storage_exports=[storage_exports]))
        volume.update(dict(storage_backups=[storage_backups]))
        # Now that storage_backup list has been identified
        # Lunr can be queried specifically for each backup
        # *** Should actually use lunr backups and query by kwargs
        # that contain account_id and volume id
        if len(storage_backups) > 1:
            for k, v in storage_backups.iteritems():
                if k != 'code':
                    lunr_backups.append(lunr_except_handler(lambda: lunr_client.backups.get(k)))
            volume.update(dict(lunr_backups=lunr_backups))
        else:
            # storage_backup only had a 404 error code
            # No backups to iterate over.
            volume.update(dict(lunr_backups=[]))
        # Now add cinder volume data to the volume dictionary
        volume.update({"cinder_volumes": volume_get(cinder_context, volume_id)})
        return dict(volume=volume)

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
        lunr_nodes = lunr_except_handler(lambda: lunr_client.nodes.list(**kwargs))
        nodes = {"count": len(lunr_nodes), "nodes": lunr_nodes}
        return nodes

    @wsgi.action('list-volumes')
    def _list_volumes(self, req, body):
        """
        Returns Cinder volume lists for specific query params
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
        admin_context = cinder.context.get_admin_context()
        kwargs = SafeDict(body).get('list-volumes', {})
        tenant_id = 'admin'
        lunr_client = lunrclient.client.LunrClient(tenant_id)
        data_name = "volumes"
        if 'node_id' in kwargs:
            lunr_node = lunr_except_handler(lambda: lunr_client.nodes.get(node_id=kwargs['node_id']))
            hostname = lunr_node['cinder_host']
            cinder_volumes = cinder_list_handler(volume_get_all_by_host(admin_context, host=hostname), data_name)
            return cinder_volumes
        if 'restore_of' in kwargs:
            lunr_volumes = lunr_except_handler(lambda: lunr_client.volumes.list(restore_of=kwargs['restore_of']))
            cinder_volumes_list = []
            if len(lunr_volumes) > 0:
                for volume in lunr_volumes:
                    if 'id' in volume:
                        cinder_volumes_list.append(volume_get(admin_context, volume_id=volume['id']))
            if isinstance(cinder_volumes_list, list):
                cinder_volumes = {"count": len(cinder_volumes_list), data_name: cinder_volumes_list}
            else:
                cinder_volumes = {"count": 0, "volumes": cinder_volumes_list}
            return cinder_volumes
        elif 'id' in kwargs:
            cinder_volumes = cinder_list_handler(volume_get(admin_context, volume_id=kwargs['id']), data_name)
            return cinder_volumes
        elif 'account_id' in kwargs:
            filters = {'project_id': kwargs['account_id']}
            cinder_volumes = cinder_list_handler(volume_get_all(admin_context, marker=None, limit=None,
                                                                sort_keys=['project_id'],
                                                                sort_dirs=['asc'], filters=filters), data_name)
            return cinder_volumes
        elif 'host' in kwargs:
            filters = {'host': kwargs['host']}
            cinder_volumes = cinder_list_handler(volume_get_all(admin_context, marker=None, limit=None,
                                                                sort_keys=['project_id'], sort_dirs=['asc'],
                                                                filters=filters), data_name)
            return cinder_volumes
        raise exc.HTTPBadRequest(
            explanation=_("Must specify node_id, restore_of, id, account_id, or host"))

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
        lunr_nodes_tmp = lunr_except_handler(lambda: lunr_client.nodes.list(**kwargs))
        if len(lunr_nodes_tmp) > 0:
            for node in lunr_nodes_tmp:
                if 'status' in node.keys() and node['status'] != 'ACTIVE':
                    node_list.append(node)
        else:
            nodes = {"count": len(lunr_nodes_tmp), "nodes": lunr_nodes_tmp}
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
        lunr_volumes_data = lunr_except_handler(lambda: lunr_client.volumes.list(**kwargs))
        lunr_volumes = {"count": len(lunr_volumes_data), "volumes": lunr_volumes_data}
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


def cinder_list_handler(client_call, data_name):
    cinder_return_data = client_call
    cinder_return_data_list = []
    if isinstance(cinder_return_data, list):
        cinder_data = {"count": len(cinder_return_data), data_name: cinder_return_data}
    elif dict(cinder_return_data):
        cinder_return_data_list.append(cinder_return_data)
        cinder_data = {"count": len(cinder_return_data_list), data_name: cinder_return_data_list}
    else:
        cinder_return_data_list.append(cinder_return_data)
        cinder_data = {"count": 0, data_name: cinder_return_data_list}
    return cinder_data


