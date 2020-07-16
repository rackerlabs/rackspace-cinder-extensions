#  Copyright 2013-2016 Rackspace US, Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License. You may obtain
#  a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#  WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#  License for the specific language governing permissions and limitations
#  under the License.

from oslo_log import log as logging
from webob import exc, Response

from cinder.api import extensions
from cinder.api.openstack import wsgi
from cinder import volume
from cinder import exception
from cinder import db
import lunrclient

LOG = logging.getLogger(__name__)


authorize_update_hostname = extensions.soft_extension_authorizer('volume',
                                                 'volume_actions:update_hostname')
authorize_update_node_id = extensions.soft_extension_authorizer('volume',
                                                 'volume_actions:update_node_id')
authorize_rename_lunr_volume = extensions.soft_extension_authorizer('volume',
                                                 'volume_actions:rename_lunr_volume')
authorize_lock_volume = extensions.soft_extension_authorizer('volume',
                                                 'volume_actions:lock_volume')
class VolumeAdminController(wsgi.Controller):
    def __init__(self, *args, **kwargs):
        super(wsgi.Controller, self).__init__(*args, **kwargs)
        self.volume_api = volume.API()

    def _get(self, *args, **kwargs):
        return self.volume_api.get(*args, **kwargs)

    @wsgi.action('update_hostname')
    def _update_hostname(self, req, id, body):
        """Updates hostname in cinderdb"""
        context = req.environ['cinder.context']
        if authorize_update_hostname(context):
            req.environ['cinder.context'] = context.elevated()
        volume = self._get(context, id)
        LOG.debug(body)
        new_host = body['update_hostname']
        msg = "Changing host from %s to %s"
        LOG.debug(msg % (volume['host'], new_host))
        if not new_host:
            raise exc.HTTPBadRequest("Invalid new hostname")
        try:
            self.volume_api.update(context, volume, {"host": new_host})
            volume = self._get(context, id)
        except Exception as e:
            raise exc.HTTPBadRequest(e)
        return volume

    @wsgi.action('update_node_id')
    def _update_node_id(self, req, id, body):
        """Updates nodeid in lunrdb"""
        context = req.environ['cinder.context']
        if authorize_update_node_id(context):
            req.environ['cinder.context'] = context.elevated()
        volume = self._get(context, id)
        new_node_id = body['update_node_id']
        msg = "Changing node_id to %s for volume %s"
        LOG.debug(msg % (new_node_id, id))
        if not new_node_id:
            raise exc.HTTPBadRequest("Invalid new hostname")
        try:
            lunr_client = lunrclient.client.LunrClient('admin', timeout=5)
            lunr_volume = lunr_client.volumes.get(id)
            LOG.debug('Fetched lunr volume %s ' % id)
            orig_node = lunr_client.nodes.get(lunr_volume['node_id'])
            if not orig_node:
                raise exc.HTTPNotFound("Node %s not found. " %
                                       lunr_volume['node_id'])
            new_node = lunr_client.nodes.get(new_node_id)
            if not new_node:
                raise exc.HTTPNotFound("New Node %s not found. " %
                                       new_node_id)
            lunr_client.volumes.update_vol_node_id(id, new_node_id)
        except Exception as e:
            LOG.error("Error while updating node id %s " % str(e))
            raise exc.HTTPBadRequest(e)
        return volume

    @wsgi.action('rename_lunr_volume')
    def _rename_lunr_volume(self, req, id, body):
        """Renames a logical volume at the storage"""
        context = req.environ['cinder.context']
        if authorize_rename_lunr_volume(context):
            req.environ['cinder.context'] = context.elevated()
        volume = self._get(context, id)
        if volume['status'] != 'maintenance':
            raise exc.HTTPBadRequest("Invalid volume status %s " % volume['status'])
        new_name = body['rename_lunr_volume']
        msg = "Changing Volume id from %s to %s"
        LOG.debug(msg % (id, new_name))
        try:
            lunr_client = lunrclient.client.LunrClient('admin', timeout=5)
            lunr_volume = lunr_client.volumes.get(id)
            storage_node = lunr_client.nodes.get(lunr_volume['node_id'])
            url = 'http://%s:%s' % (storage_node['hostname'], storage_node['port'])
            storage_client = lunrclient.client.StorageClient(url, timeout=5)
            try:
                storage_client.volumes.rename(id, new_name)
            except lunrclient.base.LunrHttpError as e:
                if e.code != 404:
                    raise
        except exception.NotFound as e:
            raise exc.HTTPNotFound(e)
        return Response(status_int=202)

    @wsgi.action('apply_maintenance')
    def apply_maintenance(self, req, id, body):
        """Puts/Moves volumes out of maintenance status"""
        context = req.environ['cinder.context']
        if authorize_lock_volume(context):
            req.environ['cinder.context'] = context.elevated()
        volume = self._get(context, id)
        operation = body['apply_maintenance']
        msg = "%s Volume id %s "
        LOG.debug(msg % (operation, id))
        try:
            try:
                if operation:
                    LOG.info('Updating volume status to maintenance ')
                    updates = {'migration_status': 'running',
                               'previous_status': volume['status'],
                               'status': 'maintenance'}
                    self.volume_api.db.volume_update(context, volume['id'],
                                                     updates)
                else:
                    LOG.info('Updating volume status to %s ' %
                             volume['previous_status'])
                    updates = {'migration_status': None,
                               'previous_status': volume['status'],
                               'status': volume['previous_status']}
                    self.volume_api.db.volume_update(context, volume['id'],
                                                     updates)

            except lunrclient.base.LunrHttpError as e:
                if e.code != 404:
                    raise
        except exception.NotFound as e:
            raise exc.HTTPNotFound(e)
        return Response(status_int=202)


class Volume_admin_interface(extensions.ExtensionDescriptor):
    """Elevates to admin context and
    consists of helper method to execute admin operations on a volume"""

    name = "VolumeAdmin"
    alias = "rs-vol-admin"
    namespace = ("http://docs.rackspace.com/volume/ext/rs-vol-admin/api/v2")
    updated = "2020-06-03T17:48:37+00:00"

    def get_controller_extensions(self):
        controller = VolumeAdminController()
        extension = extensions.ControllerExtension(self, 'volumes', controller)
        return [extension, ]
